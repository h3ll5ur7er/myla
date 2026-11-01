import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_SRC = os.path.join(_REPO, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

if os.environ.get("MYLA_NO_PYTHON_TOOLCHAIN") == "1":
    # prove a run doesn't touch the retired Python toolchain (MYLA-219): any
    # import of `myla` fails
    import importlib.abc

    class _NoPythonToolchain(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name == "myla" or name.startswith("myla."):
                raise ImportError(f"the Python toolchain is retired (MYLA-219): import {name}")
            return None

    sys.meta_path.insert(0, _NoPythonToolchain())
