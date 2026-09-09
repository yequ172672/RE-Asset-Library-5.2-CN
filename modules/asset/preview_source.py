"""Read preview resources from PAKs without extracting game files.

Construct on the worker, with plain metadata captured by the browser. The
existing PAK cache supplies patch priority and the shared reader handles
compression/encryption; this module never creates or updates that cache.
"""
from collections import OrderedDict
from pathlib import Path
import threading

_INDEXES = OrderedDict()
_LOCK = threading.RLock()


def stamp(path):
    value = Path(path)
    try:
        info = value.stat()
        return (str(value.resolve()), info.st_size, info.st_mtime_ns)
    except OSError:
        return (str(value), None, None)


def clear_cache():
    with _LOCK:
        _INDEXES.clear()


class PreviewSource:
    def __init__(self, resource):
        from ..pak import re_pak_utils as pak
        self.pak = pak
        self.metadata = resource['metadata']
        self.chunks = tuple(resource.get('chunk_paths', ()))
        self.platform = self.metadata.get('platform', 'STM')
        self.read_paths = set()
        self.dependencies = {}
        self._tables = {}
        self.paths, self.lookup = (), {}
        cache = self.metadata['pak_cache_path']
        cache_stamp = stamp(cache)
        if cache_stamp[1] is not None:
            with _LOCK:
                entry = _INDEXES.get(cache_stamp)
                if entry is None:
                    entry = pak.readPakCache(cache)
                    _INDEXES[cache_stamp] = entry
                    while len(_INDEXES) > 4:
                        _INDEXES.popitem(last=False)
                else:
                    _INDEXES.move_to_end(cache_stamp)
            self.paths, self.lookup = entry
        self.signature = (cache_stamp, tuple(stamp(path) for path in self.paths),
                          stamp(self.metadata.get('game_info_path', '')), self.chunks)

    def canonical(self, path):
        path = str(path).replace('\\', '/')
        parts = path.split('/')
        for index, part in enumerate(parts):
            if part.lower() == 'natives':
                path = '/'.join(parts[index:])
                break
        else:
            path = f'natives/{self.platform}/{path.lstrip("/")}'
        if any(part in ('.', '..') for part in path.split('/')):
            raise ValueError('Invalid preview resource path')
        return path

    def entry(self, path):
        return self.lookup.get(self.pak.pathToPakHash(self.canonical(path)))

    def local_path(self, path):
        relative = '/'.join(self.canonical(path).split('/')[2:])
        for chunk in self.chunks:
            candidate = Path(chunk) / relative
            if candidate.is_file():
                return candidate
        return None

    def exists(self, path):
        return self.entry(path) is not None or self.local_path(path) is not None

    def identity(self, path):
        path = self.canonical(path)
        entry = self.entry(path)
        if entry is not None:
            result = (path.lower(), self.signature)
        else:
            local = self.local_path(path)
            result = stamp(local) if local else (path, None, None)
        self.dependencies[path] = result
        return result

    def read(self, path):
        path = self.canonical(path)
        self.identity(path)
        self.read_paths.add(path)
        entry = self.entry(path)
        if entry is None:
            local = self.local_path(path)
            if local:
                return local.read_bytes()
            raise FileNotFoundError(f'Preview resource is absent from PAK cache and chunk paths: {path}')
        archive = self.paths[entry['pakIndex']]
        table = None
        if entry.get('offsetType') == 1:
            if archive not in self._tables:
                self._tables[archive] = self.pak._readPakChunkTable(archive)
            table = self._tables[archive]
        with open(archive, 'rb') as stream:
            return self.pak.readPakEntryData(entry, stream, table)

    def find_mdf(self, mesh_path):
        versions = self.metadata['game_info'].get('fileVersionDict', {})
        found = self.pak.findPakMDFPathFromMeshPath(
            self.canonical(mesh_path), self.lookup, versions.get('MDF2_VERSION', 999),
            self.metadata['game_name'])
        if found:
            return found
        base = self.canonical(mesh_path).split('.mesh.')[0]
        for suffix in ('', '_Mat', '_v00'):
            candidate = f'{base}{suffix}.mdf2.{versions.get("MDF2_VERSION", 999)}'
            if self.exists(candidate):
                return candidate
        return None

    def find_texture(self, reference, version):
        base = reference.replace('@', '').replace('\\', '/').split('.tex')[0]
        base = '/'.join(self.canonical(base).split('/')[2:])
        for prefix in ('streaming/', ''):
            candidate = f'natives/{self.platform}/{prefix}{base}.tex.{str(version).lstrip(".")}'
            if self.exists(candidate):
                return candidate
        return None
