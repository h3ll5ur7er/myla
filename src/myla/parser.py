"""The Myla parser: a list of Tokens -> an AST (a `Program`).

Recursive descent with a layered expression grammar encoding precedence and
associativity, mirroring docs/Language/Grammar.md. A syntax error raises
`ParseError`; a block, an impl or trait body and the program catch it, record
it and resume at the next statement, member or declaration (`_sync`), so one
run reports up to MAX_ERRORS of them (MYLA-65, D80;
docs/Architecture/Lexer-and-parser.md). `parse` raises the first, with the
others in its `more`.

Newlines (NEWLINE tokens) separate statements and top-level declarations; a
`;` may stand for such a newline (D61), and a run of both is one separator. A
few notes on the tricky bits:

- Struct literals (`Name { ... }`) are only parsed where an expression is
  unambiguously expected. Inside control-flow headers (`if`/`while` conditions,
  `for` ranges) struct-literal parsing is disabled so the `{` reads as the start
  of the body. Wrap in parentheses if you really mean a struct literal there.
- `else` may appear on the same line as the closing `}` or on a later line; the
  parser looks past newlines for it and backtracks if absent.
"""
from __future__ import annotations

from . import ast
from .errors import MAX_ERRORS, ParseError
from .tokens import Token, TokenKind as T

# The tokens that begin a declaration, and those that begin a statement other
# than an expression: where the parser resumes after an error (`_sync`).
_DECL_START = {T.FUN, T.STRUCT, T.ENUM, T.IMPL, T.TRAIT, T.TYPEALIAS, T.CONST,
               T.IMPORT, T.FROM, T.PUB, T.HASH}
_STMT_START = {T.LET, T.VAR, T.IF, T.WHILE, T.FOR, T.RETURN, T.BREAK, T.CONTINUE}

# What `_sync` skips to: the next statement of a block, the next member of an
# impl or trait body, the next top-level declaration.
_STMT, _MEMBER, _DECL = "statement", "member", "declaration"


class _Unwind(Exception):
    """Leaves the declaration being parsed without a new error: after an error,
    a block reached a line that starts a declaration, so its closing brace is
    missing. The impl or trait body (at a method) or the program catches it."""


class _Stop(Exception):
    """MAX_ERRORS errors were recorded: the parse ends."""


# Token kinds that name a primitive type in a type position.
_PRIM_TYPE_KINDS = {
    T.BOOL, T.STR,
    T.INT8, T.INT16, T.INT32, T.INT64,
    T.UINT8, T.UINT16, T.UINT32, T.UINT64,
}


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = list(tokens)       # a copy: `_type_args` may split a `>=`
        self.pos = 0
        self._allow_struct_lit = True
        self.errors: list[ParseError] = []

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
                f"expected {what}, found '{tok.lexeme}'", at=tok
            )
        return self._advance()

    def _start(self) -> tuple[int, int]:
        """Where the next token starts: the start of a node parsed from here."""
        tok = self._peek()
        return tok.line, tok.column

    def _end(self) -> tuple[int, int]:
        """Where the last consumed token ends: the end of a node built now."""
        tok = self.tokens[self.pos - 1] if self.pos > 0 else self.tokens[0]
        return tok.end_line, tok.end_column

    def _skip_newlines(self) -> None:
        while self._check(T.NEWLINE):
            self._advance()

    def _skip_separators(self) -> None:
        """Skip the newlines and `;` between statements or declarations."""
        while self._at_separator():
            self._advance()

    def _at_separator(self) -> bool:
        return self._check(T.NEWLINE) or self._check(T.SEMI)

    # -- entry point ---------------------------------------------------------

    def parse_program(self) -> ast.Program:
        decls: list[ast.Decl] = []
        self._skip_separators()
        try:
            while not self._at_end():
                start = self.pos
                try:
                    decls.append(self._declaration())
                    self._terminate("declaration")
                except ParseError as err:
                    self._recover(err, start, _DECL)
                except _Unwind:
                    pass
                self._skip_separators()
        except _Stop:
            pass
        if self.errors:
            first = self.errors[0]
            first.more = self.errors[1:]
            raise first
        return ast.Program(decls)

    # -- error recovery (MYLA-65, D80) ----------------------------------------

    def _recover(self, err: ParseError, start: int, mode: str) -> None:
        """Record `err`, raised while parsing from token `start`, and skip to
        where parsing can go on (`_sync`). An error that is not after the last
        one recorded is dropped: it follows from that one. `_recover` moves
        past `start` unless a block or body ends there (at its `}` or,
        unwinding, at a declaration), so a loop calling it makes progress."""
        last = self.errors[-1] if self.errors else None
        if last is None or (err.line, err.column) > (last.line, last.column):
            self.errors.append(err)
            if len(self.errors) >= MAX_ERRORS:
                raise _Stop()
        self._sync(start, mode)
        if self.pos == start and (mode == _DECL or not (
                self._check(T.RBRACE) or self._resuming_at_declaration())):
            self._advance()

    def _at_line_start(self) -> bool:
        return self.pos == 0 or self.tokens[self.pos - 1].kind in (T.NEWLINE, T.SEMI)

    def _sync(self, start: int, mode: str) -> None:
        """Skip from the error to where a `mode` can begin. The brackets
        opened since `start` (the statement, member or declaration's first
        token) and not closed are tracked, so a construct spanning lines is
        skipped whole. It stops at the end of the input; at a line starting a
        declaration (in a member or a declaration only when no brace is open,
        or when it is at column 1); at a `}` closing the enclosing block or
        body; and, for a statement, at a newline or `;` with no brace open,
        when no bracket is open either or the next line starts a statement,
        a declaration or with `}`."""
        opens: list[T] = []
        for i in range(start, self.pos):
            _nest(opens, self.tokens[i].kind)
        while not self._at_end():
            tok = self._peek()
            k = tok.kind
            brace = T.LBRACE in opens
            if k in _DECL_START and self._at_line_start():
                if mode == _STMT or not brace or tok.column == 1:
                    return
            if k is T.RBRACE and not brace and mode != _DECL:
                return
            if mode == _STMT and k in (T.NEWLINE, T.SEMI) and not brace:
                nxt = self._peek(1).kind
                if not opens or nxt in _STMT_START or nxt in _DECL_START or nxt is T.RBRACE:
                    return
            _nest(opens, k)
            self._advance()

    def _resuming_at_declaration(self) -> bool:
        """Whether the last error is at the next token, which starts a
        declaration on its line: then the block or body being parsed is
        missing its `}`, and the parse resumes at the declaration."""
        tok = self._peek()
        if not self.errors or tok.kind not in _DECL_START or not self._at_line_start():
            return False
        last = self.errors[-1]
        return (last.line, last.column) == (tok.line, tok.column)

    def _terminate(self, what: str) -> None:
        """Require a separator / RBRACE / EOF after a statement or declaration."""
        if self._at_separator():
            self._skip_separators()
        elif self._check(T.RBRACE) or self._at_end():
            return
        else:
            tok = self._peek()
            raise ParseError(
                f"expected end of {what} (newline or ';'), found '{tok.lexeme}'",
                at=tok,
            )

    # -- declarations --------------------------------------------------------

    def _declaration(self) -> ast.Decl:
        attrs = self._attributes()
        pub_tok = self._advance() if self._check(T.PUB) else None
        is_pub = pub_tok is not None
        tok = self._peek()
        if tok.kind is T.STRUCT:
            decl: ast.Decl = self._struct_decl()
        elif tok.kind is T.FUN:
            decl = self._fun_decl()
        elif tok.kind is T.ENUM:
            decl = self._enum_decl()
        elif tok.kind is T.IMPL:
            decl = self._impl_decl()
        elif tok.kind is T.TRAIT:
            decl = self._trait_decl()
        elif tok.kind is T.TYPEALIAS:
            decl = self._typealias_decl()
        elif tok.kind is T.CONST:
            decl = self._const_decl()
        elif tok.kind in (T.IMPORT, T.FROM):
            decl = self._import_decl(is_pub)
        else:
            raise ParseError(
                "expected a declaration (struct/fun/enum/typealias/const/trait/"
                f"impl/import), found '{tok.lexeme}'",
                at=tok,
            )
        if isinstance(decl, ast.ImplDecl):
            if attrs:
                raise ParseError(
                    "attributes are not allowed on an 'impl' block",
                    at=tok,
                )
            if is_pub:
                raise ParseError(
                    "'pub' is not allowed on an 'impl' block (visibility follows "
                    "the implemented type)",
                    at=pub_tok,
                )
        elif isinstance(decl, ast.ImportDecl):
            if attrs:
                raise ParseError(
                    "attributes are not allowed on an import statement",
                    at=tok,
                )
            # is_pub was already threaded into _import_decl.
        else:
            decl.attributes = attrs
            decl.is_pub = is_pub
        return decl

    def _import_decl(self, is_pub: bool) -> ast.ImportDecl:
        start = self._peek()
        if self._match(T.FROM):
            path = self._import_path()
            self._expect(T.IMPORT, "'import' after the path in a 'from' import")
            items: list[ast.ImportItem] = [self._import_item()]
            while self._match(T.COMMA):
                items.append(self._import_item())
            return ast.ImportDecl(path, items=items, is_pub=is_pub).at(
                start.line, start.column, self._end())
        self._expect(T.IMPORT, "'import' or 'from'")
        path = self._import_path()
        alias: str | None = None
        if self._match(T.AS):
            alias = self._expect(T.IDENT, "an alias name after 'as'").value
        if is_pub and alias is None:
            raise ParseError(
                "a 'pub import' must bind a simple name: add 'as <name>' "
                "(the full path cannot be re-exported directly)",
                at=start,
            )
        return ast.ImportDecl(path, alias=alias, is_pub=is_pub).at(
            start.line, start.column, self._end())

    def _import_path(self) -> ast.ImportPath:
        tok = self._peek()
        dots = 0
        while self._check(T.DOT) or self._check(T.DOTDOT):
            dots += 2 if self._peek().kind is T.DOTDOT else 1
            self._advance()
        segments = [self._expect(T.IDENT, "a module path segment").value]
        while self._match(T.DOT):
            segments.append(self._expect(T.IDENT, "a path segment after '.'").value)
        return ast.ImportPath(dots, segments).at(tok.line, tok.column, self._end())

    def _import_item(self) -> ast.ImportItem:
        tok = self._expect(T.IDENT, "an imported name")
        alias = None
        if self._match(T.AS):
            alias = self._expect(T.IDENT, "an alias name after 'as'").value
        return ast.ImportItem(tok.value, alias).at(tok.line, tok.column, self._end())

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
                ast.Attribute(name_tok.value, args, outputs).at(hash_tok.line, hash_tok.column, self._end())
            )
            self._skip_newlines()
        return attrs

    def _generics(self) -> tuple[list[str], dict[str, list[str]]]:
        """Parse an optional `<T, U: Bound, V: A + B>` type-parameter list. Each
        parameter may carry built-in-trait bounds after a `:` (v0.4.4, X9).
        Returns the ordered names and a {name: [trait, …]} bound map."""
        if not self._check(T.LT):
            return [], {}
        self._advance()  # <
        params: list[str] = []
        bounds: dict[str, list[str]] = {}
        while True:
            tok = self._expect(T.IDENT, "type parameter name")
            params.append(tok.value)
            if self._match(T.COLON):
                bs = [self._expect(T.IDENT, "trait name in type-parameter bound").value]
                while self._match(T.PLUS):
                    bs.append(self._expect(T.IDENT, "trait name after '+'").value)
                bounds[tok.value] = bs
            if not self._match(T.COMMA):
                break
        self._expect(T.GT, "'>' to close type parameters")
        if not params:
            raise ParseError("empty type-parameter list", at=tok)
        return params, bounds

    def _generics_no_bounds(self, where: str) -> list[str]:
        names, bounds = self._generics()
        if bounds:
            tok = self._peek()
            raise ParseError(
                f"type-parameter bounds are not supported on {where}", at=tok
            )
        return names

    def _struct_decl(self) -> ast.StructDecl:
        kw = self._advance()  # struct
        name = self._expect(T.IDENT, "struct name")
        type_params = self._generics_no_bounds("a struct")
        self._expect(T.LBRACE, "'{'")
        self._skip_newlines()
        fields: list[ast.Field] = []
        while not self._check(T.RBRACE) and not self._at_end():
            fname = self._expect(T.IDENT, "field name")
            self._expect(T.COLON, "':'")
            ftype = self._type()
            fields.append(ast.Field(fname.value, ftype).at(fname.line, fname.column, self._end()))
            if not self._match(T.COMMA):
                self._skip_newlines()
                break
            self._skip_newlines()
        self._expect(T.RBRACE, "'}'")
        return ast.StructDecl(name.value, fields, type_params=type_params).at(kw.line, kw.column, self._end())

    def _enum_decl(self) -> ast.EnumDecl:
        kw = self._advance()  # enum
        name = self._expect(T.IDENT, "enum name")
        type_params = self._generics_no_bounds("an enum")
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
            variants.append(ast.Variant(vname.value, payload).at(vname.line, vname.column, self._end()))
            # variants are separated by a comma and/or newline(s)
            if self._match(T.COMMA):
                self._skip_newlines()
            else:
                self._skip_newlines()
        self._expect(T.RBRACE, "'}'")
        return ast.EnumDecl(name.value, variants, type_params=type_params).at(kw.line, kw.column, self._end())

    def _fun_decl(self) -> ast.FunDecl:
        kw = self._advance()  # fun
        name = self._expect(T.IDENT, "function name")
        type_params, bounds = self._generics()
        self._expect(T.LPAREN, "'('")
        params: list[ast.Param] = []
        if not self._check(T.RPAREN):
            while True:
                pname = self._expect(T.IDENT, "parameter name")
                self._expect(T.COLON, "':'")
                ptype = self._type()
                params.append(ast.Param(pname.value, ptype).at(pname.line, pname.column, self._end()))
                if not self._match(T.COMMA):
                    break
        self._expect(T.RPAREN, "')'")
        ret_type = None
        if self._match(T.ARROW):
            ret_type = self._type()
        body = self._block()
        return ast.FunDecl(name.value, params, ret_type, body,
                           type_params=type_params,
                           type_param_bounds=bounds).at(kw.line, kw.column, self._end())

    def _impl_decl(self) -> ast.ImplDecl:
        kw = self._advance()  # impl
        type_params, bounds = self._generics()
        first = self._type()
        trait_name = None
        trait_args: list = []
        target = first
        # `impl Trait for T { … }` (v0.4.4) and the generic `impl Trait<Args> for
        # T { … }` (v0.5.5): the first type names the trait (plus its arguments).
        if self._match(T.FOR):
            if not isinstance(first, ast.TypeRef):
                raise ParseError(
                    "the trait in 'impl Trait for T' must be a (possibly generic) "
                    "trait name",
                    at=kw,
                )
            trait_name = first.name
            trait_args = first.args
            target = self._type()
        self._expect(T.LBRACE, "'{' to begin impl block")
        self._skip_separators()
        methods: list[ast.FunDecl] = []
        while not self._check(T.RBRACE) and not self._at_end():
            self._member(lambda: methods.append(self._method_decl()),
                         "a method ('fun ...') in impl block")
            # a method always ends in `}`, so the next method's `fun` (or the
            # impl's closing `}`) may follow on the same or a later line.
            self._skip_separators()
        self._expect(T.RBRACE, "'}' to close impl block")
        return ast.ImplDecl(
            target, methods, type_params=type_params,
            type_param_bounds=bounds, trait_name=trait_name,
            trait_args=trait_args,
        ).at(kw.line, kw.column, self._end())

    def _trait_decl(self) -> ast.TraitDecl:
        kw = self._advance()  # trait
        name = self._expect(T.IDENT, "trait name")
        type_params = self._generics_no_bounds("a trait")
        self._expect(T.LBRACE, "'{' to begin trait body")
        self._skip_separators()
        methods: list[ast.FunDecl] = []
        while not self._check(T.RBRACE) and not self._at_end():
            self._member(lambda: methods.append(self._method_sig()),
                         "a method signature ('fun ...') in trait body")
            self._skip_separators()
        self._expect(T.RBRACE, "'}' to close trait body")
        return ast.TraitDecl(
            name.value, methods, type_params=type_params
        ).at(kw.line, kw.column, self._end())

    def _member(self, parse_method, what: str) -> None:
        """One member of an impl or trait body: `parse_method` at a `fun`.
        After an error, the next `fun` or the body's `}`; a line starting
        another declaration (or at column 1) leaves the body (`_Unwind`)."""
        tok = self._peek()
        if self._resuming_at_declaration() and (tok.kind is not T.FUN or tok.column == 1):
            raise _Unwind()
        start = self.pos
        try:
            if not self._check(T.FUN):
                raise ParseError(f"expected {what}, found '{tok.lexeme}'", at=tok)
            parse_method()
        except ParseError as err:
            self._recover(err, start, _MEMBER)
        except _Unwind:
            if not (self._check(T.FUN) and self._peek().column > 1):
                raise

    def _method_header(self):
        """Parse a method header `fun name<…>(self|var self, params…) -> ret`,
        shared by `impl` methods and `trait` signatures. Returns the parts; the
        caller appends a body (or leaves it `None` for a signature)."""
        kw = self._advance()  # fun
        name = self._expect(T.IDENT, "method name")
        type_params, bounds = self._generics()
        self._expect(T.LPAREN, "'('")
        # The receiver is the first parameter: `self` or `var self`.
        receiver = None
        if self._match(T.VAR):
            self._expect(T.SELF, "'self' after 'var' in method receiver")
            receiver = "var self"
        elif self._match(T.SELF):
            receiver = "self"
        else:
            tok = self._peek()
            raise ParseError(
                "a method's first parameter must be 'self' or 'var self'",
                at=tok,
            )
        params: list[ast.Param] = []
        while self._match(T.COMMA):
            if self._check(T.RPAREN):  # trailing comma after self
                break
            pname = self._expect(T.IDENT, "parameter name")
            self._expect(T.COLON, "':'")
            ptype = self._type()
            params.append(ast.Param(pname.value, ptype).at(pname.line, pname.column, self._end()))
        self._expect(T.RPAREN, "')'")
        ret_type = None
        if self._match(T.ARROW):
            ret_type = self._type()
        return kw, name, type_params, bounds, receiver, params, ret_type

    def _method_decl(self) -> ast.FunDecl:
        kw, name, type_params, bounds, receiver, params, ret_type = self._method_header()
        body = self._block()
        return ast.FunDecl(name.value, params, ret_type, body,
                           type_params=type_params, type_param_bounds=bounds,
                           receiver=receiver).at(kw.line, kw.column, self._end())

    def _method_sig(self) -> ast.FunDecl:
        kw, name, type_params, bounds, receiver, params, ret_type = self._method_header()
        return ast.FunDecl(name.value, params, ret_type, None,
                           type_params=type_params, type_param_bounds=bounds,
                           receiver=receiver).at(kw.line, kw.column, self._end())

    def _typealias_decl(self) -> ast.TypeAliasDecl:
        kw = self._advance()  # typealias
        name = self._expect(T.IDENT, "alias name")
        self._expect(T.ASSIGN, "'='")
        target = self._type()
        return ast.TypeAliasDecl(name.value, target).at(kw.line, kw.column, self._end())

    def _const_decl(self) -> ast.ConstDecl:
        kw = self._advance()  # const
        name = self._expect(T.IDENT, "constant name")
        self._expect(T.COLON, "':' (a const requires an explicit type)")
        declared_type = self._type()
        self._expect(T.ASSIGN, "'=' in const declaration")
        value = self._expression()
        return ast.ConstDecl(name.value, declared_type, value).at(kw.line, kw.column, self._end())

    def _type(self):
        tok = self._peek()
        if tok.kind is T.LPAREN:
            return self._paren_type()
        if tok.kind is T.LBRACKET:
            self._advance()  # [
            first = self._type()
            if self._match(T.COLON):              # map type `[K: V]`
                value = self._type()
                self._expect(T.RBRACKET, "']' to close map type")
                return ast.MapTypeRef(first, value).at(tok.line, tok.column, self._end())
            self._expect(T.RBRACKET, "']' to close list type")
            return ast.ListTypeRef(first).at(tok.line, tok.column, self._end())
        if tok.kind in _PRIM_TYPE_KINDS:
            self._advance()
            return ast.TypeRef(tok.lexeme).at(tok.line, tok.column, self._end())
        if tok.kind is T.IDENT:
            self._advance()
            args = self._type_args()
            return ast.TypeRef(tok.value, args).at(tok.line, tok.column, self._end())
        raise ParseError(f"expected a type, found '{tok.lexeme}'", at=tok)

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
        if self._check(T.GE):
            # `Option<int>= x`: the `>=` token closes the list and leaves its
            # `=` behind (MYLA-15)
            ge = self._peek()
            self.tokens[self.pos] = Token(T.ASSIGN, "=", ge.line, ge.column + 1,
                                          end_line=ge.end_line, end_column=ge.end_column)
            return args
        self._expect(T.GT, "'>' to close type arguments")
        return args

    def _paren_type(self):
        """Parse a parenthesized type: either a tuple type `(T,)`/`(T, U)` or a
        function type `(T0, …) -> R` / `() -> R` (v0.4.2). Both start with `(`;
        the trailing `->` distinguishes a function type."""
        lp = self._advance()  # (
        params: list = []
        saw_comma = False
        if not self._check(T.RPAREN):
            params.append(self._type())
            while self._match(T.COMMA):
                saw_comma = True
                if self._check(T.RPAREN):
                    break
                params.append(self._type())
        self._expect(T.RPAREN, "')'")
        if self._match(T.ARROW):                       # function type
            ret = self._type()
            return ast.FnTypeRef(params, ret).at(lp.line, lp.column, self._end())
        # Otherwise a tuple type, which requires at least one comma; `()` alone
        # is only valid as a function type.
        if not params:
            raise ParseError(
                "'()' is only valid as a function type '() -> R'",
                at=lp,
            )
        if not saw_comma:
            tok = self._peek()
            raise ParseError(
                "expected ',' in tuple type (use '(T,)' for a 1-tuple)",
                at=tok,
            )
        return ast.TupleTypeRef(params).at(lp.line, lp.column, self._end())

    # -- statements ----------------------------------------------------------

    def _block(self) -> ast.Block:
        lbrace = self._expect(T.LBRACE, "'{'")
        stmts: list[ast.Stmt] = []
        self._skip_separators()
        while not self._check(T.RBRACE) and not self._at_end():
            if self._resuming_at_declaration():
                raise _Unwind()
            start = self.pos
            try:
                stmts.append(self._statement())
                if self._at_separator():
                    self._skip_separators()
                elif self._check(T.RBRACE):
                    break
                else:
                    tok = self._peek()
                    raise ParseError(
                        f"expected newline, ';' or '}}', found '{tok.lexeme}'", at=tok
                    )
            except ParseError as err:
                self._recover(err, start, _STMT)
                self._skip_separators()
        self._expect(T.RBRACE, "'}'")
        return ast.Block(stmts).at(lbrace.line, lbrace.column, self._end())

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
        if tok.kind is T.BREAK:
            self._advance()
            return ast.Break().at(tok.line, tok.column, self._end())
        if tok.kind is T.CONTINUE:
            self._advance()
            return ast.Continue().at(tok.line, tok.column, self._end())
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
            return ast.DestructDecl(kw.lexeme, binding, declared_type, init).at(kw.line, kw.column, self._end())
        name = self._expect(T.IDENT, "variable name")
        declared_type = None
        if self._match(T.COLON):
            declared_type = self._type()
        self._expect(T.ASSIGN, "'=' in variable declaration")
        init = self._expression()
        return ast.VarDecl(kw.lexeme, name.value, declared_type, init).at(kw.line, kw.column, self._end())

    def _tuple_binding(self) -> ast.BindTuple:
        lp = self._advance()  # (
        elems = [self._binding_elem()]
        # Like tuple literals, destructuring requires a comma; `(x,)` is a 1-tuple.
        if not self._match(T.COMMA):
            tok = self._peek()
            raise ParseError(
                "expected ',' in destructuring binding (use '(x,)' for a 1-tuple)",
                at=tok,
            )
        while not self._check(T.RPAREN):
            elems.append(self._binding_elem())
            if not self._match(T.COMMA):
                break
        self._expect(T.RPAREN, "')'")
        return ast.BindTuple(elems).at(lp.line, lp.column, self._end())

    def _binding_elem(self) -> ast.BindElem:
        tok = self._peek()
        if tok.kind is T.LPAREN:
            return self._tuple_binding()
        if tok.kind is T.IDENT:
            self._advance()
            if tok.value == "_":
                return ast.BindWildcard().at(tok.line, tok.column, self._end())
            return ast.BindName(tok.value).at(tok.line, tok.column, self._end())
        raise ParseError(
            f"expected a binding name, '_', or '(', found '{tok.lexeme}'",
            at=tok,
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
        return ast.If(cond, then, otherwise).at(kw.line, kw.column, self._end())

    def _while_stmt(self) -> ast.While:
        kw = self._advance()  # while
        cond = self._expression(allow_struct_lit=False)
        body = self._block()
        return ast.While(cond, body).at(kw.line, kw.column, self._end())

    def _for_stmt(self) -> ast.For:
        kw = self._advance()  # for
        var = self._expect(T.IDENT, "loop variable name")
        self._expect(T.IN, "'in'")
        first = self._expression(allow_struct_lit=False)
        if self._match(T.DOTDOT):  # range form: `start..end`
            end = self._expression(allow_struct_lit=False)
            body = self._block()
            return ast.For(var.value, first, end, body).at(kw.line, kw.column, self._end())
        # iterable form: `for v in xs`
        body = self._block()
        return ast.For(var.value, None, None, body, iterable=first).at(kw.line, kw.column, self._end())

    def _return_stmt(self) -> ast.Return:
        kw = self._advance()  # return
        value = None
        if not (self._at_separator() or self._check(T.RBRACE) or self._at_end()):
            start = self._start()
            value = self._expression()
            # `return a, b` is sugar for returning a tuple `(a, b)`.
            if self._check(T.COMMA):
                elems = [value]
                while self._match(T.COMMA):
                    elems.append(self._expression())
                value = ast.TupleLit(elems).at(value.line, value.column, self._end(), start)
        return ast.Return(value).at(kw.line, kw.column, self._end())

    def _assign_or_expr(self) -> ast.Stmt:
        start = self._start()
        expr = self._expression()
        if self._check(T.ASSIGN):
            eq = self._advance()
            if not _is_lvalue(expr):
                raise ParseError(
                    "invalid assignment target", at=expr
                )
            value = self._expression()
            return ast.Assign(expr, value).at(eq.line, eq.column, self._end(), start)
        return ast.ExprStmt(expr).at(expr.line, expr.column, self._end(), start)

    # -- expressions (precedence climbing) -----------------------------------

    def _expression(self, allow_struct_lit: bool = True) -> ast.Expr:
        prev = self._allow_struct_lit
        self._allow_struct_lit = allow_struct_lit
        try:
            return self._pipe()
        finally:
            self._allow_struct_lit = prev

    def _pipe(self) -> ast.Expr:
        # `|>` is the loosest binary level (below `||`), left-associative, and is
        # pure syntactic sugar: `x |> f` ≡ `f(x)` and `x |> f(a, b)` ≡
        # `f(x, a, b)` — the left operand is spliced as the call's first argument
        # (X6). It desugars here so the rest of the toolchain only sees calls.
        start = self._start()
        expr = self._logic_or()
        while self._check(T.PIPEGT):
            op = self._advance()
            rhs = self._logic_or()
            if isinstance(rhs, ast.Call):
                expr = ast.Call(rhs.callee, [expr] + list(rhs.args)).at(
                    op.line, op.column, self._end(), start)
            else:
                expr = ast.Call(rhs, [expr]).at(op.line, op.column, self._end(), start)
        return expr

    def _binary_left(self, sub, kinds) -> ast.Expr:
        start = self._start()
        expr = sub()
        while self._peek().kind in kinds:
            op = self._advance()
            right = sub()
            expr = ast.Binary(op.lexeme, expr, right).at(op.line, op.column, self._end(), start)
        return expr

    def _logic_or(self) -> ast.Expr:
        return self._binary_left(self._logic_and, {T.OR})

    def _logic_and(self) -> ast.Expr:
        return self._binary_left(self._equality, {T.AND})

    def _equality(self) -> ast.Expr:
        return self._binary_left(self._comparison, {T.EQ, T.NE})

    def _comparison(self) -> ast.Expr:
        return self._binary_left(self._bit_or, {T.LT, T.LE, T.GT, T.GE})

    # Bitwise operators bind tighter than comparison (so `a & b == c` parses as
    # `(a & b) == c`, avoiding C's precedence footgun), with `&` > `^` > `|`.
    def _bit_or(self) -> ast.Expr:
        return self._binary_left(self._bit_xor, {T.PIPE})

    def _bit_xor(self) -> ast.Expr:
        return self._binary_left(self._bit_and, {T.CARET})

    def _bit_and(self) -> ast.Expr:
        return self._binary_left(self._shift, {T.AMP})

    def _shift(self) -> ast.Expr:
        # `<<` / `>>` are not lexed as single tokens (so nested generic closers
        # like `Option<List<int>>` keep working); instead we recognise two
        # column-adjacent `<` or `>` tokens here as a shift operator.
        start = self._start()
        expr = self._term()
        while True:
            op = self._adjacent_shift()
            if op is None:
                return expr
            line, col = self._peek().line, self._peek().column
            self._advance()
            self._advance()
            right = self._term()
            expr = ast.Binary(op, expr, right).at(line, col, self._end(), start)

    def _adjacent_shift(self) -> str | None:
        a, b = self._peek(), self._peek(1)
        if a.line != b.line or b.column != a.column + 1:
            return None
        if a.kind is T.LT and b.kind is T.LT:
            return "<<"
        if a.kind is T.GT and b.kind is T.GT:
            return ">>"
        return None

    def _term(self) -> ast.Expr:
        return self._binary_left(self._factor, {T.PLUS, T.MINUS})

    def _factor(self) -> ast.Expr:
        return self._binary_left(self._cast, {T.STAR, T.SLASH, T.PERCENT})

    def _cast(self) -> ast.Expr:
        start = self._start()
        expr = self._unary()
        while self._check(T.AS):
            kw = self._advance()
            target = self._type()
            expr = ast.Cast(expr, target).at(kw.line, kw.column, self._end(), start)
        return expr

    def _unary(self) -> ast.Expr:
        if self._peek().kind in (T.MINUS, T.BANG, T.TILDE):
            op = self._advance()
            operand = self._unary()
            return ast.Unary(op.lexeme, operand).at(op.line, op.column, self._end())
        return self._postfix()

    def _postfix(self) -> ast.Expr:
        start = self._start()
        expr = self._primary()
        while True:
            if self._check(T.LPAREN):
                lp = self._advance()
                args = self._call_args()
                self._expect(T.RPAREN, "')'")
                expr = ast.Call(expr, args).at(lp.line, lp.column, self._end(), start)
            elif self._check(T.LBRACKET):
                lb = self._advance()
                index = self._expression()
                self._expect(T.RBRACKET, "']' to close index")
                expr = ast.Index(expr, index).at(lb.line, lb.column, self._end(), start)
            elif self._check(T.DOT):
                dot = self._advance()
                if self._check(T.INT):
                    idx_tok = self._advance()
                    if idx_tok.suffix is not None:
                        raise ParseError(
                            "tuple index may not have a type suffix",
                            at=idx_tok,
                        )
                    expr = ast.TupleIndex(expr, idx_tok.value).at(dot.line, dot.column, self._end(), start)
                else:
                    name = self._expect(T.IDENT, "field name or tuple index after '.'")
                    expr = ast.FieldAccess(expr, name.value).at(dot.line, dot.column, self._end(), start)
            elif self._check(T.QUESTION):
                q = self._advance()
                expr = ast.Try(expr).at(q.line, q.column, self._end(), start)
            else:
                break
        return expr

    def _primary(self) -> ast.Expr:
        tok = self._peek()
        if tok.kind is T.INT:
            self._advance()
            return ast.IntLit(tok.value, tok.suffix).at(tok.line, tok.column, self._end())
        if tok.kind is T.FLOAT:
            self._advance()
            return ast.FloatLit(tok.value, tok.suffix).at(tok.line, tok.column, self._end())
        if tok.kind is T.CHAR:
            self._advance()
            return ast.IntLit(tok.value, None, is_char=True).at(tok.line, tok.column, self._end())
        if tok.kind is T.STRING:
            self._advance()
            return ast.StrLit(tok.value).at(tok.line, tok.column, self._end())
        if tok.kind in (T.TRUE, T.FALSE):
            self._advance()
            return ast.BoolLit(tok.value).at(tok.line, tok.column, self._end())
        if tok.kind is T.IDENT:
            self._advance()
            if self._allow_struct_lit and self._check(T.LBRACE):
                return self._struct_lit(tok)
            return ast.Name(tok.value).at(tok.line, tok.column, self._end())
        if tok.kind is T.SELF:
            self._advance()
            return ast.Name("self").at(tok.line, tok.column, self._end())
        if tok.kind is T.MATCH:
            return self._match_expr()
        if tok.kind is T.LPAREN:
            if self._lambda_ahead():
                return self._lambda(tok)
            return self._paren_or_tuple(tok)
        if tok.kind is T.LBRACKET:
            return self._list_or_map_lit(tok)
        raise ParseError(f"expected an expression, found '{tok.lexeme}'", at=tok)

    def _list_or_map_lit(self, lb) -> ast.Expr:
        """Parse `[...]` as a list literal, or `[k: v, ...]` / `[:]` as a map."""
        self._advance()  # [
        self._skip_newlines()
        if self._match(T.COLON):                 # empty map `[:]`
            self._expect(T.RBRACKET, "']' to close empty map literal")
            return ast.MapLit([]).at(lb.line, lb.column, self._end())
        if self._check(T.RBRACKET):              # empty list `[]`
            self._advance()
            return ast.ListLit([]).at(lb.line, lb.column, self._end())
        first = self._expression(allow_struct_lit=True)
        if self._match(T.COLON):                 # map literal `[k: v, ...]`
            return self._map_lit_tail(lb, first)
        return self._list_lit_tail(lb, first)

    def _list_lit_tail(self, lb, first: ast.Expr) -> ast.ListLit:
        elems = [first]
        self._skip_newlines()
        while self._match(T.COMMA):
            self._skip_newlines()
            if self._check(T.RBRACKET):          # trailing comma
                break
            elems.append(self._expression(allow_struct_lit=True))
            self._skip_newlines()
        self._expect(T.RBRACKET, "']' to close list literal")
        return ast.ListLit(elems).at(lb.line, lb.column, self._end())

    def _map_lit_tail(self, lb, first_key: ast.Expr) -> ast.MapLit:
        first_val = self._expression(allow_struct_lit=True)
        entries = [(first_key, first_val)]
        self._skip_newlines()
        while self._match(T.COMMA):
            self._skip_newlines()
            if self._check(T.RBRACKET):          # trailing comma
                break
            key = self._expression(allow_struct_lit=True)
            self._expect(T.COLON, "':' between map key and value")
            val = self._expression(allow_struct_lit=True)
            entries.append((key, val))
            self._skip_newlines()
        self._expect(T.RBRACKET, "']' to close map literal")
        return ast.MapLit(entries).at(lb.line, lb.column, self._end())

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
            raise ParseError("match expression needs at least one arm", at=kw)
        return ast.Match(scrutinee, arms).at(kw.line, kw.column, self._end())

    def _match_arm(self) -> ast.MatchArm:
        start = self._start()
        pattern = self._pattern()
        guard = None
        if self._match(T.IF):
            guard = self._expression(allow_struct_lit=False)
        arrow = self._expect(T.FATARROW, "'=>' after match pattern")
        if self._check(T.LBRACE):
            body: ast.Expr | ast.Block = self._block()
        else:
            body = self._expression()
        return ast.MatchArm(pattern, guard, body).at(arrow.line, arrow.column, self._end(), start)

    def _pattern(self) -> ast.Pattern:
        first = self._base_pattern()
        if not self._check(T.PIPE):
            return first
        alts = [first]
        start_line, start_col = first.line, first.column
        while self._match(T.PIPE):
            alts.append(self._base_pattern())
        return ast.PatOr(alts).at(start_line, start_col, self._end(), first.span[:2])

    def _base_pattern(self) -> ast.Pattern:
        tok = self._peek()
        # literals (incl. negative integer literals and char literals)
        if tok.kind in (T.INT, T.CHAR, T.STRING, T.TRUE, T.FALSE):
            lit = self._primary()
            return ast.PatLiteral(lit).at(tok.line, tok.column, self._end())
        if tok.kind is T.MINUS:
            self._advance()
            int_tok = self._expect(T.INT, "integer literal after '-' in pattern")
            lit = ast.Unary("-", ast.IntLit(int_tok.value, int_tok.suffix)
                            .at(int_tok.line, int_tok.column, self._end())).at(tok.line, tok.column, self._end())
            return ast.PatLiteral(lit).at(tok.line, tok.column, self._end())
        # bare `.Variant` enum pattern
        if tok.kind is T.DOT:
            self._advance()
            vtok = self._expect(T.IDENT, "variant name after '.'")
            return self._enum_pattern_tail(None, vtok, tok)
        if tok.kind is T.LPAREN:
            return self._tuple_pattern()
        if tok.kind is T.IDENT:
            return self._ident_pattern(tok)
        raise ParseError(f"expected a pattern, found '{tok.lexeme}'", at=tok)

    def _ident_pattern(self, first: Token) -> ast.Pattern:
        self._advance()  # the identifier
        if first.value == "_":
            return ast.PatWildcard().at(first.line, first.column, self._end())
        # `Type { ... }` struct pattern
        if self._check(T.LBRACE):
            return self._struct_pattern(first)
        # `Enum.Variant` qualified enum pattern
        if self._check(T.DOT):
            self._advance()
            vtok = self._expect(T.IDENT, "variant name after '.'")
            return self._enum_pattern_tail(first.value, vtok, first)
        # `Variant(...)` — looks like a (possibly bare) enum variant with payload
        if self._check(T.LPAREN):
            return self._enum_pattern_tail(None, first, first)
        # otherwise a plain binding (could resolve to a no-payload variant in the
        # checker, which knows the scrutinee's type)
        return ast.PatBinding(first.value).at(first.line, first.column, self._end())

    def _enum_pattern_tail(self, enum_name, variant_tok: Token, start: Token) -> ast.PatEnum:
        """The rest of an enum pattern whose variant name is `variant_tok`;
        it started at `start` (`Enum`, `.` or the variant)."""
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
            variant_tok.line, variant_tok.column, self._end(), (start.line, start.column))

    def _tuple_pattern(self) -> ast.PatTuple:
        lp = self._advance()  # (
        elems = [self._pattern()]
        if not self._match(T.COMMA):
            tok = self._peek()
            raise ParseError(
                "expected ',' in tuple pattern (use '(p,)' for a 1-tuple)",
                at=tok,
            )
        while not self._check(T.RPAREN):
            elems.append(self._pattern())
            if not self._match(T.COMMA):
                break
        self._expect(T.RPAREN, "')'")
        return ast.PatTuple(elems).at(lp.line, lp.column, self._end())

    def _struct_pattern(self, name_tok: Token) -> ast.PatStruct:
        self._expect(T.LBRACE, "'{'")
        self._skip_newlines()
        fields: list[ast.FieldPat] = []
        while not self._check(T.RBRACE) and not self._at_end():
            fname = self._expect(T.IDENT, "field name in struct pattern")
            if self._match(T.COLON):
                pat = self._pattern()
            else:  # `{ x }` shorthand binds `x`
                pat = ast.PatBinding(fname.value).at(fname.line, fname.column, self._end())
            fields.append(ast.FieldPat(fname.value, pat).at(fname.line, fname.column, self._end()))
            if self._match(T.COMMA):
                self._skip_newlines()
            else:
                self._skip_newlines()
                break
        self._expect(T.RBRACE, "'}'")
        return ast.PatStruct(name_tok.value, fields).at(name_tok.line, name_tok.column, self._end())

    def _lambda_ahead(self) -> bool:
        """At an `LPAREN`, decide whether this begins a lambda `(params) => …`.

        Scan to the parenthesis that matches the current `(` (balancing nested
        brackets) and report whether a `=>` immediately follows. A lambda's
        parameter list is always balanced, so this needs no nesting limits."""
        depth = 0
        i = self.pos
        n = len(self.tokens)
        while i < n:
            k = self.tokens[i].kind
            if k in (T.LPAREN, T.LBRACKET, T.LBRACE):
                depth += 1
            elif k in (T.RPAREN, T.RBRACKET, T.RBRACE):
                depth -= 1
                if depth == 0:
                    j = i + 1
                    return j < n and self.tokens[j].kind is T.FATARROW
            elif k is T.EOF:
                return False
            i += 1
        return False

    def _lambda(self, lp: Token) -> ast.Lambda:
        self._advance()  # (
        params: list[ast.Param] = []
        if not self._check(T.RPAREN):
            while True:
                pname = self._expect(T.IDENT, "lambda parameter name")
                # The type annotation is optional: when the lambda is checked
                # against an expected function type the checker fills it in.
                ptype = self._type() if self._match(T.COLON) else None
                params.append(ast.Param(pname.value, ptype).at(pname.line, pname.column, self._end()))
                if not self._match(T.COMMA):
                    break
        self._expect(T.RPAREN, "')'")
        self._expect(T.FATARROW, "'=>' in lambda")
        if self._check(T.LBRACE):
            body: ast.Expr | ast.Block = self._block()
        else:
            body = self._expression()
        return ast.Lambda(params, body).at(lp.line, lp.column, self._end())

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
        return ast.TupleLit(elems).at(lp.line, lp.column, self._end())

    def _struct_lit(self, name_tok: Token) -> ast.StructLit:
        self._expect(T.LBRACE, "'{'")
        self._skip_newlines()
        fields: list[ast.FieldInit] = []
        while not self._check(T.RBRACE) and not self._at_end():
            fname = self._expect(T.IDENT, "field name")
            self._expect(T.COLON, "':'")
            value = self._expression(allow_struct_lit=True)
            fields.append(ast.FieldInit(fname.value, value).at(fname.line, fname.column, self._end()))
            if not self._match(T.COMMA):
                self._skip_newlines()
                break
            self._skip_newlines()
        self._expect(T.RBRACE, "'}'")
        return ast.StructLit(name_tok.value, fields).at(name_tok.line, name_tok.column, self._end())

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

    def _call_args(self) -> list[ast.Expr]:
        """Parse a call's argument list, recognising a bare `_` as a
        partial-application hole (v0.4.3, X7). A `_` is only a hole when it is
        the whole argument (immediately followed by ',' or ')'); otherwise it is
        an ordinary identifier expression."""
        args: list[ast.Expr] = []
        self._skip_newlines()
        if self._check(T.RPAREN):
            return args
        while True:
            if self._hole_ahead():
                tok = self._advance()
                args.append(ast.Hole().at(tok.line, tok.column, self._end()))
            else:
                args.append(self._expression(allow_struct_lit=True))
            self._skip_newlines()
            if self._match(T.COMMA):
                self._skip_newlines()
                continue
            break
        return args

    def _hole_ahead(self) -> bool:
        t = self._peek()
        if not (t.kind is T.IDENT and t.value == "_"):
            return False
        return self._peek(1).kind in (T.COMMA, T.RPAREN)


def _nest(opens: list[T], kind: T) -> None:
    """Track the brackets open while skipping tokens (`Parser._sync`): an
    opening one is pushed; a closing one pops back to its partner, or is
    ignored without one."""
    if kind in (T.LPAREN, T.LBRACKET, T.LBRACE):
        opens.append(kind)
        return
    partner = {T.RPAREN: T.LPAREN, T.RBRACKET: T.LBRACKET, T.RBRACE: T.LBRACE}.get(kind)
    if partner is not None and partner in opens:
        while opens.pop() is not partner:
            pass


def _is_lvalue(expr: ast.Expr) -> bool:
    if isinstance(expr, ast.Name):
        return True
    if isinstance(expr, ast.FieldAccess):
        return _is_lvalue(expr.target)
    if isinstance(expr, ast.Index):
        return _is_lvalue(expr.target)
    return False


def parse(tokens: list[Token]) -> ast.Program:
    """Convenience wrapper: parse a token list into a `Program`."""
    return Parser(tokens).parse_program()
