//! Lvalue navigation for assignment and in-place mutation.

use std::sync::Arc;

use myla_syntax::ast::{Expr, ExprKind};

use crate::control::{Control, Eval, RuntimeError};
use crate::env::Env;
use crate::value::Value;

use super::Interp;

pub(super) enum Step {
    Field(String),
    Index(Value),
}

impl Interp {
    fn place_path(&self, target: &Expr, env: &mut Env) -> Eval<(String, Vec<Step>)> {
        match &target.kind {
            ExprKind::Name(n) => Ok((n.clone(), Vec::new())),
            ExprKind::SelfExpr => Ok(("self".to_string(), Vec::new())),
            ExprKind::Field { recv, name } => {
                let (root, mut steps) = self.place_path(recv, env)?;
                steps.push(Step::Field(name.clone()));
                Ok((root, steps))
            }
            ExprKind::Index { recv, index } => {
                let idx = self.eval_expr(index, env)?;
                let (root, mut steps) = self.place_path(recv, env)?;
                steps.push(Step::Index(idx));
                Ok((root, steps))
            }
            _ => Err(Control::Error(RuntimeError::at(
                "invalid assignment target",
                target.span,
            ))),
        }
    }

    pub(super) fn assign_place(&self, target: &Expr, value: Value, env: &mut Env) -> Eval<()> {
        let (root, steps) = self.place_path(target, env)?;
        if steps.is_empty() {
            if env.assign(&root, value) {
                return Ok(());
            }
            return Err(Control::Error(RuntimeError::at(
                format!("cannot assign to unbound name `{root}`"),
                target.span,
            )));
        }
        let slot = env.get_mut(&root).ok_or_else(|| {
            Control::Error(RuntimeError::at(format!("unbound name `{root}`"), target.span))
        })?;
        let (last, init) = steps.split_last().unwrap();
        let parent = navigate_mut(slot, init, target.span)?;
        apply_set(parent, last, value, target.span)
    }

    /// Navigate to a place and apply an in-place mutation (push/pop/insert/...).
    pub(super) fn with_place_mut<R>(
        &self,
        target: &Expr,
        env: &mut Env,
        f: impl FnOnce(&mut Value) -> Eval<R>,
    ) -> Eval<R> {
        let (root, steps) = self.place_path(target, env)?;
        let slot = env.get_mut(&root).ok_or_else(|| {
            Control::Error(RuntimeError::at(format!("unbound name `{root}`"), target.span))
        })?;
        let target_slot = navigate_mut(slot, &steps, target.span)?;
        f(target_slot)
    }
}

fn navigate_mut<'a>(slot: &'a mut Value, steps: &[Step], span: myla_syntax::span::Span) -> Eval<&'a mut Value> {
    let mut cur = slot;
    for step in steps {
        cur = match (cur, step) {
            (Value::Struct(s), Step::Field(name)) => {
                let sm = Arc::make_mut(s);
                sm.get_mut(name)
                    .ok_or_else(|| bounds(format!("no field `{name}`"), span))?
            }
            (Value::List(xs), Step::Index(idx)) => {
                let v = Arc::make_mut(xs);
                let i = to_index(idx, span)?;
                let len = v.len();
                v.get_mut(i)
                    .ok_or_else(|| bounds(format!("index {i} out of bounds (len {len})"), span))?
            }
            (Value::Tuple(xs), Step::Index(idx)) => {
                let v = Arc::make_mut(xs);
                let i = to_index(idx, span)?;
                v.get_mut(i).ok_or_else(|| bounds("tuple index out of bounds", span))?
            }
            (Value::Map(m), Step::Index(idx)) => {
                let mm = Arc::make_mut(m);
                mm.get_mut(idx)
                    .ok_or_else(|| bounds("key not present in map", span))?
            }
            _ => return Err(bounds("cannot navigate into value", span)),
        };
    }
    Ok(cur)
}

fn apply_set(parent: &mut Value, last: &Step, value: Value, span: myla_syntax::span::Span) -> Eval<()> {
    match (parent, last) {
        (Value::Struct(s), Step::Field(name)) => {
            let sm = Arc::make_mut(s);
            match sm.get_mut(name) {
                Some(slot) => {
                    *slot = value;
                    Ok(())
                }
                None => Err(bounds(format!("no field `{name}`"), span)),
            }
        }
        (Value::List(xs), Step::Index(idx)) => {
            let v = Arc::make_mut(xs);
            let i = to_index(idx, span)?;
            if i >= v.len() {
                return Err(bounds(format!("index {i} out of bounds (len {})", v.len()), span));
            }
            v[i] = value;
            Ok(())
        }
        (Value::Tuple(xs), Step::Index(idx)) => {
            let v = Arc::make_mut(xs);
            let i = to_index(idx, span)?;
            if i >= v.len() {
                return Err(bounds("tuple index out of bounds", span));
            }
            v[i] = value;
            Ok(())
        }
        (Value::Map(m), Step::Index(idx)) => {
            let mm = Arc::make_mut(m);
            mm.insert(idx.clone(), value);
            Ok(())
        }
        _ => Err(bounds("invalid assignment target", span)),
    }
}

fn to_index(v: &Value, span: myla_syntax::span::Span) -> Eval<usize> {
    match v {
        Value::Int(i, _) if *i >= 0 => Ok(*i as usize),
        _ => Err(bounds("index must be a non-negative integer", span)),
    }
}

fn bounds(msg: impl Into<String>, span: myla_syntax::span::Span) -> Control {
    Control::Error(RuntimeError::at(msg, span))
}
