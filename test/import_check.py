import sys, pathlib
root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
print("ROOT =", root)
print("onuslibs exists?", (root/"onuslibs").exists())
print("__init__ exists?", (root/"onuslibs/__init__.py").exists())
print("db exists?", (root/"onuslibs/db").exists())
print("db __init__ exists?", (root/"onuslibs/db/__init__.py").exists())

import onuslibs, onuslibs.db
print("onuslibs file:", onuslibs.__file__)
print("OK: import onuslibs.db")
