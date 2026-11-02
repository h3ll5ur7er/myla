"""Build the recorded answers' aliases for rewritten programs (MYLA-240).

    MYLA_GOLDEN_TRACE=trace.jsonl python3 -m unittest discover -s tests/burn -t .
    python3 -m tests.burn.golden_aliases trace.jsonl

The trace holds every question the burn suite asked the recordings, with
the texts of the programs it named, taken before the programs were rewritten
by `scripts/to_methods.py` (MYLA-221). For each question the recordings
answer whose texts the rewrite changes, the key of the same question about
the rewritten texts leads to the original's answer, with the lines that
changed (`tests/burn/data/golden/aliases/<oracle>.json.gz`; `_golden.py`
moves the answer's positions). The original's key is checked against the
recording: a trace that doesn't reproduce its keys builds nothing.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sys

from tests.burn import _golden

sys.path.insert(0, os.path.join(_golden._REPO, "scripts"))
import to_methods  # noqa: E402

# Oracles whose answers are the program's own structure (tokens, syntax
# trees): a rewritten program has another, so their gates ask about recorded
# copies of the files they read (`tests/burn/data/recorded_corpus/`) instead.
STRUCTURAL = {"selfhost_lexer.tokens", "selfhost_lexer.tokens_strict", "selfhost_parser.ast"}

_CALL = re.compile(r"(?<![.\w])(" + "|".join(sorted(to_methods.BUILTINS)) + r")\s*\(")


def _myla(text: str) -> bool:
    return bool(_CALL.search(text)) and ("\n" in text or text.endswith(")"))


def _describe(arg, rewrite: bool, changed: list):
    """`_golden._describe` of a traced argument (a file is {"path", "text"}),
    its texts rewritten when `rewrite`; each changed text is added to
    `changed` as (label, old, new)."""
    if isinstance(arg, dict) and set(arg) == {"path", "text"}:
        text = arg["text"]
        path = arg["path"]
        if rewrite and path.endswith(".my") and _myla(text):
            new, where = to_methods.rewrite_mapped(text)
            if new != text:
                changed.append((os.path.basename(path), text, new, where))
                text = new
        data = text.encode("utf-8", "surrogateescape")
        for r in {_golden._REPO, os.path.realpath(_golden._REPO)}:
            data = data.replace(r.encode(), _golden.RECORDED_REPO.encode())
        digest = hashlib.sha256(data).hexdigest()
        if path.startswith(_golden._REPO + os.sep) and "/build/" not in path:
            where = os.path.relpath(path, _golden._REPO)
        else:
            where = os.path.basename(path)
        return {"file": where, "sha256": digest}
    if isinstance(arg, str):
        if rewrite and _myla(arg):
            new, where = to_methods.rewrite_mapped(arg)
            if new != arg:
                changed.append(("", arg, new, where))
                arg = new
        for r in {_golden._REPO, os.path.realpath(_golden._REPO)}:
            arg = arg.replace(r, _golden.RECORDED_REPO)
        return arg
    if isinstance(arg, list):
        return [_describe(a, rewrite, changed) for a in arg]
    if isinstance(arg, dict):
        return {k: _describe(v, rewrite, changed) for k, v in sorted(arg.items())}
    return arg


def _key(args, kwargs, rewrite: bool, changed: list) -> str:
    key_obj = [_describe(args, rewrite, changed), _describe(kwargs, rewrite, changed)]
    return hashlib.sha256(json.dumps(key_obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build(trace_path: str) -> dict[str, dict]:
    aliases: dict[str, dict] = {}
    seen = set()
    mismatched = 0
    with open(trace_path, encoding="utf-8", errors="surrogateescape") as fh:
        records = [json.loads(line) for line in fh]
    for rec in records:
        if not rec["known"] or rec["oracle"] in STRUCTURAL or (rec["oracle"], rec["key"]) in seen:
            continue
        seen.add((rec["oracle"], rec["key"]))
        if _key(rec["args"], rec["kwargs"], False, []) != rec["key"]:
            mismatched += 1
            continue
        changed: list = []
        new_key = _key(rec["args"], rec["kwargs"], True, changed)
        if new_key == rec["key"]:
            continue
        lines = []
        for label, old, new, where in changed:
            olds, news = old.split("\n"), new.split("\n")
            if len(olds) != len(news):
                raise SystemExit(f"the rewrite moved lines of {label or 'a program'}")
            at = 0
            for n, (a, b) in enumerate(zip(olds, news), 1):
                if a != b:
                    # each old column's place on the new line (its end too)
                    cols = []
                    for c in range(len(a) + 1):
                        j = where[at + c]
                        cols.append(j - (new.rfind("\n", 0, j) + 1) + 1)
                    lines.append([label, n, a, b, cols])
                at += len(a) + 1
        aliases.setdefault(rec["oracle"], {})[new_key] = {"to": rec["key"], "lines": lines}
    if mismatched:
        print(f"{mismatched} traced questions didn't reproduce their keys (left out)")
    return aliases


def main() -> int:
    aliases = build(sys.argv[1])
    os.makedirs(_golden._ALIAS_DIR, exist_ok=True)
    for oracle, table in sorted(aliases.items()):
        path = os.path.join(_golden._ALIAS_DIR, f"{oracle}.json.gz")
        with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            gz.write(json.dumps(table, indent=0, sort_keys=True, ensure_ascii=False).encode())
        print(f"{oracle:40} {len(table)} aliases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
