//! Positioned diagnostics shared across the toolchain.

use crate::span::{line_col, Span};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Severity {
    Error,
    Warning,
}

/// Which pipeline stage produced a diagnostic. Used by the error corpus
/// (`//~ <stage> error: ...`) to assert *where* a program fails.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Stage {
    Lex,
    Parse,
    Type,
    Runtime,
}

impl Stage {
    pub fn as_str(self) -> &'static str {
        match self {
            Stage::Lex => "lex",
            Stage::Parse => "parse",
            Stage::Type => "type",
            Stage::Runtime => "runtime",
        }
    }
}

#[derive(Clone, Debug)]
pub struct Diagnostic {
    pub severity: Severity,
    pub stage: Stage,
    pub message: String,
    pub span: Span,
}

impl Diagnostic {
    pub fn error(stage: Stage, message: impl Into<String>, span: Span) -> Self {
        Diagnostic {
            severity: Severity::Error,
            stage,
            message: message.into(),
            span,
        }
    }

    /// Render a compact, rustc-style caret diagnostic against `source`.
    pub fn render(&self, source: &str, filename: &str) -> String {
        let (line, col) = line_col(source, self.span.start);
        let line_text = source.lines().nth(line.saturating_sub(1)).unwrap_or("");
        let gutter = format!("{} ", line);
        let pad = " ".repeat(gutter.len());
        let caret_len = self
            .span
            .end
            .saturating_sub(self.span.start)
            .max(1)
            .min(line_text.len().saturating_sub(col.saturating_sub(1)).max(1));
        let underline = format!("{}{}", " ".repeat(col.saturating_sub(1)), "^".repeat(caret_len));
        format!(
            "{stage} error: {msg}\n  --> {file}:{line}:{col}\n{pad}|\n{gutter}| {line_text}\n{pad}| {underline}",
            stage = self.stage.as_str(),
            msg = self.message,
            file = filename,
            line = line,
            col = col,
            pad = pad,
            gutter = gutter,
            line_text = line_text,
            underline = underline,
        )
    }
}
