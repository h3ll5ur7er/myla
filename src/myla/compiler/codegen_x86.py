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
from ..types import (
    BoolType, Checker, EnumType, FuncSig, IntType, StrType, StructType,
    TupleType, Type,
)


# Size of the heap arena reserved on first allocation (256 MiB). Generous for a
# bootstrap compiler; exhausting it traps. Reference counting (v0.2.3b) will let
# this memory be reused instead of only grown.
_ARENA_BYTES = 1 << 28


def _is_struct(t: Type | None) -> bool:
    return isinstance(t, StructType)


def _is_aggregate(t: Type | None) -> bool:
    """Aggregates (structs, tuples, enums) have value semantics and live in
    multi-slot storage, passed by address rather than in a register."""
    return isinstance(t, (StructType, TupleType, EnumType))


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

    def _is_boxed(self, t: Type | None) -> bool:
        """A recursive enum is boxed: stored as an 8-byte heap pointer wherever it
        appears as an aggregate member (its inline value lives on the heap)."""
        return isinstance(t, EnumType) and t.name in self.checker.recursive_enums

    def _stored_size(self, t: Type) -> int:
        """Bytes a value of `t` occupies *as a member* of an aggregate: a boxed
        enum contributes a pointer; everything else is stored inline."""
        return 8 if self._is_boxed(t) else self._size(t)

    def _owns_heap(self, t: Type | None, seen: frozenset[str] = frozenset()) -> bool:
        """True if an inline value of `t` (transitively) holds a boxed heap
        pointer, i.e. it participates in reference counting."""
        if self._is_boxed(t):
            return True
        if isinstance(t, StructType):
            if t.name in seen:
                return False
            return any(self._owns_heap(ft, seen | {t.name})
                       for ft in self.checker.structs[t.name].values())
        if isinstance(t, TupleType):
            return any(self._owns_heap(e, seen) for e in t.elems)
        if isinstance(t, EnumType):  # non-recursive enum (recursive => _is_boxed)
            if t.name in seen:
                return False
            return any(self._owns_heap(ft, seen | {t.name})
                       for payload in self.checker.enums[t.name].values()
                       for ft in payload)
        return False

    def _size(self, t: Type) -> int:
        """Inline size of a value (the size of its own storage / heap cell)."""
        if isinstance(t, StructType):
            return sum(self._stored_size(ft) for ft in self.checker.structs[t.name].values())
        if isinstance(t, TupleType):
            return sum(self._stored_size(e) for e in t.elems)
        if isinstance(t, EnumType):
            return 8 + self._enum_payload_size(t.name)
        return 8

    def _field_offset(self, struct_name: str, field: str) -> int:
        off = 0
        for fname, ftype in self.checker.structs[struct_name].items():
            if fname == field:
                return off
            off += self._stored_size(ftype)
        raise KeyError(field)  # pragma: no cover - checker guarantees presence

    def _elem_offset(self, t: TupleType, index: int) -> int:
        return sum(self._stored_size(e) for e in t.elems[:index])

    # -- enum layout: [tag:8][payload union], 8-byte tag + max variant payload --

    def _enum_payload_size(self, enum_name: str) -> int:
        variants = self.checker.enums[enum_name]
        return max((sum(self._stored_size(ft) for ft in payload)
                    for payload in variants.values()), default=0)

    def _variant_tag(self, enum_name: str, variant: str) -> int:
        return list(self.checker.enums[enum_name]).index(variant)

    def _variant_field_offset(self, enum_name: str, variant: str, index: int) -> int:
        payload = self.checker.enums[enum_name][variant]
        return 8 + sum(self._stored_size(ft) for ft in payload[:index])

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
        self._emit_drop_helpers()
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
        # heap bookkeeping for __alloc (zero-initialized)
        out.append("\t.bss")
        out.append("\t.align 8")
        out.append("__heap_ptr:")
        out.append("\t.skip 8")
        out.append("__heap_end:")
        out.append("\t.skip 8")
        out.append("__free_list:")
        out.append("\t.skip 8")
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
        # --- heap: reference-counted cells over a lazily-mmap'd arena (v0.2.3b) ---
        # Each cell is  [size:8][refcount:8][value bytes...]  and the pointer we
        # hand around points at the value bytes, so size is at -16 and the refcount
        # at -8. Cells are freed onto a size-segregated (exact-fit, LIFO) free list
        # and reused, so a program that allocates and drops in a loop runs in
        # bounded memory. The arena itself is anonymous mmap memory, zero-filled.
        #
        # __heap_init: reserve the arena (preserves %rdi).
        e("__heap_init:")
        e("\tpushq %rdi")
        e("\tmovq $9, %rax")            # mmap
        e("\txorq %rdi, %rdi")          # addr = NULL
        e(f"\tmovq ${_ARENA_BYTES}, %rsi")  # length
        e("\tmovq $3, %rdx")            # PROT_READ|PROT_WRITE
        e("\tmovq $34, %r10")           # MAP_PRIVATE|MAP_ANONYMOUS
        e("\tmovq $-1, %r8")            # fd
        e("\txorq %r9, %r9")            # offset
        e("\tsyscall")
        e("\tcmpq $-4096, %rax")        # mmap error? (return in [-4095,-1])
        e("\tja __trap")
        e("\tmovq %rax, __heap_ptr(%rip)")
        e(f"\taddq ${_ARENA_BYTES}, %rax")
        e("\tmovq %rax, __heap_end(%rip)")
        e("\tpopq %rdi")
        e("\tret")
        e("")
        # __alloc: in %rdi = value-size in bytes; out %rax = value pointer (rc = 1).
        e("__alloc:")
        e("\taddq $7, %rdi")            # round value size up to a multiple of 8
        e("\tandq $-8, %rdi")
        e("\tmovq __heap_end(%rip), %rax")
        e("\ttestq %rax, %rax")
        e("\tjnz .Lalloc_search")
        e("\tcall __heap_init")
        e(".Lalloc_search:")            # exact-fit search of the free list
        e("\tleaq __free_list(%rip), %r8")  # %r8 = address of the link to update
        e("\tmovq __free_list(%rip), %rsi") # %rsi = current node (value ptr) or 0
        e(".Lalloc_scan:")
        e("\ttestq %rsi, %rsi")
        e("\tjz .Lalloc_bump")
        e("\tcmpq %rdi, -16(%rsi)")     # node value-size == requested?
        e("\tje .Lalloc_reuse")
        e("\tmovq %rsi, %r8")           # advance: link = &node.next (node's value area)
        e("\tmovq (%rsi), %rsi")        # node = node.next
        e("\tjmp .Lalloc_scan")
        e(".Lalloc_reuse:")
        e("\tmovq (%rsi), %rax")        # node.next
        e("\tmovq %rax, (%r8)")         # unlink node
        e("\tmovq $1, -8(%rsi)")        # refcount = 1
        e("\tmovq %rsi, %rax")
        e("\tret")
        e(".Lalloc_bump:")
        e("\tmovq __heap_ptr(%rip), %rax")
        e("\tleaq 16(%rax,%rdi), %rcx") # new top = base + header(16) + size
        e("\tcmpq __heap_end(%rip), %rcx")
        e("\tja __trap")                # out of arena
        e("\tmovq %rcx, __heap_ptr(%rip)")
        e("\tmovq %rdi, (%rax)")        # header: size
        e("\tmovq $1, 8(%rax)")         # header: refcount
        e("\tleaq 16(%rax), %rax")      # value pointer = base + 16
        e("\tret")
        e("")
        # __free: in %rdi = value pointer; push the cell onto the free list.
        e("__free:")
        e("\tmovq __free_list(%rip), %rax")
        e("\tmovq %rax, (%rdi)")        # node.next = old head (stored in value area)
        e("\tmovq %rdi, __free_list(%rip)")
        e("\tret")
        e("")

    # -- functions -----------------------------------------------------------

    def _sig(self, name: str) -> FuncSig:
        return self.checker.functions[name]

    def _gen_function(self, decl: ast.FunDecl) -> None:
        sig = self._sig(decl.name)
        self._locals = {}
        self._scopes = []
        self._drop_scopes = []
        self._struct_ret = _is_aggregate(sig.ret)
        self._ret_type = sig.ret

        frame = self._layout_frame(decl)
        self._epilogue = f".Lret_{decl.name}"

        self._emit(f"myla_{decl.name}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        if frame:
            self._emit(f"subq ${frame}, %rsp")

        # bind parameters to their incoming stack slots (parameters are borrowed,
        # so they are never dropped — the caller owns the argument)
        self._scopes.append({})
        self._drop_scopes.append([])
        param_base = 1 if self._struct_ret else 0
        for i, (param, ptype) in enumerate(zip(decl.params, sig.params)):
            offset = 16 + 8 * (param_base + i)
            self._scopes[-1][param.name] = ("param", offset, ptype)

        self._gen_block(decl.body)

        self._emit(f"{self._epilogue}:")
        self._emit("leave")
        self._emit("ret")
        self._emit("")
        self._drop_scopes.pop()
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
            elif isinstance(stmt, ast.DestructDecl):
                visit_expr(stmt.init)
                cursor[0] += 8
                self._locals[f"destructbase:{id(stmt)}"] = -cursor[0]
                for leaf in _bind_leaves(stmt.binding):
                    alloc(leaf, self._size(leaf.resolved_type))
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

        def alloc_unbox(sub, ft: Type) -> None:
            if self._is_boxed(ft) and not isinstance(sub, ast.PatWildcard):
                cursor[0] += self._size(ft)
                self._locals[f"unbox:{id(sub)}"] = -cursor[0]

        def visit_pattern(pat, t: Type) -> None:
            if isinstance(pat, ast.PatEnum):
                payload = self.checker.enums[t.name][pat.variant]
                for sub, ft in zip(pat.elems, payload):
                    alloc_unbox(sub, ft)
                    visit_pattern(sub, ft)
            elif isinstance(pat, ast.PatTuple):
                for sub, et in zip(pat.elems, t.elems):
                    alloc_unbox(sub, et)
                    visit_pattern(sub, et)
            elif isinstance(pat, ast.PatStruct):
                fields = self.checker.structs[t.name]
                for fp in pat.fields:
                    ft = fields[fp.name]
                    alloc_unbox(fp.pattern, ft)
                    visit_pattern(fp.pattern, ft)
            elif isinstance(pat, ast.PatOr):
                for alt in pat.alts:
                    visit_pattern(alt, t)

        def visit_expr(expr: ast.Expr) -> None:
            if isinstance(expr, ast.Name):
                if getattr(expr, "enum_ctor", None) is not None:
                    alloc(expr, self._size(expr.resolved_type))  # bare `None`
            elif isinstance(expr, ast.Unary):
                visit_expr(expr.operand)
            elif isinstance(expr, ast.Binary):
                visit_expr(expr.left)
                visit_expr(expr.right)
            elif isinstance(expr, ast.Call):
                for a in expr.args:
                    visit_expr(a)
                if _is_aggregate(expr.resolved_type):
                    alloc(expr, self._size(expr.resolved_type))
            elif isinstance(expr, ast.FieldAccess):
                if getattr(expr, "enum_ctor", None) is not None:
                    alloc(expr, self._size(expr.resolved_type))  # no-payload variant
                else:
                    visit_expr(expr.target)
            elif isinstance(expr, ast.TupleIndex):
                visit_expr(expr.target)
            elif isinstance(expr, ast.StructLit):
                for fi in expr.fields:
                    visit_expr(fi.value)
                alloc(expr, self._size(expr.resolved_type))
            elif isinstance(expr, ast.TupleLit):
                for e in expr.elems:
                    visit_expr(e)
                alloc(expr, self._size(expr.resolved_type))
            elif isinstance(expr, ast.Match):
                visit_expr(expr.scrutinee)
                cursor[0] += self._size(expr.scrutinee.resolved_type)
                self._locals[f"matchscrut:{id(expr)}"] = -cursor[0]
                if expr.resolved_type is not None:
                    cursor[0] += self._size(expr.resolved_type)
                    self._locals[f"matchres:{id(expr)}"] = -cursor[0]
                for arm in expr.arms:
                    binds: dict = {}
                    _collect_bindings(arm.pattern, binds)
                    for bname, bt in binds.items():
                        cursor[0] += self._size(bt)
                        self._locals[f"matchbind:{id(arm)}:{bname}"] = -cursor[0]
                    visit_pattern(arm.pattern, expr.scrutinee.resolved_type)
                    if arm.guard is not None:
                        visit_expr(arm.guard)
                    if isinstance(arm.body, ast.Block):
                        for s in arm.body.statements:
                            visit_stmt(s)
                    else:
                        visit_expr(arm.body)

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
        self._open_scope()
        for stmt in block.statements:
            self._gen_stmt(stmt)
        self._close_scope()

    def _gen_stmt(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.VarDecl):
            off = self._locals[id(stmt)]
            t = stmt.init.resolved_type
            if _is_aggregate(t):
                self._addr_of_aggregate(stmt.init)    # src -> rax
                self._emit("movq %rax, %rsi")
                self._emit(f"leaq {off}(%rbp), %rdi")
                self._emit_copy(self._size(t))
                self._retain("rbp", off, t)           # new owner of the copied refs
            else:
                self._eval(stmt.init)
                self._emit(f"movq %rax, {off}(%rbp)")
            self._scopes[-1][stmt.name] = ("local", off, t)
            self._register_owner(off, t)
            self._drop_expr_temps(stmt.init)

        elif isinstance(stmt, ast.DestructDecl):
            self._gen_destruct(stmt)

        elif isinstance(stmt, ast.Assign):
            self._gen_assign(stmt)

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
                self._emit_return_drops()
                self._emit(f"jmp {self._epilogue}")
            elif self._struct_ret:
                self._addr_of_aggregate(stmt.value)
                self._emit("movq %rax, %rsi")
                self._emit("movq 16(%rbp), %rdi")     # sret pointer
                self._emit_copy(self._size(stmt.value.resolved_type))
                if self._owns_heap(self._ret_type):   # the result escapes: retain it
                    self._emit("movq 16(%rbp), %r8")
                    self._retain("r8", 0, self._ret_type)
                self._drop_expr_temps(stmt.value)     # then release temps & locals
                self._emit_return_drops()
                self._emit("movq 16(%rbp), %rax")
                self._emit(f"jmp {self._epilogue}")
            else:
                self._eval(stmt.value)
                self._emit("pushq %rax")              # preserve result across drops
                self._drop_expr_temps(stmt.value)
                self._emit_return_drops()
                self._emit("popq %rax")
                self._emit(f"jmp {self._epilogue}")

        elif isinstance(stmt, ast.ExprStmt):
            if _is_aggregate(stmt.expr.resolved_type):
                self._addr_of_aggregate(stmt.expr)
            else:
                self._eval(stmt.expr)
            self._drop_expr_temps(stmt.expr)

    def _gen_assign(self, stmt: ast.Assign) -> None:
        t = stmt.target.resolved_type
        if self._is_boxed(t) and not isinstance(stmt.target, ast.Name):
            # assigning into a boxed member: drop the old cell, store a fresh one
            self._box(stmt.value, t)                  # rax = new pointer (rc=1)
            self._emit("pushq %rax")
            self._addr_of_lvalue(stmt.target)         # rax = address of the slot
            self._emit("movq %rax, %rcx")
            self._emit("movq (%rcx), %rsi")           # old pointer
            self._emit("popq %rax")
            self._emit("movq %rax, (%rcx)")           # store new pointer
            self._emit("movq %rsi, %rdi")
            self._emit(f"call __dropb_{t.name}")      # release old subtree
            self._drop_expr_temps(stmt.value)
        elif _is_aggregate(t) and self._owns_heap(t):
            if not isinstance(stmt.target, ast.Name):
                raise NotImplementedError(
                    "reference-counted aggregate assignment is only supported "
                    "for simple variables")
            kind, off, _ = self._lookup(stmt.target.ident)
            self._addr_of_aggregate(stmt.value)       # build new value first
            self._emit("pushq %rax")                  # (may read the old value)
            self._drop_value("rbp", off, t)           # release the old value
            self._emit("popq %rsi")
            self._emit(f"leaq {off}(%rbp), %rdi")
            self._emit_copy(self._size(t))
            self._retain("rbp", off, t)
            self._drop_expr_temps(stmt.value)
        elif _is_aggregate(t):
            self._addr_of_aggregate(stmt.value)
            self._emit("movq %rax, %rsi")
            self._addr_of_lvalue(stmt.target)
            self._emit("movq %rax, %rdi")
            self._emit_copy(self._size(t))
            self._drop_expr_temps(stmt.value)
        else:
            self._eval(stmt.value)
            self._emit("pushq %rax")
            self._addr_of_lvalue(stmt.target)
            self._emit("popq %rcx")
            self._emit("movq %rcx, (%rax)")
            self._drop_expr_temps(stmt.value)

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
        self._drop_scopes.append([])
        for s in stmt.body.statements:
            self._gen_stmt(s)
        for slot, t in reversed(self._drop_scopes[-1]):  # release per iteration
            self._drop_value("rbp", slot, t)
        self._drop_scopes.pop()
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
            self._addr_of_aggregate(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            if foff:
                self._emit(f"addq ${foff}, %rax")
        else:  # pragma: no cover - checker guarantees a valid lvalue
            raise ValueError("invalid lvalue")

    def _addr_of_aggregate(self, expr: ast.Expr) -> None:
        """Leave the *base address* of an aggregate (struct/tuple/enum) value in %rax."""
        if isinstance(expr, ast.Match):
            self._gen_match(expr)
            off = self._locals[f"matchres:{id(expr)}"]
            self._emit(f"leaq {off}(%rbp), %rax")
        elif getattr(expr, "enum_ctor", None) is not None:
            self._gen_enum_ctor(expr)
            off = self._locals[id(expr)]
            self._emit(f"leaq {off}(%rbp), %rax")
        elif isinstance(expr, ast.Name):
            kind, off, _ = self._lookup(expr.ident)
            if kind == "local":
                self._emit(f"leaq {off}(%rbp), %rax")
            else:  # aggregate param: slot holds a pointer
                self._emit(f"movq {off}(%rbp), %rax")
        elif isinstance(expr, ast.FieldAccess):
            self._addr_of_aggregate(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            if self._is_boxed(expr.resolved_type):
                self._emit(f"movq {foff}(%rax), %rax")   # boxed member: load pointer
            elif foff:
                self._emit(f"addq ${foff}, %rax")
        elif isinstance(expr, ast.TupleIndex):
            self._addr_of_aggregate(expr.target)
            foff = self._elem_offset(expr.target.resolved_type, expr.index)
            if self._is_boxed(expr.resolved_type):
                self._emit(f"movq {foff}(%rax), %rax")   # boxed member: load pointer
            elif foff:
                self._emit(f"addq ${foff}, %rax")
        elif isinstance(expr, ast.StructLit):
            self._gen_struct_lit(expr)
            off = self._locals[id(expr)]
            self._emit(f"leaq {off}(%rbp), %rax")
        elif isinstance(expr, ast.TupleLit):
            self._gen_tuple_lit(expr)
            off = self._locals[id(expr)]
            self._emit(f"leaq {off}(%rbp), %rax")
        elif isinstance(expr, ast.Call):
            self._gen_call(expr)
            off = self._locals[id(expr)]
            self._emit(f"leaq {off}(%rbp), %rax")
        else:  # pragma: no cover
            raise ValueError(f"cannot take aggregate address of {type(expr).__name__}")

    def _gen_struct_lit(self, expr: ast.StructLit) -> None:
        base = self._locals[id(expr)]
        struct_name = expr.type_name
        for fi in expr.fields:
            foff = self._field_offset(struct_name, fi.name)
            ftype = self.checker.structs[struct_name][fi.name]
            self._store_member(fi.value, base + foff, ftype)

    def _gen_tuple_lit(self, expr: ast.TupleLit) -> None:
        base = self._locals[id(expr)]
        t = expr.resolved_type
        for i, elem in enumerate(expr.elems):
            self._store_member(elem, base + self._elem_offset(t, i), t.elems[i])

    def _gen_destruct(self, stmt: ast.DestructDecl) -> None:
        self._addr_of_aggregate(stmt.init)            # base addr -> rax
        base_slot = self._locals[f"destructbase:{id(stmt)}"]
        self._emit(f"movq %rax, {base_slot}(%rbp)")
        for leaf, offset, t in self._leaf_offsets(stmt.binding, stmt.init.resolved_type):
            leaf_off = self._locals[id(leaf)]
            self._emit(f"movq {base_slot}(%rbp), %rsi")
            if offset:
                self._emit(f"addq ${offset}, %rsi")
            if self._is_boxed(t):
                self._emit("movq (%rsi), %rsi")          # boxed elem: deref pointer
                self._emit(f"leaq {leaf_off}(%rbp), %rdi")
                self._emit_copy(self._size(t))
                self._retain("rbp", leaf_off, t)
            elif _is_aggregate(t):
                self._emit(f"leaq {leaf_off}(%rbp), %rdi")
                self._emit_copy(self._size(t))
                self._retain("rbp", leaf_off, t)
            else:
                self._emit("movq (%rsi), %rax")
                self._emit(f"movq %rax, {leaf_off}(%rbp)")
            self._scopes[-1][leaf.name] = ("local", leaf_off, t)
            self._register_owner(leaf_off, t)
        self._drop_expr_temps(stmt.init)

    def _leaf_offsets(self, binding, t, base: int = 0):
        if isinstance(binding, ast.BindWildcard):
            return
        if isinstance(binding, ast.BindName):
            yield (binding, base, t)
            return
        off = base
        for elem, et in zip(binding.elems, t.elems):
            yield from self._leaf_offsets(elem, et, off)
            off += self._stored_size(et)

    # -- enums & match -------------------------------------------------------

    def _gen_enum_ctor(self, expr: ast.Expr) -> None:
        enum_name, variant = expr.enum_ctor
        base = self._locals[id(expr)]
        self._emit(f"movq ${self._variant_tag(enum_name, variant)}, {base}(%rbp)")
        if isinstance(expr, ast.Call):
            payload = self.checker.enums[enum_name][variant]
            for i, arg in enumerate(expr.args):
                slot = base + self._variant_field_offset(enum_name, variant, i)
                self._store_member(arg, slot, payload[i])

    def _gen_match(self, expr: ast.Match) -> None:
        sst = expr.scrutinee.resolved_type
        root = self._locals[f"matchscrut:{id(expr)}"]
        if _is_aggregate(sst):
            self._addr_of_aggregate(expr.scrutinee)
            self._emit("movq %rax, %rsi")
            self._emit(f"leaq {root}(%rbp), %rdi")
            self._emit_copy(self._size(sst))
        else:
            self._eval(expr.scrutinee)
            self._emit(f"movq %rax, {root}(%rbp)")

        result_off = self._locals.get(f"matchres:{id(expr)}")
        result_type = expr.resolved_type
        end = self._label()
        for arm in expr.arms:
            arm_fail = self._label()
            self._match_pat(arm.pattern, root, sst, arm, arm_fail)
            # bindings and the scrutinee copy borrow from the scrutinee, which
            # outlives the match, so they introduce no owners of their own.
            self._scopes.append(self._arm_scope(arm))
            self._drop_scopes.append([])
            if arm.guard is not None:
                self._eval(arm.guard)
                self._emit("testq %rax, %rax")
                self._emit(f"jz {arm_fail}")
            self._gen_arm_body(arm.body, result_off, result_type)
            self._emit(f"jmp {end}")
            self._drop_scopes.pop()
            self._scopes.pop()
            self._emit(f"{arm_fail}:")
        self._emit("jmp __trap")   # unreachable when the match is exhaustive
        self._emit(f"{end}:")

    def _arm_scope(self, arm: ast.MatchArm) -> dict:
        binds: dict = {}
        _collect_bindings(arm.pattern, binds)
        scope: dict[str, tuple] = {}
        for name, bt in binds.items():
            slot = self._locals[f"matchbind:{id(arm)}:{name}"]
            scope[name] = ("local", slot, bt)
        return scope

    def _match_pat(self, pat, disp: int, t: Type, arm: ast.MatchArm, fail: str) -> None:
        if isinstance(pat, ast.PatWildcard):
            return
        if isinstance(pat, ast.PatBinding):
            variant = getattr(pat, "as_variant", None)
            if variant is not None:
                tag = self._variant_tag(t.name, variant[1])
                self._emit(f"movq {disp}(%rbp), %rax")
                self._emit(f"cmpq ${tag}, %rax")
                self._emit(f"jne {fail}")
                return
            slot = self._locals[f"matchbind:{id(arm)}:{pat.name}"]
            if _is_aggregate(t):
                self._emit(f"leaq {disp}(%rbp), %rsi")
                self._emit(f"leaq {slot}(%rbp), %rdi")
                self._emit_copy(self._size(t))
            else:
                self._emit(f"movq {disp}(%rbp), %rax")
                self._emit(f"movq %rax, {slot}(%rbp)")
            return
        if isinstance(pat, ast.PatLiteral):
            self._match_literal(pat.literal, disp, t, fail)
            return
        if isinstance(pat, ast.PatEnum):
            tag = self._variant_tag(t.name, pat.variant)
            self._emit(f"movq {disp}(%rbp), %rax")
            self._emit(f"cmpq ${tag}, %rax")
            self._emit(f"jne {fail}")
            payload = self.checker.enums[t.name][pat.variant]
            for i, sub in enumerate(pat.elems):
                ft = payload[i]
                foff = self._variant_field_offset(t.name, pat.variant, i)
                self._match_pat(sub, self._member_disp(sub, disp + foff, ft), ft, arm, fail)
            return
        if isinstance(pat, ast.PatTuple):
            for i, sub in enumerate(pat.elems):
                et = t.elems[i]
                doff = disp + self._elem_offset(t, i)
                self._match_pat(sub, self._member_disp(sub, doff, et), et, arm, fail)
            return
        if isinstance(pat, ast.PatStruct):
            fields = self.checker.structs[t.name]
            for fp in pat.fields:
                ft = fields[fp.name]
                foff = self._field_offset(t.name, fp.name)
                self._match_pat(fp.pattern, self._member_disp(fp.pattern, disp + foff, ft),
                                ft, arm, fail)
            return
        if isinstance(pat, ast.PatOr):
            matched = self._label()
            for alt in pat.alts[:-1]:
                next_alt = self._label()
                self._match_pat(alt, disp, t, arm, next_alt)
                self._emit(f"jmp {matched}")
                self._emit(f"{next_alt}:")
            self._match_pat(pat.alts[-1], disp, t, arm, fail)
            self._emit(f"{matched}:")
            return
        raise ValueError(f"cannot compile pattern {type(pat).__name__}")  # pragma: no cover

    def _member_disp(self, sub, slot_disp: int, ft: Type) -> int:
        """Displacement of the inline value a sub-pattern matches against. A boxed
        member is a pointer, so unbox it (deref + copy) into a per-pattern temp."""
        if not self._is_boxed(ft) or isinstance(sub, ast.PatWildcard):
            return slot_disp
        utmp = self._locals[f"unbox:{id(sub)}"]
        self._emit(f"movq {slot_disp}(%rbp), %rsi")   # load pointer -> value address
        self._emit(f"leaq {utmp}(%rbp), %rdi")
        self._emit_copy(self._size(ft))
        return utmp

    def _match_literal(self, literal, disp: int, t: Type, fail: str) -> None:
        if isinstance(t, StrType):
            label = self._string_label(_const_str(literal))
            self._emit(f"movq {disp}(%rbp), %rdi")
            self._emit(f"leaq {label}(%rip), %rsi")
            self._emit("call __str_eq")
            self._emit("testq %rax, %rax")
            self._emit(f"jz {fail}")
            return
        value = _const_scalar(literal)
        self._emit(f"movq {disp}(%rbp), %rax")
        self._emit(f"movabsq ${value}, %rcx")
        self._emit("cmpq %rcx, %rax")
        self._emit(f"jne {fail}")

    def _gen_arm_body(self, body, result_off, result_type) -> None:
        if isinstance(body, ast.Block):
            self._open_scope()
            stmts = body.statements
            for i, s in enumerate(stmts):
                if i == len(stmts) - 1 and isinstance(s, ast.ExprStmt) and result_off is not None:
                    self._store_value(s.expr, result_off, result_type)
                    self._drop_expr_temps(s.expr)
                else:
                    self._gen_stmt(s)
            self._close_scope()
        elif result_off is not None:
            self._store_value(body, result_off, result_type)
            self._drop_expr_temps(body)
        elif _is_aggregate(body.resolved_type):
            self._addr_of_aggregate(body)
            self._drop_expr_temps(body)
        else:
            self._eval(body)
            self._drop_expr_temps(body)

    def _store_value(self, expr: ast.Expr, off: int, t: Type) -> None:
        if _is_aggregate(t):
            self._addr_of_aggregate(expr)
            self._emit("movq %rax, %rsi")
            self._emit(f"leaq {off}(%rbp), %rdi")
            self._emit_copy(self._size(t))
            self._retain("rbp", off, t)
        else:
            self._eval(expr)
            self._emit(f"movq %rax, {off}(%rbp)")

    def _emit_copy(self, size: int) -> None:
        """Copy `size` bytes from %rsi to %rdi (size is a multiple of 8)."""
        self._emit(f"movq ${size // 8}, %rcx")
        self._emit("cld")
        self._emit("rep movsq")

    def _box(self, expr: ast.Expr, t: Type) -> None:
        """Heap-allocate a copy of `expr`'s inline value (a boxed/recursive enum)
        and leave the heap pointer (refcount 1) in %rax. The fresh cell becomes a
        new owner of any boxed pointers it copied in, so we retain them."""
        self._addr_of_aggregate(expr)            # inline source address -> rax
        self._emit("pushq %rax")
        self._emit(f"movq ${self._size(t)}, %rdi")
        self._emit("call __alloc")               # %rax = fresh heap cell (rc=1)
        self._emit("popq %rsi")                  # source
        self._emit("pushq %rax")                 # save destination pointer
        self._emit("movq %rax, %rdi")
        self._emit_copy(self._size(t))           # source(%rsi) -> dest(%rdi)
        self._emit("popq %rax")                  # boxed value = dest pointer
        if self._owns_heap(t):
            self._emit("pushq %rax")
            self._emit("movq %rax, %r8")         # retain children of the new cell
            self._emit_owned_walk("r8", 0, t, self._inc_box)
            self._emit("popq %rax")

    # -- reference counting: retain (inc) / drop helpers ---------------------

    def _inc_box(self, ptr_off: int, base: str, enum_name: str) -> None:
        self._emit(f"movq {ptr_off}(%{base}), %rax")
        self._emit("incq -8(%rax)")

    def _drop_box(self, ptr_off: int, base: str, enum_name: str) -> None:
        self._emit(f"movq {ptr_off}(%{base}), %rdi")
        self._emit(f"call __dropb_{enum_name}")

    def _emit_owned_walk(self, base: str, off: int, t: Type, on_box) -> None:
        """Walk the boxed pointers an inline value of `t` directly owns, calling
        `on_box(ptr_off, base, enum_name)` for each. Recurses through inline
        sub-aggregates; boxed enum members are leaves (the action follows them)."""
        if isinstance(t, StructType):
            cur = off
            for ft in self.checker.structs[t.name].values():
                self._walk_member(base, cur, ft, on_box)
                cur += self._stored_size(ft)
        elif isinstance(t, TupleType):
            cur = off
            for et in t.elems:
                self._walk_member(base, cur, et, on_box)
                cur += self._stored_size(et)
        elif isinstance(t, EnumType):
            done = self._label()
            self._emit(f"movq {off}(%{base}), %rax")   # tag
            for variant, payload in self.checker.enums[t.name].items():
                if not any(self._is_boxed(ft) or self._owns_heap(ft) for ft in payload):
                    continue
                nxt = self._label()
                self._emit(f"cmpq ${self._variant_tag(t.name, variant)}, %rax")
                self._emit(f"jne {nxt}")
                cur = off + 8
                for ft in payload:
                    self._walk_member(base, cur, ft, on_box)
                    cur += self._stored_size(ft)
                self._emit(f"jmp {done}")
                self._emit(f"{nxt}:")
            self._emit(f"{done}:")

    def _walk_member(self, base: str, off: int, ft: Type, on_box) -> None:
        if self._is_boxed(ft):
            on_box(off, base, ft.name)
        elif self._owns_heap(ft):
            self._emit_owned_walk(base, off, ft, on_box)

    def _retain(self, base: str, off: int, t: Type) -> None:
        if self._owns_heap(t):
            self._emit_owned_walk(base, off, t, self._inc_box)

    def _drop_value(self, base: str, off: int, t: Type) -> None:
        if self._owns_heap(t):
            self._emit_owned_walk(base, off, t, self._drop_box)

    # -- ownership scopes & temporaries --------------------------------------

    def _open_scope(self) -> None:
        self._scopes.append({})
        self._drop_scopes.append([])

    def _close_scope(self) -> None:
        """Drop the owning locals declared in the innermost scope, then pop it."""
        for slot, t in reversed(self._drop_scopes[-1]):
            self._drop_value("rbp", slot, t)
        self._drop_scopes.pop()
        self._scopes.pop()

    def _register_owner(self, slot: int, t: Type) -> None:
        if self._owns_heap(t):
            self._drop_scopes[-1].append((slot, t))

    def _emit_return_drops(self) -> None:
        """Drop every owning local currently in scope (for an early `return`)."""
        for scope in reversed(self._drop_scopes):
            for slot, t in reversed(scope):
                self._drop_value("rbp", slot, t)

    def _collect_expr_temps(self, expr: ast.Expr, out: list) -> None:
        """Collect (slot, type) of owning aggregate *temporaries* produced while
        evaluating `expr` — values that live in a frame temp slot and must be
        dropped once the statement that produced them finishes. Does not descend
        into `match` arm bodies (those own their own temporaries)."""
        if expr is None:
            return
        if id(expr) in self._locals and self._owns_heap(getattr(expr, "resolved_type", None)):
            out.append((self._locals[id(expr)], expr.resolved_type))
        if isinstance(expr, ast.Unary):
            self._collect_expr_temps(expr.operand, out)
        elif isinstance(expr, ast.Binary):
            self._collect_expr_temps(expr.left, out)
            self._collect_expr_temps(expr.right, out)
        elif isinstance(expr, ast.Call):
            for a in expr.args:
                self._collect_expr_temps(a, out)
        elif isinstance(expr, ast.FieldAccess):
            if getattr(expr, "enum_ctor", None) is None:
                self._collect_expr_temps(expr.target, out)
        elif isinstance(expr, ast.TupleIndex):
            self._collect_expr_temps(expr.target, out)
        elif isinstance(expr, ast.StructLit):
            for fi in expr.fields:
                self._collect_expr_temps(fi.value, out)
        elif isinstance(expr, ast.TupleLit):
            for e in expr.elems:
                self._collect_expr_temps(e, out)
        elif isinstance(expr, ast.Match):
            self._collect_expr_temps(expr.scrutinee, out)

    def _drop_expr_temps(self, expr: ast.Expr) -> None:
        temps: list = []
        self._collect_expr_temps(expr, temps)
        for slot, t in temps:
            self._drop_value("rbp", slot, t)

    def _emit_drop_helpers(self) -> None:
        """Emit `__dropb_<E>` for each recursive enum: decrement the cell's
        refcount and, at zero, drop the children it owns and free the cell."""
        for name in sorted(self.checker.recursive_enums):
            self._emit(f"__dropb_{name}:")
            self._emit("decq -8(%rdi)")
            keep = self._label()
            self._emit(f"jnz {keep}")
            self._emit("pushq %rbp")
            self._emit("movq %rsp, %rbp")
            self._emit("pushq %rbx")
            self._emit("movq %rdi, %rbx")
            self._emit_owned_walk("rbx", 0, EnumType(name), self._drop_box)
            self._emit("movq %rbx, %rdi")
            self._emit("popq %rbx")
            self._emit("leave")
            self._emit("jmp __free")
            self._emit(f"{keep}:")
            self._emit("ret")
            self._emit("")

    def _store_member(self, value: ast.Expr, slot_off: int, mt: Type) -> None:
        """Store `value` into an aggregate member at `slot_off(%rbp)`: a boxed
        enum member holds a pointer, other aggregates are copied inline."""
        if self._is_boxed(mt):
            self._box(value, mt)
            self._emit(f"movq %rax, {slot_off}(%rbp)")
        elif _is_aggregate(mt):
            self._addr_of_aggregate(value)
            self._emit("movq %rax, %rsi")
            self._emit(f"leaq {slot_off}(%rbp), %rdi")
            self._emit_copy(self._size(mt))
            self._retain("rbp", slot_off, mt)
        else:
            self._eval(value)
            self._emit(f"movq %rax, {slot_off}(%rbp)")

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
            self._addr_of_aggregate(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            self._emit(f"movq {foff}(%rax), %rax")
        elif isinstance(expr, ast.TupleIndex):
            self._addr_of_aggregate(expr.target)
            foff = self._elem_offset(expr.target.resolved_type, expr.index)
            self._emit(f"movq {foff}(%rax), %rax")
        elif isinstance(expr, ast.Match):
            self._gen_match(expr)
            if expr.resolved_type is not None:
                off = self._locals[f"matchres:{id(expr)}"]
                self._emit(f"movq {off}(%rbp), %rax")
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
        struct_ret = _is_aggregate(sig.ret)

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
                if _is_aggregate(ptype):
                    self._addr_of_aggregate(arg)
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


def _bind_leaves(binding):
    """Yield the `BindName` leaves of a destructuring binding, in order."""
    if isinstance(binding, ast.BindName):
        yield binding
    elif isinstance(binding, ast.BindTuple):
        for elem in binding.elems:
            yield from _bind_leaves(elem)
    # BindWildcard binds nothing


def _collect_bindings(pat, into: dict) -> None:
    """Map each pattern binding name -> its resolved type (or-pattern alts share)."""
    if isinstance(pat, ast.PatBinding):
        if getattr(pat, "as_variant", None) is None:
            into[pat.name] = pat.resolved_type
    elif isinstance(pat, ast.PatEnum):
        for sub in pat.elems:
            _collect_bindings(sub, into)
    elif isinstance(pat, ast.PatTuple):
        for sub in pat.elems:
            _collect_bindings(sub, into)
    elif isinstance(pat, ast.PatStruct):
        for fp in pat.fields:
            _collect_bindings(fp.pattern, into)
    elif isinstance(pat, ast.PatOr):
        for alt in pat.alts:
            _collect_bindings(alt, into)


def _const_str(literal) -> str:
    return literal.value


def _const_scalar(literal) -> int:
    """The constant integer/bool value of a literal pattern."""
    if isinstance(literal, ast.IntLit):
        return literal.value
    if isinstance(literal, ast.BoolLit):
        return 1 if literal.value else 0
    if isinstance(literal, ast.Unary) and literal.op == "-":
        return -literal.operand.value
    raise ValueError(f"unsupported literal pattern {type(literal).__name__}")  # pragma: no cover


def generate(checker: Checker) -> str:
    return CodeGen(checker).generate()
