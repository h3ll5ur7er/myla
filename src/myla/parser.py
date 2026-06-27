"""The Myla parser: a list of Tokens -> an AST (a `Program`).

Recursive descent with a layered expression grammar encoding precedence and
associativity, mirroring docs/grammar.md §2. Panic-mode error handling: the
first syntax error raises `ParseError` (docs/architecture.md §3.2).

Newlines (NEWLINE tokens) separate statements and top-level declarations. A few
notes on the tricky bits:

- Struct literals (`Name { ... }`) are only parsed where an expression is
  unambiguously expected. Inside control-flow headers (`if`/`while` conditions,
  `for` ranges) struct-literal parsing is disabled so the `{` reads as the start
  of the body. Wrap in parentheses if you really mean a struct literal there.
- `else` may appear on the same line as the closing `}` or on a later line; the
  parser looks past newlines for it and backtracks if absent.
"""
from __future__ import annotations

from . import ast
from .errors import ParseError
from .tokens import Token, TokenKind as T

# Token kinds that name a primitive type in a type position.
_PRIM_TYPE_KINDS = {
    T.BOOL, T.STR,
    T.INT8, T.INT16, T.INT32, T.INT64,
    T.UINT8, T.UINT16, T.UINT32, T.UINT64,
}


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0
        self._allow_struct_lit = True

    # -- cursor helpers ------------------------------------------------------

    def _peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[idx]

    def _at_end(self) -> bool:
        return self._peek().kind is T.EOF

    def _check(self, kind: T) -> bool:
        return self._peek().kind is kind

    def _advance(self) -> Token:
        tok = self._peek()
        if tok.kind is not T.EOF:
            self.pos += 1
        return tok

    def _match(self, *kinds: T) -> Token | None:
        if self._peek().kind in kinds:
            return self._advance()
        return None

    def _expect(self, kind: T, what: str) -> Token:
        tok = self._peek()
        if tok.kind is not kind:
            raise ParseError(
                f"expected {what}, found '{tok.lexeme}'", tok.line, tok.column
            )
        return self._advance()

    def _skip_newlines(self) -> None:
        while self._check(T.NEWLINE):
            self._advance()

    # -- entry point ---------------------------------------------------------

    def parse_program(self) -> ast.Program:
        decls: list[ast.Decl] = []
        self._skip_newlines()
        while not self._at_end():
            decls.append(self._declaration())
            self._terminate("declaration")
        return ast.Program(decls)

    def _terminate(self, what: str) -> None:
        """Require a NEWLINE / RBRACE / EOF after a statement or declaration."""
        if self._check(T.NEWLINE):
            self._skip_newlines()
        elif self._check(T.RBRACE) or self._at_end():
            return
        else:
            tok = self._peek()
            raise ParseError(
                f"expected end of {what} (newline), found '{tok.lexeme}'",
                tok.line, tok.column,
            )

    # -- declarations --------------------------------------------------------

    def _declaration(self) -> ast.Decl:
        attrs = self._attributes()
        tok = self._peek()
        if tok.kind is T.STRUCT:
            decl: ast.Decl = self._struct_decl()
        elif tok.kind is T.FUN:
            decl = self._fun_decl()
        elif tok.kind is T.TYPEALIAS:
            decl = self._typealias_decl()
        else:
            raise ParseError(
                f"expected a declaration (struct/fun/typealias), found '{tok.lexeme}'",
                tok.line, tok.column,
            )
        decl.attributes = attrs
        return decl

    def _attributes(self) -> list[ast.Attribute]:
        attrs: list[ast.Attribute] = []
        while self._check(T.HASH):
            hash_tok = self._advance()
            name_tok = self._expect(T.IDENT, "attribute name after '#'")
            args: list[ast.Expr] = []
            outputs: list[ast.Expr] | None = None
            if self._match(T.LPAREN):
                args = self._expr_list(T.RPAREN)
                self._expect(T.RPAREN, "')'")
            if self._match(T.LBRACKET):
                outputs = self._expr_list(T.RBRACKET)
                self._expect(T.RBRACKET, "']'")
            attrs.append(
                ast.Attribute(name_tok.value, args, outputs).at(hash_tok.line, hash_tok.column)
            )
            self._skip_newlines()
        return attrs

    def _struct_decl(self) -> ast.StructDecl:
        kw = self._advance()  # struct
        name = self._expect(T.IDENT, "struct name")
        self._expect(T.LBRACE, "'{'")
        self._skip_newlines()
        fields: list[ast.Field] = []
        while not self._check(T.RBRACE) and not self._at_end():
            fname = self._expect(T.IDENT, "field name")
            self._expect(T.COLON, "':'")
            ftype = self._type()
            fields.append(ast.Field(fname.value, ftype).at(fname.line, fname.column))
            if not self._match(T.COMMA):
                self._skip_newlines()
                break
            self._skip_newlines()
        self._expect(T.RBRACE, "'}'")
        return ast.StructDecl(name.value, fields).at(kw.line, kw.column)

    def _fun_decl(self) -> ast.FunDecl:
        kw = self._advance()  # fun
        name = self._expect(T.IDENT, "function name")
        self._expect(T.LPAREN, "'('")
        params: list[ast.Param] = []
        if not self._check(T.RPAREN):
            while True:
                pname = self._expect(T.IDENT, "parameter name")
                self._expect(T.COLON, "':'")
                ptype = self._type()
                params.append(ast.Param(pname.value, ptype).at(pname.line, pname.column))
                if not self._match(T.COMMA):
                    break
        self._expect(T.RPAREN, "')'")
        ret_type = None
        if self._match(T.ARROW):
            ret_type = self._type()
        body = self._block()
        return ast.FunDecl(name.value, params, ret_type, body).at(kw.line, kw.column)

    def _typealias_decl(self) -> ast.TypeAliasDecl:
        kw = self._advance()  # typealias
        name = self._expect(T.IDENT, "alias name")
        self._expect(T.ASSIGN, "'='")
        target = self._type()
        return ast.TypeAliasDecl(name.value, target).at(kw.line, kw.column)

    def _type(self) -> ast.TypeRef:
        tok = self._peek()
        if tok.kind in _PRIM_TYPE_KINDS:
            self._advance()
            return ast.TypeRef(tok.lexeme).at(tok.line, tok.column)
        if tok.kind is T.IDENT:
            self._advance()
            return ast.TypeRef(tok.value).at(tok.line, tok.column)
        raise ParseError(f"expected a type, found '{tok.lexeme}'", tok.line, tok.column)

    # -- statements ----------------------------------------------------------

    def _block(self) -> ast.Block:
        lbrace = self._expect(T.LBRACE, "'{'")
        stmts: list[ast.Stmt] = []
        self._skip_newlines()
        while not self._check(T.RBRACE) and not self._at_end():
            stmts.append(self._statement())
            if self._check(T.NEWLINE):
                self._skip_newlines()
            elif self._check(T.RBRACE):
                break
            else:
                tok = self._peek()
                raise ParseError(
                    f"expected newline or '}}', found '{tok.lexeme}'", tok.line, tok.column
                )
        self._expect(T.RBRACE, "'}'")
        return ast.Block(stmts).at(lbrace.line, lbrace.column)

    def _statement(self) -> ast.Stmt:
        tok = self._peek()
        if tok.kind in (T.LET, T.VAR):
            return self._var_decl()
        if tok.kind is T.IF:
            return self._if_stmt()
        if tok.kind is T.WHILE:
            return self._while_stmt()
        if tok.kind is T.FOR:
            return self._for_stmt()
        if tok.kind is T.RETURN:
            return self._return_stmt()
        return self._assign_or_expr()

    def _var_decl(self) -> ast.VarDecl:
        kw = self._advance()  # let / var
        name = self._expect(T.IDENT, "variable name")
        declared_type = None
        if self._match(T.COLON):
            declared_type = self._type()
        self._expect(T.ASSIGN, "'=' in variable declaration")
        init = self._expression()
        return ast.VarDecl(kw.lexeme, name.value, declared_type, init).at(kw.line, kw.column)

    def _if_stmt(self) -> ast.If:
        kw = self._advance()  # if
        cond = self._expression(allow_struct_lit=False)
        then = self._block()
        otherwise = None
        # Look past newlines for an `else`; backtrack if it's not there.
        saved = self.pos
        self._skip_newlines()
        if self._match(T.ELSE):
            if self._check(T.IF):
                otherwise = self._if_stmt()
            else:
                otherwise = self._block()
        else:
            self.pos = saved
        return ast.If(cond, then, otherwise).at(kw.line, kw.column)

    def _while_stmt(self) -> ast.While:
        kw = self._advance()  # while
        cond = self._expression(allow_struct_lit=False)
        body = self._block()
        return ast.While(cond, body).at(kw.line, kw.column)

    def _for_stmt(self) -> ast.For:
        kw = self._advance()  # for
        var = self._expect(T.IDENT, "loop variable name")
        self._expect(T.IN, "'in'")
        start = self._expression(allow_struct_lit=False)
        self._expect(T.DOTDOT, "'..' in for range")
        end = self._expression(allow_struct_lit=False)
        body = self._block()
        return ast.For(var.value, start, end, body).at(kw.line, kw.column)

    def _return_stmt(self) -> ast.Return:
        kw = self._advance()  # return
        value = None
        if not (self._check(T.NEWLINE) or self._check(T.RBRACE) or self._at_end()):
            value = self._expression()
        return ast.Return(value).at(kw.line, kw.column)

    def _assign_or_expr(self) -> ast.Stmt:
        expr = self._expression()
        if self._check(T.ASSIGN):
            eq = self._advance()
            if not _is_lvalue(expr):
                raise ParseError(
                    "invalid assignment target", expr.line, expr.column
                )
            value = self._expression()
            return ast.Assign(expr, value).at(eq.line, eq.column)
        return ast.ExprStmt(expr).at(expr.line, expr.column)

    # -- expressions (precedence climbing) -----------------------------------

    def _expression(self, allow_struct_lit: bool = True) -> ast.Expr:
        prev = self._allow_struct_lit
        self._allow_struct_lit = allow_struct_lit
        try:
            return self._logic_or()
        finally:
            self._allow_struct_lit = prev

    def _binary_left(self, sub, kinds) -> ast.Expr:
        expr = sub()
        while self._peek().kind in kinds:
            op = self._advance()
            right = sub()
            expr = ast.Binary(op.lexeme, expr, right).at(op.line, op.column)
        return expr

    def _logic_or(self) -> ast.Expr:
        return self._binary_left(self._logic_and, {T.OR})

    def _logic_and(self) -> ast.Expr:
        return self._binary_left(self._equality, {T.AND})

    def _equality(self) -> ast.Expr:
        return self._binary_left(self._comparison, {T.EQ, T.NE})

    def _comparison(self) -> ast.Expr:
        return self._binary_left(self._term, {T.LT, T.LE, T.GT, T.GE})

    def _term(self) -> ast.Expr:
        return self._binary_left(self._factor, {T.PLUS, T.MINUS})

    def _factor(self) -> ast.Expr:
        return self._binary_left(self._unary, {T.STAR, T.SLASH, T.PERCENT})

    def _unary(self) -> ast.Expr:
        if self._peek().kind in (T.MINUS, T.BANG):
            op = self._advance()
            operand = self._unary()
            return ast.Unary(op.lexeme, operand).at(op.line, op.column)
        return self._postfix()

    def _postfix(self) -> ast.Expr:
        expr = self._primary()
        while True:
            if self._check(T.LPAREN):
                lp = self._advance()
                args = self._expr_list(T.RPAREN)
                self._expect(T.RPAREN, "')'")
                expr = ast.Call(expr, args).at(lp.line, lp.column)
            elif self._check(T.DOT):
                dot = self._advance()
                name = self._expect(T.IDENT, "field name after '.'")
                expr = ast.FieldAccess(expr, name.value).at(dot.line, dot.column)
            else:
                break
        return expr

    def _primary(self) -> ast.Expr:
        tok = self._peek()
        if tok.kind is T.INT:
            self._advance()
            return ast.IntLit(tok.value, tok.suffix).at(tok.line, tok.column)
        if tok.kind is T.STRING:
            self._advance()
            return ast.StrLit(tok.value).at(tok.line, tok.column)
        if tok.kind in (T.TRUE, T.FALSE):
            self._advance()
            return ast.BoolLit(tok.value).at(tok.line, tok.column)
        if tok.kind is T.IDENT:
            self._advance()
            if self._allow_struct_lit and self._check(T.LBRACE):
                return self._struct_lit(tok)
            return ast.Name(tok.value).at(tok.line, tok.column)
        if tok.kind is T.LPAREN:
            self._advance()
            # Parentheses reset the struct-literal restriction inside them.
            inner = self._expression(allow_struct_lit=True)
            self._expect(T.RPAREN, "')'")
            return inner
        raise ParseError(f"expected an expression, found '{tok.lexeme}'", tok.line, tok.column)

    def _struct_lit(self, name_tok: Token) -> ast.StructLit:
        self._expect(T.LBRACE, "'{'")
        self._skip_newlines()
        fields: list[ast.FieldInit] = []
        while not self._check(T.RBRACE) and not self._at_end():
            fname = self._expect(T.IDENT, "field name")
            self._expect(T.COLON, "':'")
            value = self._expression(allow_struct_lit=True)
            fields.append(ast.FieldInit(fname.value, value).at(fname.line, fname.column))
            if not self._match(T.COMMA):
                self._skip_newlines()
                break
            self._skip_newlines()
        self._expect(T.RBRACE, "'}'")
        return ast.StructLit(name_tok.value, fields).at(name_tok.line, name_tok.column)

    def _expr_list(self, closing: T) -> list[ast.Expr]:
        args: list[ast.Expr] = []
        self._skip_newlines()
        if self._check(closing):
            return args
        while True:
            args.append(self._expression(allow_struct_lit=True))
            self._skip_newlines()
            if self._match(T.COMMA):
                self._skip_newlines()
                continue
            break
        return args


def _is_lvalue(expr: ast.Expr) -> bool:
    if isinstance(expr, ast.Name):
        return True
    if isinstance(expr, ast.FieldAccess):
        return _is_lvalue(expr.target)
    return False


def parse(tokens: list[Token]) -> ast.Program:
    """Convenience wrapper: parse a token list into a `Program`."""
    return Parser(tokens).parse_program()
