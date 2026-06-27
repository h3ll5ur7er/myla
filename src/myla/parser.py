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
        elif tok.kind is T.ENUM:
            decl = self._enum_decl()
        elif tok.kind is T.TYPEALIAS:
            decl = self._typealias_decl()
        else:
            raise ParseError(
                f"expected a declaration (struct/fun/enum/typealias), found '{tok.lexeme}'",
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

    def _generics(self) -> list[str]:
        """Parse an optional `<T, U, ...>` type-parameter list after a name."""
        if not self._check(T.LT):
            return []
        self._advance()  # <
        params: list[str] = []
        while True:
            tok = self._expect(T.IDENT, "type parameter name")
            params.append(tok.value)
            if not self._match(T.COMMA):
                break
        self._expect(T.GT, "'>' to close type parameters")
        if not params:
            raise ParseError("empty type-parameter list", tok.line, tok.column)
        return params

    def _struct_decl(self) -> ast.StructDecl:
        kw = self._advance()  # struct
        name = self._expect(T.IDENT, "struct name")
        type_params = self._generics()
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
        return ast.StructDecl(name.value, fields, type_params=type_params).at(kw.line, kw.column)

    def _enum_decl(self) -> ast.EnumDecl:
        kw = self._advance()  # enum
        name = self._expect(T.IDENT, "enum name")
        type_params = self._generics()
        self._expect(T.LBRACE, "'{'")
        self._skip_newlines()
        variants: list[ast.Variant] = []
        while not self._check(T.RBRACE) and not self._at_end():
            vname = self._expect(T.IDENT, "variant name")
            payload: list = []
            if self._match(T.LPAREN):
                payload.append(self._type())
                while self._match(T.COMMA):
                    if self._check(T.RPAREN):
                        break
                    payload.append(self._type())
                self._expect(T.RPAREN, "')'")
            variants.append(ast.Variant(vname.value, payload).at(vname.line, vname.column))
            # variants are separated by a comma and/or newline(s)
            if self._match(T.COMMA):
                self._skip_newlines()
            else:
                self._skip_newlines()
        self._expect(T.RBRACE, "'}'")
        return ast.EnumDecl(name.value, variants, type_params=type_params).at(kw.line, kw.column)

    def _fun_decl(self) -> ast.FunDecl:
        kw = self._advance()  # fun
        name = self._expect(T.IDENT, "function name")
        type_params = self._generics()
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
        return ast.FunDecl(name.value, params, ret_type, body,
                           type_params=type_params).at(kw.line, kw.column)

    def _typealias_decl(self) -> ast.TypeAliasDecl:
        kw = self._advance()  # typealias
        name = self._expect(T.IDENT, "alias name")
        self._expect(T.ASSIGN, "'='")
        target = self._type()
        return ast.TypeAliasDecl(name.value, target).at(kw.line, kw.column)

    def _type(self):
        tok = self._peek()
        if tok.kind is T.LPAREN:
            return self._tuple_type()
        if tok.kind in _PRIM_TYPE_KINDS:
            self._advance()
            return ast.TypeRef(tok.lexeme).at(tok.line, tok.column)
        if tok.kind is T.IDENT:
            self._advance()
            args = self._type_args()
            return ast.TypeRef(tok.value, args).at(tok.line, tok.column)
        raise ParseError(f"expected a type, found '{tok.lexeme}'", tok.line, tok.column)

    def _type_args(self) -> list:
        """Parse an optional `<T, U, ...>` type-argument list in a type position.

        `<` is unambiguous here (types have no comparison operators). Nested
        closers like `Option<Result<int, str>>` end in `>>`, which the lexer
        produces as two `>` tokens, so each level simply consumes its own `>`.
        """
        if not self._check(T.LT):
            return []
        self._advance()  # <
        args = [self._type()]
        while self._match(T.COMMA):
            args.append(self._type())
        self._expect(T.GT, "'>' to close type arguments")
        return args

    def _tuple_type(self) -> ast.TupleTypeRef:
        lp = self._advance()  # (
        elems = [self._type()]
        # A tuple type requires at least one comma; `(T,)` is the 1-tuple.
        if not self._match(T.COMMA):
            tok = self._peek()
            raise ParseError(
                "expected ',' in tuple type (use '(T,)' for a 1-tuple)",
                tok.line, tok.column,
            )
        while not self._check(T.RPAREN):
            elems.append(self._type())
            if not self._match(T.COMMA):
                break
        self._expect(T.RPAREN, "')'")
        return ast.TupleTypeRef(elems).at(lp.line, lp.column)

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

    def _var_decl(self) -> ast.Stmt:
        kw = self._advance()  # let / var
        if self._check(T.LPAREN):
            binding = self._tuple_binding()
            declared_type = None
            if self._match(T.COLON):
                declared_type = self._type()
            self._expect(T.ASSIGN, "'=' in variable declaration")
            init = self._expression()
            return ast.DestructDecl(kw.lexeme, binding, declared_type, init).at(kw.line, kw.column)
        name = self._expect(T.IDENT, "variable name")
        declared_type = None
        if self._match(T.COLON):
            declared_type = self._type()
        self._expect(T.ASSIGN, "'=' in variable declaration")
        init = self._expression()
        return ast.VarDecl(kw.lexeme, name.value, declared_type, init).at(kw.line, kw.column)

    def _tuple_binding(self) -> ast.BindTuple:
        lp = self._advance()  # (
        elems = [self._binding_elem()]
        # Like tuple literals, destructuring requires a comma; `(x,)` is a 1-tuple.
        if not self._match(T.COMMA):
            tok = self._peek()
            raise ParseError(
                "expected ',' in destructuring binding (use '(x,)' for a 1-tuple)",
                tok.line, tok.column,
            )
        while not self._check(T.RPAREN):
            elems.append(self._binding_elem())
            if not self._match(T.COMMA):
                break
        self._expect(T.RPAREN, "')'")
        return ast.BindTuple(elems).at(lp.line, lp.column)

    def _binding_elem(self) -> ast.BindElem:
        tok = self._peek()
        if tok.kind is T.LPAREN:
            return self._tuple_binding()
        if tok.kind is T.IDENT:
            self._advance()
            if tok.value == "_":
                return ast.BindWildcard().at(tok.line, tok.column)
            return ast.BindName(tok.value).at(tok.line, tok.column)
        raise ParseError(
            f"expected a binding name, '_', or '(', found '{tok.lexeme}'",
            tok.line, tok.column,
        )

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
            # `return a, b` is sugar for returning a tuple `(a, b)`.
            if self._check(T.COMMA):
                elems = [value]
                while self._match(T.COMMA):
                    elems.append(self._expression())
                value = ast.TupleLit(elems).at(value.line, value.column)
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
                if self._check(T.INT):
                    idx_tok = self._advance()
                    if idx_tok.suffix is not None:
                        raise ParseError(
                            "tuple index may not have a type suffix",
                            idx_tok.line, idx_tok.column,
                        )
                    expr = ast.TupleIndex(expr, idx_tok.value).at(dot.line, dot.column)
                else:
                    name = self._expect(T.IDENT, "field name or tuple index after '.'")
                    expr = ast.FieldAccess(expr, name.value).at(dot.line, dot.column)
            elif self._check(T.QUESTION):
                q = self._advance()
                expr = ast.Try(expr).at(q.line, q.column)
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
        if tok.kind is T.MATCH:
            return self._match_expr()
        if tok.kind is T.LPAREN:
            return self._paren_or_tuple(tok)
        raise ParseError(f"expected an expression, found '{tok.lexeme}'", tok.line, tok.column)

    # -- match expression & patterns -----------------------------------------

    def _match_expr(self) -> ast.Match:
        kw = self._advance()  # match
        # The scrutinee is parsed with struct-literal gating so its trailing `{`
        # reads as the start of the match body, not a struct literal.
        scrutinee = self._expression(allow_struct_lit=False)
        self._expect(T.LBRACE, "'{' to begin match arms")
        self._skip_newlines()
        arms: list[ast.MatchArm] = []
        while not self._check(T.RBRACE) and not self._at_end():
            arm = self._match_arm()
            arms.append(arm)
            if self._match(T.COMMA):
                self._skip_newlines()
            elif self._check(T.NEWLINE):
                self._skip_newlines()
            elif isinstance(arm.body, ast.Block):
                # a `{ ... }` arm body may be followed directly by the next arm
                continue
            else:
                break
        self._expect(T.RBRACE, "'}' to end match")
        if not arms:
            raise ParseError("match expression needs at least one arm", kw.line, kw.column)
        return ast.Match(scrutinee, arms).at(kw.line, kw.column)

    def _match_arm(self) -> ast.MatchArm:
        pattern = self._pattern()
        guard = None
        if self._match(T.IF):
            guard = self._expression(allow_struct_lit=False)
        arrow = self._expect(T.FATARROW, "'=>' after match pattern")
        if self._check(T.LBRACE):
            body: ast.Expr | ast.Block = self._block()
        else:
            body = self._expression()
        return ast.MatchArm(pattern, guard, body).at(arrow.line, arrow.column)

    def _pattern(self) -> ast.Pattern:
        first = self._base_pattern()
        if not self._check(T.PIPE):
            return first
        alts = [first]
        start_line, start_col = first.line, first.column
        while self._match(T.PIPE):
            alts.append(self._base_pattern())
        return ast.PatOr(alts).at(start_line, start_col)

    def _base_pattern(self) -> ast.Pattern:
        tok = self._peek()
        # literals (incl. negative integer literals)
        if tok.kind in (T.INT, T.STRING, T.TRUE, T.FALSE):
            lit = self._primary()
            return ast.PatLiteral(lit).at(tok.line, tok.column)
        if tok.kind is T.MINUS:
            self._advance()
            int_tok = self._expect(T.INT, "integer literal after '-' in pattern")
            lit = ast.Unary("-", ast.IntLit(int_tok.value, int_tok.suffix)
                            .at(int_tok.line, int_tok.column)).at(tok.line, tok.column)
            return ast.PatLiteral(lit).at(tok.line, tok.column)
        # bare `.Variant` enum pattern
        if tok.kind is T.DOT:
            self._advance()
            vtok = self._expect(T.IDENT, "variant name after '.'")
            return self._enum_pattern_tail(None, vtok)
        if tok.kind is T.LPAREN:
            return self._tuple_pattern()
        if tok.kind is T.IDENT:
            return self._ident_pattern(tok)
        raise ParseError(f"expected a pattern, found '{tok.lexeme}'", tok.line, tok.column)

    def _ident_pattern(self, first: Token) -> ast.Pattern:
        self._advance()  # the identifier
        if first.value == "_":
            return ast.PatWildcard().at(first.line, first.column)
        # `Type { ... }` struct pattern
        if self._check(T.LBRACE):
            return self._struct_pattern(first)
        # `Enum.Variant` qualified enum pattern
        if self._check(T.DOT):
            self._advance()
            vtok = self._expect(T.IDENT, "variant name after '.'")
            return self._enum_pattern_tail(first.value, vtok)
        # `Variant(...)` — looks like a (possibly bare) enum variant with payload
        if self._check(T.LPAREN):
            return self._enum_pattern_tail(None, first)
        # otherwise a plain binding (could resolve to a no-payload variant in the
        # checker, which knows the scrutinee's type)
        return ast.PatBinding(first.value).at(first.line, first.column)

    def _enum_pattern_tail(self, enum_name, variant_tok: Token) -> ast.PatEnum:
        elems: list[ast.Pattern] = []
        has_payload = False
        if self._match(T.LPAREN):
            has_payload = True
            if not self._check(T.RPAREN):
                elems.append(self._pattern())
                while self._match(T.COMMA):
                    if self._check(T.RPAREN):
                        break
                    elems.append(self._pattern())
            self._expect(T.RPAREN, "')'")
        return ast.PatEnum(enum_name, variant_tok.value, elems, has_payload).at(
            variant_tok.line, variant_tok.column
        )

    def _tuple_pattern(self) -> ast.PatTuple:
        lp = self._advance()  # (
        elems = [self._pattern()]
        if not self._match(T.COMMA):
            tok = self._peek()
            raise ParseError(
                "expected ',' in tuple pattern (use '(p,)' for a 1-tuple)",
                tok.line, tok.column,
            )
        while not self._check(T.RPAREN):
            elems.append(self._pattern())
            if not self._match(T.COMMA):
                break
        self._expect(T.RPAREN, "')'")
        return ast.PatTuple(elems).at(lp.line, lp.column)

    def _struct_pattern(self, name_tok: Token) -> ast.PatStruct:
        self._expect(T.LBRACE, "'{'")
        self._skip_newlines()
        fields: list[ast.FieldPat] = []
        while not self._check(T.RBRACE) and not self._at_end():
            fname = self._expect(T.IDENT, "field name in struct pattern")
            if self._match(T.COLON):
                pat = self._pattern()
            else:  # `{ x }` shorthand binds `x`
                pat = ast.PatBinding(fname.value).at(fname.line, fname.column)
            fields.append(ast.FieldPat(fname.value, pat).at(fname.line, fname.column))
            if self._match(T.COMMA):
                self._skip_newlines()
            else:
                self._skip_newlines()
                break
        self._expect(T.RBRACE, "'}'")
        return ast.PatStruct(name_tok.value, fields).at(name_tok.line, name_tok.column)

    def _paren_or_tuple(self, lp: Token) -> ast.Expr:
        self._advance()  # (
        # Parentheses reset the struct-literal restriction inside them.
        first = self._expression(allow_struct_lit=True)
        if not self._check(T.COMMA):
            self._expect(T.RPAREN, "')'")
            return first  # plain grouping
        # A comma makes this a tuple literal. `(e,)` is the 1-tuple.
        elems = [first]
        self._advance()  # consume the first comma
        while not self._check(T.RPAREN):
            elems.append(self._expression(allow_struct_lit=True))
            if not self._match(T.COMMA):
                break
        self._expect(T.RPAREN, "')'")
        return ast.TupleLit(elems).at(lp.line, lp.column)

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
