"""Read-only archive/fallback behavior independent of Blender and game files."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('preview_source_test', Path(__file__).parents[1] / 'modules/asset/preview_source.py')
source_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source_module)


class PreviewSourceTests(unittest.TestCase):
    def make_source(self, root, lookup):
        source = source_module.PreviewSource.__new__(source_module.PreviewSource)
        source.platform = 'STM'
        source.paths = [str(root / 'archive.pak')]
        source.lookup = lookup
        source.chunks = [str(root / 'natives/STM')]
        source.signature = ('test',)
        source.read_paths = set()
        source.dependencies = {}
        source._tables = {}
        source.pak = SimpleNamespace(pathToPakHash=lambda path: path.lower(),
                                     readPakEntryData=lambda entry, stream, table: stream.read(),
                                     _readPakChunkTable=mock.Mock(return_value=['chunk']))
        return source

    def test_archive_priority_read_only_and_shared_chunk_table(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'archive.pak').write_bytes(b'archive')
            local = root / 'natives/STM/art/model.mesh.1'
            local.parent.mkdir(parents=True)
            local.write_bytes(b'old-local')
            source = self.make_source(root, {'natives/stm/art/model.mesh.1': {'pakIndex': 0, 'offsetType': 1}})
            before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(source.read('art/model.mesh.1'), b'archive')
            self.assertEqual(source.read('art/model.mesh.1'), b'archive')
            source.pak._readPakChunkTable.assert_called_once()
            self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_local_fallback_identity_changes_when_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / 'natives/STM/art/model.mesh.1'
            local.parent.mkdir(parents=True)
            local.write_bytes(b'first')
            source = self.make_source(root, {})
            identity = source.identity('art/model.mesh.1')
            self.assertEqual(source.read('art/model.mesh.1'), b'first')
            local.write_bytes(b'second-larger')
            self.assertNotEqual(source.identity('art/model.mesh.1'), identity)
            with self.assertRaises(FileNotFoundError): source.read('art/absent.mesh.1')
            self.assertFalse((local.parent / 'absent.mesh.1').exists())
            with self.assertRaises(ValueError): source.read('../escape')


if __name__ == '__main__': unittest.main()
