"""Update an existing RE Asset Library blend from its adjacent migrated TSV.

Run this inside Blender 5.2 after ``migrate_asset_library_catalog.py`` has
produced the TSV in the same library directory.  The add-on's catalog import
preserves existing Blender catalog UUIDs and only creates missing paths and
their explicit parents.  No PAK cache is rebuilt and no resource is extracted.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
from pathlib import Path
import sys

import bpy


def parse_args() -> argparse.Namespace:
    try:
        separator = sys.argv.index("--")
        argv = sys.argv[separator + 1 :]
    except ValueError:
        argv = []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-addon", required=True, help="RE Asset Library add-on directory")
    parser.add_argument("--blend", required=True, type=Path, help="Existing REAssetLibrary_XXXX.blend")
    parser.add_argument(
        "--catalog",
        type=Path,
        help="Optional catalog path; it must be the blend's adjacent REAssetCatalog_XXXX.tsv",
    )
    return parser.parse_args(argv)


def load_addon(path_value: str):
    addon_path = Path(path_value).expanduser().resolve()
    if not (addon_path / "__init__.py").is_file():
        raise FileNotFoundError(f"Asset add-on __init__.py not found: {addon_path}")
    if str(addon_path.parent) not in sys.path:
        sys.path.insert(0, str(addon_path.parent))
    module_name = addon_path.name
    result = bpy.ops.preferences.addon_enable(module=module_name)
    if "FINISHED" not in result:
        raise RuntimeError(f"Blender could not enable {module_name}: {result}")
    module = importlib.import_module(module_name)
    callback = getattr(module, "on_register", None)
    if callback is not None:
        try:
            bpy.app.timers.unregister(callback)
        except Exception:
            pass
    return module


def catalog_stats(catalog_path: Path) -> dict[str, int]:
    rows = 0
    tsv_categories: set[str] = set()
    with catalog_path.open("r", encoding="utf-8", newline="") as stream:
        import csv

        reader = csv.reader(stream, delimiter="\t", quotechar='"')
        next(reader, None)
        for row in reader:
            if not row:
                continue
            rows += 1
            if len(row) >= 3 and row[2].strip():
                tsv_categories.add(row[2].strip())
    catalog_definitions = 0
    cats_path = catalog_path.parent / "blender_assets.cats.txt"
    if cats_path.is_file():
        catalog_definitions = sum(
            1
            for line in cats_path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and not line.startswith("VERSION ")
        )
    return {
        "catalogRows": rows,
        "tsvCategories": len(tsv_categories),
        "catalogDefinitions": catalog_definitions,
    }


def asset_key(file_path: str, platform: str, language: str) -> str:
    full_path = str(file_path)
    if platform:
        full_path += "." + str(platform)
    if language:
        full_path += "." + str(language)
    return full_path.replace("\\", "/").lower()


def load_catalog_rows(catalog_path: Path, whitelist: set[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    with catalog_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t", quotechar='"')
        next(reader, None)
        for row in reader:
            if len(row) < 6:
                continue
            extension = os.path.splitext(row[0])[1][1:].lower()
            if extension in whitelist:
                rows.append(row)
    return rows


def catalog_uuid_paths(catalog_path: Path) -> dict[str, str]:
    """Read UUID-to-path mappings without importing Blender catalog internals."""

    result: dict[str, str] = {}
    cats_path = catalog_path.parent / "blender_assets.cats.txt"
    if not cats_path.is_file():
        return result
    for raw_line in cats_path.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.startswith("#") or raw_line.startswith("VERSION "):
            continue
        parts = raw_line.split(":", 2)
        if len(parts) == 3:
            result[parts[0].strip().lower()] = parts[1].strip()
    return result


def main() -> int:
    args = parse_args()
    blend_path = args.blend.expanduser().resolve()
    if not blend_path.is_file():
        raise FileNotFoundError(f"blend not found: {blend_path}")
    if not blend_path.name.startswith("REAssetLibrary_") or not blend_path.name.lower().endswith(".blend"):
        raise ValueError("blend must be named REAssetLibrary_XXXX.blend")
    game_name = blend_path.name[len("REAssetLibrary_") : -len(".blend")]
    expected_catalog = blend_path.parent / f"REAssetCatalog_{game_name}.tsv"
    catalog_path = args.catalog.expanduser().resolve() if args.catalog else expected_catalog
    if catalog_path != expected_catalog.resolve():
        raise ValueError(f"catalog must be adjacent to the blend at {expected_catalog}")
    if not catalog_path.is_file():
        raise FileNotFoundError(f"catalog not found: {catalog_path}")
    game_info_path = blend_path.parent / f"GameInfo_{game_name}.json"
    if not game_info_path.is_file():
        raise FileNotFoundError(f"GameInfo not found: {game_info_path}")

    asset_module = load_addon(args.asset_addon)
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))

    with game_info_path.open("r", encoding="utf-8") as stream:
        game_info = json.load(stream)
    whitelist = {str(item).lower() for item in game_info.get("fileTypeWhiteList", [])}
    catalog_rows = load_catalog_rows(catalog_path, whitelist)
    rows_by_key: dict[str, list[str]] = {}
    for row in catalog_rows:
        key = asset_key(row[0], row[4], row[5])
        if key in rows_by_key:
            raise RuntimeError(f"duplicate catalog asset path: {key}")
        rows_by_key[key] = row

    asset_objects = [
        obj for obj in bpy.data.objects if obj.get("~TYPE") == "RE_ASSET_LIBRARY_ASSET"
    ]
    objects_by_key: dict[str, object] = {}
    for obj in asset_objects:
        key = asset_key(obj.get("assetPath", ""), obj.get("platExt", ""), obj.get("langExt", ""))
        if key in objects_by_key:
            raise RuntimeError(f"duplicate blend asset path: {key}")
        objects_by_key[key] = obj
    missing_objects = sorted(set(rows_by_key) - set(objects_by_key))
    extra_objects = sorted(set(objects_by_key) - set(rows_by_key))
    if missing_objects or extra_objects:
        raise RuntimeError(
            "catalog/blend asset set differs; refusing to create, delete or reimport objects "
            f"(missing={len(missing_objects)}, extra={len(extra_objects)})"
        )

    # Importing the catalog operator would reset names/tags and could create
    # objects.  Generate only the catalog definitions, then update catalog_id
    # on the existing asset objects in place.
    asset_package = asset_module.__name__
    asset_operators = importlib.import_module(asset_package + ".modules.asset.re_asset_operators")
    catalog_helpers = importlib.import_module(asset_package + ".modules.asset.catalog_paths")
    categories = sorted({row[2].strip() for row in catalog_rows if row[2].strip()})
    catalog_ids = asset_operators.createBlenderCatalog(categories, str(blend_path.parent))
    uuid_to_path = catalog_uuid_paths(catalog_path)
    changed_catalog_ids = 0
    preserved_manual_catalogs = 0
    for key, row in rows_by_key.items():
        obj = objects_by_key[key]
        desired_category = row[2].strip()
        current_uuid = str(obj.asset_data.catalog_id).lower()
        current_category = uuid_to_path.get(current_uuid)
        # A custom catalog currently assigned in the blend is a manual choice.
        # Only an unassigned catalog or an exact old automatic category is
        # eligible for migration to the path category from the TSV.  Preserve
        # unknown UUIDs too: they may belong to a catalog definition managed
        # outside the staged TSV.
        if catalog_helpers.should_preserve_catalog_assignment(
            row[0], current_uuid, current_category, desired_category
        ):
            preserved_manual_catalogs += 1
            continue
        if desired_category:
            target_uuid = catalog_ids.get(desired_category)
            if not target_uuid:
                raise RuntimeError(f"catalog path was not created: {desired_category}")
            if str(obj.asset_data.catalog_id).lower() != target_uuid.lower():
                obj.asset_data.catalog_id = target_uuid
                changed_catalog_ids += 1
        elif not catalog_helpers.catalog_uuid_is_unassigned(current_uuid):
            # Blender represents an asset without a catalog with the all-zero
            # UUID.  Clear a legacy automatic assignment when its migrated
            # resource directory is the catalog root (an empty path).
            obj.asset_data.catalog_id = ""
            changed_catalog_ids += 1

    if len(
        [obj for obj in bpy.data.objects if obj.get("~TYPE") == "RE_ASSET_LIBRARY_ASSET"]
    ) != len(asset_objects):
        raise RuntimeError("asset object count changed while updating catalog IDs")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    report = {
        "blend": str(blend_path),
        "catalog": str(catalog_path),
        "assetObjects": len(asset_objects),
        "changedCatalogIds": changed_catalog_ids,
        "preservedManualCatalogs": preserved_manual_catalogs,
        **catalog_stats(catalog_path),
    }
    print("ASSET_LIBRARY_BLEND_UPDATED " + json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
