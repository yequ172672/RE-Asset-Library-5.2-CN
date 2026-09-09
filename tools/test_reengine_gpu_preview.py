"""Focused pure-Python checks for the GPU preview boundary.

The test imports the renderer with tiny ``bpy``/``gpu`` stubs and exercises
the exact mapping emitted by ``preview_data._flatten_lod``.  It does not claim
to replace Blender 5.2 shader or pixel validation; that acceptance remains a
live Blender check.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def _install_blender_stubs() -> None:
    bpy = ModuleType("bpy")
    bpy.context = SimpleNamespace(area=None, screen=None, window=None)
    bpy.app = SimpleNamespace(timers=SimpleNamespace(register=lambda *args, **kwargs: None))
    bpy.types = SimpleNamespace(SpaceView3D=SimpleNamespace())

    gpu = ModuleType("gpu")
    gpu.types = ModuleType("gpu.types")
    gpu.types.GPUBatch = object
    gpu.types.GPUIndexBuf = object
    gpu.types.GPUVertBuf = object
    gpu.types.GPUVertFormat = object

    sys.modules.setdefault("bpy", bpy)
    sys.modules.setdefault("gpu", gpu)
    sys.modules.setdefault("gpu.types", gpu.types)


_install_blender_stubs()

SPEC = importlib.util.spec_from_file_location(
    "re_asset_gpu_preview_test", ROOT / "modules" / "asset" / "gpu_preview.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load gpu_preview.py")
renderer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = renderer
SPEC.loader.exec_module(renderer)

CPU_SPEC = importlib.util.spec_from_file_location(
    "re_asset_preview_data_gpu_contract_test",
    ROOT / "modules" / "asset" / "preview_data.py",
)
if CPU_SPEC is None or CPU_SPEC.loader is None:
    raise RuntimeError("Unable to load preview_data.py")
cpu_preview = importlib.util.module_from_spec(CPU_SPEC)
sys.modules[CPU_SPEC.name] = cpu_preview
CPU_SPEC.loader.exec_module(cpu_preview)


def synthetic_payload() -> dict:
    """Return ``_flatten_lod`` output with one synthetic base-color record."""

    submesh = SimpleNamespace(
        vertexPosList=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        normalList=[(0.0, 0.0, 1.0)] * 3,
        uvList=[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
        faceList=[(0, 1, 2)],
        materialIndex=0,
        isReusedMesh=False,
        linkedSubMesh=None,
    )
    selected_lod = SimpleNamespace(
        visconGroupList=[SimpleNamespace(subMeshList=[submesh])],
        lodDistance=2.0,
    )
    mesh = SimpleNamespace(mainMeshLODList=[selected_lod], materialNameList=["Body"])
    result = cpu_preview._flatten_lod(mesh, 2, selected_lod)
    result.update(
        {
        "asset_id": "asset:test",
        "asset_name": "Test",
        "game_name": "OWOTS",
        "mesh_path": "<fixture>",
        "materials": [
            {
                "name": "Body",
                "base_color": (1.0, 0.8, 0.6, 1.0),
                "base_color_texture": {
                    "width": 2,
                    "height": 2,
                    "rgba8": bytes(
                        (
                            255,
                            0,
                            0,
                            255,
                            0,
                            255,
                            0,
                            255,
                            0,
                            0,
                            255,
                            255,
                            255,
                            255,
                            255,
                            255,
                        )
                    ),
                    "path": "<fixture>",
                },
            }
        ],
        }
    )
    return result


def test_renderer_consumes_preview_data_schema() -> None:
    normalized = renderer._normalize_payload(synthetic_payload())
    assert normalized["vertices"].shape == (3, 3)
    assert normalized["indices"].shape == (1, 3)
    assert normalized["lod_index"] == 2
    assert normalized["sections"] == [{"slot": 0, "first_index": 0, "num_faces": 1}]
    # Raw RE +Z maps to Blender -Y, matching Mesh Editor rotate90 import.
    assert tuple(normalized["normals"][0]) == (0.0, -1.0, 0.0)
    assert normalized["materials"][0]["texture"]["data"][8:12] == bytes((255, 0, 0, 255))


def test_shader_wraps_after_uv_interpolation() -> None:
    assert "uv = texCoord;" in renderer._VERTEX_SOURCE
    assert "texture(image, fract(uv))" in renderer._FRAGMENT_SOURCE
    assert "uv = fract(texCoord)" not in renderer._VERTEX_SOURCE


def test_no_viewport_reports_status_without_starting_worker() -> None:
    resource = {
        "mesh_path": "<fixture>",
        "game_name": "OWOTS",
        "chunk_paths": [],
        "asset_id": "asset:test",
        "asset_name": "Test",
    }
    result = renderer.request_preview(SimpleNamespace(area=None, screen=None, window=None), resource)
    assert result["state"] == "error"
    assert result["error"] == "no_view_3d"
    assert renderer._worker is None
    assert renderer.is_loading() is False
    renderer.clear_preview()


def test_stale_generation_is_discarded_before_gpu_creation() -> None:
    renderer._generation = 20
    renderer._RESULT_QUEUE.put(("ready", 19, renderer._normalize_payload(synthetic_payload()), None))
    renderer._poll_main_thread()
    assert renderer._draw_items == []


def test_leaving_provider_cancels_preview() -> None:
    renderer._source_browser_area = SimpleNamespace(
        type="FILE_BROWSER",
        spaces=SimpleNamespace(active=SimpleNamespace(browse_mode="EXTENSIONS", remote_asset_provider="ng4tool")),
    )
    renderer._status["state"] = "loading"
    renderer._poll_main_thread()
    assert renderer.get_status()["state"] == "idle"
    assert renderer._source_browser_area is None


def test_worker_keeps_only_newest_pending_asset() -> None:
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def decode(resource):
        calls.append(resource["asset_id"])
        if resource["asset_id"] == "first":
            entered.set()
            assert release.wait(3)
        return synthetic_payload()

    package = ModuleType("gpu_worker_fixture")
    package.preview_data = SimpleNamespace(load_preview=decode)
    area = SimpleNamespace(type="VIEW_3D", tag_redraw=lambda: None)
    context = SimpleNamespace(area=area, window=None, screen=SimpleNamespace(areas=[area]))
    resource = dict(mesh_path="fixture", game_name="OWOTS", chunk_paths=[], asset_name="fixture")
    with mock.patch.dict(sys.modules, {"gpu_worker_fixture": package}), \
         mock.patch.object(renderer, "__package__", "gpu_worker_fixture"):
        renderer.request_preview(context, dict(resource, asset_id="first"))
        worker = renderer._worker
        try:
            assert entered.wait(2)
            renderer.request_preview(context, dict(resource, asset_id="discarded"))
            renderer.request_preview(context, dict(resource, asset_id="latest"))
            assert renderer._worker is worker
        finally:
            release.set()
            worker.join(3)
        assert not worker.is_alive()
        assert calls == ["first", "latest"]
        renderer.clear_preview()
        renderer._poll_main_thread()
        assert not renderer.is_loading()


def test_geometry_is_published_before_texture_completion():
    renderer.clear_preview()
    while not renderer._RESULT_QUEUE.empty(): renderer._RESULT_QUEUE.get_nowait()
    package = ModuleType('progressive_preview_fixture')
    package.__path__ = []
    observed = []
    def load(resource):
        payload = synthetic_payload()
        resource['_on_geometry'](dict(payload, materials=[]))
        observed.append(renderer._RESULT_QUEUE.qsize())
        return payload
    package.preview_data = SimpleNamespace(load_preview=load)
    renderer._pending_request = (renderer._generation, {}, threading.Event())
    with mock.patch.dict(sys.modules, {'progressive_preview_fixture': package}), \
         mock.patch.object(renderer, '__package__', 'progressive_preview_fixture'):
        renderer._load_worker()
    assert observed == [1]
    assert [renderer._RESULT_QUEUE.get_nowait()[0] for _ in range(2)] == ['geometry', 'ready']


def test_shared_material_texture_is_normalized_once():
    payload = synthetic_payload()
    payload['materials'].append(dict(payload['materials'][0]))
    normalized = renderer._normalize_payload(payload)
    assert normalized['materials'][0]['texture'] is normalized['materials'][1]['texture']


def main() -> None:
    tests = (
        test_renderer_consumes_preview_data_schema,
        test_shader_wraps_after_uv_interpolation,
        test_no_viewport_reports_status_without_starting_worker,
        test_stale_generation_is_discarded_before_gpu_creation,
        test_leaving_provider_cancels_preview,
        test_worker_keeps_only_newest_pending_asset,
        test_geometry_is_published_before_texture_completion,
        test_shared_material_texture_is_normalized_once,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} GPU preview contract tests passed")


if __name__ == "__main__":
    main()
