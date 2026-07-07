//! Operators, casts, and indexing.

use std::sync::Arc;

use myla_runtime::IntKind;
use myla_sema::operator_method;
use myla_syntax::ast::{BinOp, TypeExpr, TypeKind, UnOp};
use myla_syntax::span::Span;

use crate::control::{Control, Eval, RuntimeError};
use crate::value::{value_eq, Value};

use super::Interp;

impl Interp {
    pub(super) fn unary(&self, op: UnOp, v: Value, span: Span) -> Eval<Value> {
        match (op, &v) {
            (UnOp::Neg, Value::Int(i, k)) => Ok(Value::int(-*i, *k)),
            (UnOp::Neg, Value::Float(f, b)) => Ok(Value::Float(-*f, *b)),
            (UnOp::Not, Value::Bool(b)) => Ok(Value::Bool(!*b)),
            (UnOp::BitNot, Value::Int(i, k)) => Ok(Value::int(!*i, *k)),
            _ => Err(err(format!("invalid unary operator on `{}`", v.type_name()), span)),
        }
    }

    pub(super) fn binary(&self, op: BinOp, l: Value, r: Value, span: Span) -> Eval<Value> {
        use BinOp::*;
        // Equality works structurally for every value.
        match op {
            Eq => return Ok(Value::Bool(value_eq(&l, &r))),
            Ne => return Ok(Value::Bool(!value_eq(&l, &r))),
            _ => {}
        }
        match (&l, &r) {
            (Value::Int(a, k), Value::Int(b, _)) => self.int_binary(op, *a, *b, *k, span),
            (Value::Float(a, bw), Value::Float(b, _)) => float_binary(op, *a, *b, *bw, span),
            (Value::Str(a), Value::Str(b)) => match op {
                Add => Ok(Value::Str(Arc::from(format!("{a}{b}").as_str()))),
                Lt => Ok(Value::Bool(a < b)),
                Le => Ok(Value::Bool(a <= b)),
                Gt => Ok(Value::Bool(a > b)),
                Ge => Ok(Value::Bool(a >= b)),
                _ => Err(err("invalid string operator", span)),
            },
            (Value::Char(a), Value::Char(b)) => match op {
                Lt => Ok(Value::Bool(a < b)),
                Le => Ok(Value::Bool(a <= b)),
                Gt => Ok(Value::Bool(a > b)),
                Ge => Ok(Value::Bool(a >= b)),
                _ => Err(err("invalid char operator", span)),
            },
            _ => {
                // operator overloading: dispatch to a user method (`add`, `cmp`, ...)
                if let (Some(method), Value::Struct(_) | Value::Enum(_)) = (operator_method(op), &l) {
                    let ty = l.type_name();
                    if self.a().methods.contains_key(&(ty.clone(), method.to_string())) {
                        let res = self.dispatch_user_method(&ty, method, l.clone(), vec![r], span)?;
                        return finalize_overload(op, res, span);
                    }
                }
                Err(err(
                    format!(
                        "operator not defined for `{}` and `{}`",
                        l.type_name(),
                        r.type_name()
                    ),
                    span,
                ))
            }
        }
    }

    fn int_binary(&self, op: BinOp, a: i128, b: i128, k: IntKind, span: Span) -> Eval<Value> {
        use BinOp::*;
        let v = match op {
            Add => k.wrap(a + b),
            Sub => k.wrap(a - b),
            Mul => k.wrap(a.wrapping_mul(b)),
            Div => {
                if b == 0 {
                    return Err(err("division by zero", span));
                }
                k.wrap(a / b)
            }
            Rem => {
                if b == 0 {
                    return Err(err("modulo by zero", span));
                }
                k.wrap(a % b)
            }
            BitAnd => k.wrap(a & b),
            BitOr => k.wrap(a | b),
            BitXor => k.wrap(a ^ b),
            Shl => {
                let amt = (b & (k.bits as i128 - 1)) as u32;
                k.wrap(a << amt)
            }
            Shr => {
                let amt = (b & (k.bits as i128 - 1)) as u32;
                k.wrap(a >> amt)
            }
            Lt => return Ok(Value::Bool(a < b)),
            Le => return Ok(Value::Bool(a <= b)),
            Gt => return Ok(Value::Bool(a > b)),
            Ge => return Ok(Value::Bool(a >= b)),
            Eq | Ne | And | Or => unreachable!(),
        };
        Ok(Value::Int(v, k))
    }

    pub(super) fn cast(&self, v: Value, ty: &TypeExpr, span: Span) -> Eval<Value> {
        let name = match &ty.kind {
            TypeKind::Named { name, .. } => name.as_str(),
            _ => return Err(err("unsupported cast target", span)),
        };
        if let Some(k) = IntKind::from_name(name) {
            let raw = match &v {
                Value::Int(i, _) => *i,
                Value::Float(f, _) => *f as i128,
                Value::Char(c) => *c as i128,
                Value::Bool(b) => *b as i128,
                _ => return Err(err("cannot cast to integer", span)),
            };
            return Ok(Value::int(raw, k));
        }
        match name {
            "float" | "float32" | "float64" => {
                let bits = if name == "float32" { 32 } else { 64 };
                let f = match &v {
                    Value::Int(i, _) => *i as f64,
                    Value::Float(f, _) => *f,
                    _ => return Err(err("cannot cast to float", span)),
                };
                let f = if bits == 32 { f as f32 as f64 } else { f };
                Ok(Value::Float(f, bits))
            }
            "char" => match &v {
                Value::Int(i, _) => char::from_u32(*i as u32)
                    .map(Value::Char)
                    .ok_or_else(|| err("invalid char code", span)),
                Value::Char(c) => Ok(Value::Char(*c)),
                _ => Err(err("cannot cast to char", span)),
            },
            _ => Err(err(format!("unsupported cast to `{name}`"), span)),
        }
    }

    pub(super) fn index(&self, base: Value, idx: Value, span: Span) -> Eval<Value> {
        match (&base, &idx) {
            (Value::List(xs), Value::Int(i, _)) => xs
                .get(*i as usize)
                .cloned()
                .ok_or_else(|| err(format!("list index {i} out of bounds (len {})", xs.len()), span)),
            (Value::Tuple(xs), Value::Int(i, _)) => xs
                .get(*i as usize)
                .cloned()
                .ok_or_else(|| err("tuple index out of bounds", span)),
            (Value::Str(s), Value::Int(i, _)) => s
                .as_bytes()
                .get(*i as usize)
                .map(|b| Value::Int(*b as i128, IntKind::U8))
                .ok_or_else(|| err("string index out of bounds", span)),
            (Value::Map(m), key) => m
                .get(key)
                .cloned()
                .ok_or_else(|| err("key not present in map", span)),
            _ => Err(err(
                format!("cannot index `{}`", base.type_name()),
                span,
            )),
        }
    }
}

/// `cmp`-style overloads return an ordering int; lift to a bool for `< <= > >=`.
fn finalize_overload(op: BinOp, res: Value, span: Span) -> Eval<Value> {
    use BinOp::*;
    match op {
        Lt | Le | Gt | Ge => {
            let ord = match res {
                Value::Int(i, _) => i,
                _ => return Err(err("`cmp` must return an integer ordering", span)),
            };
            Ok(Value::Bool(match op {
                Lt => ord < 0,
                Le => ord <= 0,
                Gt => ord > 0,
                Ge => ord >= 0,
                _ => unreachable!(),
            }))
        }
        _ => Ok(res),
    }
}

fn float_binary(op: BinOp, a: f64, b: f64, bits: u8, span: Span) -> Eval<Value> {
    use BinOp::*;
    let v = match op {
        Add => a + b,
        Sub => a - b,
        Mul => a * b,
        Div => a / b,
        Rem => a % b,
        Lt => return Ok(Value::Bool(a < b)),
        Le => return Ok(Value::Bool(a <= b)),
        Gt => return Ok(Value::Bool(a > b)),
        Ge => return Ok(Value::Bool(a >= b)),
        _ => return Err(err("invalid float operator", span)),
    };
    let v = if bits == 32 { v as f32 as f64 } else { v };
    Ok(Value::Float(v, bits))
}

fn err(msg: impl Into<String>, span: Span) -> Control {
    Control::Error(RuntimeError::at(msg, span))
}
