"""The identifier tables (MYLA-84, D72): the self-hosted lexer's copy in
selfhost/unicode.my holds exactly the ranges of src/myla/unicode_ident.py,
and both are what scripts/gen_unicode_tables.py makes from the running
Python's Unicode when that is the version they record."""
import importlib.util
import os
import re
import unicodedata
import unittest

from myla import unicode_ident

_REPO = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)


def _myla_tables() -> dict:
    with open(os.path.join(_REPO, "selfhost", "unicode.my"), encoding="utf-8") as fh:
        text = fh.read()
    out = {"UNICODE_VERSION": re.search(r'UNICODE_VERSION: str = "([^"]+)"', text)[1]}
    for name in ("XID_START", "XID_CONTINUE"):
        decl = re.search(rf"^const {name}: str = (.*)$", text, re.M)[1]
        hexes = "".join(re.findall(r'"([0-9A-F]*)"', decl))
        out[name] = tuple((int(hexes[i:i + 6], 16), int(hexes[i + 6:i + 12], 16)) for i in range(0, len(hexes), 12))
    return out


class TestUnicodeTables(unittest.TestCase):
    def test_both_lexers_have_the_same_ranges(self):
        tables = _myla_tables()
        self.assertEqual(tables["UNICODE_VERSION"], unicode_ident.UNICODE_VERSION)
        self.assertEqual(tables["XID_START"], unicode_ident.XID_START)
        self.assertEqual(tables["XID_CONTINUE"], unicode_ident.XID_CONTINUE)
        self.assertGreater(len(unicode_ident.XID_START), 600)

    @unittest.skipUnless(unicodedata.unidata_version == unicode_ident.UNICODE_VERSION,
                         "the tables come from another Unicode version than this Python's")
    def test_the_tables_are_current(self):
        spec = importlib.util.spec_from_file_location(
            "gen_unicode_tables", os.path.join(_REPO, "scripts", "gen_unicode_tables.py"))
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        self.assertEqual(tuple(gen.ranges(gen.xid_start)), unicode_ident.XID_START)
        self.assertEqual(tuple(gen.ranges(gen.xid_continue)), unicode_ident.XID_CONTINUE)

    def test_ascii_and_beyond(self):
        start, cont = unicode_ident.is_ident_start, unicode_ident.is_ident_continue
        self.assertEqual([start(c) for c in "a_Z9·℘ö€"], [True, True, True, False, False, True, True, False])
        self.assertEqual([cont(c) for c in "a_Z9·́ö€"], [True, True, True, True, True, True, True, False])


if __name__ == "__main__":
    unittest.main()
