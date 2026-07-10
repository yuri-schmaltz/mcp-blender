"""Tests for the two upstream bugs that surfaced during the e2e
harness bring-up.

1. ``scene.objects.active`` was removed in Blender 3.5+; the codebase
   used it directly in ``addon/handlers/scene_tools.py::get_scene_info``.
   The fix introduces ``_active_object_name(scene)`` that prefers the
   modern ``view_layer.objects.active`` and falls back gracefully.

2. ``BlenderMCPPreferences.bl_idname = __package__`` resolved to an
   empty string (or the wrong name) when the addon was loaded as a
   top-level module. The new resolver walks ``__package__``,
   ``blender_manifest.toml``'s ``id`` field, and finally the directory
   name of ``__init__.py`` before giving up.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Bug 1: scene.objects.active
# ---------------------------------------------------------------------------

class _FakeViewLayerObjects:
    def __init__(self, name: str | None):
        self._active = types.SimpleNamespace(name=name) if name else None

    @property
    def active(self):
        return self._active


def _load_scene_tools_helper():
    """Load ``addon/handlers/scene_tools.py`` and return ``(_active_object_name, fake_bpy)``.

    The module uses relative imports (``from ..core.router``), so we
    fake the package layout and load the file as a submodule of an
    inline ``addon`` package. That sets ``__package__`` correctly and
    lets the relative imports resolve.
    """
    fake_addon = types.ModuleType("addon")
    fake_addon.__path__ = []  # marks as package
    fake_core = types.ModuleType("addon.core")
    fake_core.__path__ = []
    fake_router = types.ModuleType("addon.core.router")

    def _noop_decorator(*_a, **_kw):
        return lambda fn: fn

    fake_router.mcp_command = _noop_decorator
    fake_bpy = types.ModuleType("bpy")
    fake_bpy.types = types.SimpleNamespace()
    fake_bpy.context = types.SimpleNamespace(
        view_layer=types.SimpleNamespace(objects=_FakeViewLayerObjects(None))
    )
    fake_bpy.data = types.SimpleNamespace()
    fake_mathutils = types.ModuleType("mathutils")
    fake_mathutils.Vector = lambda *a, **kw: None
    fake_mathutils.Matrix = lambda *a, **kw: None

    sys.modules["bpy"] = fake_bpy
    sys.modules["mathutils"] = fake_mathutils
    sys.modules["addon"] = fake_addon
    sys.modules["addon.core"] = fake_core
    sys.modules["addon.core.router"] = fake_router

    repo = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "addon.handlers._scene_tools_under_test",
        str(repo / "addon" / "handlers" / "scene_tools.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["addon.handlers"] = types.ModuleType("addon.handlers")
    sys.modules["addon.handlers"].__path__ = [str(repo / "addon" / "handlers")]
    sys.modules["addon.handlers._scene_tools_under_test"] = module
    spec.loader.exec_module(module)
    return module._active_object_name, fake_bpy


def test_active_object_name_modern_api():
    active_name, fake_bpy = _load_scene_tools_helper()
    fake_bpy.context.view_layer.objects = _FakeViewLayerObjects("Cube")
    scene = MagicMock()

    class _Boom:
        @property
        def active(self):  # pragma: no cover - defensive
            raise AssertionError("legacy scene.objects.active must not be read")

    scene.objects = _Boom()
    assert active_name(scene) == "Cube"


def test_active_object_name_no_active():
    active_name, fake_bpy = _load_scene_tools_helper()
    fake_bpy.context.view_layer.objects = _FakeViewLayerObjects(None)
    scene = MagicMock()
    scene.objects = types.SimpleNamespace(active=None)
    assert active_name(scene) is None


def test_active_object_name_legacy_fallback():
    """If ``view_layer.objects.active`` raises, fall back to the legacy
    attribute on ``scene.objects`` (Blender <= 3.4)."""

    class _BrokenViewLayer:
        @property
        def objects(self):
            raise AttributeError("view_layer is not available")

    active_name, fake_bpy = _load_scene_tools_helper()
    fake_bpy.context.view_layer = _BrokenViewLayer()
    scene = MagicMock()
    legacy_obj = types.SimpleNamespace(name="LegacyCube")
    scene.objects = types.SimpleNamespace(active=legacy_obj)
    assert active_name(scene) == "LegacyCube"


# ---------------------------------------------------------------------------
# Bug 2: bl_idname resolution
# ---------------------------------------------------------------------------

_RESOLVER_SOURCE = """from pathlib import Path
import tomllib

def _resolve_addon_id():
    pkg = __package__
    if pkg:
        return pkg
    manifest = Path(__file__).resolve().parent / 'blender_manifest.toml'
    if manifest.is_file():
        try:
            with manifest.open('rb') as fh:
                data = tomllib.load(fh)
            mid = data.get('id')
            if isinstance(mid, str) and mid:
                return mid
        except Exception:
            pass
    return Path(__file__).resolve().parent.name or 'blender_mcp'
"""


def _make_fake_addon(
    tmp_path: Path, *, dir_name: str, manifest_id: str | None, package: str = ""
):
    """Create a fake addon directory tree and load it as a top-level module.

    Returns the loaded module whose ``_resolve_addon_id`` function we
    can call. ``__package__`` is forced to ``package`` (empty by default)
    so the fallback branches are exercised.
    """
    fake_root = tmp_path / dir_name
    fake_root.mkdir()
    (fake_root / "__init__.py").write_text(
        _RESOLVER_SOURCE, encoding="utf-8"
    )
    if manifest_id is not None:
        (fake_root / "blender_manifest.toml").write_text(
            f'id = "{manifest_id}"\nversion = "0.0.0"\n', encoding="utf-8"
        )

    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module(dir_name)
        # Force the ``__package__`` we want. By default it is the
        # module's own name (PEP 366 says top-level module's __package__
        # is "" but Python's importlib sets it to the module name when
        # it's imported as a package). The bug surfaces when __package__
        # is empty OR when it points to something that does not match
        # the addon's registered id.
        mod.__package__ = package
        return mod
    finally:
        sys.path.pop(0)
        sys.modules.pop(dir_name, None)


def test_resolve_addon_id_falls_back_to_manifest(tmp_path):
    mod = _make_fake_addon(
        tmp_path, dir_name="mcp_blender_legacy", manifest_id="mcp_blender", package=""
    )
    assert mod._resolve_addon_id() == "mcp_blender"


def test_resolve_addon_id_falls_back_to_directory_name(tmp_path):
    mod = _make_fake_addon(
        tmp_path, dir_name="blender_mcp_local", manifest_id=None, package=""
    )
    assert mod._resolve_addon_id() == "blender_mcp_local"


def test_resolve_addon_id_prefers_package(tmp_path):
    mod = _make_fake_addon(
        tmp_path,
        dir_name="mcp_blender_legacy",
        manifest_id="mcp_blender",
        package="real_extension_id",
    )
    # Even if a manifest is present, a real package name wins.
    assert mod._resolve_addon_id() == "real_extension_id"


def test_resolve_addon_id_real_init_py():
    """Smoke test: the real ``__init__.py`` in this checkout resolves
    to a non-empty id, regardless of which branch fires."""
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        mod = importlib.import_module("__init__")
    finally:
        sys.path.pop(0)
    try:
        rid = mod._resolve_addon_id()
    except Exception as exc:  # pragma: no cover - surface clearly
        pytest.fail(f"_resolve_addon_id raised: {exc}")
    assert isinstance(rid, str) and rid, f"expected non-empty str, got {rid!r}"
