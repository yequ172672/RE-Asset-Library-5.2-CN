"""GPU-only viewport previews for the RE Asset Library.

The browser resolves an asset into a resource record and calls
``request_preview(context, resource)``.  The CPU reader is the only module
that understands the mesh and texture files.  It exposes one fixed entry
point, ``modules.asset.preview_data.load_preview(resource)``.

The reader returns this plain mapping::

    {
        "vertices": float[N, 3],           # raw RE coordinates
        "normals": float[N, 3],            # raw RE coordinates
        "uvs": float[N, 2],
        "indices": int[M, 3],
        "lod_index": int,
        "lod_distance": float,
        "sections": [
            {"slot": 0, "first_index": 0, "num_faces": M},
        ],
        "materials": [
            {
                "name": "Body",
                "base_color": (1.0, 1.0, 1.0, 1.0),
                "base_color_texture": {
                    "rgba8": bytes,             # top-left row order
                    "width": 512,
                    "height": 512,
                    "path": "...",
                } | None,
            },
        ],
    }

``preview_data`` uses the raw RE coordinate basis.  The renderer applies the
same ``(x, -z, y)`` rotation as the established Mesh Editor import to both
positions and normals before centering. ``sections.first_index`` is an element offset into ``indices`` and
``num_faces`` is a triangle count. Texture bytes are uploaded directly with
``gpu.texture.from_bytes``.  This module creates no
Blender Mesh, Image, material, or other datablock.  Background threads only
read and normalize data; GPU creation, draw-handler changes, viewport framing,
and release are performed by Blender's main-thread timer or draw callback.
"""

from __future__ import annotations

import queue
import threading
import traceback
from collections.abc import Mapping

import bpy
import gpu
import numpy as np
from gpu.types import GPUBatch, GPUIndexBuf, GPUVertBuf, GPUVertFormat


_LOCK = threading.RLock()
_RESULT_QUEUE = queue.Queue()

_generation = 0
_stop_event = None
_worker = None
_pending_request = None
_poll_registered = False

_target_area = None
_target_window = None
_source_browser_area = None
_draw_handler = None
_draw_items = []
_gpu_resources = {}
_shader = None

_DEFAULT_COLOR = (0.66, 0.72, 0.78, 1.0)
_POLL_INTERVAL = 0.05
_PREVIEW_DISTANCE = 3.2

_status = {
    "state": "idle",
    "message": "",
    "error": "",
    "warnings": (),
    "generation": 0,
    "asset_id": None,
    "asset_name": "",
    "game_name": "",
    "lod_index": None,
    "lod_distance": 0.0,
    "vertices": 0,
    "triangles": 0,
    "materials": 0,
    "textured_materials": 0,
}


_VERTEX_SOURCE = """
void main() {
    surface_normal = normal;
    uv = texCoord;
    gl_Position = mvp * vec4(pos, 1.0);
}
"""

_FRAGMENT_SOURCE = """
void main() {
    vec3 n = normalize(surface_normal);
    if (!gl_FrontFacing) n = -n;
    vec3 light_direction = normalize(vec3(0.35, -0.45, 0.82));
    float diffuse = max(dot(n, light_direction), 0.0);
    float lighting = 0.26 + 0.74 * diffuse;
    vec4 sampled = has_texture != 0 ? texture(image, fract(uv)) : vec4(1.0);
    vec4 base = sampled * base_color;
    // Base-color alpha is not an opacity signal for RE's packed maps.  Keep
    // this first preview path opaque until MDF semantics are available.
    fragColor = vec4(base.rgb * lighting, 1.0);
}
"""


# ---------------------------------------------------------------------------
# Public lifecycle and status API


def request_preview(context, resource):
    """Start a cancellable preview request for one resolved asset.

    ``resource`` must expose ``mesh_path``, ``game_name``, ``chunk_paths``,
    ``asset_id`` and ``asset_name``.  The browser adapter calls this on the
    Blender main thread after it has resolved those values.
    """

    global _generation, _stop_event, _worker, _pending_request
    global _target_area, _target_window, _source_browser_area

    area, window = _resolve_target_area(context)
    values = _resource_values(resource)
    missing = [
        name
        for name in ("mesh_path", "game_name", "chunk_paths", "asset_id", "asset_name")
        if name not in values
    ]
    asset_id = values.get("asset_id")
    asset_name = values.get("asset_name", "")
    game_name = values.get("game_name", "")

    with _LOCK:
        _generation += 1
        generation = _generation
        previous_stop = _stop_event
        _stop_event = threading.Event()
        _pending_request = None
        _target_area = area
        _target_window = window
        source_area = getattr(context, "area", None)
        _source_browser_area = source_area if getattr(source_area, "type", None) == "FILE_BROWSER" else None
    if previous_stop is not None:
        previous_stop.set()

    # Browser operators run on Blender's main thread.  This call removes the
    # old handler before the new worker can publish a result.
    _clear_gpu_resources_main()

    if area is None:
        state = "error"
        message = "Preview needs an open 3D Viewport."
        error = "no_view_3d"
    elif missing:
        state = "error"
        message = "Preview resource is incomplete."
        error = "missing_resource_fields:" + ",".join(missing)
    else:
        state = "loading"
        message = "Loading preview..."
        error = ""

    with _LOCK:
        _status.update(
            state=state,
            message=message,
            error=error,
            warnings=(),
            generation=generation,
            asset_id=asset_id,
            asset_name=asset_name,
            game_name=game_name,
            lod_index=None,
            lod_distance=0.0,
            vertices=0,
            triangles=0,
            materials=0,
            textured_materials=0,
        )

    if area is None or missing:
        with _LOCK:
            _pending_request = None
        _tag_redraw()
        return get_status()

    stop_event = _stop_event
    with _LOCK:
        _pending_request = (generation, resource, stop_event)
        worker = _worker
        start_worker = worker is None or not worker.is_alive()
        if start_worker:
            worker = threading.Thread(
                target=_load_worker,
                name="REAssetPreview",
                daemon=True,
            )
            _worker = worker
    _ensure_poll_timer()
    if start_worker:
        worker.start()
    return get_status()


def clear_preview():
    """Cancel the current reader and remove all preview GPU resources."""

    global _generation, _stop_event, _worker, _pending_request
    global _target_area, _target_window, _source_browser_area
    with _LOCK:
        _generation += 1
        generation = _generation
        previous_stop = _stop_event
        old_area = _target_area
        _stop_event = None
        _pending_request = None
        if _worker is not None and not _worker.is_alive():
            _worker = None
        _target_area = None
        _target_window = None
        _source_browser_area = None
        _status.update(
            state="idle",
            message="",
            error="",
            warnings=(),
            generation=generation,
            asset_id=None,
            asset_name="",
            game_name="",
            lod_index=None,
            lod_distance=0.0,
            vertices=0,
            triangles=0,
            materials=0,
            textured_materials=0,
        )
    if previous_stop is not None:
        previous_stop.set()
    if _is_main_thread():
        _clear_gpu_resources_main(old_area)
    else:
        _schedule_main(lambda: _clear_if_current(generation, old_area))


def stop_preview():
    """Alias for adapters that stop a preview when their panel closes."""

    clear_preview()


def unregister():
    """Release preview state during add-on unload."""

    clear_preview()


def get_status():
    """Return a copy of the status snapshot suitable for a Blender panel."""

    with _LOCK:
        return dict(_status)


def is_active():
    """Return whether this module currently owns drawable preview batches."""

    with _LOCK:
        return _draw_handler is not None and bool(_draw_items)


def is_loading():
    """Return whether the single CPU preview worker is still decoding."""

    with _LOCK:
        return _worker is not None and _worker.is_alive()


def poll():
    """Drain pending results once; useful for focused lifecycle tests."""

    return _poll_main_thread()


# ---------------------------------------------------------------------------
# Background read and main-thread polling


def _load_worker():
    """Run at most one decoder at a time and always take the newest request."""

    global _worker, _pending_request
    try:
        from . import preview_data
    except Exception as exc:
        with _LOCK:
            request = _pending_request
            _pending_request = None
            if _worker is threading.current_thread():
                _worker = None
        if request is not None:
            generation = request[0]
            if _is_current_generation(generation):
                _RESULT_QUEUE.put(("error", generation, None, _error_text(exc)))
        return

    while True:
        with _LOCK:
            request = _pending_request
            _pending_request = None
            if request is None:
                if _worker is threading.current_thread():
                    _worker = None
                return

        generation, resource, stop_event = request
        try:
            loader_resource = resource
            if isinstance(resource, Mapping):
                loader_resource = dict(resource)
                loader_resource["_cancel_event"] = stop_event
            payload = preview_data.load_preview(loader_resource)
            if stop_event.is_set() or not _is_current_generation(generation):
                continue
            normalized = _normalize_payload(payload)
            if stop_event.is_set() or not _is_current_generation(generation):
                continue
            _RESULT_QUEUE.put(("ready", generation, normalized, None))
        except Exception as exc:
            if stop_event.is_set() or not _is_current_generation(generation):
                continue
            _RESULT_QUEUE.put(("error", generation, None, _error_text(exc)))


def _ensure_poll_timer():
    global _poll_registered
    with _LOCK:
        if _poll_registered:
            return
        _poll_registered = True
    register = getattr(getattr(getattr(bpy, "app", None), "timers", None), "register", None)
    if not callable(register):
        with _LOCK:
            _poll_registered = False
        return
    try:
        register(_poll_main_thread, first_interval=0.0)
    except Exception:
        with _LOCK:
            _poll_registered = False


def _poll_main_thread():
    global _poll_registered, _worker
    keep_running = False
    stop_timer = False
    try:
        if not _preview_context_valid():
            clear_preview()
        while True:
            try:
                kind, generation, payload, error = _RESULT_QUEUE.get_nowait()
            except queue.Empty:
                break
            if not _is_current_generation(generation):
                continue
            if kind == "ready":
                _create_gpu_preview_main(generation, payload)
            elif kind == "error":
                _set_error_main(generation, error)

        with _LOCK:
            worker = _worker
        if worker is not None and worker.is_alive():
            keep_running = True
        else:
            with _LOCK:
                if _worker is worker:
                    _worker = None
        # Keep observing the originating browser while a preview is visible.
        # Switching provider must clear it even if the viewport has not redrawn.
        keep_running = keep_running or _draw_handler is not None
    except Exception as exc:
        traceback.print_exc()
        with _LOCK:
            if _status["generation"] == _generation:
                _status.update(state="error", message="Preview failed.", error=_error_text(exc))
    finally:
        if not keep_running and _RESULT_QUEUE.empty():
            with _LOCK:
                _poll_registered = False
            stop_timer = True
    return None if stop_timer else _POLL_INTERVAL


def _set_error_main(generation, error):
    if not _is_current_generation(generation):
        return
    _clear_gpu_resources_main()
    with _LOCK:
        _status.update(state="error", message="Preview failed.", error=str(error))
    _tag_redraw()


# ---------------------------------------------------------------------------
# Fixed CPU payload normalization


def _normalize_payload(payload):
    if not isinstance(payload, Mapping):
        raise ValueError("Preview reader must return a mapping")
    for field in ("vertices", "indices", "sections", "materials", "lod_index"):
        if field not in payload:
            raise ValueError(f"Preview payload is missing '{field}'")

    vertices = np.asarray(payload["vertices"], dtype=np.float32)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) < 3:
        raise ValueError("Preview vertices must be an N x 3 array")
    if not np.isfinite(vertices).all():
        raise ValueError("Preview vertices contain non-finite values")
    vertices = _to_blender_space(vertices)

    indices = np.asarray(payload["indices"], dtype=np.int64)
    if indices.ndim != 2 or indices.shape[1] != 3 or len(indices) == 0:
        raise ValueError("Preview indices must be an M x 3 array")
    if (indices < 0).any() or (indices >= len(vertices)).any():
        raise ValueError("Preview indices are out of bounds")
    indices = np.ascontiguousarray(indices, dtype=np.int32)

    normals_value = payload.get("normals")
    if normals_value is None:
        normals = _compute_vertex_normals(vertices, indices)
    else:
        normals = np.asarray(normals_value, dtype=np.float32)
        if normals.shape != (len(vertices), 3):
            raise ValueError("Preview normals must match the vertex count")
        normals = _normalize_vectors(_to_blender_space(normals))

    uvs_value = payload.get("uvs")
    if uvs_value is None:
        uvs = np.zeros((len(vertices), 2), dtype=np.float32)
    else:
        uvs = np.asarray(uvs_value, dtype=np.float32)
        if uvs.shape != (len(vertices), 2):
            raise ValueError("Preview UVs must match the vertex count")
        uvs = np.ascontiguousarray(uvs)

    sections = _normalize_sections(payload["sections"], len(indices))
    materials = _normalize_materials(payload["materials"])
    display_vertices, center, scale = _normalize_vertices(vertices)
    return {
        "vertices": display_vertices,
        "normals": normals,
        "uvs": uvs,
        "indices": indices,
        "sections": sections,
        "materials": materials,
        "lod_index": int(payload["lod_index"]),
        "lod_distance": float(payload.get("lod_distance", 0.0)),
        "warnings": tuple(str(value) for value in payload.get("warnings", ())),
        "center": center,
        "scale": scale,
    }


def _normalize_sections(raw_sections, triangle_count):
    if not isinstance(raw_sections, (list, tuple)) or not raw_sections:
        raise ValueError("Preview sections must be a non-empty list")
    result = []
    total_indices = triangle_count * 3
    for section in raw_sections:
        if not isinstance(section, Mapping):
            raise ValueError("Preview sections must contain mappings")
        slot = int(section["slot"])
        first = int(section["first_index"])
        faces = int(section["num_faces"])
        if first < 0 or faces <= 0 or first % 3 or first + faces * 3 > total_indices:
            raise ValueError("Preview section range is invalid")
        result.append({"slot": slot, "first_index": first, "num_faces": faces})
    return result


def _normalize_materials(raw_materials):
    if not isinstance(raw_materials, (list, tuple)):
        raise ValueError("Preview materials must be a list")
    result = {}
    for slot, material in enumerate(raw_materials):
        if not isinstance(material, Mapping):
            raise ValueError("Preview materials must contain mappings")
        texture_value = material.get("base_color_texture")
        texture = None if texture_value is None else _normalize_texture(texture_value)
        color = _normalize_color(material.get("base_color"), bool(texture))
        result[slot] = {"texture": texture, "color": color}
    return result


def _normalize_texture(texture):
    if not isinstance(texture, Mapping):
        raise ValueError("Preview texture must be a mapping")
    width = int(texture["width"])
    height = int(texture["height"])
    if width <= 0 or height <= 0:
        raise ValueError("Preview texture dimensions must be positive")
    data = memoryview(texture["rgba8"]).tobytes()
    if len(data) != width * height * 4:
        raise ValueError("Preview texture byte length does not match dimensions")
    # preview_data returns decoded image bytes in conventional top-left row
    # order.  Blender's raw GPU upload path addresses row zero from the
    # opposite side, so flip exactly once before from_bytes().
    data = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 4)[::-1].copy().tobytes()
    pixel_format = "RGBA8"
    return {
        "data": data,
        "width": width,
        "height": height,
        "format": pixel_format,
        "srgb": True,
    }


def _normalize_color(value, has_texture):
    if value is None:
        return (1.0, 1.0, 1.0, 1.0) if has_texture else _DEFAULT_COLOR
    values = [float(component) for component in value]
    if len(values) not in (3, 4):
        raise ValueError("Preview material color must have three or four values")
    if len(values) == 3:
        values.append(1.0)
    if max(abs(component) for component in values) > 1.0:
        values = [component / 255.0 for component in values]
    return tuple(max(0.0, min(1.0, component)) for component in values)


def _compute_vertex_normals(vertices, indices):
    v0 = vertices[indices[:, 0]]
    v1 = vertices[indices[:, 1]]
    v2 = vertices[indices[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0)
    normals = np.zeros((len(vertices), 3), dtype=np.float32)
    np.add.at(normals, indices[:, 0], face_normals)
    np.add.at(normals, indices[:, 1], face_normals)
    np.add.at(normals, indices[:, 2], face_normals)
    return _normalize_vectors(normals)


def _normalize_vectors(values):
    lengths = np.linalg.norm(values, axis=1, keepdims=True)
    lengths[lengths < 1e-8] = 1.0
    values = values / lengths
    return np.ascontiguousarray(np.nan_to_num(values, nan=0.0), dtype=np.float32)


def _normalize_vertices(vertices):
    minimum = vertices.min(axis=0)
    maximum = vertices.max(axis=0)
    center = (minimum + maximum) * 0.5
    extent = float(np.max(maximum - minimum))
    scale = 2.0 / max(extent, 1e-6)
    normalized = np.ascontiguousarray((vertices - center) * scale, dtype=np.float32)
    return normalized, tuple(float(value) for value in center), scale


def _to_blender_space(values):
    """Apply the RE Mesh Editor's default rotate90 transform."""

    return np.ascontiguousarray(
        np.column_stack((values[:, 0], -values[:, 2], values[:, 1])),
        dtype=np.float32,
    )


# ---------------------------------------------------------------------------
# GPU creation, draw callback, and cleanup


def _create_gpu_preview_main(generation, payload):
    global _draw_handler, _draw_items, _gpu_resources, _shader
    if not _is_current_generation(generation):
        return
    if _target_area is None or getattr(_target_area, "type", None) != "VIEW_3D":
        _set_error_main(generation, "No VIEW_3D target is available.")
        return

    try:
        _clear_gpu_resources_main()
        shader = _create_shader()
        vertices = payload["vertices"]
        normals = payload["normals"]
        uvs = payload["uvs"]
        indices = payload["indices"]

        fmt = GPUVertFormat()
        fmt.attr_add(id="pos", comp_type="F32", len=3, fetch_mode="FLOAT")
        fmt.attr_add(id="normal", comp_type="F32", len=3, fetch_mode="FLOAT")
        fmt.attr_add(id="texCoord", comp_type="F32", len=2, fetch_mode="FLOAT")
        vbo = GPUVertBuf(fmt, len(vertices))
        vbo.attr_fill("pos", vertices)
        vbo.attr_fill("normal", normals)
        vbo.attr_fill("texCoord", uvs)

        draw_items = []
        ibos = []
        batches = []
        textures = []
        textured_count = 0
        texture_errors = []
        for section in payload["sections"]:
            slot = section["slot"]
            start = section["first_index"]
            end = start + section["num_faces"] * 3
            triangles = np.ascontiguousarray(indices.reshape(-1)[start:end].reshape(-1, 3), dtype=np.int32)
            ibo = GPUIndexBuf(type="TRIS", seq=triangles)
            batch = GPUBatch(type="TRIS", buf=vbo, elem=ibo)
            material = payload["materials"].get(slot, {"texture": None, "color": _DEFAULT_COLOR})
            texture_info = material["texture"]
            texture = None
            if texture_info is not None:
                try:
                    texture = _create_texture(texture_info, slot)
                except Exception as exc:
                    # Geometry remains useful if an optional base-color upload
                    # fails; the panel gets a warning through the status text.
                    texture = None
                    texture_errors.append(
                        f"Base color texture slot {slot} upload failed: {_error_text(exc)}"
                    )
            if texture is not None:
                textured_count += 1
                textures.append(texture)
            color = material["color"]
            draw_items.append(
                {
                    "slot": slot,
                    "batch": batch,
                    "texture": texture,
                    "color": color,
                    "transparent": False,
                }
            )
            ibos.append(ibo)
            batches.append(batch)

        if not draw_items:
            raise ValueError("Preview geometry has no drawable sections")

        _shader = shader
        _draw_items = draw_items
        _gpu_resources = {
            "vbo": vbo,
            "ibos": ibos,
            "batches": batches,
            "textures": textures,
            "shader": shader,
        }
        _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_callback, (), "WINDOW", "POST_VIEW"
        )
        _frame_target_viewport()
        with _LOCK:
            warnings = tuple(payload["warnings"]) + tuple(texture_errors)
            _status.update(
                state="ready",
                message=(
                    "Preview ready."
                    if not warnings
                    else f"Preview ready with {len(warnings)} warning(s)."
                ),
                error="",
                warnings=warnings,
                vertices=len(vertices),
                triangles=len(indices),
                materials=len(draw_items),
                textured_materials=textured_count,
                lod_index=payload["lod_index"],
                lod_distance=payload["lod_distance"],
            )
        _tag_redraw()
    except Exception as exc:
        traceback.print_exc()
        _clear_gpu_resources_main()
        _set_error_main(generation, _error_text(exc))


def _create_shader():
    types = gpu.types
    info = types.GPUShaderCreateInfo()
    interface = types.GPUStageInterfaceInfo("re_asset_preview_interface")
    interface.smooth("VEC3", "surface_normal")
    interface.smooth("VEC2", "uv")
    info.push_constant("MAT4", "mvp")
    info.push_constant("INT", "has_texture")
    info.push_constant("VEC4", "base_color")
    info.sampler(0, "FLOAT_2D", "image")
    info.vertex_in(0, "VEC3", "pos")
    info.vertex_in(1, "VEC3", "normal")
    info.vertex_in(2, "VEC2", "texCoord")
    info.vertex_out(interface)
    info.fragment_out(0, "VEC4", "fragColor")
    info.vertex_source(_VERTEX_SOURCE)
    info.fragment_source(_FRAGMENT_SOURCE)
    return gpu.shader.create_from_info(info)


def _create_texture(info, slot):
    kwargs = {
        "format": "SRGB8_A8" if info["srgb"] else "RGBA8",
        "name": f"REAssetPreview_BaseColor_{slot}",
    }
    if info["format"] == "BGRA8":
        kwargs["swizzle"] = "bgra"
    return gpu.texture.from_bytes(info["width"], info["height"], info["data"], **kwargs)


def _draw_callback():
    if not _draw_items or _shader is None:
        return
    # A WINDOW draw handler runs for every 3D View.  Restrict this preview to
    # the area captured when the browser action was invoked.
    if not _area_matches(getattr(bpy.context, "area", None)):
        return

    old_depth_test = None
    old_depth_mask = None
    old_blend = None
    try:
        old_depth_test = gpu.state.depth_test_get()
        old_depth_mask = gpu.state.depth_mask_get()
        blend_get = getattr(gpu.state, "blend_get", None)
        old_blend = blend_get() if callable(blend_get) else None
        gpu.state.depth_test_set("LESS_EQUAL")
        gpu.state.depth_mask_set(True)

        mvp = gpu.matrix.get_projection_matrix() @ gpu.matrix.get_model_view_matrix()
        _shader.bind()
        _shader.uniform_float("mvp", mvp)
        for item in sorted(_draw_items, key=lambda value: value["transparent"]):
            transparent = item["transparent"]
            gpu.state.blend_set("ALPHA" if transparent else "NONE")
            gpu.state.depth_mask_set(not transparent)
            texture = item["texture"]
            _shader.uniform_int("has_texture", 1 if texture is not None else 0)
            _shader.uniform_float("base_color", item["color"])
            if texture is not None:
                _shader.uniform_sampler("image", texture)
            item["batch"].draw(_shader)
    except Exception as exc:
        with _LOCK:
            _status.update(state="error", message="Preview draw failed.", error=_error_text(exc))
    finally:
        try:
            gpu.state.blend_set(old_blend if old_blend is not None else "NONE")
        except Exception:
            pass
        try:
            if old_depth_mask is not None:
                gpu.state.depth_mask_set(old_depth_mask)
        except Exception:
            pass
        try:
            if old_depth_test is not None:
                gpu.state.depth_test_set(old_depth_test)
        except Exception:
            pass


def _clear_gpu_resources_main(redraw_area=None):
    global _draw_handler, _draw_items, _gpu_resources, _shader
    handler = _draw_handler
    _draw_handler = None
    if handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handler, "WINDOW")
        except Exception:
            pass
    _draw_items = []
    _gpu_resources = {}
    _shader = None
    _tag_redraw(redraw_area)


def _clear_if_current(generation, redraw_area):
    with _LOCK:
        if generation != _generation:
            return
    _clear_gpu_resources_main(redraw_area)


def _frame_target_viewport():
    if _target_area is None:
        return
    try:
        from mathutils import Quaternion, Vector

        region_3d = _target_area.spaces.active.region_3d
        region_3d.view_location = Vector((0.0, 0.0, 0.0))
        region_3d.view_distance = _PREVIEW_DISTANCE
        region_3d.view_perspective = "ORTHO"
        component = 2**-0.5
        region_3d.view_rotation = Quaternion((component, component, 0.0, 0.0))
    except Exception:
        pass


def _tag_redraw(area=None):
    try:
        area = area or _target_area
        if area is None or area.type != "VIEW_3D":
            return
        area.tag_redraw()
    except Exception:
        pass


def _preview_context_valid():
    try:
        if _target_area is not None:
            if _target_area.type != "VIEW_3D":
                return False
            if _target_window is not None and not any(
                area == _target_area for area in _target_window.screen.areas
            ):
                return False
        if _source_browser_area is not None:
            if _source_browser_area.type != "FILE_BROWSER":
                return False
            space = _source_browser_area.spaces.active
            return space.browse_mode == "EXTENSIONS" and space.remote_asset_provider == "reengine"
        return True
    except (ReferenceError, RuntimeError, AttributeError):
        return False


def _area_matches(area):
    target = _target_area
    if area is None or target is None:
        return False
    if area is target:
        return True
    try:
        return area.as_pointer() == target.as_pointer()
    except (AttributeError, RuntimeError, TypeError):
        try:
            return area == target
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Resource/context helpers


def _resolve_target_area(context):
    context = context or getattr(bpy, "context", None)
    if context is None:
        return None, None
    area = getattr(context, "area", None)
    window = getattr(context, "window", None)
    if getattr(area, "type", None) == "VIEW_3D":
        return area, window
    screen = getattr(context, "screen", None) or getattr(window, "screen", None)
    for candidate in getattr(screen, "areas", ()):
        if getattr(candidate, "type", None) == "VIEW_3D":
            return candidate, window
    return None, None


def _resource_values(resource):
    if isinstance(resource, Mapping):
        return dict(resource)
    return {
        name: getattr(resource, name)
        for name in ("mesh_path", "game_name", "chunk_paths", "asset_id", "asset_name")
        if hasattr(resource, name)
    }


def _is_current_generation(generation):
    with _LOCK:
        return generation == _generation


def _is_main_thread():
    return threading.current_thread() is threading.main_thread()


def _schedule_main(callback):
    register = getattr(getattr(getattr(bpy, "app", None), "timers", None), "register", None)
    if callable(register):
        try:
            register(callback, first_interval=0.0)
            return
        except Exception:
            pass
    callback()


def _error_text(error):
    text = str(error).strip()
    return text or error.__class__.__name__
