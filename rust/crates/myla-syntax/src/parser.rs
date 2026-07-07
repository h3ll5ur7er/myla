//! Recursive-descent + Pratt parser.
//!
//! Statement termination is newline-or-`;` (optional semicolons): a newline ends
//! a statement unless it sits inside `()`/`[]`, follows a binary operator, or
//! precedes a `.`/`|>`/`?` continuation. `;` is always an explicit terminator and
//! lets several statements share a line.

use crate::ast::*;
use crate::diagnostic::{Diagnostic, Stage};
use crate::lexer::Token;
use crate::span::Span;
use crate::token::TokenKind as T;

pub struct Parser<'s> {
    source: &'s str,
    tokens: Vec<Token>,
    pos: usize,
    errors: Vec<Diagnostic>,
    /// Suppress struct-literal parsing (in control-flow conditions / scrutinees).
    no_struct_lit: bool,
}

type PResult<A> = Result<A, ()>;

impl<'s> Parser<'s> {
    pub fn new(source: &'s str, tokens: Vec<Token>) -> Self {
        Parser {
            source,
            tokens,
            pos: 0,
            errors: Vec::new(),
            no_struct_lit: false,
        }
    }

    // --- token cursor ---

    fn peek(&self) -> Token {
        self.tokens[self.pos]
    }

    fn peek_kind(&self) -> T {
        self.tokens[self.pos].kind
    }

    fn nth_kind(&self, n: usize) -> T {
        self.tokens
            .get(self.pos + n)
            .map(|t| t.kind)
            .unwrap_or(T::Eof)
    }

    fn bump(&mut self) -> Token {
        let t = self.tokens[self.pos];
        if t.kind != T::Eof {
            self.pos += 1;
        }
        t
    }

    fn text(&self, tok: Token) -> &'s str {
        tok.text(self.source)
    }

    fn at(&self, kind: T) -> bool {
        self.peek_kind() == kind
    }

    fn eat(&mut self, kind: T) -> bool {
        if self.at(kind) {
            self.bump();
            true
        } else {
            false
        }
    }

    fn skip_newlines(&mut self) {
        while self.at(T::Newline) {
            self.bump();
        }
    }

    fn skip_separators(&mut self) {
        while matches!(self.peek_kind(), T::Newline | T::Semi) {
            self.bump();
        }
    }

    /// Index of the next non-newline token from `self.pos`.
    fn next_significant_kind(&self) -> T {
        let mut i = self.pos;
        while self.tokens.get(i).map(|t| t.kind) == Some(T::Newline) {
            i += 1;
        }
        self.tokens.get(i).map(|t| t.kind).unwrap_or(T::Eof)
    }

    fn error(&mut self, message: impl Into<String>, span: Span) {
        self.errors.push(Diagnostic::error(Stage::Parse, message, span));
    }

    fn expect(&mut self, kind: T, what: &str) -> PResult<Token> {
        if self.at(kind) {
            Ok(self.bump())
        } else {
            let tok = self.peek();
            self.error(
                format!("expected {what}, found {}", tok.kind.describe()),
                tok.span,
            );
            Err(())
        }
    }

    fn expect_ident(&mut self) -> PResult<(String, Span)> {
        let tok = self.expect(T::Ident, "identifier")?;
        Ok((self.text(tok).to_string(), tok.span))
    }

    // --- program ---

    pub fn parse_program(mut self) -> Result<Program, Vec<Diagnostic>> {
        let mut items = Vec::new();
        self.skip_separators();
        while !self.at(T::Eof) {
            match self.parse_item() {
                Ok(item) => items.push(item),
                Err(()) => {
                    self.recover_to_item();
                }
            }
            self.skip_separators();
        }
        if self.errors.is_empty() {
            Ok(Program { items })
        } else {
            Err(self.errors)
        }
    }

    /// Parse exactly one expression (for f-string holes / REPL).
    pub fn parse_single_expr(mut self) -> Result<Expr, Vec<Diagnostic>> {
        self.skip_newlines();
        match self.parse_expr() {
            Ok(e) if self.errors.is_empty() => Ok(e),
            _ => {
                if self.errors.is_empty() {
                    self.errors.push(Diagnostic::error(
                        Stage::Parse,
                        "expected an expression",
                        self.peek().span,
                    ));
                }
                Err(self.errors)
            }
        }
    }

    fn recover_to_item(&mut self) {
        while !matches!(
            self.peek_kind(),
            T::Eof | T::Fun | T::Struct | T::Enum | T::Trait | T::Impl | T::Const | T::Typealias
                | T::Import | T::From | T::Pub | T::Actor | T::Hash | T::Async
        ) {
            self.bump();
        }
    }

    // --- items ---

    fn parse_attributes(&mut self) -> PResult<Vec<Attribute>> {
        let mut attrs = Vec::new();
        while self.at(T::Hash) {
            let start = self.bump().span;
            let (name, _) = self.expect_ident()?;
            let mut args = Vec::new();
            let mut outputs = None;
            if self.eat(T::LParen) {
                self.skip_newlines();
                if !self.at(T::RParen) {
                    args = self.parse_comma_exprs(T::RParen)?;
                }
                self.expect(T::RParen, "`)`")?;
            }
            if self.eat(T::LBracket) {
                self.skip_newlines();
                let mut outs = Vec::new();
                if !self.at(T::RBracket) {
                    outs = self.parse_comma_exprs(T::RBracket)?;
                }
                self.expect(T::RBracket, "`]`")?;
                outputs = Some(outs);
            }
            let end = self.tokens[self.pos.saturating_sub(1)].span;
            attrs.push(Attribute {
                name,
                args,
                outputs,
                span: start.merge(end),
            });
            self.skip_newlines();
        }
        Ok(attrs)
    }

    fn parse_item(&mut self) -> PResult<Item> {
        let attrs = self.parse_attributes()?;
        let is_pub = self.eat(T::Pub);
        match self.peek_kind() {
            T::Fun | T::Async => Ok(Item::Function(self.parse_fun(attrs, is_pub)?)),
            T::Struct => Ok(Item::Struct(self.parse_struct(attrs, is_pub)?)),
            T::Enum => Ok(Item::Enum(self.parse_enum(attrs, is_pub)?)),
            T::Trait => Ok(Item::Trait(self.parse_trait(is_pub)?)),
            T::Impl => Ok(Item::Impl(self.parse_impl()?)),
            T::Actor => Ok(Item::Actor(self.parse_actor(is_pub)?)),
            T::Typealias => Ok(Item::TypeAlias(self.parse_typealias(is_pub)?)),
            T::Const => Ok(Item::Const(self.parse_const(is_pub)?)),
            T::Import | T::From => Ok(Item::Import(self.parse_import(is_pub)?)),
            _ => {
                let tok = self.peek();
                self.error(
                    format!("expected a declaration, found {}", tok.kind.describe()),
                    tok.span,
                );
                Err(())
            }
        }
    }

    fn parse_generics(&mut self) -> PResult<Vec<GenericParam>> {
        let mut params = Vec::new();
        if self.eat(T::Lt) {
            loop {
                self.skip_newlines();
                let (name, _) = self.expect_ident()?;
                let mut bounds = Vec::new();
                if self.eat(T::Colon) {
                    loop {
                        let (b, _) = self.expect_ident()?;
                        bounds.push(b);
                        if !self.eat(T::Plus) {
                            break;
                        }
                    }
                }
                params.push(GenericParam { name, bounds });
                if !self.eat(T::Comma) {
                    break;
                }
                if self.at(T::Gt) {
                    break;
                }
            }
            self.expect(T::Gt, "`>`")?;
        }
        Ok(params)
    }

    fn parse_fun(&mut self, attrs: Vec<Attribute>, is_pub: bool) -> PResult<FunDecl> {
        let is_async = self.eat(T::Async);
        let start = self.expect(T::Fun, "`fun`")?.span;
        let (name, _) = self.expect_ident()?;
        let generics = self.parse_generics()?;
        let params = self.parse_params()?;
        let ret = if self.eat(T::Arrow) {
            Some(self.parse_type()?)
        } else {
            None
        };
        let body = self.parse_block()?;
        let span = start.merge(body.span);
        Ok(FunDecl {
            name,
            generics,
            params,
            ret,
            body,
            is_async,
            attrs,
            is_pub,
            span,
        })
    }

    fn parse_params(&mut self) -> PResult<Vec<Param>> {
        self.expect(T::LParen, "`(`")?;
        let mut params = Vec::new();
        self.skip_newlines();
        while !self.at(T::RParen) {
            let self_mut = self.at(T::Var) && self.nth_kind(1) == T::SelfKw;
            if self_mut {
                self.bump();
            }
            if self.at(T::SelfKw) {
                let span = self.bump().span;
                params.push(Param {
                    name: "self".to_string(),
                    ty: None,
                    is_self: true,
                    self_mut,
                    span,
                });
            } else {
                let (name, span) = self.expect_ident()?;
                let ty = if self.eat(T::Colon) {
                    Some(self.parse_type()?)
                } else {
                    None
                };
                params.push(Param {
                    name,
                    ty,
                    is_self: false,
                    self_mut: false,
                    span,
                });
            }
            self.skip_newlines();
            if !self.eat(T::Comma) {
                break;
            }
            self.skip_newlines();
        }
        self.expect(T::RParen, "`)`")?;
        Ok(params)
    }

    fn parse_struct(&mut self, attrs: Vec<Attribute>, is_pub: bool) -> PResult<StructDecl> {
        let start = self.bump().span;
        let (name, _) = self.expect_ident()?;
        let generics = self.parse_generics()?;
        self.expect(T::LBrace, "`{`")?;
        let fields = self.parse_field_list()?;
        let end = self.expect(T::RBrace, "`}`")?.span;
        Ok(StructDecl {
            name,
            generics,
            fields,
            attrs,
            is_pub,
            span: start.merge(end),
        })
    }

    fn parse_field_list(&mut self) -> PResult<Vec<Field>> {
        let mut fields = Vec::new();
        self.skip_separators();
        while !self.at(T::RBrace) {
            let (name, _) = self.expect_ident()?;
            self.expect(T::Colon, "`:`")?;
            let ty = self.parse_type()?;
            fields.push(Field { name, ty });
            self.skip_newlines();
            if !self.eat(T::Comma) {
                self.skip_separators();
                if !self.at(T::RBrace) {
                    continue;
                }
                break;
            }
            self.skip_separators();
        }
        Ok(fields)
    }

    fn parse_enum(&mut self, attrs: Vec<Attribute>, is_pub: bool) -> PResult<EnumDecl> {
        let start = self.bump().span;
        let (name, _) = self.expect_ident()?;
        let generics = self.parse_generics()?;
        self.expect(T::LBrace, "`{`")?;
        let mut variants = Vec::new();
        self.skip_separators();
        while !self.at(T::RBrace) {
            let (vname, _) = self.expect_ident()?;
            let mut payload = Vec::new();
            if self.eat(T::LParen) {
                self.skip_newlines();
                while !self.at(T::RParen) {
                    payload.push(self.parse_type()?);
                    self.skip_newlines();
                    if !self.eat(T::Comma) {
                        break;
                    }
                    self.skip_newlines();
                }
                self.expect(T::RParen, "`)`")?;
            }
            variants.push(Variant { name: vname, payload });
            self.skip_newlines();
            self.eat(T::Comma);
            self.skip_separators();
        }
        let end = self.expect(T::RBrace, "`}`")?.span;
        Ok(EnumDecl {
            name,
            generics,
            variants,
            attrs,
            is_pub,
            span: start.merge(end),
        })
    }

    fn parse_trait(&mut self, is_pub: bool) -> PResult<TraitDecl> {
        let start = self.bump().span;
        let (name, _) = self.expect_ident()?;
        let generics = self.parse_generics()?;
        self.expect(T::LBrace, "`{`")?;
        let mut methods = Vec::new();
        self.skip_separators();
        while !self.at(T::RBrace) {
            methods.push(self.parse_fun(Vec::new(), false)?);
            self.skip_separators();
        }
        let end = self.expect(T::RBrace, "`}`")?.span;
        Ok(TraitDecl {
            name,
            generics,
            methods,
            is_pub,
            span: start.merge(end),
        })
    }

    fn parse_impl(&mut self) -> PResult<ImplDecl> {
        let start = self.bump().span;
        let generics = self.parse_generics()?;
        let first = self.parse_type()?;
        let (trait_name, type_name) = if self.eat(T::For) {
            let trait_n = match &first.kind {
                TypeKind::Named { name, .. } => Some(name.clone()),
                _ => None,
            };
            (trait_n, self.parse_type()?)
        } else {
            (None, first)
        };
        self.expect(T::LBrace, "`{`")?;
        let mut methods = Vec::new();
        self.skip_separators();
        while !self.at(T::RBrace) {
            let is_pub = self.eat(T::Pub);
            methods.push(self.parse_fun(Vec::new(), is_pub)?);
            self.skip_separators();
        }
        let end = self.expect(T::RBrace, "`}`")?.span;
        Ok(ImplDecl {
            generics,
            trait_name,
            type_name,
            methods,
            span: start.merge(end),
        })
    }

    fn parse_actor(&mut self, is_pub: bool) -> PResult<ActorDecl> {
        let start = self.bump().span;
        let (name, _) = self.expect_ident()?;
        self.expect(T::LBrace, "`{`")?;
        let mut fields = Vec::new();
        let mut methods = Vec::new();
        self.skip_separators();
        while !self.at(T::RBrace) {
            if self.at(T::Fun) || self.at(T::Async) {
                methods.push(self.parse_fun(Vec::new(), false)?);
            } else {
                let (fname, _) = self.expect_ident()?;
                self.expect(T::Colon, "`:`")?;
                let ty = self.parse_type()?;
                fields.push(Field { name: fname, ty });
                self.eat(T::Comma);
            }
            self.skip_separators();
        }
        let end = self.expect(T::RBrace, "`}`")?.span;
        Ok(ActorDecl {
            name,
            fields,
            methods,
            is_pub,
            span: start.merge(end),
        })
    }

    fn parse_typealias(&mut self, is_pub: bool) -> PResult<TypeAliasDecl> {
        let start = self.bump().span;
        let (name, _) = self.expect_ident()?;
        self.expect(T::Eq, "`=`")?;
        let target = self.parse_type()?;
        let span = start.merge(target.span);
        Ok(TypeAliasDecl {
            name,
            target,
            is_pub,
            span,
        })
    }

    fn parse_const(&mut self, is_pub: bool) -> PResult<ConstDecl> {
        let start = self.bump().span;
        let (name, _) = self.expect_ident()?;
        self.expect(T::Colon, "`:`")?;
        let ty = self.parse_type()?;
        self.expect(T::Eq, "`=`")?;
        let value = self.parse_expr()?;
        let span = start.merge(value.span);
        Ok(ConstDecl {
            name,
            ty,
            value,
            is_pub,
            span,
        })
    }

    fn parse_import(&mut self, is_pub: bool) -> PResult<ImportDecl> {
        let start = self.peek().span;
        if self.eat(T::From) {
            let mut path = Vec::new();
            loop {
                while self.at(T::Dot) {
                    self.bump();
                }
                let (seg, _) = self.expect_ident()?;
                path.push(seg);
                if !self.eat(T::Dot) {
                    break;
                }
            }
            self.expect(T::Import, "`import`")?;
            let mut items = Vec::new();
            loop {
                let (name, _) = self.expect_ident()?;
                let alias = if self.eat(T::As) {
                    Some(self.expect_ident()?.0)
                } else {
                    None
                };
                items.push((name, alias));
                if !self.eat(T::Comma) {
                    break;
                }
            }
            Ok(ImportDecl {
                path,
                items: Some(items),
                alias: None,
                is_pub,
                span: start,
            })
        } else {
            self.expect(T::Import, "`import`")?;
            let mut path = Vec::new();
            loop {
                let (seg, _) = self.expect_ident()?;
                path.push(seg);
                if !self.eat(T::Dot) {
                    break;
                }
            }
            let alias = if self.eat(T::As) {
                Some(self.expect_ident()?.0)
            } else {
                None
            };
            Ok(ImportDecl {
                path,
                items: None,
                alias,
                is_pub,
                span: start,
            })
        }
    }

    // --- types ---

    fn parse_type(&mut self) -> PResult<TypeExpr> {
        let tok = self.peek();
        let start = tok.span;
        match tok.kind {
            T::LParen => {
                self.bump();
                self.skip_newlines();
                let mut elems = Vec::new();
                let mut trailing_comma = false;
                while !self.at(T::RParen) {
                    elems.push(self.parse_type()?);
                    self.skip_newlines();
                    if self.eat(T::Comma) {
                        trailing_comma = true;
                        self.skip_newlines();
                    } else {
                        trailing_comma = false;
                        break;
                    }
                }
                let end = self.expect(T::RParen, "`)`")?.span;
                if self.eat(T::Arrow) {
                    let ret = self.parse_type()?;
                    let span = start.merge(ret.span);
                    return Ok(TypeExpr {
                        kind: TypeKind::Func {
                            params: elems,
                            ret: Box::new(ret),
                        },
                        span,
                    });
                }
                if elems.len() == 1 && !trailing_comma {
                    return Ok(elems.into_iter().next().unwrap());
                }
                Ok(TypeExpr {
                    kind: TypeKind::Tuple(elems),
                    span: start.merge(end),
                })
            }
            T::LBracket => {
                self.bump();
                let key = self.parse_type()?;
                if self.eat(T::Colon) {
                    let val = self.parse_type()?;
                    let end = self.expect(T::RBracket, "`]`")?.span;
                    Ok(TypeExpr {
                        kind: TypeKind::Map(Box::new(key), Box::new(val)),
                        span: start.merge(end),
                    })
                } else {
                    let end = self.expect(T::RBracket, "`]`")?.span;
                    Ok(TypeExpr {
                        kind: TypeKind::List(Box::new(key)),
                        span: start.merge(end),
                    })
                }
            }
            T::Chan => {
                self.bump();
                self.expect(T::Lt, "`<`")?;
                let inner = self.parse_type()?;
                let end = self.expect(T::Gt, "`>`")?.span;
                Ok(TypeExpr {
                    kind: TypeKind::Chan(Box::new(inner)),
                    span: start.merge(end),
                })
            }
            T::SelfKw => {
                let span = self.bump().span;
                Ok(TypeExpr {
                    kind: TypeKind::SelfType,
                    span,
                })
            }
            T::Ident | T::Str => {
                // sized-type keywords arrive as idents; `str`/`bool` too if not keyworded
                let (name, nspan) = self.parse_type_name()?;
                let mut args = Vec::new();
                let mut end = nspan;
                if self.at(T::Lt) {
                    self.bump();
                    loop {
                        self.skip_newlines();
                        args.push(self.parse_type()?);
                        self.skip_newlines();
                        if !self.eat(T::Comma) {
                            break;
                        }
                    }
                    end = self.expect(T::Gt, "`>`")?.span;
                }
                Ok(TypeExpr {
                    kind: TypeKind::Named { name, args },
                    span: start.merge(end),
                })
            }
            _ => {
                self.error(
                    format!("expected a type, found {}", tok.kind.describe()),
                    tok.span,
                );
                Err(())
            }
        }
    }

    fn parse_type_name(&mut self) -> PResult<(String, Span)> {
        let tok = self.bump();
        let name = self.text(tok).to_string();
        Ok((name, tok.span))
    }

    // --- statements & blocks ---

    fn parse_block(&mut self) -> PResult<Block> {
        let start = self.expect(T::LBrace, "`{`")?.span;
        let mut stmts = Vec::new();
        let mut tail = None;
        self.skip_separators();
        while !self.at(T::RBrace) && !self.at(T::Eof) {
            let stmt = self.parse_stmt()?;
            // A trailing expression with no following statement becomes the block's value.
            if let StmtKind::Expr(e) = &stmt.kind {
                self.skip_newlines();
                if self.at(T::RBrace) {
                    tail = Some(Box::new(e.clone()));
                    break;
                }
            }
            stmts.push(stmt);
            self.skip_separators();
        }
        let end = self.expect(T::RBrace, "`}`")?.span;
        Ok(Block {
            stmts,
            tail,
            span: start.merge(end),
        })
    }

    fn parse_stmt(&mut self) -> PResult<Stmt> {
        let start = self.peek().span;
        match self.peek_kind() {
            T::Let | T::Var => {
                let kind = if self.bump().kind == T::Let {
                    LetKind::Let
                } else {
                    LetKind::Var
                };
                let (name, _) = self.expect_ident()?;
                let ty = if self.eat(T::Colon) {
                    Some(self.parse_type()?)
                } else {
                    None
                };
                self.expect(T::Eq, "`=`")?;
                self.skip_newlines();
                let init = self.parse_expr()?;
                let span = start.merge(init.span);
                Ok(Stmt {
                    kind: StmtKind::Let {
                        kind,
                        name,
                        ty,
                        init,
                    },
                    span,
                })
            }
            T::Return => {
                self.bump();
                let value = if matches!(self.peek_kind(), T::Newline | T::Semi | T::RBrace | T::Eof) {
                    None
                } else {
                    Some(self.parse_expr()?)
                };
                let span = value.as_ref().map(|v| start.merge(v.span)).unwrap_or(start);
                Ok(Stmt {
                    kind: StmtKind::Return(value),
                    span,
                })
            }
            T::Break => {
                let span = self.bump().span;
                Ok(Stmt {
                    kind: StmtKind::Break,
                    span,
                })
            }
            T::Continue => {
                let span = self.bump().span;
                Ok(Stmt {
                    kind: StmtKind::Continue,
                    span,
                })
            }
            T::While => {
                self.bump();
                let saved = self.no_struct_lit;
                self.no_struct_lit = true;
                let cond = self.parse_expr()?;
                self.no_struct_lit = saved;
                let body = self.parse_block()?;
                let span = start.merge(body.span);
                Ok(Stmt {
                    kind: StmtKind::While { cond, body },
                    span,
                })
            }
            T::For => {
                self.bump();
                let (var, _) = self.expect_ident()?;
                self.expect(T::In, "`in`")?;
                let saved = self.no_struct_lit;
                self.no_struct_lit = true;
                let iter = self.parse_expr()?;
                self.no_struct_lit = saved;
                let body = self.parse_block()?;
                let span = start.merge(body.span);
                Ok(Stmt {
                    kind: StmtKind::For { var, iter, body },
                    span,
                })
            }
            T::Select => {
                self.bump();
                self.expect(T::LBrace, "`{`")?;
                let mut arms = Vec::new();
                self.skip_separators();
                while !self.at(T::RBrace) {
                    let binding = if self.at(T::Ident) && self.nth_kind(1) == T::Eq {
                        let (n, _) = self.expect_ident()?;
                        self.bump();
                        Some(n)
                    } else {
                        None
                    };
                    let channel = self.parse_expr()?;
                    self.expect(T::FatArrow, "`=>`")?;
                    let body = self.parse_block()?;
                    arms.push(SelectArm {
                        binding,
                        channel,
                        body,
                    });
                    self.skip_separators();
                }
                let end = self.expect(T::RBrace, "`}`")?.span;
                Ok(Stmt {
                    kind: StmtKind::Select(arms),
                    span: start.merge(end),
                })
            }
            _ => {
                let expr = self.parse_expr()?;
                // assignment?
                if let Some(op) = self.peek_assign_op() {
                    self.skip_newlines();
                    let value = self.parse_expr()?;
                    let span = expr.span.merge(value.span);
                    return Ok(Stmt {
                        kind: StmtKind::Assign {
                            target: expr,
                            op,
                            value,
                        },
                        span,
                    });
                }
                let span = expr.span;
                Ok(Stmt {
                    kind: StmtKind::Expr(expr),
                    span,
                })
            }
        }
    }

    /// If the cursor is at an assignment operator, consume it and return the
    /// optional compound op (None = plain `=`).
    fn peek_assign_op(&mut self) -> Option<Option<BinOp>> {
        let (op, len): (Option<BinOp>, usize) = match self.peek_kind() {
            T::Eq => (None, 1),
            _ => return None,
        };
        for _ in 0..len {
            self.bump();
        }
        Some(op)
    }

    // --- expressions (Pratt) ---

    fn parse_expr(&mut self) -> PResult<Expr> {
        self.parse_expr_bp(0)
    }

    fn parse_expr_bp(&mut self, min_bp: u8) -> PResult<Expr> {
        let mut lhs = self.parse_prefix()?;
        loop {
            // method-chain / try continuation across newlines
            if self.at(T::Newline) {
                let next = self.next_significant_kind();
                if matches!(next, T::Dot | T::PipeArrow | T::Question) {
                    self.skip_newlines();
                } else {
                    break;
                }
            }
            let Some((op, l_bp, r_bp, advance)) = self.peek_infix() else {
                break;
            };
            if l_bp < min_bp {
                break;
            }
            // pipeline and range handled as distinct ExprKinds
            match op {
                InfixOp::Pipe => {
                    for _ in 0..advance {
                        self.bump();
                    }
                    self.skip_newlines();
                    let rhs = self.parse_expr_bp(r_bp)?;
                    let span = lhs.span.merge(rhs.span);
                    lhs = Expr {
                        kind: ExprKind::Pipe {
                            lhs: Box::new(lhs),
                            rhs: Box::new(rhs),
                        },
                        span,
                    };
                }
                InfixOp::Range => {
                    for _ in 0..advance {
                        self.bump();
                    }
                    self.skip_newlines();
                    let rhs = self.parse_expr_bp(r_bp)?;
                    let span = lhs.span.merge(rhs.span);
                    lhs = Expr {
                        kind: ExprKind::Range {
                            start: Box::new(lhs),
                            end: Box::new(rhs),
                        },
                        span,
                    };
                }
                InfixOp::Bin(b) => {
                    for _ in 0..advance {
                        self.bump();
                    }
                    self.skip_newlines();
                    let rhs = self.parse_expr_bp(r_bp)?;
                    let span = lhs.span.merge(rhs.span);
                    lhs = Expr {
                        kind: ExprKind::Binary {
                            op: b,
                            lhs: Box::new(lhs),
                            rhs: Box::new(rhs),
                        },
                        span,
                    };
                }
            }
        }
        Ok(lhs)
    }

    fn peek_infix(&self) -> Option<(InfixOp, u8, u8, usize)> {
        use InfixOp::*;
        let k = self.peek_kind();
        let next = self.nth_kind(1);
        let adjacent = self.peek().span.end == self.tokens.get(self.pos + 1).map(|t| t.span.start).unwrap_or(usize::MAX);
        Some(match k {
            T::PipeArrow => (Pipe, 1, 2, 1),
            T::DotDot => (Range, 3, 4, 1),
            T::PipePipe => (Bin(BinOp::Or), 5, 6, 1),
            T::AmpAmp => (Bin(BinOp::And), 7, 8, 1),
            T::EqEq => (Bin(BinOp::Eq), 9, 10, 1),
            T::NotEq => (Bin(BinOp::Ne), 9, 10, 1),
            T::Lt if next == T::Lt && adjacent => (Bin(BinOp::Shl), 19, 20, 2),
            T::Gt if next == T::Gt && adjacent => (Bin(BinOp::Shr), 19, 20, 2),
            T::Lt => (Bin(BinOp::Lt), 11, 12, 1),
            T::LtEq => (Bin(BinOp::Le), 11, 12, 1),
            T::Gt => (Bin(BinOp::Gt), 11, 12, 1),
            T::GtEq => (Bin(BinOp::Ge), 11, 12, 1),
            T::Pipe => (Bin(BinOp::BitOr), 13, 14, 1),
            T::Caret => (Bin(BinOp::BitXor), 15, 16, 1),
            T::Amp => (Bin(BinOp::BitAnd), 17, 18, 1),
            T::Plus => (Bin(BinOp::Add), 21, 22, 1),
            T::Minus => (Bin(BinOp::Sub), 21, 22, 1),
            T::Star => (Bin(BinOp::Mul), 23, 24, 1),
            T::Slash => (Bin(BinOp::Div), 23, 24, 1),
            T::Percent => (Bin(BinOp::Rem), 23, 24, 1),
            _ => return None,
        })
    }

    fn parse_prefix(&mut self) -> PResult<Expr> {
        let tok = self.peek();
        let start = tok.span;
        let mut expr = match tok.kind {
            T::Minus => {
                self.bump();
                let e = self.parse_prefix()?;
                let span = start.merge(e.span);
                Expr {
                    kind: ExprKind::Unary {
                        op: UnOp::Neg,
                        expr: Box::new(e),
                    },
                    span,
                }
            }
            T::Bang => {
                self.bump();
                let e = self.parse_prefix()?;
                let span = start.merge(e.span);
                Expr {
                    kind: ExprKind::Unary {
                        op: UnOp::Not,
                        expr: Box::new(e),
                    },
                    span,
                }
            }
            T::Tilde => {
                self.bump();
                let e = self.parse_prefix()?;
                let span = start.merge(e.span);
                Expr {
                    kind: ExprKind::Unary {
                        op: UnOp::BitNot,
                        expr: Box::new(e),
                    },
                    span,
                }
            }
            T::Await => {
                self.bump();
                let e = self.parse_prefix()?;
                let span = start.merge(e.span);
                Expr {
                    kind: ExprKind::Await(Box::new(e)),
                    span,
                }
            }
            T::Spawn | T::Go => {
                self.bump();
                let e = self.parse_prefix()?;
                let span = start.merge(e.span);
                Expr {
                    kind: ExprKind::Spawn(Box::new(e)),
                    span,
                }
            }
            _ => self.parse_postfix()?,
        };
        // `as` cast binds tightly
        while self.at(T::As) {
            self.bump();
            let ty = self.parse_type()?;
            let span = expr.span.merge(ty.span);
            expr = Expr {
                kind: ExprKind::Cast {
                    expr: Box::new(expr),
                    ty,
                },
                span,
            };
        }
        Ok(expr)
    }

    fn parse_postfix(&mut self) -> PResult<Expr> {
        let mut expr = self.parse_primary()?;
        loop {
            match self.peek_kind() {
                T::LParen => {
                    self.bump();
                    let args = self.parse_call_args()?;
                    let end = self.expect(T::RParen, "`)`")?.span;
                    let span = expr.span.merge(end);
                    expr = Expr {
                        kind: ExprKind::Call {
                            callee: Box::new(expr),
                            args,
                        },
                        span,
                    };
                }
                T::Dot => {
                    self.bump();
                    let (name, nspan) = self.expect_ident()?;
                    if self.at(T::LParen) {
                        self.bump();
                        let args = self.parse_call_args()?;
                        let end = self.expect(T::RParen, "`)`")?.span;
                        let span = expr.span.merge(end);
                        expr = Expr {
                            kind: ExprKind::MethodCall {
                                recv: Box::new(expr),
                                method: name,
                                args,
                            },
                            span,
                        };
                    } else {
                        let span = expr.span.merge(nspan);
                        expr = Expr {
                            kind: ExprKind::Field {
                                recv: Box::new(expr),
                                name,
                            },
                            span,
                        };
                    }
                }
                T::LBracket => {
                    self.bump();
                    self.skip_newlines();
                    let index = self.parse_expr()?;
                    let end = self.expect(T::RBracket, "`]`")?.span;
                    let span = expr.span.merge(end);
                    expr = Expr {
                        kind: ExprKind::Index {
                            recv: Box::new(expr),
                            index: Box::new(index),
                        },
                        span,
                    };
                }
                T::Question => {
                    let end = self.bump().span;
                    let span = expr.span.merge(end);
                    expr = Expr {
                        kind: ExprKind::Try(Box::new(expr)),
                        span,
                    };
                }
                _ => break,
            }
        }
        Ok(expr)
    }

    fn parse_call_args(&mut self) -> PResult<Vec<Expr>> {
        self.skip_newlines();
        let mut args = Vec::new();
        while !self.at(T::RParen) {
            args.push(self.parse_expr()?);
            self.skip_newlines();
            if !self.eat(T::Comma) {
                break;
            }
            self.skip_newlines();
        }
        Ok(args)
    }

    fn parse_comma_exprs(&mut self, close: T) -> PResult<Vec<Expr>> {
        let mut exprs = Vec::new();
        while !self.at(close) {
            exprs.push(self.parse_expr()?);
            self.skip_newlines();
            if !self.eat(T::Comma) {
                break;
            }
            self.skip_newlines();
        }
        Ok(exprs)
    }

    fn parse_primary(&mut self) -> PResult<Expr> {
        let tok = self.peek();
        let span = tok.span;
        match tok.kind {
            T::Int => {
                self.bump();
                Ok(Expr {
                    kind: ExprKind::Int {
                        text: self.text(tok).to_string(),
                    },
                    span,
                })
            }
            T::Float => {
                self.bump();
                Ok(Expr {
                    kind: ExprKind::Float {
                        text: self.text(tok).to_string(),
                    },
                    span,
                })
            }
            T::Str => {
                self.bump();
                Ok(Expr {
                    kind: ExprKind::Str(unescape_str(self.text(tok))),
                    span,
                })
            }
            T::FStr => {
                self.bump();
                let parts = self.parse_fstring(self.text(tok), span)?;
                Ok(Expr {
                    kind: ExprKind::FStr(parts),
                    span,
                })
            }
            T::Char => {
                self.bump();
                Ok(Expr {
                    kind: ExprKind::Char(unescape_char(self.text(tok))),
                    span,
                })
            }
            T::True => {
                self.bump();
                Ok(Expr {
                    kind: ExprKind::Bool(true),
                    span,
                })
            }
            T::False => {
                self.bump();
                Ok(Expr {
                    kind: ExprKind::Bool(false),
                    span,
                })
            }
            T::SelfKw => {
                self.bump();
                Ok(Expr {
                    kind: ExprKind::SelfExpr,
                    span,
                })
            }
            T::Ident => {
                // lambda?  `(...) =>` is handled at LParen; bare ident here
                self.bump();
                let name = self.text(tok).to_string();
                // struct literal?
                if self.at(T::LBrace) && !self.no_struct_lit && self.looks_like_struct_lit() {
                    return self.parse_struct_lit(name, span);
                }
                if name == "_" {
                    return Ok(Expr {
                        kind: ExprKind::Hole,
                        span,
                    });
                }
                Ok(Expr {
                    kind: ExprKind::Name(name),
                    span,
                })
            }
            T::LParen => self.parse_paren_or_lambda(),
            T::LBracket => self.parse_list_or_map(),
            T::LBrace => {
                let block = self.parse_block()?;
                let bspan = block.span;
                Ok(Expr {
                    kind: ExprKind::Block(block),
                    span: bspan,
                })
            }
            T::If => self.parse_if(),
            T::Match => self.parse_match(),
            _ => {
                self.error(
                    format!("expected an expression, found {}", tok.kind.describe()),
                    tok.span,
                );
                Err(())
            }
        }
    }

    fn looks_like_struct_lit(&self) -> bool {
        // at `{`; struct lit if `}` follows, or `ident :`
        if self.nth_kind(1) == T::RBrace {
            return true;
        }
        self.nth_kind(1) == T::Ident && self.nth_kind(2) == T::Colon
    }

    fn parse_struct_lit(&mut self, name: String, start: Span) -> PResult<Expr> {
        self.expect(T::LBrace, "`{`")?;
        self.skip_newlines();
        let mut fields = Vec::new();
        while !self.at(T::RBrace) {
            let (fname, _) = self.expect_ident()?;
            let value = if self.eat(T::Colon) {
                self.parse_expr()?
            } else {
                // field shorthand `Point { x, y }`
                Expr {
                    kind: ExprKind::Name(fname.clone()),
                    span: start,
                }
            };
            fields.push((fname, value));
            self.skip_newlines();
            if !self.eat(T::Comma) {
                break;
            }
            self.skip_newlines();
        }
        let end = self.expect(T::RBrace, "`}`")?.span;
        Ok(Expr {
            kind: ExprKind::StructLit { name, fields },
            span: start.merge(end),
        })
    }

    fn parse_paren_or_lambda(&mut self) -> PResult<Expr> {
        if self.is_lambda_ahead() {
            return self.parse_lambda();
        }
        let start = self.expect(T::LParen, "`(`")?.span;
        self.skip_newlines();
        if self.at(T::RParen) {
            let end = self.bump().span;
            return Ok(Expr {
                kind: ExprKind::TupleLit(Vec::new()),
                span: start.merge(end),
            });
        }
        let first = self.parse_expr()?;
        self.skip_newlines();
        if self.eat(T::Comma) {
            self.skip_newlines();
            let mut elems = vec![first];
            while !self.at(T::RParen) {
                elems.push(self.parse_expr()?);
                self.skip_newlines();
                if !self.eat(T::Comma) {
                    break;
                }
                self.skip_newlines();
            }
            let end = self.expect(T::RParen, "`)`")?.span;
            Ok(Expr {
                kind: ExprKind::TupleLit(elems),
                span: start.merge(end),
            })
        } else {
            self.expect(T::RParen, "`)`")?;
            Ok(first)
        }
    }

    /// Look ahead from a `(` to its matching `)` and check for a following `=>`.
    fn is_lambda_ahead(&self) -> bool {
        if !self.at(T::LParen) {
            return false;
        }
        let mut depth = 0i32;
        let mut i = self.pos;
        while let Some(t) = self.tokens.get(i) {
            match t.kind {
                T::LParen => depth += 1,
                T::RParen => {
                    depth -= 1;
                    if depth == 0 {
                        // skip newlines after
                        let mut j = i + 1;
                        while self.tokens.get(j).map(|t| t.kind) == Some(T::Newline) {
                            j += 1;
                        }
                        return self.tokens.get(j).map(|t| t.kind) == Some(T::FatArrow);
                    }
                }
                T::Eof => return false,
                _ => {}
            }
            i += 1;
        }
        false
    }

    fn parse_lambda(&mut self) -> PResult<Expr> {
        let params = self.parse_params()?;
        let start = params.first().map(|p| p.span).unwrap_or(self.peek().span);
        self.expect(T::FatArrow, "`=>`")?;
        self.skip_newlines();
        let body = self.parse_expr()?;
        let span = start.merge(body.span);
        Ok(Expr {
            kind: ExprKind::Lambda {
                params,
                body: Box::new(body),
            },
            span,
        })
    }

    fn parse_list_or_map(&mut self) -> PResult<Expr> {
        let start = self.expect(T::LBracket, "`[`")?.span;
        self.skip_newlines();
        // empty map `[:]`
        if self.at(T::Colon) {
            self.bump();
            let end = self.expect(T::RBracket, "`]`")?.span;
            return Ok(Expr {
                kind: ExprKind::MapLit(Vec::new()),
                span: start.merge(end),
            });
        }
        if self.at(T::RBracket) {
            let end = self.bump().span;
            return Ok(Expr {
                kind: ExprKind::ListLit(Vec::new()),
                span: start.merge(end),
            });
        }
        let first = self.parse_expr()?;
        self.skip_newlines();
        if self.eat(T::Colon) {
            // map literal
            self.skip_newlines();
            let v = self.parse_expr()?;
            let mut entries = vec![(first, v)];
            self.skip_newlines();
            while self.eat(T::Comma) {
                self.skip_newlines();
                if self.at(T::RBracket) {
                    break;
                }
                let k = self.parse_expr()?;
                self.expect(T::Colon, "`:`")?;
                self.skip_newlines();
                let v = self.parse_expr()?;
                entries.push((k, v));
                self.skip_newlines();
            }
            let end = self.expect(T::RBracket, "`]`")?.span;
            Ok(Expr {
                kind: ExprKind::MapLit(entries),
                span: start.merge(end),
            })
        } else {
            let mut elems = vec![first];
            while self.eat(T::Comma) {
                self.skip_newlines();
                if self.at(T::RBracket) {
                    break;
                }
                elems.push(self.parse_expr()?);
                self.skip_newlines();
            }
            let end = self.expect(T::RBracket, "`]`")?.span;
            Ok(Expr {
                kind: ExprKind::ListLit(elems),
                span: start.merge(end),
            })
        }
    }

    fn parse_if(&mut self) -> PResult<Expr> {
        let start = self.expect(T::If, "`if`")?.span;
        let saved = self.no_struct_lit;
        self.no_struct_lit = true;
        let cond = self.parse_expr()?;
        self.no_struct_lit = saved;
        let then = self.parse_block()?;
        let otherwise = if self.eat(T::Else) {
            if self.at(T::If) {
                Some(Box::new(self.parse_if()?))
            } else {
                let block = self.parse_block()?;
                let bspan = block.span;
                Some(Box::new(Expr {
                    kind: ExprKind::Block(block),
                    span: bspan,
                }))
            }
        } else {
            None
        };
        let end = otherwise
            .as_ref()
            .map(|e| e.span)
            .unwrap_or(then.span);
        Ok(Expr {
            kind: ExprKind::If {
                cond: Box::new(cond),
                then,
                otherwise,
            },
            span: start.merge(end),
        })
    }

    fn parse_match(&mut self) -> PResult<Expr> {
        let start = self.expect(T::Match, "`match`")?.span;
        let saved = self.no_struct_lit;
        self.no_struct_lit = true;
        let scrutinee = self.parse_expr()?;
        self.no_struct_lit = saved;
        self.expect(T::LBrace, "`{`")?;
        let mut arms = Vec::new();
        self.skip_separators();
        while !self.at(T::RBrace) {
            let astart = self.peek().span;
            let pattern = self.parse_pattern()?;
            let guard = if self.eat(T::If) {
                Some(self.parse_expr()?)
            } else {
                None
            };
            self.expect(T::FatArrow, "`=>`")?;
            self.skip_newlines();
            let body = self.parse_expr()?;
            let aspan = astart.merge(body.span);
            arms.push(MatchArm {
                pattern,
                guard,
                body,
                span: aspan,
            });
            self.skip_newlines();
            self.eat(T::Comma);
            self.skip_separators();
        }
        let end = self.expect(T::RBrace, "`}`")?.span;
        Ok(Expr {
            kind: ExprKind::Match {
                scrutinee: Box::new(scrutinee),
                arms,
            },
            span: start.merge(end),
        })
    }

    fn parse_pattern(&mut self) -> PResult<Pattern> {
        let first = self.parse_pattern_atom()?;
        if self.at(T::Pipe) {
            let mut alts = vec![first];
            while self.eat(T::Pipe) {
                self.skip_newlines();
                alts.push(self.parse_pattern_atom()?);
            }
            let span = alts.first().unwrap().span.merge(alts.last().unwrap().span);
            Ok(Pattern {
                kind: PatternKind::Or(alts),
                span,
            })
        } else {
            Ok(first)
        }
    }

    fn parse_pattern_atom(&mut self) -> PResult<Pattern> {
        let tok = self.peek();
        let start = tok.span;
        match tok.kind {
            T::Ident if self.text(tok) == "_" => {
                self.bump();
                Ok(Pattern {
                    kind: PatternKind::Wildcard,
                    span: start,
                })
            }
            T::Int => {
                self.bump();
                Ok(Pattern {
                    kind: PatternKind::Int(self.text(tok).to_string()),
                    span: start,
                })
            }
            T::Str => {
                self.bump();
                Ok(Pattern {
                    kind: PatternKind::Str(unescape_str(self.text(tok))),
                    span: start,
                })
            }
            T::Char => {
                self.bump();
                Ok(Pattern {
                    kind: PatternKind::Char(unescape_char(self.text(tok))),
                    span: start,
                })
            }
            T::True => {
                self.bump();
                Ok(Pattern {
                    kind: PatternKind::Bool(true),
                    span: start,
                })
            }
            T::False => {
                self.bump();
                Ok(Pattern {
                    kind: PatternKind::Bool(false),
                    span: start,
                })
            }
            T::LParen => {
                self.bump();
                self.skip_newlines();
                let mut subs = Vec::new();
                while !self.at(T::RParen) {
                    subs.push(self.parse_pattern()?);
                    self.skip_newlines();
                    if !self.eat(T::Comma) {
                        break;
                    }
                    self.skip_newlines();
                }
                let end = self.expect(T::RParen, "`)`")?.span;
                Ok(Pattern {
                    kind: PatternKind::Tuple(subs),
                    span: start.merge(end),
                })
            }
            T::Dot | T::Ident => {
                // `.Variant`, `Enum.Variant`, `Variant(...)`, or a binding
                let leading_dot = self.eat(T::Dot);
                let (first_name, _) = self.expect_ident()?;
                let mut path = vec![first_name.clone()];
                while self.eat(T::Dot) {
                    let (seg, _) = self.expect_ident()?;
                    path.push(seg);
                }
                // struct pattern?
                if self.at(T::LBrace) {
                    self.bump();
                    self.skip_newlines();
                    let mut fields = Vec::new();
                    while !self.at(T::RBrace) {
                        let (fname, _) = self.expect_ident()?;
                        let pat = if self.eat(T::Colon) {
                            self.parse_pattern()?
                        } else {
                            Pattern {
                                kind: PatternKind::Binding(fname.clone()),
                                span: start,
                            }
                        };
                        fields.push((fname, pat));
                        self.skip_newlines();
                        if !self.eat(T::Comma) {
                            break;
                        }
                        self.skip_newlines();
                    }
                    let end = self.expect(T::RBrace, "`}`")?.span;
                    return Ok(Pattern {
                        kind: PatternKind::Struct {
                            name: path.join("."),
                            fields,
                        },
                        span: start.merge(end),
                    });
                }
                if self.at(T::LParen) {
                    self.bump();
                    self.skip_newlines();
                    let mut subs = Vec::new();
                    while !self.at(T::RParen) {
                        subs.push(self.parse_pattern()?);
                        self.skip_newlines();
                        if !self.eat(T::Comma) {
                            break;
                        }
                        self.skip_newlines();
                    }
                    let end = self.expect(T::RParen, "`)`")?.span;
                    return Ok(Pattern {
                        kind: PatternKind::Variant { path, sub: subs },
                        span: start.merge(end),
                    });
                }
                // bare lowercase ident with no path -> binding; otherwise a nullary variant
                if !leading_dot && path.len() == 1 && is_lower(&path[0]) {
                    Ok(Pattern {
                        kind: PatternKind::Binding(path.into_iter().next().unwrap()),
                        span: start,
                    })
                } else {
                    Ok(Pattern {
                        kind: PatternKind::Variant { path, sub: Vec::new() },
                        span: start,
                    })
                }
            }
            _ => {
                self.error("expected a pattern", tok.span);
                Err(())
            }
        }
    }

    // --- f-strings ---

    fn parse_fstring(&mut self, raw: &str, span: Span) -> PResult<Vec<FStrPart>> {
        // raw includes the leading `f"` and trailing `"`.
        let inner = &raw[2..raw.len() - 1];
        let mut parts = Vec::new();
        let mut lit = String::new();
        let bytes: Vec<char> = inner.chars().collect();
        let mut i = 0;
        while i < bytes.len() {
            let c = bytes[i];
            if c == '{' {
                if i + 1 < bytes.len() && bytes[i + 1] == '{' {
                    lit.push('{');
                    i += 2;
                    continue;
                }
                if !lit.is_empty() {
                    parts.push(FStrPart::Lit(unescape_body(&lit)));
                    lit.clear();
                }
                // collect until matching `}`
                let mut depth = 1;
                let mut expr_src = String::new();
                i += 1;
                while i < bytes.len() && depth > 0 {
                    match bytes[i] {
                        '{' => {
                            depth += 1;
                            expr_src.push('{');
                        }
                        '}' => {
                            depth -= 1;
                            if depth > 0 {
                                expr_src.push('}');
                            }
                        }
                        ch => expr_src.push(ch),
                    }
                    i += 1;
                }
                match crate::parse_expr_string(&expr_src) {
                    Ok(e) => parts.push(FStrPart::Expr(Box::new(e))),
                    Err(_) => {
                        self.error("invalid expression in interpolation", span);
                        return Err(());
                    }
                }
            } else if c == '}' {
                if i + 1 < bytes.len() && bytes[i + 1] == '}' {
                    lit.push('}');
                    i += 2;
                    continue;
                }
                lit.push('}');
                i += 1;
            } else {
                lit.push(c);
                i += 1;
            }
        }
        if !lit.is_empty() {
            parts.push(FStrPart::Lit(unescape_body(&lit)));
        }
        Ok(parts)
    }
}

#[derive(Clone, Copy)]
enum InfixOp {
    Bin(BinOp),
    Pipe,
    Range,
}

fn is_lower(s: &str) -> bool {
    s.chars().next().map(|c| c.is_lowercase() || c == '_').unwrap_or(false)
}

fn unescape_str(raw: &str) -> String {
    // raw includes surrounding quotes
    unescape_body(&raw[1..raw.len() - 1])
}

fn unescape_body(s: &str) -> String {
    let mut out = String::new();
    let mut chars = s.chars();
    while let Some(c) = chars.next() {
        if c == '\\' {
            match chars.next() {
                Some('n') => out.push('\n'),
                Some('t') => out.push('\t'),
                Some('r') => out.push('\r'),
                Some('\\') => out.push('\\'),
                Some('"') => out.push('"'),
                Some('\'') => out.push('\''),
                Some('0') => out.push('\0'),
                Some('u') => {
                    // \u{XXXX}
                    let mut hex = String::new();
                    if let Some('{') = chars.clone().next() {
                        chars.next();
                        for c in chars.by_ref() {
                            if c == '}' {
                                break;
                            }
                            hex.push(c);
                        }
                        if let Ok(cp) = u32::from_str_radix(&hex, 16) {
                            if let Some(ch) = char::from_u32(cp) {
                                out.push(ch);
                            }
                        }
                    }
                }
                Some(other) => out.push(other),
                None => {}
            }
        } else {
            out.push(c);
        }
    }
    out
}

fn unescape_char(raw: &str) -> char {
    let body = &raw[1..raw.len() - 1];
    unescape_body(body).chars().next().unwrap_or('\0')
}

#[cfg(test)]
mod tests {
    use crate::parse_program;

    fn ok(src: &str) {
        if let Err(errs) = parse_program(src) {
            panic!("parse failed for {src:?}: {errs:?}");
        }
    }

    #[test]
    fn parses_core_program() {
        ok(r#"
struct Point { x: int, y: int }

enum Shape { Circle(float), Rect(int, int) }

fun area(s: Shape) -> float {
    match s {
        Shape.Circle(r) => 3.14 * r * r,
        Shape.Rect(w, h) => (w * h) as float,
    }
}

#main
fun main() {
    let p = Point { x: 1, y: 2 }
    var total = 0; var i = 0
    while i < 10 { total = total + i; i = i + 1 }
    for k in 0..5 { print(k) }
    let xs = [1, 2, 3]
    let m = ["a": 1, "b": 2]
    let f = (a: int, b: int) => a + b
    let r = xs |> len
    print(f"sum is {total}")
}
"#);
    }

    #[test]
    fn parses_optional_semicolons_and_multiline() {
        ok("fun main() { let a = 1; let b = 2; print(a + b) }");
        // trailing-operator line continuation
        ok("fun f(x: int) -> int {\n    return x +\n        1\n}");
        // leading `.` / `|>` continuation for fluent chains
        ok("fun g(xs: [int]) -> int {\n    return xs\n        |> len\n}");
    }

    #[test]
    fn parses_concurrency() {
        ok(r#"
actor Counter {
    count: int
    async fun incr(var self) { self.count = self.count + 1 }
}

fun main() {
    let ch = make_chan()
    spawn { ch.send(1) }
    let v = await ch.recv()
    print(v)
}
"#);
    }
}
