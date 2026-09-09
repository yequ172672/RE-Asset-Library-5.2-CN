"""Pure CPU checks for the RE Asset Library preview-data boundary.

The tests use small parser-shaped objects so they run with the system Python;
the real parser is still loaded dynamically by ``load_preview`` when the tool
is called from Blender.  A real extracted game file is intentionally not
required for these selection and byte-layout checks.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "modules" / "asset" / "preview_data.py"
SPEC = importlib.util.spec_from_file_location("re_asset_preview_data_test", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load preview module: {MODULE_PATH}")
preview = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preview
SPEC.loader.exec_module(preview)


def triangle_submesh(material_index: int, x_offset: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        vertexPosList=[
            (x_offset + 0.0, 0.0, 0.0),
            (x_offset + 1.0, 0.0, 0.0),
            (x_offset + 0.0, 1.0, 0.0),
        ],
        normalList=[(0.0, 0.0, 1.0)] * 3,
        uvList=[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
        faceList=[(0, 1, 2)],
        materialIndex=material_index,
        isReusedMesh=False,
        linkedSubMesh=None,
    )


def lod(*submeshes: SimpleNamespace, distance: float = 0.0) -> SimpleNamespace:
    group = SimpleNamespace(subMeshList=list(submeshes), visconGroupNum=0)
    return SimpleNamespace(visconGroupList=[group], lodDistance=distance)


def parsed(*lods: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(mainMeshLODList=list(lods), materialNameList=["Body", "Eyes"])


class PreviewDataTests(unittest.TestCase):
    def test_preview_mip_preserves_source_and_selects_512(self):
        original = SimpleNamespace(header=SimpleNamespace(width=2048, height=1024, depth=1, mipCount=4, imageCount=2),
                                   imageMipDataList=[['m0', 'm1', 'm2', 'm3'], ['other']])
        selected = preview._preview_mip(original, 512)
        self.assertEqual((selected.header.width, selected.header.height), (512, 256))
        self.assertEqual(selected.imageMipDataList, [['m2']])
        self.assertEqual(original.header.width, 2048)
        self.assertEqual(original.header.mipCount, 4)

    def test_tga_origin_and_24bit_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'origin.tga'
            header = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, 2, 1, 24, 0x10)
            path.write_bytes(header + bytes((255, 0, 0, 0, 0, 255)))
            self.assertEqual(preview._decode_tga(str(path)), (2, 1, bytes((255, 0, 0, 255, 0, 0, 255, 255))))
            path.write_bytes(header + b'bad')
            with self.assertRaises(preview.PreviewError): preview._decode_tga(str(path))

    def test_cache_has_byte_limit(self):
        cache = preview.OrderedDict()
        preview._cache_put(cache, 'a', 'first', 6, 10)
        preview._cache_put(cache, 'b', 'second', 6, 10)
        self.assertIsNone(preview._cache_get(cache, 'a'))
        self.assertEqual(preview._cache_get(cache, 'b'), 'second')
        preview._cache_put(cache, 'huge', 'skip', 11, 10)
        self.assertIsNone(preview._cache_get(cache, 'huge'))

    def test_lod_policy_prefers_lod2_then_falls_back_without_going_above_lod2(self) -> None:
        empty = lod()
        chosen_index, _ = preview._choose_lod(
            parsed(empty, empty, lod(triangle_submesh(0), distance=2.0), lod(triangle_submesh(1), distance=3.0))
        )
        self.assertEqual(chosen_index, 2, "LOD3 must never be selected even when it has geometry")

        chosen_index, _ = preview._choose_lod(parsed(empty, lod(triangle_submesh(1)), empty))
        self.assertEqual(chosen_index, 1)

        chosen_index, _ = preview._choose_lod(parsed(lod(triangle_submesh(0)), empty, empty))
        self.assertEqual(chosen_index, 0)


    def test_flatten_preserves_submesh_material_ranges_and_defaults_missing_streams(self) -> None:
        mesh = parsed(lod(triangle_submesh(1), triangle_submesh(0, 2.0)))
        flattened = preview._flatten_lod(mesh, 0, mesh.mainMeshLODList[0])

        self.assertEqual(flattened["vertices"], [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (2.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
            (2.0, 1.0, 0.0),
        ])
        self.assertEqual(flattened["indices"], [(0, 1, 2), (3, 4, 5)])
        self.assertEqual([row["slot"] for row in flattened["sections"]], [1, 0])
        self.assertEqual([row["first_index"] for row in flattened["sections"]], [0, 3])


    def test_base_color_binding_ignores_normal_and_roughness_maps(self) -> None:
        normal = SimpleNamespace(textureType="NormalRoughnessMap", texturePath="body_nrrt.tex")
        albedo = SimpleNamespace(textureType="BaseDielectricMap", texturePath="body_albd.tex")
        material = SimpleNamespace(textureList=[normal, albedo])
        self.assertIs(preview._choose_base_color_binding(material), albedo)


    def test_texture_path_uses_streaming_sidecar_and_active_editor_version(self) -> None:
        with tempfile.TemporaryDirectory(prefix="re_preview_tex_") as temp_dir:
            chunk = Path(temp_dir) / "natives" / "STM"
            texture = chunk / "streaming" / "art" / "body.tex.251111100"
            texture.parent.mkdir(parents=True)
            texture.write_bytes(b"fixture")
            fake_tex_module = SimpleNamespace(
                getTexVersionFromGameName=lambda game_name: 251111100,
            )
            with mock.patch.object(preview, "_editor_module", return_value=fake_tex_module):
                found = preview._find_texture_path(
                    "art/body.tex", [str(chunk)], "OWOTS", 51, fake_tex_module
                )
        self.assertEqual(found, str(texture.resolve()))


    def test_material_record_contains_only_decoded_base_color_texture(self) -> None:
        normal = SimpleNamespace(textureType="NormalRoughnessMap", texturePath="body_nrrt.tex")
        albedo = SimpleNamespace(textureType="BaseMap", texturePath="art/body.tex")
        source_material = SimpleNamespace(
            materialName="Body",
            propertyList=[SimpleNamespace(propName="BaseColor", propValue=[0.25, 0.5, 0.75, 1.0])],
            textureList=[normal, albedo],
        )
        mdf = SimpleNamespace(materialList=[source_material], fileVersion=51)
        parsed_mesh = SimpleNamespace(materialNameList=["Body"])
        fake_tex_module = SimpleNamespace(
            __name__="fake_texture_editor",
            getTexVersionFromGameName=lambda game_name: 251111100,
        )
        with tempfile.TemporaryDirectory(prefix="re_preview_material_") as temp_dir:
            chunk = Path(temp_dir) / "natives" / "STM"
            texture = chunk / "art" / "body.tex.251111100"
            texture.parent.mkdir(parents=True)
            texture.write_bytes(b"fixture")
            resource = {
                "game_name": "OWOTS",
                "chunk_paths": [str(chunk)],
                "cache_dir": temp_dir,
            }
            with mock.patch.object(preview, "_editor_module", return_value=fake_tex_module), mock.patch.object(
                preview, "_decode_rgba8", return_value=(1, 1, bytes((10, 20, 30, 255)))
            ):
                records = preview._material_records(parsed_mesh, mdf, fake_tex_module, resource, [])
        self.assertEqual(records[0]["base_color"], (0.25, 0.5, 0.75, 1.0))
        self.assertEqual(records[0]["base_color_texture"]["width"], 1)
        self.assertEqual(records[0]["base_color_texture"]["rgba8"], bytes((10, 20, 30, 255)))


    def test_tga_decode_returns_top_left_rgba8_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="re_preview_tga_") as temp_dir:
            path = Path(temp_dir) / "fixture.tga"
            _write_tga(path)
            width, height, rgba8 = preview._decode_tga(str(path))

        self.assertEqual((width, height), (2, 1))
        self.assertEqual(rgba8, bytes((255, 0, 0, 255, 0, 255, 0, 128)))


    def test_decode_rgba8_routes_tex_and_dds_to_converter(self) -> None:
        for extension in (".tex.251111100", ".DDS"):
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / ("base" + extension)
                source.write_bytes(b"source")
                tex_file = mock.Mock()
                dds_file = mock.Mock()
                dds_file.write.side_effect = lambda path: Path(path).write_bytes(b"converted")
                def convert(path, out, verbose):
                    self.assertEqual(Path(path).read_bytes(), b"source" if extension == ".DDS" else b"converted")
                    target = Path(out) / "preview.tga"
                    _write_tga(target)
                    return str(target)
                modules = [
                    SimpleNamespace(RE_TexFile=mock.Mock(return_value=tex_file), TexToDDS=mock.Mock()),
                    SimpleNamespace(DDSFile=mock.Mock(return_value=dds_file)),
                    SimpleNamespace(Texconv=lambda: SimpleNamespace(convert_to_tga=convert)),
                ]
                with mock.patch.object(preview, "_editor_module", side_effect=modules):
                    result = preview._decode_rgba8(str(source), object(), root / "cache")
                self.assertEqual(result, (2, 1, bytes((255, 0, 0, 255, 0, 255, 0, 128))))
                self.assertEqual(tex_file.read.call_count, 0 if extension == ".DDS" else 1)

    def test_load_preview_returns_plain_cpu_schema_without_bpy_data(self) -> None:
        mesh = parsed(lod(triangle_submesh(0)))
        fake_mesh_module = SimpleNamespace(__name__="fake_mesh_editor")
        resource = {
            "mesh_path": "fixture.mesh.260209350",
            "game_name": "OWOTS",
            "chunk_paths": [],
            "asset_id": "asset:fixture",
            "asset_name": "Fixture",
            "_mesh_module": fake_mesh_module,
        }

        with tempfile.TemporaryDirectory(prefix="re_preview_mesh_") as temp_dir:
            mesh_path = Path(temp_dir) / "fixture.mesh.260209350"
            mesh_path.write_bytes(b"fixture")
            resource["mesh_path"] = str(mesh_path)
            with mock.patch.object(preview, "_parse_mesh", return_value=mesh):
                result = preview.load_preview(resource)

        self.assertEqual(result["asset_id"], "asset:fixture")
        self.assertEqual(result["lod_index"], 0)
        self.assertEqual(result["indices"], [(0, 1, 2)])
        self.assertEqual(result["sections"], [{"slot": 0, "first_index": 0, "num_faces": 1}])
        self.assertEqual(result["materials"], [
            {
                "name": "Body",
                "base_color": (0.8, 0.8, 0.8, 1.0),
                "base_color_texture": None,
            },
            {
                "name": "Eyes",
                "base_color": (0.8, 0.8, 0.8, 1.0),
                "base_color_texture": None,
            },
        ])
        self.assertTrue(all(not isinstance(value, bytearray) for value in result["vertices"]))


    def test_load_preview_rejects_mply_without_collapsing_meshlets(self) -> None:
        mesh = parsed(lod(triangle_submesh(0)))
        mesh.isMPLY = True
        fake_mesh_module = SimpleNamespace(__name__="fake_mesh_editor")
        resource = {
            "game_name": "OWOTS",
            "chunk_paths": [],
            "asset_id": "asset:meshlet",
            "asset_name": "Meshlet",
            "_mesh_module": fake_mesh_module,
        }
        with tempfile.TemporaryDirectory(prefix="re_preview_mply_") as temp_dir:
            path = Path(temp_dir) / "meshlet.mesh.260209350"
            path.write_bytes(b"fixture")
            resource["mesh_path"] = str(path)
            with mock.patch.object(preview, "_parse_mesh", return_value=mesh):
                with self.assertRaisesRegex(preview.PreviewError, "MPLY meshlet previews"):
                    preview.load_preview(resource)


def _write_tga(path: Path) -> None:
    # 2x1, top-left origin, BGR(A) pixels: red then green.
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, 2, 1, 32, 0x20 | 8)
    path.write_bytes(header + bytes((0, 0, 255, 255, 0, 255, 0, 128)))


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PreviewDataTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
