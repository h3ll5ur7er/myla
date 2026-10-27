"""DWARF debug information for `myla build -g`: variables and types (MYLA-66).

The assembler builds the line table from the `.file`/`.loc` directives the code
generator emits (MYLA-71). This module writes the rest as assembler data: a
fixed `.debug_abbrev` table and one compile unit in `.debug_info` holding a
subprogram per Myla function (named by its label, `myla_<name>`), with its
parameters, captured variables, its locals in nested lexical blocks (a block
opens where a binding starts and ends with the Myla scope, so shadowing and
scoping are exact), and the types they use. Every slot has a fixed `%rbp`
offset, so the frame base is `%rbp` and a location is `DW_OP_fbreg <offset>`.

The unit says its language is Rust: gdb's Rust rules print values as Myla
writes them (`char` as `97 'a'`, `uint8` as a number, `true`, structs as
`Point {x: 1, y: 2}`, tuples, enums as `Shape::Circle(…)`, arrays), and its
expression syntax is close to Myla's.

How values are described (docs/Development/Debugging.md):

- A scalar sits in an 8-byte slot holding its canonical 64-bit value, so a base
  type of its real width at the slot's address reads it (little-endian); a
  signed integer is described as the whole slot, so that gdb's `set var` writes
  it sign-extended. A `float32` is kept as a double: a variable converts it
  (`DW_OP_GNU_deref_type`, `DW_OP_GNU_convert`), a field or element shows the
  double.
- A `str` or `StringBuilder` variable is shown as a Rust `&str`, a composite
  location whose two pieces (`data_ptr`, `length`) are computed from the cell.
- A list variable is an array located at the cell's elements, whose count is
  read from the cell's header through `DW_OP_push_object_address`.
- A map variable, and any heap value inside an aggregate or a list, is a
  pointer to a description of its cell (`p *x` shows it): gdb can't give array
  elements or fields types whose size depends on their value.

The self-hosted code generator emits the same (`selfhost/codegen.my`).
"""
from __future__ import annotations

from ..types import (
    BoolType, CharType, EnumType, FloatType, FuncType, IntType, ListType, MapType,
    StrType, StringBuilderType, StructType, TupleType, Type, type_name,
)

# Abbreviation codes, and the table: (code, DW_TAG, has children, [(DW_AT, DW_FORM)]).
CU, BASE, SUBPROGRAM, PARAM, VAR, BLOCK, PTR, VOIDPTR, STRUCT, MEMBER, ARRAY, SUBRANGE, \
    VARIANT_PART, VARIANT, TAG = range(1, 16)

_STRING, _DATA1, _DATA2, _DATA8, _UDATA, _ADDR, _REF4, _EXPRLOC, _SECOFF, _FLAG = (
    0x08, 0x0b, 0x05, 0x07, 0x0f, 0x01, 0x13, 0x18, 0x17, 0x19)
_NAME, _TYPE, _LOCATION, _BYTE_SIZE, _LOW_PC, _HIGH_PC = 0x03, 0x49, 0x02, 0x0b, 0x11, 0x12

ABBREVS = [
    (CU, 0x11, True, [(0x25, _STRING), (0x13, _DATA2), (_NAME, _STRING), (0x1b, _STRING),
                      (_LOW_PC, _ADDR), (_HIGH_PC, _DATA8), (0x10, _SECOFF)]),
    (BASE, 0x24, False, [(_NAME, _STRING), (0x3e, _DATA1), (_BYTE_SIZE, _DATA1)]),
    (SUBPROGRAM, 0x2e, True, [(_NAME, _STRING), (_LOW_PC, _ADDR), (_HIGH_PC, _DATA8),
                              (0x40, _EXPRLOC)]),
    (PARAM, 0x05, False, [(_NAME, _STRING), (_TYPE, _REF4), (_LOCATION, _EXPRLOC)]),
    (VAR, 0x34, False, [(_NAME, _STRING), (_TYPE, _REF4), (_LOCATION, _EXPRLOC)]),
    (BLOCK, 0x0b, True, [(_LOW_PC, _ADDR), (_HIGH_PC, _DATA8)]),
    (PTR, 0x0f, False, [(_BYTE_SIZE, _DATA1), (_TYPE, _REF4)]),
    (VOIDPTR, 0x0f, False, [(_BYTE_SIZE, _DATA1)]),
    (STRUCT, 0x13, True, [(_NAME, _STRING), (_BYTE_SIZE, _UDATA)]),
    (MEMBER, 0x0d, False, [(_NAME, _STRING), (_TYPE, _REF4), (0x38, _UDATA)]),
    (ARRAY, 0x01, True, [(_TYPE, _REF4), (0x51, _UDATA)]),
    (SUBRANGE, 0x21, False, [(0x37, _EXPRLOC)]),
    (VARIANT_PART, 0x33, True, [(0x15, _REF4)]),
    (VARIANT, 0x19, True, [(0x16, _UDATA)]),
    (TAG, 0x0d, False, [(_NAME, _STRING), (_TYPE, _REF4), (0x38, _UDATA), (0x34, _FLAG)]),
]

DW_LANG_RUST = 0x1c

# DWARF expression operators
_FBREG, _DEREF, _PLUS_UCONST, _STACK_VALUE, _PIECE = 0x91, 0x06, 0x23, 0x9f, 0x93
_PUSH_OBJECT_ADDRESS, _LIT0, _MINUS, _REG6 = 0x97, 0x30, 0x1c, 0x56
_GNU_DEREF_TYPE, _GNU_CONVERT = 0xf6, 0xf7

# DW_ATE encodings
_ATE_BOOLEAN, _ATE_FLOAT, _ATE_SIGNED, _ATE_UNSIGNED, _ATE_UTF = 0x02, 0x04, 0x05, 0x07, 0x10


def uleb(n: int) -> list[int]:
    out = []
    while True:
        b = n & 0x7f
        n >>= 7
        if n == 0:
            return out + [b]
        out.append(b | 0x80)


def sleb(n: int) -> list[int]:
    out = []
    while True:
        b = n & 0x7f
        n >>= 7
        if (n == 0 and not b & 0x40) or (n == -1 and b & 0x40):
            return out + [b]
        out.append(b | 0x80)


def abbrev_section() -> list[str]:
    out = ['\t.section .debug_abbrev,"",@progbits', ".Ldebug_abbrev0:"]
    for code, tag, children, attrs in ABBREVS:
        out.append(f"\t.uleb128 {code}, {tag}, {int(children)}")
        out.append("\t.uleb128 " + ", ".join(f"{a}, {f}" for a, f in attrs) + ", 0, 0")
    out.append("\t.byte 0")
    return out


def _string(text: str) -> str:
    return '\t.string "' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ref(label: str) -> str:
    return f"\t.long {label} - .Ldebug_info0"


def _is_aggregate(t: Type) -> bool:
    return isinstance(t, (StructType, TupleType, EnumType, FuncType))


class _Scope:
    """A Myla scope: the label its lexical blocks end at, how many it opened."""

    def __init__(self, end: str):
        self.end = end
        self.blocks = 0


class DebugInfo:
    """The `.debug_info` of one compile unit, built while the code generator
    walks the program. `cg` answers layout questions (`_size`, `_stored_size`,
    `_is_boxed`, `checker`); `emit` appends a line to the code (block labels)."""

    def __init__(self, cg, emit, display_names: dict[str, str]):
        self.cg = cg
        self.emit = emit
        self.display_names = display_names
        self.lines: list[str] = []           # the subprograms' DIEs
        self.types: dict[tuple, str] = {}    # type key -> DIE label
        self.pending: list[tuple[str, object]] = []
        self.scopes: list[_Scope] = []
        self.fn_end = ""
        self.last_block: tuple | None = None
        self.n = 0

    def _label(self, kind: str) -> str:
        self.n += 1
        return f".Ld{kind}{self.n}"

    # -- functions and scopes ------------------------------------------------

    def begin_function(self, symbol: str) -> None:
        self.fn_end = self._label("f")
        self.scopes = []
        self.lines += [f"\t.uleb128 {SUBPROGRAM}", _string(symbol), f"\t.quad {symbol}",
                       f"\t.quad {self.fn_end} - {symbol}", "\t.uleb128 1", f"\t.byte {_REG6}"]

    def end_function(self) -> None:
        """Close the subprogram; its end label goes after the function's code."""
        self.emit(f"{self.fn_end}:")
        self.lines.append("\t.byte 0")

    def push_scope(self) -> None:
        self.scopes.append(_Scope(self._label("e")))

    def pop_scope(self) -> None:
        scope = self.scopes.pop()
        if scope.blocks:
            self.emit(f"{scope.end}:")
            self.lines += ["\t.byte 0"] * scope.blocks

    def variable(self, name: str, entry: tuple, t: Type, whole_function: bool, param: bool) -> None:
        """Describe the binding `name` (a scope entry of the code generator:
        `("local", off, t)`, `("param", off, t)` or `("capture", env_off,
        cap_off, t)`). A parameter or a capture is visible in the whole
        function; another binding from here to the end of its scope, in a
        lexical block that starts at a label emitted now."""
        if name.startswith("__"):
            return
        if not whole_function:
            scope = self.scopes[-1]
            mark = (scope.end, len(self.cg.text))
            if self.last_block != mark:     # code since the last block opened here
                start = self._label("b")
                self.emit(f"{start}:")
                self.lines += [f"\t.uleb128 {BLOCK}", f"\t.quad {start}",
                               f"\t.quad {scope.end} - {start}"]
                scope.blocks += 1
                self.last_block = (scope.end, len(self.cg.text))
        ty, ops = self._variable_location(entry, t)
        self.lines += [f"\t.uleb128 {PARAM if param else VAR}", _string(name), _ref(ty)]
        self.lines += self._exprloc(ops)

    def _variable_location(self, entry: tuple, t: Type) -> tuple[str, list]:
        """The type DIE and the location expression of a variable."""
        if entry[0] == "capture":
            _, env_off, cap_off, _ = entry
            addr = [_FBREG, *sleb(env_off), _DEREF]
            if cap_off:
                addr += [_PLUS_UCONST, *uleb(cap_off)]
        elif entry[0] == "param" and _is_aggregate(t):
            addr = [_FBREG, *sleb(entry[1]), _DEREF]   # passed (or borrowed) by address
        else:
            addr = [_FBREG, *sleb(entry[1])]
        if isinstance(t, (StrType, StringBuilderType)):
            data = 8 if isinstance(t, StrType) else 16
            ops = (addr + [_DEREF, _PLUS_UCONST, data, _STACK_VALUE, _PIECE, 8]
                   + addr + [_DEREF, _DEREF, _STACK_VALUE, _PIECE, 8])
            return self._str_slice(), ops
        if isinstance(t, ListType):
            return self._items(t.elem), addr + [_DEREF, _PLUS_UCONST, 16]
        if isinstance(t, FloatType) and t.width == 32:
            f64 = self._base(FloatType(64))
            ops = addr + [_GNU_DEREF_TYPE, 8, ("ref", f64), _GNU_CONVERT,
                          ("ref", self._base(t)), _STACK_VALUE]
            return self._base(t), ops
        if isinstance(t, EnumType):
            return self._aggregate(t), addr      # a variable holds even a boxed enum inline
        return self._element(t), addr

    def _exprloc(self, ops: list) -> list[str]:
        """An exprloc: plain bytes, or (for DIE references) a length computed by
        the assembler."""
        if all(isinstance(op, int) for op in ops):
            return [f"\t.uleb128 {len(ops)}", "\t.byte " + ", ".join(str(b) for b in ops)]
        start, end = self._label("x"), self._label("x")
        out = [f"\t.uleb128 {end} - {start}", f"{start}:"]
        for op in ops:
            if isinstance(op, int):
                out.append(f"\t.byte {op}")
            else:
                out.append(f"\t.uleb128 {op[1]} - .Ldebug_info0")
        return out + [f"{end}:"]

    # -- types -------------------------------------------------------------------

    def display(self, t: Type) -> str:
        """`t` as Myla spells it, generic instances included (`Box<int32>`)."""
        if isinstance(t, (StructType, EnumType)):
            return self.display_names.get(t.name, t.name)
        if isinstance(t, TupleType):
            inner = ", ".join(self.display(e) for e in t.elems)
            return f"({inner},)" if len(t.elems) == 1 else f"({inner})"
        if isinstance(t, ListType):
            return f"[{self.display(t.elem)}]"
        if isinstance(t, MapType):
            return f"[{self.display(t.key)}: {self.display(t.value)}]"
        if isinstance(t, FuncType):
            ret = self.display(t.ret) if t.ret is not None else "()"
            return "(" + ", ".join(self.display(p) for p in t.params) + ") -> " + ret
        return type_name(t)

    def _type(self, key: tuple, build) -> str:
        """The label of the DIE `key` names; `build()` gives its lines, once."""
        label = self.types.get(key)
        if label is None:
            label = f".Ldty{len(self.types)}"
            self.types[key] = label
            self.pending.append((label, build))
        return label

    def _base(self, t: Type, size: int | None = None) -> str:
        if isinstance(t, IntType):
            # a signed integer is its whole sign-extended slot, so that `set
            # var` writes a canonical value (an unsigned one's upper bytes stay 0)
            enc, width = (_ATE_SIGNED, 8) if t.signed else (_ATE_UNSIGNED, t.width // 8)
        elif isinstance(t, BoolType):
            enc, width = _ATE_BOOLEAN, 1
        elif isinstance(t, CharType):
            enc, width = _ATE_UTF, 4
        else:
            enc, width = _ATE_FLOAT, t.width // 8
        name, width = type_name(t), size or width
        return self._type(("base", name, width), lambda: [
            f"\t.uleb128 {BASE}", _string(name), f"\t.byte {enc}", f"\t.byte {width}"])

    def _byte(self) -> str:
        """A string's byte, shown with its character."""
        return self._type(("byte",), lambda: [
            f"\t.uleb128 {BASE}", _string("uint8"), f"\t.byte {_ATE_UTF}", "\t.byte 1"])

    def _pointer(self, target: str) -> str:
        return self._type(("ptr", target), lambda: [f"\t.uleb128 {PTR}", "\t.byte 8", _ref(target)])

    def _void_pointer(self) -> str:
        return self._type(("voidptr",), lambda: [f"\t.uleb128 {VOIDPTR}", "\t.byte 8"])

    def _struct(self, key: tuple, name: str, size: int, members) -> str:
        """A structure type; `members()` gives (name, type label, offset)."""
        def build() -> list[str]:
            out = [f"\t.uleb128 {STRUCT}", _string(name), f"\t.uleb128 {size}"]
            for mname, mtype, off in members():
                out += [f"\t.uleb128 {MEMBER}", _string(mname), _ref(mtype), f"\t.uleb128 {off}"]
            return out + ["\t.byte 0"]
        return self._type(key, build)

    def _str_slice(self) -> str:
        """A Rust `&str`, which gdb prints as a string literal."""
        i64 = IntType(64, True)
        return self._struct(("slice",), "&str", 16, lambda: [
            ("data_ptr", self._pointer(self._byte()), 0), ("length", self._base(i64), 8)])

    def _dynamic_array(self, elem: str, stride: int, header: int) -> str:
        """An array of `elem`s `stride` bytes apart, as many as the 8 bytes
        `header` bytes before the first say (a cell's length)."""
        count = [_PUSH_OBJECT_ADDRESS, _LIT0 + header, _MINUS, _DEREF]
        return self._type(("array", elem, stride, header), lambda: [
            f"\t.uleb128 {ARRAY}", _ref(elem), f"\t.uleb128 {stride}",
            f"\t.uleb128 {SUBRANGE}", f"\t.uleb128 {len(count)}",
            "\t.byte " + ", ".join(str(b) for b in count), "\t.byte 0"])

    def _items(self, elem: Type) -> str:
        """The elements of a list of `elem`s, at its cell + 16."""
        return self._dynamic_array(self._element(elem), self.cg._stored_size(elem), 16)

    def _cell(self, t: Type) -> str:
        """The heap cell of a `str`, list, builder or map, for a pointer to it."""
        i64 = IntType(64, True)
        if isinstance(t, StrType):
            return self._struct(("cell", "str"), "str", 8, lambda: [
                ("len", self._base(i64), 0), ("bytes", self._dynamic_array(self._byte(), 1, 8), 8)])
        if isinstance(t, StringBuilderType):
            return self._struct(("cell", "sb"), "StringBuilder", 16, lambda: [
                ("len", self._base(i64), 0), ("cap", self._base(i64), 8),
                ("bytes", self._dynamic_array(self._byte(), 1, 16), 16)])
        if isinstance(t, ListType):
            return self._struct(("cell", self.display(t)), self.display(t), 16, lambda: [
                ("len", self._base(i64), 0), ("cap", self._base(i64), 8),
                ("items", self._items(t.elem), 16)])
        return self._struct(("cell", self.display(t)), self.display(t), 16, lambda: [
            ("len", self._base(i64), 0), ("cap", self._base(i64), 8)])

    def _element(self, t: Type) -> str:
        """The type of a value stored inside an aggregate or a list (or a
        scalar variable): types of a fixed size only."""
        if isinstance(t, FloatType) and t.width == 32:
            return self._base(t, 8)              # the double it is kept as
        if isinstance(t, (IntType, BoolType, CharType, FloatType)):
            return self._base(t)
        if isinstance(t, (StrType, StringBuilderType, ListType, MapType)):
            return self._pointer(self._cell(t))
        if self.cg._is_boxed(t):
            return self._pointer(self._aggregate(t))
        return self._aggregate(t)

    def _aggregate(self, t: Type) -> str:
        cg = self.cg
        name, size = self.display(t), cg._size(t)
        if isinstance(t, StructType):
            def fields():
                off, out = 0, []
                for fname, ft in cg.checker.structs[t.name].items():
                    out.append((fname, self._element(ft), off))
                    off += cg._stored_size(ft)
                return out
            return self._struct(("struct", t.name), name, size, fields)
        if isinstance(t, TupleType):
            def elems():
                off, out = 0, []
                for i, et in enumerate(t.elems):
                    out.append((f"__{i}", self._element(et), off))
                    off += cg._stored_size(et)
                return out
            return self._struct(("tuple", name), name, size, elems)
        if isinstance(t, FuncType):
            # `fn…`: a name starting with `(` would make gdb take it for a tuple
            return self._struct(("fn", name), "fn" + name, 16, lambda: [
                ("code_ptr", self._void_pointer(), 0), ("env_ptr", self._void_pointer(), 8)])
        return self._type(("enum", t.name), lambda: self._enum_lines(t, name, size))

    def _enum_lines(self, t: EnumType, name: str, size: int) -> list[str]:
        """An enum as Rust describes one: a variant part whose discriminant is
        the tag, a variant per tag value holding a struct of the payload
        (fields `__0`, `__1`, … at their offsets in the whole value)."""
        variants = list(self.cg.checker.enums[t.name].items())
        tag = self._label("g")
        out = [f"\t.uleb128 {STRUCT}", _string(name), f"\t.uleb128 {size}",
               f"\t.uleb128 {VARIANT_PART}", _ref(tag),
               f"{tag}:", f"\t.uleb128 {TAG}", _string("<tag>"),
               _ref(self._base(IntType(64, False))), "\t.uleb128 0"]
        structs = [self._label("v") for _ in variants]
        for i, (vname, _payload) in enumerate(variants):
            out += [f"\t.uleb128 {VARIANT}", f"\t.uleb128 {i}",
                    f"\t.uleb128 {MEMBER}", _string(vname), _ref(structs[i]), "\t.uleb128 0",
                    "\t.byte 0"]
        out.append("\t.byte 0")                  # end of the variant part
        for label, (vname, payload) in zip(structs, variants):
            out += [f"{label}:", f"\t.uleb128 {STRUCT}", _string(vname), f"\t.uleb128 {size}"]
            off = 8
            for i, ft in enumerate(payload):
                out += [f"\t.uleb128 {MEMBER}", _string(f"__{i}"), _ref(self._element(ft)),
                        f"\t.uleb128 {off}"]
                off += self.cg._stored_size(ft)
            out.append("\t.byte 0")
        return out + ["\t.byte 0"]

    # -- the sections ------------------------------------------------------------

    def sections(self, producer: str, name: str, comp_dir: str) -> list[str]:
        """`.debug_abbrev`, `.debug_info`, and the start of `.debug_line` (the
        assembler appends the line table it builds from `.loc` there)."""
        types: list[str] = []
        while self.pending:
            label, build = self.pending.pop(0)
            types += [f"{label}:"] + build()
        out = abbrev_section()
        out += ['\t.section .debug_info,"",@progbits', ".Ldebug_info0:",
                "\t.long .Ldebug_info_end - .Ldebug_info_start", ".Ldebug_info_start:",
                "\t.value 4", "\t.long .Ldebug_abbrev0", "\t.byte 8",
                f"\t.uleb128 {CU}", _string(producer), f"\t.value {DW_LANG_RUST:#x}",
                _string(name), _string(comp_dir), "\t.quad .Ltext0",
                "\t.quad .Letext0 - .Ltext0", "\t.long .Ldebug_line0"]
        out += self.lines + types + ["\t.byte 0", ".Ldebug_info_end:"]
        out += ['\t.section .debug_line,"",@progbits', ".Ldebug_line0:"]
        return out
