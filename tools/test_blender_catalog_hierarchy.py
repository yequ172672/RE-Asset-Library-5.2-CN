"""Validate path catalog parents and UUID preservation in isolated Blender.

This test writes only to the explicit temporary output directory and never
opens a game file or a user library blend.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
import uuid

import bpy


def parse_args() -> argparse.Namespace:
    try:
        separator = sys.argv.index("--")
        argv = sys.argv[separator + 1 :]
    except ValueError:
        argv = []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-addon", required=True, help="RE Asset Library add-on directory")
    parser.add_argument("--output-dir", required=True, type=Path, help="Empty isolated output directory")
    return parser.parse_args(argv)


def load_addon(path_value: str):
    addon_path = Path(path_value).expanduser().resolve()
    if str(addon_path.parent) not in sys.path:
        sys.path.insert(0, str(addon_path.parent))
    result = bpy.ops.preferences.addon_enable(module=addon_path.name)
    if "FINISHED" not in result:
        raise RuntimeError(f"Blender could not enable {addon_path.name}: {result}")
    module = importlib.import_module(addon_path.name)
    callback = getattr(module, "on_register", None)
    if callback is not None:
        try:
            bpy.app.timers.unregister(callback)
        except Exception:
            pass
    return module


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cats_path = output_dir / "blender_assets.cats.txt"
    preserved_uuid = "12345678-1234-5678-9abc-def012345678"
    cats_path.write_text(
        "# test catalog\nVERSION 1\n"
        f"{preserved_uuid}:art/model/character/ch0/ch001_00/00:custom-label\n",
        encoding="utf-8",
    )

    addon = load_addon(args.asset_addon)
    operators = importlib.import_module(addon.__name__ + ".modules.asset.re_asset_operators")
    operators.createBlenderCatalog(
        ["art/model/character/ch0/ch001_00/00", "art/model/ground"],
        str(output_dir),
    )

    entries: dict[str, tuple[str, str]] = {}
    for raw_line in cats_path.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.startswith("#") or raw_line.startswith("VERSION "):
            continue
        parts = raw_line.split(":", 2)
        if len(parts) == 3:
            entries[parts[1]] = (parts[0], parts[2])
    required = {
        "art",
        "art/model",
        "art/model/character",
        "art/model/character/ch0",
        "art/model/character/ch0/ch001_00",
        "art/model/character/ch0/ch001_00/00",
        "art/model/ground",
    }
    missing = sorted(required - set(entries))
    if missing:
        raise AssertionError(f"missing catalog paths: {missing}")
    if entries["art/model/character/ch0/ch001_00/00"] != (preserved_uuid, "custom-label"):
        raise AssertionError("existing UUID/simple name was not preserved")
    if operators.getCatalogUUIDDict(str(cats_path)).get(preserved_uuid) != "art/model/character/ch0/ch001_00/00":
        raise AssertionError("catalog UUID lookup did not preserve the custom path")
    uuids = [value[0] for value in entries.values()]
    if len(uuids) != len(set(uuids)) or any(not _is_uuid(value) for value in uuids):
        raise AssertionError("catalog UUIDs are not unique and valid")

    print(
        "BLENDER_CATALOG_HIERARCHY_TEST "
        + json.dumps(
            {"catalog": str(cats_path), "entries": len(entries), "required": len(required)},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
