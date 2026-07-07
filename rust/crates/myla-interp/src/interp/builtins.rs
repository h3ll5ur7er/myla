//! Built-in free functions, method dispatch, and the standard-library surface
//! (rich I/O, processes, time) backed by Rust's `std`.

use std::io::Write as _;
use std::sync::Arc;

use myla_runtime::IntKind;
use myla_syntax::ast::{Expr, ExprKind, FunDecl};
use myla_syntax::span::Span;

use crate::control::{Control, Eval, RuntimeError};
use crate::env::Env;
use crate::value::{EnumVal, Value};

use super::Interp;

const BUILTINS: &[&str] = &[
    "print", "println", "eprint", "eprintln", "format", "len", "assert", "panic",
    "unreachable", "exit", "chan", "make_chan", "args", "read_file", "write_file",
    "append_file", "file_exists", "remove_file", "env_var", "now_millis",
    "sleep_millis", "run", "read_line", "int_to_str", "str_to_int", "abs",
];

pub(super) fn builtin_name(name: &str) -> Option<&'static str> {
    BUILTINS.iter().copied().find(|b| *b == name)
}

fn ok(v: Value) -> Value {
    Value::Enum(Arc::new(EnumVal {
        enum_name: "Result".into(),
        variant: "Ok".into(),
        payload: vec![v],
    }))
}
fn err(msg: impl Into<String>) -> Value {
    Value::Enum(Arc::new(EnumVal {
        enum_name: "Result".into(),
        variant: "Err".into(),
        payload: vec![Value::Str(Arc::from(msg.into().as_str()))],
    }))
}
fn some(v: Value) -> Value {
    Value::Enum(Arc::new(EnumVal {
        enum_name: "Option".into(),
        variant: "Some".into(),
        payload: vec![v],
    }))
}
fn none() -> Value {
    Value::Enum(Arc::new(EnumVal {
        enum_name: "Option".into(),
        variant: "None".into(),
        payload: vec![],
    }))
}

fn rt(msg: impl Into<String>, span: Span) -> Control {
    Control::Error(RuntimeError::at(msg, span))
}

impl Interp {
    pub(super) fn call_builtin(&self, name: &str, args: Vec<Value>, span: Span) -> Eval<Value> {
        let arg = |i: usize| args.get(i).cloned().unwrap_or(Value::Unit);
        match name {
            "print" | "println" => {
                let mut out = std::io::stdout().lock();
                let _ = writeln!(out, "{}", arg(0).display());
                Ok(Value::Unit)
            }
            "eprint" => {
                eprint!("{}", arg(0).display());
                Ok(Value::Unit)
            }
            "eprintln" => {
                eprintln!("{}", arg(0).display());
                Ok(Value::Unit)
            }
            "format" => {
                let fmt = match arg(0) {
                    Value::Str(s) => s,
                    _ => return Err(rt("format expects a string template", span)),
                };
                Ok(Value::Str(Arc::from(render_format(&fmt, &args[1..]).as_str())))
            }
            "len" => match arg(0) {
                Value::List(xs) => Ok(Value::Int(xs.len() as i128, IntKind::I32)),
                Value::Map(m) => Ok(Value::Int(m.len() as i128, IntKind::I32)),
                Value::Str(s) => Ok(Value::Int(s.as_bytes().len() as i128, IntKind::I32)),
                Value::Tuple(xs) => Ok(Value::Int(xs.len() as i128, IntKind::I32)),
                other => Err(rt(format!("`len` not defined for `{}`", other.type_name()), span)),
            },
            "abs" => match arg(0) {
                Value::Int(i, k) => Ok(Value::int(i.abs(), k)),
                Value::Float(f, b) => Ok(Value::Float(f.abs(), b)),
                _ => Err(rt("`abs` expects a number", span)),
            },
            "assert" => {
                let cond = arg(0).as_bool().unwrap_or(false);
                if !cond {
                    let msg = match args.get(1) {
                        Some(Value::Str(s)) => s.to_string(),
                        _ => "assertion failed".to_string(),
                    };
                    return Err(rt(msg, span));
                }
                Ok(Value::Unit)
            }
            "panic" => {
                let msg = match arg(0) {
                    Value::Str(s) => s.to_string(),
                    other => other.display(),
                };
                Err(rt(format!("panic: {msg}"), span))
            }
            "unreachable" => Err(rt("entered unreachable code", span)),
            "exit" => {
                let code = match arg(0) {
                    Value::Int(i, _) => i as i32,
                    _ => 0,
                };
                Err(Control::Exit(code))
            }
            "chan" | "make_chan" => Ok(self.make_channel()),
            "args" => {
                let list: Vec<Value> = self
                    .program_args()
                    .into_iter()
                    .map(|s| Value::Str(Arc::from(s.as_str())))
                    .collect();
                Ok(Value::List(Arc::new(list)))
            }
            "read_file" => {
                let path = as_str(&arg(0), span)?;
                match std::fs::read_to_string(&path) {
                    Ok(contents) => Ok(ok(Value::Str(Arc::from(contents.as_str())))),
                    Err(e) => Ok(err(e.to_string())),
                }
            }
            "write_file" => {
                let path = as_str(&arg(0), span)?;
                let content = as_str(&arg(1), span)?;
                match std::fs::write(&path, content) {
                    Ok(()) => Ok(ok(Value::Unit)),
                    Err(e) => Ok(err(e.to_string())),
                }
            }
            "append_file" => {
                let path = as_str(&arg(0), span)?;
                let content = as_str(&arg(1), span)?;
                let res = std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&path)
                    .and_then(|mut f| f.write_all(content.as_bytes()));
                match res {
                    Ok(()) => Ok(ok(Value::Unit)),
                    Err(e) => Ok(err(e.to_string())),
                }
            }
            "file_exists" => Ok(Value::Bool(std::path::Path::new(&as_str(&arg(0), span)?).exists())),
            "remove_file" => match std::fs::remove_file(as_str(&arg(0), span)?) {
                Ok(()) => Ok(ok(Value::Unit)),
                Err(e) => Ok(err(e.to_string())),
            },
            "env_var" => match std::env::var(as_str(&arg(0), span)?) {
                Ok(v) => Ok(some(Value::Str(Arc::from(v.as_str())))),
                Err(_) => Ok(none()),
            },
            "now_millis" => {
                let ms = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_millis() as i128)
                    .unwrap_or(0);
                Ok(Value::Int(ms, IntKind::I64))
            }
            "sleep_millis" => {
                if let Value::Int(ms, _) = arg(0) {
                    std::thread::sleep(std::time::Duration::from_millis(ms.max(0) as u64));
                }
                Ok(Value::Unit)
            }
            "read_line" => {
                let mut line = String::new();
                match std::io::stdin().read_line(&mut line) {
                    Ok(0) => Ok(none()),
                    Ok(_) => {
                        let trimmed = line.trim_end_matches('\n').to_string();
                        Ok(some(Value::Str(Arc::from(trimmed.as_str()))))
                    }
                    Err(_) => Ok(none()),
                }
            }
            "run" => {
                let cmd = as_str(&arg(0), span)?;
                let mut command = std::process::Command::new(&cmd);
                if let Value::List(xs) = arg(1) {
                    for x in xs.iter() {
                        command.arg(x.display());
                    }
                }
                match command.output() {
                    Ok(o) => Ok(ok(Value::Str(Arc::from(
                        String::from_utf8_lossy(&o.stdout).to_string().as_str(),
                    )))),
                    Err(e) => Ok(err(e.to_string())),
                }
            }
            "int_to_str" => Ok(Value::Str(Arc::from(arg(0).display().as_str()))),
            "str_to_int" => {
                let s = as_str(&arg(0), span)?;
                match s.trim().parse::<i128>() {
                    Ok(v) => Ok(some(Value::int(v, IntKind::I32))),
                    Err(_) => Ok(none()),
                }
            }
            _ => Err(rt(format!("unknown builtin `{name}`"), span)),
        }
    }

    // --- method calls ---

    pub(super) fn eval_method_call(
        &self,
        recv: &Expr,
        method: &str,
        args: &[Expr],
        span: Span,
        env: &mut Env,
    ) -> Eval<Value> {
        // Qualified enum-variant construction: `Shape.Circle(r)`.
        if let ExprKind::Name(tn) = &recv.kind {
            if let Some(en) = self.a().enums.get(tn).cloned() {
                if en.variants.iter().any(|v| v.name == method) {
                    let payload = self.eval_args(args, env)?;
                    return Ok(Value::Enum(Arc::new(EnumVal {
                        enum_name: tn.clone(),
                        variant: method.to_string(),
                        payload,
                    })));
                }
            }
        }

        // In-place mutating collection methods operate on a place.
        match method {
            "push" => {
                let v = self.eval_expr(&args[0], env)?;
                return self.with_place_mut(recv, env, |slot| match slot {
                    Value::List(xs) => {
                        Arc::make_mut(xs).push(v);
                        Ok(Value::Unit)
                    }
                    _ => Err(rt("`push` requires a list", span)),
                });
            }
            "pop" => {
                return self.with_place_mut(recv, env, |slot| match slot {
                    Value::List(xs) => Ok(Arc::make_mut(xs).pop().map(some).unwrap_or_else(none)),
                    _ => Err(rt("`pop` requires a list", span)),
                });
            }
            "insert" => {
                let k = self.eval_expr(&args[0], env)?;
                let v = self.eval_expr(&args[1], env)?;
                return self.with_place_mut(recv, env, |slot| match slot {
                    Value::Map(m) => {
                        Arc::make_mut(m).insert(k, v);
                        Ok(Value::Unit)
                    }
                    _ => Err(rt("`insert` requires a map", span)),
                });
            }
            "remove" => {
                let k = self.eval_expr(&args[0], env)?;
                return self.with_place_mut(recv, env, |slot| match slot {
                    Value::Map(m) => Ok(Arc::make_mut(m).remove(&k).map(some).unwrap_or_else(none)),
                    _ => Err(rt("`remove` requires a map", span)),
                });
            }
            _ => {}
        }

        // Evaluate the receiver once.
        let recv_val = self.eval_expr(recv, env)?;
        let arg_vals = self.eval_args(args, env)?;

        // Actor methods run with serialized state via the actor handle.
        if matches!(recv_val, Value::Actor(_)) {
            return self.call_actor_method(recv_val, method, arg_vals, span);
        }

        // user `var self` methods need write-back if recv is a place.
        let ty = recv_val.type_name();
        if let Some(decl) = self.a().methods.get(&(ty.clone(), method.to_string())).cloned() {
            let mutates = decl
                .params
                .first()
                .map(|p| p.is_self && p.self_mut)
                .unwrap_or(false);
            let (result, final_self) = self.call_method_decl(&decl, recv_val, arg_vals)?;
            if mutates {
                let _ = self.assign_place(recv, final_self, env);
            }
            return Ok(result);
        }

        // built-in value methods
        self.dispatch_builtin_method(recv_val, method, arg_vals, span)
    }

    pub(super) fn dispatch_user_method(
        &self,
        ty: &str,
        method: &str,
        recv: Value,
        args: Vec<Value>,
        span: Span,
    ) -> Eval<Value> {
        let decl = self
            .a()
            .methods
            .get(&(ty.to_string(), method.to_string()))
            .cloned()
            .ok_or_else(|| rt(format!("no method `{method}` on `{ty}`"), span))?;
        let (result, _) = self.call_method_decl(&decl, recv, args)?;
        Ok(result)
    }

    fn call_method_decl(
        &self,
        decl: &FunDecl,
        recv: Value,
        args: Vec<Value>,
    ) -> Eval<(Value, Value)> {
        let mut env = Env::new();
        let mut params = decl.params.iter();
        if let Some(first) = decl.params.first() {
            if first.is_self {
                env.declare("self", recv.clone());
                params.next();
            }
        }
        let mut ai = args.into_iter();
        for p in params {
            env.declare(&p.name, ai.next().unwrap_or(Value::Unit));
        }
        let result = match self.eval_block(&decl.body, &mut env) {
            Ok(v) => v,
            Err(Control::Return(v)) => v,
            Err(other) => return Err(other),
        };
        let final_self = env.get("self").unwrap_or(recv);
        Ok((result, final_self))
    }

    fn dispatch_builtin_method(
        &self,
        recv: Value,
        method: &str,
        args: Vec<Value>,
        span: Span,
    ) -> Eval<Value> {
        let arg = |i: usize| args.get(i).cloned().unwrap_or(Value::Unit);
        match (&recv, method) {
            (Value::List(xs), "len") => Ok(Value::Int(xs.len() as i128, IntKind::I32)),
            (Value::List(xs), "get") => {
                if let Value::Int(i, _) = arg(0) {
                    Ok(xs.get(i as usize).cloned().map(some).unwrap_or_else(none))
                } else {
                    Err(rt("`get` expects an index", span))
                }
            }
            (Value::List(xs), "contains") => {
                Ok(Value::Bool(xs.iter().any(|v| *v == arg(0))))
            }
            (Value::List(xs), "map") => {
                let mut out = Vec::with_capacity(xs.len());
                for x in xs.iter() {
                    out.push(self.call_value(arg(0), vec![x.clone()], span)?);
                }
                Ok(Value::List(Arc::new(out)))
            }
            (Value::List(xs), "filter") => {
                let mut out = Vec::new();
                for x in xs.iter() {
                    if self.call_value(arg(0), vec![x.clone()], span)?.as_bool().unwrap_or(false) {
                        out.push(x.clone());
                    }
                }
                Ok(Value::List(Arc::new(out)))
            }
            (Value::Map(m), "len") => Ok(Value::Int(m.len() as i128, IntKind::I32)),
            (Value::Map(m), "get") => Ok(m.get(&arg(0)).cloned().map(some).unwrap_or_else(none)),
            (Value::Map(m), "contains") => Ok(Value::Bool(m.contains(&arg(0)))),
            (Value::Map(m), "keys") => Ok(Value::List(Arc::new(m.keys()))),
            (Value::Map(m), "values") => {
                Ok(Value::List(Arc::new(m.entries.iter().map(|(_, v)| v.clone()).collect())))
            }
            (Value::Str(s), "len") => Ok(Value::Int(s.as_bytes().len() as i128, IntKind::I32)),
            (Value::Str(s), "chars") => {
                Ok(Value::List(Arc::new(s.chars().map(Value::Char).collect())))
            }
            (Value::Str(s), "contains") => {
                Ok(Value::Bool(s.contains(&as_str(&arg(0), span)?)))
            }
            (Value::Str(s), "starts_with") => {
                Ok(Value::Bool(s.starts_with(&as_str(&arg(0), span)?)))
            }
            (Value::Str(s), "ends_with") => {
                Ok(Value::Bool(s.ends_with(&as_str(&arg(0), span)?)))
            }
            (Value::Str(s), "to_upper") => Ok(Value::Str(Arc::from(s.to_uppercase().as_str()))),
            (Value::Str(s), "to_lower") => Ok(Value::Str(Arc::from(s.to_lowercase().as_str()))),
            (Value::Str(s), "trim") => Ok(Value::Str(Arc::from(s.trim()))),
            (Value::Str(s), "split") => {
                let sep = as_str(&arg(0), span)?;
                let parts: Vec<Value> =
                    s.split(&sep).map(|p| Value::Str(Arc::from(p))).collect();
                Ok(Value::List(Arc::new(parts)))
            }
            (Value::Chan(c), "send") => {
                c.send(arg(0));
                Ok(Value::Unit)
            }
            (Value::Chan(c), "recv") => Ok(c.recv().unwrap_or(Value::Unit)),
            (Value::Chan(c), "try_recv") => Ok(c.try_recv().map(some).unwrap_or_else(none)),
            (Value::Task(t), "join") | (Value::Task(t), "await") => Ok(t.join()),
            (Value::Actor(_), _) => self.call_actor_method(recv, method, args, span),
            _ => Err(rt(
                format!("no method `{method}` on `{}`", recv.type_name()),
                span,
            )),
        }
    }

    fn call_actor_method(
        &self,
        recv: Value,
        method: &str,
        args: Vec<Value>,
        span: Span,
    ) -> Eval<Value> {
        let handle = match &recv {
            Value::Actor(h) => h.clone(),
            _ => unreachable!(),
        };
        let decl = self
            .a()
            .methods
            .get(&(handle.name.clone(), method.to_string()))
            .cloned()
            .ok_or_else(|| rt(format!("no method `{method}` on actor `{}`", handle.name), span))?;

        // Serialize access to the actor's state (actor isolation).
        let mut state = handle.state.lock().unwrap();
        let self_struct = Value::Struct(Arc::new(crate::value::StructVal {
            name: handle.name.clone(),
            fields: state.iter().map(|(k, v)| (k.clone(), v.clone())).collect(),
        }));
        let (result, final_self) = self.call_method_decl(&decl, self_struct, args)?;
        if let Value::Struct(s) = &final_self {
            for (k, v) in &s.fields {
                state.insert(k.clone(), v.clone());
            }
        }
        Ok(result)
    }
}

fn render_format(fmt: &str, args: &[Value]) -> String {
    let mut out = String::new();
    let mut iter = args.iter();
    let chars: Vec<char> = fmt.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '{' && i + 1 < chars.len() && chars[i + 1] == '}' {
            if let Some(v) = iter.next() {
                out.push_str(&v.display());
            }
            i += 2;
        } else if chars[i] == '{' && i + 1 < chars.len() && chars[i + 1] == '{' {
            out.push('{');
            i += 2;
        } else if chars[i] == '}' && i + 1 < chars.len() && chars[i + 1] == '}' {
            out.push('}');
            i += 2;
        } else {
            out.push(chars[i]);
            i += 1;
        }
    }
    out
}

fn as_str(v: &Value, span: Span) -> Eval<String> {
    match v {
        Value::Str(s) => Ok(s.to_string()),
        other => Err(rt(format!("expected a string, found `{}`", other.type_name()), span)),
    }
}
