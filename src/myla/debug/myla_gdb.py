# gdb pretty-printers for Myla programs built with `myla build -g` (MYLA-66, D82).
#
# The DWARF of a -g build describes a heap value inside a struct, tuple, enum,
# list or map (a str, list, builder or map, a boxed enum) as a pointer to its
# cell, and a float32 kept as a double as an 8-byte float named float32: gdb
# can't give fields and elements types whose size depends on their value.
# These printers show them as Myla values instead:
#
#   Bag {items: [4, 5], label: "two", ratio: 0.100000001, tags: {"k": 4}}
#
# Both compilers embed this file in the binary's .debug_gdb_scripts section,
# so gdb runs it when it loads the program, if `auto-load safe-path` allows
# the program's path (`gdb -iex 'add-auto-load-safe-path .' ./prog`, or that
# line in ~/.config/gdb/gdbinit). Or load it by hand: `source <this file>`.
# `print/r x` shows a value without them, `disable pretty-printer global myla`
# turns them off.
#
# Keep this file ASCII: the compilers copy it byte for byte into the assembly.

import struct

import gdb
import gdb.printing


def _address(val):
    """The address a pointer holds, or of a value in memory."""
    if val.type.strip_typedefs().code == gdb.TYPE_CODE_PTR:
        return int(val)
    return int(val.address)


def _read_u64(address):
    return int.from_bytes(bytes(gdb.selected_inferior().read_memory(address, 8)), "little")


def _cell_kind(t):
    """What a cell type describes: 'str', 'sb', 'list' or 'map' (None for
    other types). Cells are the structs the compilers name `str`,
    `StringBuilder`, `[T]` and `[K: V]`, with these fields."""
    if t.code != gdb.TYPE_CODE_STRUCT:
        return None
    name = t.name or ""
    if name != "str" and name != "StringBuilder" and not name.startswith("["):
        return None
    fields = tuple(f.name for f in t.fields())
    if name == "str" and fields == ("len", "bytes"):
        return "str"
    if name == "StringBuilder" and fields == ("len", "cap", "bytes"):
        return "sb"
    if fields == ("len", "cap", "items"):
        return "list"
    if fields == ("len", "cap", "slots"):
        return "map"
    return None


class StringPrinter:
    """A str or StringBuilder cell (or a pointer to one): the text."""

    def __init__(self, val, cell_type, data):
        self.address = _address(val)
        self.byte = cell_type.fields()[-1].type.target()
        self.data = data

    def to_string(self):
        try:
            length = _read_u64(self.address)
        except gdb.MemoryError:
            return "<unreadable cell 0x%x>" % self.address
        start = gdb.Value(self.address + self.data).cast(self.byte.pointer())
        return start.lazy_string(encoding="utf-8", length=length)

    def display_hint(self):
        return "string"


class ListPrinter:
    """A list cell (or a pointer to one): its elements, `[4, 5]`."""

    def __init__(self, cell):
        self.cell = cell

    def to_string(self):
        return self.cell["items"]


def _limit():
    n = gdb.parameter("print elements")
    return None if n is None or n == 0 else n


class MapPrinter:
    """A map cell (or a pointer to one): its occupied slots, `{"k": 4}`, in
    the order `for k in m` visits them."""

    def __init__(self, cell):
        self.cell = cell

    def to_string(self):
        slots = self.cell["slots"]
        cap = int(self.cell["cap"])
        limit = _limit()
        parts = []
        for i in range(cap):
            slot = slots[i]
            if int(slot["state"]) != 1:
                continue
            if limit is not None and len(parts) == limit:
                parts.append("...")
                break
            parts.append("%s: %s" % (slot["key"].format_string(), slot["value"].format_string()))
        return "{" + ", ".join(parts) + "}"


class Float32Printer:
    """A float32 kept as a double (a field or element): as gdb prints a float."""

    def __init__(self, val):
        self.val = val

    def to_string(self):
        single = struct.unpack("<f", struct.pack("<f", float(self.val)))[0]
        return "%.9g" % single


class DerefPrinter:
    """A pointer to a struct or enum (a boxed enum inside an aggregate, a
    function's aggregate result): the value it points at."""

    def __init__(self, val):
        self.val = val

    def to_string(self):
        if int(self.val) == 0:
            return "0x0"
        return self.val.dereference()


def _printer(val):
    t = val.type.strip_typedefs()
    if t.code == gdb.TYPE_CODE_FLT:
        if t.name == "float32" and t.sizeof == 8:
            return Float32Printer(val)
        return None
    pointer = t.code == gdb.TYPE_CODE_PTR
    if pointer:
        t = t.target().strip_typedefs()
    kind = _cell_kind(t)
    if kind is None:
        if pointer and t.code == gdb.TYPE_CODE_STRUCT and t.name and not t.name.startswith("&"):
            return DerefPrinter(val)
        return None
    if kind == "str":
        return StringPrinter(val, t, 8)
    if kind == "sb":
        return StringPrinter(val, t, 16)
    if pointer:
        if int(val) == 0:
            return None
        val = val.dereference()
    return ListPrinter(val) if kind == "list" else MapPrinter(val)


class MylaPrinters(gdb.printing.PrettyPrinter):
    def __init__(self):
        super().__init__("myla")

    def __call__(self, val):
        return _printer(val) if self.enabled else None


# Globally, not for the objfile being loaded: gdb runs an embedded script of a
# given name once per program space, so the printers must outlive the first
# Myla binary loaded. They only match the compilers' cell and float32 types.
gdb.printing.register_pretty_printer(None, MylaPrinters(), replace=True)
