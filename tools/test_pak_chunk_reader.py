"""Small regression tests for the v4.2 PAK chunk content table reader."""

import io
import ctypes
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The add-on normally provides zstandard through Blender.  The synthetic
# tests pass their decompressor explicitly, so a lightweight import stub keeps
# this test runnable in a plain Python environment too.
try:
    import zstandard as _zstandard
except ImportError:
    zstandard_stub = types.ModuleType("zstandard")

    bundled_zstd = REPO_ROOT.parent / "REE.PAK.Tool" / "REE.Unpacker" / "REE.Unpacker" / "Libs" / "libzstd.dll"
    if bundled_zstd.is_file():
        zstd_dll = ctypes.CDLL(str(bundled_zstd))
        zstd_dll.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
        zstd_dll.ZSTD_compressBound.restype = ctypes.c_size_t
        zstd_dll.ZSTD_compress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        zstd_dll.ZSTD_compress.restype = ctypes.c_size_t
        zstd_dll.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        zstd_dll.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
        zstd_dll.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
        zstd_dll.ZSTD_decompress.restype = ctypes.c_size_t
        zstd_dll.ZSTD_isError.argtypes = [ctypes.c_size_t]
        zstd_dll.ZSTD_isError.restype = ctypes.c_uint

        class BundledZstdCompressor:
            def compress(self, data):
                source = ctypes.create_string_buffer(data)
                capacity = zstd_dll.ZSTD_compressBound(len(data))
                target = ctypes.create_string_buffer(capacity)
                size = zstd_dll.ZSTD_compress(target, capacity, source, len(data), 3)
                if zstd_dll.ZSTD_isError(size):
                    raise RuntimeError("bundled zstd compression failed")
                return target.raw[:size]

        class BundledZstdDecompressor:
            def decompress(self, data):
                source = ctypes.create_string_buffer(data)
                size = zstd_dll.ZSTD_getFrameContentSize(source, len(data))
                if size >= (1 << 64) - 2:
                    size = max(len(data) * 100, 1024 * 1024)
                target = ctypes.create_string_buffer(size)
                result = zstd_dll.ZSTD_decompress(target, size, source, len(data))
                if zstd_dll.ZSTD_isError(result):
                    raise RuntimeError("bundled zstd decompression failed")
                return target.raw[:result]

        zstandard_stub.ZstdCompressor = BundledZstdCompressor
        zstandard_stub.ZstdDecompressor = BundledZstdDecompressor
    else:
        class ImportZstd:
            def decompress(self, data):
                raise AssertionError("synthetic tests should pass their decompressor")

        zstandard_stub.ZstdDecompressor = ImportZstd
    sys.modules["zstandard"] = zstandard_stub

sys.path.insert(0, str(REPO_ROOT))

from modules.pak.file_re_pak import PakChunkEntry, PakChunkTable, PakTOCEntry
from modules.pak.re_pak_utils import (
    PAK_CACHE_ENTRY_STRUCT,
    PAK_CACHE_VERSION,
    getStreamingPath,
    isStreamingFilePath,
    pathToPakHash,
    readPakCache,
    readPakEntryData,
)
from modules.pak.re_pak_extract_mp import pakExtractor


class SparseChunkStream:
    def __init__(self, chunks):
        self.chunks = chunks
        self.position = 0
        self.seeks = []

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.position = offset
        elif whence == io.SEEK_CUR:
            self.position += offset
        else:
            raise ValueError("SparseChunkStream only supports SEEK_SET/SEEK_CUR")
        self.seeks.append(self.position)

    def read(self, size=-1):
        data = self.chunks.get(self.position, b"")
        return data if size < 0 else data[:size]


class FakeZstd:
    def decompress(self, data):
        return {b"Z01": b"ZSTD", b"Z2": b"TAIL"}[data]


class PakChunkReaderTests(unittest.TestCase):
    def test_overflow_raw_zstd_and_final_trim(self):
        table = PakChunkTable()
        table.blockSize = 4
        table.entryList = []
        for offset, attributes in (
            (0, 4 << 10),
            (12, (3 << 10) | 1),
            (20, (2 << 10) | 2),
        ):
            chunk = PakChunkEntry()
            chunk.offset = offset
            chunk.attributes = attributes
            table.entryList.append(chunk)

        stream = SparseChunkStream({
            0: b"RAW!",
            0x100000000 + 12: b"Z01",
            0x200000000 + 20: b"Z2",
        })
        entry = PakTOCEntry()
        entry.offset = 0
        entry.compressedSize = 9
        entry.decompressedSize = 10
        entry.offsetType = 1

        result = readPakEntryData(entry, stream, table, FakeZstd())

        self.assertEqual(result, b"RAW!ZSTDTA")
        self.assertEqual(stream.seeks, [0, 0x100000000 + 12, 0x200000000 + 20])
        self.assertEqual(table.entryList[1].fileOffset, 0x100000000 + 12)
        self.assertEqual(table.entryList[2].fileOffset, 0x200000000 + 20)

    def test_regular_zstd_entry_still_uses_byte_offset(self):
        stream = SparseChunkStream({100: b"compressed"})
        entry = PakTOCEntry()
        entry.offset = 100
        entry.compressedSize = len(b"compressed")
        entry.decompressedSize = 4
        entry.compressionType = 2

        class DirectZstd:
            def decompress(self, data):
                self.seen = data
                return b"DATA"

        decompressor = DirectZstd()
        self.assertEqual(readPakEntryData(entry, stream, None, decompressor), b"DATA")
        self.assertEqual(stream.seeks, [100])
        self.assertEqual(decompressor.seen, b"compressed")

    def test_streaming_path_handles_platform_and_extension_case(self):
        base_path = "natives/stm/art/model/character/ch0/ch001_00/00/textures/top.TEX.251111100"
        streaming_path = "natives/stm/streaming/art/model/character/ch0/ch001_00/00/textures/top.TEX.251111100"
        lookup = {pathToPakHash(streaming_path): {}}
        self.assertTrue(isStreamingFilePath(base_path))
        self.assertEqual(getStreamingPath(base_path.replace("natives/stm", "natives/STM"), "STM", lookup), streaming_path.replace("natives/stm", "natives/STM"))

    @unittest.skipUnless("zstandard" in sys.modules and hasattr(sys.modules["zstandard"], "ZstdCompressor"), "requires zstandard")
    def test_real_zstd_chunk_frame_roundtrip(self):
        import zstandard

        source = (b"OWOTS zstd chunk regression " * 32) + b"end"
        compressed = zstandard.ZstdCompressor().compress(source)
        table = PakChunkTable()
        table.blockSize = 4096
        chunk = PakChunkEntry()
        chunk.offset = 0
        chunk.attributes = len(compressed) << 10
        table.entryList = [chunk]
        entry = PakTOCEntry()
        entry.offsetType = 1
        entry.compressedSize = len(compressed)
        entry.decompressedSize = len(source)

        result = readPakEntryData(
            entry,
            SparseChunkStream({0: compressed}),
            table,
            zstandard.ZstdDecompressor(),
        )
        self.assertEqual(result, source)

    def test_rejects_bad_compression_and_offset_types(self):
        stream = SparseChunkStream({0: b"DATA"})
        bad_compression = PakTOCEntry()
        bad_compression.compressedSize = 4
        bad_compression.decompressedSize = 4
        bad_compression.compressionType = 99
        with self.assertRaises(Exception):
            readPakEntryData(bad_compression, stream, None, FakeZstd())

        bad_offset_type = PakTOCEntry()
        bad_offset_type.offsetType = 2
        bad_offset_type.compressedSize = 4
        bad_offset_type.decompressedSize = 4
        with self.assertRaises(Exception):
            readPakEntryData(bad_offset_type, stream, None, FakeZstd())

        bad_decompressed_size = PakTOCEntry()
        bad_decompressed_size.compressedSize = 4
        bad_decompressed_size.decompressedSize = 5
        with self.assertRaises(Exception):
            readPakEntryData(bad_decompressed_size, stream, None, FakeZstd())

    def test_rejects_truncated_and_inconsistent_chunk_data(self):
        stream = SparseChunkStream({0: b"DAT"})
        entry = PakTOCEntry()
        entry.compressedSize = 4
        entry.decompressedSize = 4
        with self.assertRaises(Exception):
            readPakEntryData(entry, stream, None, FakeZstd())

        missing_table = PakTOCEntry()
        missing_table.offsetType = 1
        missing_table.compressedSize = 4
        missing_table.decompressedSize = 4
        with self.assertRaises(Exception):
            readPakEntryData(missing_table, stream, None, FakeZstd())

        table = PakChunkTable()
        table.blockSize = 4
        chunk = PakChunkEntry()
        chunk.offset = 0
        chunk.attributes = 4 << 10
        table.entryList = [chunk]
        too_large = PakTOCEntry()
        too_large.offsetType = 1
        too_large.compressedSize = 3
        too_large.decompressedSize = 4
        with self.assertRaises(Exception):
            readPakEntryData(too_large, SparseChunkStream({0: b"DATA"}), table, FakeZstd())

        short_output = PakChunkEntry()
        short_output.offset = 0
        short_output.attributes = 3 << 10
        table.entryList = [short_output]
        short_entry = PakTOCEntry()
        short_entry.offsetType = 1
        short_entry.compressedSize = 3
        short_entry.decompressedSize = 5
        with self.assertRaises(Exception):
            readPakEntryData(short_entry, SparseChunkStream({0: b"Z01"}), table, FakeZstd())

        compressed_chunk = PakTOCEntry()
        compressed_chunk.offsetType = 1
        compressed_chunk.compressionType = 2
        compressed_chunk.compressedSize = 3
        compressed_chunk.decompressedSize = 4
        with self.assertRaises(Exception):
            readPakEntryData(compressed_chunk, SparseChunkStream({0: b"Z01"}), table, FakeZstd())

        encrypted_chunk = PakTOCEntry()
        encrypted_chunk.offsetType = 1
        encrypted_chunk.encryptionType = 1
        encrypted_chunk.compressedSize = 3
        encrypted_chunk.decompressedSize = 4
        with self.assertRaises(Exception):
            readPakEntryData(encrypted_chunk, SparseChunkStream({0: b"Z01"}), table, FakeZstd())

    def test_cache_v3_roundtrip_preserves_chunk_metadata(self):
        with tempfile.TemporaryDirectory(prefix="pak_cache_v3_test_") as temp_dir:
            cache_path = os.path.join(temp_dir, "test.pakcache")
            pak_path = r"D:\game\re_chunk_000.pak"
            encoded_path = pak_path.encode("utf-16le")
            with open(cache_path, "wb") as stream:
                stream.write(struct.pack("<IIH", PAK_CACHE_VERSION, 1, 1))
                stream.write(struct.pack("<IQ", 0, 0))
                stream.write(struct.pack("<I", len(encoded_path)))
                stream.write(encoded_path)
                stream.write(PAK_CACHE_ENTRY_STRUCT.pack(
                    0x1122334455667788,
                    44369,
                    7215,
                    15816,
                    0,
                    0,
                    1,
                    0,
                ))

            paths, lookup = readPakCache(cache_path)
            self.assertEqual(paths, [pak_path])
            self.assertEqual(lookup[0x1122334455667788]["offset"], 44369)
            self.assertEqual(lookup[0x1122334455667788]["decompressedSize"], 15816)
            self.assertEqual(lookup[0x1122334455667788]["offsetType"], 1)

    def test_mp_worker_matches_shared_reader(self):
        with tempfile.TemporaryDirectory(prefix="pak_mp_test_") as temp_dir:
            pak_path = os.path.join(temp_dir, "plain.pak")
            with open(pak_path, "wb") as stream:
                stream.write(b"DATA")
            out_dir = os.path.join(temp_dir, "out")
            job = {
                "jobIndex": 0,
                "pakPath": pak_path,
                "outDir": out_dir,
                "fileEntries": [{
                    "offset": 0,
                    "compressedSize": 4,
                    "decompressedSize": 4,
                    "compressionType": 0,
                    "encryptionType": 0,
                    "offsetType": 0,
                    "filePath": "natives/stm/test.user.3",
                }],
            }
            self.assertTrue(pakExtractor(job))
            with open(os.path.join(out_dir, "natives", "stm", "test.user.3"), "rb") as stream:
                self.assertEqual(stream.read(), b"DATA")

    def test_mp_worker_failure_returns_nonzero(self):
        with tempfile.TemporaryDirectory(prefix="pak_mp_failure_test_") as temp_dir:
            pak_path = os.path.join(temp_dir, "plain.pak")
            with open(pak_path, "wb") as stream:
                stream.write(b"DATA")
            job = {
                "jobIndex": 0,
                "pakPath": pak_path,
                "outDir": os.path.join(temp_dir, "out"),
                "fileEntries": [{
                    "offset": 0,
                    "compressedSize": 4,
                    "decompressedSize": 4,
                    "compressionType": 99,
                    "encryptionType": 0,
                    "offsetType": 0,
                    "filePath": "natives/stm/bad.user.3",
                }],
            }
            code = (
                "import sys, types; "
                "z=types.ModuleType('zstandard'); "
                "z.ZstdDecompressor=type('Z', (), {}); sys.modules['zstandard']=z; "
                f"sys.path.insert(0, {str(self.repo_root())!r}); "
                "from modules.pak.re_pak_extract_mp import pakExtractor; "
                f"pakExtractor({job!r})"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    @staticmethod
    def repo_root():
        return str(REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
