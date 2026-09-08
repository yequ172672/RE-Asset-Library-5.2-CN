"""Headless Blender validation for RE Asset Library and its RE editor dependencies.

Run this file with Blender, not the system Python interpreter.  The launcher
should pass ``--factory-startup`` and point ``BLENDER_USER_CONFIG`` and
``BLENDER_USER_SCRIPTS`` at an isolated temporary directory.  Add-on packages
are loaded from the paths supplied on the command line, so the user's enabled
add-ons are not required.

The validator deliberately skips mesh files whose numeric extension is not in
the installed RE Mesh Editor map.  Pass ``--allow-unsupported-mesh`` only when
you explicitly want to exercise the editor's nearest-version fallback; such a
run is reported as heuristic and never as a supported import.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import traceback
from typing import Any


try:
    import bpy
except ImportError as exc:  # pragma: no cover - this file is run by Blender.
    raise SystemExit("headless_validate.py must be executed with Blender: %s" % exc)


RESULT_MARKER = "HEADLESS_VALIDATE_RESULT"


def parse_args() -> argparse.Namespace:
    """Parse only arguments after Blender's ``--`` separator."""

    try:
        separator = sys.argv.index("--")
        argv = sys.argv[separator + 1 :]
    except ValueError:
        argv = []

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--asset-addon",
        required=True,
        help="Path to the RE Asset Library add-on source directory.",
    )
    parser.add_argument(
        "--mesh-addon",
        required=True,
        help="Path to the RE Mesh Editor add-on source directory.",
    )
    parser.add_argument(
        "--chain-addon",
        help="Optional path to the RE Chain Editor add-on source directory.",
    )
    parser.add_argument(
        "--list",
        dest="list_path",
        help="Optional REE.PAK.Tool .list file for catalog/GameInfo generation.",
    )
    parser.add_argument(
        "--game-name",
        default="VALIDATION",
        help="Game ID used for temporary GameInfo/catalog output (default: VALIDATION).",
    )
    parser.add_argument(
        "--mesh",
        help="Optional extracted .mesh.<version> file to import directly.",
    )
    parser.add_argument(
        "--mdf",
        help="Optional .mdf2.<version> file used when --load-materials is enabled.",
    )
    parser.add_argument(
        "--load-materials",
        action="store_true",
        help="Load MDF/material data during a requested mesh import.",
    )
    parser.add_argument(
        "--reload-cached-textures",
        action="store_true",
        help="Force texture conversion instead of reusing the Mesh Editor cache.",
    )
    parser.add_argument(
        "--highest-lod-only",
        action="store_true",
        help="Import only source LOD0, matching the Mesh Editor's default import path.",
    )
    parser.add_argument(
        "--require-texture-pattern",
        action="append",
        default=[],
        help="Require a file-backed image whose name or path contains this pattern (repeatable).",
    )
    parser.add_argument(
        "--require-texture-min-size",
        nargs=2,
        type=int,
        metavar=("WIDTH", "HEIGHT"),
        help="Minimum width and height for images matched by --require-texture-pattern.",
    )
    parser.add_argument(
        "--allow-unsupported-mesh",
        action="store_true",
        help="Exercise nearest-version fallback for an unknown mesh extension.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code for requested checks that fail or are skipped.",
    )
    parser.add_argument(
        "--require-armature",
        action="store_true",
        help="In strict mesh validation, require at least one armature and one bone.",
    )
    parser.add_argument(
        "--require-weights",
        action="store_true",
        help="In strict mesh validation, require weighted vertices and vertex groups.",
    )
    return parser.parse_args(argv)


def load_addon(path_value: str) -> Any:
    """Enable an add-on from an arbitrary directory under its real package name."""

    addon_path = Path(path_value).expanduser().resolve()
    init_path = addon_path / "__init__.py"
    if not init_path.is_file():
        raise FileNotFoundError("add-on __init__.py not found: %s" % init_path)

    # addon_utils scans sys.path for the package.  Using the actual directory
    # name is required because RE Asset Library discovers Mesh Editor through
    # the canonical preference key containing ``RE-Mesh-Editor``.
    module_name = addon_path.name
    if str(addon_path.parent) not in sys.path:
        sys.path.insert(0, str(addon_path.parent))
    result = bpy.ops.preferences.addon_enable(module=module_name)
    if "FINISHED" not in result:
        raise RuntimeError("Blender could not enable add-on %s: %s" % (module_name, result))
    if module_name not in bpy.context.preferences.addons:
        raise RuntimeError("enabled add-on has no preference entry: %s" % module_name)
    module = importlib.import_module(module_name)
    return module


def finish_addon_enable(module: Any) -> None:
    """Suppress the Asset Library preference callback after Blender enables it."""

    # RE Asset Library schedules this callback to inspect the real Blender
    # preferences.  Manual loading intentionally has no preferences entry, so
    # cancel it before the timer can run and create state outside this test.
    callback = getattr(module, "on_register", None)
    if callback is not None:
        try:
            bpy.app.timers.unregister(callback)
        except Exception:
            pass


def enum_from_rna(owner: Any, property_name: str) -> tuple[list[dict[str, str]], str]:
    """Read an enum from RNA, falling back to Blender's deferred annotation."""

    rna = getattr(owner, "bl_rna", None)
    if rna is not None:
        try:
            prop = rna.properties[property_name]
            if prop.type == "ENUM":
                return (
                    [
                        {"identifier": item.identifier, "name": item.name}
                        for item in prop.enum_items
                    ],
                    "rna",
                )
        except (KeyError, AttributeError, TypeError):
            pass

    annotation = getattr(owner, "__annotations__", {}).get(property_name)
    keywords = getattr(annotation, "keywords", {})
    items = keywords.get("items", []) if isinstance(keywords, dict) else []
    if callable(items):
        try:
            items = items(None, None)
        except Exception:
            items = []
    return (
        [
            {"identifier": str(item[0]), "name": str(item[1])}
            for item in items
            if isinstance(item, (tuple, list)) and len(item) >= 2
        ],
        "annotation" if items else "missing",
    )


def operator_exists(category: str, name: str) -> bool:
    """Return whether a Blender operator was registered."""

    try:
        operator = getattr(getattr(bpy.ops, category), name)
        get_rna_type = getattr(operator, "get_rna_type", None)
        if not callable(get_rna_type):
            return False
        try:
            return get_rna_type() is not None
        except (AttributeError, KeyError, RuntimeError, TypeError):
            return False
    except (AttributeError, KeyError, RuntimeError, TypeError):
        return False


def operator_rna_fields(owner: Any) -> list[str]:
    """Return custom RNA property names for an operator class."""

    rna = getattr(owner, "bl_rna", None)
    if rna is None:
        return []
    return [
        prop.identifier
        for prop in rna.properties
        if prop.identifier not in {
            "rna_type",
            "name",
            "properties",
            "has_reports",
            "bl_idname",
            "bl_label",
            "bl_translation_context",
            "bl_description",
            "bl_undo_group",
            "bl_options",
            "bl_cursor_pending",
            "layout",
            "options",
            "macros",
        }
    ]


def module_version(module: Any) -> str | None:
    info = getattr(module, "bl_info", {})
    version = info.get("version") if isinstance(info, dict) else None
    return ".".join(str(part) for part in version) if version else None


def read_editor_maps(mesh_module: Any) -> dict[str, Any]:
    """Expose the installed editor's file/game mappings for the report."""

    mesh_file = importlib.import_module(
        mesh_module.__name__ + ".modules.mesh.file_re_mesh"
    )
    mdf_file = importlib.import_module(
        mesh_module.__name__ + ".modules.mdf.file_re_mdf"
    )
    tex_versions = importlib.import_module(
        mesh_module.__name__ + ".modules.tex.enums.game_version_enum"
    )
    return {
        "mesh_file_to_game": {
            str(key): value
            for key, value in mesh_file.meshFileVersionToGameNameDict.items()
        },
        "mdf_file_to_game": {
            str(key): value
            for key, value in mdf_file.gameNameMDFVersionDict.items()
            if isinstance(key, int)
        },
        "mdf_game_to_file": {
            str(key): value
            for key, value in mdf_file.gameNameMDFVersionDict.items()
            if isinstance(key, str)
        },
        "tex_game_to_file": {
            str(key): value
            for key, value in tex_versions.gameNameToTexVersionDict.items()
        },
    }


def generate_catalog(asset_module: Any, list_path: str, game_name: str) -> dict[str, Any]:
    """Generate catalog/GameInfo in a temporary directory and summarize them."""

    source = Path(list_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("list file not found: %s" % source)

    with tempfile.TemporaryDirectory(prefix="re_asset_library_validation_") as temp_dir:
        temp = Path(temp_dir)
        catalog_path = temp / ("REAssetCatalog_%s.tsv" % game_name)
        game_info_path = temp / ("GameInfo_%s.json" % game_name)
        asset_module.REToolListFileToREAssetCatalogAndGameInfo(
            str(source),
            str(catalog_path),
            str(game_info_path),
            ["mesh", "chain", "chain2", "fbxskel"],
        )

        with game_info_path.open("r", encoding="utf-8") as stream:
            game_info = json.load(stream)
        with catalog_path.open("r", encoding="utf-8") as stream:
            catalog_rows = max(sum(1 for _ in stream) - 1, 0)

        return {
            "ok": True,
            "source": str(source),
            "catalog_rows": catalog_rows,
            "catalog_bytes": catalog_path.stat().st_size,
            "game_info_bytes": game_info_path.stat().st_size,
            "game_info": game_info,
            "temporary_output": True,
        }


def mesh_import_options(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "clearScene": True,
        "createCollections": True,
        "loadMaterials": bool(args.load_materials),
        "loadMDFData": bool(args.load_materials),
        "loadShellFur": False,
        "loadUnusedTextures": False,
        "loadUnusedProps": False,
        "useBackfaceCulling": False,
        "reloadCachedTextures": bool(
            args.reload_cached_textures or (args.strict and args.load_materials)
        ),
        "mdfPath": str(Path(args.mdf).expanduser().resolve()) if args.mdf else "",
        "importAllLODs": not args.highest_lod_only,
        "importBlendShapes": True,
        "rotate90": True,
        "mergeArmature": "",
        "importArmatureOnly": False,
        "mergeGroups": False,
        "importShadowMeshes": False,
        "importOcclusionMeshes": False,
        "importBoundingBoxes": False,
    }


def image_stats() -> dict[str, Any]:
    """Count usable file-backed images while excluding default empty images."""

    file_backed = []
    empty = 0
    for image in bpy.data.images:
        try:
            filepath = str(image.filepath)
            width, height = image.size[:2]
            if filepath and image.source == "FILE" and width > 0 and height > 0:
                file_backed.append(image)
            else:
                empty += 1
        except Exception:
            empty += 1
    dimensions = [
        {
            "name": str(image.name),
            "filepath": str(image.filepath),
            "width": int(image.size[0]),
            "height": int(image.size[1]),
        }
        for image in file_backed
    ]
    return {
        "file_backed_image_count": len(file_backed),
        "empty_or_default_image_count": empty,
        "file_backed_dimensions": dimensions,
    }


def source_lod_stats(mesh_module: Any, source: Path) -> list[dict[str, Any]]:
    """Parse source LODs without importing Blender objects or materials."""

    blender_mesh = importlib.import_module(
        mesh_module.__name__ + ".modules.mesh.blender_re_mesh"
    )
    # readREMesh parses every source LOD when lodTarget=None.  ParsedREMesh
    # retains reused submeshes as links; count only their owning submesh, just
    # as the Blender importer does when it creates mesh datablocks.
    raw_mesh = blender_mesh.readREMesh(str(source), lodTarget=None)
    parsed_mesh = blender_mesh.ParsedREMesh()
    parsed_mesh.ParseREMesh(raw_mesh)
    lods: list[dict[str, Any]] = []
    for lod_index, lod in enumerate(parsed_mesh.mainMeshLODList):
        submeshes = [
            submesh
            for group in lod.visconGroupList
            for submesh in group.subMeshList
        ]
        owned_submeshes = [submesh for submesh in submeshes if not submesh.isReusedMesh]
        lods.append(
            {
                "index": lod_index,
                "distance": float(lod.lodDistance),
                "group_count": len(lod.visconGroupList),
                "submesh_count": len(owned_submeshes),
                "reused_submesh_count": len(submeshes) - len(owned_submeshes),
                "vertex_count": sum(
                    len(submesh.vertexPosList or []) for submesh in owned_submeshes
                ),
                "polygon_count": sum(
                    len(submesh.faceList or []) for submesh in owned_submeshes
                ),
            }
        )
    return lods


def import_mesh(mesh_module: Any, args: argparse.Namespace, maps: dict[str, Any]) -> dict[str, Any]:
    """Import one supported mesh and report geometry/material/image counts."""

    source = Path(args.mesh).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("mesh file not found: %s" % source)
    suffix = source.suffix
    try:
        file_version = int(suffix[1:]) if suffix.startswith(".") else None
    except ValueError:
        file_version = None

    known_versions = {int(value) for value in maps["mesh_file_to_game"]}
    supported = file_version in known_versions
    result: dict[str, Any] = {
        "source": str(source),
        "file_version": file_version,
        "supported_by_editor_map": supported,
        "heuristic_fallback": False,
        "lod_mode": "highest_lod_only" if args.highest_lod_only else "all_lods",
    }
    if not supported and not args.allow_unsupported_mesh:
        result["status"] = "skipped_unsupported_version"
        result["ok"] = False
        result["reason"] = (
            "The installed RE Mesh Editor has no exact map entry; "
            "pass --allow-unsupported-mesh to exercise nearest-version fallback."
        )
        return result
    if not supported:
        result["heuristic_fallback"] = True

    before = {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "images": len(bpy.data.images),
    }
    importer = getattr(mesh_module, "importREMeshFile", None)
    if importer is None:
        raise RuntimeError("RE Mesh Editor importREMeshFile is unavailable")

    import_log = io.StringIO()
    source_lods: list[dict[str, Any]] = []
    source_lod_error: str | None = None
    with redirect_stdout(import_log), redirect_stderr(import_log):
        try:
            source_lods = source_lod_stats(mesh_module, source)
        except Exception as exc:
            source_lod_error = str(exc)
        warnings, errors = importer(str(source), mesh_import_options(args))
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    log_lines = [
        ansi_escape.sub("", line).strip()
        for line in import_log.getvalue().splitlines()
        if line.strip()
    ]
    missing_texture_warnings = [
        line for line in log_lines if "Could not find texture:" in line
    ]
    log_errors = [
        line
        for line in log_lines
        if (
            line.startswith("ERROR")
            or "Could not import mesh materials" in line
            or "an error occured" in line.lower()
            or "an error occurred" in line.lower()
            or "read past bounds" in line.lower()
            or "failed to convert" in line.lower()
            or "could not convert" in line.lower()
            or "traceback" in line.lower()
        )
    ]
    mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    mesh_object_count = len(mesh_objects)
    vertex_count = sum(len(obj.data.vertices) for obj in mesh_objects)
    polygon_count = sum(len(obj.data.polygons) for obj in mesh_objects)
    armature_objects = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    armature_bone_count = sum(len(obj.data.bones) for obj in armature_objects)
    vertex_group_count = sum(len(obj.vertex_groups) for obj in mesh_objects)
    vertex_weight_counts = [
        len(vertex.groups)
        for obj in mesh_objects
        for vertex in obj.data.vertices
    ]
    weighted_vertex_count = sum(count > 0 for count in vertex_weight_counts)
    unweighted_vertex_count = sum(count == 0 for count in vertex_weight_counts)
    max_weights_per_vertex = max(vertex_weight_counts, default=0)
    shape_key_object_count = sum(
        obj.data.shape_keys is not None for obj in mesh_objects
    )
    result.update(
        {
            "status": "imported_heuristic" if not supported else "imported",
            "warnings": list(dict.fromkeys(
                list(warnings or []) + missing_texture_warnings
            )),
            "errors": list(dict.fromkeys(list(errors or []) + log_errors)),
            "missing_texture_warnings": missing_texture_warnings,
            "reload_cached_textures": bool(
                args.reload_cached_textures or (args.strict and args.load_materials)
            ),
            "import_log_line_count": len(log_lines),
            "before": before,
            "after": {
                "objects": len(bpy.data.objects),
                "meshes": len(bpy.data.meshes),
                "materials": len(bpy.data.materials),
                "images": len(bpy.data.images),
            },
            "mesh_object_count": mesh_object_count,
            "vertex_count": vertex_count,
            "polygon_count": polygon_count,
            "armature_object_count": len(armature_objects),
            "armature_bone_count": armature_bone_count,
            "vertex_group_count": vertex_group_count,
            "weighted_vertex_count": weighted_vertex_count,
            "unweighted_vertex_count": unweighted_vertex_count,
            "max_weights_per_vertex": max_weights_per_vertex,
            "shape_key_object_count": shape_key_object_count,
            "object_material_slots": sum(
                len(obj.material_slots) for obj in mesh_objects
            ),
            "texture_image_count": len(bpy.data.images),
        }
    )
    result.update(image_stats())
    result["material_load_ok"] = not args.load_materials or (
        not missing_texture_warnings and result["file_backed_image_count"] > 0
    )
    result["source_lods"] = source_lods
    if source_lod_error is not None:
        result["source_lod_error"] = source_lod_error
    if source_lods:
        expected_lod = 0
        expected_vertices = source_lods[expected_lod]["vertex_count"]
        expected_polygons = source_lods[expected_lod]["polygon_count"]
        if not args.highest_lod_only:
            expected_vertices = sum(item["vertex_count"] for item in source_lods)
            expected_polygons = sum(item["polygon_count"] for item in source_lods)
        result["lod_validation"] = {
            "expected_source_lod": expected_lod if args.highest_lod_only else "all",
            "expected_vertex_count": expected_vertices,
            "expected_polygon_count": expected_polygons,
            "actual_vertex_count": vertex_count,
            "actual_polygon_count": polygon_count,
            "vertex_count_match": vertex_count == expected_vertices,
            "polygon_count_match": polygon_count == expected_polygons,
        }
    else:
        result["lod_validation"] = {
            "expected_source_lod": 0 if args.highest_lod_only else "all",
            "expected_vertex_count": None,
            "expected_polygon_count": None,
            "actual_vertex_count": vertex_count,
            "actual_polygon_count": polygon_count,
            "vertex_count_match": False,
            "polygon_count_match": False,
        }
    patterns = [pattern.casefold() for pattern in args.require_texture_pattern]
    matched_texture_requirements: list[dict[str, Any]] = []
    for pattern in patterns:
        matches = [
            item
            for item in result["file_backed_dimensions"]
            if pattern in item["name"].casefold()
            or pattern in item["filepath"].casefold()
        ]
        matched_texture_requirements.append({"pattern": pattern, "matches": matches})
    result["texture_requirements"] = {
        "patterns": matched_texture_requirements,
        "minimum_size": list(args.require_texture_min_size)
        if args.require_texture_min_size
        else None,
    }
    if args.require_texture_min_size:
        minimum_width, minimum_height = args.require_texture_min_size
        for requirement in matched_texture_requirements:
            for image in requirement["matches"]:
                image["meets_minimum_size"] = (
                    image["width"] >= minimum_width and image["height"] >= minimum_height
                )
    result["ok"] = (
        not result["errors"]
        and vertex_count > 0
        and result["material_load_ok"]
        and source_lod_error is None
        and bool(source_lods)
    )
    if not result["ok"]:
        result["status"] = "imported_with_errors"
    return result


def main() -> int:
    args = parse_args()
    report: dict[str, Any] = {
        "blender": {
            "version": ".".join(str(part) for part in bpy.app.version),
            "version_string": bpy.app.version_string,
            "binary": bpy.app.binary_path,
        },
        "isolation": {
            "factory_startup_expected": True,
            "user_config": os.environ.get("BLENDER_USER_CONFIG"),
            "user_scripts": os.environ.get("BLENDER_USER_SCRIPTS"),
            "python_dont_write_bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE"),
        },
        "addons": {},
        "checks": {},
        "errors": [],
    }
    mesh_module = None
    asset_module = None

    try:
        mesh_module = load_addon(args.mesh_addon)
        finish_addon_enable(mesh_module)
        report["addons"]["mesh_editor"] = {
            "ok": True,
            "version": module_version(mesh_module),
            "path": str(Path(args.mesh_addon).expanduser().resolve()),
            "module": mesh_module.__name__,
        }
    except Exception as exc:
        report["addons"]["mesh_editor"] = {"ok": False, "error": str(exc)}
        report["errors"].append("mesh_editor: %s" % exc)

    if args.chain_addon:
        try:
            chain_module = load_addon(args.chain_addon)
            finish_addon_enable(chain_module)
            report["addons"]["chain_editor"] = {
                "ok": True,
                "version": module_version(chain_module),
                "path": str(Path(args.chain_addon).expanduser().resolve()),
                "module": chain_module.__name__,
            }
        except Exception as exc:
            report["addons"]["chain_editor"] = {"ok": False, "error": str(exc)}
            report["errors"].append("chain_editor: %s" % exc)

    try:
        asset_module = load_addon(args.asset_addon)
        finish_addon_enable(asset_module)
        report["addons"]["asset_library"] = {
            "ok": True,
            "version": module_version(asset_module),
            "path": str(Path(args.asset_addon).expanduser().resolve()),
            "module": asset_module.__name__,
        }
    except Exception as exc:
        report["addons"]["asset_library"] = {"ok": False, "error": str(exc)}
        report["errors"].append("asset_library: %s" % exc)

    if mesh_module is not None:
        try:
            maps = read_editor_maps(mesh_module)
            report["checks"]["editor_maps"] = maps
            report["checks"]["mesh_chunk_games"] = [
                item["identifier"]
                for item in enum_from_rna(mesh_module.ChunkPathPropertyGroup, "gameName")[0]
            ]
            mdf_panel = getattr(getattr(bpy.context, "scene", None), "re_mdf_toolpanel", None)
            if mdf_panel is not None:
                games, source = enum_from_rna(type(mdf_panel), "activeGame")
                report["checks"]["mesh_active_games"] = {
                    "source": source,
                    "items": games,
                }
        except Exception as exc:
            report["errors"].append("editor_maps: %s" % exc)

    if asset_module is not None:
        try:
            owner = asset_module.WM_OT_CreateNewREAssetLibrary
            games, source = enum_from_rna(owner, "gameName")
            report["checks"]["asset_create_games"] = {
                "source": source,
                "items": games,
            }
        except Exception as exc:
            report["errors"].append("asset_enum: %s" % exc)

        try:
            asset_helpers = importlib.import_module(
                asset_module.__name__ + ".modules.asset.blender_re_asset"
            )
            mesh_pref_name = asset_helpers.findREMeshEditorAddon()
            report["checks"]["cross_addon"] = {
                "findREMeshEditorAddon": mesh_pref_name,
                "preference_modules": sorted(
                    bpy.context.preferences.addons.keys()
                ),
                "ok": mesh_pref_name is not None,
            }
        except Exception as exc:
            report["checks"]["cross_addon"] = {"ok": False, "error": str(exc)}
            report["errors"].append("cross_addon: %s" % exc)

    report["checks"]["operators"] = {
        "mesh_import": operator_exists("re_mesh", "importfile"),
        "mesh_export": operator_exists("re_mesh", "exportfile"),
        "chain_import": operator_exists("re_chain", "importfile"),
        "chain2_import": operator_exists("re_chain2", "importfile"),
        "asset_create_library": operator_exists("re_asset", "create_re_asset_library"),
    }
    if mesh_module is not None:
        report["checks"]["mesh_import_operator_rna_fields"] = operator_rna_fields(
            getattr(mesh_module, "ImportREMesh", None)
        )

    if args.list_path and asset_module is not None:
        try:
            report["checks"]["catalog_generation"] = generate_catalog(
                asset_module, args.list_path, args.game_name
            )
        except Exception as exc:
            report["checks"]["catalog_generation"] = {"ok": False, "error": str(exc)}
            report["errors"].append("catalog_generation: %s" % exc)
    else:
        report["checks"]["catalog_generation"] = {"status": "skipped"}

    if args.mesh and mesh_module is not None:
        try:
            report["checks"]["mesh_import"] = import_mesh(
                mesh_module, args, report["checks"]["editor_maps"]
            )
        except Exception as exc:
            report["checks"]["mesh_import"] = {
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            report["errors"].append("mesh_import: %s" % exc)
    else:
        report["checks"]["mesh_import"] = {"status": "skipped"}

    target = args.game_name.upper()
    asset_games = {
        item["identifier"]
        for item in report.get("checks", {}).get("asset_create_games", {}).get("items", [])
    }
    chunk_games = set(report.get("checks", {}).get("mesh_chunk_games", []))
    report["checks"]["target_game_name"] = {
        "target": target,
        "asset_enum_present": target in asset_games,
        "mesh_chunk_enum_present": target in chunk_games,
        "ok": target in asset_games and target in chunk_games,
    }

    strict_failures: list[str] = []
    if args.strict and not report["checks"]["target_game_name"]["ok"]:
        strict_failures.append("target game is absent from asset and mesh chunk enums")
    if args.strict and not report["checks"].get("cross_addon", {}).get("ok", False):
        strict_failures.append("RE Asset Library cannot resolve Mesh Editor preferences")
    mesh_result = report.get("checks", {}).get("mesh_import", {})
    if args.strict and args.mesh and not mesh_result.get("ok", False):
        if mesh_result.get("errors"):
            strict_failures.append("requested mesh import reported errors")
        elif mesh_result.get("vertex_count", 0) == 0:
            strict_failures.append("requested mesh import produced no geometry")
    if args.strict and args.mesh and args.require_armature:
        if mesh_result.get("armature_object_count", 0) == 0:
            strict_failures.append("requested mesh import produced no armature")
        if mesh_result.get("armature_bone_count", 0) == 0:
            strict_failures.append("requested mesh import produced no bones")
    if args.strict and args.mesh and args.require_weights:
        if mesh_result.get("vertex_group_count", 0) == 0:
            strict_failures.append("requested mesh import produced no vertex groups")
        if mesh_result.get("weighted_vertex_count", 0) == 0:
            strict_failures.append("requested mesh import produced no weighted vertices")
    if args.strict and args.mesh:
        lod_validation = mesh_result.get("lod_validation", {})
        if mesh_result.get("source_lod_error"):
            strict_failures.append("source LOD statistics could not be parsed")
        if not lod_validation.get("vertex_count_match", False):
            strict_failures.append("imported vertex count does not match requested source LOD mode")
        if not lod_validation.get("polygon_count_match", False):
            strict_failures.append("imported polygon count does not match requested source LOD mode")
    if args.strict and args.mesh and args.load_materials:
        if mesh_result.get("missing_texture_warnings"):
            strict_failures.append("requested material load has missing textures")
        if mesh_result.get("file_backed_image_count", 0) == 0:
            strict_failures.append("requested material load produced no file-backed images")
    if args.strict and args.mesh and args.require_texture_pattern:
        requirements = mesh_result.get("texture_requirements", {}).get("patterns", [])
        for requirement in requirements:
            matches = requirement.get("matches", [])
            if not matches:
                strict_failures.append(
                    "no file-backed image matched texture pattern %s"
                    % requirement.get("pattern", "")
                )
            elif args.require_texture_min_size and not any(
                item.get("meets_minimum_size", False) for item in matches
            ):
                strict_failures.append(
                    "no image matched texture pattern %s at the required minimum size"
                    % requirement.get("pattern", "")
                )
    if args.strict and args.mesh and args.require_texture_min_size and not args.require_texture_pattern:
        strict_failures.append(
            "--require-texture-min-size requires at least one --require-texture-pattern"
        )
    report["checks"]["strict_failures"] = strict_failures
    ok = not report["errors"] and not strict_failures
    report["ok"] = ok
    print(RESULT_MARKER)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
