"""Build a local RE Asset Library in headless Blender without touching the game.

The script is executed by Blender with arguments after ``--``. It creates the
catalog, GameInfo, ExtractInfo, PAK cache, an empty extraction root, and a
library blend containing catalog asset placeholders. It never calls
``save_userpref`` and never writes under the game directory.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
from zlib import crc32

import bpy


def parse_args() -> argparse.Namespace:
    try:
        separator = sys.argv.index("--")
        argv = sys.argv[separator + 1 :]
    except ValueError:
        argv = []

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-addon", required=True, help="RE Asset Library add-on directory")
    parser.add_argument("--mesh-addon", required=True, help="RE Mesh Editor add-on directory")
    parser.add_argument("--chain-addon", required=True, help="RE Chain Editor add-on directory")
    parser.add_argument("--list", dest="list_path", required=True, help="RE Tool .list file")
    parser.add_argument("--game-name", required=True, help="Library ID, for example OWOTS")
    parser.add_argument("--game-exe", required=True, help="Game executable used for ExtractInfo")
    parser.add_argument("--output-dir", required=True, help="Output library directory")
    parser.add_argument("--extract-dir", required=True, help="Empty extraction root (for example .../OWOTS_EXTRACT/re_chunk_000)")
    parser.add_argument("--platform", default="STM", choices=["STM", "MSG", "x64"])
    parser.add_argument(
        "--file-types",
        nargs="*",
        default=["mesh", "chain", "chain2", "fbxskel"],
        help="Catalog file types to include",
    )
    return parser.parse_args(argv)


def load_addon(path_value: str):
    addon_path = Path(path_value).expanduser().resolve()
    if not (addon_path / "__init__.py").is_file():
        raise FileNotFoundError("Asset add-on __init__.py not found: %s" % addon_path)
    if str(addon_path.parent) not in sys.path:
        sys.path.insert(0, str(addon_path.parent))
    module_name = addon_path.name
    result = bpy.ops.preferences.addon_enable(module=module_name)
    if "FINISHED" not in result:
        raise RuntimeError("Blender could not enable %s: %s" % (module_name, result))
    module = importlib.import_module(module_name)
    callback = getattr(module, "on_register", None)
    if callback is not None:
        try:
            bpy.app.timers.unregister(callback)
        except Exception:
            pass
    return module, addon_path


def get_file_crc(path: Path) -> int:
    value = 0
    with path.open("rb") as stream:
        while chunk := stream.read(10 * 1024 * 1024):
            value = crc32(chunk, value)
    return value


def parse_after_build(
    game_info_path: Path,
    catalog_path: Path,
    blend_path: Path,
    extract_info_path: Path,
    pak_cache_path: Path,
    extract_dir: Path,
) -> dict:
    with game_info_path.open("r", encoding="utf-8") as stream:
        game_info = json.load(stream)
    expected_paths: set[str] = set()
    catalog_rows = 0
    with catalog_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t", quotechar='"')
        next(reader, None)
        for row in reader:
            catalog_rows += 1
            if len(row) < 6 or row[1] == "":
                continue
            if row[0].rsplit(".", 1)[-1].lower() not in {
                str(item).lower() for item in game_info["fileTypeWhiteList"]
            }:
                continue
            path = row[0]
            if row[4]:
                path += "." + row[4]
            if row[5]:
                path += "." + row[5]
            expected_paths.add(path.replace("\\", "/").lower())

    asset_objects = [
        obj
        for obj in bpy.data.objects
        if obj.get("~TYPE") == "RE_ASSET_LIBRARY_ASSET"
    ]
    actual_paths = set()
    invalid_paths = []
    for obj in asset_objects:
        path = str(obj.get("assetPath", "")).replace("\\", "/")
        if not path or os.path.isabs(path) or ".." in Path(path).parts:
            invalid_paths.append(path)
            continue
        for key in ("platExt", "langExt"):
            if obj.get(key):
                path += "." + str(obj[key])
        actual_paths.add(path.lower())
    missing_paths = sorted(expected_paths - actual_paths)
    extra_paths = sorted(actual_paths - expected_paths)
    with extract_info_path.open("r", encoding="utf-8") as stream:
        extract_info = json.load(stream)
    extract_files = [path for path in extract_dir.rglob("*") if path.is_file()]
    return {
        "gameName": game_info["GameName"],
        "catalogRows": catalog_rows,
        "assetPlaceholderObjects": len(asset_objects),
        "expectedAssetObjects": len(expected_paths),
        "missingAssetPaths": missing_paths[:50],
        "extraAssetPaths": extra_paths[:50],
        "invalidAssetPaths": invalid_paths[:50],
        "assetPathCheckOk": not missing_paths and not extra_paths and not invalid_paths,
        "blendBytes": blend_path.stat().st_size,
        "catalogBytes": catalog_path.stat().st_size,
        "gameInfoBytes": game_info_path.stat().st_size,
        "extractInfoPath": str(extract_info_path),
        "extractPathMatches": Path(extract_info["extractPath"]).resolve() == extract_dir.resolve(),
        "extractFileCount": len(extract_files),
        "pakCacheBytes": pak_cache_path.stat().st_size,
    }


def main() -> int:
    args = parse_args()
    mesh_module, _ = load_addon(args.mesh_addon)
    chain_module, _ = load_addon(args.chain_addon)
    asset_module, addon_dir = load_addon(args.asset_addon)
    list_path = Path(args.list_path).expanduser().resolve()
    game_exe = Path(args.game_exe).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    extract_dir = Path(args.extract_dir).expanduser().resolve()
    if not list_path.is_file():
        raise FileNotFoundError("list file not found: %s" % list_path)
    if not game_exe.is_file() or game_exe.suffix.lower() != ".exe":
        raise FileNotFoundError("game executable not found: %s" % game_exe)
    if output_dir == game_exe.parent or output_dir.is_relative_to(game_exe.parent):
        raise ValueError("output directory must be outside the game directory")
    if extract_dir == game_exe.parent or extract_dir.is_relative_to(game_exe.parent):
        raise ValueError("extract directory must be outside the game directory")

    output_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    game_info_path = output_dir / ("GameInfo_%s.json" % args.game_name)
    catalog_path = output_dir / ("REAssetCatalog_%s.tsv" % args.game_name)
    blend_path = output_dir / ("REAssetLibrary_%s.blend" % args.game_name)
    extract_info_path = output_dir / ("ExtractInfo_%s.json" % args.game_name)
    pak_cache_path = output_dir / ("PakCache_%s.pakcache" % args.game_name)

    asset_module.REToolListFileToREAssetCatalogAndGameInfo(
        str(list_path),
        str(catalog_path),
        str(game_info_path),
        list(args.file_types),
    )

    extract_info = {
        "exePath": str(game_exe),
        "exeDate": game_exe.stat().st_mtime,
        "exeCRC": get_file_crc(game_exe),
        "extractPath": str(extract_dir),
        "platform": args.platform,
    }
    extract_info_path.write_text(
        json.dumps(extract_info, indent=4, ensure_ascii=False), encoding="utf-8"
    )

    pak_utils = importlib.import_module(
        asset_module.__name__ + ".modules.pak.re_pak_utils"
    )
    pak_paths = pak_utils.scanForPakFiles(str(game_exe.parent))
    if not pak_paths:
        raise RuntimeError("No PAK files found beside %s" % game_exe)
    pak_paths.reverse()
    pak_utils.createPakCacheFile(pak_paths, str(pak_cache_path))

    source_blend = addon_dir / "Resources" / "Blend" / "libraryBase.blend"
    if not source_blend.is_file():
        raise FileNotFoundError("libraryBase.blend missing: %s" % source_blend)
    shutil.copyfile(source_blend, blend_path)

    # Load the copied base blend, create catalog placeholders, and save only
    # the output blend. The initialize operator also saves user preferences,
    # so import_catalog is called directly after setting the library markers.
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    bpy.context.scene["isREAssetLibrary"] = True
    bpy.context.scene["REAssetLibrary_Game"] = args.game_name
    result = bpy.ops.re_asset.import_catalog()
    if "FINISHED" not in result:
        raise RuntimeError("Catalog import failed: %s" % result)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    report = parse_after_build(
        game_info_path,
        catalog_path,
        blend_path,
        extract_info_path,
        pak_cache_path,
        extract_dir,
    )
    report.update(
        {
            "outputDir": str(output_dir),
            "extractRoot": str(extract_dir),
            "extractInfo": str(extract_info_path),
            "pakCache": str(pak_cache_path),
            "pakCount": len(pak_paths),
            "blendPath": str(blend_path),
        }
    )
    report_path = output_dir / "build_manifest.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("LOCAL_LIBRARY_BUILD", json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
