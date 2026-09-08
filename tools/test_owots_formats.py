"""Regression checks for the OWOTS mesh, MDF and texture registrations.

Run inside Blender 5.2 with arguments after ``--``::

    blender --background --factory-startup -noaudio \
      --python tools/test_owots_formats.py -- \
      --mesh-addon D:/CODE/re/RE-Mesh-Editor-main \
      --mesh D:/path/to/file.mesh.260209350 \
      --mdf D:/path/to/file.mdf2.51

The checks use a real extracted sample for the format-specific assertions and
build one ordinary v51 MDF in memory for the non-Onimusha regression.
"""

from __future__ import annotations

import argparse
import importlib
import io
import struct
import sys
import tempfile
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    try:
        argv = sys.argv[sys.argv.index("--") + 1 :]
    except ValueError:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-addon", required=True)
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--mdf", required=True)
    parser.add_argument("--tex", required=True)
    parser.add_argument("--quality-base-texture")
    parser.add_argument("--quality-streaming-texture")
    return parser.parse_args(argv)


def enable_mesh_addon(path: str):
    addon_path = Path(path).resolve()
    if str(addon_path.parent) not in sys.path:
        sys.path.insert(0, str(addon_path.parent))
    result = bpy.ops.preferences.addon_enable(module=addon_path.name)
    if "FINISHED" not in result:
        raise RuntimeError(f"could not enable mesh addon: {result}")
    return importlib.import_module(addon_path.name)


def material_signature(mdf) -> list[tuple[str, str, str]]:
    return [
        (
            material.materialName,
            binding.textureType,
            binding.texturePath,
        )
        for material in mdf.materialList
        for binding in material.textureList
    ]


def assert_format_maps(mesh_module) -> None:
    mesh_file = importlib.import_module(mesh_module.__name__ + ".modules.mesh.file_re_mesh")
    mdf_file = importlib.import_module(mesh_module.__name__ + ".modules.mdf.file_re_mdf")
    tex_versions = importlib.import_module(
        mesh_module.__name__ + ".modules.tex.enums.game_version_enum"
    )

    assert mesh_file.meshFileVersionToGameNameDict[260209350] == "OWOTS"
    assert mesh_file.meshFileVersionToInternalVersionDict[260209350] == 250203152
    assert mdf_file.gameNameMDFVersionDict["OWOTS"] == 51
    assert tex_versions.gameNameToTexVersionDict["OWOTS"] == 251111100
    assert "OWOTS" in {
        item.identifier
        for item in mesh_module.ChunkPathPropertyGroup.bl_rna.properties["gameName"].enum_items
    }


def assert_mdf_roundtrip(mesh_module, path: Path) -> None:
    mdf_file = importlib.import_module(mesh_module.__name__ + ".modules.mdf.file_re_mdf")
    mdf = mdf_file.readMDF(str(path))
    fast = mdf_file.readMDFFast(str(path))
    assert mdf.isOnimushaVariant is True
    assert len(mdf.materialList) > 0
    assert material_signature(mdf) == material_signature(fast)

    with tempfile.TemporaryDirectory(prefix="owots_mdf_test_") as temp_dir:
        roundtrip_path = Path(temp_dir) / "roundtrip.mdf2.51"
        mdf_file.writeMDF(mdf, str(roundtrip_path))
        result = mdf_file.readMDF(str(roundtrip_path))
        assert result.isOnimushaVariant is True
        assert material_signature(result) == material_signature(mdf)

        # Keep the ordinary v51 layout covered. The upper half of its trailing
        # uint64 is zero, so it must not be mistaken for the Onimusha variant.
        regular = mdf_file.MDFFile()
        regular.materialList = [mdf_file.Material()]
        regular.materialList[0].materialName = "RegularV51"
        regular.materialList[0].mmtrPath = "regular.mmtr"
        regular.materialList[0].ver51UnknOffset = 0
        regular_path = Path(temp_dir) / "regular.mdf2.51"
        mdf_file.writeMDF(regular, str(regular_path))
        regular_result = mdf_file.readMDF(str(regular_path))
        assert regular_result.isOnimushaVariant is False
        assert regular_result.materialList[0].materialName == "RegularV51"


def assert_direct_mdf_game_identification(mesh_module, path: Path) -> None:
    mdf_ops = importlib.import_module(mesh_module.__name__ + ".modules.mdf.blender_re_mdf")
    mdf_ops.importMDFFile(str(path))
    assert bpy.context.scene.re_mdf_toolpanel.activeGame == "OWOTS"


def assert_mesh_import(mesh_module, path: Path, mdf_path: Path) -> None:
    importer = mesh_module.importREMeshFile
    options = {
        "clearScene": True,
        "createCollections": True,
        "loadMaterials": True,
        "loadMDFData": True,
        "loadShellFur": False,
        "loadUnusedTextures": False,
        "loadUnusedProps": False,
        "useBackfaceCulling": False,
        "reloadCachedTextures": False,
        "mdfPath": str(mdf_path),
        "importAllLODs": True,
        "importBlendShapes": False,
        "rotate90": True,
        "mergeArmature": "",
        "importArmatureOnly": False,
        "mergeGroups": False,
        "importShadowMeshes": False,
        "importOcclusionMeshes": False,
        "importBoundingBoxes": False,
    }
    warnings, errors = importer(str(path), options)
    mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    vertices = sum(len(obj.data.vertices) for obj in mesh_objects)
    assert not warnings, warnings
    assert not errors, errors
    assert mesh_objects and vertices > 0


def assert_tex_import(mesh_module, path: Path) -> None:
    tex_module = importlib.import_module(mesh_module.__name__ + ".modules.tex.file_re_tex")
    tex = tex_module.RE_TexFile()
    tex.read(str(path))
    header = tex.tex.header
    assert header.version == 251111100
    assert header.width > 0 and header.height > 0
    assert header.mipCount > 0
    assert len(tex.tex.imageMipDataList) == header.imageCount
    assert tex.tex.imageMipDataList[0][0].textureData

    # The file version is shared with MHS3. Keep the GDeflate branch covered
    # with a valid compressed-header table while the real OWOTS sample above
    # exercises the Modern/uncompressed branch.
    valid = bytearray(146)
    struct.pack_into("<Q", valid, 0, 100)
    struct.pack_into("<II", valid, 100, 20, 0)
    struct.pack_into("<II", valid, 108, 10, 20)
    assert tex_module.Tex._hasValidGDeflateHeaders(io.BytesIO(valid), 2, 1)
    invalid = bytearray(valid)
    struct.pack_into("<II", invalid, 108, 10, 0)
    assert not tex_module.Tex._hasValidGDeflateHeaders(io.BytesIO(invalid), 2, 1)


def assert_streaming_quality(mesh_module, base_path: Path, streaming_path: Path) -> None:
    tex_module = importlib.import_module(mesh_module.__name__ + ".modules.tex.file_re_tex")
    base = tex_module.RE_TexFile()
    base.read(str(base_path))
    streaming = tex_module.RE_TexFile()
    streaming.read(str(streaming_path))
    base_size = (base.tex.header.width, base.tex.header.height)
    streaming_size = (streaming.tex.header.width, streaming.tex.header.height)
    assert streaming_size[0] > base_size[0] or streaming_size[1] > base_size[1], (
        f"streaming texture did not improve mip dimensions: base={base_size}, "
        f"streaming={streaming_size}"
    )
    assert streaming_size[0] >= 2048 and streaming_size[1] >= 2048
    assert streaming.tex.header.mipCount >= base.tex.header.mipCount
    print(f"OWOTS texture quality: base={base_size}, streaming={streaming_size}")


def main() -> int:
    args = parse_args()
    mesh_module = enable_mesh_addon(args.mesh_addon)
    assert_format_maps(mesh_module)
    assert_mdf_roundtrip(mesh_module, Path(args.mdf).resolve())
    assert_direct_mdf_game_identification(mesh_module, Path(args.mdf).resolve())
    if args.quality_base_texture or args.quality_streaming_texture:
        if not args.quality_base_texture or not args.quality_streaming_texture:
            raise ValueError("quality check requires both base and streaming texture paths")
        assert_streaming_quality(
            mesh_module,
            Path(args.quality_base_texture).resolve(),
            Path(args.quality_streaming_texture).resolve(),
        )
    assert_tex_import(mesh_module, Path(args.tex).resolve())
    assert_mesh_import(mesh_module, Path(args.mesh).resolve(), Path(args.mdf).resolve())
    print("OWOTS format regression checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
