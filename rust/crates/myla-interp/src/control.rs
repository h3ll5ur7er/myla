//! Non-local control flow and runtime errors.

use myla_syntax::span::Span;

use crate::value::Value;

#[derive(Debug, Clone)]
pub struct RuntimeError {
    pub message: String,
    pub span: Option<Span>,
}

impl RuntimeError {
    pub fn new(message: impl Into<String>) -> RuntimeError {
        RuntimeError {
            message: message.into(),
            span: None,
        }
    }
    pub fn at(message: impl Into<String>, span: Span) -> RuntimeError {
        RuntimeError {
            message: message.into(),
            span: Some(span),
        }
    }
}

/// Propagated via `Result::Err` so `?` threads it through evaluation.
pub enum Control {
    Return(Value),
    Break,
    Continue,
    Error(RuntimeError),
    /// Process exit requested by `exit(code)`.
    Exit(i32),
}

pub type Eval<T> = Result<T, Control>;

impl From<RuntimeError> for Control {
    fn from(e: RuntimeError) -> Self {
        Control::Error(e)
    }
}
