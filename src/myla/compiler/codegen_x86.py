"""x86-64 code generator for Myla v0.0 (docs/architecture.md §7).

Emits GAS / AT&T-syntax assembly for Linux x86-64, with no libc dependency:
I/O is done with raw `write`/`exit` syscalls. The generator is a single,
register-light pass over the type-checked AST and is meant to be obvious rather
than fast — it must produce the *same observable output* as the interpreter.

Conventions chosen for v0.0 (internal; we never call into C):

- Calling convention is stack-based (cdecl-like): the caller pushes arguments in
  reverse so argument *i* lands at ``16 + 8*i`` above the callee's ``%rbp``;
  the callee cleans nothing, the caller pops. Scalars are passed by value;
  structs are passed as a pointer to the caller's storage (safe because Myla
  parameters are immutable). A struct-returning function takes a hidden first
  argument: a pointer to caller-allocated result storage (sret).
- Every scalar occupies one 8-byte stack slot holding its *canonical* 64-bit
  value (signed values sign-extended, unsigned zero-extended), so loads/stores
  are plain 8-byte moves and only arithmetic needs width-aware wrapping.
- Expression results land in ``%rax``; binary operators evaluate the right
  operand, push it, evaluate the left, then pop the right into ``%rcx``.
"""
from __future__ import annotations

from .. import ast
from ..types import BoolType, Checker, FuncSig, IntType, StrType, StructType, Type


def _is_struct(t: Type | None) -> bool:
    return isinstance(t, StructType)


# signed / unsigned `set` mnemonics for the relational operators
_SET_MNEMONIC = {
    "<": ("setl", "setb"),
    "<=": ("setle", "setbe"),
    ">": ("setg", "seta"),
    ">=": ("setge", "setae"),
}


class CodeGen:
    def __init__(self, checker: Checker):
        self.checker = checker
        self.text: list[str] = []
        self.rodata: list[str] = []
        self._label_n = 0
        self._str_n = 0
        self._strings: dict[str, str] = {}  # raw text -> label
        # per-function state
        self._locals: dict[int, int] = {}   # id(node) -> rbp offset (negative)
        self._scopes: list[dict[str, tuple]] = []
        self._epilogue = ""
        self._struct_ret = False

    # -- type layout ---------------------------------------------------------

    def _size(self, t: Type) -> int:
        if isinstance(t, StructType):
            return sum(self._size(ft) for ft in self.checker.structs[t.name].values())
        return 8

    def _field_offset(self, struct_name: str, field: str) -> int:
        off = 0
        for fname, ftype in self.checker.structs[struct_name].items():
            if fname == field:
                return off
            off += self._size(ftype)
        raise KeyError(field)  # pragma: no cover - checker guarantees presence

    # -- emit helpers --------------------------------------------------------

    def _emit(self, line: str) -> None:
        self.text.append("\t" + line if line and not line.endswith(":") else line)

    def _label(self) -> str:
        self._label_n += 1
        return f".L{self._label_n}"

    def _string_label(self, text: str) -> str:
        if text in self._strings:
            return self._strings[text]
        label = f".Lstr{self._str_n}"
        self._str_n += 1
        self._strings[text] = label
        data = text.encode("utf-8")
        self.rodata.append(f"{label}:")
        self.rodata.append(f"\t.quad {len(data)}")
        if data:
            self.rodata.append("\t.byte " + ", ".join(str(b) for b in data))
        return label

    # -- public --------------------------------------------------------------

    def generate(self) -> str:
        entry = self.checker.entry
        if entry is None:
            raise ValueError("no entry point to compile")

        self._emit_runtime_prelude(entry.name)
        for decl in self.checker.program.decls:
            if isinstance(decl, ast.FunDecl):
                self._gen_function(decl)
        return self._assemble_source()

    def _assemble_source(self) -> str:
        out: list[str] = []
        out.append("\t.text")
        out.extend(self.text)
        out.append("")
        out.append("\t.section .rodata")
        out.append('.Lbool_true:\n\t.ascii "true"')
        out.append('.Lbool_false:\n\t.ascii "false"')
        out.extend(self.rodata)
        out.append("")
        # mark the stack non-executable to silence the linker
        out.append('\t.section .note.GNU-stack,"",@progbits')
        out.append("")
        return "\n".join(out)

    # -- runtime prelude (_start + print/trap helpers) -----------------------

    def _emit_runtime_prelude(self, entry_name: str) -> None:
        e = self.text.append
        e("\t.global _start")
        e("_start:")
        e(f"\tcall myla_{entry_name}")
        e("\tmovq $60, %rax")          # exit
        e("\txorq %rdi, %rdi")
        e("\tsyscall")
        e("")
        # __trap: exit(1) for runtime errors (e.g. divide by zero)
        e("__trap:")
        e("\tmovq $60, %rax")
        e("\tmovq $1, %rdi")
        e("\tsyscall")
        e("")
        # __print_nl: write a single newline to stdout
        e("__print_nl:")
        e("\tsubq $16, %rsp")
        e("\tmovb $10, (%rsp)")
        e("\tmovq $1, %rax")
        e("\tmovq $1, %rdi")
        e("\tmovq %rsp, %rsi")
        e("\tmovq $1, %rdx")
        e("\tsyscall")
        e("\taddq $16, %rsp")
        e("\tret")
        e("")
        # __print_minus: write a single '-' (no newline)
        e("__print_minus:")
        e("\tsubq $16, %rsp")
        e("\tmovb $45, (%rsp)")
        e("\tmovq $1, %rax")
        e("\tmovq $1, %rdi")
        e("\tmovq %rsp, %rsi")
        e("\tmovq $1, %rdx")
        e("\tsyscall")
        e("\taddq $16, %rsp")
        e("\tret")
        e("")
        # __print_uint: print %rdi as unsigned decimal, then a newline
        e("__print_uint:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tsubq $48, %rsp")
        e("\tmovq %rdi, %rax")
        e("\tleaq -1(%rbp), %rsi")     # write digits backwards from rbp-1
        e("\tmovq $10, %rcx")
        e("\ttestq %rax, %rax")
        e("\tjnz .Lpu_loop")
        e("\tmovb $48, (%rsi)")        # '0'
        e("\tdecq %rsi")
        e("\tjmp .Lpu_done")
        e(".Lpu_loop:")
        e("\ttestq %rax, %rax")
        e("\tjz .Lpu_done")
        e("\txorq %rdx, %rdx")
        e("\tdivq %rcx")               # rax/10 -> rax, rem -> rdx
        e("\taddb $48, %dl")
        e("\tmovb %dl, (%rsi)")
        e("\tdecq %rsi")
        e("\tjmp .Lpu_loop")
        e(".Lpu_done:")
        e("\tincq %rsi")               # rsi -> first digit
        e("\tmovq %rbp, %rdx")
        e("\tsubq %rsi, %rdx")         # length = rbp - rsi
        e("\tmovq $1, %rax")
        e("\tmovq $1, %rdi")
        e("\tsyscall")
        e("\tcall __print_nl")
        e("\tleave")
        e("\tret")
        e("")
        # __print_int: print %rdi as signed decimal, then a newline
        e("__print_int:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\ttestq %rdi, %rdi")
        e("\tjns .Lpi_pos")
        e("\tpushq %rdi")
        e("\tcall __print_minus")
        e("\tpopq %rdi")
        e("\tnegq %rdi")
        e(".Lpi_pos:")
        e("\tcall __print_uint")
        e("\tleave")
        e("\tret")
        e("")
        # __print_bool: %rdi != 0 -> "true", else "false" (then newline)
        e("__print_bool:")
        e("\ttestq %rdi, %rdi")
        e("\tjz .Lpb_false")
        e("\tleaq .Lbool_true(%rip), %rsi")
        e("\tmovq $4, %rdx")
        e("\tjmp .Lpb_write")
        e(".Lpb_false:")
        e("\tleaq .Lbool_false(%rip), %rsi")
        e("\tmovq $5, %rdx")
        e(".Lpb_write:")
        e("\tmovq $1, %rax")
        e("\tmovq $1, %rdi")
        e("\tsyscall")
        e("\tcall __print_nl")
        e("\tret")
        e("")
        # __print_str: %rdi -> [len:8][bytes]; write bytes then newline
        e("__print_str:")
        e("\tmovq (%rdi), %rdx")       # len
        e("\tleaq 8(%rdi), %rsi")      # data
        e("\tmovq $1, %rax")
        e("\tmovq $1, %rdi")
        e("\tsyscall")
        e("\tcall __print_nl")
        e("\tret")
        e("")
        # __str_eq: rdi,rsi -> ptrs; result 1/0 in rax
        e("__str_eq:")
        e("\tmovq (%rdi), %rcx")
        e("\tmovq (%rsi), %rdx")
        e("\tcmpq %rdx, %rcx")
        e("\tjne .Lse_ne")
        e("\tleaq 8(%rdi), %rdi")
        e("\tleaq 8(%rsi), %rsi")
        e(".Lse_loop:")
        e("\ttestq %rcx, %rcx")
        e("\tjz .Lse_eq")
        e("\tmovb (%rdi), %al")
        e("\tmovb (%rsi), %dl")
        e("\tcmpb %dl, %al")
        e("\tjne .Lse_ne")
        e("\tincq %rdi")
        e("\tincq %rsi")
        e("\tdecq %rcx")
        e("\tjmp .Lse_loop")
        e(".Lse_eq:")
        e("\tmovq $1, %rax")
        e("\tret")
        e(".Lse_ne:")
        e("\txorq %rax, %rax")
        e("\tret")
        e("")

    # -- functions -----------------------------------------------------------

    def _sig(self, name: str) -> FuncSig:
        return self.checker.functions[name]

    def _gen_function(self, decl: ast.FunDecl) -> None:
        sig = self._sig(decl.name)
        self._locals = {}
        self._scopes = []
        self._struct_ret = _is_struct(sig.ret)

        frame = self._layout_frame(decl)
        self._epilogue = f".Lret_{decl.name}"

        self._emit(f"myla_{decl.name}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        if frame:
            self._emit(f"subq ${frame}, %rsp")

        # bind parameters to their incoming stack slots
        self._scopes.append({})
        param_base = 1 if self._struct_ret else 0
        for i, (param, ptype) in enumerate(zip(decl.params, sig.params)):
            offset = 16 + 8 * (param_base + i)
            self._scopes[-1][param.name] = ("param", offset, ptype)

        self._gen_block(decl.body)

        self._emit(f"{self._epilogue}:")
        self._emit("leave")
        self._emit("ret")
        self._emit("")
        self._scopes.pop()

    def _layout_frame(self, decl: ast.FunDecl) -> int:
        """Assign a unique stack slot to every local/temp; return frame size."""
        cursor = [0]

        def alloc(node, size: int) -> None:
            cursor[0] += size
            self._locals[id(node)] = -cursor[0]

        def visit_stmt(stmt: ast.Stmt) -> None:
            if isinstance(stmt, ast.VarDecl):
                visit_expr(stmt.init)
                alloc(stmt, self._size(stmt.init.resolved_type))
            elif isinstance(stmt, ast.Assign):
                visit_expr(stmt.target)
                visit_expr(stmt.value)
            elif isinstance(stmt, ast.If):
                visit_expr(stmt.cond)
                for s in stmt.then.statements:
                    visit_stmt(s)
                if isinstance(stmt.otherwise, ast.If):
                    visit_stmt(stmt.otherwise)
                elif isinstance(stmt.otherwise, ast.Block):
                    for s in stmt.otherwise.statements:
                        visit_stmt(s)
            elif isinstance(stmt, ast.While):
                visit_expr(stmt.cond)
                for s in stmt.body.statements:
                    visit_stmt(s)
            elif isinstance(stmt, ast.For):
                visit_expr(stmt.start)
                visit_expr(stmt.end)
                cursor[0] += 8
                self._locals[f"loopvar:{id(stmt)}"] = -cursor[0]
                cursor[0] += 8
                self._locals[f"forend:{id(stmt)}"] = -cursor[0]
                for s in stmt.body.statements:
                    visit_stmt(s)
            elif isinstance(stmt, ast.Return):
                if stmt.value is not None:
                    visit_expr(stmt.value)
            elif isinstance(stmt, ast.ExprStmt):
                visit_expr(stmt.expr)

        def visit_expr(expr: ast.Expr) -> None:
            if isinstance(expr, ast.Unary):
                visit_expr(expr.operand)
            elif isinstance(expr, ast.Binary):
                visit_expr(expr.left)
                visit_expr(expr.right)
            elif isinstance(expr, ast.Call):
                for a in expr.args:
                    visit_expr(a)
                if _is_struct(expr.resolved_type):
                    alloc(expr, self._size(expr.resolved_type))
            elif isinstance(expr, ast.FieldAccess):
                visit_expr(expr.target)
            elif isinstance(expr, ast.StructLit):
                for fi in expr.fields:
                    visit_expr(fi.value)
                alloc(expr, self._size(expr.resolved_type))

        for s in decl.body.statements:
            visit_stmt(s)
        # round up to 16 for tidiness
        return (cursor[0] + 15) & ~15

    # special-key offset accessors (loop vars/ends use composite string keys)
    def _loopvar_off(self, stmt: ast.For) -> int:
        return self._locals[f"loopvar:{id(stmt)}"]

    def _forend_off(self, stmt: ast.For) -> int:
        return self._locals[f"forend:{id(stmt)}"]

    # -- scope helpers -------------------------------------------------------

    def _lookup(self, name: str) -> tuple:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        raise KeyError(name)  # pragma: no cover - checker guarantees presence

    # -- statements ----------------------------------------------------------

    def _gen_block(self, block: ast.Block) -> None:
        self._scopes.append({})
        for stmt in block.statements:
            self._gen_stmt(stmt)
        self._scopes.pop()

    def _gen_stmt(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.VarDecl):
            off = self._locals[id(stmt)]
            t = stmt.init.resolved_type
            if _is_struct(t):
                self._addr_of_struct(stmt.init)       # src -> rax
                self._emit("movq %rax, %rsi")
                self._emit(f"leaq {off}(%rbp), %rdi")
                self._emit_copy(self._size(t))
            else:
                self._eval(stmt.init)
                self._emit(f"movq %rax, {off}(%rbp)")
            self._scopes[-1][stmt.name] = ("local", off, t)

        elif isinstance(stmt, ast.Assign):
            t = stmt.target.resolved_type
            if _is_struct(t):
                self._addr_of_struct(stmt.value)
                self._emit("movq %rax, %rsi")
                self._addr_of_lvalue(stmt.target)
                self._emit("movq %rax, %rdi")
                self._emit_copy(self._size(t))
            else:
                self._eval(stmt.value)
                self._emit("pushq %rax")
                self._addr_of_lvalue(stmt.target)
                self._emit("popq %rcx")
                self._emit("movq %rcx, (%rax)")

        elif isinstance(stmt, ast.If):
            self._gen_if(stmt)

        elif isinstance(stmt, ast.While):
            start, end = self._label(), self._label()
            self._emit(f"{start}:")
            self._eval(stmt.cond)
            self._emit("testq %rax, %rax")
            self._emit(f"jz {end}")
            self._gen_block(stmt.body)
            self._emit(f"jmp {start}")
            self._emit(f"{end}:")

        elif isinstance(stmt, ast.For):
            self._gen_for(stmt)

        elif isinstance(stmt, ast.Return):
            if stmt.value is None:
                self._emit(f"jmp {self._epilogue}")
            elif self._struct_ret:
                self._addr_of_struct(stmt.value)
                self._emit("movq %rax, %rsi")
                self._emit("movq 16(%rbp), %rdi")     # sret pointer
                self._emit_copy(self._size(stmt.value.resolved_type))
                self._emit("movq 16(%rbp), %rax")
                self._emit(f"jmp {self._epilogue}")
            else:
                self._eval(stmt.value)
                self._emit(f"jmp {self._epilogue}")

        elif isinstance(stmt, ast.ExprStmt):
            if _is_struct(stmt.expr.resolved_type):
                self._addr_of_struct(stmt.expr)
            else:
                self._eval(stmt.expr)

    def _gen_if(self, stmt: ast.If) -> None:
        end = self._label()
        self._eval(stmt.cond)
        self._emit("testq %rax, %rax")
        if stmt.otherwise is None:
            self._emit(f"jz {end}")
            self._gen_block(stmt.then)
            self._emit(f"{end}:")
        else:
            els = self._label()
            self._emit(f"jz {els}")
            self._gen_block(stmt.then)
            self._emit(f"jmp {end}")
            self._emit(f"{els}:")
            if isinstance(stmt.otherwise, ast.If):
                self._gen_if(stmt.otherwise)
            else:
                self._gen_block(stmt.otherwise)
            self._emit(f"{end}:")

    def _gen_for(self, stmt: ast.For) -> None:
        loop_t = stmt.start.resolved_type
        lv = self._loopvar_off(stmt)
        fe = self._forend_off(stmt)
        self._eval(stmt.start)
        self._emit(f"movq %rax, {lv}(%rbp)")
        self._eval(stmt.end)
        self._emit(f"movq %rax, {fe}(%rbp)")

        start, end = self._label(), self._label()
        self._emit(f"{start}:")
        self._emit(f"movq {lv}(%rbp), %rax")
        self._emit(f"movq {fe}(%rbp), %rcx")
        self._emit("cmpq %rcx, %rax")
        stop = "jge" if loop_t.signed else "jae"
        self._emit(f"{stop} {end}")

        self._scopes.append({stmt.var_name: ("local", lv, loop_t)})
        for s in stmt.body.statements:
            self._gen_stmt(s)
        self._scopes.pop()

        self._emit(f"movq {lv}(%rbp), %rax")
        self._emit("addq $1, %rax")
        self._wrap(loop_t)
        self._emit(f"movq %rax, {lv}(%rbp)")
        self._emit(f"jmp {start}")
        self._emit(f"{end}:")

    # -- lvalues & struct addresses ------------------------------------------

    def _addr_of_lvalue(self, expr: ast.Expr) -> None:
        """Leave the *address* of a scalar lvalue in %rax."""
        if isinstance(expr, ast.Name):
            kind, off, _ = self._lookup(expr.ident)
            # scalar params are immutable, so an assignable Name is always local
            self._emit(f"leaq {off}(%rbp), %rax")
        elif isinstance(expr, ast.FieldAccess):
            self._addr_of_struct(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            if foff:
                self._emit(f"addq ${foff}, %rax")
        else:  # pragma: no cover - checker guarantees a valid lvalue
            raise ValueError("invalid lvalue")

    def _addr_of_struct(self, expr: ast.Expr) -> None:
        """Leave the *base address* of a struct value in %rax."""
        if isinstance(expr, ast.Name):
            kind, off, _ = self._lookup(expr.ident)
            if kind == "local":
                self._emit(f"leaq {off}(%rbp), %rax")
            else:  # struct param: slot holds a pointer
                self._emit(f"movq {off}(%rbp), %rax")
        elif isinstance(expr, ast.FieldAccess):
            self._addr_of_struct(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            if foff:
                self._emit(f"addq ${foff}, %rax")
        elif isinstance(expr, ast.StructLit):
            self._gen_struct_lit(expr)
            off = self._locals[id(expr)]
            self._emit(f"leaq {off}(%rbp), %rax")
        elif isinstance(expr, ast.Call):
            self._gen_call(expr)
            off = self._locals[id(expr)]
            self._emit(f"leaq {off}(%rbp), %rax")
        else:  # pragma: no cover
            raise ValueError(f"cannot take struct address of {type(expr).__name__}")

    def _gen_struct_lit(self, expr: ast.StructLit) -> None:
        base = self._locals[id(expr)]
        struct_name = expr.type_name
        for fi in expr.fields:
            foff = self._field_offset(struct_name, fi.name)
            ftype = self.checker.structs[struct_name][fi.name]
            slot = base + foff
            if _is_struct(ftype):
                self._addr_of_struct(fi.value)
                self._emit("movq %rax, %rsi")
                self._emit(f"leaq {slot}(%rbp), %rdi")
                self._emit_copy(self._size(ftype))
            else:
                self._eval(fi.value)
                self._emit(f"movq %rax, {slot}(%rbp)")

    def _emit_copy(self, size: int) -> None:
        """Copy `size` bytes from %rsi to %rdi (size is a multiple of 8)."""
        self._emit(f"movq ${size // 8}, %rcx")
        self._emit("cld")
        self._emit("rep movsq")

    # -- expressions ---------------------------------------------------------

    def _eval(self, expr: ast.Expr) -> None:
        """Evaluate a scalar expression, leaving its value in %rax."""
        if isinstance(expr, ast.IntLit):
            self._emit(f"movabsq ${expr.value}, %rax")
            self._wrap(expr.resolved_type)
        elif isinstance(expr, ast.BoolLit):
            self._emit(f"movq ${1 if expr.value else 0}, %rax")
        elif isinstance(expr, ast.StrLit):
            label = self._string_label(expr.value)
            self._emit(f"leaq {label}(%rip), %rax")
        elif isinstance(expr, ast.Name):
            _, off, _ = self._lookup(expr.ident)
            self._emit(f"movq {off}(%rbp), %rax")
        elif isinstance(expr, ast.Unary):
            self._eval_unary(expr)
        elif isinstance(expr, ast.Binary):
            self._eval_binary(expr)
        elif isinstance(expr, ast.Call):
            self._gen_call(expr)
        elif isinstance(expr, ast.FieldAccess):
            self._addr_of_struct(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            self._emit(f"movq {foff}(%rax), %rax")
        else:  # pragma: no cover
            raise ValueError(f"cannot evaluate {type(expr).__name__}")

    def _eval_unary(self, expr: ast.Unary) -> None:
        self._eval(expr.operand)
        if expr.op == "-":
            self._emit("negq %rax")
            self._wrap(expr.resolved_type)
        else:  # "!"
            self._emit("testq %rax, %rax")
            self._emit("sete %al")
            self._emit("movzbq %al, %rax")

    def _eval_binary(self, expr: ast.Binary) -> None:
        op = expr.op
        if op in ("&&", "||"):
            self._eval_logical(expr)
            return

        # operand type drives signedness / str handling
        ltype = expr.left.resolved_type

        if op in ("==", "!=") and isinstance(ltype, StrType):
            self._eval(expr.right)
            self._emit("pushq %rax")
            self._eval(expr.left)
            self._emit("movq %rax, %rdi")
            self._emit("popq %rsi")
            self._emit("call __str_eq")
            if op == "!=":
                self._emit("testq %rax, %rax")
                self._emit("sete %al")
                self._emit("movzbq %al, %rax")
            return

        # evaluate right, push; evaluate left into rax; pop right into rcx
        self._eval(expr.right)
        self._emit("pushq %rax")
        self._eval(expr.left)
        self._emit("popq %rcx")

        if op == "+":
            self._emit("addq %rcx, %rax")
            self._wrap(expr.resolved_type)
        elif op == "-":
            self._emit("subq %rcx, %rax")
            self._wrap(expr.resolved_type)
        elif op == "*":
            self._emit("imulq %rcx, %rax")
            self._wrap(expr.resolved_type)
        elif op in ("/", "%"):
            self._emit("testq %rcx, %rcx")
            self._emit("jz __trap")
            if ltype.signed:
                self._emit("cqo")
                self._emit("idivq %rcx")
            else:
                self._emit("xorq %rdx, %rdx")
                self._emit("divq %rcx")
            if op == "%":
                self._emit("movq %rdx, %rax")
            self._wrap(expr.resolved_type)
        elif op in _SET_MNEMONIC:
            signed_set, unsigned_set = _SET_MNEMONIC[op]
            self._emit("cmpq %rcx, %rax")
            self._emit(f"{signed_set if ltype.signed else unsigned_set} %al")
            self._emit("movzbq %al, %rax")
        elif op in ("==", "!="):
            self._emit("cmpq %rcx, %rax")
            self._emit(f"{'sete' if op == '==' else 'setne'} %al")
            self._emit("movzbq %al, %rax")
        else:  # pragma: no cover
            raise ValueError(f"unknown operator {op}")

    def _eval_logical(self, expr: ast.Binary) -> None:
        short = self._label()
        end = self._label()
        if expr.op == "&&":
            self._eval(expr.left)
            self._emit("testq %rax, %rax")
            self._emit(f"jz {short}")
            self._eval(expr.right)
            self._emit("testq %rax, %rax")
            self._emit(f"jz {short}")
            self._emit("movq $1, %rax")
            self._emit(f"jmp {end}")
            self._emit(f"{short}:")
            self._emit("xorq %rax, %rax")
            self._emit(f"{end}:")
        else:  # "||"
            self._eval(expr.left)
            self._emit("testq %rax, %rax")
            self._emit(f"jnz {short}")
            self._eval(expr.right)
            self._emit("testq %rax, %rax")
            self._emit(f"jnz {short}")
            self._emit("xorq %rax, %rax")
            self._emit(f"jmp {end}")
            self._emit(f"{short}:")
            self._emit("movq $1, %rax")
            self._emit(f"{end}:")

    def _gen_call(self, expr: ast.Call) -> None:
        callee = expr.callee
        assert isinstance(callee, ast.Name)
        name = callee.ident

        if name == "print":
            self._gen_print(expr.args[0])
            return

        sig = self._sig(name)
        struct_ret = _is_struct(sig.ret)

        # build the logical argument list and push it in reverse
        logical: list = []
        if struct_ret:
            logical.append(("sret", self._locals[id(expr)]))
        for i, arg in enumerate(expr.args):
            logical.append(("arg", i, arg, sig.params[i]))

        for item in reversed(logical):
            if item[0] == "sret":
                self._emit(f"leaq {item[1]}(%rbp), %rax")
            else:
                _, _, arg, ptype = item
                if _is_struct(ptype):
                    self._addr_of_struct(arg)
                else:
                    self._eval(arg)
            self._emit("pushq %rax")

        self._emit(f"call myla_{name}")
        if logical:
            self._emit(f"addq ${8 * len(logical)}, %rsp")

    def _gen_print(self, arg: ast.Expr) -> None:
        self._eval(arg)
        self._emit("movq %rax, %rdi")
        t = arg.resolved_type
        if isinstance(t, BoolType):
            self._emit("call __print_bool")
        elif isinstance(t, StrType):
            self._emit("call __print_str")
        elif isinstance(t, IntType):
            self._emit("call __print_int" if t.signed else "call __print_uint")
        else:  # pragma: no cover - checker restricts print()
            raise ValueError("unprintable type")

    # -- integer wrapping ----------------------------------------------------

    def _wrap(self, t: Type) -> None:
        assert isinstance(t, IntType)
        if t.width == 64:
            return
        if t.signed:
            shift = 64 - t.width
            self._emit(f"shlq ${shift}, %rax")
            self._emit(f"sarq ${shift}, %rax")
        elif t.width == 32:
            self._emit("movl %eax, %eax")        # zero-extend low 32 bits
        else:
            self._emit(f"andq ${(1 << t.width) - 1}, %rax")


def generate(checker: Checker) -> str:
    return CodeGen(checker).generate()
