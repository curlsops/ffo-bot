from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

_PATCH_MARKER = 'elif machine() in ("x86_64", "amd64"):'
_NEEDLE = "    elif \"x86\" in machine():\n        file_ext = '-x86.so'"
_INSERT = (
    '    elif machine() in ("x86_64", "amd64"):\n'
    "        file_ext = '-amd64.so'\n"
    '    elif "x86" in machine():\n'
    "        file_ext = '-x86.so'"
)


def patch_tls_client_cffi(cffi_path: Path) -> bool:
    if not cffi_path.is_file():
        return False
    text = cffi_path.read_text()
    if _PATCH_MARKER in text:
        return False
    if _NEEDLE not in text:
        return False
    cffi_path.write_text(text.replace(_NEEDLE, _INSERT, 1))
    return True


def linux_musl() -> bool:
    return sys.platform.startswith("linux") and os.path.isfile("/lib/ld-musl-x86_64.so.1")


def spotapi_native_supported() -> bool:
    return not linux_musl()


def _tls_client_cffi_path(cffi_mod: object) -> Path | None:
    if not isinstance(cffi_mod, types.ModuleType):
        return None
    cffi_file = getattr(cffi_mod, "__file__", None)
    if isinstance(cffi_file, str) and cffi_file:
        return Path(cffi_file)
    try:
        spec = importlib.util.find_spec("tls_client.cffi")
    except (ImportError, ModuleNotFoundError, ValueError):
        return None
    if spec is None:
        return None
    origin = getattr(spec, "origin", None)
    if not isinstance(origin, str) or not origin or origin == "namespace":
        return None
    return Path(origin)


def ensure_tls_client_alpine_patch() -> bool:
    if not linux_musl():
        return False
    try:
        import tls_client.cffi as cffi_mod
    except ImportError:
        return False
    cffi_path = _tls_client_cffi_path(cffi_mod)
    if cffi_path is None:
        return False
    return patch_tls_client_cffi(cffi_path)
