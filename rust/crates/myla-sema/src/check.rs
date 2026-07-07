//! Mutability / assignability checks over function bodies.

use myla_syntax::ast::*;
use myla_syntax::diagnostic::{Diagnostic, Stage};

use crate::Analyzed;

struct Scopes {
    stack: Vec<Vec<(String, bool)>>, // (name, mutable)
}

impl Scopes {
    fn new() -> Self {
        Scopes { stack: vec![Vec::new()] }
    }
    fn push(&mut self) {
        self.stack.push(Vec::new());
    }
    fn pop(&mut self) {
        self.stack.pop();
    }
    fn declare(&mut self, name: &str, mutable: bool) {
        self.stack.last_mut().unwrap().push((name.to_string(), mutable));
    }
    fn lookup(&self, name: &str) -> Option<bool> {
        for scope in self.stack.iter().rev() {
            for (n, m) in scope.iter().rev() {
                if n == name {
                    return Some(*m);
                }
            }
        }
        None
    }
}

pub fn check_program(program: &Program, _a: &Analyzed, errors: &mut Vec<Diagnostic>) {
    for item in &program.items {
        match item {
            Item::Function(f) => check_fun(f, errors),
            Item::Impl(im) => {
                for m in &im.methods {
                    check_fun(m, errors);
                }
            }
            Item::Actor(ac) => {
                for m in &ac.methods {
                    check_fun(m, errors);
                }
            }
            _ => {}
        }
    }
}

fn check_fun(f: &FunDecl, errors: &mut Vec<Diagnostic>) {
    let mut scopes = Scopes::new();
    for p in &f.params {
        let mutable = p.is_self && p.self_mut;
        scopes.declare(&p.name, mutable);
    }
    check_block(&f.body, &mut scopes, errors);
}

fn check_block(block: &Block, scopes: &mut Scopes, errors: &mut Vec<Diagnostic>) {
    scopes.push();
    for stmt in &block.stmts {
        check_stmt(stmt, scopes, errors);
    }
    if let Some(tail) = &block.tail {
        check_expr(tail, scopes, errors);
    }
    scopes.pop();
}

fn check_stmt(stmt: &Stmt, scopes: &mut Scopes, errors: &mut Vec<Diagnostic>) {
    match &stmt.kind {
        StmtKind::Let { kind, name, init, .. } => {
            check_expr(init, scopes, errors);
            scopes.declare(name, *kind == LetKind::Var);
        }
        StmtKind::Assign { target, value, .. } => {
            check_expr(value, scopes, errors);
            check_assignable(target, scopes, errors);
        }
        StmtKind::Expr(e) => check_expr(e, scopes, errors),
        StmtKind::Return(Some(e)) => check_expr(e, scopes, errors),
        StmtKind::Return(None) => {}
        StmtKind::While { cond, body } => {
            check_expr(cond, scopes, errors);
            check_block(body, scopes, errors);
        }
        StmtKind::For { var, iter, body } => {
            check_expr(iter, scopes, errors);
            scopes.push();
            scopes.declare(var, false);
            check_block(body, scopes, errors);
            scopes.pop();
        }
        StmtKind::Break | StmtKind::Continue => {}
        StmtKind::Select(arms) => {
            for arm in arms {
                check_expr(&arm.channel, scopes, errors);
                scopes.push();
                if let Some(b) = &arm.binding {
                    scopes.declare(b, false);
                }
                check_block(&arm.body, scopes, errors);
                scopes.pop();
            }
        }
    }
}

fn check_assignable(target: &Expr, scopes: &mut Scopes, errors: &mut Vec<Diagnostic>) {
    match root_name(target) {
        Some(name) => match scopes.lookup(name) {
            Some(true) => {}
            Some(false) => errors.push(Diagnostic::error(
                Stage::Type,
                format!("cannot assign to immutable binding `{name}`"),
                target.span,
            )),
            None => {
                // self field assignment etc.; assume valid for non-locals
            }
        },
        None => errors.push(Diagnostic::error(
            Stage::Type,
            "invalid assignment target",
            target.span,
        )),
    }
}

fn root_name(expr: &Expr) -> Option<&str> {
    match &expr.kind {
        ExprKind::Name(n) => Some(n),
        ExprKind::SelfExpr => Some("self"),
        ExprKind::Field { recv, .. } => root_name(recv),
        ExprKind::Index { recv, .. } => root_name(recv),
        _ => None,
    }
}

fn check_expr(expr: &Expr, scopes: &mut Scopes, errors: &mut Vec<Diagnostic>) {
    match &expr.kind {
        ExprKind::Unary { expr, .. } => check_expr(expr, scopes, errors),
        ExprKind::Binary { lhs, rhs, .. } => {
            check_expr(lhs, scopes, errors);
            check_expr(rhs, scopes, errors);
        }
        ExprKind::Call { callee, args } => {
            check_expr(callee, scopes, errors);
            for a in args {
                check_expr(a, scopes, errors);
            }
        }
        ExprKind::MethodCall { recv, args, .. } => {
            check_expr(recv, scopes, errors);
            for a in args {
                check_expr(a, scopes, errors);
            }
        }
        ExprKind::Field { recv, .. } => check_expr(recv, scopes, errors),
        ExprKind::Index { recv, index } => {
            check_expr(recv, scopes, errors);
            check_expr(index, scopes, errors);
        }
        ExprKind::StructLit { fields, .. } => {
            for (_, v) in fields {
                check_expr(v, scopes, errors);
            }
        }
        ExprKind::ListLit(xs) => xs.iter().for_each(|e| check_expr(e, scopes, errors)),
        ExprKind::MapLit(entries) => {
            for (k, v) in entries {
                check_expr(k, scopes, errors);
                check_expr(v, scopes, errors);
            }
        }
        ExprKind::TupleLit(xs) => xs.iter().for_each(|e| check_expr(e, scopes, errors)),
        ExprKind::Lambda { params, body } => {
            scopes.push();
            for p in params {
                scopes.declare(&p.name, false);
            }
            check_expr(body, scopes, errors);
            scopes.pop();
        }
        ExprKind::If { cond, then, otherwise } => {
            check_expr(cond, scopes, errors);
            check_block(then, scopes, errors);
            if let Some(e) = otherwise {
                check_expr(e, scopes, errors);
            }
        }
        ExprKind::Match { scrutinee, arms } => {
            check_expr(scrutinee, scopes, errors);
            for arm in arms {
                scopes.push();
                declare_pattern(&arm.pattern, scopes);
                if let Some(g) = &arm.guard {
                    check_expr(g, scopes, errors);
                }
                check_expr(&arm.body, scopes, errors);
                scopes.pop();
            }
        }
        ExprKind::Block(b) => check_block(b, scopes, errors),
        ExprKind::Range { start, end } => {
            check_expr(start, scopes, errors);
            check_expr(end, scopes, errors);
        }
        ExprKind::Cast { expr, .. } => check_expr(expr, scopes, errors),
        ExprKind::Pipe { lhs, rhs } => {
            check_expr(lhs, scopes, errors);
            check_expr(rhs, scopes, errors);
        }
        ExprKind::Try(e) | ExprKind::Await(e) | ExprKind::Spawn(e) => {
            check_expr(e, scopes, errors)
        }
        ExprKind::FStr(parts) => {
            for p in parts {
                if let FStrPart::Expr(e) = p {
                    check_expr(e, scopes, errors);
                }
            }
        }
        _ => {}
    }
}

fn declare_pattern(pat: &Pattern, scopes: &mut Scopes) {
    match &pat.kind {
        PatternKind::Binding(n) => scopes.declare(n, false),
        PatternKind::Tuple(subs) => subs.iter().for_each(|p| declare_pattern(p, scopes)),
        PatternKind::Variant { sub, .. } => sub.iter().for_each(|p| declare_pattern(p, scopes)),
        PatternKind::Struct { fields, .. } => {
            fields.iter().for_each(|(_, p)| declare_pattern(p, scopes))
        }
        PatternKind::Or(alts) => {
            if let Some(first) = alts.first() {
                declare_pattern(first, scopes);
            }
        }
        _ => {}
    }
}
