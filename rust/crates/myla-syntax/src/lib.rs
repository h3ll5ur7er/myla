//! Lexing, AST, and parsing for the Myla language (Rust implementation).

pub mod span;
pub mod token;
pub mod lexer;
pub mod ast;
pub mod parser;
pub mod diagnostic;

pub use diagnostic::{Diagnostic, Severity, Stage};
pub use span::Span;

/// Lex + parse a source string into a [`ast::Program`].
pub fn parse_program(source: &str) -> Result<ast::Program, Vec<Diagnostic>> {
    let tokens = lexer::lex(source)?;
    parser::Parser::new(source, tokens).parse_program()
}

/// Lex + parse a source string holding a single expression (used by f-strings).
pub fn parse_expr_string(source: &str) -> Result<ast::Expr, Vec<Diagnostic>> {
    let tokens = lexer::lex(source)?;
    parser::Parser::new(source, tokens).parse_single_expr()
}
