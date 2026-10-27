"""x86-64 code generator for Myla v0.0 (docs/Architecture/Native-backend.md).

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

import dataclasses
import struct

from .. import ast
from ..types import (
    BoolType, CharType, Checker, EnumType, FloatType, FuncSig, FuncType, IntType,
    ListType, MapType, StrType, StringBuilderType, StructType, TupleType, Type,
    type_name, _is_diverging, _is_literal_expr as _is_literal,
    _FF_MINK, _FF_MAXK, _FF_POW10_DD, _FF_SPLIT, _FF_BIG, _FF_UP, _FF_DOWN, round_float,
)
from .monomorphize import type_token


# The runtime-error entries and their messages (MYLA-17); the same in the
# self-hosted code generator.
_TRAPS = [
    ("__trap", "runtime error"),
    ("__trap_index", "index out of bounds"),
    ("__trap_key", "map key not found"),
    ("__trap_pop", "pop from an empty list"),
    ("__trap_div", "division by zero"),
    ("__trap_mod", "modulo by zero"),
    ("__trap_match", "no match arm matched"),
    ("__trap_oom", "out of memory"),
]

# The refcount of a `str` cell in the binary: retains and drops change it like
# any other, but it never reaches zero, so it is never freed (MYLA-18).
STATIC_RC = 1 << 62

# The float renderer's constant results.
_FLOAT_STRS = [
    (".Lstr_nan", b"nan"),
    (".Lstr_inf", b"inf"),
    (".Lstr_ninf", b"-inf"),
    (".Lstr_fzero", b"0"),
    (".Lstr_fnzero", b"-0"),
]

# Heap cells whose pointer is the value: `_owns_heap`, retained and dropped as
# one pointer.
_CELL_TYPES = (ListType, MapType, StringBuilderType, StrType)


def _static_str(label: str, data: bytes) -> list[str]:
    """A `str` cell in the data section: the heap's `[size][refcount]` header,
    then `[len][bytes]` at `label` (MYLA-18)."""
    out = ["\t.balign 8", f"\t.quad {8 + len(data)}", f"\t.quad {STATIC_RC}",
           f"{label}:", f"\t.quad {len(data)}"]
    if data:
        out.append("\t.byte " + ", ".join(str(b) for b in data))
    return out


def _f64_bits(x: float) -> int:
    """The unsigned 64-bit pattern of `x` as an IEEE-754 double."""
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _f64_imm(x: float) -> int:
    """The pattern of `x` as a signed 64-bit immediate (for `movabsq`)."""
    return struct.unpack("<q", struct.pack("<d", x))[0]


# Size of the heap arena reserved on first allocation (1 GiB). Generous for a
# bootstrap compiler; exhausting it traps. Reference counting (v0.2.3b) will let
# this memory be reused instead of only grown. (The arena is lazily-faulted
# anonymous mmap, so an unused tail costs nothing until touched. Kept <2 GiB so
# the `addq $_ARENA_BYTES` immediate fits a signed imm32.)
_ARENA_BYTES = 1 << 30

# Freed cells up to this value size (bytes) go onto one exact-size free list per
# 8-byte size class, so allocating and freeing them never scans (MYLA-16). Larger
# cells share one list that is searched for an exact fit. The self-hosted
# runtime uses the same limit.
_SMALL_CELL_LIMIT = 4096


def _is_struct(t: Type | None) -> bool:
    return isinstance(t, StructType)


def _is_aggregate(t: Type | None) -> bool:
    """Aggregates (structs, tuples, enums, function values) have value semantics
    and live in multi-slot storage, passed by address rather than in a register.
    A function value is a 16-byte `(code_ptr, env_ptr)` fat value (v0.4.2)."""
    return isinstance(t, (StructType, TupleType, EnumType, FuncType))


# signed / unsigned `set` mnemonics for the relational operators
_SET_MNEMONIC = {
    "<": ("setl", "setb"),
    "<=": ("setle", "setbe"),
    ">": ("setg", "seta"),
    ">=": ("setge", "setae"),
}


class CodeGen:
    def __init__(self, checker: Checker, debug: bool = False):
        self.checker = checker
        self.text: list[str] = []
        # debug line tables (MYLA-71): source path -> `.file` number, the number
        # of the file being generated (None: no line info for this function, e.g.
        # the prelude), and the file of each lambda, set where it is created.
        self._debug = debug
        self._files: dict[str, int] = {}
        self._cur_file: int | None = None
        self._last_loc = ""
        self._lambda_files: dict[int, int | None] = {}
        self.rodata: list[str] = []
        self.strdata: list[str] = []        # static `str` cells (_static_str)
        self._label_n = 0
        self._str_n = 0
        self._strings: dict[str, str] = {}  # raw text -> label
        # per-function state
        self._locals: dict[int, int] = {}   # id(node) -> rbp offset (negative)
        self._scopes: list[dict[str, tuple]] = []
        # per staged value not yet committed: drop emitters for what an early
        # return must release (see _stage_value)
        self._staged_drops: list[list] = []
        self._epilogue = ""
        self._struct_ret = False
        # top-level `fun`s referenced as values: each needs an env-ignoring thunk
        # so it shares the closure calling convention (v0.4.2)
        self._fnval_thunks: set[str] = set()
        # set once any float operation is emitted, so the SSE2 float runtime
        # (helpers + power-of-ten tables) is only appended when actually needed.
        self._uses_float = False
        # set once any `char` is printed/formatted, so the UTF-8 encoder helper
        # (__char_to_str) is only appended when actually needed.
        self._uses_char = False
        # set once `chars()` is used, gating the UTF-8 decode helper (__str_chars).
        self._uses_str_chars = False
        # set once `std.io.__write` is used, gating the raw `write` helper.
        self._uses_write = False
        # set once `std.process.args` (`__args`) is used, gating the argv->[str]
        # builder helper. (`_start` always stashes argc/argv; only the builder is
        # conditional.)
        self._uses_args = False
        # set once `std.fs.read_to_string` (`__read_file`/`__io_errno`) is used,
        # gating the file-read helper + its errno global.
        self._uses_read_file = False
        # set once `std.fs.write_to_file` (`__write_file`) is used, gating the
        # file-write helper (shares the `__io_errno_val` global).
        self._uses_write_file = False
        # set once `std.io`'s reader (`__read`) is used, gating the read helper
        # (MYLA-78; shares the `__io_errno_val` global).
        self._uses_read = False
        # set once `Reader.ready` (`__poll`) is used, gating the poll helper
        # (MYLA-80; shares the `__io_errno_val` global).
        self._uses_poll = False
        # set once `__io_errno` is used, gating the `__io_errno_val` global
        # (also emitted for the helpers that set it).
        self._uses_io_errno = False
        # set once `std.process.run`/`Command` (`__run`/`__run_*`) is used, gating
        # the subprocess runtime (fork/execve/pipe/poll/wait4) + its result globals.
        self._uses_run = False

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
        if isinstance(t, _CELL_TYPES):           # refcounted cell
            return True
        if isinstance(t, FuncType):  # owns a (possibly null) refcounted env cell
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
        if isinstance(t, FuncType):
            return 16                       # (code_ptr, env_ptr) fat value
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
        """A stable, injective identifier fragment for `t`, used to name
        per-type helpers (MYLA-9). Structs and enums are already concrete,
        with mangled names, after monomorphization."""
        if isinstance(t, (StructType, EnumType)):
            return t.name
        return type_token(t, self._type_mangle)

    def _list_drop_name(self, t: ListType) -> str:
        return "__drop_list_" + self._type_mangle(t.elem)

    def _list_clone_name(self, t: ListType) -> str:
        return "__clone_list_" + self._type_mangle(t.elem)

    def _list_grow_name(self, t: ListType) -> str:
        return "__grow_list_" + self._type_mangle(t.elem)

    # -- map layout: a heap cell [len:8][cap:8][slot0]...]; each slot is
    # [state:8][key:8][value:vs] with state 0=empty / 1=occupied / 2=tombstone --

    def _map_suffix(self, t: MapType) -> str:
        return self._type_mangle(t)

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

    def _gather_list_types(self, t: Type | None, into: dict, visited: set) -> None:
        """Add every list/map/builder type reachable from `t` to `into` (keyed by
        mangle, in discovery order). `visited` holds the types already expanded
        during this collection, so each type is walked once however many paths
        lead to it (MYLA-60); it also breaks recursive (boxed) type cycles."""
        if t is None or t in visited:
            return
        visited.add(t)
        if isinstance(t, StringBuilderType):
            into.setdefault("SB", t)
        elif isinstance(t, ListType):
            into.setdefault(self._type_mangle(t), t)
            self._gather_list_types(t.elem, into, visited)
        elif isinstance(t, MapType):
            into.setdefault(self._type_mangle(t), t)
            self._gather_list_types(t.key, into, visited)
            self._gather_list_types(t.value, into, visited)
        elif isinstance(t, StructType):
            for ft in self.checker.structs.get(t.name, {}).values():
                self._gather_list_types(ft, into, visited)
        elif isinstance(t, EnumType):
            for payload in self.checker.enums.get(t.name, {}).values():
                for ft in payload:
                    self._gather_list_types(ft, into, visited)
        elif isinstance(t, TupleType):
            for e in t.elems:
                self._gather_list_types(e, into, visited)
        elif isinstance(t, FuncType):
            for p in t.params:
                self._gather_list_types(p, into, visited)
            self._gather_list_types(t.ret, into, visited)

    def _collect_list_types(self) -> dict:
        """Every concrete list type used anywhere in the program (keyed by mangle),
        so we can emit one `__drop_list_<elem>` routine per element type."""
        found: dict = {}
        visited: set = set()
        for fields in self.checker.structs.values():
            for ft in fields.values():
                self._gather_list_types(ft, found, visited)
        for variants in self.checker.enums.values():
            for payload in variants.values():
                for ft in payload:
                    self._gather_list_types(ft, found, visited)
        for sig in self.checker.functions.values():
            for p in sig.params:
                self._gather_list_types(p, found, visited)
            self._gather_list_types(sig.ret, found, visited)
        for info in self.checker.consts.values():
            self._gather_list_types(info.type, found, visited)

        def walk(node) -> None:
            import dataclasses
            self._gather_list_types(getattr(node, "resolved_type", None), found, visited)
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
        self.strdata.extend(_static_str(label, text.encode("utf-8")))
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
        # lifted lambda bodies + their per-lambda env-drop helpers (v0.4.2)
        for lam in self.checker._lambdas:
            self._gen_lambda_function(lam)
        # env-ignoring thunks for plain `fun`s referenced as values
        for name in sorted(self._fnval_thunks):
            self._emit_fnval_thunk(name)
        if self._uses_float:
            self._emit_float_runtime()
        if self._uses_char:
            self._emit_char_runtime()
        if self._uses_str_chars:
            self._emit_str_chars_runtime()
        if self._uses_write:
            self._emit_write_runtime()
        if self._uses_args:
            self._emit_args_runtime()
        if self._uses_read_file:
            self._emit_read_file_runtime()
        if self._uses_write_file:
            self._emit_write_file_runtime()
        if self._uses_read:
            self._emit_read_runtime()
        if self._uses_poll:
            self._emit_poll_runtime()
        if self._uses_run:
            self._emit_run_runtime()
        return self._assemble_source()

    def _assemble_source(self) -> str:
        out: list[str] = []
        out.append("\t.text")
        for path, number in self._files.items():
            out.append(f'\t.file {number} "{_asm_string(path)}"')
        out.extend(self.text)
        out.append("")
        out.append("\t.section .rodata")
        out.append('.Lbool_true:\n\t.ascii "true"')
        out.append('.Lbool_false:\n\t.ascii "false"')
        for label, message in _TRAPS:
            text = "runtime error: " + message
            out.append(f'.Lmsg{label}:\n\t.quad {len(text)}\n\t.ascii "{text}"')
        if self._uses_float:
            out.extend(self._float_rodata())
        out.extend(self.rodata)
        out.append("")
        # `str` values that live in the binary (literals, the renderers'
        # constants): cells with a count that never reaches zero (MYLA-18)
        out.append("\t.data")
        out.extend(_static_str(".Lstr_true", b"true"))
        out.extend(_static_str(".Lstr_false", b"false"))
        out.extend(_static_str(".Lstr_minus", b"-"))
        if self._uses_float:
            for label, text in _FLOAT_STRS:
                out.extend(_static_str(label, text))
        out.extend(self.strdata)
        out.append("")
        # heap bookkeeping for __alloc (zero-initialized)
        out.append("\t.bss")
        out.append("\t.align 8")
        out.append("__heap_ptr:")
        out.append("\t.skip 8")
        out.append("__heap_end:")
        out.append("\t.skip 8")
        # one list head per 8-byte size class up to _SMALL_CELL_LIMIT, then one
        # per power of two (indexed by its exponent) for larger cells
        out.append("__free_buckets:")
        out.append(f"\t.skip {_SMALL_CELL_LIMIT + 8 + 8 * 64}")
        # argc/argv captured at `_start` for `std.process.args` (D29)
        out.append("__argc:")
        out.append("\t.skip 8")
        out.append("__argv:")
        out.append("\t.skip 8")
        # envp captured at `_start`, passed through to `execve` by `__run` (D29)
        out.append("__envp:")
        out.append("\t.skip 8")
        if self._uses_run:
            # results of the last `__run`, read by the `__run_*` primitives:
            # the stderr `[uint8]` cell, the exit code, the signal, the errno.
            out.append("__run_stderr_val:")
            out.append("\t.skip 8")
            out.append("__run_exit_val:")
            out.append("\t.skip 8")
            out.append("__run_signal_val:")
            out.append("\t.skip 8")
            out.append("__run_errno_val:")
            out.append("\t.skip 8")
        if (self._uses_read_file or self._uses_write_file or self._uses_read or self._uses_poll
                or self._uses_io_errno):
            # errno of the last `__read_file`, `__write_file`, `__read` or `__poll` (0 on
            # success), read by `__io_errno`
            out.append("__io_errno_val:")
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
        # capture argc/argv from the entry stack (D29) for `std.process.args`.
        e("\tmovq (%rsp), %rax")        # argc
        e("\tmovq %rax, __argc(%rip)")
        e("\tleaq 8(%rsp), %rcx")       # &argv[0]
        e("\tmovq %rcx, __argv(%rip)")
        # envp = &argv[argc + 1] = rsp + 16 + argc*8 (past argv's NULL terminator)
        e("\tleaq 16(%rsp,%rax,8), %rcx")
        e("\tmovq %rcx, __envp(%rip)")
        e(f"\tcall myla_{entry_name}")
        e("\tmovq $60, %rax")          # exit
        e("\txorq %rdi, %rdi")
        e("\tsyscall")
        e("")
        # Runtime errors: `runtime error: <message>` on stderr, then exit(1)
        # (MYLA-17). Each kind has its own entry; the message is the
        # interpreter's, without the values.
        for label, _message in _TRAPS:
            e(f"{label}:")
            e(f"\tleaq .Lmsg{label}(%rip), %rdi")
            e("\tjmp __panic")
        e("")
        # __write_all: write rdx bytes at rsi to fd rdi, however many write
        # calls it takes: a short write continues, EINTR and EAGAIN (a full
        # non-blocking pipe) retry, another error gives up (MYLA-17).
        e("__write_all:")
        e(".Lwa_loop:")
        e("\ttestq %rdx, %rdx")
        e("\tjz .Lwa_done")
        e("\tmovq $1, %rax")            # write
        e("\tsyscall")
        e("\tcmpq $-4, %rax")           # EINTR
        e("\tje .Lwa_loop")
        e("\tcmpq $-11, %rax")          # EAGAIN
        e("\tje .Lwa_loop")
        e("\ttestq %rax, %rax")
        e("\tjs .Lwa_done")
        e("\taddq %rax, %rsi")
        e("\tsubq %rax, %rdx")
        e("\tjmp .Lwa_loop")
        e(".Lwa_done:")
        e("\tret")
        e("")
        # __panic: %rdi -> [len:8][bytes]; write the message + newline to stderr,
        # then exit(1). Used by assert/panic/unreachable (§7) and the traps.
        e("__panic:")
        e("\tmovq (%rdi), %rdx")        # len
        e("\tleaq 8(%rdi), %rsi")       # data
        e("\tmovq $2, %rdi")            # stderr
        e("\tcall __write_all")
        e("\tsubq $16, %rsp")           # newline to stderr
        e("\tmovb $10, (%rsp)")
        e("\tmovq $2, %rdi")
        e("\tmovq %rsp, %rsi")
        e("\tmovq $1, %rdx")
        e("\tcall __write_all")
        e("\taddq $16, %rsp")
        e("\tmovq $60, %rax")           # exit(1)
        e("\tmovq $1, %rdi")
        e("\tsyscall")
        e("")
        # __print_nl: write a single newline to stdout
        e("__print_nl:")
        e("\tsubq $16, %rsp")
        e("\tmovb $10, (%rsp)")
        e("\tmovq $1, %rdi")
        e("\tmovq %rsp, %rsi")
        e("\tmovq $1, %rdx")
        e("\tcall __write_all")
        e("\taddq $16, %rsp")
        e("\tret")
        e("")
        # __print_minus: write a single '-' (no newline)
        e("__print_minus:")
        e("\tsubq $16, %rsp")
        e("\tmovb $45, (%rsp)")
        e("\tmovq $1, %rdi")
        e("\tmovq %rsp, %rsi")
        e("\tmovq $1, %rdx")
        e("\tcall __write_all")
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
        e("\tmovq $1, %rdi")
        e("\tcall __write_all")
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
        e("\tmovq $1, %rdi")
        e("\tcall __write_all")
        e("\tcall __print_nl")
        e("\tret")
        e("")
        # __print_str: %rdi -> [len:8][bytes]; write bytes then newline
        e("__print_str:")
        e("\tmovq (%rdi), %rdx")       # len
        e("\tleaq 8(%rdi), %rsi")      # data
        e("\tmovq $1, %rdi")
        e("\tcall __write_all")
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
        e("\tmovq %rax, %rbx")          # magnitude (the sign is no longer needed)
        e("\tmovq %rax, %rsi")
        e("\tleaq .Lstr_minus(%rip), %rdi")
        e("\tcall __str_concat")       # '-' + magnitude
        e("\tmovq %rbx, %rdi")
        e("\tmovq %rax, %rbx")
        e("\tcall __str_drop")         # release the magnitude
        e("\tmovq %rbx, %rax")
        e(".Li2s_done:")
        e("\tpopq %rbx")
        e("\tleave")
        e("\tret")
        e("")
        # __bool_to_str: rdi != 0 -> a new reference to the static "true"/"false"
        # str cell.
        e("__bool_to_str:")
        e("\ttestq %rdi, %rdi")
        e("\tjz .Lb2s_false")
        e("\tleaq .Lstr_true(%rip), %rax")
        e("\tincq -8(%rax)")           # a new reference, like the other renderers
        e("\tret")
        e(".Lb2s_false:")
        e("\tleaq .Lstr_false(%rip), %rax")
        e("\tincq -8(%rax)")
        e("\tret")
        e("")
        # __str_drop: rdi = str cell. Decrement the refcount; free at zero (a
        # str owns nothing else). Static cells never reach zero (MYLA-18).
        # Clobbers only %rax, like __free.
        e("__str_drop:")
        e("\tdecq -8(%rdi)")
        e("\tjnz .Lsdrop_keep")
        e("\tjmp __free")
        e(".Lsdrop_keep:")
        e("\tret")
        e("")
        # --- heap: reference-counted cells over a lazily-mmap'd arena (v0.2.3b) ---
        # Each cell is  [size:8][refcount:8][value bytes...]  and the pointer we
        # hand around points at the value bytes, so size is at -16 and the refcount
        # at -8. Freed cells are reused, so a program that allocates and drops in
        # a loop runs in bounded memory: cells up to _SMALL_CELL_LIMIT bytes go on
        # LIFO free lists, one per 8-byte size class (`__free_buckets`, indexed by
        # byte offset = size). A larger cell is rounded up to a power of two and
        # goes on that power's list after them, so a freed cell serves any later
        # request of its class: an exact-fit list kept every cell of a new size
        # forever (MYLA-80). The same scheme as the self-hosted runtime. The arena
        # itself is anonymous mmap memory, zero-filled.
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
        e("\tja __trap_oom")
        e("\tmovq %rax, __heap_ptr(%rip)")
        e(f"\taddq ${_ARENA_BYTES}, %rax")
        e("\tmovq %rax, __heap_end(%rip)")
        e("\tpopq %rdi")
        e("\tret")
        e("")
        # __alloc: in %rdi = value-size in bytes; out %rax = value pointer (rc = 1).
        # Clobbers %rcx, %rsi, %r8 and %rdi.
        e("__alloc:")
        e("\taddq $7, %rdi")            # round value size up to a multiple of 8
        e("\tandq $-8, %rdi")
        e("\tmovq $8, %rax")            # at least 8: a free cell's value area
        e("\tcmpq %rax, %rdi")          # holds the free-list link
        e("\tcmovbq %rax, %rdi")
        e("\tmovq __heap_end(%rip), %rax")
        e("\ttestq %rax, %rax")
        e("\tjnz .Lalloc_search")
        e("\tcall __heap_init")
        e(".Lalloc_search:")
        e(f"\tcmpq ${_SMALL_CELL_LIMIT}, %rdi")
        e("\tja .Lalloc_large")
        e("\tleaq __free_buckets(%rip), %r8")
        e("\tmovq (%r8,%rdi), %rsi")    # head of this size's list, or 0
        e("\ttestq %rsi, %rsi")
        e("\tjz .Lalloc_bump")
        e("\tmovq (%rsi), %rax")        # pop: head = node.next
        e("\tmovq %rax, (%r8,%rdi)")
        e("\tmovq $1, -8(%rsi)")        # refcount = 1
        e("\tmovq %rsi, %rax")
        e("\tret")
        e(".Lalloc_large:")             # round up to 2^k, k = bitlen(size - 1)
        e("\tleaq -1(%rdi), %rcx")
        e("\tbsrq %rcx, %rcx")
        e("\taddq $1, %rcx")
        e("\tmovq $1, %rdi")
        e("\tshlq %cl, %rdi")           # the class size
        e(f"\tleaq __free_buckets+{_SMALL_CELL_LIMIT + 8}(%rip), %r8")
        e("\tmovq (%r8,%rcx,8), %rsi")  # head of this power's list, or 0
        e("\ttestq %rsi, %rsi")
        e("\tjz .Lalloc_bump")
        e("\tmovq (%rsi), %rax")        # pop
        e("\tmovq %rax, (%r8,%rcx,8)")
        e("\tmovq $1, -8(%rsi)")        # refcount = 1
        e("\tmovq %rsi, %rax")
        e("\tret")
        e(".Lalloc_bump:")
        e("\tmovq __heap_ptr(%rip), %rax")
        e("\tleaq 16(%rax,%rdi), %rcx") # new top = base + header(16) + size
        e("\tcmpq __heap_end(%rip), %rcx")
        e("\tja __trap_oom")            # out of arena
        e("\tmovq %rcx, __heap_ptr(%rip)")
        e("\tmovq %rdi, (%rax)")        # header: size
        e("\tmovq $1, 8(%rax)")         # header: refcount
        e("\tleaq 16(%rax), %rax")      # value pointer = base + 16
        e("\tret")
        e("")
        # __free: in %rdi = value pointer; push the cell onto its free list.
        # Clobbers only %rax: drop sequences walk aggregates through other
        # caller-saved registers (e.g. %rcx) across calls that end in __free.
        e("__free:")
        e("\tpushq %rcx")
        e("\tmovq -16(%rdi), %rcx")     # value size
        e(f"\tcmpq ${_SMALL_CELL_LIMIT}, %rcx")
        e("\tja .Lfree_large")
        e("\tleaq __free_buckets(%rip), %rax")
        e("\taddq %rcx, %rax")          # &bucket for this size
        e("\tmovq (%rax), %rcx")
        e("\tmovq %rcx, (%rdi)")        # node.next = old head
        e("\tmovq %rdi, (%rax)")        # head = node
        e("\tpopq %rcx")
        e("\tret")
        e(".Lfree_large:")              # its size is a power of two: 2^k
        e("\tbsrq %rcx, %rcx")          # k
        e(f"\tleaq __free_buckets+{_SMALL_CELL_LIMIT + 8}(%rip), %rax")
        e("\tleaq (%rax,%rcx,8), %rax") # &list head for 2^k
        e("\tmovq (%rax), %rcx")
        e("\tmovq %rcx, (%rdi)")        # node.next = old head
        e("\tmovq %rdi, (%rax)")        # head = node
        e("\tpopq %rcx")
        e("\tret")
        e("")
        # __func_retain: in %rdi = a closure env pointer (may be null). Bumps the
        # env cell's refcount. Clobbers only flags, so it is safe to call from a
        # retain walk. (v0.4.2)
        e("__func_retain:")
        e("\ttestq %rdi, %rdi")
        e("\tjz .Lfret_done")
        e("\tincq -8(%rdi)")
        e(".Lfret_done:")
        e("\tret")
        e("")
        # __func_drop: in %rdi = a closure env pointer (may be null). Decrements
        # the env cell's refcount and, at zero, tail-calls its stored drop fn
        # (env[0]), which drops the captures and frees the cell. (v0.4.2)
        e("__func_drop:")
        e("\ttestq %rdi, %rdi")
        e("\tjz .Lfdrop_done")
        e("\tdecq -8(%rdi)")
        e("\tjnz .Lfdrop_done")
        e("\tmovq (%rdi), %rax")        # drop_fn
        e("\tjmp *%rax")                # tail-call: returns to our caller
        e(".Lfdrop_done:")
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
        self._staged_drops = []
        self._loops = []   # (continue_label, break_label, drop_scope_depth)
        self._struct_ret = _is_aggregate(sig.ret)
        self._ret_type = sig.ret

        frame = self._layout_frame(decl)
        self._epilogue = f".Lret_{decl.name}"
        self._cur_file = self._file_number(getattr(decl, "source_path", None))

        self._emit(f"myla_{decl.name}:")
        self._emit_loc(decl)
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
        self._end_loc()
        self._emit("")
        self._drop_scopes.pop()
        self._scopes.pop()

    # -- debug line tables (MYLA-71) ------------------------------------------

    def _file_number(self, path: str | None) -> int | None:
        """The `.file` number of `path`, registering it on first use; None when
        line tables are off or the code has no source file."""
        if not self._debug or path is None:
            return None
        return self._files.setdefault(path, len(self._files) + 1)

    def _emit_loc(self, node: ast.Node) -> None:
        """Attribute the code that follows to `node`'s source position."""
        if self._cur_file is None or node.line <= 0:
            return
        loc = f".loc {self._cur_file} {node.line} {node.column}"
        if loc != self._last_loc:
            self._emit(loc)
            self._last_loc = loc

    def _end_loc(self) -> None:
        """Mark the code that follows as having no source line (line 0), so
        runtime helpers emitted after a function aren't attributed to it."""
        if self._cur_file is not None:
            self._emit(f".loc {self._cur_file} 0 0")
        self._cur_file = None
        self._last_loc = ""

    def _layout_frame(self, decl: ast.FunDecl) -> int:
        """Assign a unique stack slot to every local/temp; return frame size."""
        cursor = [0]

        def alloc(node, size: int) -> None:
            cursor[0] += size
            self._locals[id(node)] = -cursor[0]

        def stage(node, t: Type, inline: bool = False) -> None:
            # a value staged before it is stored (_stage_value)
            cursor[0] += self._size(t) if inline else self._stored_size(t)
            self._locals[f"staged:{id(node)}"] = -cursor[0]

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
                    stage(stmt, tgt.resolved_type)
                    cursor[0] += 8       # scratch for the map lvalue holder address
                    self._locals[f"mutholder:{id(stmt)}"] = -cursor[0]
                elif self._owns_heap(tgt.resolved_type):
                    stage(stmt, tgt.resolved_type, isinstance(tgt, ast.Name))
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
                elif getattr(expr, "func_ref", None) is not None:
                    alloc(expr, 16)            # `fun` as value: a fat-value temp
            elif isinstance(expr, ast.Lambda):
                alloc(expr, 16)                # the closure's fat-value temp
            elif isinstance(expr, ast.Unary):
                visit_expr(expr.operand)
            elif isinstance(expr, ast.Cast):
                visit_expr(expr.operand)
            elif isinstance(expr, ast.Binary):
                visit_expr(expr.left)
                visit_expr(expr.right)
                if isinstance(expr.resolved_type, StrType):
                    alloc(expr, 8)     # the concatenation's temp (MYLA-18)
            elif isinstance(expr, ast.Call):
                if getattr(expr, "indirect_call", False):
                    visit_expr(expr.callee)
                for a in expr.args:
                    visit_expr(a)
                rt = expr.resolved_type
                if _is_aggregate(rt) or self._owns_heap(rt):
                    alloc(expr, self._size(rt))
                if getattr(expr, "indirect_call", False):
                    cursor[0] += 8       # saved code_ptr across argument evaluation
                    self._locals[f"indcode:{id(expr)}"] = -cursor[0]
                    cursor[0] += 8       # saved env_ptr
                    self._locals[f"indenv:{id(expr)}"] = -cursor[0]
                if (isinstance(expr.callee, ast.Name)
                        and expr.callee.ident in ("push", "remove",
                                                  "append", "append_byte")):
                    cursor[0] += 8       # scratch to hold the lvalue holder address
                    self._locals[f"mutholder:{id(expr)}"] = -cursor[0]
                    if expr.callee.ident == "push":
                        stage(expr, expr.args[0].resolved_type.elem)
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
                stage(expr, expr.resolved_type.value)
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
        self._emit_loc(stmt)
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
            self._eval_scalar(stmt.cond)
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
        target = stmt.target
        t = target.resolved_type
        if isinstance(target, ast.Index) and isinstance(target.target.resolved_type, MapType):
            self._gen_map_set(stmt)               # m[k] = v (insert/update, CoW)
            return
        if self._owns_heap(t):
            # Take the new value (one reference) before releasing the old one,
            # which it may share or be part of (`p = p`, `o.a = o.a`).
            inline = isinstance(target, ast.Name)  # a variable holds even a boxed enum inline
            staged = self._locals[f"staged:{id(stmt)}"]
            self._stage_value(stmt.value, t, staged, inline)
            self._mut_place_addr(target)          # rax = &place (CoW, bounds-checked)
            self._emit("movq %rax, %rcx")
            self._drop_stored(t, inline)
            self._commit_staged(t, staged, inline)
        elif _is_aggregate(t):
            self._addr_of_aggregate(stmt.value)
            self._emit("pushq %rax")
            self._mut_place_addr(target)
            self._emit("movq %rax, %rdi")
            self._emit("popq %rsi")
            self._emit_copy(self._size(t))
        else:
            self._eval(stmt.value)
            self._emit("pushq %rax")
            self._mut_place_addr(target)
            self._emit("popq %rcx")
            self._emit("movq %rcx, (%rax)")
        self._drop_expr_temps(stmt.value)

    def _eval_scalar(self, expr: ast.Expr) -> None:
        """Evaluate a scalar `expr` that no statement end follows (a condition,
        a guard, a range bound) into %rax, and release its temporaries
        (MYLA-74)."""
        self._eval(expr)
        temps: list = []
        self._collect_expr_temps(expr, temps)
        if temps:
            self._emit("pushq %rax")
            for slot, t in temps:
                self._drop_value("rbp", slot, t)
            self._emit("popq %rax")

    def _gen_if(self, stmt: ast.If) -> None:
        end = self._label()
        self._eval_scalar(stmt.cond)
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
        # the reference is an owner a `return` from the body releases (break
        # and continue stop at the body scope; the loop's end releases it)
        self._drop_scopes.append([(mp, mt)])

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
        self._drop_scopes.pop()
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
        # the reference is an owner a `return` from the body releases (break
        # and continue stop at the body scope; the loop's end releases it,
        # MYLA-80)
        self._drop_scopes.append([(lp, lt)])

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
        self._drop_scopes.pop()
        self._drop_value("rbp", lp, lt)         # release the loop reference

    def _gen_for_range(self, stmt: ast.For) -> None:
        loop_t = stmt.start.resolved_type
        lv = self._loopvar_off(stmt)
        fe = self._forend_off(stmt)
        self._eval_scalar(stmt.start)
        self._emit(f"movq %rax, {lv}(%rbp)")
        self._eval_scalar(stmt.end)
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
        elif isinstance(expr, ast.Lambda):
            self._gen_lambda_value(expr)
            off = self._locals[id(expr)]
            self._emit(f"leaq {off}(%rbp), %rax")
        elif isinstance(expr, ast.Name) and getattr(expr, "func_ref", None) is not None:
            # a top-level `fun` used as a value: a fat value with a null env whose
            # code pointer is an env-ignoring thunk (shared calling convention)
            self._fnval_thunks.add(expr.func_ref)
            off = self._locals[id(expr)]
            self._emit(f"leaq myla_{expr.func_ref}__fnval(%rip), %rax")
            self._emit(f"movq %rax, {off}(%rbp)")
            self._emit(f"movq $0, {off + 8}(%rbp)")
            self._emit(f"leaq {off}(%rbp), %rax")
        elif isinstance(expr, ast.Name):
            entry = self._lookup(expr.ident)
            if entry[0] == "capture":
                _, env_off, cap_off, _ = entry
                self._emit(f"movq {env_off}(%rbp), %rax")
                if cap_off:
                    self._emit(f"addq ${cap_off}, %rax")
            elif entry[0] == "local":
                self._emit(f"leaq {entry[1]}(%rbp), %rax")
            else:  # aggregate param: slot holds a pointer
                self._emit(f"movq {entry[1]}(%rbp), %rax")
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
        staged = self._locals[f"staged:{id(expr)}"]
        for key, value in expr.entries:
            self._eval(key)                      # key, then value (MYLA-8)
            self._emit("pushq %rax")
            self._stage_value(value, vt, staged)
            self._emit("popq %rsi")
            self._emit(f"movq {slot}(%rbp), %rdi")  # cell
            self._emit(f"call {self._map_put_name(mt)}")  # rax=&value, rdx=found
            self._commit_map_value(vt, staged)

    # -- storing into containers ----------------------------------------------
    # A store into a list element, map value or builder evaluates the value
    # first and only then touches the container, as the interpreter does
    # (MYLA-4): the value may return early (`?`) or change the same container
    # (`push(xs, pop(xs))`), and neither may see a half-made slot. The new value
    # is also taken before the old one is released, so `xs[i] = xs[i]` is safe.

    def _stage_value(self, value: ast.Expr, t: Type, slot: int,
                     inline: bool = False) -> None:
        """Evaluate `value` into frame slot `slot` in its stored form
        (`_stored_size(t)` bytes), owning one reference to every heap cell it
        holds: a fresh box for a boxed enum, a retained copy of an inline
        aggregate, or a scalar or retained cell pointer. With `inline`, for a
        variable, even a boxed enum is staged as an inline copy."""
        if self._is_boxed(t) and not inline:
            self._box(value, t)                  # rax = fresh heap copy (rc=1)
            self._emit(f"movq %rax, {slot}(%rbp)")
        elif _is_aggregate(t):
            self._addr_of_aggregate(value)       # rax = src
            self._emit("movq %rax, %rsi")
            self._emit(f"leaq {slot}(%rbp), %rdi")
            self._emit_copy(self._size(t))
            self._retain("rbp", slot, t)
        else:
            self._eval(value)
            if self._owns_heap(t):
                self._emit("incq -8(%rax)")      # the container gets a reference
            self._emit(f"movq %rax, {slot}(%rbp)")
        # Until _commit_staged hands the value over, an early return (a `?` in
        # the key, the index or the container expression) must release it, and
        # the value's temporaries, which the statement's end would have dropped.
        temps: list = []
        self._collect_expr_temps(value, temps)
        drops = [lambda off=off, tt=tt: self._drop_value("rbp", off, tt)
                 for off, tt in temps]
        if self._owns_heap(t):
            drops.append(lambda: self._release(slot, t, inline))
        self._staged_drops.append(drops)

    def _commit_staged(self, t: Type, slot: int, inline: bool = False) -> None:
        """Move the value staged in `slot` into the storage at %rcx, which takes
        over its references."""
        self._staged_drops.pop()
        if _is_aggregate(t) and (inline or not self._is_boxed(t)):
            self._emit(f"leaq {slot}(%rbp), %rsi")
            self._emit("movq %rcx, %rdi")
            self._emit_copy(self._size(t))
        else:
            self._emit(f"movq {slot}(%rbp), %rax")
            self._emit("movq %rax, (%rcx)")

    def _drop_stored(self, t: Type, inline: bool = False) -> None:
        """Release the value of type `t` stored at %rcx (preserved). The walk
        keeps the address in callee-saved %rbx across the drop calls."""
        if self._owns_heap(t):
            self._emit("pushq %rbx")
            self._emit("movq %rcx, %rbx")
            self._release(0, t, inline, base="rbx")
            self._emit("movq %rbx, %rcx")
            self._emit("popq %rbx")

    def _release(self, off: int, t: Type, inline: bool, base: str = "rbp") -> None:
        """Release the value of type `t` at `off(%base)`: stored as a member
        (a boxed enum as its pointer) or, with `inline`, as a variable holds it."""
        if inline:
            self._drop_value(base, off, t)
        else:
            self._walk_member(base, off, t, self._drop_box)

    def _commit_map_value(self, vt: Type, slot: int) -> None:
        """After a map put (%rax = &value slot, %rdx = key already present):
        release the previous value if there was one, then move the staged value
        in."""
        self._emit("movq %rax, %rcx")
        if self._owns_heap(vt):
            fresh = self._label()
            self._emit("testq %rdx, %rdx")
            self._emit(f"jz {fresh}")
            self._drop_stored(vt)
            self._emit(f"{fresh}:")
        self._commit_staged(vt, slot)

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
        self._emit("jz __trap_key")          # key absent
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
        self._emit("jae __trap_index")       # i < 0 (huge unsigned) or i >= len
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
        self._emit("jae __trap_index")       # i < 0 (huge unsigned) or i >= len
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
        self._emit("jae __trap_index")
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
        self._emit("jz __trap_key")
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
            self._mut_place_addr(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            if foff:
                self._emit(f"addq ${foff}, %rax")
        elif isinstance(expr, ast.Index):
            self._mut_index_addr(expr)          # the element/value slot holds the ptr
        else:  # pragma: no cover - checker guarantees a valid lvalue
            raise ValueError("invalid list lvalue")

    def _mut_place_addr(self, expr: ast.Expr) -> None:
        """Leave the address of place `expr` (a variable, a field or a list
        element / map value, at any depth) in %rax, unsharing (CoW) every list
        and map cell on the path, so the write that follows doesn't reach other
        owners of the container (MYLA-3)."""
        if isinstance(expr, ast.Name):
            kind, off, _ = self._lookup(expr.ident)
            if kind == "local":
                self._emit(f"leaq {off}(%rbp), %rax")
            else:  # a `var self` aggregate param: the slot holds a pointer to
                # the caller's storage, so mutations write straight back to it.
                self._emit(f"movq {off}(%rbp), %rax")
        elif isinstance(expr, ast.FieldAccess):
            self._mut_place_addr(expr.target)
            foff = self._field_offset(expr.target.resolved_type.name, expr.field_name)
            if foff:
                self._emit(f"addq ${foff}, %rax")
        elif isinstance(expr, ast.Index):
            self._mut_index_addr(expr)
        else:  # pragma: no cover
            raise ValueError("invalid struct lvalue")

    def _gen_push(self, expr: ast.Call) -> None:
        arg0 = expr.args[0]
        lt = arg0.resolved_type
        et = lt.elem
        stride = self._stored_size(et)
        holder = self._locals[f"mutholder:{id(expr)}"]
        staged = self._locals[f"staged:{id(expr)}"]
        self._stage_value(expr.args[1], et, staged)
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
        self._emit("leaq 16(%rax,%rdx), %rcx")    # &elem (the fresh slot)
        self._commit_staged(et, staged)
        # The value temp (if any) is released by the enclosing statement's
        # `_drop_expr_temps`, which recurses into call arguments; dropping it
        # here too would double-free an owning temp (e.g. a closure or list).

    def _gen_sb_append_byte(self, expr: ast.Call) -> None:
        """`append_byte(sb, b)`: evaluate the byte, make `sb` unique (CoW), grow
        if full, store the packed byte and bump the length."""
        arg0 = expr.args[0]
        holder = self._locals[f"mutholder:{id(expr)}"]
        self._eval(expr.args[1])                  # byte value -> rax, first (MYLA-4)
        self._emit("pushq %rax")
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
        self._emit("popq %rcx")                   # byte value
        self._emit("movb %cl, 16(%rax,%rdx)")     # packed, stride 1
        # Arg temp released by the enclosing statement (see _gen_push).

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
        if len(expr.args) == 4:                   # append(sb, s, start, end) (MYLA-85)
            self._emit("pushq %rax")
            self._eval(expr.args[2])              # start -> rax
            self._emit("pushq %rax")
            self._eval(expr.args[3])              # end -> rax
            self._emit("movslq %eax, %rcx")       # (int32, sign-extended)
            self._emit("popq %rdx")
            self._emit("movslq %edx, %rdx")
            self._emit("popq %rsi")               # str
            self._emit("popq %rdi")               # builder cell
            self._emit("call __sb_extend_range")  # rax = (maybe reallocated) cell
        else:
            self._emit("movq %rax, %rsi")
            self._emit("popq %rdi")               # builder cell
            self._emit("call __sb_extend")        # rax = (maybe reallocated) cell
        self._emit(f"movq {holder}(%rbp), %rcx")
        self._emit("movq %rax, (%rcx)")           # publish the cell
        # Arg temp released by the enclosing statement (see _gen_push).

    def _gen_pop(self, expr: ast.Call) -> None:
        arg0 = expr.args[0]
        lt = arg0.resolved_type
        et = lt.elem
        stride = self._stored_size(et)
        self._mut_container_cell(arg0)            # rax = unique cell
        self._emit("movq (%rax), %rdx")           # len
        self._emit("testq %rdx, %rdx")
        self._emit("jz __trap_pop")               # pop from an empty list traps
        self._emit("decq %rdx")
        self._emit("movq %rdx, (%rax)")           # len -= 1
        self._emit(f"imulq ${stride}, %rdx")
        self._emit("leaq 16(%rax,%rdx), %rax")    # &elem (removed last element)
        if self._is_boxed(et):
            # The list held a box: copy the value out, give the copy its own
            # references, then release the box (MYLA-74).
            slot = self._locals[id(expr)]
            self._emit("movq (%rax), %rsi")
            self._emit("pushq %rsi")
            self._emit(f"leaq {slot}(%rbp), %rdi")
            self._emit_copy(self._size(et))
            self._retain("rbp", slot, et)
            self._emit("popq %rdi")
            self._emit(f"call __dropb_{et.name}")
        elif _is_aggregate(et):                   # copy out (ownership transfers)
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
        # Arg temp released by the enclosing statement (see _gen_push).

    def _gen_map_set(self, stmt: ast.Assign) -> None:
        """`m[key] = value` (insert or update): evaluate the value, make the map
        unique (CoW), grow it if inserting would exceed the load factor, then
        store the value, releasing the previous one if the key already existed."""
        target = stmt.target
        mt = target.target.resolved_type
        vt = mt.value
        holder = self._locals[f"mutholder:{id(stmt)}"]
        staged = self._locals[f"staged:{id(stmt)}"]
        self._stage_value(stmt.value, vt, staged)
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
        self._commit_map_value(vt, staged)
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
                self._retain("rbp", leaf_off, t)   # a list/map/builder leaf owns a reference
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
        # When an arm may write to the variable the scrutinee comes from
        # (`match xs { ys => push(xs, 1) }`), the copy holds its own references
        # (MYLA-2): the bindings borrow from the copy, and the write copies on
        # write instead of changing or freeing what they see. It is released
        # after the match, or by an early exit from an arm. Otherwise (no arm
        # writes it, or it is a temporary such as a `?` operand) the bindings
        # can safely borrow from the scrutinee itself.
        root_var = _place_root(expr.scrutinee)
        owns_copy = (root_var is not None and self._owns_heap(sst)
                     and any(_may_write([arm.guard, arm.body], root_var) for arm in expr.arms))
        if owns_copy:
            self._retain("rbp", root, sst)
        # The scrutinee's temporaries (a call's result, say) are dropped when
        # the statement ends; an arm that leaves early (`return`, `break`,
        # `continue`, a failing `?`) skips that, so it drops them (MYLA-74).
        temps: list = []
        self._collect_expr_temps(expr.scrutinee, temps)
        self._drop_scopes.append(([(root, sst)] if owns_copy else []) + temps)

        result_off = self._locals.get(f"matchres:{id(expr)}")
        result_type = expr.resolved_type
        end = self._label()
        for arm in expr.arms:
            arm_fail = self._label()
            self._match_pat(arm.pattern, root, sst, arm, arm_fail)
            # bindings borrow from the scrutinee copy: no owners of their own
            self._scopes.append(self._arm_scope(arm))
            self._drop_scopes.append([])
            if arm.guard is not None:
                self._eval_scalar(arm.guard)
                self._emit("testq %rax, %rax")
                self._emit(f"jz {arm_fail}")
            self._gen_arm_body(arm.body, result_off, result_type)
            self._emit(f"jmp {end}")
            self._drop_scopes.pop()
            self._scopes.pop()
            self._emit(f"{arm_fail}:")
        self._emit("jmp __trap_match")   # unreachable when the match is exhaustive
        self._emit(f"{end}:")
        self._drop_scopes.pop()
        if owns_copy:
            self._drop_value("rbp", root, sst)

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
        # An arm ending in `panic`/`unreachable` never produces the match's
        # value: generate the call alone, with nothing to store.
        if isinstance(body, ast.Block):
            self._open_scope()
            stmts = body.statements
            for i, s in enumerate(stmts):
                if (i == len(stmts) - 1 and isinstance(s, ast.ExprStmt)
                        and result_off is not None and not _is_diverging(s.expr)):
                    self._store_value(s.expr, result_off, result_type)
                    self._drop_expr_temps(s.expr)
                else:
                    self._gen_stmt(s)
            self._close_scope()
        elif result_off is not None and not _is_diverging(body):
            self._emit_loc(body)
            self._store_value(body, result_off, result_type)
            self._drop_expr_temps(body)
        elif _is_aggregate(body.resolved_type) and not _is_diverging(body):
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
        if isinstance(t, FuncType):
            # a function value's env pointer may be null (non-capturing); the
            # null-safe helper bumps the env cell's refcount.
            self._emit(f"movq {ptr_off}(%{base}), %rdi")
            self._emit("call __func_retain")
            return
        self._emit(f"movq {ptr_off}(%{base}), %rax")
        self._emit("incq -8(%rax)")

    def _drop_box(self, ptr_off: int, base: str, t: Type) -> None:
        """Release a heap-pointer leaf via its type-specific drop routine."""
        if isinstance(t, FuncType):
            self._emit(f"movq {ptr_off}(%{base}), %rdi")
            self._emit("call __func_drop")
            return
        self._emit(f"movq {ptr_off}(%{base}), %rdi")
        if isinstance(t, ListType):
            self._emit(f"call {self._list_drop_name(t)}")
        elif isinstance(t, MapType):
            self._emit(f"call {self._map_drop_name(t)}")
        elif isinstance(t, StringBuilderType):
            self._emit("call __sb_drop")
        elif isinstance(t, StrType):
            self._emit("call __str_drop")
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
        if self._is_boxed(ft) or isinstance(ft, _CELL_TYPES):
            on_box(off, base, ft)
        elif isinstance(ft, FuncType):
            # the refcounted env pointer is the second word of the fat value
            on_box(off + 8, base, ft)
        elif self._owns_heap(ft):
            self._emit_owned_walk(base, off, ft, on_box)

    def _retain(self, base: str, off: int, t: Type) -> None:
        if isinstance(t, _CELL_TYPES):           # cell ptr at off
            self._inc_box(off, base, t)
        elif isinstance(t, FuncType):
            self._inc_box(off + 8, base, t)
        elif self._owns_heap(t):
            self._emit_owned_walk(base, off, t, self._inc_box)

    def _drop_value(self, base: str, off: int, t: Type) -> None:
        if isinstance(t, _CELL_TYPES):
            self._drop_box(off, base, t)
        elif isinstance(t, FuncType):
            self._drop_box(off + 8, base, t)
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
        """Drop every owning local currently in scope (for an early `return`),
        and any value staged for a container store that hasn't been committed."""
        for drops in reversed(self._staged_drops):
            for drop in drops:
                drop()
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
            if expr.op not in ("&&", "||"):       # those release their own
                self._collect_expr_temps(expr.left, out)
                self._collect_expr_temps(expr.right, out)
        elif isinstance(expr, ast.Call):
            if getattr(expr, "indirect_call", False):
                self._collect_expr_temps(expr.callee, out)
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
            # the arm's value is retained into the result slot (MYLA-74)
            res = self._locals.get(f"matchres:{id(expr)}")
            if res is not None and self._owns_heap(expr.resolved_type):
                out.append((res, expr.resolved_type))

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
        e("\txorq %rdx, %rdx")             # the whole string: 0..slen
        e("\tmovq (%rsi), %rcx")
        # __sb_extend_range: the same for the bytes str[rdx..rcx]; traps unless
        # 0 <= start <= end <= slen (MYLA-85).
        e("__sb_extend_range:")
        e("\ttestq %rdx, %rdx")
        e("\tjl __trap_index")             # start < 0
        e("\tcmpq %rdx, %rcx")
        e("\tjl __trap_index")             # end < start
        e("\tcmpq (%rsi), %rcx")
        e("\tjg __trap_index")             # end > slen
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tpushq %r14")
        e("\tmovq %rdi, %rbx")             # cell
        e("\tleaq (%rsi,%rdx), %r12")      # str shifted by start: its bytes at 8(%r12)
        e("\tmovq %rcx, %r13")
        e("\tsubq %rdx, %r13")             # count = end - start
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
        if the key already existed else 0 (newly inserted, len incremented, and
        a `str` key retained). A free slot is guaranteed by the load factor
        invariant (< 0.75)."""
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
        if self._owns_heap(t.key):               # the map holds a reference (MYLA-18)
            self._emit("incq -8(%r13)")
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
        (rc=1); retain each occupied key and value, decrement the original's
        refcount."""
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
        if self._owns_heap(vt) or self._owns_heap(t.key):
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
            self._walk_member("rcx", 8, t.key, self._inc_box)
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
        self._move_key_from(t, "r15")
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

    def _move_key_from(self, t: MapType, slot: str) -> None:
        """After `__put_map` inserted the key of the old slot at `(%slot)` into a
        new cell, give back the reference put took: the key moved (MYLA-18).
        Preserves %rax."""
        if self._owns_heap(t.key):
            self._emit(f"movq 8(%{slot}), %rcx")
            self._emit("decq -8(%rcx)")          # the new cell still holds one

    def _emit_map_drop_helper(self, t: MapType) -> None:
        """`__drop_map_<m>`: %rdi = cell. Decrement the refcount; at zero, drop each
        occupied entry's key (a `str`) and value, and free the cell."""
        ss = self._map_slot_size(t)
        vt = t.value
        keep = self._label()
        self._emit(f"{self._map_drop_name(t)}:")
        self._emit("decq -8(%rdi)")
        self._emit(f"jnz {keep}")
        if self._owns_heap(vt) or self._owns_heap(t.key):
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
            self._walk_member("r14", 8, t.key, self._drop_box)
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
        the occupied keys (any order); the list holds a reference to each `str`
        key."""
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
        if self._owns_heap(t.key):
            self._emit("incq -8(%rcx)")
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
        self._move_key_from(t, "r15")
        self._emit("leaq 16(%r15), %rsi")         # &old value
        self._emit("movq %rax, %rdi")
        self._emit(f"movq ${vs // 8}, %rcx")
        self._emit("cld")
        self._emit("rep movsq")                   # move the value bytes over
        self._emit(f"jmp {skip}")
        self._emit(f"{drop}:")                     # the removed entry: release it
        if self._owns_heap(t.key):
            self._drop_value("r15", 8, t.key)
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
            if not isinstance(expr.resolved_type, CharType):
                self._wrap(expr.resolved_type)   # a char codepoint needs no wrapping
        elif isinstance(expr, ast.FloatLit):
            self._uses_float = True
            image = round_float(expr.value, expr.resolved_type)
            self._emit(f"movabsq ${_f64_bits(image)}, %rax")  # f64 image of {image}
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
                entry = self._lookup(expr.ident)
                if entry[0] == "capture":     # captured scalar: load via env
                    _, env_off, cap_off, _ = entry
                    self._emit(f"movq {env_off}(%rbp), %r10")
                    self._emit(f"movq {cap_off}(%r10), %rax")
                else:
                    self._emit(f"movq {entry[1]}(%rbp), %rax")
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
            self._gen_cast(expr)
        else:  # pragma: no cover
            raise ValueError(f"cannot evaluate {type(expr).__name__}")

    def _round_xmm0(self, t: Type) -> None:
        """Narrow %xmm0 to single precision when `t` is `float32` (round to
        nearest), then widen back to the f64 image we carry at runtime."""
        if isinstance(t, FloatType) and t.width == 32:
            self._emit("cvtsd2ss %xmm0, %xmm0")
            self._emit("cvtss2sd %xmm0, %xmm0")

    def _gen_cast(self, expr: ast.Cast) -> None:
        src = expr.operand.resolved_type
        target = expr.resolved_type
        self._eval(expr.operand)
        if isinstance(target, CharType):
            # int -> char: keep the codepoint value in %rax unchanged (unchecked).
            return
        if isinstance(src, CharType):
            # char -> int: the codepoint is already in %rax; wrap to the width.
            self._wrap(target)
            return
        if isinstance(target, FloatType):
            self._uses_float = True
            if isinstance(src, FloatType):
                # float -> float: the runtime image is already f64; only an
                # f64 -> f32 narrowing changes anything.
                self._emit("movq %rax, %xmm0")
                self._round_xmm0(target)
                self._emit("movq %xmm0, %rax")
            else:  # int -> float
                if not src.signed and src.width == 64:
                    # unsigned 64-bit with the high bit set can't go through the
                    # signed cvtsi2sd; use the round-to-odd halving trick.
                    direct = self._label()
                    done = self._label()
                    self._emit("testq %rax, %rax")
                    self._emit(f"jns {direct}")
                    self._emit("movq %rax, %rcx")
                    self._emit("shrq $1, %rcx")          # u >> 1
                    self._emit("andq $1, %rax")          # u & 1 (sticky bit)
                    self._emit("orq %rax, %rcx")         # round-to-odd of u/2
                    self._emit("cvtsi2sdq %rcx, %xmm0")
                    self._emit("addsd %xmm0, %xmm0")     # * 2
                    self._emit(f"jmp {done}")
                    self._emit(f"{direct}:")
                    self._emit("cvtsi2sdq %rax, %xmm0")
                    self._emit(f"{done}:")
                else:
                    self._emit("cvtsi2sdq %rax, %xmm0")
                self._round_xmm0(target)
                self._emit("movq %xmm0, %rax")
        elif isinstance(src, FloatType):
            self._float_to_int(target)
        else:  # int -> int
            self._wrap(target)

    def _float_to_int(self, t: IntType) -> None:
        """The float in %rax `as t`: truncate toward zero, clamp to the range
        of `t`, NaN gives 0 (D59, `types.float_to_int`). cvttsd2si alone
        returns 2^63 for anything outside the int64 range."""
        self._uses_float = True
        low = -(1 << (t.width - 1)) if t.signed else 0
        high = (1 << (t.width - 1 if t.signed else t.width)) - 1
        high_imm = high - (1 << 64) if high >= 1 << 63 else high   # all ones for uint64
        done = self._label()
        self._emit("movq %rax, %xmm0")
        self._emit("xorl %eax, %eax")
        self._emit("ucomisd %xmm0, %xmm0")
        self._emit(f"jp {done}")                     # NaN -> 0
        self._emit(f"movabsq ${_f64_imm(float(high + 1))}, %rcx")
        self._emit("movq %rcx, %xmm1")
        self._emit(f"movabsq ${high_imm}, %rax")
        self._emit("ucomisd %xmm1, %xmm0")
        self._emit(f"jae {done}")                    # x >= high + 1 -> high
        self._emit(f"movabsq ${_f64_imm(float(low))}, %rcx")
        self._emit("movq %rcx, %xmm1")
        self._emit(f"movabsq ${low}, %rax")
        self._emit("ucomisd %xmm1, %xmm0")
        self._emit(f"jbe {done}")                    # x <= low -> low
        if t.width == 64 and not t.signed:
            # 2^63 <= x < 2^64: convert x - 2^63, then set the top bit
            small = self._label()
            self._emit(f"movabsq ${_f64_imm(2.0 ** 63)}, %rcx")
            self._emit("movq %rcx, %xmm1")
            self._emit("ucomisd %xmm1, %xmm0")
            self._emit(f"jb {small}")
            self._emit("subsd %xmm1, %xmm0")
            self._emit("cvttsd2si %xmm0, %rax")
            self._emit("btcq $63, %rax")
            self._emit(f"jmp {done}")
            self._emit(f"{small}:")
        self._emit("cvttsd2si %xmm0, %rax")
        self._emit(f"{done}:")

    def _eval_unary(self, expr: ast.Unary) -> None:
        if expr.op == "-" and isinstance(expr.resolved_type, FloatType):
            self._uses_float = True
            self._eval(expr.operand)
            self._emit("movabsq $-9223372036854775808, %rcx")  # 0x8000…0 sign bit
            self._emit("xorq %rcx, %rax")
            return
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

        if isinstance(ltype, FloatType):
            self._eval_binary_float(expr)
            return

        if op in ("==", "!=") and isinstance(ltype, StrType):
            self._eval_operands(expr)
            self._emit("movq %rax, %rdi")
            self._emit("movq %rcx, %rsi")
            self._emit("call __str_eq")
            if op == "!=":
                self._emit("testq %rax, %rax")
                self._emit("sete %al")
                self._emit("movzbq %al, %rax")
            return

        if op == "+" and isinstance(ltype, StrType):
            self._eval_operands(expr)
            self._emit("movq %rax, %rdi")        # A
            self._emit("movq %rcx, %rsi")        # B
            self._emit("call __str_concat")      # rax = A + B (fresh heap str)
            # its temp: the statement's end releases it unless it's consumed
            self._emit(f"movq %rax, {self._locals[id(expr)]}(%rbp)")
            return

        self._eval_operands(expr)

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
            self._emit("jz __trap_div" if op == "/" else "jz __trap_mod")
            if ltype.signed:
                # x / -1 is -x and x % -1 is 0; idivq would trap on the
                # minimum (its quotient overflows), the language wraps (MYLA-5)
                divide, done = self._label(), self._label()
                self._emit("cmpq $-1, %rcx")
                self._emit(f"jne {divide}")
                self._emit("negq %rax" if op == "/" else "xorl %eax, %eax")
                self._emit(f"jmp {done}")
                self._emit(f"{divide}:")
                self._emit("cqo")
                self._emit("idivq %rcx")
                if op == "%":
                    self._emit("movq %rdx, %rax")
                self._emit(f"{done}:")
            else:
                self._emit("xorq %rdx, %rdx")
                self._emit("divq %rcx")
                if op == "%":
                    self._emit("movq %rdx, %rax")
            self._wrap(expr.resolved_type)
        elif op in _SET_MNEMONIC:
            signed_set, unsigned_set = _SET_MNEMONIC[op]
            # `char` compares as an unsigned codepoint; only IntType carries sign.
            signed = isinstance(ltype, IntType) and ltype.signed
            self._emit("cmpq %rcx, %rax")
            self._emit(f"{signed_set if signed else unsigned_set} %al")
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

    # set/and/or sequences for float comparisons via `ucomisd` (NaN-aware).
    # `<`/`<=`/`==` must additionally exclude the unordered (NaN) case (PF=1);
    # `>`/`>=` use seta/setae which are already false when unordered.
    _FCMP = {
        ">": [("seta", "%al")],
        ">=": [("setae", "%al")],
        "<": [("setb", "%al"), ("setnp", "%cl"), ("andb", "%cl, %al")],
        "<=": [("setbe", "%al"), ("setnp", "%cl"), ("andb", "%cl, %al")],
        "==": [("sete", "%al"), ("setnp", "%cl"), ("andb", "%cl, %al")],
        "!=": [("setne", "%al"), ("setp", "%cl"), ("orb", "%cl, %al")],
    }
    _FARITH = {"+": "addsd", "-": "subsd", "*": "mulsd", "/": "divsd"}

    def _eval_operands(self, expr: ast.Binary) -> None:
        """Evaluate the left operand into %rax and the right into %rcx, left
        to right (MYLA-8). With a literal operand the order can't be observed,
        and the right-first sequence is one instruction shorter."""
        if _is_literal(expr.left) or _is_literal(expr.right):
            self._eval(expr.right)
            self._emit("pushq %rax")
            self._eval(expr.left)
            self._emit("popq %rcx")
            return
        self._eval(expr.left)
        self._emit("pushq %rax")
        self._eval(expr.right)
        self._emit("movq %rax, %rcx")
        self._emit("popq %rax")

    def _eval_binary_float(self, expr: ast.Binary) -> None:
        """Float arithmetic/comparison (D56): operands are carried as f64 images
        in %rax; compute in XMM, then narrow `float32` results."""
        self._uses_float = True
        op = expr.op
        self._eval_operands(expr)
        self._emit("movq %rax, %xmm0")        # left
        self._emit("movq %rcx, %xmm1")        # right
        if op in self._FARITH:
            self._emit(f"{self._FARITH[op]} %xmm1, %xmm0")
            self._round_xmm0(expr.resolved_type)
            self._emit("movq %xmm0, %rax")
        elif op == "%":
            self._emit("call __fmod")          # fmod(xmm0, xmm1) -> xmm0
            self._round_xmm0(expr.resolved_type)
            self._emit("movq %xmm0, %rax")
        else:  # comparison -> 0/1 in %rax
            self._emit("ucomisd %xmm1, %xmm0")
            for mnem, ops in self._FCMP[op]:
                self._emit(f"{mnem} {ops}")
            self._emit("movzbq %al, %rax")

    def _eval_logical(self, expr: ast.Binary) -> None:
        short = self._label()
        end = self._label()
        # Each operand releases its own temporaries: the right one may not run,
        # so the statement's end can't (MYLA-74).
        if expr.op == "&&":
            self._eval_scalar(expr.left)
            self._emit("testq %rax, %rax")
            self._emit(f"jz {short}")
            self._eval_scalar(expr.right)
            self._emit("testq %rax, %rax")
            self._emit(f"jz {short}")
            self._emit("movq $1, %rax")
            self._emit(f"jmp {end}")
            self._emit(f"{short}:")
            self._emit("xorq %rax, %rax")
            self._emit(f"{end}:")
        else:  # "||"
            self._eval_scalar(expr.left)
            self._emit("testq %rax, %rax")
            self._emit(f"jnz {short}")
            self._eval_scalar(expr.right)
            self._emit("testq %rax, %rax")
            self._emit(f"jnz {short}")
            self._emit("xorq %rax, %rax")
            self._emit(f"jmp {end}")
            self._emit(f"{short}:")
            self._emit("movq $1, %rax")
            self._emit(f"{end}:")

    # -- function values, closures & indirect calls (v0.4.2) ----------------

    def _capture_layout(self, lam: ast.Lambda):
        """Env-cell layout for a lambda: returns (offsets, env_size, owns_any).
        Slot 0 (8 bytes) holds the drop fn; captures follow, each stored inline
        like a variable (a recursive enum too, not as a pointer)."""
        offsets: list[int] = []
        cur = 8
        owns = False
        for _name, t in lam.captures:
            offsets.append(cur)
            cur += self._size(t)
            if self._owns_heap(t):
                owns = True
        return offsets, cur, owns

    def _gen_lambda_value(self, lam: ast.Lambda) -> None:
        """Materialize a lambda's `(code_ptr, env_ptr)` fat value into its temp
        slot. A non-capturing lambda uses a null env; a capturing one allocates a
        refcounted env cell and copies/retains each captured value (D15)."""
        off = self._locals[id(lam)]
        code_label = "myla_" + lam.lifted_name
        self._lambda_files[id(lam)] = self._cur_file   # its body is generated later
        if not lam.captures:
            self._emit(f"leaq {code_label}(%rip), %rax")
            self._emit(f"movq %rax, {off}(%rbp)")
            self._emit(f"movq $0, {off + 8}(%rbp)")
            return
        offsets, env_size, owns = self._capture_layout(lam)
        self._emit(f"movq ${env_size}, %rdi")
        self._emit("call __alloc")                    # rax = env cell (rc=1)
        self._emit(f"movq %rax, {off + 8}(%rbp)")     # env_ptr
        self._emit(f"leaq {code_label}(%rip), %rcx")
        self._emit(f"movq %rcx, {off}(%rbp)")         # code_ptr
        drop_fn = ("myla_" + lam.lifted_name + "_env_drop") if owns else "__free"
        self._emit(f"leaq {drop_fn}(%rip), %rcx")
        self._emit("movq %rcx, (%rax)")               # env[0] = drop fn
        for (name, t), capoff in zip(lam.captures, offsets):
            self._store_capture(name, t, off, capoff)

    def _store_capture(self, name: str, t: Type, fat_off: int, capoff: int) -> None:
        """Copy the enclosing variable `name` into the env cell at `capoff`,
        becoming a new owner of any heap references it holds."""
        src = ast.Name(name)
        if _is_aggregate(t):
            self._addr_of_aggregate(src)              # rax = src address
            self._emit("movq %rax, %rsi")
            self._emit(f"movq {fat_off + 8}(%rbp), %rdi")
            if capoff:
                self._emit(f"addq ${capoff}, %rdi")
            self._emit_copy(self._size(t))
            self._emit(f"movq {fat_off + 8}(%rbp), %r8")
            self._retain("r8", capoff, t)
        else:
            self._eval(src)                           # value -> rax
            self._emit(f"movq {fat_off + 8}(%rbp), %rcx")
            self._emit(f"movq %rax, {capoff}(%rcx)")
            if self._owns_heap(t):
                self._emit(f"movq {fat_off + 8}(%rbp), %r8")
                self._retain("r8", capoff, t)

    def _gen_lambda_function(self, lam: ast.Lambda) -> None:
        """Emit a lambda's lifted top-level function `myla_<lifted>` whose hidden
        first argument is the env pointer; captured variables are read through it
        (v0.4.2). Mirrors `_gen_function`'s prologue/epilogue."""
        ft = lam.resolved_type
        ret = ft.ret
        self._locals = {}
        self._scopes = []
        self._drop_scopes = []
        self._staged_drops = []
        self._loops = []
        self._struct_ret = _is_aggregate(ret)
        self._ret_type = ret

        if isinstance(lam.body, ast.Block):
            body = lam.body
        else:
            body = ast.Block([ast.Return(lam.body).at(lam.line, lam.column)])
        synth = ast.FunDecl(lam.lifted_name, list(lam.params), None, body)
        frame = self._layout_frame(synth)
        self._epilogue = f".Lret_{lam.lifted_name}"
        self._cur_file = self._lambda_files.get(id(lam))

        self._emit(f"myla_{lam.lifted_name}:")
        self._emit_loc(lam)
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        if frame:
            self._emit(f"subq ${frame}, %rsp")

        self._scopes.append({})
        self._drop_scopes.append([])
        param_base = 1 if self._struct_ret else 0
        env_off = 16 + 8 * param_base          # the hidden env pointer
        for i, (param, ptype) in enumerate(zip(lam.params, ft.params)):
            offset = 16 + 8 * (param_base + 1 + i)
            self._scopes[-1][param.name] = ("param", offset, ptype)
        offsets, _env_size, owns = self._capture_layout(lam)
        for (cname, ctype), capoff in zip(lam.captures, offsets):
            self._scopes[-1][cname] = ("capture", env_off, capoff, ctype)

        self._gen_block(body)

        self._emit(f"{self._epilogue}:")
        self._emit("leave")
        self._emit("ret")
        self._end_loc()
        self._emit("")
        self._drop_scopes.pop()
        self._scopes.pop()

        if owns:
            self._emit_lambda_env_drop(lam, offsets)

    def _emit_fnval_thunk(self, name: str) -> None:
        """`myla_<fn>__fnval(env, args…)`: an adapter so a plain `fun` can be
        called through the closure convention. Drops the (ignored) env argument
        and forwards the rest to `myla_<fn>` (v0.4.2)."""
        sig = self._sig(name)
        struct_ret = _is_aggregate(sig.ret)
        nargs = len(sig.params)
        self._emit(f"myla_{name}__fnval:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        # incoming (from 16(%rbp)): [sret?], env, arg0, arg1, …
        arg0_off = 16 + 8 * ((1 if struct_ret else 0) + 1)
        for i in reversed(range(nargs)):
            self._emit(f"movq {arg0_off + 8 * i}(%rbp), %rax")
            self._emit("pushq %rax")
        if struct_ret:
            self._emit("movq 16(%rbp), %rax")     # sret pointer
            self._emit("pushq %rax")
        self._emit(f"call myla_{name}")
        cleanup = 8 * (nargs + (1 if struct_ret else 0))
        if cleanup:
            self._emit(f"addq ${cleanup}, %rsp")
        self._emit("leave")
        self._emit("ret")
        self._emit("")

    def _emit_lambda_env_drop(self, lam: ast.Lambda, offsets: list) -> None:
        """`myla_<lifted>_env_drop(%rdi = env)`: drop each owned capture, then
        tail-call `__free` on the cell."""
        self._emit(f"myla_{lam.lifted_name}_env_drop:")
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        self._emit("pushq %rbx")
        self._emit("movq %rdi, %rbx")
        for (cname, ctype), capoff in zip(lam.captures, offsets):
            if self._owns_heap(ctype):
                self._drop_value("rbx", capoff, ctype)
        self._emit("movq %rbx, %rdi")
        self._emit("popq %rbx")
        self._emit("leave")
        self._emit("jmp __free")
        self._emit("")

    def _gen_indirect_call(self, expr: ast.Call) -> None:
        """Call a function value `f(args)`: load `(code_ptr, env_ptr)` from the
        fat value and call `code_ptr(env_ptr, args…)` (env first, then the usual
        sret/argument convention)."""
        ft = expr.callee.resolved_type
        struct_ret = _is_aggregate(ft.ret)
        code_off = self._locals[f"indcode:{id(expr)}"]
        env_off = self._locals[f"indenv:{id(expr)}"]
        self._addr_of_aggregate(expr.callee)          # rax = &fat value
        self._emit("movq (%rax), %rcx")
        self._emit(f"movq %rcx, {code_off}(%rbp)")    # save code_ptr
        self._emit("movq 8(%rax), %rcx")
        self._emit(f"movq %rcx, {env_off}(%rbp)")     # save env_ptr

        logical: list = []
        if struct_ret:
            logical.append(("sret", self._locals[id(expr)]))
        logical.append(("env", env_off))
        for i, arg in enumerate(expr.args):
            logical.append(("arg", arg, ft.params[i]))
        self._store_call_words(logical)
        self._emit(f"call *{code_off}(%rbp)")
        self._emit(f"addq ${8 * len(logical)}, %rsp")

    def _gen_call(self, expr: ast.Call) -> None:
        if getattr(expr, "indirect_call", False):
            self._gen_indirect_call(expr)
            return
        callee = expr.callee
        assert isinstance(callee, ast.Name)
        name = callee.ident

        if name == "print":
            self._gen_print(expr.args[0])
            return

        if name == "__write":
            self._uses_write = True
            self._eval(expr.args[0])             # fd -> rax
            self._emit("pushq %rax")
            self._eval(expr.args[1])             # str cell pointer -> rax
            self._emit("movq %rax, %rsi")
            self._emit("popq %rdi")              # fd
            self._emit("movl %edi, %edi")        # (int32, zero-extended)
            self._emit("call __write")
            return
        if name == "__exit":
            self._eval(expr.args[0])             # exit code -> rax
            self._emit("movl %eax, %edi")        # status (int32)
            self._emit("movq $60, %rax")         # exit syscall
            self._emit("syscall")
            return
        if name == "__args":
            self._uses_args = True
            self._emit("call __args")            # rax = fresh [str] list cell
            return
        if name == "__read_file":
            self._uses_read_file = True
            self._eval(expr.args[0])             # path str cell -> rax
            self._emit("movq %rax, %rdi")
            self._emit("call __read_file")       # rax = contents str (errno -> global)
            return
        if name == "__io_errno":
            self._uses_io_errno = True
            self._emit("movq __io_errno_val(%rip), %rax")
            return
        if name == "__poll":
            self._uses_poll = True
            self._eval(expr.args[0])             # fd -> rax
            self._emit("pushq %rax")
            self._eval(expr.args[1])             # timeout -> rax
            self._emit("movslq %eax, %rsi")      # (int32, sign-extended)
            self._emit("popq %rdi")              # fd
            self._emit("call __poll")            # rax = 1, 0 or -1 (errno -> global)
            return
        if name == "__read":
            self._uses_read = True
            self._eval(expr.args[0])             # fd -> rax
            self._emit("pushq %rax")
            self._eval(expr.args[1])             # n -> rax
            self._emit("movslq %eax, %rsi")      # (int32, sign-extended)
            self._emit("popq %rdi")              # fd
            self._emit("movl %edi, %edi")        # (int32, zero-extended)
            self._emit("call __read")            # rax = fresh str (errno -> global)
            return

        if name == "__write_file":
            self._uses_write_file = True
            self._eval(expr.args[0])             # path str cell -> rax
            self._emit("pushq %rax")
            self._eval(expr.args[1])             # contents str cell -> rax
            self._emit("movq %rax, %rsi")        # contents
            self._emit("popq %rdi")              # path
            self._emit("call __write_file")      # errno -> global
            return

        if name == "__run":
            self._uses_run = True
            self._eval(expr.args[0])             # program str cell -> rax
            self._emit("pushq %rax")
            self._eval(expr.args[1])             # argv [str] list cell -> rax
            self._emit("movq %rax, %rsi")        # argv list cell
            self._emit("popq %rdi")              # program
            self._emit("call __run")             # rax = stdout [uint8] cell
            return
        if name == "__run_stderr":
            self._uses_run = True
            self._emit("movq __run_stderr_val(%rip), %rax")
            return
        if name == "__run_exit_code":
            self._uses_run = True
            self._emit("movslq __run_exit_val(%rip), %rax")
            return
        if name == "__run_signal":
            self._uses_run = True
            self._emit("movslq __run_signal_val(%rip), %rax")
            return
        if name == "__run_errno":
            self._uses_run = True
            self._emit("movslq __run_errno_val(%rip), %rax")
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
        if name == "chars":
            self._uses_str_chars = True
            self._eval(expr.args[0])             # str cell -> rax
            self._emit("movq %rax, %rdi")
            self._emit("call __str_chars")       # rax = fresh [char] list cell
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

        logical: list = []
        if struct_ret:
            logical.append(("sret", self._locals[id(expr)]))
        for i, arg in enumerate(expr.args):
            logical.append(("arg", arg, sig.params[i]))
        self._store_call_words(logical)
        self._emit(f"call myla_{name}")
        if logical:
            self._emit(f"addq ${8 * len(logical)}, %rsp")

    def _store_call_words(self, logical: list) -> None:
        """Put the outgoing argument words on the stack, the first at the
        lowest address, evaluating the arguments left to right (MYLA-8): the
        words are reserved, then filled in source order. When at most one word
        has effects or reads state (the others are literals, the sret pointer
        or the env), pushing them last to first is the same and shorter.
        Items: ("sret", slot), ("env", slot) or ("arg", expr, type)."""
        if not logical:
            return
        ordered = sum(1 for item in logical if item[0] == "arg" and not _is_literal(item[1])) > 1
        if ordered:
            self._emit(f"subq ${8 * len(logical)}, %rsp")
        for k in range(len(logical)) if ordered else reversed(range(len(logical))):
            item = logical[k]
            if item[0] == "sret":
                self._emit(f"leaq {item[1]}(%rbp), %rax")
            elif item[0] == "env":
                self._emit(f"movq {item[1]}(%rbp), %rax")
            else:
                _, arg, ptype = item
                if _is_aggregate(ptype):
                    self._addr_of_aggregate(arg)
                else:
                    self._eval(arg)
            self._emit(f"movq %rax, {8 * k}(%rsp)" if ordered else "pushq %rax")

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
        elif isinstance(t, FloatType):
            self._uses_float = True
            self._emit(f"movabsq ${_f64_bits(value)}, %rax")  # f64 image of {value}
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
        elif isinstance(t, FloatType):
            self._uses_float = True
            self._emit(f"movq ${9 if t.width == 32 else 17}, %rsi")  # sig digits
            self._emit("call __float_to_str")
            self._print_and_drop_str()
        elif isinstance(t, CharType):
            self._uses_char = True
            self._emit("call __char_to_str")     # rdi = codepoint -> rax = str
            self._print_and_drop_str()
        else:  # pragma: no cover - checker restricts print()
            raise ValueError("unprintable type")

    def _print_and_drop_str(self) -> None:
        """Print the fresh `str` in %rax, then release it."""
        self._emit("pushq %rax")
        self._emit("movq %rax, %rdi")
        self._emit("call __print_str")
        self._emit("popq %rdi")
        self._emit("call __str_drop")

    def _gen_render_to_str(self, arg: ast.Expr) -> bool:
        """Evaluate `arg` and leave a `str` pointer for its `print` rendering in
        %rax (used by format(): str passes through, int/bool are converted).
        True if the pointer is a fresh reference the caller must release."""
        self._eval(arg)
        t = arg.resolved_type
        if isinstance(t, StrType):
            return False                         # borrowed: the arg's own temp
        self._render_scalar(t)
        return True

    def _render_scalar(self, t: Type) -> None:
        """Convert the non-`str` value in %rax to a fresh `str` in %rax."""
        if isinstance(t, FloatType):
            self._uses_float = True
            self._emit("movq %rax, %rdi")
            self._emit(f"movq ${9 if t.width == 32 else 17}, %rsi")
            self._emit("call __float_to_str")
            return
        if isinstance(t, CharType):
            self._uses_char = True
            self._emit("movq %rax, %rdi")
            self._emit("call __char_to_str")
            return
        self._emit("movq %rax, %rdi")
        if isinstance(t, BoolType):
            self._emit("call __bool_to_str")
        else:  # IntType
            self._emit("call __int_to_str" if t.signed else "call __uint_to_str")

    def _gen_format(self, expr: ast.Call) -> None:
        """Build the `format(fmt, args…)` result by folding the literal segments
        and rendered arguments together with `__str_concat`. The running result
        is kept on the stack between pieces; a piece or running result that is
        a fresh reference is released once it has been concatenated (MYLA-18).
        The result is always a fresh reference."""
        fmt = expr.args[0].value
        pieces = _format_pieces(fmt)         # ('lit', text) | ('arg', index)
        rest = expr.args[1:]

        def emit_piece(piece) -> bool:
            kind, payload = piece
            if kind == "lit":
                label = self._string_label(payload)
                self._emit(f"leaq {label}(%rip), %rax")
                return False
            return self._gen_render_to_str(rest[payload])

        owned = emit_piece(pieces[0])        # result = first piece -> rax
        if len(pieces) == 1 and not owned:
            self._emit("incq -8(%rax)")      # the result is a new reference
        for piece in pieces[1:]:
            self._emit("pushq %rax")         # save running result (A)
            piece_owned = emit_piece(piece)  # next piece (B) -> rax
            self._emit("pushq %rax")
            self._emit("movq %rax, %rsi")    # B
            self._emit("movq 8(%rsp), %rdi") # A
            self._emit("call __str_concat")  # rax = A + B
            self._emit("popq %rdi")          # B
            if piece_owned:
                self._drop_str_keeping_rax()
            self._emit("popq %rdi")          # A
            if owned:
                self._drop_str_keeping_rax()
            owned = True

    def _drop_str_keeping_rax(self) -> None:
        """Release the `str` in %rdi, preserving %rax."""
        self._emit("pushq %rax")
        self._emit("call __str_drop")
        self._emit("popq %rax")

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

    # -- SSE2 float runtime (D56) -------------------------------------------
    # Emitted only when the program uses floats. The number→text routine mirrors
    # `types.format_float` exactly (same constants, same op order) so the native
    # output is byte-identical to the interpreter's.

    def _float_rodata(self) -> list[str]:
        out: list[str] = ["\t.align 8"]
        # 10**k high parts (k = _FF_MINK.._FF_MAXK) — also the plain f64 table.
        out.append("__pow10_hi:")
        out += [f"\t.quad {_f64_bits(hi)}" for hi, _lo in _FF_POW10_DD]
        out.append("__pow10_lo:")          # the double-double low corrections
        out += [f"\t.quad {_f64_bits(lo)}" for _hi, lo in _FF_POW10_DD]
        out.append(f"__fsplit:\n\t.quad {_f64_bits(_FF_SPLIT)}")  # 2**27 + 1
        out.append(f"__fbig:\n\t.quad {_f64_bits(_FF_BIG)}")      # 2**996
        out.append(f"__fup:\n\t.quad {_f64_bits(_FF_UP)}")        # 2**64
        out.append(f"__fdown:\n\t.quad {_f64_bits(_FF_DOWN)}")    # 2**-64
        return out

    def _emit_float_runtime(self) -> None:
        e = self.text.append
        e("")
        # __fmod: xmm0 = a, xmm1 = b -> xmm0 = fmod(a, b) via x87 `fprem`
        # (exact remainder, truncated toward zero — matches Python math.fmod).
        e("__fmod:")
        e("\tsubq $16, %rsp")
        e("\tmovsd %xmm1, (%rsp)")
        e("\tmovsd %xmm0, 8(%rsp)")
        e("\tfldl (%rsp)")                 # st0 = b
        e("\tfldl 8(%rsp)")                # st0 = a, st1 = b
        e(".Lfm_loop:")
        e("\tfprem")
        e("\tfnstsw %ax")
        e("\ttestb $0x04, %ah")            # C2 set => reduction incomplete
        e("\tjnz .Lfm_loop")
        e("\tfstpl 8(%rsp)")               # store result, pop -> st0 = b
        e("\tfstp %st(0)")                 # pop b
        e("\tmovsd 8(%rsp), %xmm0")
        e("\taddq $16, %rsp")
        e("\tret")
        e("")
        # __two_prod: xmm0=a, xmm1=b -> xmm0=p, xmm1=e with p+e == a*b exactly
        # (Dekker). Clobbers xmm2..xmm7; preserves xmm8. An operand above 2^996
        # would overflow the split: scale it down by 2^64 and the other up
        # (exact; mirrors types._ff_two_prod).
        e("__two_prod:")
        e("\tmovsd __fbig(%rip), %xmm7")
        e("\tucomisd %xmm7, %xmm0")
        e("\tjbe .Ltp_b")                   # a <= 2^996
        e("\tmulsd __fdown(%rip), %xmm0")
        e("\tmulsd __fup(%rip), %xmm1")
        e("\tjmp .Ltp_split")
        e(".Ltp_b:")
        e("\tucomisd %xmm7, %xmm1")
        e("\tjbe .Ltp_split")               # b <= 2^996
        e("\tmulsd __fup(%rip), %xmm0")
        e("\tmulsd __fdown(%rip), %xmm1")
        e(".Ltp_split:")
        e("\tmovsd __fsplit(%rip), %xmm7")  # S
        e("\tmovsd %xmm0, %xmm2")           # split a
        e("\tmulsd %xmm7, %xmm2")           # ca = S*a
        e("\tmovsd %xmm2, %xmm3")
        e("\tsubsd %xmm0, %xmm3")           # ca - a
        e("\tsubsd %xmm3, %xmm2")           # ahi = ca-(ca-a)
        e("\tmovsd %xmm0, %xmm3")
        e("\tsubsd %xmm2, %xmm3")           # alo = a - ahi
        e("\tmovsd %xmm1, %xmm4")           # split b
        e("\tmulsd %xmm7, %xmm4")           # cb = S*b
        e("\tmovsd %xmm4, %xmm5")
        e("\tsubsd %xmm1, %xmm5")           # cb - b
        e("\tsubsd %xmm5, %xmm4")           # bhi = cb-(cb-b)
        e("\tmovsd %xmm1, %xmm5")
        e("\tsubsd %xmm4, %xmm5")           # blo = b - bhi
        e("\tmulsd %xmm1, %xmm0")           # p = a*b
        e("\tmovsd %xmm2, %xmm6")           # ahi
        e("\tmulsd %xmm4, %xmm6")           # ahi*bhi
        e("\tsubsd %xmm0, %xmm6")           # ahi*bhi - p
        e("\tmovsd %xmm2, %xmm7")           # ahi
        e("\tmulsd %xmm5, %xmm7")           # ahi*blo
        e("\taddsd %xmm7, %xmm6")
        e("\tmovsd %xmm3, %xmm7")           # alo
        e("\tmulsd %xmm4, %xmm7")           # alo*bhi
        e("\taddsd %xmm7, %xmm6")
        e("\tmovsd %xmm3, %xmm7")           # alo
        e("\tmulsd %xmm5, %xmm7")           # alo*blo
        e("\taddsd %xmm7, %xmm6")
        e("\tmovsd %xmm6, %xmm1")           # e
        e("\tret")
        e("")
        # __fscale: xmm8 = m (magnitude), r12 = idx -> rax = round(m * 10**idx)
        # as an int64, using double-double scaling (split for very small m;
        # mirrors types._ff_scaled_int). Clobbers xmm0..xmm9.
        e("__fscale:")
        e("\txorpd %xmm9, %xmm9")           # e1 = 0
        e("\tcmpq $308, %r12")              # idx > _FF_MAXK ?
        e("\tjle .Lfsc_direct")
        e("\tmovsd %xmm8, %xmm0")           # a = m
        e("\tleaq __pow10_hi(%rip), %rax")
        e("\tmovsd 4184(%rax), %xmm1")      # hi(10**200), index 523
        e("\tcall __two_prod")
        e("\tleaq __pow10_lo(%rip), %rax")
        e("\tmovsd 4184(%rax), %xmm2")      # lo(10**200)
        e("\tmovsd %xmm8, %xmm3")
        e("\tmulsd %xmm2, %xmm3")           # m * lo
        e("\taddsd %xmm3, %xmm1")           # e1 = e + m*lo
        e("\tmovsd %xmm1, %xmm9")
        e("\tmovsd %xmm0, %xmm8")           # m <- p (double-double (p, e1))
        e("\tsubq $200, %r12")              # idx -= 200
        e(".Lfsc_direct:")
        e("\tleaq 323(%r12), %r11")         # table index = idx - _FF_MINK
        e("\tmovsd %xmm8, %xmm0")           # a = m
        e("\tleaq __pow10_hi(%rip), %rax")
        e("\tmovsd (%rax,%r11,8), %xmm1")   # hi(10**idx)
        e("\tcall __two_prod")
        e("\tleaq __pow10_lo(%rip), %rax")
        e("\tmovsd (%rax,%r11,8), %xmm2")   # lo(10**idx)
        e("\tmovsd %xmm8, %xmm3")
        e("\tmulsd %xmm2, %xmm3")           # m * lo
        e("\taddsd %xmm3, %xmm1")           # e += m*lo
        e("\tleaq __pow10_hi(%rip), %rax")
        e("\tmovsd (%rax,%r11,8), %xmm4")   # hi(10**idx)
        e("\tmulsd %xmm9, %xmm4")           # e1 * hi
        e("\taddsd %xmm4, %xmm1")           # e += e1*hi
        e("\tcvtsd2si %xmm0, %rax")         # llrint(p)
        e("\tcvtsd2si %xmm1, %rcx")         # llrint(e)
        e("\taddq %rcx, %rax")              # D = llrint(p) + llrint(e)
        e("\tret")
        e("")
        # __float_to_str: rdi = f64 image bits, rsi = P (sig digits) -> rax = heap
        # str [len:8][bytes], plain round-trippable decimal (mirrors format_float).
        e("__float_to_str:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tpushq %r14")
        e("\tpushq %r15")
        e("\tsubq $1088, %rsp")             # scratch: DIGBUF/OUTBUF below rbp
        e("\tmovq %rdi, %rbx")              # raw bits
        e("\tmovq %rsi, %r15")              # P
        e("\tmovq %rbx, %rax")
        e("\tmovabsq $0x7fffffffffffffff, %rcx")
        e("\tandq %rcx, %rax")              # absbits = bits & ~sign
        e("\tmovabsq $0x7ff0000000000000, %rcx")
        e("\tcmpq %rcx, %rax")
        e("\tja .Lf_nan")                   # absbits > inf bits -> NaN
        e("\tje .Lf_inf")                   # == inf bits -> +/- inf
        e("\ttestq %rax, %rax")
        e("\tjz .Lf_zero")                  # +/- 0
        e("\txorq %r14, %r14")              # neg flag
        e("\ttestq %rbx, %rbx")
        e("\tjns .Lf_pos")
        e("\tmovq $1, %r14")
        e(".Lf_pos:")
        e("\tmovq %rax, %xmm8")             # m = magnitude (f64 image)
        # e10 = max k in [MINK,MAXK] with pow10_hi[k] <= m (binary search).
        e("\txorq %r8, %r8")                # lo index = 0
        e("\tmovq $631, %r9")               # hi index = N-1
        e("\tmovq $-1, %r10")               # ridx (relative result), -1 = none
        e("\tleaq __pow10_hi(%rip), %r13")
        e(".Lf_bs:")
        e("\tcmpq %r9, %r8")
        e("\tjg .Lf_bsd")
        e("\tleaq (%r8,%r9), %r11")
        e("\tsarq $1, %r11")                # mid = (lo+hi)/2
        e("\tmovsd (%r13,%r11,8), %xmm0")   # pow10_hi[mid]
        e("\tucomisd %xmm0, %xmm8")         # m vs pow10_hi[mid]
        e("\tjb .Lf_bs_lo")                 # m < pow10[mid]
        e("\tmovq %r11, %r10")              # m >= : ridx = mid; lo = mid+1
        e("\tleaq 1(%r11), %r8")
        e("\tjmp .Lf_bs")
        e(".Lf_bs_lo:")
        e("\tleaq -1(%r11), %r9")           # hi = mid-1
        e("\tjmp .Lf_bs")
        e(".Lf_bsd:")
        # idx = (P-1) - _FF_MINK - ridx = (P-1) + 323 - ridx
        e("\tmovq %r15, %r12")
        e("\tdecq %r12")                    # P-1
        e("\taddq $323, %r12")              # (P-1) - MINK
        e("\tsubq %r10, %r12")              # idx
        e("\tcall __fscale")               # rax = D
        # renormalize against 10**(P-1) and 10**P
        e("\tmovq $1, %r8")                 # r8 = 10**(P-1)
        e("\tmovq %r15, %rcx")
        e("\tdecq %rcx")
        e(".Lf_p10:")
        e("\ttestq %rcx, %rcx")
        e("\tjz .Lf_p10d")
        e("\timulq $10, %r8")
        e("\tdecq %rcx")
        e("\tjmp .Lf_p10")
        e(".Lf_p10d:")
        e("\tleaq (%r8,%r8,4), %r9")
        e("\taddq %r9, %r9")                # r9 = 10**P
        e("\tcmpq %r9, %rax")               # D >= 10**P ?
        e("\tjb .Lf_norm2")
        e("\txorq %rdx, %rdx")
        e("\tmovq $10, %rcx")
        e("\tdivq %rcx")                    # D /= 10
        e("\tincq %r10")                    # e10 += 1
        e(".Lf_norm2:")
        e("\tcmpq %r8, %rax")               # D < 10**(P-1) ?
        e("\tjae .Lf_digits")
        e("\tmovq %r8, %rax")               # D = 10**(P-1)
        e(".Lf_digits:")
        # write P decimal digits of D, MSB-first, into DIGBUF (rbp-1088)
        e("\tleaq -1088(%rbp), %rdi")       # DIGBUF
        e("\tmovq %r15, %rcx")              # P
        e("\tleaq -1(%rdi,%rcx), %rsi")     # &DIGBUF[P-1]
        e("\tmovq $10, %r11")
        e(".Lf_dg:")
        e("\txorq %rdx, %rdx")
        e("\tdivq %r11")
        e("\taddb $48, %dl")
        e("\tmovb %dl, (%rsi)")
        e("\tdecq %rsi")
        e("\tdecq %rcx")
        e("\tjnz .Lf_dg")
        # nsig = P - trailing zeros (at least 1)
        e("\tmovq %r15, %rcx")              # nsig = P
        e("\tleaq -1088(%rbp), %rdi")       # DIGBUF
        e(".Lf_trim:")
        e("\tcmpq $1, %rcx")
        e("\tjle .Lf_trimd")
        e("\tmovzbl -1(%rdi,%rcx), %eax")
        e("\tcmpb $48, %al")
        e("\tjne .Lf_trimd")
        e("\tdecq %rcx")
        e("\tjmp .Lf_trim")
        e(".Lf_trimd:")
        e("\tmovq %rcx, %r8")               # r8 = nsig (n)
        e("\tleaq -323(%r10), %r13")        # r13 = e10 (absolute)
        # positional layout into OUTBUF (rbp-512); r12 = start, rdi = write ptr
        e("\tleaq -512(%rbp), %r12")        # OUTBUF
        e("\tmovq %r12, %rdi")
        e("\ttestq %r14, %r14")
        e("\tjz .Lf_nosign")
        e("\tmovb $45, (%rdi)")             # '-'
        e("\tincq %rdi")
        e(".Lf_nosign:")
        e("\tleaq -1088(%rbp), %rsi")       # src = DIGBUF
        e("\tcld")
        e("\tmovq %r8, %rax")
        e("\tdecq %rax")                    # n-1
        e("\tcmpq %rax, %r13")              # e10 vs n-1
        e("\tjge .Lf_brA")
        e("\ttestq %r13, %r13")
        e("\tjs .Lf_brC")
        # branch B: 0 <= e10 < n-1  ->  d[0:e10+1] '.' d[e10+1:]
        e("\tleaq 1(%r13), %rcx")           # e10+1 digits
        e("\trep movsb")
        e("\tmovb $46, (%rdi)")             # '.'
        e("\tincq %rdi")
        e("\tmovq %r8, %rcx")
        e("\tsubq %r13, %rcx")
        e("\tdecq %rcx")                    # n - e10 - 1
        e("\trep movsb")
        e("\tjmp .Lf_emit")
        e(".Lf_brA:")
        # integer with trailing zeros: copy n digits then (e10-n+1) zeros
        e("\tmovq %r8, %rcx")
        e("\trep movsb")
        e("\tmovq %r13, %rcx")
        e("\tsubq %r8, %rcx")
        e("\tincq %rcx")                    # e10 - n + 1
        e(".Lf_zA:")
        e("\ttestq %rcx, %rcx")
        e("\tjz .Lf_emit")
        e("\tmovb $48, (%rdi)")
        e("\tincq %rdi")
        e("\tdecq %rcx")
        e("\tjmp .Lf_zA")
        e(".Lf_brC:")
        # e10 < 0: "0." then (-e10-1) zeros then n digits
        e("\tmovb $48, (%rdi)")             # '0'
        e("\tincq %rdi")
        e("\tmovb $46, (%rdi)")             # '.'
        e("\tincq %rdi")
        e("\tmovq %r13, %rcx")
        e("\tnegq %rcx")
        e("\tdecq %rcx")                    # -e10-1
        e(".Lf_zC:")
        e("\ttestq %rcx, %rcx")
        e("\tjz .Lf_cC")
        e("\tmovb $48, (%rdi)")
        e("\tincq %rdi")
        e("\tdecq %rcx")
        e("\tjmp .Lf_zC")
        e(".Lf_cC:")
        e("\tmovq %r8, %rcx")               # copy n digits
        e("\trep movsb")
        e(".Lf_emit:")
        e("\tmovq %rdi, %r8")
        e("\tsubq %r12, %r8")               # len = end - start
        e("\tleaq 8(%r8), %rdi")            # alloc size = 8 + len
        e("\tpushq %r8")
        e("\tpushq %r12")
        e("\tcall __alloc")               # rax = heap cell
        e("\tpopq %r12")
        e("\tpopq %r8")
        e("\tmovq %r8, (%rax)")            # length
        e("\tleaq 8(%rax), %rdi")          # dst
        e("\tmovq %r12, %rsi")             # src = OUTBUF
        e("\tmovq %r8, %rcx")
        e("\tcld")
        e("\tpushq %rax")
        e("\trep movsb")
        e("\tpopq %rax")
        e("\tjmp .Lf_ret")
        e(".Lf_nan:")
        e("\tleaq .Lstr_nan(%rip), %rax")
        e("\tjmp .Lf_static")
        e(".Lf_inf:")
        e("\ttestq %rbx, %rbx")
        e("\tjs .Lf_ninf")
        e("\tleaq .Lstr_inf(%rip), %rax")
        e("\tjmp .Lf_static")
        e(".Lf_ninf:")
        e("\tleaq .Lstr_ninf(%rip), %rax")
        e("\tjmp .Lf_static")
        e(".Lf_zero:")
        e("\ttestq %rbx, %rbx")
        e("\tjs .Lf_nzero")
        e("\tleaq .Lstr_fzero(%rip), %rax")
        e("\tjmp .Lf_static")
        e(".Lf_nzero:")
        e("\tleaq .Lstr_fnzero(%rip), %rax")
        e(".Lf_static:")
        e("\tincq -8(%rax)")                # a new reference, like the heap path
        e(".Lf_ret:")
        e("\tleaq -40(%rbp), %rsp")
        e("\tpopq %r15")
        e("\tpopq %r14")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tpopq %rbp")
        e("\tret")
        e("")

    def _emit_char_runtime(self) -> None:
        """`__char_to_str`: rdi = Unicode scalar -> rax = a fresh heap str holding
        its UTF-8 bytes. Mirrors `types.char_utf8_bytes` exactly (same range
        thresholds and bit masks) so the interpreter and native output agree."""
        e = self.text.append
        e("")
        e("__char_to_str:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tsubq $16, %rsp")               # scratch for up to 4 UTF-8 bytes
        e("\tmovq %rdi, %rax")              # rax = codepoint
        e("\tcmpq $0x80, %rax")
        e("\tjae .Lc2s_2")
        # 1 byte: [cp]
        e("\tmovb %al, -8(%rbp)")
        e("\tmovq $1, %r8")
        e("\tjmp .Lc2s_emit")
        e(".Lc2s_2:")
        e("\tcmpq $0x800, %rax")
        e("\tjae .Lc2s_3")
        # 2 bytes: C0|(cp>>6), 80|(cp&3F)
        e("\tmovq %rax, %rcx")
        e("\tshrq $6, %rcx")
        e("\torq $0xC0, %rcx")
        e("\tmovb %cl, -8(%rbp)")
        e("\tmovq %rax, %rcx")
        e("\tandq $0x3F, %rcx")
        e("\torq $0x80, %rcx")
        e("\tmovb %cl, -7(%rbp)")
        e("\tmovq $2, %r8")
        e("\tjmp .Lc2s_emit")
        e(".Lc2s_3:")
        e("\tcmpq $0x10000, %rax")
        e("\tjae .Lc2s_4")
        # 3 bytes: E0|(cp>>12), 80|((cp>>6)&3F), 80|(cp&3F)
        e("\tmovq %rax, %rcx")
        e("\tshrq $12, %rcx")
        e("\torq $0xE0, %rcx")
        e("\tmovb %cl, -8(%rbp)")
        e("\tmovq %rax, %rcx")
        e("\tshrq $6, %rcx")
        e("\tandq $0x3F, %rcx")
        e("\torq $0x80, %rcx")
        e("\tmovb %cl, -7(%rbp)")
        e("\tmovq %rax, %rcx")
        e("\tandq $0x3F, %rcx")
        e("\torq $0x80, %rcx")
        e("\tmovb %cl, -6(%rbp)")
        e("\tmovq $3, %r8")
        e("\tjmp .Lc2s_emit")
        e(".Lc2s_4:")
        # 4 bytes: F0|((cp>>18)&07), 80|((cp>>12)&3F), 80|((cp>>6)&3F), 80|(cp&3F)
        e("\tmovq %rax, %rcx")
        e("\tshrq $18, %rcx")
        e("\tandq $0x07, %rcx")
        e("\torq $0xF0, %rcx")
        e("\tmovb %cl, -8(%rbp)")
        e("\tmovq %rax, %rcx")
        e("\tshrq $12, %rcx")
        e("\tandq $0x3F, %rcx")
        e("\torq $0x80, %rcx")
        e("\tmovb %cl, -7(%rbp)")
        e("\tmovq %rax, %rcx")
        e("\tshrq $6, %rcx")
        e("\tandq $0x3F, %rcx")
        e("\torq $0x80, %rcx")
        e("\tmovb %cl, -6(%rbp)")
        e("\tmovq %rax, %rcx")
        e("\tandq $0x3F, %rcx")
        e("\torq $0x80, %rcx")
        e("\tmovb %cl, -5(%rbp)")
        e("\tmovq $4, %r8")
        e(".Lc2s_emit:")
        e("\tleaq 8(%r8), %rdi")            # value size = 8 + len
        e("\tpushq %r8")
        e("\tcall __alloc")                 # rax = cell (rc=1)
        e("\tpopq %r8")
        e("\tmovq %r8, (%rax)")             # store length
        e("\tleaq 8(%rax), %rdi")           # dst = bytes region
        e("\tleaq -8(%rbp), %rsi")          # src = scratch
        e("\tmovq %r8, %rcx")
        e("\tcld")
        e("\tpushq %rax")
        e("\trep movsb")
        e("\tpopq %rax")
        e("\tleave")
        e("\tret")
        e("")

    def _emit_str_chars_runtime(self) -> None:
        """`__str_chars`: rdi = str cell [len:8][bytes] -> rax = a fresh `[char]`
        list cell [len:8][cap:8][cp:8 …]: the scalar of each well-formed UTF-8
        sequence, and U+FFFD for each byte that isn't part of one (a `str` read
        from a file needn't be UTF-8, MYLA-12; `_decode_chars` in the
        interpreter). Capacity is the byte length (an upper bound on the
        element count); length is the exact count."""
        e = self.text.append
        e("")
        e("__str_chars:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tpushq %r14")
        e("\tpushq %r15")
        e("\tmovq (%rdi), %r12")            # byte length
        e("\tleaq 8(%rdi), %rbx")           # src bytes
        e("\tmovq %r12, %rax")
        e("\tshlq $3, %rax")                # byte_len * 8
        e("\taddq $16, %rax")               # + header
        e("\tmovq %rax, %rdi")
        e("\tcall __alloc")                 # rax = list cell (rc=1)
        e("\tmovq %rax, %r13")
        e("\tmovq %r12, 8(%r13)")           # capacity = byte length
        e("\tleaq 16(%r13), %r15")          # dst element pointer
        e("\txorq %r14, %r14")              # byte index i = 0
        e(".Lsc_loop:")
        e("\tcmpq %r12, %r14")
        e("\tjae .Lsc_done")
        e("\tmovzbq (%rbx,%r14), %rax")     # b0
        e("\tcmpq $0x80, %rax")
        e("\tjb .Lsc_1")
        # a lead byte: rdx = sequence length, rcx = its payload bits,
        # r8 = the least scalar of that length (shorter is overlong)
        e("\tcmpq $0xC2, %rax")
        e("\tjb .Lsc_bad")
        e("\tcmpq $0xE0, %rax")
        e("\tjb .Lsc_lead2")
        e("\tcmpq $0xF0, %rax")
        e("\tjb .Lsc_lead3")
        e("\tcmpq $0xF5, %rax")
        e("\tjae .Lsc_bad")
        e("\tmovq %rax, %rcx")
        e("\tandq $0x07, %rcx")
        e("\tmovq $4, %rdx")
        e("\tmovq $0x10000, %r8")
        e("\tjmp .Lsc_seq")
        e(".Lsc_lead3:")
        e("\tmovq %rax, %rcx")
        e("\tandq $0x0F, %rcx")
        e("\tmovq $3, %rdx")
        e("\tmovq $0x800, %r8")
        e("\tjmp .Lsc_seq")
        e(".Lsc_lead2:")
        e("\tmovq %rax, %rcx")
        e("\tandq $0x1F, %rcx")
        e("\tmovq $2, %rdx")
        e("\tmovq $0x80, %r8")
        e(".Lsc_seq:")
        e("\tleaq (%r14,%rdx), %r9")        # end of the sequence
        e("\tcmpq %r12, %r9")
        e("\tja .Lsc_bad")                  # cut off by the end of the string
        e("\tleaq (%rbx,%r14), %r11")
        e("\tmovq $1, %r10")
        e(".Lsc_cont:")
        e("\tmovzbq (%r11,%r10), %rax")
        e("\tmovq %rax, %rsi")
        e("\tandq $0xC0, %rsi")
        e("\tcmpq $0x80, %rsi")
        e("\tjne .Lsc_bad")                 # not a continuation byte
        e("\tshlq $6, %rcx")
        e("\tandq $0x3F, %rax")
        e("\torq %rax, %rcx")
        e("\tincq %r10")
        e("\tcmpq %rdx, %r10")
        e("\tjb .Lsc_cont")
        e("\tcmpq %r8, %rcx")
        e("\tjb .Lsc_bad")                  # overlong
        e("\tcmpq $0x10FFFF, %rcx")
        e("\tja .Lsc_bad")
        e("\tmovq %rcx, %rax")
        e("\tandq $-2048, %rax")
        e("\tcmpq $0xD800, %rax")
        e("\tje .Lsc_bad")                  # a surrogate
        e("\tmovq %r9, %r14")
        e("\tjmp .Lsc_store")
        e(".Lsc_bad:")
        e("\tmovq $0xFFFD, %rcx")           # U+FFFD for this byte
        e("\tincq %r14")
        e("\tjmp .Lsc_store")
        e(".Lsc_1:")
        e("\tmovq %rax, %rcx")              # cp = b0
        e("\tincq %r14")
        e(".Lsc_store:")
        e("\tmovq %rcx, (%r15)")
        e("\taddq $8, %r15")
        e("\tjmp .Lsc_loop")
        e(".Lsc_done:")
        e("\tmovq %r15, %rax")              # len = (dst - base - 16) / 8
        e("\tsubq %r13, %rax")
        e("\tsubq $16, %rax")
        e("\tshrq $3, %rax")
        e("\tmovq %rax, (%r13)")            # length = scalar count
        e("\tmovq %r13, %rax")              # return the list cell
        e("\tpopq %r15")
        e("\tpopq %r14")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tpopq %rbp")
        e("\tret")
        e("")

    def _emit_write_runtime(self) -> None:
        """`__write`: rdi = fd, rsi = str cell [len:8][bytes]; write the bytes to
        `fd` via the Linux `write` syscall (no trailing newline). Backs
        `std.io.write`/`println`/`eprint`/`eprintln` (D29)."""
        e = self.text.append
        e("__write:")
        e("\tmovq (%rsi), %rdx")        # len
        e("\tleaq 8(%rsi), %rsi")       # data pointer
        e("\tjmp __write_all")          # rdi = fd already set
        e("")

    def _emit_args_runtime(self) -> None:
        """`__args`: build a fresh `[str]` list cell from the argc/argv captured
        at `_start`. Each C string `argv[i]` is measured (strlen) and copied into
        a heap `str` cell [len:8][bytes]; the list holds the str pointers. Backs
        `std.process.args` (D29). Assumes well-formed (NUL-terminated) argv."""
        e = self.text.append
        e("__args:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")                  # argc
        e("\tpushq %r12")                  # argv base
        e("\tpushq %r13")                  # list cell
        e("\tpushq %r14")                  # i
        e("\tpushq %r15")                  # dst element pointer
        e("\tmovq __argc(%rip), %rbx")
        e("\tmovq __argv(%rip), %r12")
        e("\tmovq %rbx, %rdi")
        e("\tshlq $3, %rdi")               # argc * 8
        e("\taddq $16, %rdi")              # + [len][cap] header
        e("\tcall __alloc")                # rax = list cell (rc=1)
        e("\tmovq %rax, %r13")
        e("\tmovq %rbx, (%r13)")           # length = argc
        e("\tmovq %rbx, 8(%r13)")          # capacity = argc
        e("\tleaq 16(%r13), %r15")         # dst element pointer
        e("\txorq %r14, %r14")             # i = 0
        e(".La_loop:")
        e("\tcmpq %rbx, %r14")
        e("\tjae .La_done")
        e("\tmovq (%r12,%r14,8), %rsi")    # argv[i] (C string pointer)
        e("\txorq %rcx, %rcx")             # strlen
        e(".La_strlen:")
        e("\tmovb (%rsi,%rcx), %al")
        e("\ttestb %al, %al")
        e("\tjz .La_haslen")
        e("\tincq %rcx")
        e("\tjmp .La_strlen")
        e(".La_haslen:")
        e("\tpushq %rsi")                  # save src pointer
        e("\tpushq %rcx")                  # save length
        e("\tleaq 8(%rcx), %rdi")          # str cell size = 8 + len
        e("\tcall __alloc")                # rax = str cell (rc=1)
        e("\tpopq %rcx")                   # length
        e("\tpopq %rsi")                   # src pointer
        e("\tmovq %rcx, (%rax)")           # str length
        e("\tleaq 8(%rax), %rdi")          # dst bytes
        e(".La_copy:")
        e("\ttestq %rcx, %rcx")
        e("\tjz .La_stored")
        e("\tmovb (%rsi), %dl")
        e("\tmovb %dl, (%rdi)")
        e("\tincq %rsi")
        e("\tincq %rdi")
        e("\tdecq %rcx")
        e("\tjmp .La_copy")
        e(".La_stored:")
        e("\tmovq %rax, (%r15)")           # list element = str cell pointer
        e("\taddq $8, %r15")
        e("\tincq %r14")
        e("\tjmp .La_loop")
        e(".La_done:")
        e("\tmovq %r13, %rax")             # return the list cell
        e("\tpopq %r15")
        e("\tpopq %r14")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tpopq %rbp")
        e("\tret")
        e("")

    def _emit_read_file_runtime(self) -> None:
        """`__read_file`: rdi = path str cell -> rax = a fresh `str` cell with the
        whole file's bytes (rc=1); `__io_errno_val` is set to 0 on success or the
        positive errno on failure (open/read). Uses open(2)/fstat(5)/read(0)/
        close(3); the path is NUL-terminated on the stack first. Backs
        `std.fs.read_to_string` (D29). On any error a valid (possibly empty) str
        is still returned so the Myla wrapper can branch on the errno."""
        e = self.text.append
        e("__read_file:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tpushq %r14")
        e("\tpushq %r15")
        e("\tmovq $0, __io_errno_val(%rip)")    # clear errno
        # build a NUL-terminated copy of the path on the stack
        e("\tmovq (%rdi), %r12")               # path length
        e("\tleaq 8(%rdi), %r13")              # path bytes (src)
        e("\tleaq 16(%r12), %rax")             # >= len + 1, with slack
        e("\tandq $-16, %rax")                 # 16-byte aligned size
        e("\tsubq %rax, %rsp")                 # carve stack
        e("\tmovq %rsp, %r14")                 # dst path buffer
        e("\txorq %rcx, %rcx")
        e(".Lrf_pcopy:")
        e("\tcmpq %r12, %rcx")
        e("\tjae .Lrf_pdone")
        e("\tmovb (%r13,%rcx), %dl")
        e("\tmovb %dl, (%r14,%rcx)")
        e("\tincq %rcx")
        e("\tjmp .Lrf_pcopy")
        e(".Lrf_pdone:")
        e("\tmovb $0, (%r14,%r12)")            # NUL terminator
        # open(path, O_RDONLY, 0)
        e("\tmovq $2, %rax")                   # sys_open
        e("\tmovq %r14, %rdi")
        e("\txorq %rsi, %rsi")                 # O_RDONLY
        e("\txorq %rdx, %rdx")
        e("\tsyscall")
        e("\ttestq %rax, %rax")
        e("\tjs .Lrf_open_err")                # rax < 0 -> -errno
        e("\tmovq %rax, %rbx")                 # fd
        # fstat(fd, statbuf) -> st_size at offset 48
        e("\tsubq $144, %rsp")                 # statbuf
        e("\tmovq %rsp, %rsi")
        e("\tmovq $5, %rax")                   # sys_fstat
        e("\tmovq %rbx, %rdi")
        e("\tsyscall")
        e("\tmovq 48(%rsp), %r15")             # total size
        e("\taddq $144, %rsp")                 # discard statbuf
        # allocate the contents str cell: 8 (len) + size
        e("\tleaq 8(%r15), %rdi")
        e("\tcall __alloc")                    # rax = cell (rc=1)
        e("\tmovq %rax, %r13")
        e("\tmovq %r15, (%r13)")               # len = size (corrected below)
        e("\txorq %r14, %r14")                 # bytes read = 0
        e(".Lrf_read:")
        e("\tcmpq %r15, %r14")
        e("\tjae .Lrf_read_done")
        e("\tmovq $0, %rax")                   # sys_read
        e("\tmovq %rbx, %rdi")
        e("\tleaq 8(%r13), %rsi")
        e("\taddq %r14, %rsi")                 # dst + done
        e("\tmovq %r15, %rdx")
        e("\tsubq %r14, %rdx")                 # remaining
        e("\tsyscall")
        e("\ttestq %rax, %rax")
        e("\tjs .Lrf_read_err")                # < 0 -> error
        e("\tjz .Lrf_read_done")               # 0 -> EOF
        e("\taddq %rax, %r14")
        e("\tjmp .Lrf_read")
        e(".Lrf_read_done:")
        e("\tmovq %r14, (%r13)")               # actual length = bytes read
        e("\tmovq $3, %rax")                   # close(fd)
        e("\tmovq %rbx, %rdi")
        e("\tsyscall")
        e("\tmovq %r13, %rax")                 # return contents
        e("\tjmp .Lrf_ret")
        e(".Lrf_read_err:")
        e("\tnegq %rax")
        e("\tmovq %rax, __io_errno_val(%rip)")
        e("\tmovq $3, %rax")                   # close(fd)
        e("\tmovq %rbx, %rdi")
        e("\tsyscall")
        e("\tmovq %r13, %rax")                 # partial contents (ignored on err)
        e("\tjmp .Lrf_ret")
        e(".Lrf_open_err:")
        e("\tnegq %rax")
        e("\tmovq %rax, __io_errno_val(%rip)")
        e("\tmovq $8, %rdi")                   # empty str cell
        e("\tcall __alloc")
        e("\tmovq $0, (%rax)")                 # len = 0
        e(".Lrf_ret:")
        e("\tleaq -40(%rbp), %rsp")            # discard path buffer/statbuf
        e("\tpopq %r15")
        e("\tpopq %r14")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tpopq %rbp")
        e("\tret")
        e("")

    def _emit_read_runtime(self) -> None:
        """`__read`: rdi = fd, rsi = n -> rax = a fresh `str` cell (rc=1) with
        what one read(0) of at most n bytes returned (retried on EINTR): empty
        at the end of the input, when n <= 0, or on an error, which sets
        `__io_errno_val` (0 otherwise). Backs `std.io`'s reader (MYLA-78)."""
        e = self.text.append
        e("__read:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tmovq $0, __io_errno_val(%rip)")    # clear errno
        e("\tmovq %rdi, %rbx")                 # fd
        e("\tmovq %rsi, %r12")                 # n
        e("\ttestq %r12, %r12")
        e("\tjg .Lrd_alloc")
        e("\txorq %r12, %r12")                 # n <= 0: read nothing
        e(".Lrd_alloc:")
        e("\tleaq 8(%r12), %rdi")              # str cell: 8 (len) + n
        e("\tcall __alloc")                    # rax = cell (rc=1)
        e("\tmovq %rax, %r13")
        e("\tmovq $0, (%r13)")                 # len = 0 until the read
        e("\ttestq %r12, %r12")
        e("\tjz .Lrd_done")
        e(".Lrd_retry:")
        e("\txorq %rax, %rax")                 # sys_read
        e("\tmovq %rbx, %rdi")
        e("\tleaq 8(%r13), %rsi")
        e("\tmovq %r12, %rdx")
        e("\tsyscall")
        e("\tcmpq $-4, %rax")                  # EINTR: try again
        e("\tje .Lrd_retry")
        e("\ttestq %rax, %rax")
        e("\tjs .Lrd_err")
        e("\tmovq %rax, (%r13)")               # len = bytes read (0 at EOF)
        e("\tjmp .Lrd_done")
        e(".Lrd_err:")
        e("\tnegq %rax")
        e("\tmovq %rax, __io_errno_val(%rip)")
        e(".Lrd_done:")
        e("\tmovq %r13, %rax")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tpopq %rbp")
        e("\tret")
        e("")

    def _emit_poll_runtime(self) -> None:
        """`__poll`: rdi = fd, rsi = timeout in ms (negative: none) -> rax = 1
        when a read of fd won't block (input, its end, or an error such as a
        bad descriptor), 0 when the time ran out, -1 when poll(7) failed, which
        sets `__io_errno_val` (0 otherwise); retried on EINTR. Backs
        `std.io`'s `Reader.ready` (MYLA-80)."""
        e = self.text.append
        e("__poll:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tsubq $16, %rsp")
        e("\tmovq $0, __io_errno_val(%rip)")    # clear errno
        e("\tmovl %edi, (%rsp)")              # struct pollfd: fd
        e("\tmovw $1, 4(%rsp)")               # events = POLLIN
        e("\tmovw $0, 6(%rsp)")               # revents
        e("\tmovq %rsi, 8(%rsp)")             # timeout
        e(".Lpl_retry:")
        e("\tmovq $7, %rax")                  # sys_poll
        e("\tmovq %rsp, %rdi")
        e("\tmovq $1, %rsi")                  # one descriptor
        e("\tmovq 8(%rsp), %rdx")
        e("\tsyscall")
        e("\tcmpq $-4, %rax")                 # EINTR: try again
        e("\tje .Lpl_retry")
        e("\ttestq %rax, %rax")
        e("\tjs .Lpl_err")
        e("\tjz .Lpl_done")                   # timed out: 0
        e("\tmovq $1, %rax")
        e("\tjmp .Lpl_done")
        e(".Lpl_err:")
        e("\tnegq %rax")
        e("\tmovq %rax, __io_errno_val(%rip)")
        e("\tmovq $-1, %rax")
        e(".Lpl_done:")
        e("\tleave")
        e("\tret")
        e("")

    def _emit_write_file_runtime(self) -> None:
        """`__write_file`: rdi = path str cell, rsi = contents str cell -> void;
        `__io_errno_val` is set to 0 on success or the positive errno on failure.
        Uses open(2, O_WRONLY|O_CREAT|O_TRUNC, 0644)/write(1)/close(3); the path
        is NUL-terminated on the stack first. Backs `std.fs.write_to_file`."""
        e = self.text.append
        e("__write_file:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tpushq %r14")
        e("\tpushq %r15")
        e("\tmovq $0, __io_errno_val(%rip)")    # clear errno
        e("\tmovq %rsi, %r12")                 # contents str cell (save)
        # build a NUL-terminated copy of the path on the stack
        e("\tmovq (%rdi), %r13")               # path length
        e("\tleaq 8(%rdi), %r14")              # path bytes (src)
        e("\tleaq 16(%r13), %rax")             # >= len + 1, with slack
        e("\tandq $-16, %rax")                 # 16-byte aligned size
        e("\tsubq %rax, %rsp")                 # carve stack
        e("\tmovq %rsp, %r15")                 # dst path buffer
        e("\txorq %rcx, %rcx")
        e(".Lwf_pcopy:")
        e("\tcmpq %r13, %rcx")
        e("\tjae .Lwf_pdone")
        e("\tmovb (%r14,%rcx), %dl")
        e("\tmovb %dl, (%r15,%rcx)")
        e("\tincq %rcx")
        e("\tjmp .Lwf_pcopy")
        e(".Lwf_pdone:")
        e("\tmovb $0, (%r15,%r13)")            # NUL terminator
        # open(path, O_WRONLY|O_CREAT|O_TRUNC, 0644)
        e("\tmovq $2, %rax")                   # sys_open
        e("\tmovq %r15, %rdi")
        e("\tmovq $577, %rsi")                 # O_WRONLY|O_CREAT|O_TRUNC (0x241)
        e("\tmovq $420, %rdx")                 # mode 0644
        e("\tsyscall")
        e("\ttestq %rax, %rax")
        e("\tjs .Lwf_open_err")
        e("\tmovq %rax, %rbx")                 # fd
        e("\tmovq (%r12), %r15")               # contents length
        e("\tleaq 8(%r12), %r14")              # contents bytes
        e("\txorq %r13, %r13")                 # bytes written = 0
        e(".Lwf_write:")
        e("\tcmpq %r15, %r13")
        e("\tjae .Lwf_write_done")
        e("\tmovq $1, %rax")                   # sys_write
        e("\tmovq %rbx, %rdi")
        e("\tleaq (%r14,%r13), %rsi")          # data + written
        e("\tmovq %r15, %rdx")
        e("\tsubq %r13, %rdx")                 # remaining
        e("\tsyscall")
        e("\ttestq %rax, %rax")
        e("\tjs .Lwf_write_err")
        e("\taddq %rax, %r13")
        e("\tjmp .Lwf_write")
        e(".Lwf_write_done:")
        e("\tmovq $3, %rax")                   # close(fd)
        e("\tmovq %rbx, %rdi")
        e("\tsyscall")
        e("\tjmp .Lwf_ret")
        e(".Lwf_write_err:")
        e("\tnegq %rax")
        e("\tmovq %rax, __io_errno_val(%rip)")
        e("\tmovq $3, %rax")                   # close(fd)
        e("\tmovq %rbx, %rdi")
        e("\tsyscall")
        e("\tjmp .Lwf_ret")
        e(".Lwf_open_err:")
        e("\tnegq %rax")
        e("\tmovq %rax, __io_errno_val(%rip)")
        e(".Lwf_ret:")
        e("\tleaq -40(%rbp), %rsp")            # discard path buffer
        e("\tpopq %r15")
        e("\tpopq %r14")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tpopq %rbp")
        e("\tret")
        e("")

    def _emit_run_runtime(self) -> None:
        """`__run`: rdi = program str cell, rsi = argv `[str]` list cell -> rax =
        a fresh `[uint8]` list cell with the child's captured stdout (rc=1). The
        stderr `[uint8]` cell, the exit code (or -1 if signaled), the terminating
        signal (0 if exited), and the spawn errno (0 on success) are stored in
        `__run_stderr_val`/`__run_exit_val`/`__run_signal_val`/`__run_errno_val`
        for the `__run_*` primitives. Backs `std.process.run`/`Command` (D29).

        The program is located by the exact path given (no PATH search); the
        child inherits the parent environment (`__envp`). stdout and stderr are
        drained concurrently with poll(2) to avoid pipe-buffer deadlock, and an
        O_CLOEXEC \"exec error\" pipe reports an execve failure's errno precisely
        (so a missing/again-non-executable program maps to NotFound/EACCES)."""
        e = self.text.append
        # ---- growable [uint8] list helpers ---------------------------------
        # __u8list_new: rdi = capacity (elements) -> rax = empty list cell (rc=1)
        e("__u8list_new:")
        e("\tpushq %r12")
        e("\tmovq %rdi, %r12")             # capacity
        e("\tshlq $3, %rdi")               # cap * 8
        e("\taddq $16, %rdi")              # + [len][cap] header
        e("\tcall __alloc")                # rax = cell (rc=1)
        e("\tmovq $0, (%rax)")             # length = 0
        e("\tmovq %r12, 8(%rax)")          # capacity
        e("\tpopq %r12")
        e("\tret")
        e("")
        # __u8list_append: rdi = list cell, rsi = src bytes, rdx = n
        #   -> rax = the (possibly reallocated) list cell with n bytes appended,
        #   each zero-extended into an 8-byte element slot.
        e("__u8list_append:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tpushq %r14")
        e("\tpushq %r15")
        e("\tmovq %rdi, %r12")             # list cell
        e("\tmovq %rsi, %r13")             # src
        e("\tmovq %rdx, %r14")             # n
        e("\tmovq (%r12), %rbx")           # len
        e("\tmovq 8(%r12), %r15")          # cap
        e("\tmovq %rbx, %rax")
        e("\taddq %r14, %rax")             # need = len + n
        e("\tcmpq %r15, %rax")
        e("\tjbe .Lap_copy")
        # grow: newcap = smallest cap*2^k (>= 8) that reaches `need`
        e("\tmovq %r15, %rcx")
        e("\ttestq %rcx, %rcx")
        e("\tjnz .Lap_dbl")
        e("\tmovq $8, %rcx")
        e(".Lap_dbl:")
        e("\tshlq $1, %rcx")
        e("\tcmpq %rax, %rcx")
        e("\tjb .Lap_dbl")
        e("\tpushq %rcx")                  # save newcap
        e("\tmovq %rcx, %rdi")
        e("\tshlq $3, %rdi")               # newcap * 8
        e("\taddq $16, %rdi")              # + header
        e("\tcall __alloc")                # rax = new cell
        e("\tpopq %rcx")                   # newcap
        e("\tmovq %rax, %r15")             # new cell
        e("\tmovq %rbx, (%r15)")           # len (old)
        e("\tmovq %rcx, 8(%r15)")          # capacity = newcap
        e("\tleaq 16(%r12), %rsi")         # old elements
        e("\tleaq 16(%r15), %rdi")         # new elements
        e("\tmovq %rbx, %rcx")             # len
        e("\ttestq %rcx, %rcx")
        e("\tjz .Lap_freed")
        e(".Lap_cp:")
        e("\tmovq (%rsi), %rdx")
        e("\tmovq %rdx, (%rdi)")
        e("\taddq $8, %rsi")
        e("\taddq $8, %rdi")
        e("\tdecq %rcx")
        e("\tjnz .Lap_cp")
        e(".Lap_freed:")
        e("\tmovq %r12, %rdi")             # free the old cell
        e("\tcall __free")
        e("\tmovq %r15, %r12")             # list = new cell
        e(".Lap_copy:")
        e("\tleaq 16(%r12), %rdi")
        e("\tleaq (%rdi,%rbx,8), %rdi")    # dst = elems + len*8
        e("\txorq %rcx, %rcx")
        e(".Lap_bcopy:")
        e("\tcmpq %r14, %rcx")
        e("\tjae .Lap_bdone")
        e("\tmovzbq (%r13,%rcx), %rax")    # zero-extend byte -> slot
        e("\tmovq %rax, (%rdi)")
        e("\taddq $8, %rdi")
        e("\tincq %rcx")
        e("\tjmp .Lap_bcopy")
        e(".Lap_bdone:")
        e("\taddq %r14, %rbx")             # len += n
        e("\tmovq %rbx, (%r12)")
        e("\tmovq %r12, %rax")
        e("\tpopq %r15")
        e("\tpopq %r14")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tpopq %rbp")
        e("\tret")
        e("")
        # ---- __run ---------------------------------------------------------
        # stack frame (offsets from %rbp, below 40 bytes of saved rbx/r12-r15):
        #   -48 stdout_pipe [rd:-48, wr:-44]   -56 stderr_pipe [rd:-56, wr:-52]
        #   -64 exec_pipe   [rd:-64, wr:-60]   -72 child_pid    -80 status
        #   -88 argv C-array ptr               -96 path buffer ptr
        #   -112 pollfds (entry0 @-112, entry1 @-104)
        #   -4208 io_buffer (4096 bytes)
        e("__run:")
        e("\tpushq %rbp")
        e("\tmovq %rsp, %rbp")
        e("\tpushq %rbx")
        e("\tpushq %r12")
        e("\tpushq %r13")
        e("\tpushq %r14")
        e("\tpushq %r15")
        e("\tsubq $4176, %rsp")
        e("\tmovq %rdi, %r12")             # program str cell
        e("\tmovq %rsi, %r13")             # argv [str] list cell
        e("\tmovq $0, __run_errno_val(%rip)")
        e("\tmovq $0, __run_exit_val(%rip)")
        e("\tmovq $0, __run_signal_val(%rip)")
        # build the NUL-terminated argv pointer array on the heap
        e("\tmovq (%r13), %rbx")           # argc
        e("\tleaq 8(%rbx), %rdi")          # argc + 1
        e("\tshlq $3, %rdi")               # * 8
        e("\tcall __alloc")
        e("\tmovq %rax, -88(%rbp)")        # argv C-array base
        e("\txorq %r14, %r14")             # i = 0
        e(".Lrun_av:")
        e("\tcmpq %rbx, %r14")
        e("\tjae .Lrun_av_done")
        e("\tmovq 16(%r13,%r14,8), %r15")  # str cell argv[i]
        e("\tmovq (%r15), %rcx")           # str length
        e("\tleaq 1(%rcx), %rdi")          # + NUL
        e("\tcall __alloc")                # rax = C-string buffer
        e("\tmovq -88(%rbp), %rdx")
        e("\tmovq %rax, (%rdx,%r14,8)")    # argv_arr[i] = buffer
        e("\tmovq (%r15), %rcx")           # length (reload)
        e("\tleaq 8(%r15), %rsi")          # src bytes
        e("\tmovq %rax, %rdi")             # dst
        e("\txorq %rdx, %rdx")
        e(".Lrun_avc:")
        e("\tcmpq %rcx, %rdx")
        e("\tjae .Lrun_avcd")
        e("\tmovb (%rsi,%rdx), %r8b")
        e("\tmovb %r8b, (%rdi,%rdx)")
        e("\tincq %rdx")
        e("\tjmp .Lrun_avc")
        e(".Lrun_avcd:")
        e("\tmovb $0, (%rdi,%rcx)")        # NUL terminator
        e("\tincq %r14")
        e("\tjmp .Lrun_av")
        e(".Lrun_av_done:")
        e("\tmovq -88(%rbp), %rdx")
        e("\tmovq $0, (%rdx,%rbx,8)")      # argv[argc] = NULL
        # build the NUL-terminated program path on the heap
        e("\tmovq (%r12), %rcx")           # program length
        e("\tleaq 1(%rcx), %rdi")
        e("\tcall __alloc")
        e("\tmovq %rax, -96(%rbp)")        # path buffer
        e("\tmovq (%r12), %rcx")           # length (reload)
        e("\tleaq 8(%r12), %rsi")          # src bytes
        e("\tmovq %rax, %rdi")             # dst
        e("\txorq %rdx, %rdx")
        e(".Lrun_pc:")
        e("\tcmpq %rcx, %rdx")
        e("\tjae .Lrun_pcd")
        e("\tmovb (%rsi,%rdx), %r8b")
        e("\tmovb %r8b, (%rdi,%rdx)")
        e("\tincq %rdx")
        e("\tjmp .Lrun_pc")
        e(".Lrun_pcd:")
        e("\tmovb $0, (%rdi,%rcx)")        # NUL terminator
        # pipe(stdout), pipe(stderr), pipe2(exec, O_CLOEXEC)
        e("\tleaq -48(%rbp), %rdi")
        e("\tmovq $22, %rax")              # sys_pipe
        e("\tsyscall")
        e("\ttestq %rax, %rax")
        e("\tjs .Lrun_spawn_err")
        e("\tleaq -56(%rbp), %rdi")
        e("\tmovq $22, %rax")
        e("\tsyscall")
        e("\ttestq %rax, %rax")
        e("\tjs .Lrun_spawn_err")
        e("\tleaq -64(%rbp), %rdi")
        e("\tmovq $524288, %rsi")          # O_CLOEXEC
        e("\tmovq $293, %rax")             # sys_pipe2
        e("\tsyscall")
        e("\ttestq %rax, %rax")
        e("\tjs .Lrun_spawn_err")
        # fork
        e("\tmovq $57, %rax")              # sys_fork
        e("\tsyscall")
        e("\ttestq %rax, %rax")
        e("\tjs .Lrun_spawn_err")
        e("\tjz .Lrun_child")
        e("\tmovq %rax, -72(%rbp)")        # parent: child pid
        e("\tjmp .Lrun_parent")
        # ---- child ----
        e(".Lrun_child:")
        e("\tmovl -44(%rbp), %edi")        # dup2(stdout write, 1)
        e("\tmovl $1, %esi")
        e("\tmovq $33, %rax")
        e("\tsyscall")
        e("\tmovl -52(%rbp), %edi")        # dup2(stderr write, 2)
        e("\tmovl $2, %esi")
        e("\tmovq $33, %rax")
        e("\tsyscall")
        e("\tmovl -48(%rbp), %edi")        # close stdout read
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl -44(%rbp), %edi")        # close stdout write
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl -56(%rbp), %edi")        # close stderr read
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl -52(%rbp), %edi")        # close stderr write
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl -64(%rbp), %edi")        # close exec read
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovq -96(%rbp), %rdi")        # execve(path, argv, envp)
        e("\tmovq -88(%rbp), %rsi")
        e("\tmovq __envp(%rip), %rdx")
        e("\tmovq $59, %rax")
        e("\tsyscall")
        e("\tnegq %rax")                   # execve failed: rax = -errno -> errno
        e("\tmovl %eax, -80(%rbp)")        # stash errno
        e("\tmovl -60(%rbp), %edi")        # write errno to exec pipe
        e("\tleaq -80(%rbp), %rsi")
        e("\tmovq $4, %rdx")
        e("\tmovq $1, %rax")
        e("\tsyscall")
        e("\tmovq $127, %rdi")             # _exit(127)
        e("\tmovq $60, %rax")
        e("\tsyscall")
        # ---- parent ----
        e(".Lrun_parent:")
        e("\tmovl -44(%rbp), %edi")        # close stdout write
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl -52(%rbp), %edi")        # close stderr write
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl -60(%rbp), %edi")        # close exec write
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl -64(%rbp), %edi")        # read exec pipe: errno or EOF
        e("\tleaq -4208(%rbp), %rsi")
        e("\tmovq $4, %rdx")
        e("\tmovq $0, %rax")
        e("\tsyscall")
        e("\ttestq %rax, %rax")
        e("\tjle .Lrun_exec_ok")           # EOF (0) => execve succeeded
        e("\tmovl -4208(%rbp), %eax")      # execve failed with this errno
        e("\tmovl %eax, __run_errno_val(%rip)")
        e("\tmovl -64(%rbp), %edi")        # close exec read
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl -48(%rbp), %edi")        # close stdout read
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl -56(%rbp), %edi")        # close stderr read
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e(".Lrun_reap:")
        e("\tmovq -72(%rbp), %rdi")        # wait4(pid, &status, 0, 0) to reap
        e("\tleaq -80(%rbp), %rsi")
        e("\txorq %rdx, %rdx")
        e("\txorq %r10, %r10")
        e("\tmovq $61, %rax")
        e("\tsyscall")
        e("\tcmpq $-4, %rax")              # EINTR
        e("\tje .Lrun_reap")
        e("\tjmp .Lrun_empty_ret")
        e(".Lrun_exec_ok:")
        e("\tmovl -64(%rbp), %edi")        # close exec read
        e("\tmovq $3, %rax")
        e("\tsyscall")
        # allocate the stdout / stderr accumulator lists
        e("\tmovq $64, %rdi")
        e("\tcall __u8list_new")
        e("\tmovq %rax, %r14")             # stdout list
        e("\tmovq $64, %rdi")
        e("\tcall __u8list_new")
        e("\tmovq %rax, %r15")             # stderr list
        e("\tmovl -48(%rbp), %r12d")       # stdout read fd
        e("\tmovl -56(%rbp), %r13d")       # stderr read fd
        # poll/drain loop
        e(".Lrun_poll:")
        e("\tcmpl $-1, %r12d")
        e("\tjne .Lrun_open")
        e("\tcmpl $-1, %r13d")
        e("\tje .Lrun_drain_done")
        e(".Lrun_open:")
        e("\tmovl %r12d, -112(%rbp)")      # pollfd[0].fd
        e("\tmovw $1, -108(%rbp)")         # events = POLLIN
        e("\tmovw $0, -106(%rbp)")         # revents
        e("\tmovl %r13d, -104(%rbp)")      # pollfd[1].fd
        e("\tmovw $1, -100(%rbp)")         # events = POLLIN
        e("\tmovw $0, -98(%rbp)")          # revents
        e("\tleaq -112(%rbp), %rdi")
        e("\tmovq $2, %rsi")
        e("\tmovq $-1, %rdx")              # infinite timeout
        e("\tmovq $7, %rax")               # sys_poll
        e("\tsyscall")
        e("\tcmpq $-4, %rax")              # EINTR
        e("\tje .Lrun_poll")
        e("\ttestq %rax, %rax")
        e("\tjs .Lrun_drain_done")         # poll error: stop draining
        e("\tmovzwl -106(%rbp), %eax")     # stdout revents
        e("\ttestl %eax, %eax")
        e("\tjz .Lrun_do_err")
        e("\tcmpl $-1, %r12d")
        e("\tje .Lrun_do_err")
        e("\tmovl %r12d, %edi")            # read stdout
        e("\tleaq -4208(%rbp), %rsi")
        e("\tmovq $4096, %rdx")
        e("\tmovq $0, %rax")
        e("\tsyscall")
        e("\tcmpq $-4, %rax")              # EINTR
        e("\tje .Lrun_poll")
        e("\ttestq %rax, %rax")
        e("\tjg .Lrun_so_data")
        e("\tmovl %r12d, %edi")            # EOF/error: close stdout read
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl $-1, %r12d")
        e("\tjmp .Lrun_do_err")
        e(".Lrun_so_data:")
        e("\tmovq %r14, %rdi")
        e("\tleaq -4208(%rbp), %rsi")
        e("\tmovq %rax, %rdx")
        e("\tcall __u8list_append")
        e("\tmovq %rax, %r14")
        e(".Lrun_do_err:")
        e("\tmovzwl -98(%rbp), %eax")      # stderr revents
        e("\ttestl %eax, %eax")
        e("\tjz .Lrun_poll")
        e("\tcmpl $-1, %r13d")
        e("\tje .Lrun_poll")
        e("\tmovl %r13d, %edi")            # read stderr
        e("\tleaq -4208(%rbp), %rsi")
        e("\tmovq $4096, %rdx")
        e("\tmovq $0, %rax")
        e("\tsyscall")
        e("\tcmpq $-4, %rax")              # EINTR
        e("\tje .Lrun_poll")
        e("\ttestq %rax, %rax")
        e("\tjg .Lrun_se_data")
        e("\tmovl %r13d, %edi")            # EOF/error: close stderr read
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e("\tmovl $-1, %r13d")
        e("\tjmp .Lrun_poll")
        e(".Lrun_se_data:")
        e("\tmovq %r15, %rdi")
        e("\tleaq -4208(%rbp), %rsi")
        e("\tmovq %rax, %rdx")
        e("\tcall __u8list_append")
        e("\tmovq %rax, %r15")
        e("\tjmp .Lrun_poll")
        e(".Lrun_drain_done:")
        e("\tcmpl $-1, %r12d")             # close any still-open read ends
        e("\tje .Lrun_dc1")
        e("\tmovl %r12d, %edi")
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e(".Lrun_dc1:")
        e("\tcmpl $-1, %r13d")
        e("\tje .Lrun_dc2")
        e("\tmovl %r13d, %edi")
        e("\tmovq $3, %rax")
        e("\tsyscall")
        e(".Lrun_dc2:")
        e(".Lrun_wait:")
        e("\tmovq -72(%rbp), %rdi")        # wait4(pid, &status, 0, 0)
        e("\tleaq -80(%rbp), %rsi")
        e("\txorq %rdx, %rdx")
        e("\txorq %r10, %r10")
        e("\tmovq $61, %rax")
        e("\tsyscall")
        e("\tcmpq $-4, %rax")              # EINTR
        e("\tje .Lrun_wait")
        e("\tmovl -80(%rbp), %eax")        # decode wait status
        e("\tmovl %eax, %ecx")
        e("\tandl $127, %ecx")             # low 7 bits = terminating signal
        e("\ttestl %ecx, %ecx")
        e("\tjnz .Lrun_signaled")
        e("\tshrl $8, %eax")               # exited: (status >> 8) & 0xff
        e("\tandl $255, %eax")
        e("\tmovl %eax, __run_exit_val(%rip)")
        e("\tmovl $0, __run_signal_val(%rip)")
        e("\tjmp .Lrun_finish")
        e(".Lrun_signaled:")
        e("\tmovl %ecx, __run_signal_val(%rip)")
        e("\tmovl $-1, __run_exit_val(%rip)")
        e(".Lrun_finish:")
        e("\tmovq %r15, __run_stderr_val(%rip)")  # stash stderr
        e("\tmovq %r14, %rax")             # return stdout
        e("\tjmp .Lrun_ret")
        # spawn failed before/at fork or execve: report errno, return empties
        e(".Lrun_spawn_err:")
        e("\tnegq %rax")
        e("\tmovl %eax, __run_errno_val(%rip)")
        e(".Lrun_empty_ret:")
        e("\tmovq $0, %rdi")
        e("\tcall __u8list_new")
        e("\tmovq %rax, %r14")
        e("\tmovq $0, %rdi")
        e("\tcall __u8list_new")
        e("\tmovq %rax, %r15")
        e("\tmovq %r15, __run_stderr_val(%rip)")
        e("\tmovq %r14, %rax")
        e(".Lrun_ret:")
        e("\tleaq -40(%rbp), %rsp")
        e("\tpopq %r15")
        e("\tpopq %r14")
        e("\tpopq %r13")
        e("\tpopq %r12")
        e("\tpopq %rbx")
        e("\tpopq %rbp")
        e("\tret")
        e("")


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


def _asm_string(text: str) -> str:
    """Escape `text` for a double-quoted GAS string."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _place_root(expr: ast.Expr) -> str | None:
    """The variable a place (`x`, `x.f`, `x[i].g`) starts from, or None when
    `expr` is not a place."""
    while isinstance(expr, (ast.FieldAccess, ast.TupleIndex, ast.Index)):
        if getattr(expr, "enum_ctor", None) is not None:
            return None
        expr = expr.target
    if isinstance(expr, ast.Name) and getattr(expr, "func_ref", None) is None:
        return expr.ident
    return None


_MUTATING_BUILTINS = ("push", "pop", "remove", "append", "append_byte")


def _may_write(node, name: str) -> bool:
    """Whether running `node` may write to variable `name`, conservatively: an
    assignment to or into it, a mutating builtin on it, or a method call on it
    (the method may take `var self`). Myla has no references and closures
    capture by value, so nothing else can."""
    if isinstance(node, list):
        return any(_may_write(n, name) for n in node)
    if not isinstance(node, ast.Node):
        return False
    if isinstance(node, ast.Assign) and _place_root(node.target) == name:
        return True
    if isinstance(node, ast.Call):
        callee = node.callee
        if isinstance(callee, ast.FieldAccess) and _place_root(callee.target) == name:
            return True
        if (isinstance(callee, ast.Name) and callee.ident in _MUTATING_BUILTINS
                and node.args and _place_root(node.args[0]) == name):
            return True
    return any(_may_write(getattr(node, f.name), name) for f in dataclasses.fields(node))


def generate(checker: Checker, debug: bool = False) -> str:
    return CodeGen(checker, debug=debug).generate()
