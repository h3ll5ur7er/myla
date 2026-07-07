//! Token kinds. The lexical grammar is driven by `logos`.

use logos::{Lexer, Logos, Skip};

/// Consume a non-nesting block comment up to and including the first `*/`.
fn skip_block_comment(lex: &mut Lexer<TokenKind>) -> Skip {
    let rest = lex.remainder();
    match rest.find("*/") {
        Some(idx) => lex.bump(idx + 2),
        None => lex.bump(rest.len()),
    }
    Skip
}

/// A lexical token kind.
///
/// Whitespace (except newlines) and comments are skipped. Newlines are
/// preserved as [`TokenKind::Newline`] so the parser can implement the
/// optional-semicolon / newline-sensitive statement termination rules.
#[derive(Logos, Debug, Clone, Copy, PartialEq, Eq)]
#[logos(skip r"[ \t\r]+")]
#[logos(skip r"//[^\n]*")]
pub enum TokenKind {
    #[token("\n")]
    Newline,

    /// Non-nesting block comment; scanned by a callback and skipped.
    #[token("/*", skip_block_comment)]
    BlockComment,

    // --- keywords ---
    #[token("let")] Let,
    #[token("var")] Var,
    #[token("const")] Const,
    #[token("fun")] Fun,
    #[token("return")] Return,
    #[token("struct")] Struct,
    #[token("enum")] Enum,
    #[token("trait")] Trait,
    #[token("impl")] Impl,
    #[token("typealias")] Typealias,
    #[token("if")] If,
    #[token("else")] Else,
    #[token("while")] While,
    #[token("for")] For,
    #[token("in")] In,
    #[token("match")] Match,
    #[token("break")] Break,
    #[token("continue")] Continue,
    #[token("as")] As,
    #[token("import")] Import,
    #[token("from")] From,
    #[token("pub")] Pub,
    #[token("self")] SelfKw,
    #[token("true")] True,
    #[token("false")] False,

    // --- concurrency keywords (bonus) ---
    #[token("async")] Async,
    #[token("await")] Await,
    #[token("actor")] Actor,
    #[token("spawn")] Spawn,
    #[token("go")] Go,
    #[token("chan")] Chan,
    #[token("select")] Select,

    // --- identifiers & literals ---
    #[regex(r"[A-Za-z_][A-Za-z0-9_]*")]
    Ident,

    // float must out-prioritize int when a dot/exponent is present
    #[regex(r"[0-9][0-9_]*\.[0-9_]+([eE][+-]?[0-9_]+)?(f32|f64)?")]
    #[regex(r"[0-9][0-9_]*[eE][+-]?[0-9_]+(f32|f64)?")]
    #[regex(r"[0-9][0-9_]*(f32|f64)")]
    Float,

    #[regex(r"0[xX][0-9a-fA-F_]+((i|u)(8|16|32|64))?")]
    #[regex(r"0[bB][01_]+((i|u)(8|16|32|64))?")]
    #[regex(r"0[oO][0-7_]+((i|u)(8|16|32|64))?")]
    #[regex(r"[0-9][0-9_]*((i|u)(8|16|32|64))?")]
    Int,

    #[regex(r#""([^"\\]|\\.)*""#)]
    Str,

    #[regex(r#"f"([^"\\]|\\.)*""#)]
    FStr,

    #[regex(r#"'([^'\\]|\\.)'"#)]
    #[regex(r#"'\\u\{[0-9a-fA-F]+\}'"#)]
    Char,

    // --- multi-char punctuation (longest match wins) ---
    #[token("->")] Arrow,
    #[token("=>")] FatArrow,
    #[token("..")] DotDot,
    #[token("|>")] PipeArrow,
    #[token("==")] EqEq,
    #[token("!=")] NotEq,
    #[token("<=")] LtEq,
    #[token(">=")] GtEq,
    #[token("&&")] AmpAmp,
    #[token("||")] PipePipe,

    // --- single-char punctuation ---
    #[token("+")] Plus,
    #[token("-")] Minus,
    #[token("*")] Star,
    #[token("/")] Slash,
    #[token("%")] Percent,
    #[token("=")] Eq,
    #[token("<")] Lt,
    #[token(">")] Gt,
    #[token("!")] Bang,
    #[token("&")] Amp,
    #[token("|")] Pipe,
    #[token("^")] Caret,
    #[token("~")] Tilde,
    #[token("?")] Question,
    #[token("(")] LParen,
    #[token(")")] RParen,
    #[token("{")] LBrace,
    #[token("}")] RBrace,
    #[token("[")] LBracket,
    #[token("]")] RBracket,
    #[token(",")] Comma,
    #[token(":")] Colon,
    #[token(".")] Dot,
    #[token(";")] Semi,
    #[token("#")] Hash,

    Eof,
}

impl TokenKind {
    /// A human-readable name for diagnostics.
    pub fn describe(self) -> &'static str {
        use TokenKind::*;
        match self {
            Newline => "newline",
            Ident => "identifier",
            Int => "integer literal",
            Float => "float literal",
            Str => "string literal",
            FStr => "interpolated string",
            Char => "char literal",
            Eof => "end of input",
            _ => "token",
        }
    }
}
