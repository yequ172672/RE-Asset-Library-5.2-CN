"""Focused pure-Python checks for the RE Engine Extension Browser adapter.

The tree/index tests intentionally do not require Blender or game files.  The
resolver test uses an already-extracted temporary mesh and verifies the seam
returned to the preview/import operators without invoking a PAK extractor.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


SOURCE_ROOT = Path(__file__).resolve().parents[1]
ASSET_MODULE_ROOT = SOURCE_ROOT / "modules" / "asset"
TEST_PACKAGE = "re_asset_library_test"


def load_asset_module(name: str):
    full_name = f"{TEST_PACKAGE}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = ASSET_MODULE_ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(
        full_name,
        path,
        submodule_search_locations=[str(ASSET_MODULE_ROOT)] if name == "__init__" else None,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


def load_resources():
    package = type(sys)(TEST_PACKAGE)
    package.__path__ = [str(ASSET_MODULE_ROOT)]
    package.__package__ = TEST_PACKAGE
    sys.modules.setdefault(TEST_PACKAGE, package)
    load_asset_module("catalog_paths")
    return load_asset_module("browser_resources")


def load_native():
    load_resources()
    if "bpy" not in sys.modules:
        bpy_module = type(sys)("bpy")
        bpy_props = type(sys)("bpy.props")
        bpy_types = type(sys)("bpy.types")
        bpy_props.StringProperty = lambda **_kwargs: ""
        bpy_types.Operator = type("Operator", (), {})
        bpy_types.Panel = type("Panel", (), {})
        bpy_module.props = bpy_props
        bpy_module.types = bpy_types
        sys.modules["bpy"] = bpy_module
        sys.modules["bpy.props"] = bpy_props
        sys.modules["bpy.types"] = bpy_types
    return load_asset_module("native_browser")


class ReEngineBrowserTests(unittest.TestCase):
    def setUp(self):
        self.resources = load_resources()
        self.temp_dir = tempfile.TemporaryDirectory(prefix="reengine-browser-")
        self.root = Path(self.temp_dir.name)
        self.game_dir = self.root / "OWOTS"
        self.game_dir.mkdir()
        (self.game_dir / "GameInfo_OWOTS.json").write_text(
            json.dumps(
                {
                    "GameName": "OWOTS",
                    "GameInfoVersion": 1,
                    "fileVersionDict": {"MESH_VERSION": "260209350", "CHAIN2_VERSION": "17"},
                }
            ),
            encoding="utf-8",
        )
        (self.game_dir / "REAssetCatalog_OWOTS.tsv").write_text(
            "File Path\tDisplay Name\tCategory (Forward Slash Separated)\tTags (Comma Separated)\tPlatform Extension\tLanguage Extension\n"
            "art/model/ch0/body.mesh\tBody Display\tlegacy category\tmain\t\t\n"
            "art/model/ch0/body.chain2\tBody Chain\tlegacy category\t\tSTM\ten\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_tree_uses_resource_directories_and_stable_ids(self):
        root = self.resources.build_tree(str(self.root), "/Assets")
        self.assertEqual(root["protocol_version"], 1)
        self.assertEqual([item["name"] for item in root["children"]], ["OWOTS"])

        body_dir = self.resources.build_tree(str(self.root), "/Assets/OWOTS/art/model/ch0")
        self.assertEqual(len(body_dir["children"]), 2)
        mesh = next(item for item in body_dir["children"] if item["type"] == "MESH")
        chain = next(item for item in body_dir["children"] if item["type"] == "CHAIN2")
        self.assertEqual(mesh["path"], "/Assets/OWOTS/art/model/ch0/body.mesh")
        self.assertEqual(mesh["name"], "Body Display")
        self.assertTrue(mesh["has_preview"])
        self.assertTrue(mesh["can_import"])
        self.assertFalse(chain["has_preview"])
        self.assertFalse(chain["can_import"])
        self.assertEqual(
            mesh["asset_id"],
            self.resources.asset_id_for("OWOTS", "art/model/ch0/body.mesh"),
        )
        self.assertEqual(
            chain["asset_id"],
            self.resources.asset_id_for("OWOTS", "art/model/ch0/body.chain2", "STM", "en"),
        )

    def test_resolve_asset_returns_absolute_import_contract(self):
        asset_id = self.resources.asset_id_for("OWOTS", "art/model/ch0/body.mesh")
        chunk_root = self.root / "extract" / "natives" / "STM"
        mesh = chunk_root / "art/model/ch0/body.mesh.260209350"
        mesh.parent.mkdir(parents=True)
        mesh.write_bytes(b"mesh")

        # The existing Blender-specific chunk-path resolver is intentionally
        # replaced here; this test exercises the pure contract with an
        # already-extracted file and does not fake a PAK extraction success.
        original = self.resources._chunk_paths
        self.resources._chunk_paths = lambda _game: [str(chunk_root)]
        try:
            resource = self.resources.resolve_asset(
                asset_id,
                asset_library_root_path=str(self.root),
                force_extract=False,
            )
        finally:
            self.resources._chunk_paths = original

        self.assertEqual(resource["asset_id"], asset_id)
        self.assertEqual(resource["game_name"], "OWOTS")
        self.assertEqual(Path(resource["mesh_path"]), mesh.resolve())
        self.assertEqual(resource["chunk_paths"], [str(chunk_root.resolve())])
        self.assertEqual(resource["metadata"]["asset_type"], "MESH")

    def test_invalid_tree_paths_do_not_escape_virtual_root(self):
        response = self.resources.build_tree(str(self.root), "/Assets/../outside")
        self.assertEqual(response["path"], "/Assets")

    def test_import_seam_passes_resolved_mesh_path_and_asset_metadata(self):
        native = load_native()
        record = self.resources.find_asset(
            str(self.root), self.resources.asset_id_for("OWOTS", "art/model/ch0/body.mesh")
        )
        proxy = self.resources._AssetProxy(record)
        calls = []

        def importer(asset, path, preferences):
            calls.append((asset, path, preferences))
            return True

        mesh_path = str((self.root / "body.mesh.260209350").resolve())
        preferences = SimpleNamespace(showMeshImportOptions=False)
        context = SimpleNamespace(area=SimpleNamespace(type="VIEW_3D"))
        result = native._run_mesh_import(context, importer, proxy, mesh_path, preferences)

        self.assertTrue(result)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], proxy)
        self.assertEqual(calls[0][1], mesh_path)
        self.assertEqual(calls[0][0].get("~GAME"), "OWOTS")
        self.assertEqual(calls[0][0].get("assetType"), "MESH")

    def test_provider_registration_rolls_back_after_endpoint_failure(self):
        native = load_native()
        calls = []

        class Bridge:
            API_VERSION = 1

            def register_provider(self, **_kwargs):
                calls.append("register")

            def unregister_provider(self, provider_id):
                calls.append(("unregister", provider_id))

            def configure_provider(self, *_args):
                raise RuntimeError("endpoint failed")

            def refresh_provider(self, *_args):
                calls.append("refresh")

            def is_provider_available(self, *_args):
                return False

            def register_icon(self, *_args):
                pass

            def clear_icons(self, *_args):
                pass

            def list_providers(self):
                return ()

        old_bridge, old_loaded, old_registered = native._bridge, native._bridge_loaded, native._registered
        native._bridge = Bridge()
        native._bridge_loaded = True
        native._registered = False
        try:
            self.assertFalse(native.register())
            self.assertEqual(calls, ["register", ("unregister", native.PROVIDER_ID)])
            self.assertFalse(native.is_registered())
            self.assertIsNone(native._server)
        finally:
            native._bridge = old_bridge
            native._bridge_loaded = old_loaded
            native._registered = old_registered

    def test_import_waits_for_native_preview_decode_without_retrying(self):
        native = load_native()
        loading = [True]
        preview = SimpleNamespace(clear_preview=mock.Mock(), is_loading=lambda: loading[0])
        callbacks = []
        timers = SimpleNamespace(register=lambda fn, **kwargs: callbacks.append(fn))
        context = SimpleNamespace(area=None, window=None, window_manager=None)
        importer = mock.Mock(return_value=True)
        with mock.patch.object(native, "_registered", True), \
             mock.patch.object(native, "_pending_import_callback", None), \
             mock.patch.object(native.bpy, "app", SimpleNamespace(timers=timers), create=True), \
             mock.patch.object(native.importlib, "import_module", return_value=preview), \
             mock.patch.object(native, "_run_mesh_import", importer):
            self.assertTrue(native._import_after_preview(context, None, None, "mesh", None))
            self.assertEqual(len(callbacks), 1)
            self.assertEqual(callbacks[0](), 0.1)
            importer.assert_not_called()
            loading[0] = False
            self.assertIsNone(callbacks[0]())
            importer.assert_called_once()
            self.assertIsNone(native._pending_import_callback)

    def test_catalog_navigation_reuses_snapshot_until_refresh(self):
        index = self.resources.CatalogIndex(str(self.root))
        with mock.patch.object(self.resources, "iter_assets", side_effect=AssertionError("TSV re-read")):
            self.assertEqual(index.summary()["assets"], 2)
            self.assertEqual(len(index.tree("/Assets/OWOTS/art/model/ch0")["children"]), 2)
            self.assertIsNotNone(index.find(self.resources.asset_id_for("OWOTS", "art/model/ch0/body.mesh")))


if __name__ == "__main__":
    unittest.main()
