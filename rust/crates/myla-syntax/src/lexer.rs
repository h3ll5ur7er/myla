//! Turns source text into a flat token stream.

use logos::Logos;

use crate::diagnostic::{Diagnostic, Stage};
use crate::span::Span;
use crate::token::TokenKind;

#[derive(Clone, Copy, Debug)]
pub struct Token {
    pub kind: TokenKind,
    pub span: Span,
}

impl Token {
    pub fn text<'s>(&self, source: &'s str) -> &'s str {
        &source[self.span.as_range()]
    }
}

/// Lex `source` into tokens, terminated by an `Eof` token.
pub fn lex(source: &str) -> Result<Vec<Token>, Vec<Diagnostic>> {
    let mut tokens = Vec::new();
    let mut errors = Vec::new();
    let mut lex = TokenKind::lexer(source);
    while let Some(result) = lex.next() {
        let span = Span::new(lex.span().start, lex.span().end);
        match result {
            Ok(kind) => tokens.push(Token { kind, span }),
            Err(_) => errors.push(Diagnostic::error(
                Stage::Lex,
                format!("unexpected character `{}`", &source[span.as_range()]),
                span,
            )),
        }
    }
    tokens.push(Token {
        kind: TokenKind::Eof,
        span: Span::new(source.len(), source.len()),
    });
    if errors.is_empty() {
        Ok(tokens)
    } else {
        Err(errors)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn kinds(src: &str) -> Vec<TokenKind> {
        lex(src)
            .unwrap()
            .into_iter()
            .map(|t| t.kind)
            .filter(|k| *k != TokenKind::Newline)
            .collect()
    }

    #[test]
    fn lexes_basic_decl() {
        let ks = kinds("fun main() { let x = 1 }");
        use TokenKind::*;
        assert_eq!(
            ks,
            vec![Fun, Ident, LParen, RParen, LBrace, Let, Ident, Eq, Int, RBrace, Eof]
        );
    }

    #[test]
    fn lexes_floats_and_ranges() {
        assert_eq!(kinds("3.14"), vec![TokenKind::Float, TokenKind::Eof]);
        assert_eq!(
            kinds("0..5"),
            vec![TokenKind::Int, TokenKind::DotDot, TokenKind::Int, TokenKind::Eof]
        );
        assert_eq!(kinds("1e9f64"), vec![TokenKind::Float, TokenKind::Eof]);
    }

    #[test]
    fn skips_comments() {
        let ks = kinds("// hi\n/* block */ 42");
        assert_eq!(ks, vec![TokenKind::Int, TokenKind::Eof]);
    }

    #[test]
    fn lexes_concurrency_keywords() {
        use TokenKind::*;
        assert_eq!(
            kinds("spawn go chan async await actor select"),
            vec![Spawn, Go, Chan, Async, Await, Actor, Select, Eof]
        );
    }
}
