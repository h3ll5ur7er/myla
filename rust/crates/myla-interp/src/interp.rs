//! The tree-walking interpreter: the reference semantics of Myla.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use myla_runtime::concurrency::{Channel, Task};
use myla_runtime::IntKind;
use myla_sema::Analyzed;
use myla_syntax::ast::*;
use myla_syntax::span::Span;

use crate::control::{Control, Eval, RuntimeError};
use crate::env::Env;
use crate::lit;
use crate::value::{ActorHandle, Closure, EnumVal, OrderedMap, Partial, StructVal, Value};

mod builtins;
mod ops;
mod place;

#[derive(Clone)]
pub struct Interp {
    inner: Arc<Inner>,
}

struct Inner {
    a: Arc<Analyzed>,
    consts: Mutex<HashMap<String, Value>>,
    args: Vec<String>,
}

impl Interp {
    pub fn new(a: Arc<Analyzed>, args: Vec<String>) -> Interp {
        Interp {
            inner: Arc::new(Inner {
                a,
                consts: Mutex::new(HashMap::new()),
                args,
            }),
        }
    }

    fn a(&self) -> &Analyzed {
        &self.inner.a
    }

    fn program_args(&self) -> Vec<String> {
        self.inner.args.clone()
    }

    /// Run the program's entry point; returns the process exit code.
    pub fn run(&self) -> Result<i32, RuntimeError> {
        let entry = match &self.a().entry {
            Some(name) => name.clone(),
            None => return Err(RuntimeError::new("no entry point (`#main` or `main`)")),
        };
        let decl = self.a().functions.get(&entry).unwrap().clone();
        match self.call_function(&decl, Vec::new()) {
            Ok(_) => Ok(0),
            Err(Control::Exit(code)) => Ok(code),
            Err(Control::Error(e)) => Err(e),
            Err(_) => Ok(0),
        }
    }

    /// Evaluate a top-level function as a `#test` would: call with args, return value.
    pub fn eval_call_named(&self, func: &str, args: Vec<Value>) -> Eval<Value> {
        let decl = self
            .a()
            .functions
            .get(func)
            .ok_or_else(|| RuntimeError::new(format!("unknown function `{func}`")))?
            .clone();
        self.call_function(&decl, args)
    }

    pub fn eval_const_expr(&self, expr: &Expr) -> Eval<Value> {
        let mut env = Env::new();
        self.eval_expr(expr, &mut env)
    }

    // --- function calls ---

    fn call_function(&self, decl: &Arc<FunDecl>, args: Vec<Value>) -> Eval<Value> {
        if decl.is_async {
            // Async functions run as a spawned task; `await` joins them.
            let me = self.clone();
            let decl = decl.clone();
            let task = Task::spawn(move || {
                me.invoke_body(&decl, args).unwrap_or(Value::Unit)
            });
            return Ok(Value::Task(task));
        }
        self.invoke_body(decl, args)
    }

    fn invoke_body(&self, decl: &FunDecl, args: Vec<Value>) -> Eval<Value> {
        let mut env = Env::new();
        let mut ai = args.into_iter();
        for p in &decl.params {
            let v = ai.next().unwrap_or(Value::Unit);
            env.declare(&p.name, v);
        }
        match self.eval_block(&decl.body, &mut env) {
            Ok(v) => Ok(v),
            Err(Control::Return(v)) => Ok(v),
            Err(other) => Err(other),
        }
    }

    fn call_value(&self, callee: Value, args: Vec<Value>, span: Span) -> Eval<Value> {
        match callee {
            Value::Func(decl) => self.call_function(&decl, args),
            Value::Builtin(name) => self.call_builtin(name, args, span),
            Value::Closure(c) => self.call_closure(&c, args),
            Value::Partial(p) => {
                let mut filled = Vec::new();
                let mut provided = args.into_iter();
                for slot in &p.slots {
                    match slot {
                        Some(v) => filled.push(v.clone()),
                        None => filled.push(provided.next().unwrap_or(Value::Unit)),
                    }
                }
                self.call_value(p.callee.clone(), filled, span)
            }
            other => Err(Control::Error(RuntimeError::at(
                format!("value of type `{}` is not callable", other.type_name()),
                span,
            ))),
        }
    }

    fn call_closure(&self, c: &Closure, args: Vec<Value>) -> Eval<Value> {
        let mut env = Env::from_map(c.captured.clone());
        env.push();
        let mut ai = args.into_iter();
        for p in &c.params {
            env.declare(&p.name, ai.next().unwrap_or(Value::Unit));
        }
        match self.eval_expr(&c.body, &mut env) {
            Ok(v) => Ok(v),
            Err(Control::Return(v)) => Ok(v),
            Err(other) => Err(other),
        }
    }

    // --- blocks & statements ---

    fn eval_block(&self, block: &Block, env: &mut Env) -> Eval<Value> {
        env.push();
        let result = (|| {
            for stmt in &block.stmts {
                self.exec_stmt(stmt, env)?;
            }
            if let Some(tail) = &block.tail {
                self.eval_expr(tail, env)
            } else {
                Ok(Value::Unit)
            }
        })();
        env.pop();
        result
    }

    fn exec_stmt(&self, stmt: &Stmt, env: &mut Env) -> Eval<()> {
        match &stmt.kind {
            StmtKind::Let { name, init, .. } => {
                let v = self.eval_expr(init, env)?;
                env.declare(name, v);
                Ok(())
            }
            StmtKind::Assign { target, op, value } => {
                let rhs = self.eval_expr(value, env)?;
                let new = match op {
                    None => rhs,
                    Some(binop) => {
                        let cur = self.eval_expr(target, env)?;
                        self.binary(*binop, cur, rhs, stmt.span)?
                    }
                };
                self.assign_place(target, new, env)
            }
            StmtKind::Expr(e) => {
                self.eval_expr(e, env)?;
                Ok(())
            }
            StmtKind::Return(value) => {
                let v = match value {
                    Some(e) => self.eval_expr(e, env)?,
                    None => Value::Unit,
                };
                Err(Control::Return(v))
            }
            StmtKind::Break => Err(Control::Break),
            StmtKind::Continue => Err(Control::Continue),
            StmtKind::While { cond, body } => {
                loop {
                    let c = self.eval_expr(cond, env)?;
                    if !c.as_bool().unwrap_or(false) {
                        break;
                    }
                    match self.eval_block(body, env) {
                        Ok(_) => {}
                        Err(Control::Break) => break,
                        Err(Control::Continue) => continue,
                        Err(other) => return Err(other),
                    }
                }
                Ok(())
            }
            StmtKind::For { var, iter, body } => self.exec_for(var, iter, body, env),
            StmtKind::Select(arms) => self.exec_select(arms, env),
        }
    }

    fn exec_for(&self, var: &str, iter: &Expr, body: &Block, env: &mut Env) -> Eval<()> {
        let items: Vec<Value> = match &iter.kind {
            ExprKind::Range { start, end } => {
                let s = self.eval_expr(start, env)?;
                let e = self.eval_expr(end, env)?;
                let (s, k) = as_int(&s, iter.span)?;
                let (e, _) = as_int(&e, iter.span)?;
                (s..e).map(|i| Value::int(i, k)).collect()
            }
            _ => {
                let v = self.eval_expr(iter, env)?;
                match v {
                    Value::List(xs) => (*xs).clone(),
                    Value::Map(m) => m.keys(),
                    Value::Str(s) => s.chars().map(Value::Char).collect(),
                    other => {
                        return Err(Control::Error(RuntimeError::at(
                            format!("cannot iterate over `{}`", other.type_name()),
                            iter.span,
                        )))
                    }
                }
            }
        };
        for item in items {
            env.push();
            env.declare(var, item);
            let r = self.eval_block(body, env);
            env.pop();
            match r {
                Ok(_) => {}
                Err(Control::Break) => break,
                Err(Control::Continue) => continue,
                Err(other) => return Err(other),
            }
        }
        Ok(())
    }

    // --- expressions ---

    fn eval_expr(&self, expr: &Expr, env: &mut Env) -> Eval<Value> {
        match &expr.kind {
            ExprKind::Int { text } => {
                let (v, k) = lit::parse_int(text);
                Ok(Value::Int(v, k))
            }
            ExprKind::Float { text } => {
                let (v, b) = lit::parse_float(text);
                Ok(Value::Float(v, b))
            }
            ExprKind::Str(s) => Ok(Value::Str(Arc::from(s.as_str()))),
            ExprKind::Char(c) => Ok(Value::Char(*c)),
            ExprKind::Bool(b) => Ok(Value::Bool(*b)),
            ExprKind::FStr(parts) => {
                let mut out = String::new();
                for p in parts {
                    match p {
                        FStrPart::Lit(s) => out.push_str(s),
                        FStrPart::Expr(e) => out.push_str(&self.eval_expr(e, env)?.display()),
                    }
                }
                Ok(Value::Str(Arc::from(out.as_str())))
            }
            ExprKind::Name(n) => self.eval_name(n, expr.span, env),
            ExprKind::SelfExpr => env
                .get("self")
                .ok_or_else(|| Control::Error(RuntimeError::at("`self` is not bound", expr.span))),
            ExprKind::Hole => Err(Control::Error(RuntimeError::at(
                "`_` placeholder used outside a call",
                expr.span,
            ))),
            ExprKind::Unary { op, expr: inner } => {
                let v = self.eval_expr(inner, env)?;
                self.unary(*op, v, expr.span)
            }
            ExprKind::Binary { op, lhs, rhs } => {
                // short-circuit logical operators
                if matches!(op, BinOp::And | BinOp::Or) {
                    let l = self.eval_expr(lhs, env)?.as_bool().ok_or_else(|| {
                        Control::Error(RuntimeError::at("expected bool", lhs.span))
                    })?;
                    match op {
                        BinOp::And if !l => return Ok(Value::Bool(false)),
                        BinOp::Or if l => return Ok(Value::Bool(true)),
                        _ => {}
                    }
                    let r = self.eval_expr(rhs, env)?.as_bool().ok_or_else(|| {
                        Control::Error(RuntimeError::at("expected bool", rhs.span))
                    })?;
                    return Ok(Value::Bool(r));
                }
                let l = self.eval_expr(lhs, env)?;
                let r = self.eval_expr(rhs, env)?;
                self.binary(*op, l, r, expr.span)
            }
            ExprKind::Call { callee, args } => self.eval_call(callee, args, expr.span, env),
            ExprKind::MethodCall { recv, method, args } => {
                self.eval_method_call(recv, method, args, expr.span, env)
            }
            ExprKind::Field { recv, name } => {
                let v = self.eval_expr(recv, env)?;
                self.field_access(v, name, expr.span)
            }
            ExprKind::Index { recv, index } => {
                let base = self.eval_expr(recv, env)?;
                let idx = self.eval_expr(index, env)?;
                self.index(base, idx, expr.span)
            }
            ExprKind::StructLit { name, fields } => self.eval_struct_lit(name, fields, expr.span, env),
            ExprKind::ListLit(xs) => {
                let mut out = Vec::with_capacity(xs.len());
                for e in xs {
                    out.push(self.eval_expr(e, env)?);
                }
                Ok(Value::List(Arc::new(out)))
            }
            ExprKind::MapLit(entries) => {
                let mut m = OrderedMap::new();
                for (k, v) in entries {
                    let kv = self.eval_expr(k, env)?;
                    let vv = self.eval_expr(v, env)?;
                    m.insert(kv, vv);
                }
                Ok(Value::Map(Arc::new(m)))
            }
            ExprKind::TupleLit(xs) => {
                let mut out = Vec::with_capacity(xs.len());
                for e in xs {
                    out.push(self.eval_expr(e, env)?);
                }
                Ok(Value::Tuple(Arc::new(out)))
            }
            ExprKind::Lambda { params, body } => Ok(Value::Closure(Arc::new(Closure {
                params: params.clone(),
                body: Arc::new((**body).clone()),
                captured: env.flatten(),
                is_async: false,
            }))),
            ExprKind::If { cond, then, otherwise } => {
                let c = self.eval_expr(cond, env)?;
                if c.as_bool().unwrap_or(false) {
                    self.eval_block(then, env)
                } else if let Some(else_e) = otherwise {
                    self.eval_expr(else_e, env)
                } else {
                    Ok(Value::Unit)
                }
            }
            ExprKind::Match { scrutinee, arms } => {
                let v = self.eval_expr(scrutinee, env)?;
                self.eval_match(v, arms, expr.span, env)
            }
            ExprKind::Block(b) => self.eval_block(b, env),
            ExprKind::Range { .. } => Err(Control::Error(RuntimeError::at(
                "ranges are only valid in `for` loops",
                expr.span,
            ))),
            ExprKind::Cast { expr: inner, ty } => {
                let v = self.eval_expr(inner, env)?;
                self.cast(v, ty, expr.span)
            }
            ExprKind::Pipe { lhs, rhs } => self.eval_pipe(lhs, rhs, expr.span, env),
            ExprKind::Try(inner) => {
                let v = self.eval_expr(inner, env)?;
                self.eval_try(v, expr.span)
            }
            ExprKind::Await(inner) => {
                let v = self.eval_expr(inner, env)?;
                match v {
                    Value::Task(t) => Ok(t.join()),
                    other => Ok(other),
                }
            }
            ExprKind::Spawn(inner) => self.eval_spawn(inner, env),
        }
    }

    fn eval_name(&self, name: &str, span: Span, env: &mut Env) -> Eval<Value> {
        if let Some(v) = env.get(name) {
            return Ok(v);
        }
        if name == "_" {
            return Ok(Value::Unit);
        }
        if let Some(c) = self.a().consts.get(name) {
            if let Some(v) = self.inner.consts.lock().unwrap().get(name) {
                return Ok(v.clone());
            }
            let v = self.eval_const_expr(&c.value)?;
            self.inner.consts.lock().unwrap().insert(name.to_string(), v.clone());
            return Ok(v);
        }
        if let Some(f) = self.a().functions.get(name) {
            return Ok(Value::Func(f.clone()));
        }
        // nullary enum variant (e.g. `None`)
        if let Some(en) = self.a().variant_to_enum.get(name) {
            return Ok(Value::Enum(Arc::new(EnumVal {
                enum_name: en.clone(),
                variant: name.to_string(),
                payload: Vec::new(),
            })));
        }
        if let Some(b) = builtins::builtin_name(name) {
            return Ok(Value::Builtin(b));
        }
        Err(Control::Error(RuntimeError::at(
            format!("unknown name `{name}`"),
            span,
        )))
    }

    fn eval_call(&self, callee: &Expr, args: &[Expr], span: Span, env: &mut Env) -> Eval<Value> {
        // Unqualified enum-variant construction: `Some(x)`, `Ok(v)`, user variants.
        if let ExprKind::Name(n) = &callee.kind {
            if let Some(en) = self.a().variant_to_enum.get(n).cloned() {
                let payload = self.eval_args(args, env)?;
                return Ok(Value::Enum(Arc::new(EnumVal {
                    enum_name: en,
                    variant: n.clone(),
                    payload,
                })));
            }
        }
        // Partial application if any `_` holes are present.
        if args.iter().any(|a| matches!(a.kind, ExprKind::Hole)) {
            let callee_val = self.eval_expr(callee, env)?;
            let mut slots = Vec::new();
            for a in args {
                if matches!(a.kind, ExprKind::Hole) {
                    slots.push(None);
                } else {
                    slots.push(Some(self.eval_expr(a, env)?));
                }
            }
            return Ok(Value::Partial(Arc::new(Partial {
                callee: callee_val,
                slots,
            })));
        }
        let callee_val = self.eval_expr(callee, env)?;
        let arg_vals = self.eval_args(args, env)?;
        self.call_value(callee_val, arg_vals, span)
    }

    fn eval_args(&self, args: &[Expr], env: &mut Env) -> Eval<Vec<Value>> {
        let mut out = Vec::with_capacity(args.len());
        for a in args {
            out.push(self.eval_expr(a, env)?);
        }
        Ok(out)
    }

    fn eval_struct_lit(
        &self,
        name: &str,
        fields: &[(String, Expr)],
        span: Span,
        env: &mut Env,
    ) -> Eval<Value> {
        // Actor construction shares struct-literal syntax.
        if let Some(actor) = self.a().actors.get(name).cloned() {
            let mut state = HashMap::new();
            for (fname, fexpr) in fields {
                state.insert(fname.clone(), self.eval_expr(fexpr, env)?);
            }
            return Ok(Value::Actor(Arc::new(ActorHandle {
                name: name.to_string(),
                decl: actor,
                state: Mutex::new(state),
            })));
        }
        let mut out = Vec::with_capacity(fields.len());
        for (fname, fexpr) in fields {
            out.push((fname.clone(), self.eval_expr(fexpr, env)?));
        }
        let _ = span;
        Ok(Value::Struct(Arc::new(StructVal {
            name: name.to_string(),
            fields: out,
        })))
    }

    fn field_access(&self, v: Value, name: &str, span: Span) -> Eval<Value> {
        match v {
            Value::Struct(s) => s
                .get(name)
                .cloned()
                .ok_or_else(|| Control::Error(RuntimeError::at(format!("no field `{name}`"), span))),
            other => Err(Control::Error(RuntimeError::at(
                format!("type `{}` has no field `{name}`", other.type_name()),
                span,
            ))),
        }
    }

    // --- pattern matching ---

    fn eval_match(&self, v: Value, arms: &[MatchArm], span: Span, env: &mut Env) -> Eval<Value> {
        for arm in arms {
            env.push();
            let matched = bind_pattern(&arm.pattern, &v, env);
            if matched {
                let guard_ok = match &arm.guard {
                    Some(g) => self.eval_expr(g, env)?.as_bool().unwrap_or(false),
                    None => true,
                };
                if guard_ok {
                    let r = self.eval_expr(&arm.body, env);
                    env.pop();
                    return r;
                }
            }
            env.pop();
        }
        Err(Control::Error(RuntimeError::at("no match arm matched", span)))
    }

    // --- pipeline & try ---

    fn eval_pipe(&self, lhs: &Expr, rhs: &Expr, span: Span, env: &mut Env) -> Eval<Value> {
        let left = self.eval_expr(lhs, env)?;
        // `x |> f(a, b)` splices x as the first argument
        match &rhs.kind {
            ExprKind::Call { callee, args } => {
                let callee_val = self.eval_expr(callee, env)?;
                let mut arg_vals = vec![left];
                for a in args {
                    arg_vals.push(self.eval_expr(a, env)?);
                }
                self.call_value(callee_val, arg_vals, span)
            }
            _ => {
                let f = self.eval_expr(rhs, env)?;
                self.call_value(f, vec![left], span)
            }
        }
    }

    fn eval_try(&self, v: Value, span: Span) -> Eval<Value> {
        match v {
            Value::Enum(e) => match (e.enum_name.as_str(), e.variant.as_str()) {
                ("Result", "Ok") | ("Option", "Some") => {
                    Ok(e.payload.first().cloned().unwrap_or(Value::Unit))
                }
                ("Result", "Err") => Err(Control::Return(Value::Enum(e))),
                ("Option", "None") => Err(Control::Return(Value::Enum(e))),
                _ => Err(Control::Error(RuntimeError::at(
                    "`?` requires an Option or Result",
                    span,
                ))),
            },
            _ => Err(Control::Error(RuntimeError::at(
                "`?` requires an Option or Result",
                span,
            ))),
        }
    }

    // --- concurrency ---

    fn eval_spawn(&self, inner: &Expr, env: &mut Env) -> Eval<Value> {
        let captured = env.flatten();
        let me = self.clone();
        let body = inner.clone();
        let task = Task::spawn(move || {
            let mut env = Env::from_map(captured);
            me.eval_expr(&body, &mut env).unwrap_or(Value::Unit)
        });
        Ok(Value::Task(task))
    }

    fn exec_select(&self, arms: &[SelectArm], env: &mut Env) -> Eval<()> {
        use myla_runtime::concurrency::Select;
        let mut channels = Vec::new();
        for arm in arms {
            match self.eval_expr(&arm.channel, env)? {
                Value::Chan(c) => channels.push(c),
                other => {
                    return Err(Control::Error(RuntimeError::at(
                        format!("`select` arm is not a channel (got `{}`)", other.type_name()),
                        arm.channel.span,
                    )))
                }
            }
        }
        let mut sel = Select::new();
        for c in &channels {
            sel.recv(&c.rx);
        }
        let oper = sel.select();
        let i = oper.index();
        let value = oper
            .recv(&channels[i].rx)
            .map_err(|_| Control::Error(RuntimeError::new("select channel closed")))?;
        env.push();
        if let Some(b) = &arms[i].binding {
            env.declare(b, value);
        }
        let r = self.eval_block(&arms[i].body, env);
        env.pop();
        r.map(|_| ())
    }

    fn make_channel(&self) -> Value {
        Value::Chan(Channel::<Value>::unbounded())
    }
}

// --- helpers ---

pub(crate) fn as_int(v: &Value, span: Span) -> Eval<(i128, IntKind)> {
    match v {
        Value::Int(i, k) => Ok((*i, *k)),
        other => Err(Control::Error(RuntimeError::at(
            format!("expected an integer, found `{}`", other.type_name()),
            span,
        ))),
    }
}

fn bind_pattern(pat: &Pattern, v: &Value, env: &mut Env) -> bool {
    match &pat.kind {
        PatternKind::Wildcard => true,
        PatternKind::Binding(name) => {
            env.declare(name, v.clone());
            true
        }
        PatternKind::Int(text) => {
            let (iv, _) = lit::parse_int(text);
            matches!(v, Value::Int(x, _) if *x == iv)
        }
        PatternKind::Bool(b) => matches!(v, Value::Bool(x) if x == b),
        PatternKind::Str(s) => matches!(v, Value::Str(x) if x.as_ref() == s.as_str()),
        PatternKind::Char(c) => matches!(v, Value::Char(x) if x == c),
        PatternKind::Tuple(subs) => match v {
            Value::Tuple(xs) | Value::List(xs) => {
                subs.len() == xs.len()
                    && subs.iter().zip(xs.iter()).all(|(p, e)| bind_pattern(p, e, env))
            }
            _ => false,
        },
        PatternKind::Variant { path, sub } => {
            let variant = path.last().unwrap();
            match v {
                Value::Enum(e) => {
                    if &e.variant != variant {
                        return false;
                    }
                    sub.len() == e.payload.len()
                        && sub
                            .iter()
                            .zip(e.payload.iter())
                            .all(|(p, e)| bind_pattern(p, e, env))
                }
                _ => false,
            }
        }
        PatternKind::Struct { name, fields } => match v {
            Value::Struct(s) => {
                if !name.ends_with(&s.name) && name != &s.name {
                    // allow bare or qualified struct names
                }
                fields.iter().all(|(fname, fpat)| {
                    s.get(fname).map(|fv| bind_pattern(fpat, fv, env)).unwrap_or(false)
                })
            }
            _ => false,
        },
        PatternKind::Or(alts) => alts.iter().any(|p| bind_pattern(p, v, env)),
    }
}
