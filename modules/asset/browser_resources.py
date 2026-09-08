"""Catalog and extraction helpers for the RE Engine extension browser.

The extension browser reads a virtual tree over HTTP.  The HTTP handler must
remain independent of Blender's RNA state, so catalog discovery and tree
construction live in this module as filesystem-only functions.  Resolving an
asset is deliberately a separate operation: it runs from a Blender operator
on the main thread and may consult Mesh Editor preferences or the PAK cache.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .catalog_paths import category_for_resource_path, normalize_resource_path


PROTOCOL_VERSION = 1
BROWSER_ROOT = "/Assets"
_CATALOG_RE = re.compile(r"^REAssetCatalog_(?P<game>.+)\.tsv$", re.IGNORECASE)
_GAME_INFO_RE = re.compile(r"^GameInfo_(?P<game>.+)\.json$", re.IGNORECASE)


class BrowserResourceError(RuntimeError):
    """Base exception used for user-facing resource resolution failures."""


class MissingCatalogError(BrowserResourceError):
    """Raised when an asset-library root has no usable game catalogs."""


class MissingAssetError(BrowserResourceError, FileNotFoundError):
    """Raised when a catalog asset cannot be found or extracted."""


def normalize_browser_path(path: str | None) -> str:
    """Return a safe absolute virtual path used by the tree protocol."""

    value = str(path or BROWSER_ROOT).replace("\\", "/")
    if not value.startswith("/"):
        value = "/" + value
    parts: list[str] = []
    for part in value.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            # The browser has no parent traversal semantics in its protocol.
            # Treat an unsafe request as the root instead of exposing a path
            # outside the virtual tree.
            return BROWSER_ROOT
        parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def _safe_catalog_resource_path(value: object) -> str:
    """Normalize a catalog resource path and reject traversal/absolute paths."""

    raw = str(value or "").replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        return ""
    if any(part == ".." for part in raw.split("/")):
        return ""
    return normalize_resource_path(raw)


def _safe_component(value: object, fallback: str = "Unknown") -> str:
    result = str(value or fallback).replace("/", "_").replace("\\", "_").strip()
    return result or fallback


def _valid_protocol_field(value: object, maximum_bytes: int) -> bool:
    text = str(value)
    return "\x00" not in text and len(text.encode("utf-8")) <= maximum_bytes


def _absolute(path: str | os.PathLike[str]) -> str:
    return os.path.abspath(os.path.expandvars(os.path.expanduser(os.fspath(path))))


def _read_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _game_files(library_dir: str) -> tuple[str, str, str] | None:
    """Return ``(game_name, catalog_path, game_info_path)`` for a library dir."""

    try:
        entries = sorted(os.scandir(library_dir), key=lambda entry: entry.name.lower())
    except OSError:
        return None

    game_info_path = ""
    game_name = ""
    for entry in entries:
        if not entry.is_file():
            continue
        match = _GAME_INFO_RE.match(entry.name)
        if not match:
            continue
        candidate = _absolute(entry.path)
        info = _read_json(candidate)
        game_name = str(info.get("GameName", "")).strip() if info else ""
        game_info_path = candidate
        if game_name:
            break
        game_name = match.group("game")

    catalog_path = ""
    for entry in entries:
        if not entry.is_file():
            continue
        match = _CATALOG_RE.match(entry.name)
        if not match:
            continue
        catalog_game = match.group("game")
        if not game_name:
            game_name = catalog_game
        if catalog_game.casefold() == game_name.casefold():
            catalog_path = _absolute(entry.path)
            break
        if not catalog_path:
            catalog_path = _absolute(entry.path)

    if not game_name or not catalog_path:
        return None
    if not game_info_path:
        expected = os.path.join(library_dir, f"GameInfo_{game_name}.json")
        game_info_path = _absolute(expected) if os.path.isfile(expected) else ""
    return game_name, catalog_path, game_info_path


def _library_dirs(asset_library_root: str) -> Iterable[tuple[str, str, str, str]]:
    """Yield ``(game_name, library_dir, catalog, game_info)`` deterministically."""

    root = _absolute(asset_library_root)
    if not os.path.isdir(root):
        return

    # Normal installations keep one catalog in each game directory.  Direct
    # root catalogs are accepted too, which is useful for small test libraries
    # and preserves compatibility with older manually-created libraries.
    candidates: list[str] = []
    try:
        entries = sorted(os.scandir(root), key=lambda entry: entry.name.casefold())
    except OSError:
        return
    for entry in entries:
        if entry.is_dir():
            candidates.append(entry.path)
    if any(entry.is_file() and _CATALOG_RE.match(entry.name) for entry in entries):
        candidates.append(root)

    for library_dir in candidates:
        found = _game_files(library_dir)
        if found is None:
            continue
        game_name, catalog_path, game_info_path = found
        yield game_name, _absolute(library_dir), catalog_path, game_info_path


def _catalog_rows(catalog_path: str) -> Iterable[dict[str, Any]]:
    try:
        handle = open(catalog_path, "r", encoding="utf-8", newline="")
    except OSError:
        return
    with handle:
        reader = csv.reader(handle, delimiter="\t", quotechar='"')
        try:
            next(reader)
        except StopIteration:
            return
        for row_number, row in enumerate(reader, start=2):
            if len(row) < 6:
                continue
            asset_path = _safe_catalog_resource_path(row[0])
            if not asset_path:
                continue
            display_name = str(row[1] or "").strip() or asset_path.rsplit("/", 1)[-1]
            category = _safe_catalog_resource_path(row[2])
            if not category:
                category = category_for_resource_path(asset_path)
            extension = os.path.splitext(asset_path.rsplit("/", 1)[-1])[1].lstrip(".").upper()
            yield {
                "row_number": row_number,
                "asset_path": asset_path,
                "asset_name": display_name,
                "category": category,
                "tags": str(row[3] or ""),
                "platform_extension": str(row[4] or "").strip(),
                "language_extension": str(row[5] or "").strip(),
                "asset_type": extension or "UNKNOWN",
            }


def asset_id_for(
    game_name: str,
    asset_path: str,
    platform_extension: str = "",
    language_extension: str = "",
) -> str:
    """Build a deterministic, opaque-enough ID for one catalog row."""

    parts = [str(game_name).strip(), _safe_catalog_resource_path(asset_path)]
    parts.extend((str(platform_extension or "").strip(), str(language_extension or "").strip()))
    # Keep the ID human-readable for diagnostics while preserving the full
    # relative path used by the catalog.  The Extension Browser treats it as
    # opaque and forwards it unchanged to the action operators.
    candidate = "asset:" + ":".join(parts)
    if len(candidate.encode("utf-8")) <= 1023:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:24]
    game = str(game_name).strip().encode("utf-8")[:200].decode("utf-8", "ignore")
    return f"asset:{game}:{digest}"


def iter_assets(asset_library_root: str) -> Iterable[dict[str, Any]]:
    """Yield catalog records used by both the HTTP tree and main-thread resolver."""

    for game_name, library_dir, catalog_path, game_info_path in _library_dirs(asset_library_root):
        for row in _catalog_rows(catalog_path):
            record = dict(row)
            record.update(
                {
                    "game_name": game_name,
                    "library_dir": library_dir,
                    "catalog_path": catalog_path,
                    "game_info_path": game_info_path,
                }
            )
            record["asset_id"] = asset_id_for(
                game_name,
                record["asset_path"],
                record["platform_extension"],
                record["language_extension"],
            )
            if not (
                _valid_protocol_field(record["game_name"], 255)
                and _valid_protocol_field(record["asset_name"], 255)
                and _valid_protocol_field(record["asset_id"], 1023)
                and _valid_protocol_field(record["asset_path"], 1023)
                and _valid_protocol_field(record["asset_type"], 63)
            ):
                continue
            yield record


def _node(path: str, name: str, node_id: str, node_type: str = "Folder") -> dict[str, Any]:
    return {
        "id": node_id,
        "path": path,
        "name": name,
        "type": node_type,
        "has_preview": False,
        "can_import": False,
    }


def _canonical_asset_path(record: Mapping[str, Any], game_path: str) -> str:
    """Build a source-resource path for a tree node, independent of display name."""

    relative = record["asset_path"]
    variant = ".".join(
        part
        for part in (record.get("platform_extension"), record.get("language_extension"))
        if part
    )
    if variant:
        relative += "." + variant
    return f"{game_path}/{relative}"


class CatalogIndex:
    """One immutable-ish catalog snapshot shared by tree and status requests.

    Parsing a large catalog is intentionally explicit.  ``refresh`` is called
    when the provider starts or the user presses Refresh; HTTP requests only
    read the resulting dictionaries and never touch Blender or reparse TSVs.
    """

    def __init__(self, asset_library_root: str = "") -> None:
        self._lock = __import__("threading").RLock()
        self.root = ""
        self._records: tuple[dict[str, Any], ...] = ()
        self._by_id: dict[str, dict[str, Any]] = {}
        self._children: dict[str, tuple[dict[str, Any], ...]] = {}
        self._summary = {"games": 0, "assets": 0}
        self.refresh(asset_library_root)

    def refresh(self, asset_library_root: str | None = None) -> None:
        if asset_library_root is not None:
            root = _absolute(asset_library_root) if asset_library_root else ""
        else:
            root = self.root
        raw_records = list(iter_assets(root)) if root else []
        records_list: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for raw_record in raw_records:
            record = raw_record
            base_id = str(record["asset_id"])
            if base_id in seen_ids:
                record = dict(record)
                record["asset_id"] = f"{base_id}#row{record['row_number']}"
            seen_ids.add(str(record["asset_id"]))
            records_list.append(record)
        records = tuple(records_list)
        by_id = {record["asset_id"]: record for record in records}
        child_nodes: dict[str, dict[str, dict[str, Any]]] = {BROWSER_ROOT: {}}
        games: set[str] = set()

        for record in records:
            games.add(str(record["game_name"]))
            game = _safe_component(record["game_name"])
            game_path = f"{BROWSER_ROOT}/{game}"
            child_nodes.setdefault(BROWSER_ROOT, {})[game_path] = _node(
                game_path, game, f"folder:game:{record['game_name']}"
            )
            child_nodes.setdefault(game_path, {})

            # Browse by the source resource directory.  Catalog category text
            # is retained in metadata but does not become a second, lossy tree
            # namespace.
            source_parts = [part for part in record["asset_path"].split("/") if part]
            parent_path = game_path
            for segment in source_parts[:-1]:
                safe_segment = _safe_component(segment)
                folder_path = f"{parent_path}/{safe_segment}"
                child_nodes.setdefault(parent_path, {})[folder_path] = _node(
                    folder_path,
                    safe_segment,
                    f"folder:resource:{record['game_name']}:{record['asset_path'].rsplit('/', 1)[0]}",
                )
                child_nodes.setdefault(folder_path, {})
                parent_path = folder_path

            asset_name = _safe_component(
                record["asset_name"], record["asset_path"].rsplit("/", 1)[-1]
            )
            asset_path = _canonical_asset_path(record, game_path)
            if not _valid_protocol_field(asset_path, 1023):
                continue
            asset_node = {
                "id": record["asset_id"],
                "asset_id": record["asset_id"],
                "path": asset_path,
                "name": asset_name,
                "type": record["asset_type"],
                "asset_type": record["asset_type"],
                "has_preview": record["asset_type"] == "MESH",
                "can_import": record["asset_type"] == "MESH",
            }
            # Platform/language suffixes make variant paths unique.  If a
            # malformed catalog repeats every identity field, preserve all
            # records with a deterministic ID suffix instead of overwriting.
            candidate_path = asset_path
            collision_index = 2
            while candidate_path in child_nodes[parent_path]:
                candidate_path = f"{asset_path} [{collision_index}]"
                collision_index += 1
            asset_node["path"] = candidate_path
            child_nodes[parent_path][candidate_path] = asset_node

        frozen_children: dict[str, tuple[dict[str, Any], ...]] = {}
        for parent, entries in child_nodes.items():
            values = list(entries.values())
            values.sort(
                key=lambda item: (
                    item["type"].casefold() != "FOLDER",
                    item["name"].casefold(),
                    item["path"],
                )
            )
            frozen_children[parent] = tuple(values)

        with self._lock:
            self.root = root
            self._records = records
            self._by_id = by_id
            self._children = frozen_children
            self._summary = {"games": len(games), "assets": len(records)}

    def find(self, asset_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._by_id.get(str(asset_id))

    def tree(self, path: str = BROWSER_ROOT) -> dict[str, Any]:
        requested_path = normalize_browser_path(path)
        with self._lock:
            children = self._children.get(requested_path, ())
            copied = [dict(item) for item in children]
        return {"protocol_version": PROTOCOL_VERSION, "path": requested_path, "children": copied}

    def summary(self) -> dict[str, int]:
        with self._lock:
            return dict(self._summary)


def find_asset(asset_library_root: str, asset_id: str) -> dict[str, Any] | None:
    """Find one catalog record by its stable provider ID."""

    return CatalogIndex(asset_library_root).find(asset_id)


def build_tree(asset_library_root: str, path: str = BROWSER_ROOT) -> dict[str, Any]:
    """Build one Extension Browser v1 response (convenience/test API)."""

    return CatalogIndex(asset_library_root).tree(path)


def catalog_summary(asset_library_root: str) -> dict[str, int]:
    """Return status values for callers that do not own a long-lived index."""

    return CatalogIndex(asset_library_root).summary()


def _get_bpy() -> Any:
    try:
        import bpy  # type: ignore
    except ImportError as error:  # pragma: no cover - exercised by Blender only
        raise BrowserResourceError("Blender is required to resolve an RE Engine asset") from error
    return bpy


def addon_preferences() -> Any:
    """Return this add-on's preferences without hard-coding its install folder."""

    bpy = _get_bpy()
    package_name = __package__.split(".")[0]
    addons = bpy.context.preferences.addons
    try:
        addon = addons.get(package_name)
    except AttributeError:
        addon = addons[package_name] if package_name in addons else None
    if addon is None:
        # Blender may load a compatibility copy under a different package
        # directory.  Match by the module suffix before failing.
        for key, candidate in getattr(addons, "items", lambda: ())():
            if str(key).casefold().startswith("re-asset-library"):
                addon = candidate
                break
    if addon is None:
        raise BrowserResourceError(f"RE Asset Library preferences are unavailable for {package_name}")
    return addon.preferences


def asset_library_root(preferences: Any | None = None) -> str:
    """Resolve the configured asset-library directory on Blender's main thread."""

    if preferences is None:
        preferences = addon_preferences()
    value = getattr(preferences, "assetLibraryPath", "")
    if not value:
        return ""
    bpy = _get_bpy()
    try:
        value = bpy.path.abspath(value)
    except (AttributeError, TypeError):
        pass
    return _absolute(value)


def _extract_info(library_dir: str, game_name: str) -> dict[str, Any]:
    path = os.path.join(library_dir, f"ExtractInfo_{game_name}.json")
    info = _read_json(path)
    if info is None:
        raise MissingAssetError(
            f"Missing ExtractInfo_{game_name}.json in {library_dir}; set game extract paths first"
        )
    return info


def _versioned_name(record: Mapping[str, Any], game_info: Mapping[str, Any], platform: str) -> str:
    extension = str(record["asset_type"]).upper()
    version = str(game_info.get("fileVersionDict", {}).get(f"{extension}_VERSION", "999"))
    result = f"{record['asset_path']}.{version}"
    platform_extension = str(record.get("platform_extension", ""))
    if platform_extension:
        result += "." + platform_extension.replace("STM", platform)
    language_extension = str(record.get("language_extension", ""))
    if language_extension:
        result += "." + language_extension
    return result.replace("/", os.sep).replace("\\", os.sep)


def _chunk_paths(game_name: str) -> list[str]:
    # Importing this module only on the main thread is intentional: it imports
    # bpy and reads the Mesh Editor's chunk-path preference collection.
    from .blender_re_asset import getChunkPathList

    return [_absolute(path) for path in getChunkPathList(game_name)]


class _AssetProxy(dict):
    """Small mapping/object bridge accepted by the existing extractor/importer."""

    def __init__(self, record: Mapping[str, Any]) -> None:
        super().__init__()
        self.name = str(record["asset_name"])
        self.update(
            {
                "~GAME": record["game_name"],
                "assetType": record["asset_type"],
                "assetPath": record["asset_path"],
                "platExt": record.get("platform_extension", ""),
                "langExt": record.get("language_extension", ""),
            }
        )


def resolve_asset(
    asset_id: str,
    force_extract: bool = False,
    *,
    asset_library_root_path: str | None = None,
    preferences: Any | None = None,
    catalog_index: CatalogIndex | None = None,
) -> dict[str, Any]:
    """Resolve a catalog ID to an absolute mesh/resource and extraction context.

    This function is intentionally main-thread-only.  It reads Blender
    preferences and can invoke the existing PAK extractor, which must not run
    from the extension-browser HTTP handler.
    """

    root = asset_library_root_path
    if root is None:
        root = asset_library_root(preferences)
    if not root or not os.path.isdir(root):
        raise MissingCatalogError(f"RE asset library path is missing or invalid: {root or '<empty>'}")

    normalized_root = _absolute(root)
    if catalog_index is not None and catalog_index.root == normalized_root:
        record = catalog_index.find(asset_id)
    else:
        record = find_asset(root, asset_id)
    if record is None:
        raise MissingAssetError(f"Asset ID is not present in the configured catalogs: {asset_id}")
    game_info = _read_json(record.get("game_info_path", ""))
    if game_info is None:
        raise MissingAssetError(f"Missing GameInfo for {record['game_name']} in {record['library_dir']}")

    extract_info_path = os.path.join(record["library_dir"], f"ExtractInfo_{record['game_name']}.json")
    pak_cache_path = os.path.join(record["library_dir"], f"PakCache_{record['game_name']}.pakcache")
    extract_info = _read_json(extract_info_path)
    platform = str((extract_info or {}).get("platform", "STM"))
    chunk_paths = _chunk_paths(record["game_name"])
    if not chunk_paths:
        raise MissingAssetError(f"No chunk paths for {record['game_name']} are configured")

    relative_name = _versioned_name(record, game_info, platform)

    def find_path() -> str | None:
        for chunk_path in chunk_paths:
            candidate = _absolute(os.path.join(chunk_path, relative_name))
            if os.path.isfile(candidate):
                return candidate
        return None

    mesh_path = find_path()
    if force_extract or mesh_path is None:
        # Preserve the established extractor/cache behavior.  It computes the
        # natives path and platform/language suffix from the proxy object.
        _extract_info(record["library_dir"], record["game_name"])
        from ..pak.re_pak_utils import extractFilesFromPakCache

        extractFilesFromPakCache(
            record["game_info_path"],
            [],
            extract_info_path,
            pak_cache_path,
            extractDependencies=True,
            blenderAssetObj=_AssetProxy(record),
        )
        mesh_path = find_path()

    if mesh_path is None:
        raise MissingAssetError(
            f"{record['asset_path']} was not found in configured chunk paths for {record['game_name']}"
        )

    metadata = dict(record)
    metadata.update(
        {
            "asset_path": record["asset_path"],
            "asset_type": record["asset_type"],
            "game_info_path": _absolute(record["game_info_path"]),
            "extract_info_path": _absolute(extract_info_path),
            "pak_cache_path": _absolute(pak_cache_path),
            "platform": platform,
            "game_info": game_info,
        }
    )
    return {
        "mesh_path": _absolute(mesh_path),
        "game_name": record["game_name"],
        "chunk_paths": chunk_paths,
        "asset_id": record["asset_id"],
        "asset_name": record["asset_name"],
        "metadata": metadata,
    }


__all__ = [
    "BROWSER_ROOT",
    "PROTOCOL_VERSION",
    "BrowserResourceError",
    "CatalogIndex",
    "MissingCatalogError",
    "MissingAssetError",
    "asset_id_for",
    "asset_library_root",
    "addon_preferences",
    "build_tree",
    "catalog_summary",
    "find_asset",
    "iter_assets",
    "normalize_browser_path",
    "resolve_asset",
]
