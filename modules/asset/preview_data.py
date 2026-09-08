"""CPU-side data extraction for the RE Asset Library viewport preview.

The preview path deliberately stops before Blender data-block creation.  The
active RE Mesh Editor add-on remains the source of truth for mesh, MDF and TEX
parsing; this module only converts its parsed objects into plain Python data
that a main-thread GPU adapter can upload.

``load_preview`` returns a dictionary with this stable shape::

    {
        "asset_id": str,
        "asset_name": str,
        "game_name": str,
        "mesh_path": str,
        "lod_index": int,
        "lod_distance": float,
        "vertices": [(x, y, z), ...],
        "normals": [(x, y, z), ...],
        "uvs": [(u, v), ...],
        "indices": [(i0, i1, i2), ...],
        "sections": [{"slot": int, "first_index": int,
                      "num_faces": int}, ...],
        "materials": [{"name": str, "base_color": (r, g, b, a),
                        "base_color_texture": {"width": int,
                            "height": int, "rgba8": bytes,
                            "path": str} | None}, ...],
        "bounds": {"min": (x, y, z), "max": (x, y, z)},
        "warnings": [str, ...],
    }

The selected source is LOD2, then LOD1, then LOD0.  Higher source LOD indices
are intentionally ignored.  Texture decoding currently handles the TEX
formats that the active Mesh Editor's bundled Texconv supports by converting
the selected TEX image to an in-memory CPU RGBA8 payload.  Normal, roughness,
AO, emissive, and other auxiliary material maps are not loaded here.
"""

from __future__ import annotations

import importlib
import math
import os
from pathlib import Path
import struct
import tempfile
from concurrent.futures import CancelledError
from typing import Any, Iterable, Mapping, Sequence


_DEFAULT_BASE_COLOR = (0.8, 0.8, 0.8, 1.0)

# These names mirror the active Mesh Editor's albedoTypeSet.  Keep the local
# fallback so a plain CPU test can exercise material selection without loading
# Blender or the editor's UI modules.
_BASE_COLOR_TYPES = (
    "ALBD",
    "ALBDmap",
    "BaseDielectricMap",
    "BaseDielectricMapBase",
    "BaseMap",
    "BaseAlphaMap",
    "BaseMetalMap",
    "BaseMetalMapArray",
    "BaseShiftMap",
    "BaseAnisoShiftMap",
    "BackMap",
    "BackMap_1",
    "FaceBaseMap",
    "Face_BaseDielectricMap",
    "CloudMap",
    "CloudMap_1",
    "Moon_Tex",
    "Sky_Top_Tex",
    "RTReflectionBaseMap",
)
_BASE_COLOR_PROPERTY_NAMES = (
    "BaseColor",
    "Base_Color",
    "DiffuseColor",
    "AlbedoColor",
    "ColorParam",
)

# The active editor owns the authoritative map.  These values are only used
# when its enum module cannot be imported (for example, in a pure CPU test).
class PreviewError(RuntimeError):
    """Raised when a preview cannot be prepared from the supplied resource."""


def _check_cancelled(resource: Mapping[str, Any]) -> None:
    event = resource.get("_cancel_event")
    if event is not None and event.is_set():
        raise CancelledError("Preview request was superseded or cleared")


def _as_module(module_or_name: Any) -> Any:
    if module_or_name is None:
        return None
    if isinstance(module_or_name, str):
        return importlib.import_module(module_or_name)
    return module_or_name


def resolve_active_mesh_module() -> Any:
    """Resolve the enabled RE Mesh Editor package on Blender's main thread.

    Call this from the operator/adapter and put the returned package in
    ``resource["_mesh_module"]`` before dispatching worker work.  The worker
    path intentionally has no ``bpy`` or preference lookup fallback.
    """

    try:
        import bpy  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised outside Blender
        raise PreviewError("active Mesh Editor resolution requires Blender") from exc
    for addon in bpy.context.preferences.addons:
        module_name = getattr(addon, "module", "")
        if "RE-Mesh-Editor" not in module_name:
            continue
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            raise PreviewError(
                f"Unable to import active RE Mesh Editor add-on {module_name!r}: {exc}"
            ) from exc
    raise PreviewError("RE Mesh Editor add-on is not enabled")


def _resolve_active_mesh_module(resource: Mapping[str, Any]) -> Any:
    module = _as_module(resource.get("_mesh_module"))
    if module is None:
        raise PreviewError(
            "preview worker resource is missing '_mesh_module'; resolve the active "
            "RE Mesh Editor package on Blender's main thread first"
        )
    return module


def _editor_module(mesh_module: Any, suffix: str) -> Any:
    return importlib.import_module(f"{mesh_module.__name__}.{suffix}")


def _parse_mesh(mesh_module: Any, mesh_path: str) -> Any:
    mesh_file = _editor_module(mesh_module, "modules.mesh.file_re_mesh")
    mesh_parse = _editor_module(mesh_module, "modules.mesh.re_mesh_parse")
    raw_mesh = mesh_file.readREMesh(mesh_path, lodTarget=None)
    parsed = mesh_parse.ParsedREMesh()
    parsed.ParseREMesh(
        raw_mesh,
        {
            "importAllLOD": True,
            "importShadowMesh": False,
            "importOcclusionMesh": False,
            "importBlendShapes": False,
        },
    )
    return parsed


def _safe_list(value: Any) -> list[Any]:
    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _vector(value: Any, count: int, default: Sequence[float]) -> tuple[float, ...]:
    try:
        values = list(value)
    except (TypeError, ValueError):
        values = []
    result = []
    for index in range(count):
        try:
            number = float(values[index])
        except (IndexError, TypeError, ValueError):
            number = float(default[index])
        if not math.isfinite(number):
            number = float(default[index])
        result.append(number)
    return tuple(result)


def _valid_triangle(face: Any, vertex_count: int) -> tuple[int, int, int] | None:
    try:
        values = list(face)
    except (TypeError, ValueError):
        return None
    if len(values) != 3:
        return None
    try:
        result = tuple(int(value) for value in values)
    except (TypeError, ValueError):
        return None
    if min(result) < 0 or max(result) >= vertex_count:
        return None
    return result


def _iter_lod_submeshes(lod: Any) -> Iterable[tuple[int, int, Any]]:
    for group_index, group in enumerate(_safe_list(getattr(lod, "visconGroupList", []))):
        for submesh_index, submesh in enumerate(_safe_list(getattr(group, "subMeshList", []))):
            yield group_index, submesh_index, submesh


def _geometry_source(submesh: Any) -> Any:
    """Follow parser reuse links when a repeated submesh has no own payload."""

    if not getattr(submesh, "isReusedMesh", False):
        return submesh
    linked = getattr(submesh, "linkedSubMesh", None)
    if linked is None:
        return submesh
    own_positions = _safe_list(getattr(submesh, "vertexPosList", []))
    own_faces = _safe_list(getattr(submesh, "faceList", []))
    linked_positions = _safe_list(getattr(linked, "vertexPosList", []))
    linked_faces = _safe_list(getattr(linked, "faceList", []))
    if not own_positions or not own_faces:
        return linked
    if not linked_positions or not linked_faces:
        return submesh
    return submesh


def _choose_lod(parsed_mesh: Any) -> tuple[int, Any]:
    lods = _safe_list(getattr(parsed_mesh, "mainMeshLODList", []))
    for index in range(min(2, len(lods) - 1), -1, -1):
        lod = lods[index]
        has_geometry = False
        for _, _, submesh in _iter_lod_submeshes(lod):
            source = _geometry_source(submesh)
            positions = _safe_list(getattr(source, "vertexPosList", []))
            faces = _safe_list(getattr(source, "faceList", []))
            if positions and any(_valid_triangle(face, len(positions)) for face in faces):
                has_geometry = True
                break
        if has_geometry:
            return index, lod
    raise PreviewError("RE mesh has no non-empty main mesh LOD in the supported range 0..2")


def _flatten_lod(parsed_mesh: Any, lod_index: int, lod: Any) -> dict[str, Any]:
    material_names = [str(name) for name in _safe_list(getattr(parsed_mesh, "materialNameList", []))]
    if not material_names:
        material_names = ["Default"]

    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    indices: list[tuple[int, int, int]] = []
    submeshes: list[dict[str, Any]] = []
    warnings: list[str] = []

    for group_index, submesh_index, submesh in _iter_lod_submeshes(lod):
        source = _geometry_source(submesh)
        raw_positions = _safe_list(getattr(source, "vertexPosList", []))
        raw_faces = _safe_list(getattr(source, "faceList", []))
        if not raw_positions or not raw_faces:
            continue

        vertex_start = len(positions)
        index_start = len(indices)
        raw_normals = _safe_list(getattr(source, "normalList", []))
        raw_uvs = _safe_list(getattr(source, "uvList", []))
        for vertex_index, position in enumerate(raw_positions):
            positions.append(_vector(position, 3, (0.0, 0.0, 0.0)))
            normal = raw_normals[vertex_index] if vertex_index < len(raw_normals) else (0.0, 0.0, 1.0)
            uv = raw_uvs[vertex_index] if vertex_index < len(raw_uvs) else (0.0, 0.0)
            normals.append(_vector(normal, 3, (0.0, 0.0, 1.0)))
            uvs.append(_vector(uv, 2, (0.0, 0.0)))

        local_face_count = 0
        for face in raw_faces:
            triangle = _valid_triangle(face, len(raw_positions))
            if triangle is None:
                warnings.append(
                    f"Skipped invalid triangle in LOD{lod_index} group {group_index} submesh {submesh_index}"
                )
                continue
            indices.append(tuple(index + vertex_start for index in triangle))
            local_face_count += 1

        if local_face_count == 0:
            del positions[vertex_start:]
            del normals[vertex_start:]
            del uvs[vertex_start:]
            continue

        material_index = int(getattr(submesh, "materialIndex", 0) or 0)
        if material_index < 0 or material_index >= len(material_names):
            warnings.append(
                f"Material index {material_index} is outside the mesh material list; using Default"
            )
            material_index = 0
        submeshes.append(
            {
                "name": f"LOD{lod_index}_Group{group_index}_Sub{submesh_index}",
                "group_index": group_index,
                "submesh_index": submesh_index,
                "material_index": material_index,
                "material_name": material_names[material_index],
                "vertex_start": vertex_start,
                "vertex_count": len(raw_positions),
                "index_start": index_start,
                "index_count": local_face_count,
            }
        )

    if not positions or not indices:
        raise PreviewError(f"Selected LOD{lod_index} contains no drawable triangles")

    minimum = tuple(min(position[axis] for position in positions) for axis in range(3))
    maximum = tuple(max(position[axis] for position in positions) for axis in range(3))
    sections = [
        {
            "slot": row["material_index"],
            "first_index": row["index_start"] * 3,
            "num_faces": row["index_count"],
        }
        for row in submeshes
    ]
    return {
        "lod_index": lod_index,
        "lod_distance": float(getattr(lod, "lodDistance", 0.0) or 0.0),
        "vertices": positions,
        "normals": normals,
        "uvs": uvs,
        "indices": indices,
        "sections": sections,
        "material_names": material_names,
        "bounds": {"min": minimum, "max": maximum},
        "warnings": warnings,
    }


def _property_values(material: Any) -> Mapping[str, Any]:
    properties = getattr(material, "propertyList", None)
    if properties is not None:
        result: dict[str, Any] = {}
        for prop in _safe_list(properties):
            name = getattr(prop, "propName", None)
            if name:
                result[str(name)] = getattr(prop, "propValue", None)
        return result
    for key in ("properties", "property_dict", "props"):
        value = getattr(material, key, None)
        if isinstance(value, Mapping):
            return value
    if isinstance(material, Mapping):
        value = material.get("properties")
        if isinstance(value, Mapping):
            return value
    return {}


def _material_color(material: Any) -> tuple[float, float, float, float]:
    properties = _property_values(material)
    for name in _BASE_COLOR_PROPERTY_NAMES:
        if name not in properties:
            continue
        value = properties[name]
        if isinstance(value, Mapping):
            value = value.get("value", value.get("values", value))
        try:
            values = list(value)
        except (TypeError, ValueError):
            continue
        if len(values) < 3:
            continue
        values = values[:4]
        if len(values) == 3:
            values.append(1.0)
        result = []
        for component in values:
            try:
                number = float(component)
            except (TypeError, ValueError):
                number = 1.0
            result.append(max(0.0, min(1.0, number)))
        return tuple(result)  # type: ignore[return-value]
    return _DEFAULT_BASE_COLOR


def _has_material_color(material: Any) -> bool:
    properties = _property_values(material)
    return any(name in properties for name in _BASE_COLOR_PROPERTY_NAMES)


def _material_name(material: Any) -> str:
    if isinstance(material, Mapping):
        return str(material.get("materialName", material.get("name", "")))
    return str(getattr(material, "materialName", getattr(material, "name", "")))


def _texture_bindings(material: Any) -> list[Any]:
    if isinstance(material, Mapping):
        value = material.get("textureList", material.get("textures", []))
    else:
        value = getattr(material, "textureList", getattr(material, "textures", []))
    return _safe_list(value)


def _texture_type(binding: Any) -> str:
    if isinstance(binding, Mapping):
        return str(binding.get("textureType", binding.get("type", "")))
    return str(getattr(binding, "textureType", getattr(binding, "type", "")))


def _texture_reference(binding: Any) -> str:
    if isinstance(binding, Mapping):
        return str(binding.get("texturePath", binding.get("path", "")))
    return str(getattr(binding, "texturePath", getattr(binding, "path", "")))


def _choose_base_color_binding(material: Any) -> Any:
    bindings = _texture_bindings(material)
    for texture_type in _BASE_COLOR_TYPES:
        for binding in bindings:
            if _texture_type(binding) == texture_type:
                return binding
    # Match the editor's useful fallback: if the MDF does not label an albedo
    # binding, a texture path containing _ALB is still a base color candidate.
    for binding in bindings:
        reference = _texture_reference(binding).lower()
        if "_alb" in reference or "_albd" in reference:
            return binding
    return None


def _find_mdf_path(mesh_path: str, game_name: str, chunk_paths: Sequence[str], mesh_module: Any) -> str | None:
    explicit = None
    try:
        helper = _editor_module(mesh_module, "modules.mdf.blender_re_mesh_mdf")
        finder = getattr(helper, "findMDFPathFromMeshPath", None)
        if finder is not None:
            explicit = finder(mesh_path, game_name)
    except Exception:
        explicit = None
    if explicit and os.path.isfile(explicit):
        return os.path.abspath(explicit)

    # Search the same resource-relative location in each configured chunk.
    mesh = Path(mesh_path)
    mesh_name = mesh.name
    if ".mesh" not in mesh_name:
        return None
    root_name, version = mesh_name.split(".mesh", 1)
    mdf_version = None
    try:
        mdf_file = _editor_module(mesh_module, "modules.mdf.file_re_mdf")
        get_mdf_version = getattr(mdf_file, "getMDFVersionToGameName", None)
        if callable(get_mdf_version):
            value = get_mdf_version(game_name)
            if value not in (None, -1):
                mdf_version = int(value)
    except Exception:
        pass
    candidate_names = []
    if mdf_version is not None:
        suffix = f".mdf2.{mdf_version}"
        candidate_names.extend((f"{root_name}{suffix}", f"{root_name}_Mat{suffix}", f"{root_name}_v00{suffix}"))
    candidate_names.extend((f"{root_name}.mdf2.*", f"{root_name}_Mat.mdf2.*", f"{root_name}_v00.mdf2.*"))

    relative = _resource_relative_path(mesh_path)
    relative_parent = str(Path(relative).parent) if relative else ""
    for chunk in chunk_paths:
        chunk_path = Path(chunk)
        parent = _join_chunk_resource(chunk_path, relative_parent)
        for candidate in candidate_names:
            if "*" in candidate:
                matches = sorted(parent.glob(candidate))
                if matches:
                    return str(matches[0].resolve())
            else:
                path = parent / candidate
                if path.is_file():
                    return str(path.resolve())
    return None


def _resource_relative_path(path: str) -> str:
    parts = Path(path).parts
    for index, part in enumerate(parts):
        if part.lower() == "natives" and index + 2 < len(parts):
            return str(Path(*parts[index + 2 :]))
    return Path(path).name


def _join_chunk_resource(chunk: Path, relative: str) -> Path:
    if not relative or relative == ".":
        return chunk
    lower = str(chunk).replace("\\", "/").lower().rstrip("/")
    # Preferences normally store .../natives/STM.  For a chunk root, also
    # account for the platform directory present in the source mesh path.
    if "/natives/" in lower:
        return chunk / Path(relative)
    return chunk / "natives" / "STM" / Path(relative)


def _texture_version(mesh_module: Any, game_name: str) -> Any:
    try:
        tex_file = _editor_module(mesh_module, "modules.tex.file_re_tex")
        get_version = getattr(tex_file, "getTexVersionFromGameName", None)
        if callable(get_version):
            value = get_version(game_name)
            if value not in (None, -1):
                return value
    except Exception:
        pass
    return None


def _find_texture_path(reference: str, chunk_paths: Sequence[str], game_name: str, mdf_version: Any, mesh_module: Any) -> str | None:
    if not reference:
        return None
    direct = Path(reference)
    if direct.is_file():
        return str(direct.resolve())
    base = reference.replace("@", "").replace(".tex", "").replace("/", os.sep).replace("\\", os.sep)
    version = _texture_version(mesh_module, game_name)
    if version is None:
        raise PreviewError(
            f"No TEX version mapping is available in the active Mesh Editor for {game_name!r}"
        )
    version_text = str(version)
    version_suffix = f".tex{version_text if version_text.startswith('.') else '.' + version_text}"
    for chunk in chunk_paths:
        root = Path(chunk)
        for relative in (Path("streaming") / base, Path(base)):
            pattern = str(root / (str(relative) + version_suffix + "*"))
            matches = sorted(Path(path) for path in _glob(pattern))
            if matches:
                return str(matches[0].resolve())
    return None


def _glob(pattern: str) -> list[str]:
    import glob

    return glob.glob(pattern)


def _load_mdf(mesh_module: Any, mdf_path: str) -> Any:
    mdf_file = _editor_module(mesh_module, "modules.mdf.file_re_mdf")
    return mdf_file.readMDF(mdf_path)


def _cache_root(resource: Mapping[str, Any]) -> Path:
    requested = resource.get("cache_dir") or resource.get("_cache_dir")
    if requested:
        root = Path(os.fspath(requested)).resolve()
    else:
        # Use a caller-owned cache when available.  The fallback is a private
        # temporary directory, never the installed add-on or a game directory.
        root = Path(tempfile.gettempdir()) / "re_asset_preview"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _decode_tga(path: str) -> tuple[int, int, bytes]:
    data = Path(path).read_bytes()
    if len(data) < 18:
        raise PreviewError(f"TGA file is truncated: {path}")
    header = struct.unpack_from("<BBBHHBHHHHBB", data, 0)
    id_length, color_map_type, image_type = header[:3]
    width, height, bits_per_pixel, descriptor = header[8], header[9], header[10], header[11]
    if color_map_type != 0 or image_type not in (2, 10):
        raise PreviewError(f"Unsupported TGA image type {image_type} in {path}")
    if bits_per_pixel not in (24, 32):
        raise PreviewError(f"Unsupported TGA pixel depth {bits_per_pixel} in {path}")
    offset = 18 + id_length
    pixel_size = bits_per_pixel // 8
    pixel_count = width * height
    pixels: list[bytes] = []
    if image_type == 2:
        end = offset + pixel_count * pixel_size
        if end > len(data):
            raise PreviewError(f"TGA pixel data is truncated: {path}")
        source = data[offset:end]
        pixels = [source[index : index + pixel_size] for index in range(0, len(source), pixel_size)]
    else:
        while len(pixels) < pixel_count:
            if offset >= len(data):
                raise PreviewError(f"TGA RLE data is truncated: {path}")
            packet = data[offset]
            offset += 1
            count = (packet & 0x7F) + 1
            if packet & 0x80:
                if offset + pixel_size > len(data):
                    raise PreviewError(f"TGA RLE pixel is truncated: {path}")
                pixel = data[offset : offset + pixel_size]
                offset += pixel_size
                pixels.extend([pixel] * count)
            else:
                end = offset + count * pixel_size
                if end > len(data):
                    raise PreviewError(f"TGA RLE packet is truncated: {path}")
                pixels.extend(data[index : index + pixel_size] for index in range(offset, end, pixel_size))
                offset = end
        pixels = pixels[:pixel_count]

    rgba = [bytes((pixel[2], pixel[1], pixel[0], pixel[3] if pixel_size == 4 else 255)) for pixel in pixels]
    rows = [rgba[row * width : (row + 1) * width] for row in range(height)]
    if not (descriptor & 0x20):
        rows.reverse()
    if descriptor & 0x10:
        rows = [list(reversed(row)) for row in rows]
    return width, height, b"".join(b"".join(row) for row in rows)


def _decode_rgba8(path: str, mesh_module: Any, cache_root: Path) -> tuple[int, int, bytes]:
    """Decode one source texture without creating a Blender Image datablock."""

    tex_utils = _editor_module(mesh_module, "modules.tex.re_tex_utils")
    dds_file_module = _editor_module(mesh_module, "modules.dds.file_dds")
    texconv_module = _editor_module(mesh_module, "modules.ddsconv.directx.texconv")
    cache_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="decode_", dir=str(cache_root)) as temp_dir:
        temp = Path(temp_dir)
        dds_path = temp / "preview.dds"
        if suffix == ".dds":
            dds_path.write_bytes(Path(path).read_bytes())
        else:
            tex_file = tex_utils.RE_TexFile()
            tex_file.read(path)
            dds = tex_utils.TexToDDS(tex_file.tex, 0)
            dds_file = dds_file_module.DDSFile()
            dds_file.dds = dds
            dds_file.write(str(dds_path))
        converter = texconv_module.Texconv()
        tga_path = converter.convert_to_tga(str(dds_path), out=str(temp), verbose=False)
        return _decode_tga(tga_path)


def _material_records(parsed_mesh: Any, mdf: Any, mesh_module: Any, resource: Mapping[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    material_names = [str(name) for name in _safe_list(getattr(parsed_mesh, "materialNameList", []))]
    if not material_names:
        material_names = ["Default"]
    source_materials = {}
    if mdf is not None:
        source_materials = {_material_name(material): material for material in _safe_list(getattr(mdf, "materialList", []))}
    chunk_paths = [str(path) for path in _safe_list(resource.get("chunk_paths", []))]
    game_name = str(resource.get("game_name", ""))
    mdf_version = getattr(mdf, "fileVersion", None) if mdf is not None else None
    cache_root = _cache_root(resource)
    records = []
    decoded_by_path: dict[str, dict[str, Any]] = {}
    for material_name in material_names:
        _check_cancelled(resource)
        source = source_materials.get(material_name)
        base_color = _material_color(source) if source is not None else _DEFAULT_BASE_COLOR
        texture_record = None
        if source is not None:
            binding = _choose_base_color_binding(source)
            if binding is not None:
                if not _has_material_color(source):
                    # The GPU adapter multiplies the sampled texture by this
                    # tint.  An absent MDF color parameter therefore means
                    # white, otherwise every textured asset is darkened.
                    base_color = (1.0, 1.0, 1.0, 1.0)
                reference = _texture_reference(binding)
                try:
                    texture_path = _find_texture_path(
                        reference, chunk_paths, game_name, mdf_version, mesh_module
                    )
                except Exception as exc:
                    warnings.append(f"Base color texture path resolution failed for {reference}: {exc}")
                    texture_path = None
                if texture_path is None:
                    warnings.append(f"Base color texture not found: {reference}")
                else:
                    try:
                        texture_record = decoded_by_path.get(texture_path)
                        if texture_record is None:
                            width, height, rgba8 = _decode_rgba8(texture_path, mesh_module, cache_root)
                            texture_record = {
                                "width": int(width),
                                "height": int(height),
                                "rgba8": bytes(rgba8),
                                "path": texture_path,
                            }
                            decoded_by_path[texture_path] = texture_record
                    except Exception as exc:
                        warnings.append(f"Base color texture decode failed for {texture_path}: {exc}")
        records.append(
            {
                "name": material_name,
                "base_color": base_color,
                "base_color_texture": texture_record,
            }
        )
    return records


def load_preview(resource: Mapping[str, Any]) -> dict[str, Any]:
    """Parse one asset into CPU preview data.

    ``resource`` must provide ``mesh_path``, ``game_name``, ``chunk_paths``,
    ``asset_id`` and ``asset_name``.  The active mesh package must be supplied
    as the private ``_mesh_module`` value by a Blender main-thread adapter.
    """

    if not isinstance(resource, Mapping):
        raise TypeError("preview resource must be a mapping")
    required = ("mesh_path", "game_name", "chunk_paths", "asset_id", "asset_name")
    missing = [key for key in required if key not in resource]
    if missing:
        raise ValueError(f"preview resource is missing required fields: {', '.join(missing)}")
    mesh_path = os.path.abspath(os.fspath(resource["mesh_path"]))
    if not os.path.isfile(mesh_path):
        raise PreviewError(f"Preview mesh does not exist: {mesh_path}")
    mesh_module = _resolve_active_mesh_module(resource)
    _check_cancelled(resource)
    parsed_mesh = _parse_mesh(mesh_module, mesh_path)
    _check_cancelled(resource)
    if bool(getattr(parsed_mesh, "isMPLY", False)):
        raise PreviewError(
            "MPLY meshlet previews are not supported yet; use full mesh import for this asset"
        )
    lod_index, lod = _choose_lod(parsed_mesh)
    flattened = _flatten_lod(parsed_mesh, lod_index, lod)
    warnings = list(flattened.pop("warnings", []))

    mdf = None
    mdf_path = resource.get("mdf_path") or resource.get("_mdf_path")
    if mdf_path is None:
        mdf_path = _find_mdf_path(
            mesh_path,
            str(resource["game_name"]),
            [str(path) for path in _safe_list(resource["chunk_paths"])],
            mesh_module,
        )
    if mdf_path:
        try:
            mdf = _load_mdf(mesh_module, str(mdf_path))
        except Exception as exc:
            warnings.append(f"MDF preview data unavailable for {mdf_path}: {exc}")
    else:
        warnings.append("MDF file not found; using default material color")

    materials = _material_records(parsed_mesh, mdf, mesh_module, resource, warnings)
    _check_cancelled(resource)
    flattened.update(
        {
            "asset_id": str(resource["asset_id"]),
            "asset_name": str(resource["asset_name"]),
            "game_name": str(resource["game_name"]),
            "mesh_path": mesh_path,
            "materials": materials,
            "warnings": warnings,
        }
    )
    return flattened


__all__ = [
    "PreviewError",
    "load_preview",
    "resolve_active_mesh_module",
    "_choose_lod",
    "_flatten_lod",
    "_choose_base_color_binding",
    "_decode_tga",
]
