"""Headless Blender check for asset-browser append, PAK extraction and dispatch queue.

This intentionally replaces the editor import callback with a recorder. Blender
5.2 cannot safely run the interactive Mesh Editor operator re-entrantly from a
background ``blend_import_post`` callback; the real editor importer is covered
separately by ``headless_validate.py`` after this script's extracted path.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

import bpy


def parse_args() -> argparse.Namespace:
    try:
        argv = sys.argv[sys.argv.index("--") + 1 :]
    except ValueError:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-addon", required=True)
    parser.add_argument("--mesh-addon", required=True)
    parser.add_argument("--chain-addon")
    parser.add_argument("--library", required=True)
    parser.add_argument("--extract", required=True)
    parser.add_argument("--asset-name", nargs="+", default=["sm45_0020_03.mesh", "sm45_0020_02.mesh"])
    return parser.parse_args(argv)


def enable_addon(path: str):
    addon_path = Path(path).resolve()
    if str(addon_path.parent) not in sys.path:
        sys.path.insert(0, str(addon_path.parent))
    result = bpy.ops.preferences.addon_enable(module=addon_path.name)
    if "FINISHED" not in result:
        raise RuntimeError(f"could not enable {addon_path.name}: {result}")
    return importlib.import_module(addon_path.name)


def main() -> int:
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh_module = enable_addon(args.mesh_addon)
    if args.chain_addon:
        enable_addon(args.chain_addon)
    asset_module = enable_addon(args.asset_addon)
    try:
        bpy.app.timers.unregister(asset_module.on_register)
    except Exception:
        pass

    mesh_preferences = bpy.context.preferences.addons[mesh_module.__name__].preferences
    chunk_item = mesh_preferences.chunkPathList_items.add()
    chunk_item.gameName = "OWOTS"
    chunk_item.path = str(Path(args.extract) / "natives" / "STM")
    asset_preferences = bpy.context.preferences.addons[asset_module.__name__].preferences
    asset_preferences.showMeshImportOptions = False
    asset_preferences.forceExtract = True

    calls = []

    def record_import(obj, path, preferences):
        calls.append({"name": obj.name, "path": path})
        return True

    asset_module.importREMeshAsset = record_import
    library = str(Path(args.library).resolve())
    for asset_name in args.asset_name:
        bpy.ops.wm.append(
            directory=library + "\\Object\\",
            filename=asset_name,
            link=False,
        )
    if asset_module.execution_queue.empty():
        raise RuntimeError("asset append did not enqueue deferred import/cleanup")
    try:
        bpy.app.timers.unregister(asset_module.execute_queued_functions)
    except Exception:
        pass
    asset_module.execute_queued_functions()
    if len(calls) != len(args.asset_name):
        raise RuntimeError("deferred asset import callback was not called")
    for call in calls:
        extracted = Path(call["path"])
        if not extracted.is_file():
            raise RuntimeError(f"deferred callback path is missing: {extracted}")
    print("ASSET_BROWSER_DISPATCH_RESULT")
    print(json.dumps({
        "assets": args.asset_name,
        "callbacks": calls,
        "extracted_sizes": [Path(call["path"]).stat().st_size for call in calls],
        "queue_empty": asset_module.execution_queue.empty(),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
