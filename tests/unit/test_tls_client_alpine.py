import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from bot.services import tls_client_alpine

_UNPATCHED = """\
else:
    if machine() == "aarch64":
        file_ext = '-arm64.so'
    elif "x86" in machine():
        file_ext = '-x86.so'
    else:
        file_ext = '-amd64.so'
"""

_PATCHED = """\
else:
    if machine() == "aarch64":
        file_ext = '-arm64.so'
    elif machine() in ("x86_64", "amd64"):
        file_ext = '-amd64.so'
    elif "x86" in machine():
        file_ext = '-x86.so'
    else:
        file_ext = '-amd64.so'
"""


class TestPatchTlsClientCffi:
    def test_patches_unpatched_layout(self, tmp_path: Path):
        cffi = tmp_path / "cffi.py"
        cffi.write_text(_UNPATCHED)
        assert tls_client_alpine.patch_tls_client_cffi(cffi) is True
        assert _PATCHED in cffi.read_text()

    def test_idempotent_when_already_patched(self, tmp_path: Path):
        cffi = tmp_path / "cffi.py"
        cffi.write_text(_PATCHED)
        assert tls_client_alpine.patch_tls_client_cffi(cffi) is False

    def test_missing_file_returns_false(self, tmp_path: Path):
        assert tls_client_alpine.patch_tls_client_cffi(tmp_path / "missing.py") is False

    def test_unexpected_layout_returns_false(self, tmp_path: Path):
        cffi = tmp_path / "cffi.py"
        cffi.write_text("# no needle\n")
        assert tls_client_alpine.patch_tls_client_cffi(cffi) is False

    def test_ensure_skips_on_glibc(self, monkeypatch):
        monkeypatch.setattr(tls_client_alpine, "linux_musl", lambda: False)
        assert tls_client_alpine.ensure_tls_client_alpine_patch() is False

    def test_ensure_patch_import_error(self, monkeypatch):
        import builtins

        monkeypatch.setattr(tls_client_alpine, "linux_musl", lambda: True)
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "tls_client.cffi":
                raise ImportError("no tls_client")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert tls_client_alpine.ensure_tls_client_alpine_patch() is False

    def test_ensure_noop_when_cffi_has_no_file(self, monkeypatch):
        import sys
        import types

        monkeypatch.setattr(tls_client_alpine, "linux_musl", lambda: True)
        cffi_mod = types.ModuleType("tls_client.cffi")
        pkg = types.ModuleType("tls_client")
        monkeypatch.setitem(sys.modules, "tls_client", pkg)
        monkeypatch.setitem(sys.modules, "tls_client.cffi", cffi_mod)
        assert tls_client_alpine.ensure_tls_client_alpine_patch() is False

    def test_tls_client_cffi_path_from_file(self, tmp_path: Path):
        import types

        cffi = tmp_path / "cffi.py"
        cffi.write_text("# stub")
        mod = types.ModuleType("tls_client.cffi")
        mod.__file__ = str(cffi)
        assert tls_client_alpine._tls_client_cffi_path(mod) == cffi

    def test_tls_client_cffi_path_rejects_non_module(self):
        assert tls_client_alpine._tls_client_cffi_path(MagicMock()) is None

    def test_tls_client_cffi_path_from_find_spec(self, tmp_path: Path, monkeypatch):
        cffi = tmp_path / "cffi.py"
        cffi.write_text("# stub")
        mod = ModuleType("tls_client.cffi")
        spec = importlib.util.spec_from_file_location("tls_client.cffi", cffi)
        monkeypatch.setattr(importlib.util, "find_spec", lambda _name: spec)
        assert tls_client_alpine._tls_client_cffi_path(mod) == cffi

    @pytest.mark.parametrize(
        ("spec", "find_spec_side_effect"),
        [
            (None, None),
            (MagicMock(origin="namespace"), None),
            (MagicMock(origin=""), None),
            (None, ValueError("bad")),
        ],
    )
    def test_tls_client_cffi_path_find_spec_miss(self, spec, find_spec_side_effect, monkeypatch):
        mod = ModuleType("tls_client.cffi")

        def _find_spec(_name: str):
            if find_spec_side_effect is not None:
                raise find_spec_side_effect
            return spec

        monkeypatch.setattr(importlib.util, "find_spec", _find_spec)
        assert tls_client_alpine._tls_client_cffi_path(mod) is None

    def test_ensure_patch_applies_when_needed(self, monkeypatch, tmp_path: Path):
        import sys
        import types

        monkeypatch.setattr(tls_client_alpine, "linux_musl", lambda: True)
        cffi = tmp_path / "cffi.py"
        cffi.write_text(_UNPATCHED)
        cffi_mod = types.ModuleType("tls_client.cffi")
        cffi_mod.__file__ = str(cffi)
        pkg = types.ModuleType("tls_client")
        monkeypatch.setitem(sys.modules, "tls_client", pkg)
        monkeypatch.setitem(sys.modules, "tls_client.cffi", cffi_mod)
        assert tls_client_alpine.ensure_tls_client_alpine_patch() is True


class TestLinuxMusl:
    def test_linux_musl_when_loader_present(self, monkeypatch):
        import os
        import sys

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(
            os.path,
            "isfile",
            lambda path: path == "/lib/ld-musl-x86_64.so.1",
        )
        assert tls_client_alpine.linux_musl() is True


class TestSpotapiNativeSupported:
    def test_supported_on_glibc(self, monkeypatch):
        monkeypatch.setattr(tls_client_alpine, "linux_musl", lambda: False)
        assert tls_client_alpine.spotapi_native_supported() is True

    def test_unsupported_on_musl(self, monkeypatch):
        monkeypatch.setattr(tls_client_alpine, "linux_musl", lambda: True)
        assert tls_client_alpine.spotapi_native_supported() is False
