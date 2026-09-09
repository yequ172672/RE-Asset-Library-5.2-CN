"""RE Engine adapter for Blender's custom Extension Browser API v1.

The adapter owns only the browser boundary.  Catalog data is served by a
small loopback HTTP server, while all operations that can touch Blender state
or extraction caches run in the registered operators on Blender's main thread.
"""

import importlib
import json
import os
import threading
import textwrap
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import bpy  # type: ignore
from bpy.props import StringProperty  # type: ignore
from bpy.types import Operator, Panel  # type: ignore

from . import browser_resources


API_VERSION = 1
PROVIDER_ID = "reengine"
PROVIDER_LABEL = "RE Engine"
PROVIDER_ROOT = browser_resources.BROWSER_ROOT
PROVIDER_TREE_URL = "/browser/tree?path={path}"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6170

_REQUIRED_METHODS = (
    "register_provider",
    "unregister_provider",
    "configure_provider",
    "refresh_provider",
    "is_provider_available",
    "register_icon",
    "clear_icons",
    "list_providers",
)

_bridge: Any | None = None
_bridge_loaded = False
_registered = False
_server: "_BrowserServer | None" = None
_selected_asset_id = ""
_pending_import_callback = None


def _translate(function_name: str, message: str, /, **values: Any) -> str:
    """Translate UI/report text when Blender's translation module is loaded."""

    try:
        translations = importlib.import_module("...translations", package=__package__)
        function = getattr(translations, function_name)
        return function(message, **values)
    except (ImportError, AttributeError, TypeError, RuntimeError, ValueError):
        try:
            return message.format(**values)
        except (KeyError, IndexError, ValueError):
            return message


def _load_bridge() -> Any | None:
    global _bridge, _bridge_loaded
    if _bridge_loaded:
        return _bridge
    _bridge_loaded = True
    try:
        _bridge = importlib.import_module("_remote_asset_browser")
    except ImportError:
        _bridge = None
    return _bridge


def is_available() -> bool:
    bridge = _load_bridge()
    return bool(
        bridge
        and getattr(bridge, "API_VERSION", None) == API_VERSION
        and all(callable(getattr(bridge, name, None)) for name in _REQUIRED_METHODS)
    )


class _BrowserServer(ThreadingHTTPServer):
    """Loopback catalog server with no Blender calls in request threads."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host: str, port: int, root: str):
        self.catalog_root = root
        self._root_lock = threading.RLock()
        self.catalog_index = browser_resources.CatalogIndex(root)
        super().__init__((host, int(port)), _BrowserRequestHandler)

    def set_catalog_root(self, root: str) -> None:
        with self._root_lock:
            if self.catalog_root != root:
                self.catalog_root = root
                self.catalog_index.refresh(root)

    def refresh_catalogs(self) -> None:
        with self._root_lock:
            self.catalog_index.refresh(self.catalog_root)

    def get_catalog_root(self) -> str:
        with self._root_lock:
            return self.catalog_root

    def get_tree(self, path: str) -> dict[str, Any]:
        with self._root_lock:
            return self.catalog_index.tree(path)

    def get_summary(self) -> dict[str, int]:
        with self._root_lock:
            return self.catalog_index.summary()


class _BrowserRequestHandler(BaseHTTPRequestHandler):
    """Serve only the JSON tree endpoint expected by Extension Browser v1."""

    server: _BrowserServer

    def log_message(self, _format: str, *_args: Any) -> None:
        # Blender's system console should not receive one line per tree read.
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path not in {"/browser/tree", "/tree"}:
            self._send_json(404, {"error": "unknown endpoint"})
            return
        query = parse_qs(parsed.query, keep_blank_values=True)
        path = query.get("path", [PROVIDER_ROOT])[0]
        try:
            payload = self.server.get_tree(path)
        except Exception as error:  # filesystem state may change between reads
            payload = {
                "protocol_version": browser_resources.PROTOCOL_VERSION,
                "path": browser_resources.normalize_browser_path(path),
                "children": [],
                "error": str(error),
            }
        self._send_json(200, payload)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass


def _start_server(root: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> _BrowserServer:
    """Start the catalog server, falling back to an ephemeral port on conflict."""

    global _server
    if _server is not None:
        _server.set_catalog_root(root)
        return _server
    try:
        server = _BrowserServer(host, int(port), root)
    except OSError:
        # FModel and NG4Tool historically use 6170 too.  Running both addons
        # should remain possible; the provider receives the actual endpoint.
        server = _BrowserServer(host, 0, root)
    thread = threading.Thread(target=server.serve_forever, name="REEngineBrowser", daemon=True)
    thread.start()
    server._serve_thread = thread  # type: ignore[attr-defined]
    _server = server
    return server


def _stop_server() -> None:
    global _server
    server = _server
    _server = None
    if server is None:
        return
    try:
        server.shutdown()
    finally:
        server.server_close()
        thread = getattr(server, "_serve_thread", None)
        if thread is not None:
            thread.join(timeout=2.0)


def _server_endpoint() -> tuple[str, int]:
    if _server is None:
        return DEFAULT_HOST, DEFAULT_PORT
    host, port = _server.server_address[:2]
    return str(host), int(port)


def _preferences() -> Any | None:
    if bpy is None:
        return None
    try:
        return browser_resources.addon_preferences()
    except Exception:
        return None


def _catalog_root_from_preferences() -> str:
    preferences = _preferences()
    if preferences is None:
        return ""
    try:
        return browser_resources.asset_library_root(preferences)
    except Exception:
        return ""


def register() -> bool:
    """Register the provider after action operators have been registered."""

    global _registered
    if _registered:
        return True
    bridge = _load_bridge()
    if not is_available():
        return False

    root = _catalog_root_from_preferences()
    provider_registered = False
    try:
        server = _start_server(root)
        host, port = _server_endpoint()
        bridge.register_provider(
            identifier=PROVIDER_ID,
            label=PROVIDER_LABEL,
            root=PROVIDER_ROOT,
            tree_url=PROVIDER_TREE_URL,
            host=host,
            port=port,
            select_operator="re_asset.select_asset",
            preview_operator="re_asset.preview_asset",
            import_operator="re_asset.import_asset",
        )
        provider_registered = True
        # Keep the lifecycle explicit: register, configure the actual bound
        # endpoint, then ask Blender to refresh its provider tree generation.
        bridge.configure_provider(PROVIDER_ID, host, port)
        bridge.refresh_provider(PROVIDER_ID)
        _registered = True
        return True
    except Exception as error:
        print(f"[RE Asset Library Browser] Failed to register provider: {error}")
        if provider_registered:
            try:
                bridge.unregister_provider(PROVIDER_ID)
            except Exception as cleanup_error:
                print(f"[RE Asset Library Browser] Failed to roll back provider: {cleanup_error}")
        _stop_server()
        return False


def unregister() -> None:
    """Detach the provider before operators and preview resources are removed."""

    global _registered, _pending_import_callback
    bridge = _load_bridge()
    if bridge is not None and _registered:
        try:
            bridge.unregister_provider(PROVIDER_ID)
        except Exception as error:
            print(f"[RE Asset Library Browser] Failed to unregister provider: {error}")
        finally:
            _registered = False
    if _pending_import_callback is not None:
        if bpy.app.timers.is_registered(_pending_import_callback):
            bpy.app.timers.unregister(_pending_import_callback)
        _pending_import_callback = None
    _stop_server()
    _clear_gpu_preview()
    _clear_preview_caches()


def is_registered() -> bool:
    return _registered


def configure_reengine(host: str = DEFAULT_HOST, port: int | None = None) -> bool:
    bridge = _load_bridge()
    if not is_available() or not _registered:
        return False
    if _server is not None:
        _server.set_catalog_root(_catalog_root_from_preferences())
    actual_host, actual_port = _server_endpoint()
    try:
        bridge.configure_provider(PROVIDER_ID, host or actual_host, int(port or actual_port))
        return True
    except Exception:
        return False


def refresh_reengine() -> bool:
    bridge = _load_bridge()
    if not is_available() or not _registered:
        return False
    _clear_gpu_preview()
    _clear_preview_caches()
    if _server is not None:
        _server.set_catalog_root(_catalog_root_from_preferences())
        _server.refresh_catalogs()
    try:
        bridge.refresh_provider(PROVIDER_ID)
        return True
    except Exception:
        return False


def is_reengine_available() -> bool:
    bridge = _load_bridge()
    if not is_available() or not _registered:
        return False
    try:
        return bool(bridge.is_provider_available(PROVIDER_ID))
    except Exception:
        return False


def _clear_preview_caches():
    for name in ('preview_data', 'preview_source'):
        module = importlib.import_module('.' + name, package=__package__)
        module.clear_cache()


def register_icon(type_name: str, png_path: str) -> bool:
    bridge = _load_bridge()
    if not is_available() or not _registered:
        return False
    try:
        bridge.register_icon(PROVIDER_ID, type_name, png_path)
        return True
    except Exception:
        return False


def clear_icons() -> bool:
    bridge = _load_bridge()
    if not is_available() or not _registered:
        return False
    try:
        bridge.clear_icons(PROVIDER_ID)
        return True
    except Exception:
        return False


def list_providers() -> tuple[str, ...]:
    bridge = _load_bridge()
    if not is_available():
        return ()
    try:
        return tuple(bridge.list_providers())
    except Exception:
        return ()


def _clear_gpu_preview() -> None:
    try:
        preview = importlib.import_module(".gpu_preview", package=__package__)
        clear = getattr(preview, "clear_preview", None)
        if callable(clear):
            clear()
    except (ImportError, RuntimeError, AttributeError):
        pass


def _gpu_preview_status() -> dict[str, Any]:
    try:
        preview = importlib.import_module(".gpu_preview", package=__package__)
        getter = getattr(preview, "get_status", None)
        if callable(getter):
            value = getter()
            if isinstance(value, dict):
                return value
    except (ImportError, RuntimeError, AttributeError):
        pass
    return {"state": "idle", "message": ""}


def _request_gpu_preview(context: Any, resource: dict[str, Any]) -> Any:
    if _pending_import_callback is not None:
        raise RuntimeError("A mesh import is waiting for preview decoding to stop")
    # Mesh Editor module discovery reads Blender preferences and therefore
    # belongs here, on the operator's main thread.  The preview worker then
    # receives an explicit module reference and performs only file parsing.
    preview_data = importlib.import_module(".preview_data", package=__package__)
    resolver = getattr(preview_data, "resolve_active_mesh_module", None)
    if not callable(resolver):
        raise RuntimeError("RE Engine preview data resolver is unavailable")
    prepared_resource = dict(resource)
    prepared_resource["_mesh_module"] = resolver()
    preview = importlib.import_module(".gpu_preview", package=__package__)
    request = getattr(preview, "request_preview", None)
    if not callable(request):
        raise RuntimeError("RE Engine GPU preview module is unavailable")
    status = request(context, prepared_resource)
    if status.get("state") == "error":
        raise RuntimeError(status.get("message") or status.get("error") or "Preview failed")
    return status


def _resolve(asset_id: str, *, force_extract: bool = False) -> dict[str, Any]:
    preferences = _preferences()
    index = _server.catalog_index if _server is not None else None
    return browser_resources.resolve_asset(
        asset_id,
        force_extract=force_extract,
        preferences=preferences,
        catalog_index=index,
    )


def _report(operator: Any, message: str, level: set[str] | None = None) -> None:
    if level is None:
        level = {"ERROR"}
    try:
        operator.report(level, _translate("tr_report", message))
    except (AttributeError, RuntimeError):
        print(f"RE Asset Library - {message}")


class REENGINE_OT_select_asset(Operator):
    """Record the selected ID without resolving or extracting anything."""

    bl_idname = "re_asset.select_asset"
    bl_label = "Select RE Engine Asset"
    bl_options = {"INTERNAL"}
    asset_id: StringProperty(name="Asset ID", options={"HIDDEN"})
    asset_name: StringProperty(name="Asset Name", options={"HIDDEN"})
    path: StringProperty(name="Path", options={"HIDDEN"})

    def execute(self, context: Any):
        global _selected_asset_id
        _selected_asset_id = self.asset_id
        return {"FINISHED"}


class REENGINE_OT_preview_asset(Operator):
    """Resolve and hand one mesh to the GPU-only preview path."""

    bl_idname = "re_asset.preview_asset"
    bl_label = "Preview RE Engine Asset"
    bl_options = {"INTERNAL"}
    asset_id: StringProperty(name="Asset ID", options={"HIDDEN"})
    asset_name: StringProperty(name="Asset Name", options={"HIDDEN"})
    path: StringProperty(name="Path", options={"HIDDEN"})

    def execute(self, context: Any):
        try:
            preferences = _preferences()
            resource = browser_resources.preview_resource(
                self.asset_id, preferences=preferences,
                catalog_index=_server.catalog_index if _server is not None else None,
            )
            if resource["metadata"].get("asset_type") != "MESH":
                raise browser_resources.BrowserResourceError("Only .mesh assets support GPU preview")
            _request_gpu_preview(context, resource)
            return {"FINISHED"}
        except Exception as error:
            _report(self, str(error))
            return {"CANCELLED"}


class REENGINE_OT_import_asset(Operator):
    """Route full imports through the corresponding editor operators."""

    bl_idname = "re_asset.import_asset"
    bl_label = "Import RE Engine Asset"
    bl_options = {"INTERNAL", "UNDO"}
    asset_id: StringProperty(name="Asset ID", options={"HIDDEN"})
    asset_name: StringProperty(name="Asset Name", options={"HIDDEN"})
    path: StringProperty(name="Path", options={"HIDDEN"})

    def execute(self, context: Any):
        try:
            preferences = _preferences()
            resource = _resolve(
                self.asset_id,
                force_extract=bool(getattr(preferences, "forceExtract", False)),
            )
            importer_name = {
                "MESH": "importREMeshAsset",
                "CHAIN2": "importREChain2Asset",
                "MDF2": "importREMDFAsset",
            }.get(resource["metadata"].get("asset_type"))
            if importer_name is None:
                raise browser_resources.BrowserResourceError("Unsupported asset type for full import")
            if preferences is None:
                raise browser_resources.BrowserResourceError("RE Asset Library preferences are unavailable")

            # Reuse editor-specific options and operator status handling.
            proxy = browser_resources._AssetProxy(resource["metadata"])
            import_module = importlib.import_module(".blender_re_asset", package=__package__)
            importer = getattr(import_module, importer_name)
            result = _import_after_preview(context, importer, proxy, resource["mesh_path"], preferences)
            if result is False:
                raise browser_resources.BrowserResourceError(
                    f"Import failed for {resource['asset_name']}"
                )
            _clear_gpu_preview()
            return {"FINISHED"}
        except Exception as error:
            _report(self, str(error))
            return {"CANCELLED"}


def _import_after_preview(context, importer, proxy, mesh_path, preferences):
    """Keep the original importer's Texconv unload away from a running decode.

    Polling uses a Blender timer so a slow native decode never blocks the UI.
    Only one import can wait, and unregister cancels its callback.
    """
    global _pending_import_callback
    if _pending_import_callback is not None:
        raise RuntimeError("An asset import is already waiting for preview decoding")
    preview = importlib.import_module(".gpu_preview", package=__package__)
    preview.clear_preview()
    if not preview.is_loading():
        return _run_mesh_import(context, importer, proxy, mesh_path, preferences)

    snapshot = SimpleNamespace(
        area=context.area, window=context.window, window_manager=context.window_manager,
    )

    def finish_import():
        global _pending_import_callback
        if not _registered:
            _pending_import_callback = None
            return None
        if preview.is_loading():
            return 0.1
        _pending_import_callback = None
        try:
            if _run_mesh_import(snapshot, importer, proxy, mesh_path, preferences) is False:
                raise RuntimeError(f"Import failed for {proxy.name}")
        except Exception as error:
            from .blender_re_asset import _reportImportFailure
            _reportImportFailure(str(error))
        return None

    _pending_import_callback = finish_import
    try:
        bpy.app.timers.register(finish_import, first_interval=0.1)
    except Exception:
        _pending_import_callback = None
        raise
    return True


def _run_mesh_import(
    context: Any,
    importer: Any,
    proxy: Any,
    mesh_path: str,
    preferences: Any,
) -> Any:
    """Use a 3D View override when the action originated in File Browser."""

    if bpy is None or getattr(getattr(context, "area", None), "type", "") != "FILE_BROWSER":
        return importer(proxy, mesh_path, preferences)
    window_manager = getattr(context, "window_manager", None)
    current_window = getattr(context, "window", None)
    windows = [current_window] if current_window is not None else list(getattr(window_manager, "windows", ()))
    for window in windows:
        screen = getattr(window, "screen", None)
        for area in getattr(screen, "areas", ()):
            if getattr(area, "type", "") != "VIEW_3D":
                continue
            region = next((item for item in getattr(area, "regions", ()) if item.type == "WINDOW"), None)
            if region is None:
                continue
            try:
                override = bpy.context.temp_override(
                    window=window, screen=screen, area=area, region=region
                )
            except (AttributeError, RuntimeError, TypeError):
                continue
            # Do not catch errors from the real importer here.  A mesh import
            # can have partially created datablocks; retrying it in another
            # area would duplicate or corrupt that work.
            with override:
                return importer(proxy, mesh_path, preferences)
    return importer(proxy, mesh_path, preferences)


class REENGINE_OT_refresh_browser(Operator):
    bl_idname = "re_asset.refresh_browser"
    bl_label = "Refresh RE Engine Browser"
    bl_description = "Reload RE Engine catalog files from the configured asset library path"
    bl_options = {"INTERNAL"}

    def execute(self, _context: Any):
        root = _catalog_root_from_preferences()
        if not root or not os.path.isdir(root):
            _report(self, "RE asset library path is missing or invalid")
            return {"CANCELLED"}
        if not refresh_reengine():
            _report(self, "RE Engine Extension Browser API is unavailable")
            return {"CANCELLED"}
        return {"FINISHED"}


class REENGINE_OT_clear_preview(Operator):
    bl_idname = "re_asset.clear_preview"
    bl_label = "Clear RE Engine Preview"
    bl_description = "Remove the GPU-only RE Engine preview"
    bl_options = {"INTERNAL"}

    def execute(self, _context: Any):
        _clear_gpu_preview()
        return {"FINISHED"}


class FILEBROWSER_PT_REEngineBrowser(Panel):
    """Provider-scoped controls shown only in the native File Browser."""

    bl_label = "RE Engine Browser"
    bl_idname = "FILEBROWSER_PT_re_engine_browser"
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "CHANNELS"
    bl_category = "RE Engine"

    @classmethod
    def poll(cls, context: Any) -> bool:
        space = getattr(context, "space_data", None)
        return bool(
            getattr(space, "type", None) == "FILE_BROWSER"
            and getattr(space, "browse_mode", None) == "EXTENSIONS"
            and getattr(space, "remote_asset_provider", None) == PROVIDER_ID
        )

    def draw(self, context: Any) -> None:
        layout = self.layout
        preferences = _preferences()
        layout.label(text=_translate("tr_iface", "RE Engine Asset Browser"))
        if preferences is not None:
            layout.prop(preferences, "assetLibraryPath")
            layout.prop(preferences, "showMeshImportOptions")
        root = _catalog_root_from_preferences()
        if not root:
            layout.label(text=_translate("tr_iface", "Asset library path is not configured"), icon="ERROR")
        elif not os.path.isdir(root):
            layout.label(text=_translate("tr_iface", "Asset library path is missing"), icon="ERROR")
        else:
            summary = _server.get_summary() if _server is not None else {"games": 0, "assets": 0}
            if summary["assets"] == 0:
                layout.label(text=_translate("tr_iface", "No RE asset catalogs found"), icon="ERROR")
            else:
                layout.label(
                    text=_translate(
                        "tr_iface",
                        "Catalogs: {games}  Assets: {assets}",
                        games=summary["games"],
                        assets=summary["assets"],
                    )
                )
        row = layout.row(align=True)
        row.operator(REENGINE_OT_refresh_browser.bl_idname, icon="FILE_REFRESH")
        row.operator(REENGINE_OT_clear_preview.bl_idname, icon="X")
        preview_status = _gpu_preview_status()
        if _pending_import_callback is not None:
            layout.label(text=_translate("tr_iface", "Waiting for preview decoding before import"))
        if preview_status.get("state") not in (None, "idle"):
            message = _translate('tr_iface', str(preview_status.get("message") or preview_status.get("state")))
            layout.label(
                text=_translate("tr_iface", "Preview: {message}", message=message),
                icon="VIEWZOOM",
            )
            if preview_status.get("state") == "ready":
                lod = preview_status.get("lod_index")
                if lod is not None:
                    layout.label(text=f"LOD{lod}")
                layout.label(text=_translate(
                    "tr_iface", "Vertices: {vertices}  Triangles: {triangles}",
                    vertices=preview_status.get("vertices", 0),
                    triangles=preview_status.get("triangles", 0),
                ))
            details = []
            if preview_status.get("error"):
                details.append(str(preview_status["error"]))
            details.extend(str(value) for value in preview_status.get("warnings", ())[:3])
            for detail in details:
                box = layout.box()
                for line in textwrap.wrap(detail, width=42):
                    box.label(text=line)


CLASSES = (
    REENGINE_OT_select_asset,
    REENGINE_OT_preview_asset,
    REENGINE_OT_import_asset,
    REENGINE_OT_refresh_browser,
    REENGINE_OT_clear_preview,
    FILEBROWSER_PT_REEngineBrowser,
)


__all__ = [
    "API_VERSION",
    "PROVIDER_ID",
    "CLASSES",
    "FILEBROWSER_PT_REEngineBrowser",
    "configure_reengine",
    "is_available",
    "is_registered",
    "is_reengine_available",
    "list_providers",
    "register",
    "register_icon",
    "refresh_reengine",
    "unregister",
]
