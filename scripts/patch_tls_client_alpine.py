#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
from pathlib import Path

_PATCH_MARKER = 'elif machine() in ("x86_64", "amd64"):'
_NEEDLE = "    elif \"x86\" in machine():\n        file_ext = '-x86.so'"
_INSERT = (
    '    elif machine() in ("x86_64", "amd64"):\n'
    "        file_ext = '-amd64.so'\n"
    '    elif "x86" in machine():\n'
    "        file_ext = '-x86.so'"
)


def patch_file(cffi: Path) -> int:
    if not cffi.is_file():
        print(f"skip: {cffi} not found", file=sys.stderr)
        return 0
    text = cffi.read_text()
    if _PATCH_MARKER in text:
        print("already patched")
        return 0
    if _NEEDLE not in text:
        print(f"skip: unexpected tls_client cffi layout in {cffi}", file=sys.stderr)
        return 1
    cffi.write_text(text.replace(_NEEDLE, _INSERT, 1))
    print(f"patched {cffi}")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <site-packages>", file=sys.stderr)
        return 2
    if not os.path.isfile("/lib/ld-musl-x86_64.so.1"):
        print("skip: not musl")
        return 0
    return patch_file(Path(sys.argv[1]) / "tls_client" / "cffi.py")


if __name__ == "__main__":
    raise SystemExit(main())
