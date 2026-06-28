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
    BoolType, Checker, EnumType, FuncSig, IntType, ListType, MapType, StrType,
    StringBuilderType, StructType, TupleType, Type, type_name,
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
        if isinstance(t, (ListType, MapType, StringBuilderType)):  # refcounted cell
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

    # -- list layout: a heap cell [len:8][cap:8][elem0][elem1]...] ------------

    def _type_mangle(self, t: Type) -> str:
        """A stable identifier fragment for `t`, used to name per-type helpers."""
        if isinstance(t, ListType):
            return "L_" + self._type_mangle(t.elem)
        if isinstance(t, MapType):
            return "M_" + self._type_mangle(t.key) + "_" + self._type_mangle(t.value)
        if isinstance(t, (StructType, EnumType)):
            return t.name
        if isinstance(t, TupleType):
            return "T" + str(len(t.elems)) + "".join(
                "_" + self._type_mangle(e) for e in t.elems)
        if isinstance(t, StringBuilderType):
            return "SB"
        return type_name(t)  # int32 / bool / str

    def _list_drop_name(self, t: ListType) -> str:
        return "__drop_list_" + self._type_mangle(t.elem)

    def _list_clone_name(self, t: ListType) -> str:
        return "__clone_list_" + self._type_mangle(t.elem)

    def _list_grow_name(self, t: ListType) -> str:
        return "__grow_list_" + self._type_mangle(t.elem)

    # -- map layout: a heap cell [len:8][cap:8][slot0]...]; each slot is
    # [state:8][key:8][value:vs] with state 0=empty / 1=occupied / 2=tombstone --

    def _map_suffix(self, t: MapType) -> str:
        return self._type_mangle(t.key) + "_" + self._type_mangle(t.value)

    def _map_slot_size(self, t: MapType) -> int:
        return 16 + self._stored_size(t.value)

    def _map_drop_name(self, t: MapType) -> str:
        return "__drop_map_" + self._map_suffix(t)

    def _map_clone_name(self, t: MapType) -> str:
        return "__clone_map_" + self._map_suffix(t)

    def _map_grow_name(self, t: MapType) -> str:
        return "__grow_map_" + self._map_suffix(t)

    def _map_new_name(self, t: MapType) -> str:
        return "__new_map_" + self._map_suffix(t)

    def _map_put_name(self, t: MapType) -> str:
        return "__put_map_" + self._map_suffix(t)

    def _map_find_name(self, t: MapType) -> str:
        return "__find_map_" + self._map_suffix(t)

    def _map_keys_name(self, t: MapType) -> str:
        return "__keys_map_" + self._map_suffix(t)

    def _map_remove_name(self, t: MapType) -> str:
        return "__remove_map_" + self._map_suffix(t)

    def _heap_clone_name(self, t: Type) -> str:
        if isinstance(t, StringBuilderType):
            return "__sb_clone"
        return self._map_clone_name(t) if isinstance(t, MapType) \
            else self._list_clone_name(t)

    def _gather_list_types(self, t: Type | None, into: dict,
                           seen: frozenset = frozenset()) -> None:
        if isinstance(t, StringBuilderType):
            into.setdefault("SB", t)
        elif isinstance(t, ListType):
            into.setdefault(self._type_mangle(t), t)
            self._gather_list_types(t.elem, into, seen)
        elif isinstance(t, MapType):
            into.setdefault(self._type_mangle(t), t)
            self._gather_list_types(t.key, into, seen)
            self._gather_list_types(t.value, into, seen)
        elif isinstance(t, StructType):
            if t.name in seen:  # break recursive (boxed) type cycles
                return
            for ft in self.checker.structs.get(t.name, {}).values():
                self._gather_list_types(ft, into, seen | {t.name})
        elif isinstance(t, EnumType):
            if t.name in seen:
                return
            for payload in self.checker.enums.get(t.name, {}).values():
                for ft in payload:
                    self._gather_list_types(ft, into, seen | {t.name})
        elif isinstance(t, TupleType):
            for e in t.elems:
                self._gather_list_types(e, into, seen)

    def _collect_list_types(self) -> dict:
        """Every concrete list type used anywhere in the program (keyed by mangle),
        so we can emit one `__drop_list_<elem>` routine per element type."""
        found: dict = {}
        for fields in self.checker.structs.values():
            for ft in fields.values():
                self._gather_list_types(ft, found)
        for variants in self.checker.enums.values():
            for payload in variants.values():
                for ft in payload:
                    self._gather_list_types(ft, found)
        for sig in self.checker.functions.values():
            for p in sig.params:
                self._gather_list_types(p, found)
            self._gather_list_types(sig.ret, found)
        for info in self.checker.consts.values():
            self._gather_list_types(info.type, found)

        def walk(node) -> None:
            import dataclasses
            self._gather_list_types(getattr(node, "resolved_type", None), found)
            if not dataclasses.is_dataclass(node):
                return
            for f in dataclasses.fields(node):
                v = getattr(node, f.name)
                if isinstance(v, ast.Node):
                    walk(v)
                elif isinstance(v, list):
                    for it in v:
                        if isinstance(it, ast.Node):
                            walk(it)

        for decl in self.checker.program.decls:
            walk(decl)
        return found

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
        # length-prefixed `str` cells used by format()'s runtime renderers
        out.append('.Lstr_true:\n\t.quad 4\n\t.ascii "true"')
        out.append('.Lstr_false:\n\t.quad 5\n\t.ascii "false"')
        out.append('.Lstr_minus:\n\t.quad 1\n\t.ascii "-"')
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
        # __panic: %rdi -> [len:8][bytes]; write the message + newline to stderr,
        # then exit(1). Used by assert/panic/unreachable (§7).
        e("__panic:")
        e("\tmovq (%rdi), %rdx")        # len
        e("\tleaq 8(%rdi), %rsi")       # data
        e("\tmovq $1, %rax")            # write
        e("\tmovq $2, %rdi")            # stderr
        e("\tsyscall")
        e("\tsubq $16, %rsp")           # newline to stderr
        e("\tmovb $10, (%rsp)")
        e("\tmovq $1, %rax")
        e("\tmovq $2, %rdi")
        e("\tmovq %rsp, %rsi")
        e("\tmovq $1, %rdx")
        e("\tsyscall")
        e("\taddq $16, %rsp")
        e("\tmovq $60, %rax")           # exit(1)
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
        # __str_concat: rdi = A, rsi = B (both -> [len:8][bytes]); out rax = a fresh
        # heap str [len:8][bytes] holding A's bytes followed by B's.
        e("__str_concat:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tpushq %r14")
        e("\tpushq %r15")
        e("\tmovq %rdi, %rbx")          # A
        e("\tmovq %rsi, %r12")          # B
        e("\tmovq (%rbx), %r13")        # lenA
        e("\tmovq (%r12), %r14")        # lenB
        e("\tleaq (%r13,%r14), %rdi")   # total = lenA + lenB
        e("\taddq $8, %rdi")            # value size = 8 (len field) + total
        e("\tcall __alloc")            # rax = new cell (rc=1)
        e("\tmovq %rax, %r15")          # result
        e("\tleaq (%r13,%r14), %rax")
        e("\tmovq %rax, (%r15)")        # store total length
        e("\tleaq 8(%r15), %rdi")       # dst = result bytes
        e("\tleaq 8(%rbx), %rsi")       # src = A bytes
        e("\tmovq %r13, %rcx")          # count = lenA
        e("\tcld")
        e("\trep movsb")               # copy A; rdi now points past A's bytes
        e("\tleaq 8(%r12), %rsi")       # src = B bytes
        e("\tmovq %r14, %rcx")          # count = lenB
        e("\trep movsb")               # copy B
        e("\tmovq %r15, %rax")
        e("\tpopq %r15")
        e("\tpopq %r14")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tleave")
        e("\tret")
        e("")
        # __uint_to_str: rdi = value -> rax = a fresh heap str of its decimal digits.
        e("__uint_to_str:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tsubq $48, %rsp")
        e("\tmovq %rdi, %rax")
        # write digits backwards into the scratch region *below* the saved
        # registers (rbp-8 = rbx, rbp-16 = r12), starting at rbp-17.
        e("\tleaq -17(%rbp), %rbx")
        e("\tmovq $10, %rcx")
        e("\ttestq %rax, %rax")
        e("\tjnz .Lu2s_loop")
        e("\tmovb $48, (%rbx)")         # '0'
        e("\tdecq %rbx")
        e("\tjmp .Lu2s_done")
        e(".Lu2s_loop:")
        e("\ttestq %rax, %rax")
        e("\tjz .Lu2s_done")
        e("\txorq %rdx, %rdx")
        e("\tdivq %rcx")               # rax/10 -> rax, rem -> rdx
        e("\taddb $48, %dl")
        e("\tmovb %dl, (%rbx)")
        e("\tdecq %rbx")
        e("\tjmp .Lu2s_loop")
        e(".Lu2s_done:")
        e("\tincq %rbx")               # rbx -> first (most significant) digit
        e("\tleaq -16(%rbp), %r12")     # one past the last digit (rbp-17 + 1)
        e("\tsubq %rbx, %r12")          # length = (rbp-16) - rbx
        e("\tleaq 8(%r12), %rdi")       # value size = 8 + length
        e("\tcall __alloc")            # rax = cell
        e("\tmovq %r12, (%rax)")        # length
        e("\tleaq 8(%rax), %rdi")       # dst
        e("\tmovq %rbx, %rsi")          # src = first digit
        e("\tmovq %r12, %rcx")
        e("\tcld")
        e("\tpushq %rax")              # preserve cell across rep movsb
        e("\trep movsb")
        e("\tpopq %rax")
        e("\taddq $48, %rsp")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tleave")
        e("\tret")
        e("")
        # __int_to_str: rdi = signed value -> rax = decimal str (with '-' if < 0).
        e("__int_to_str:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\txorq %rbx, %rbx")
        e("\ttestq %rdi, %rdi")
        e("\tjns .Li2s_go")
        e("\tmovq $1, %rbx")            # remember the sign
        e("\tnegq %rdi")
        e(".Li2s_go:")
        e("\tcall __uint_to_str")      # rax = digits of the magnitude
        e("\ttestq %rbx, %rbx")
        e("\tjz .Li2s_done")
        e("\tmovq %rax, %rsi")          # magnitude
        e("\tleaq .Lstr_minus(%rip), %rdi")
        e("\tcall __str_concat")       # '-' + magnitude
        e(".Li2s_done:")
        e("\tpopq %rbx")
        e("\tleave")
        e("\tret")
        e("")
        # __bool_to_str: rdi != 0 -> ptr to the static "true"/"false" str cell.
        e("__bool_to_str:")
        e("\ttestq %rdi, %rdi")
        e("\tjz .Lb2s_false")
        e("\tleaq .Lstr_true(%rip), %rax")
        e("\tret")
        e(".Lb2s_false:")
        e("\tleaq .Lstr_false(%rip), %rax")
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
        self._loops = []   # (continue_label, break_label, drop_scope_depth)
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
                tgt = stmt.target
                if (isinstance(tgt, ast.Index)
                        and isinstance(tgt.target.resolved_type, MapType)):
                    cursor[0] += 8       # scratch for the map lvalue holder address
                    self._locals[f"mutholder:{id(stmt)}"] = -cursor[0]
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
                if stmt.iterable is not None:
                    visit_expr(stmt.iterable)
                    cursor[0] += 8
                    self._locals[f"loopvar:{id(stmt)}"] = -cursor[0]
                    cursor[0] += 8
                    self._locals[f"listptr:{id(stmt)}"] = -cursor[0]
                    cursor[0] += 8
                    self._locals[f"listidx:{id(stmt)}"] = -cursor[0]
                else:
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
            elif isinstance(expr, ast.Cast):
                visit_expr(expr.operand)
            elif isinstance(expr, ast.Binary):
                visit_expr(expr.left)
                visit_expr(expr.right)
            elif isinstance(expr, ast.Call):
                for a in expr.args:
                    visit_expr(a)
                rt = expr.resolved_type
                if _is_aggregate(rt) or self._owns_heap(rt):
                    alloc(expr, self._size(rt))
                if (isinstance(expr.callee, ast.Name)
                        and expr.callee.ident in ("push", "remove",
                                                  "append", "append_byte")):
                    cursor[0] += 8       # scratch to hold the lvalue holder address
                    self._locals[f"mutholder:{id(expr)}"] = -cursor[0]
            elif isinstance(expr, ast.FieldAccess):
                if getattr(expr, "enum_ctor", None) is not None:
                    alloc(expr, self._size(expr.resolved_type))  # no-payload variant
                else:
                    visit_expr(expr.target)
            elif isinstance(expr, ast.TupleIndex):
                visit_expr(expr.target)
            elif isinstance(expr, ast.Index):
                visit_expr(expr.target)
                visit_expr(expr.index)
            elif isinstance(expr, ast.ListLit):
                for e in expr.elems:
                    visit_expr(e)
                alloc(expr, 8)  # frame temp holding the cell pointer
            elif isinstance(expr, ast.MapLit):
                for k, v in expr.entries:
                    visit_expr(k)
                    visit_expr(v)
                alloc(expr, 8)  # frame temp holding the cell pointer
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
                if self._owns_heap(t):                # list pointer: new reference
                    self._retain("rbp", off, t)
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
            self._loops.append((start, end, len(self._drop_scopes)))
            self._gen_block(stmt.body)
            self._loops.pop()
            self._emit(f"jmp {start}")
            self._emit(f"{end}:")

        elif isinstance(stmt, ast.For):
            self._gen_for(stmt)

        elif isinstance(stmt, ast.Break):
            cont, end, depth = self._loops[-1]
            self._emit_loop_exit_drops(depth)
            self._emit(f"jmp {end}")

        elif isinstance(stmt, ast.Continue):
            cont, end, depth = self._loops[-1]
            self._emit_loop_exit_drops(depth)
            self._emit(f"jmp {cont}")

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
                if self._owns_heap(self._ret_type):   # list result escapes: retain
                    self._emit("incq -8(%rax)")
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
        if isinstance(stmt.target, ast.Index):
            if isinstance(stmt.target.target.resolved_type, MapType):
                self._gen_map_set(stmt)           # m[k] = v (insert/update, CoW)
                return
            self._mut_elem_addr(stmt.target)      # rax = &element (CoW, bounds-checked)
            self._emit("pushq %rax")
            self._store_into_elem(stmt.value, t, drop_old=True)
            self._drop_expr_temps(stmt.value)
            return
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
        elif self._owns_heap(t):  # reassigning a list variable (scalar pointer)
            kind, off, _ = self._lookup(stmt.target.ident)
            self._eval(stmt.value)                # new cell pointer -> rax
            self._emit("pushq %rax")
            self._emit("incq -8(%rax)")           # the variable takes a reference
            self._drop_value("rbp", off, t)       # release the old list
            self._emit("popq %rax")
            self._emit(f"movq %rax, {off}(%rbp)")
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
        if stmt.iterable is None:
            self._gen_for_range(stmt)
        elif isinstance(stmt.iterable.resolved_type, MapType):
            self._gen_for_map(stmt)
        else:
            self._gen_for_list(stmt)

    def _gen_for_map(self, stmt: ast.For) -> None:
        """`for k in m`: iterate the map's occupied keys (unspecified order). The
        loop variable borrows a non-owning primitive key; the map is retained for
        the loop's duration."""
        mt = stmt.iterable.resolved_type        # MapType
        ss = self._map_slot_size(mt)
        lv = self._locals[f"loopvar:{id(stmt)}"]
        mp = self._locals[f"listptr:{id(stmt)}"]
        si = self._locals[f"listidx:{id(stmt)}"]

        self._eval(stmt.iterable)               # map cell -> rax
        self._emit(f"movq %rax, {mp}(%rbp)")
        self._retain("rbp", mp, mt)             # hold a reference for the loop
        self._drop_expr_temps(stmt.iterable)
        self._emit(f"movq $0, {si}(%rbp)")      # slot index

        start, cont, after = self._label(), self._label(), self._label()
        self._emit(f"{start}:")
        self._emit(f"movq {mp}(%rbp), %rcx")    # cell
        self._emit(f"movq {si}(%rbp), %rax")    # i
        self._emit("cmpq 8(%rcx), %rax")        # i vs cap
        self._emit(f"jae {after}")
        self._emit(f"imulq ${ss}, %rax")
        self._emit("leaq 16(%rcx,%rax), %rdx")  # &slot
        self._emit("movq (%rdx), %rax")         # state
        self._emit("cmpq $1, %rax")
        self._emit(f"jne {cont}")               # empty/tombstone: skip
        self._emit("movq 8(%rdx), %rax")        # key
        self._emit(f"movq %rax, {lv}(%rbp)")    # bind loop var (borrowed)

        self._scopes.append({stmt.var_name: ("local", lv, mt.key)})
        self._drop_scopes.append([])            # loop var is a non-owning key
        self._loops.append((cont, after, len(self._drop_scopes) - 1))
        for s in stmt.body.statements:
            self._gen_stmt(s)
        self._loops.pop()
        for slot, t in reversed(self._drop_scopes[-1]):
            self._drop_value("rbp", slot, t)
        self._drop_scopes.pop()
        self._scopes.pop()

        self._emit(f"{cont}:")
        self._emit(f"movq {si}(%rbp), %rax")
        self._emit("incq %rax")
        self._emit(f"movq %rax, {si}(%rbp)")
        self._emit(f"jmp {start}")
        self._emit(f"{after}:")
        self._drop_value("rbp", mp, mt)         # release the loop reference

    def _gen_for_list(self, stmt: ast.For) -> None:
        lt = stmt.iterable.resolved_type        # ListType
        elem_t = lt.elem
        stride = self._stored_size(elem_t)
        lv = self._locals[f"loopvar:{id(stmt)}"]
        lp = self._locals[f"listptr:{id(stmt)}"]
        li = self._locals[f"listidx:{id(stmt)}"]

        self._eval(stmt.iterable)               # cell pointer -> rax
        self._emit(f"movq %rax, {lp}(%rbp)")
        self._retain("rbp", lp, lt)             # hold a reference for the loop
        self._drop_expr_temps(stmt.iterable)    # release a literal/temp iterable
        self._emit(f"movq $0, {li}(%rbp)")

        start, cont, after = self._label(), self._label(), self._label()
        self._emit(f"{start}:")
        self._emit(f"movq {lp}(%rbp), %rcx")    # cell
        self._emit(f"movq {li}(%rbp), %rax")    # i
        self._emit("cmpq (%rcx), %rax")         # i vs len
        self._emit(f"jae {after}")
        self._emit(f"imulq ${stride}, %rax")
        self._emit("leaq 16(%rcx,%rax), %rdx")  # &elem[i]
        if _is_aggregate(elem_t) and not self._is_boxed(elem_t):
            self._emit(f"movq %rdx, {lv}(%rbp)")    # borrow: slot holds the address
            kind = "param"
        else:                                       # scalar/list pointer or boxed enum
            self._emit("movq (%rdx), %rdx")
            self._emit(f"movq %rdx, {lv}(%rbp)")
            kind = "param" if self._is_boxed(elem_t) else "local"

        self._scopes.append({stmt.var_name: (kind, lv, elem_t)})
        self._drop_scopes.append([])            # loop var is borrowed: no owners
        self._loops.append((cont, after, len(self._drop_scopes) - 1))
        for s in stmt.body.statements:
            self._gen_stmt(s)
        self._loops.pop()
        for slot, t in reversed(self._drop_scopes[-1]):
            self._drop_value("rbp", slot, t)
        self._drop_scopes.pop()
        self._scopes.pop()

        self._emit(f"{cont}:")
        self._emit(f"movq {li}(%rbp), %rax")
        self._emit("incq %rax")
        self._emit(f"movq %rax, {li}(%rbp)")
        self._emit(f"jmp {start}")
        self._emit(f"{after}:")
        self._drop_value("rbp", lp, lt)         # release the loop reference

    def _gen_for_range(self, stmt: ast.For) -> None:
        loop_t = stmt.start.resolved_type
        lv = self._loopvar_off(stmt)
        fe = self._forend_off(stmt)
        self._eval(stmt.start)
        self._emit(f"movq %rax, {lv}(%rbp)")
        self._eval(stmt.end)
        self._emit(f"movq %rax, {fe}(%rbp)")

        start, cont, end = self._label(), self._label(), self._label()
        self._emit(f"{start}:")
        self._emit(f"movq {lv}(%rbp), %rax")
        self._emit(f"movq {fe}(%rbp), %rcx")
        self._emit("cmpq %rcx, %rax")
        stop = "jge" if loop_t.signed else "jae"
        self._emit(f"{stop} {end}")

        self._scopes.append({stmt.var_name: ("local", lv, loop_t)})
        self._drop_scopes.append([])
        # `continue` lands on the increment (after this scope's drops); `break`
        # lands on the exit. Both first release any heap owners they jump past.
        self._loops.append((cont, end, len(self._drop_scopes) - 1))
        for s in stmt.body.statements:
            self._gen_stmt(s)
        self._loops.pop()
        for slot, t in reversed(self._drop_scopes[-1]):  # release per iteration
            self._drop_value("rbp", slot, t)
        self._drop_scopes.pop()
        self._scopes.pop()

        self._emit(f"{cont}:")
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
        elif isinstance(expr, ast.Index):
            self._index_addr(expr)               # &elem -> rax
            if self._is_boxed(expr.resolved_type):
                self._emit("movq (%rax), %rax")   # boxed element: deref to the cell
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

    def _gen_list_lit(self, expr: ast.ListLit) -> None:
        """Allocate a list cell `[len][cap][elems...]` (rc=1) and fill it; the
        pointer is left in the expression's frame temp slot."""
        slot = self._locals[id(expr)]
        et = expr.resolved_type.elem
        n = len(expr.elems)
        stride = self._stored_size(et)
        self._emit(f"movq ${16 + n * stride}, %rdi")
        self._emit("call __alloc")
        self._emit(f"movq %rax, {slot}(%rbp)")
        self._emit(f"movq ${n}, (%rax)")     # length
        self._emit(f"movq ${n}, 8(%rax)")    # capacity
        for i, elem in enumerate(expr.elems):
            self._store_list_elem(elem, slot, 16 + i * stride, et)

    def _store_list_elem(self, value: ast.Expr, cell_slot: int, off: int,
                         mt: Type) -> None:
        """Store `value` into a list cell element at `off`, taking ownership of any
        heap references it brings in (mirrors `_store_member`, but the destination
        base pointer is reloaded from `cell_slot` since evaluating `value` may
        allocate/clobber)."""
        if self._is_boxed(mt):
            self._box(value, mt)                       # rax = fresh heap copy (rc=1)
            self._emit(f"movq {cell_slot}(%rbp), %rcx")
            self._emit(f"movq %rax, {off}(%rcx)")
        elif _is_aggregate(mt):
            self._addr_of_aggregate(value)             # src -> rax
            self._emit("movq %rax, %rsi")
            self._emit(f"movq {cell_slot}(%rbp), %rdi")
            self._emit(f"addq ${off}, %rdi")
            self._emit_copy(self._size(mt))
            self._emit(f"movq {cell_slot}(%rbp), %r8")
            self._retain("r8", off, mt)
        else:                                          # scalar or list pointer
            self._eval(value)
            self._emit(f"movq {cell_slot}(%rbp), %rcx")
            self._emit(f"movq %rax, {off}(%rcx)")
            if self._owns_heap(mt):                    # list element: new reference
                self._emit(f"movq {cell_slot}(%rbp), %r8")
                self._retain("r8", off, mt)

    def _gen_map_lit(self, expr: ast.MapLit) -> None:
        """Allocate a map cell (rc=1) sized so the literal's entries stay under
        the 0.75 load factor, then insert each entry; the pointer is left in the
        expression's frame temp slot."""
        slot = self._locals[id(expr)]
        mt = expr.resolved_type
        vt = mt.value
        n = len(expr.entries)
        cap = 8
        while n * 4 >= cap * 3:                  # keep final load factor < 0.75
            cap *= 2
        self._emit(f"movq ${cap}, %rdi")
        self._emit(f"call {self._map_new_name(mt)}")
        self._emit(f"movq %rax, {slot}(%rbp)")
        for key, value in expr.entries:
            self._emit(f"movq {slot}(%rbp), %rax")
            self._emit("pushq %rax")             # cell
            self._eval(key)                      # key -> rax
            self._emit("movq %rax, %rsi")
            self._emit("popq %rdi")              # cell
            self._emit(f"call {self._map_put_name(mt)}")  # rax=&value, rdx=found
            self._emit("pushq %rdx")             # found
            self._emit("pushq %rax")             # &value
            self._store_map_value(value, vt)

    def _store_map_value(self, value: ast.Expr, vt: Type) -> None:
        """Store `value` into the value slot whose address is on the stack top,
        with the `found` flag pushed just below it. When `found`, the previous
        value is released first; heap references the new value brings in are
        retained (mirrors `_store_into_elem`, but the drop is conditional)."""
        if self._is_boxed(vt):
            self._box(value, vt)                 # rax = fresh heap copy (rc=1)
            self._emit("popq %rcx")              # &value
            self._emit("popq %rdx")              # found
            skip = self._label()
            self._emit("testq %rdx, %rdx")
            self._emit(f"jz {skip}")
            self._emit("pushq %rax")
            self._emit("pushq %rcx")
            self._emit("movq (%rcx), %rdi")
            self._emit(f"call __dropb_{vt.name}")
            self._emit("popq %rcx")
            self._emit("popq %rax")
            self._emit(f"{skip}:")
            self._emit("movq %rax, (%rcx)")
        elif _is_aggregate(vt):
            self._addr_of_aggregate(value)       # rax = src
            self._emit("popq %rcx")              # dest = &value
            self._emit("popq %rdx")              # found
            skip = self._label()
            self._emit("testq %rdx, %rdx")
            self._emit(f"jz {skip}")
            self._emit("pushq %rax")             # save src
            self._emit("pushq %rcx")             # save dest
            self._walk_member("rcx", 0, vt, self._drop_box)
            self._emit("popq %rcx")
            self._emit("popq %rax")
            self._emit(f"{skip}:")
            self._emit("movq %rax, %rsi")        # src
            self._emit("pushq %rcx")
            self._emit("movq %rcx, %rdi")        # dest
            self._emit_copy(self._size(vt))
            self._emit("popq %rcx")
            self._retain("rcx", 0, vt)
        else:                                    # scalar or list/map pointer
            self._eval(value)                    # rax = new value
            self._emit("popq %rcx")              # &value
            self._emit("popq %rdx")              # found
            if self._owns_heap(vt):
                self._emit("incq -8(%rax)")      # store copies a reference
                skip = self._label()
                self._emit("testq %rdx, %rdx")
                self._emit(f"jz {skip}")
                self._emit("pushq %rax")
                self._emit("pushq %rcx")
                self._emit("movq (%rcx), %rdi")
                self._emit(f"call {self._map_drop_name(vt) if isinstance(vt, MapType) else self._list_drop_name(vt)}")
                self._emit("popq %rcx")
                self._emit("popq %rax")
                self._emit(f"{skip}:")
            self._emit("movq %rax, (%rcx)")

    def _map_find_addr(self, expr: ast.Index) -> None:
        """Leave the address of the value for `m[key]` in %rax, trapping when the
        key is absent (the read form; `get` is the safe alternative)."""
        mt = expr.target.resolved_type
        self._eval(expr.target)              # cell -> rax
        self._emit("pushq %rax")
        self._eval(expr.index)               # key -> rax
        self._emit("movq %rax, %rsi")
        self._emit("popq %rdi")              # cell
        self._emit(f"call {self._map_find_name(mt)}")
        self._emit("testq %rax, %rax")
        self._emit("jz __trap")              # key absent
        self._emit("addq $16, %rax")         # &value (skip state + key)

    def _gen_str_index(self, expr: ast.Index) -> None:
        """Leave the byte `s[i]` (zero-extended to a `uint8`) in %rax. A string is
        a pointer to a `[len:8][bytes…]` blob; the index is bounds-checked and
        traps on out-of-bounds (D40)."""
        self._eval(expr.target)              # str pointer -> rax
        self._emit("pushq %rax")
        self._eval(expr.index)               # index -> rax
        self._emit("popq %rcx")              # str pointer
        self._emit("movq (%rcx), %rdx")      # byte length (offset 0)
        self._emit("cmpq %rdx, %rax")
        self._emit("jae __trap")             # i < 0 (huge unsigned) or i >= len
        self._emit("movzbq 8(%rcx,%rax), %rax")

    def _index_addr(self, expr: ast.Index) -> None:
        """Leave the *address* of `target[index]` in %rax: a list element (trapping
        on out-of-bounds) or a map value (trapping on an absent key)."""
        if isinstance(expr.target.resolved_type, MapType):
            self._map_find_addr(expr)
            return
        et = expr.resolved_type
        stride = self._stored_size(et)
        self._eval(expr.target)              # list cell pointer -> rax
        self._emit("pushq %rax")
        self._eval(expr.index)               # index -> rax
        self._emit("popq %rcx")              # cell pointer
        self._emit("movq (%rcx), %rdx")      # length
        self._emit("cmpq %rdx, %rax")
        self._emit("jae __trap")             # i < 0 (huge unsigned) or i >= len
        self._emit(f"imulq ${stride}, %rax")
        self._emit("leaq 16(%rcx,%rax), %rax")

    # -- mutable list lvalues & copy-on-write --------------------------------

    def _cow_unique(self, t: Type) -> None:
        """In: %rax = address of the slot holding a list/map pointer. Ensure the
        cell is uniquely owned (clone it if its refcount > 1, storing the clone
        back into the slot). Out: %rax = the now-unique cell pointer."""
        self._emit("movq %rax, %rcx")           # rcx = &holder
        self._emit("movq (%rcx), %rdi")         # current cell pointer
        skip = self._label()
        self._emit("cmpq $1, -8(%rdi)")
        self._emit(f"jbe {skip}")               # rc <= 1: already unique
        self._emit("pushq %rcx")
        self._emit(f"call {self._heap_clone_name(t)}")  # rax = clone, old decremented
        self._emit("popq %rcx")
        self._emit("movq %rax, (%rcx)")         # store the clone back
        self._emit("movq %rax, %rdi")
        self._emit(f"{skip}:")
        self._emit("movq %rdi, %rax")           # unique cell pointer

    def _mut_container_cell(self, expr: ast.Expr) -> None:
        """Leave the uniquely-owned cell pointer of list lvalue `expr` in %rax,
        cloning shared cells along the path so the write is private (D38)."""
        self._mut_addr_of_list_holder(expr)     # &holder -> rax
        self._cow_unique(expr.resolved_type)    # unique cell -> rax

    def _mut_elem_addr(self, expr: ast.Index) -> None:
        """Leave the address of element `target[index]` in %rax, after making the
        container list unique. Traps on an out-of-bounds index."""
        stride = self._stored_size(expr.resolved_type)
        self._mut_container_cell(expr.target)   # unique cell -> rax
        self._emit("pushq %rax")
        self._eval(expr.index)                  # index -> rax
        self._emit("popq %rcx")                 # cell
        self._emit("movq (%rcx), %rdx")         # len
        self._emit("cmpq %rdx, %rax")
        self._emit("jae __trap")
        self._emit(f"imulq ${stride}, %rax")
        self._emit("leaq 16(%rcx,%rax), %rax")

    def _mut_map_value_addr(self, expr: ast.Index) -> None:
        """Leave the address of the value for map lvalue `m[key]` in %rax, after
        making the container map unique (CoW). Traps when the key is absent (this
        is the read-for-mutation path, e.g. `m[k].field = v`)."""
        mt = expr.target.resolved_type
        self._mut_container_cell(expr.target)   # unique map cell -> rax
        self._emit("pushq %rax")
        self._eval(expr.index)                  # key -> rax
        self._emit("movq %rax, %rsi")
        self._emit("popq %rdi")                 # cell
        self._emit(f"call {self._map_find_name(mt)}")
        self._emit("testq %rax, %rax")
        self._emit("jz __trap")
        self._emit("addq $16, %rax")            # &value

    def _mut_index_addr(self, expr: ast.Index) -> None:
        """Dispatch an `Index` mutable lvalue to the list-element or map-value
        address routine."""
        if isinstance(expr.target.resolved_type, MapType):
            self._mut_map_value_addr(expr)
        else:
            self._mut_elem_addr(expr)

    def _mut_addr_of_list_holder(self, expr: ast.Expr) -> None:
        """Leave in %rax the address of the slot that holds list/map lvalue
        `expr`'s cell pointer (so a CoW clone can be written back)."""
        if isinstance(expr, ast.Name):
            _, off, _ = self._lookup(expr.ident)
            self._emit(f"leaq {off}(%rbp), %rax")
        elif isinstance(expr, ast.FieldAccess):
            self._mut_addr_of_struct(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            if foff:
                self._emit(f"addq ${foff}, %rax")
        elif isinstance(expr, ast.Index):
            self._mut_index_addr(expr)          # the element/value slot holds the ptr
        else:  # pragma: no cover - checker guarantees a valid lvalue
            raise ValueError("invalid list lvalue")

    def _mut_addr_of_struct(self, expr: ast.Expr) -> None:
        """Leave the address of inline-struct lvalue `expr` in %rax (CoW-ing any
        list/map cell on the path)."""
        if isinstance(expr, ast.Name):
            _, off, _ = self._lookup(expr.ident)
            self._emit(f"leaq {off}(%rbp), %rax")
        elif isinstance(expr, ast.FieldAccess):
            self._mut_addr_of_struct(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            if foff:
                self._emit(f"addq ${foff}, %rax")
        elif isinstance(expr, ast.Index):
            self._mut_index_addr(expr)
        else:  # pragma: no cover
            raise ValueError("invalid struct lvalue")

    def _store_into_elem(self, value: ast.Expr, et: Type, drop_old: bool) -> None:
        """Store `value` into the element whose address is on the stack top
        (consumed), taking ownership of heap references it brings in and, when
        `drop_old`, releasing whatever the slot held before."""
        if self._is_boxed(et):
            self._box(value, et)                  # rax = fresh heap copy (rc=1)
            self._emit("popq %rcx")               # &elem
            if drop_old:
                self._emit("pushq %rax")
                self._emit("pushq %rcx")
                self._emit("movq (%rcx), %rdi")
                self._emit(f"call __dropb_{et.name}")
                self._emit("popq %rcx")
                self._emit("popq %rax")
            self._emit("movq %rax, (%rcx)")
        elif _is_aggregate(et):
            self._addr_of_aggregate(value)        # rax = src
            self._emit("popq %rcx")               # dest = &elem
            self._emit("pushq %rcx")              # keep dest
            if drop_old:
                self._emit("pushq %rax")          # save src
                self._walk_member("rcx", 0, et, self._drop_box)
                self._emit("popq %rax")           # src
            self._emit("movq %rax, %rsi")
            self._emit("movq (%rsp), %rdi")       # dest (peek)
            self._emit_copy(self._size(et))
            self._emit("popq %rcx")               # dest
            self._retain("rcx", 0, et)
        elif self._owns_heap(et):                 # list element (scalar pointer)
            self._eval(value)                     # rax = new cell pointer
            self._emit("popq %rcx")               # &elem
            self._emit("incq -8(%rax)")           # store copies a reference
            if drop_old:
                self._emit("pushq %rax")
                self._emit("pushq %rcx")
                self._emit("movq (%rcx), %rdi")
                self._emit(f"call {self._list_drop_name(et)}")
                self._emit("popq %rcx")
                self._emit("popq %rax")
            self._emit("movq %rax, (%rcx)")
        else:                                     # plain scalar (int/bool/str)
            self._eval(value)
            self._emit("popq %rcx")
            self._emit("movq %rax, (%rcx)")

    def _gen_push(self, expr: ast.Call) -> None:
        arg0 = expr.args[0]
        lt = arg0.resolved_type
        et = lt.elem
        stride = self._stored_size(et)
        holder = self._locals[f"mutholder:{id(expr)}"]
        self._mut_addr_of_list_holder(arg0)       # rax = &holder
        self._emit(f"movq %rax, {holder}(%rbp)")
        self._cow_unique(lt)                      # rax = unique cell (rc==1)
        have = self._label()
        self._emit("movq (%rax), %rdx")           # len
        self._emit("movq 8(%rax), %rcx")          # cap
        self._emit("cmpq %rcx, %rdx")
        self._emit(f"jb {have}")                  # len < cap: room to append
        self._emit("movq %rax, %rdi")
        self._emit(f"call {self._list_grow_name(lt)}")   # rax = larger cell
        self._emit(f"movq {holder}(%rbp), %rcx")
        self._emit("movq %rax, (%rcx)")           # publish the grown cell
        self._emit(f"{have}:")
        self._emit("movq (%rax), %rdx")           # current length (append index)
        self._emit("leaq 1(%rdx), %rcx")
        self._emit("movq %rcx, (%rax)")           # length += 1
        self._emit(f"imulq ${stride}, %rdx")
        self._emit("leaq 16(%rax,%rdx), %rax")    # &elem (the fresh slot)
        self._emit("pushq %rax")
        self._store_into_elem(expr.args[1], et, drop_old=False)
        self._drop_expr_temps(expr.args[1])

    def _gen_sb_append_byte(self, expr: ast.Call) -> None:
        """`append_byte(sb, b)`: make `sb` unique (CoW), grow if full, store one
        packed byte and bump the length."""
        arg0 = expr.args[0]
        holder = self._locals[f"mutholder:{id(expr)}"]
        self._mut_addr_of_list_holder(arg0)       # rax = &holder
        self._emit(f"movq %rax, {holder}(%rbp)")
        self._cow_unique(arg0.resolved_type)      # rax = unique cell (rc==1)
        have = self._label()
        self._emit("movq (%rax), %rdx")           # len
        self._emit("movq 8(%rax), %rcx")          # cap
        self._emit("cmpq %rcx, %rdx")
        self._emit(f"jb {have}")                  # len < cap: room to append
        self._emit("movq %rax, %rdi")
        self._emit("call __sb_grow")
        self._emit(f"movq {holder}(%rbp), %rcx")
        self._emit("movq %rax, (%rcx)")           # publish the grown cell
        self._emit(f"{have}:")
        self._emit("movq (%rax), %rdx")           # current length (append index)
        self._emit("leaq 1(%rdx), %rcx")
        self._emit("movq %rcx, (%rax)")           # length += 1
        self._emit("leaq 16(%rax,%rdx), %rax")    # &byte (packed, stride 1)
        self._emit("pushq %rax")
        self._eval(expr.args[1])                  # byte value -> rax
        self._emit("popq %rcx")                   # &byte
        self._emit("movb %al, (%rcx)")
        self._drop_expr_temps(expr.args[1])

    def _gen_sb_append(self, expr: ast.Call) -> None:
        """`append(sb, s)`: make `sb` unique (CoW), then append the string's bytes
        (growing as needed), publishing any reallocated cell."""
        arg0 = expr.args[0]
        holder = self._locals[f"mutholder:{id(expr)}"]
        self._mut_addr_of_list_holder(arg0)       # rax = &holder
        self._emit(f"movq %rax, {holder}(%rbp)")
        self._cow_unique(arg0.resolved_type)      # rax = unique cell (rc==1)
        self._emit("pushq %rax")
        self._eval(expr.args[1])                  # str ptr -> rax
        self._emit("movq %rax, %rsi")
        self._emit("popq %rdi")                   # builder cell
        self._emit("call __sb_extend")            # rax = (maybe reallocated) cell
        self._emit(f"movq {holder}(%rbp), %rcx")
        self._emit("movq %rax, (%rcx)")           # publish the cell
        self._drop_expr_temps(expr.args[1])

    def _gen_pop(self, expr: ast.Call) -> None:
        arg0 = expr.args[0]
        lt = arg0.resolved_type
        et = lt.elem
        stride = self._stored_size(et)
        self._mut_container_cell(arg0)            # rax = unique cell
        self._emit("movq (%rax), %rdx")           # len
        self._emit("testq %rdx, %rdx")
        self._emit("jz __trap")                   # pop from an empty list traps
        self._emit("decq %rdx")
        self._emit("movq %rdx, (%rax)")           # len -= 1
        self._emit(f"imulq ${stride}, %rdx")
        self._emit("leaq 16(%rax,%rdx), %rax")    # &elem (removed last element)
        if _is_aggregate(et):                     # copy out (ownership transfers)
            slot = self._locals[id(expr)]
            self._emit("movq %rax, %rsi")
            self._emit(f"leaq {slot}(%rbp), %rdi")
            self._emit_copy(self._size(et))
        else:
            self._emit("movq (%rax), %rax")       # scalar / list pointer (transferred)

    def _gen_contains(self, expr: ast.Call) -> None:
        """`contains(m, key) -> bool`: leave 1/0 in %rax."""
        mt = expr.args[0].resolved_type
        self._eval(expr.args[0])              # map cell -> rax
        self._emit("pushq %rax")
        self._eval(expr.args[1])              # key -> rax
        self._emit("movq %rax, %rsi")
        self._emit("popq %rdi")               # map cell
        self._emit(f"call {self._map_find_name(mt)}")
        self._emit("testq %rax, %rax")
        self._emit("setne %al")
        self._emit("movzbq %al, %rax")

    def _gen_remove(self, expr: ast.Call) -> None:
        """`remove(m, key)`: make the map unique (CoW), then rebuild it without
        `key` (rebuild deletion), publishing the fresh cell."""
        arg0 = expr.args[0]
        mt = arg0.resolved_type
        holder = self._locals[f"mutholder:{id(expr)}"]
        self._mut_addr_of_list_holder(arg0)   # &holder -> rax
        self._emit(f"movq %rax, {holder}(%rbp)")
        self._cow_unique(mt)                  # unique cell -> rax (rc==1)
        self._emit("pushq %rax")              # save cell
        self._eval(expr.args[1])              # key -> rax
        self._emit("movq %rax, %rsi")
        self._emit("popq %rdi")               # cell
        self._emit(f"call {self._map_remove_name(mt)}")  # rax = rebuilt cell
        self._emit(f"movq {holder}(%rbp), %rcx")
        self._emit("movq %rax, (%rcx)")       # publish the rebuilt cell
        self._drop_expr_temps(expr.args[1])

    def _gen_map_set(self, stmt: ast.Assign) -> None:
        """`m[key] = value` (insert or update): make the map unique (CoW), grow it
        if inserting would exceed the load factor, then store the value, releasing
        the previous one if the key already existed."""
        target = stmt.target
        mt = target.target.resolved_type
        vt = mt.value
        holder = self._locals[f"mutholder:{id(stmt)}"]
        self._mut_addr_of_list_holder(target.target)  # rax = &holder
        self._emit(f"movq %rax, {holder}(%rbp)")
        self._cow_unique(mt)                          # rax = unique cell (rc==1)
        have = self._label()
        self._emit("movq (%rax), %rcx")               # len
        self._emit("incq %rcx")                       # len + 1
        self._emit("imulq $4, %rcx")                  # (len+1) * 4
        self._emit("movq 8(%rax), %rdx")              # cap
        self._emit("imulq $3, %rdx")                  # cap * 3
        self._emit("cmpq %rdx, %rcx")
        self._emit(f"jb {have}")                      # (len+1)*4 < cap*3: room
        self._emit("movq %rax, %rdi")
        self._emit(f"call {self._map_grow_name(mt)}")  # rax = larger cell
        self._emit(f"movq {holder}(%rbp), %rcx")
        self._emit("movq %rax, (%rcx)")               # publish the grown cell
        self._emit(f"{have}:")
        self._emit("pushq %rax")                      # cell
        self._eval(target.index)                      # key -> rax
        self._emit("movq %rax, %rsi")
        self._emit("popq %rdi")                       # cell
        self._emit(f"call {self._map_put_name(mt)}")  # rax=&value, rdx=found
        self._emit("pushq %rdx")                      # found
        self._emit("pushq %rax")                      # &value
        self._store_map_value(stmt.value, vt)
        self._drop_expr_temps(target.index)
        self._drop_expr_temps(stmt.value)

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
            if self._owns_heap(t):  # a list pointer: storing copies a reference
                self._retain("rbp", off, t)

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

    def _inc_box(self, ptr_off: int, base: str, t: Type) -> None:
        """Retain a heap-pointer leaf (boxed enum or list): just bump its
        refcount. Sharing is shallow — children are not touched."""
        self._emit(f"movq {ptr_off}(%{base}), %rax")
        self._emit("incq -8(%rax)")

    def _drop_box(self, ptr_off: int, base: str, t: Type) -> None:
        """Release a heap-pointer leaf via its type-specific drop routine."""
        self._emit(f"movq {ptr_off}(%{base}), %rdi")
        if isinstance(t, ListType):
            self._emit(f"call {self._list_drop_name(t)}")
        elif isinstance(t, MapType):
            self._emit(f"call {self._map_drop_name(t)}")
        elif isinstance(t, StringBuilderType):
            self._emit("call __sb_drop")
        else:
            self._emit(f"call __dropb_{t.name}")

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
        # Heap-pointer leaves (boxed enum, list, map) hand the action the *type*
        # so it can pick the right routine; inline aggregates recurse.
        if self._is_boxed(ft) or isinstance(ft, (ListType, MapType, StringBuilderType)):
            on_box(off, base, ft)
        elif self._owns_heap(ft):
            self._emit_owned_walk(base, off, ft, on_box)

    def _retain(self, base: str, off: int, t: Type) -> None:
        if isinstance(t, (ListType, MapType, StringBuilderType)):  # cell ptr at off
            self._inc_box(off, base, t)
        elif self._owns_heap(t):
            self._emit_owned_walk(base, off, t, self._inc_box)

    def _drop_value(self, base: str, off: int, t: Type) -> None:
        if isinstance(t, (ListType, MapType, StringBuilderType)):
            self._drop_box(off, base, t)
        elif self._owns_heap(t):
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

    def _emit_loop_exit_drops(self, depth: int) -> None:
        """Drop owners from the innermost scope down to the loop body scope at
        `depth` (inclusive), for a `break`/`continue` that jumps past them."""
        for scope in reversed(self._drop_scopes[depth:]):
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
        if isinstance(expr, (ast.Unary, ast.Cast)):
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
        elif isinstance(expr, ast.Index):
            self._collect_expr_temps(expr.target, out)
            self._collect_expr_temps(expr.index, out)
        elif isinstance(expr, ast.ListLit):
            for e in expr.elems:
                self._collect_expr_temps(e, out)
        elif isinstance(expr, ast.MapLit):
            for k, v in expr.entries:
                self._collect_expr_temps(k, out)
                self._collect_expr_temps(v, out)
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
        """Emit `__dropb_<E>` for each recursive enum and `__drop_list_<T>` for
        each list element type: decrement the cell's refcount and, at zero, drop
        the children it owns and free the cell."""
        collected = self._collect_list_types()
        if "SB" in collected:
            self._emit_string_builder_helpers()
        for mangle, t in collected.items():
            if mangle == "SB":
                continue
            if isinstance(t, MapType):
                self._emit_map_helpers(t)
            else:
                self._emit_list_drop_helper(t)
                self._emit_list_clone_helper(t)
                self._emit_list_grow_helper(t)
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

    def _emit_list_drop_helper(self, t: ListType) -> None:
        """`__drop_list_<elem>`: %rdi = list cell. Decrement the refcount; at zero
        drop each of the `len` elements (if they own heap) and free the cell."""
        et = t.elem
        stride = self._stored_size(et)
        self._emit(f"{self._list_drop_name(t)}:")
        self._emit("decq -8(%rdi)")
        keep = self._label()
        self._emit(f"jnz {keep}")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %rbx")
        self._emit("pushq %r12")
        self._emit("pushq %r13")
        self._emit("pushq %r14")
        self._emit("movq %rdi, %rbx")            # cell
        if self._owns_heap(et):
            self._emit("movq (%rbx), %r12")      # len
            self._emit("xorq %r13, %r13")        # i = 0
            loop, done = self._label(), self._label()
            self._emit(f"{loop}:")
            self._emit("cmpq %r12, %r13")
            self._emit(f"jge {done}")
            self._emit("movq %r13, %rax")
            self._emit(f"imulq ${stride}, %rax")
            self._emit("leaq 16(%rbx,%rax), %r14")   # &elem[i]
            self._walk_member("r14", 0, et, self._drop_box)
            self._emit("incq %r13")
            self._emit(f"jmp {loop}")
            self._emit(f"{done}:")
        self._emit("movq %rbx, %rdi")
        self._emit("popq %r14")
        self._emit("popq %r13")
        self._emit("popq %r12")
        self._emit("popq %rbx")
        self._emit("leave")
        self._emit("jmp __free")
        self._emit(f"{keep}:")
        self._emit("ret")
        self._emit("")

    def _emit_list_clone_helper(self, t: ListType) -> None:
        """`__clone_list_<elem>`: %rdi = shared cell. Allocate an independent copy
        (rc=1), retain each element it now shares, decrement the original's
        refcount, and return the copy in %rax (the copy-on-write clone, D38)."""
        et = t.elem
        stride = self._stored_size(et)
        self._emit(f"{self._list_clone_name(t)}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %rbx")
        self._emit("pushq %r12")
        self._emit("pushq %r13")
        self._emit("pushq %r14")
        self._emit("movq %rdi, %rbx")            # old cell
        self._emit("movq -16(%rbx), %r12")       # value size (bytes)
        self._emit("movq %r12, %rdi")
        self._emit("call __alloc")               # rax = new cell (rc=1)
        self._emit("movq %rax, %r13")            # new cell
        self._emit("movq %rbx, %rsi")
        self._emit("movq %r13, %rdi")
        self._emit("movq %r12, %rcx")
        self._emit("shrq $3, %rcx")
        self._emit("cld")
        self._emit("rep movsq")                  # copy old -> new
        if self._owns_heap(et):
            self._emit("movq (%r13), %r12")      # len
            self._emit("xorq %r14, %r14")        # i = 0
            loop, done = self._label(), self._label()
            self._emit(f"{loop}:")
            self._emit("cmpq %r12, %r14")
            self._emit(f"jge {done}")
            self._emit("movq %r14, %rax")
            self._emit(f"imulq ${stride}, %rax")
            self._emit("leaq 16(%r13,%rax), %rcx")   # &elem[i] in the copy
            self._walk_member("rcx", 0, et, self._inc_box)
            self._emit("incq %r14")
            self._emit(f"jmp {loop}")
            self._emit(f"{done}:")
        self._emit("decq -8(%rbx)")              # original loses this reference
        self._emit("movq %r13, %rax")            # return the copy
        self._emit("popq %r14")
        self._emit("popq %r13")
        self._emit("popq %r12")
        self._emit("popq %rbx")
        self._emit("leave")
        self._emit("ret")
        self._emit("")

    def _emit_list_grow_helper(self, t: ListType) -> None:
        """`__grow_list_<elem>`: %rdi = uniquely-owned, full cell (rc=1). Reallocate
        with *doubled* capacity (min 4) so pushes are amortized O(1) and freed
        cells fall into a few size classes the allocator can reuse; move the
        elements over (ownership transfers), free the old cell, return new cell."""
        et = t.elem
        stride = self._stored_size(et)
        self._emit(f"{self._list_grow_name(t)}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %rbx")
        self._emit("pushq %r12")
        self._emit("pushq %r13")
        self._emit("movq %rdi, %rbx")            # old cell
        self._emit("movq (%rbx), %r12")          # len
        self._emit("movq 8(%rbx), %r13")         # cap
        self._emit("addq %r13, %r13")            # newcap = cap * 2
        nz = self._label()
        self._emit("testq %r13, %r13")
        self._emit(f"jnz {nz}")
        self._emit("movq $4, %r13")              # empty list grows to 4
        self._emit(f"{nz}:")
        self._emit("movq %r13, %rax")            # new size = 16 + newcap*stride
        self._emit(f"imulq ${stride}, %rax")
        self._emit("addq $16, %rax")
        self._emit("movq %rax, %rdi")
        self._emit("call __alloc")               # rax = new cell (rc=1)
        self._emit("movq %r12, %rcx")            # copy 16 + len*stride bytes
        self._emit(f"imulq ${stride}, %rcx")
        self._emit("addq $16, %rcx")
        self._emit("shrq $3, %rcx")
        self._emit("movq %rbx, %rsi")
        self._emit("movq %rax, %rdi")
        self._emit("pushq %rax")                 # save new cell
        self._emit("cld")
        self._emit("rep movsq")
        self._emit("popq %rax")
        self._emit("movq %r13, 8(%rax)")         # capacity = newcap
        self._emit("movq %rax, %r12")            # save new cell
        self._emit("movq %rbx, %rdi")
        self._emit("call __free")                # release the old cell (rc was 1)
        self._emit("movq %r12, %rax")
        self._emit("popq %r13")
        self._emit("popq %r12")
        self._emit("popq %rbx")
        self._emit("leave")
        self._emit("ret")
        self._emit("")

    # -- StringBuilder runtime helpers (D41) ---------------------------------

    def _emit_string_builder_helpers(self) -> None:
        """Emit the `StringBuilder` cell routines, once per program. A builder is
        a refcounted cell `[len:8][cap:8][bytes…]` (the bytes are packed, one per
        byte — unlike list elements, which occupy 8-byte slots)."""
        e = self._emit
        # __sb_new -> rax = an empty builder (len=0, cap=8, rc=1).
        e("__sb_new:")
        e("\tmovq $24, %rdi")              # 16 header + 8 initial capacity
        e("\tcall __alloc")
        e("\tmovq $0, (%rax)")             # len = 0
        e("\tmovq $8, 8(%rax)")            # cap = 8
        e("\tret")
        e("")
        # __sb_drop: rdi = cell. Decrement the refcount; free at zero (the bytes
        # are scalars, so there is nothing else to release).
        e("__sb_drop:")
        e("\tdecq -8(%rdi)")
        keep = self._label()
        e(f"\tjnz {keep}")
        e("\tjmp __free")
        e(f"{keep}:")
        e("\tret")
        e("")
        # __sb_clone: rdi = shared cell -> rax = an independent copy (rc=1); the
        # original loses this reference (copy-on-write, D38).
        e("__sb_clone:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tmovq %rdi, %rbx")             # old cell
        e("\tmovq -16(%rbx), %r12")        # value size (bytes)
        e("\tmovq %r12, %rdi")
        e("\tcall __alloc")               # rax = new cell (rc=1)
        e("\tmovq %rbx, %rsi")
        e("\tmovq %rax, %rdi")
        e("\tmovq %r12, %rcx")
        e("\tcld")
        e("\tpushq %rax")
        e("\trep movsb")                  # copy len+cap+bytes (header untouched)
        e("\tpopq %rax")
        e("\tdecq -8(%rbx)")               # original loses this reference
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tleave")
        e("\tret")
        e("")
        # __sb_grow: rdi = uniquely-owned cell (rc=1) -> rax = a cell with doubled
        # capacity; the live bytes move over and the old cell is freed.
        e("__sb_grow:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tmovq %rdi, %rbx")             # old cell
        e("\tmovq (%rbx), %r12")           # len
        e("\tmovq 8(%rbx), %r13")          # cap
        e("\taddq %r13, %r13")             # newcap = cap * 2
        e("\tleaq 16(%r13), %rdi")         # value size = 16 + newcap
        e("\tcall __alloc")               # rax = new cell (rc=1)
        e("\tpushq %rax")
        e("\tmovq %rbx, %rsi")
        e("\tmovq %rax, %rdi")
        e("\tleaq 16(%r12), %rcx")         # copy 16 header + len live bytes
        e("\tcld")
        e("\trep movsb")
        e("\tpopq %rax")
        e("\tmovq %r13, 8(%rax)")          # capacity = newcap
        e("\tmovq %rax, %r12")             # save new cell
        e("\tmovq %rbx, %rdi")
        e("\tcall __free")                # release the old cell (rc was 1)
        e("\tmovq %r12, %rax")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tleave")
        e("\tret")
        e("")
        # __sb_extend: rdi = unique cell, rsi = str ptr -> rax = the cell (possibly
        # reallocated) with the string's bytes appended; len grows by the string
        # length. Grows repeatedly until the appended bytes fit.
        e("__sb_extend:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tpushq %r14")
        e("\tmovq %rdi, %rbx")             # cell
        e("\tmovq %rsi, %r12")             # str
        e("\tmovq (%r12), %r13")           # slen
        e("\tmovq (%rbx), %r14")           # len
        grow, fit = self._label(), self._label()
        e(f"{grow}:")
        e("\tleaq (%r14,%r13), %rax")      # needed = len + slen
        e("\tcmpq 8(%rbx), %rax")          # needed <= cap?
        e(f"\tjbe {fit}")
        e("\tmovq %rbx, %rdi")
        e("\tcall __sb_grow")             # rax = larger cell
        e("\tmovq %rax, %rbx")
        e(f"\tjmp {grow}")
        e(f"{fit}:")
        e("\tleaq 16(%rbx,%r14), %rdi")    # dst = &bytes[len]
        e("\tleaq 8(%r12), %rsi")          # src = str bytes
        e("\tmovq %r13, %rcx")
        e("\tcld")
        e("\trep movsb")
        e("\tleaq (%r14,%r13), %rax")      # len += slen
        e("\tmovq %rax, (%rbx)")
        e("\tmovq %rbx, %rax")
        e("\tpopq %r14")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tleave")
        e("\tret")
        e("")
        # __sb_build: rdi = builder cell -> rax = a fresh str [len:8][bytes] holding
        # a snapshot of the builder's bytes.
        e("__sb_build:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tmovq %rdi, %rbx")             # builder cell
        e("\tmovq (%rbx), %r12")           # len
        e("\tleaq 8(%r12), %rdi")          # str value size = 8 + len
        e("\tcall __alloc")
        e("\tmovq %r12, (%rax)")           # str length
        e("\tpushq %rax")
        e("\tleaq 8(%rax), %rdi")          # dst = str bytes
        e("\tleaq 16(%rbx), %rsi")         # src = builder bytes
        e("\tmovq %r12, %rcx")
        e("\tcld")
        e("\trep movsb")
        e("\tpopq %rax")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tleave")
        e("\tret")
        e("")

    # -- map runtime helpers -------------------------------------------------

    def _emit_fnv_hash(self, kt: Type) -> None:
        """Hash the key in %rsi with FNV-1a, leaving the 64-bit hash in %rax.
        Clobbers %rcx/%r8/%r9/%r10/%r11; %rsi/%rdi are preserved."""
        self._emit("movabsq $0xcbf29ce484222325, %rax")   # FNV offset basis
        self._emit("movabsq $0x100000001b3, %r8")         # FNV prime
        loop, done = self._label(), self._label()
        if isinstance(kt, StrType):
            self._emit("movq (%rsi), %r10")               # length
            self._emit("leaq 8(%rsi), %r9")               # &bytes
            self._emit(f"{loop}:")
            self._emit("testq %r10, %r10")
            self._emit(f"jz {done}")
            self._emit("movzbq (%r9), %r11")
            self._emit("xorq %r11, %rax")
            self._emit("imulq %r8, %rax")
            self._emit("incq %r9")
            self._emit("decq %r10")
            self._emit(f"jmp {loop}")
            self._emit(f"{done}:")
        else:                                             # int / bool / byte: 8 bytes
            self._emit("movq %rsi, %r9")
            self._emit("movq $8, %r10")
            self._emit(f"{loop}:")
            self._emit("movzbq %r9b, %r11")
            self._emit("xorq %r11, %rax")
            self._emit("imulq %r8, %rax")
            self._emit("shrq $8, %r9")
            self._emit("decq %r10")
            self._emit(f"jnz {loop}")

    def _emit_key_eq(self, kt: Type, found_label: str) -> None:
        """Compare the slot key at 8(%r9) with the search key in %r13; jump to
        `found_label` when equal. Preserves the probe registers (r9/r11-r14)."""
        if isinstance(kt, StrType):
            self._emit("movq 8(%r9), %rdi")               # slot key pointer
            self._emit("movq %r13, %rsi")                 # search key pointer
            self._emit("call __str_eq")                   # rax=1/0 (preserves r9..r14)
            self._emit("testq %rax, %rax")
            self._emit(f"jnz {found_label}")
        else:
            self._emit("movq 8(%r9), %rcx")
            self._emit("cmpq %r13, %rcx")
            self._emit(f"je {found_label}")

    def _emit_map_helpers(self, t: MapType) -> None:
        self._emit_map_new_helper(t)
        self._emit_map_put_helper(t)
        self._emit_map_find_helper(t)
        self._emit_map_clone_helper(t)
        self._emit_map_grow_helper(t)
        self._emit_map_drop_helper(t)
        self._emit_map_keys_helper(t)
        self._emit_map_remove_helper(t)

    def _emit_map_new_helper(self, t: MapType) -> None:
        """`__new_map_<m>`: %rdi = capacity (power of two) -> %rax = a fresh cell
        with zeroed slots, len 0, the given capacity."""
        ss = self._map_slot_size(t)
        self._emit(f"{self._map_new_name(t)}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %rbx")
        self._emit("pushq %r12")
        self._emit("movq %rdi, %rbx")            # cap
        self._emit(f"imulq ${ss}, %rdi")
        self._emit("addq $16, %rdi")
        self._emit("call __alloc")               # rax = cell (rc=1, dirty)
        self._emit("movq %rax, %r12")
        self._emit("movq $0, (%r12)")            # len = 0
        self._emit("movq %rbx, 8(%r12)")         # cap
        self._emit("leaq 16(%r12), %rdi")        # zero the slot area
        self._emit("movq %rbx, %rcx")
        self._emit(f"imulq ${ss // 8}, %rcx")
        self._emit("xorq %rax, %rax")
        self._emit("cld")
        self._emit("rep stosq")
        self._emit("movq %r12, %rax")
        self._emit("popq %r12")
        self._emit("popq %rbx")
        self._emit("leave")
        self._emit("ret")
        self._emit("")

    def _emit_map_put_helper(self, t: MapType) -> None:
        """`__put_map_<m>`: %rdi = cell, %rsi = key -> %rax = &value slot, %rdx = 1
        if the key already existed else 0 (newly inserted, len incremented). A
        free slot is guaranteed by the load factor invariant (< 0.75)."""
        ss = self._map_slot_size(t)
        probe, insert, found, ret = (self._label(), self._label(),
                                     self._label(), self._label())
        self._emit(f"{self._map_put_name(t)}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %r12")
        self._emit("pushq %r13")
        self._emit("pushq %r14")
        self._emit("movq %rdi, %r12")            # cell
        self._emit("movq %rsi, %r13")            # key
        self._emit_fnv_hash(t.key)               # rax = hash
        self._emit("movq 8(%r12), %r14")         # cap
        self._emit("decq %r14")                  # mask = cap - 1
        self._emit("andq %r14, %rax")
        self._emit("movq %rax, %r11")            # idx
        self._emit(f"{probe}:")
        self._emit("movq %r11, %r9")
        self._emit(f"imulq ${ss}, %r9")
        self._emit("leaq 16(%r12,%r9), %r9")     # &slot
        self._emit("movq (%r9), %rcx")           # state
        self._emit("testq %rcx, %rcx")
        self._emit(f"jz {insert}")               # empty: insert here
        self._emit_key_eq(t.key, found)
        self._emit("incq %r11")                  # advance (linear probe)
        self._emit("andq %r14, %r11")
        self._emit(f"jmp {probe}")
        self._emit(f"{insert}:")
        self._emit("movq $1, (%r9)")             # state = occupied
        self._emit("movq %r13, 8(%r9)")          # key
        self._emit("incq (%r12)")                # len += 1
        self._emit("leaq 16(%r9), %rax")         # &value
        self._emit("xorq %rdx, %rdx")            # found = 0
        self._emit(f"jmp {ret}")
        self._emit(f"{found}:")
        self._emit("leaq 16(%r9), %rax")
        self._emit("movq $1, %rdx")              # found = 1
        self._emit(f"{ret}:")
        self._emit("popq %r14")
        self._emit("popq %r13")
        self._emit("popq %r12")
        self._emit("leave")
        self._emit("ret")
        self._emit("")

    def _emit_map_find_helper(self, t: MapType) -> None:
        """`__find_map_<m>`: %rdi = cell, %rsi = key -> %rax = &slot (state word) if
        present else 0. There are no tombstones (`remove` rebuilds), so an empty
        slot terminates the probe."""
        ss = self._map_slot_size(t)
        probe, found, nf, ret = (self._label(), self._label(),
                                 self._label(), self._label())
        self._emit(f"{self._map_find_name(t)}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %r12")
        self._emit("pushq %r13")
        self._emit("pushq %r14")
        self._emit("movq %rdi, %r12")            # cell
        self._emit("movq %rsi, %r13")            # key
        self._emit_fnv_hash(t.key)               # rax = hash
        self._emit("movq 8(%r12), %r14")         # cap
        self._emit("decq %r14")                  # mask
        self._emit("andq %r14, %rax")
        self._emit("movq %rax, %r11")            # idx
        self._emit(f"{probe}:")
        self._emit("movq %r11, %r9")
        self._emit(f"imulq ${ss}, %r9")
        self._emit("leaq 16(%r12,%r9), %r9")     # &slot
        self._emit("movq (%r9), %rcx")           # state
        self._emit("testq %rcx, %rcx")
        self._emit(f"jz {nf}")                   # empty: stop, not found
        self._emit_key_eq(t.key, found)
        self._emit("incq %r11")
        self._emit("andq %r14, %r11")
        self._emit(f"jmp {probe}")
        self._emit(f"{found}:")
        self._emit("movq %r9, %rax")             # &slot
        self._emit(f"jmp {ret}")
        self._emit(f"{nf}:")
        self._emit("xorq %rax, %rax")            # not found
        self._emit(f"{ret}:")
        self._emit("popq %r14")
        self._emit("popq %r13")
        self._emit("popq %r12")
        self._emit("leave")
        self._emit("ret")
        self._emit("")

    def _emit_map_clone_helper(self, t: MapType) -> None:
        """`__clone_map_<m>`: %rdi = shared cell -> %rax = an independent copy
        (rc=1); retain each occupied value, decrement the original's refcount."""
        ss = self._map_slot_size(t)
        vt = t.value
        self._emit(f"{self._map_clone_name(t)}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %rbx")
        self._emit("pushq %r12")
        self._emit("pushq %r13")
        self._emit("pushq %r14")
        self._emit("movq %rdi, %rbx")            # old cell
        self._emit("movq -16(%rbx), %r12")       # value size in bytes
        self._emit("movq %r12, %rdi")
        self._emit("call __alloc")               # rax = new cell (rc=1)
        self._emit("movq %rax, %r13")
        self._emit("movq %rbx, %rsi")
        self._emit("movq %r13, %rdi")
        self._emit("movq %r12, %rcx")
        self._emit("shrq $3, %rcx")
        self._emit("cld")
        self._emit("rep movsq")                  # copy old -> new
        if self._owns_heap(vt):
            self._emit("movq 8(%r13), %r12")     # cap
            self._emit("xorq %r14, %r14")        # i = 0
            loop, done, skip = self._label(), self._label(), self._label()
            self._emit(f"{loop}:")
            self._emit("cmpq %r12, %r14")
            self._emit(f"jge {done}")
            self._emit("movq %r14, %rax")
            self._emit(f"imulq ${ss}, %rax")
            self._emit("leaq 16(%r13,%rax), %rcx")   # &slot
            self._emit("movq (%rcx), %rax")          # state
            self._emit("cmpq $1, %rax")
            self._emit(f"jne {skip}")
            self._walk_member("rcx", 16, vt, self._inc_box)
            self._emit(f"{skip}:")
            self._emit("incq %r14")
            self._emit(f"jmp {loop}")
            self._emit(f"{done}:")
        self._emit("decq -8(%rbx)")              # original loses this reference
        self._emit("movq %r13, %rax")
        self._emit("popq %r14")
        self._emit("popq %r13")
        self._emit("popq %r12")
        self._emit("popq %rbx")
        self._emit("leave")
        self._emit("ret")
        self._emit("")

    def _emit_map_grow_helper(self, t: MapType) -> None:
        """`__grow_map_<m>`: %rdi = uniquely-owned cell (rc=1) -> %rax = a cell with
        doubled capacity, every occupied entry rehashed in (ownership moves)."""
        ss = self._map_slot_size(t)
        vs = self._stored_size(t.value)
        self._emit(f"{self._map_grow_name(t)}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %rbx")
        self._emit("pushq %r12")
        self._emit("pushq %r13")
        self._emit("pushq %r14")
        self._emit("pushq %r15")
        self._emit("movq %rdi, %rbx")            # old cell
        self._emit("movq 8(%rbx), %rdi")         # old cap
        self._emit("addq %rdi, %rdi")            # new cap = old cap * 2
        self._emit(f"call {self._map_new_name(t)}")  # rax = new cell (zeroed)
        self._emit("movq %rax, %r13")            # new cell
        self._emit("movq 8(%rbx), %r12")         # old cap
        self._emit("xorq %r14, %r14")            # i = 0
        loop, done, skip = self._label(), self._label(), self._label()
        self._emit(f"{loop}:")
        self._emit("cmpq %r12, %r14")
        self._emit(f"jge {done}")
        self._emit("movq %r14, %rax")
        self._emit(f"imulq ${ss}, %rax")
        self._emit("leaq 16(%rbx,%rax), %r15")   # &old slot
        self._emit("movq (%r15), %rax")          # state
        self._emit("cmpq $1, %rax")
        self._emit(f"jne {skip}")
        self._emit("movq %r13, %rdi")
        self._emit("movq 8(%r15), %rsi")         # key
        self._emit(f"call {self._map_put_name(t)}")   # rax = &new value slot
        self._emit("leaq 16(%r15), %rsi")        # &old value
        self._emit("movq %rax, %rdi")
        self._emit(f"movq ${vs // 8}, %rcx")
        self._emit("cld")
        self._emit("rep movsq")                  # move the value bytes over
        self._emit(f"{skip}:")
        self._emit("incq %r14")
        self._emit(f"jmp {loop}")
        self._emit(f"{done}:")
        self._emit("movq %rbx, %rdi")
        self._emit("call __free")                # old cell freed (values moved out)
        self._emit("movq %r13, %rax")
        self._emit("popq %r15")
        self._emit("popq %r14")
        self._emit("popq %r13")
        self._emit("popq %r12")
        self._emit("popq %rbx")
        self._emit("leave")
        self._emit("ret")
        self._emit("")

    def _emit_map_drop_helper(self, t: MapType) -> None:
        """`__drop_map_<m>`: %rdi = cell. Decrement the refcount; at zero, drop each
        occupied value (keys are non-owning primitives) and free the cell."""
        ss = self._map_slot_size(t)
        vt = t.value
        keep = self._label()
        self._emit(f"{self._map_drop_name(t)}:")
        self._emit("decq -8(%rdi)")
        self._emit(f"jnz {keep}")
        if self._owns_heap(vt):
            self._emit("pushq %rbp")
            self._emit("movq %rsp, %rbp")
            self._emit("pushq %rbx")
            self._emit("pushq %r12")
            self._emit("pushq %r13")
            self._emit("pushq %r14")
            self._emit("movq %rdi, %rbx")        # cell
            self._emit("movq 8(%rbx), %r12")     # cap
            self._emit("xorq %r13, %r13")        # i = 0
            loop, done, skip = self._label(), self._label(), self._label()
            self._emit(f"{loop}:")
            self._emit("cmpq %r12, %r13")
            self._emit(f"jge {done}")
            self._emit("movq %r13, %rax")
            self._emit(f"imulq ${ss}, %rax")
            self._emit("leaq 16(%rbx,%rax), %r14")   # &slot
            self._emit("movq (%r14), %rax")          # state
            self._emit("cmpq $1, %rax")
            self._emit(f"jne {skip}")
            self._walk_member("r14", 16, vt, self._drop_box)
            self._emit(f"{skip}:")
            self._emit("incq %r13")
            self._emit(f"jmp {loop}")
            self._emit(f"{done}:")
            self._emit("movq %rbx, %rdi")
            self._emit("popq %r14")
            self._emit("popq %r13")
            self._emit("popq %r12")
            self._emit("popq %rbx")
            self._emit("leave")
            self._emit("jmp __free")
        else:
            self._emit("jmp __free")
        self._emit(f"{keep}:")
        self._emit("ret")
        self._emit("")

    def _emit_map_keys_helper(self, t: MapType) -> None:
        """`__keys_map_<m>`: %rdi = map cell -> %rax = a fresh `[K]` list (rc=1) of
        the occupied keys (any order). Keys are non-owning primitives, so no
        retain is needed."""
        ss = self._map_slot_size(t)
        self._emit(f"{self._map_keys_name(t)}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %rbx")
        self._emit("pushq %r12")
        self._emit("pushq %r13")
        self._emit("pushq %r14")
        self._emit("movq %rdi, %rbx")            # map cell
        self._emit("movq (%rbx), %r12")          # n = len
        self._emit("leaq 16(,%r12,8), %rdi")     # list size = 16 + n*8
        self._emit("call __alloc")               # rax = list cell (rc=1)
        self._emit("movq %rax, %r13")
        self._emit("movq %r12, (%r13)")          # list len = n
        self._emit("movq %r12, 8(%r13)")         # list cap = n
        self._emit("movq 8(%rbx), %r12")         # map cap
        self._emit("leaq 16(%r13), %rdx")        # &list[0] (write pointer)
        self._emit("xorq %r14, %r14")            # slot index i = 0
        loop, done, skip = self._label(), self._label(), self._label()
        self._emit(f"{loop}:")
        self._emit("cmpq %r12, %r14")
        self._emit(f"jge {done}")
        self._emit("movq %r14, %rax")
        self._emit(f"imulq ${ss}, %rax")
        self._emit("leaq 16(%rbx,%rax), %rax")   # &slot
        self._emit("movq (%rax), %rcx")          # state
        self._emit("cmpq $1, %rcx")
        self._emit(f"jne {skip}")
        self._emit("movq 8(%rax), %rcx")         # key
        self._emit("movq %rcx, (%rdx)")          # append to list
        self._emit("addq $8, %rdx")
        self._emit(f"{skip}:")
        self._emit("incq %r14")
        self._emit(f"jmp {loop}")
        self._emit(f"{done}:")
        self._emit("movq %r13, %rax")
        self._emit("popq %r14")
        self._emit("popq %r13")
        self._emit("popq %r12")
        self._emit("popq %rbx")
        self._emit("leave")
        self._emit("ret")
        self._emit("")

    def _emit_map_remove_helper(self, t: MapType) -> None:
        """`__remove_map_<m>`: %rdi = uniquely-owned cell (rc=1), %rsi = key ->
        %rax = a fresh cell (same cap) with every entry except `key` rehashed in
        (rebuild deletion — no tombstones); the removed value is dropped, the old
        cell freed."""
        ss = self._map_slot_size(t)
        vs = self._stored_size(t.value)
        vt = t.value
        self._emit(f"{self._map_remove_name(t)}:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %rbx")
        self._emit("pushq %r12")
        self._emit("pushq %r13")
        self._emit("pushq %r14")
        self._emit("pushq %r15")
        self._emit("subq $8, %rsp")              # spill slot for the search key
        self._emit("movq %rdi, %rbx")            # old cell
        self._emit("movq %rsi, -48(%rbp)")       # search key
        self._emit("movq 8(%rbx), %rdi")         # cap (rebuild keeps the capacity)
        self._emit(f"call {self._map_new_name(t)}")
        self._emit("movq %rax, %r13")            # new cell
        self._emit("movq 8(%rbx), %r12")         # cap
        self._emit("xorq %r14, %r14")            # i = 0
        loop, done, skip, keep, drop = (self._label(), self._label(),
                                        self._label(), self._label(), self._label())
        self._emit(f"{loop}:")
        self._emit("cmpq %r12, %r14")
        self._emit(f"jge {done}")
        self._emit("movq %r14, %rax")
        self._emit(f"imulq ${ss}, %rax")
        self._emit("leaq 16(%rbx,%rax), %r15")   # &old slot
        self._emit("movq (%r15), %rax")          # state
        self._emit("cmpq $1, %rax")
        self._emit(f"jne {skip}")
        if isinstance(t.key, StrType):
            self._emit("movq 8(%r15), %rdi")
            self._emit("movq -48(%rbp), %rsi")
            self._emit("call __str_eq")
            self._emit("testq %rax, %rax")
            self._emit(f"jnz {drop}")
        else:
            self._emit("movq 8(%r15), %rax")
            self._emit("cmpq -48(%rbp), %rax")
            self._emit(f"je {drop}")
        self._emit(f"{keep}:")                    # not the removed key: rehash in
        self._emit("movq %r13, %rdi")
        self._emit("movq 8(%r15), %rsi")          # key
        self._emit(f"call {self._map_put_name(t)}")   # rax = &new value slot
        self._emit("leaq 16(%r15), %rsi")         # &old value
        self._emit("movq %rax, %rdi")
        self._emit(f"movq ${vs // 8}, %rcx")
        self._emit("cld")
        self._emit("rep movsq")                   # move the value bytes over
        self._emit(f"jmp {skip}")
        self._emit(f"{drop}:")                     # the removed entry: release it
        if self._owns_heap(vt):
            self._drop_value("r15", 16, vt)
        self._emit(f"{skip}:")
        self._emit("incq %r14")
        self._emit(f"jmp {loop}")
        self._emit(f"{done}:")
        self._emit("movq %rbx, %rdi")
        self._emit("call __free")                 # old cell freed (values moved out)
        self._emit("movq %r13, %rax")
        self._emit("addq $8, %rsp")
        self._emit("popq %r15")
        self._emit("popq %r14")
        self._emit("popq %r13")
        self._emit("popq %r12")
        self._emit("popq %rbx")
        self._emit("leave")
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
            if self._owns_heap(mt):  # list member: store copies a reference
                self._retain("rbp", slot_off, mt)

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
            cref = getattr(expr, "const_ref", None)
            if cref is not None:
                self._eval_const(cref, expr.resolved_type)
            else:
                _, off, _ = self._lookup(expr.ident)
                self._emit(f"movq {off}(%rbp), %rax")
        elif isinstance(expr, ast.Unary):
            self._eval_unary(expr)
        elif isinstance(expr, ast.Binary):
            self._eval_binary(expr)
        elif isinstance(expr, ast.Call):
            self._gen_call(expr)
            rt = expr.resolved_type
            if rt is not None and self._owns_heap(rt) and not _is_aggregate(rt):
                # a list result: stash the (escaped) pointer in its temp slot so
                # the temp-drop machinery releases it if it isn't consumed
                self._emit(f"movq %rax, {self._locals[id(expr)]}(%rbp)")
        elif isinstance(expr, ast.FieldAccess):
            self._addr_of_aggregate(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            self._emit(f"movq {foff}(%rax), %rax")
        elif isinstance(expr, ast.TupleIndex):
            self._addr_of_aggregate(expr.target)
            foff = self._elem_offset(expr.target.resolved_type, expr.index)
            self._emit(f"movq {foff}(%rax), %rax")
        elif isinstance(expr, ast.ListLit):
            self._gen_list_lit(expr)
            self._emit(f"movq {self._locals[id(expr)]}(%rbp), %rax")
        elif isinstance(expr, ast.MapLit):
            self._gen_map_lit(expr)
            self._emit(f"movq {self._locals[id(expr)]}(%rbp), %rax")
        elif isinstance(expr, ast.Index):
            if isinstance(expr.target.resolved_type, StrType):
                self._gen_str_index(expr)         # byte at s[i], zero-extended
            else:
                self._index_addr(expr)            # &elem / &value -> rax
                self._emit("movq (%rax), %rax")   # load the scalar element/value
        elif isinstance(expr, ast.Match):
            self._gen_match(expr)
            if expr.resolved_type is not None:
                off = self._locals[f"matchres:{id(expr)}"]
                self._emit(f"movq {off}(%rbp), %rax")
        elif isinstance(expr, ast.Cast):
            self._eval(expr.operand)
            self._wrap(expr.resolved_type)
        else:  # pragma: no cover
            raise ValueError(f"cannot evaluate {type(expr).__name__}")

    def _eval_unary(self, expr: ast.Unary) -> None:
        self._eval(expr.operand)
        if expr.op == "-":
            self._emit("negq %rax")
            self._wrap(expr.resolved_type)
        elif expr.op == "~":
            self._emit("notq %rax")
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

        if op == "+" and isinstance(ltype, StrType):
            self._eval(expr.right)
            self._emit("pushq %rax")
            self._eval(expr.left)
            self._emit("movq %rax, %rdi")        # A
            self._emit("popq %rsi")              # B
            self._emit("call __str_concat")      # rax = A + B (fresh heap str)
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
        elif op == "&":
            self._emit("andq %rcx, %rax")
            self._wrap(expr.resolved_type)
        elif op == "|":
            self._emit("orq %rcx, %rax")
            self._wrap(expr.resolved_type)
        elif op == "^":
            self._emit("xorq %rcx, %rax")
            self._wrap(expr.resolved_type)
        elif op in ("<<", ">>"):
            # Mask the count to the operand width so the result is well-defined
            # and matches the interpreter (the hardware would otherwise mask the
            # 64-bit shift count modulo 64). `cl` is the low byte of %rcx.
            self._emit(f"andq ${expr.resolved_type.width - 1}, %rcx")
            if op == "<<":
                self._emit("shlq %cl, %rax")
            elif ltype.signed:
                self._emit("sarq %cl, %rax")   # arithmetic: preserve sign
            else:
                self._emit("shrq %cl, %rax")   # logical: zero-fill
            self._wrap(expr.resolved_type)
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

        if name == "len":
            self._eval(expr.args[0])             # list cell pointer -> rax
            self._emit("movq (%rax), %rax")      # length at offset 0
            return

        if name == "push":
            self._gen_push(expr)
            return
        if name == "pop":
            self._gen_pop(expr)
            return
        if name == "contains":
            self._gen_contains(expr)
            return
        if name == "remove":
            self._gen_remove(expr)
            return
        if name == "keys":
            self._eval(expr.args[0])             # map cell -> rax
            self._emit("movq %rax, %rdi")
            self._emit(f"call {self._map_keys_name(expr.args[0].resolved_type)}")
            return

        if name == "format":
            self._gen_format(expr)
            return

        if name == "StringBuilder":
            self._emit("call __sb_new")
            return
        if name == "build":
            self._eval(expr.args[0])             # builder cell -> rax
            self._emit("movq %rax, %rdi")
            self._emit("call __sb_build")
            return
        if name == "append":
            self._gen_sb_append(expr)
            return
        if name == "append_byte":
            self._gen_sb_append_byte(expr)
            return

        if name in ("assert", "panic", "unreachable"):
            self._gen_intrinsic(expr)
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

    def _gen_intrinsic(self, expr: ast.Call) -> None:
        """`assert`/`panic`/`unreachable`: write a message to stderr and exit(1)
        (D-, §7). `__panic` takes %rdi -> [len:8][bytes]."""
        name = expr.callee.ident
        if name == "panic":
            self._eval(expr.args[0])  # message pointer -> %rax
            self._emit("movq %rax, %rdi")
            self._emit("call __panic")
            return
        if name == "unreachable":
            label = self._string_label("reached unreachable code")
            self._emit(f"leaq {label}(%rip), %rdi")
            self._emit("call __panic")
            return
        # assert(cond[, msg]): fall through (pass) when the condition holds.
        ok = self._label()
        self._eval(expr.args[0])  # cond -> %rax (0/1)
        self._emit("testq %rax, %rax")
        self._emit(f"jnz {ok}")
        if len(expr.args) == 2:
            self._eval(expr.args[1])
            self._emit("movq %rax, %rdi")
        else:
            label = self._string_label("assertion failed")
            self._emit(f"leaq {label}(%rip), %rdi")
        self._emit("call __panic")
        self._emit(f"{ok}:")

    def _eval_const(self, name: str, t: Type) -> None:
        """Inline the folded value of const `name` into %rax (D28)."""
        value = self.checker.consts[name].value
        if isinstance(t, StrType):
            label = self._string_label(value)
            self._emit(f"leaq {label}(%rip), %rax")
        elif isinstance(t, BoolType):
            self._emit(f"movq ${1 if value else 0}, %rax")
        else:  # IntType
            self._emit(f"movabsq ${value}, %rax")

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

    def _gen_render_to_str(self, arg: ast.Expr) -> None:
        """Evaluate `arg` and leave a `str` pointer for its `print` rendering in
        %rax (used by format(): str passes through, int/bool are converted)."""
        self._eval(arg)
        t = arg.resolved_type
        if isinstance(t, StrType):
            return
        self._emit("movq %rax, %rdi")
        if isinstance(t, BoolType):
            self._emit("call __bool_to_str")
        else:  # IntType
            self._emit("call __int_to_str" if t.signed else "call __uint_to_str")

    def _gen_format(self, expr: ast.Call) -> None:
        """Build the `format(fmt, args…)` result by folding the literal segments
        and rendered arguments together with `__str_concat`. The running result
        is kept on the stack between pieces."""
        fmt = expr.args[0].value
        pieces = _format_pieces(fmt)         # ('lit', text) | ('arg', index)
        rest = expr.args[1:]

        def emit_piece(piece) -> None:
            kind, payload = piece
            if kind == "lit":
                label = self._string_label(payload)
                self._emit(f"leaq {label}(%rip), %rax")
            else:
                self._gen_render_to_str(rest[payload])

        emit_piece(pieces[0])                # result = first piece -> rax
        for piece in pieces[1:]:
            self._emit("pushq %rax")         # save running result
            emit_piece(piece)                # next piece -> rax
            self._emit("movq %rax, %rsi")    # B = next piece
            self._emit("popq %rdi")          # A = running result
            self._emit("call __str_concat")  # rax = A + B

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


def _format_pieces(fmt: str) -> list:
    """Split a `format` string into an alternating list of literal segments and
    argument holes: `('lit', text)` and `('arg', index)`. `{{`/`}}` are literal
    braces; the checker has already validated the brace structure and counts."""
    pieces: list = []
    buf: list[str] = []
    arg = 0
    i = 0
    n = len(fmt)
    while i < n:
        c = fmt[i]
        if c == "{" and i + 1 < n and fmt[i + 1] == "{":
            buf.append("{")
            i += 2
        elif c == "}" and i + 1 < n and fmt[i + 1] == "}":
            buf.append("}")
            i += 2
        elif c == "{" and i + 1 < n and fmt[i + 1] == "}":
            pieces.append(("lit", "".join(buf)))
            buf = []
            pieces.append(("arg", arg))
            arg += 1
            i += 2
        else:
            buf.append(c)
            i += 1
    pieces.append(("lit", "".join(buf)))
    return pieces


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
