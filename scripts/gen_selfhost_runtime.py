#!/usr/bin/env python3
"""Generate the runtime helpers the self-hosted compiler shares verbatim with
the Python backend (MYLA-29): the SSE2 float runtime and `__char_to_str`.

The number-to-text routine must print exactly what the interpreter prints, so
the self-hosted code generator emits the same instructions and the same
power-of-ten tables as `src/myla/compiler/codegen_x86.py`. This script renders
the Python backend's `_emit_float_runtime`, `_float_rodata` and
`_emit_char_runtime` and writes them as Myla into the marked region of
`selfhost/codegen.my`. Run it after changing those; a unit test
(`tests/unit/test_compiler.py`) checks that the two stay identical.

    python3 scripts/gen_selfhost_runtime.py
"""
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, os.path.join(REPO, "src"))

from myla.compiler.codegen_x86 import CodeGen  # noqa: E402

BEGIN = "    // -- BEGIN generated runtime"
END = "    // -- END generated runtime"


def _myla_str(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped.replace("\t", "\\t").replace("\n", "\\n") + '"'


def _chunks(name: str, doc: list[str], lines: list[str], size: int = 40) -> list[str]:
    """A method returning `lines` as a few string chunks: string data costs no
    code, unlike one emit call or list element per line."""
    out = [f"    // {d}" for d in doc]
    out += [f"    fun {name}(self) -> [str] {{", "        return ["]
    for k in range(0, len(lines), size):
        out.append("            " + _myla_str("\n".join(lines[k:k + size])) + ",")
    out += ["        ]", "    }", ""]
    return out


def render() -> str:
    cg = CodeGen.__new__(CodeGen)
    cg.text = []
    cg._emit_float_runtime()
    float_runtime = cg.text
    rodata = "\n".join(cg._float_rodata()).split("\n")
    cg.text = []
    cg._emit_char_runtime()
    lines = [
        BEGIN + " (scripts/gen_selfhost_runtime.py renders the Python backend's",
        "    // _emit_float_runtime, _float_rodata and _emit_char_runtime; don't",
        "    // edit by hand)",
        "",
    ]
    lines += _chunks("float_runtime_text", [
        "__fmod, __float_to_str and their helpers: emitted once, after the",
        "functions, when the program uses floats.",
    ], float_runtime)
    lines += _chunks("float_rodata_text", [
        "The float runtime's read-only data: 10^k as double-double (high and",
        "low parts, k = -323 … 308) and the constants and strings it uses.",
    ], rodata)
    lines += _chunks("char_to_str_text", [
        "__char_to_str: rdi = Unicode scalar -> rax = its UTF-8 text as a str.",
    ], cg.text)
    lines.append(END)
    return "\n".join(lines)


def main() -> None:
    path = os.path.join(REPO, "selfhost", "codegen.my")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    begin = src.index(BEGIN)
    end = src.index(END) + len(END)
    new = src[:begin] + render() + src[end:]     # render before truncating the file
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    print(f"wrote the shared runtime into {os.path.relpath(path, REPO)}")


if __name__ == "__main__":
    main()
