"""Compare direct, cache-backed and MP-worker reads of one OWOTS chunk entry.

Example::

    python tools/validate_owots_pak.py \
      --game-dir D:/gametest/steamapps/common/OnimushaWotS \
      --output-dir D:/temp/owots_pak_validation/pak_entry_validation
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import types


REPO_ROOT = Path(__file__).resolve().parents[1]


def install_zstd_fallback() -> None:
    try:
        import zstandard  # noqa: F401
        return
    except ImportError:
        pass

    dll_path = REPO_ROOT.parent / "REE.PAK.Tool" / "REE.Unpacker" / "REE.Unpacker" / "Libs" / "libzstd.dll"
    if not dll_path.is_file():
        raise RuntimeError("zstandard is unavailable and the bundled libzstd.dll was not found")
    dll = ctypes.CDLL(str(dll_path))
    dll.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    dll.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
    dll.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    dll.ZSTD_decompress.restype = ctypes.c_size_t
    dll.ZSTD_isError.argtypes = [ctypes.c_size_t]
    dll.ZSTD_isError.restype = ctypes.c_uint

    class BundledZstdDecompressor:
        def decompress(self, data):
            source = ctypes.create_string_buffer(data)
            size = dll.ZSTD_getFrameContentSize(source, len(data))
            if size >= (1 << 64) - 2:
                size = max(len(data) * 100, 1024 * 1024)
            target = ctypes.create_string_buffer(size)
            result = dll.ZSTD_decompress(target, size, source, len(data))
            if dll.ZSTD_isError(result):
                raise RuntimeError("bundled zstd decompression failed")
            return target.raw[:result]

    zstandard_stub = types.ModuleType("zstandard")
    zstandard_stub.ZstdDecompressor = BundledZstdDecompressor
    sys.modules["zstandard"] = zstandard_stub


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--game-dir",
        default=r"D:\gametest\steamapps\common\OnimushaWotS",
        help="Onimusha: Way of the Sword installation directory",
    )
    parser.add_argument(
        "--output-dir",
        default=r"D:\temp\owots_pak_validation\pak_entry_validation",
        help="directory for temporary cache and MP output",
    )
    parser.add_argument(
        "--path",
        default="natives/stm/gui/ui_tips/movie/tips_movie_024.mov.1",
        help="known path to compare across readers",
    )
    parser.add_argument(
        "--check-streaming",
        action="store_true",
        help="also retrieve the case-insensitive streaming sidecar from the cache",
    )
    return parser.parse_args()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    args = parse_args()
    game_dir = Path(args.game_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(REPO_ROOT))
    install_zstd_fallback()

    from modules.pak.file_re_pak import PakFile
    from modules.pak.re_pak_extract_mp import pakExtractor
    from modules.pak.re_pak_utils import (
        PakCacheStream,
        createPakCacheFile,
        getStreamingPath,
        pathToPakHash,
        readPakEntryData,
        scanForPakFiles,
    )

    pak_paths = scanForPakFiles(str(game_dir))
    if not pak_paths:
        raise RuntimeError(f"no PAK files found under {game_dir}")
    print("scan order:")
    for index, pak_path in enumerate(pak_paths):
        print(f"  {index}: {Path(pak_path).name}")

    target_hash = pathToPakHash(args.path)
    source_path = None
    source_file = None
    source_entry = None
    source_entry_index = None
    source_chunk_table = None
    pak_hash_sets = {}
    for pak_path in pak_paths:
        with open(pak_path, "rb") as stream:
            pak_file = PakFile()
            pak_file.readTOC(stream)
        pak_hash_sets[Path(pak_path).name] = {
            (entry.hashNameLower << 32) | entry.hashNameUpper
            for entry in pak_file.toc.entryList
        }
        if source_entry is None:
            for entry_index, entry in enumerate(pak_file.toc.entryList):
                combined_hash = (entry.hashNameLower << 32) | entry.hashNameUpper
                if combined_hash == target_hash:
                    source_path = pak_path
                    source_file = pak_file
                    source_entry = entry
                    source_entry_index = entry_index
                    source_chunk_table = pak_file.chunkTable
                    break
    if source_entry is None or source_file is None or source_path is None:
        raise RuntimeError(f"path was not found: {args.path}")

    print("entry overlaps:")
    for index, left in enumerate(pak_paths):
        left_name = Path(left).name
        for right in pak_paths[index + 1:]:
            right_name = Path(right).name
            print(f"  {left_name} / {right_name}: {len(pak_hash_sets[left_name] & pak_hash_sets[right_name])}")
    if source_entry.offsetType != 1 and not args.check_streaming:
        raise RuntimeError("selected sample is not a chunk-table entry")
    chunk_descriptors = []
    chunk = None
    overflow = None
    physical_offset = None
    if source_entry.offsetType == 1:
        if source_chunk_table is None:
            raise RuntimeError("selected chunk entry has no chunk table")
        chunk = source_chunk_table.entryList[source_entry.offset]
        overflow = chunk.attributes & 0x3FF
        physical_offset = chunk.fileOffset
        if physical_offset <= 0x100000000:
            raise RuntimeError("selected chunk does not exercise a >4GiB offset")
        remaining_compressed = source_entry.compressedSize
        chunk_index = source_entry.offset
        while remaining_compressed > 0:
            current = source_chunk_table.entryList[chunk_index]
            current_size = current.compressedSize
            if current_size <= 0 or current_size > remaining_compressed:
                raise RuntimeError("invalid chunk span while preparing validation report")
            current_overflow = current.attributes & 0x3FF
            chunk_descriptors.append({
                "index": chunk_index,
                "physicalOffset": current.fileOffset,
                "overflow": current_overflow,
                "chunkSize": current_size,
                "rawBlock": current_size == source_chunk_table.blockSize,
            })
            remaining_compressed -= current_size
            chunk_index += 1
        if remaining_compressed != 0:
            raise RuntimeError("chunk span does not cover compressed entry size")

    with open(source_path, "rb") as stream:
        direct_data = readPakEntryData(source_entry, stream, source_chunk_table)

    cache_path = output_dir / "PakCache_OWOTS.pakcache"
    cache_order = list(reversed(pak_paths))
    print("cache priority order:")
    for index, pak_path in enumerate(cache_order):
        print(f"  {index}: {Path(pak_path).name}")
    createPakCacheFile(cache_order, str(cache_path))
    exe_path = game_dir / "OnimushaWotS.exe"
    extract_info = output_dir / "ExtractInfo_OWOTS.json"
    extract_info.write_text(json.dumps({
        "exePath": str(exe_path),
        "exeDate": os.path.getmtime(exe_path) + 1,
        "exeCRC": 0,
        "extractPath": str(output_dir),
        "platform": "STM",
    }), encoding="utf-8")
    cache_stream = PakCacheStream(str(output_dir), "OWOTS")
    try:
        cache_data = cache_stream.retrieveFileData(args.path)
        streaming_path = None
        streaming_data = None
        if args.check_streaming:
            streaming_path = getStreamingPath(args.path, "STM", cache_stream.lookupDict)
            if streaming_path is None:
                raise RuntimeError(f"streaming sidecar was not found for {args.path}")
            streaming_data = cache_stream.retrieveFileData(streaming_path)
    finally:
        cache_stream.closeStreams()

    mp_output = output_dir / "mp_extract"
    mp_job = {
        "jobIndex": 0,
        "pakPath": source_path,
        "outDir": str(mp_output),
        "fileEntries": [{
            "offset": source_entry.offset,
            "compressedSize": source_entry.compressedSize,
            "decompressedSize": source_entry.decompressedSize,
            "compressionType": source_entry.compressionType,
            "encryptionType": source_entry.encryptionType,
            "offsetType": source_entry.offsetType,
            "filePath": args.path,
        }],
    }
    pakExtractor(mp_job)
    print()
    mp_path = mp_output / Path(*args.path.split("/"))
    mp_data = mp_path.read_bytes()

    hashes = {"direct": sha256(direct_data), "cache": sha256(cache_data), "mp": sha256(mp_data)}
    print("selected source:", Path(source_path).name)
    offset_label = "chunkIndex" if source_entry.offsetType == 1 else "byteOffset"
    print("entryIndex:", source_entry_index, offset_label, source_entry.offset, "compressed", source_entry.compressedSize, "decompressed", source_entry.decompressedSize)
    print("chunkCount:", len(chunk_descriptors), "chunks:", chunk_descriptors)
    if chunk is not None:
        print("chunk:", source_entry.offset, "rawOffset", chunk.offset, "overflow", overflow, "physicalOffset", physical_offset, "encodedSize", chunk.attributes, "chunkSize", chunk.attributes >> 10)
    print("sizes:", {name: len(data) for name, data in (("direct", direct_data), ("cache", cache_data), ("mp", mp_data))})
    print("headMagic:", direct_data[:16].hex(" "))
    print("sha256:", hashes)
    if streaming_data is not None:
        print("streamingPair:", streaming_path, "size", len(streaming_data), "headMagic", streaming_data[:16].hex(" "), "sha256", sha256(streaming_data))
    if len(set(hashes.values())) != 1:
        raise RuntimeError("direct/cache/MP outputs differ")
    print("PAK validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
