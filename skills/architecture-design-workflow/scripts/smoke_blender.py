"""Optional Blender smoke test. Run inside Blender or Python with bpy installed."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_shell import export
from render_study import digest, run


def smoke():
    with TemporaryDirectory() as directory:
        temp = Path(directory)
        model = temp/"fixture.blend"
        source = {"units": "m", "meshes": {"floor": [{
            "vertices_m": [[-6, -6, 0], [6, -6, 0], [6, 6, 0], [-6, 6, 0]],
            "faces": [[0, 1, 2, 3]],
        }]}}
        export(source, model)
        bpy.ops.wm.open_mainfile(filepath=str(model), use_scripts=False)
        assert "floor/1" in bpy.context.scene.objects
        bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 2))
        bpy.context.object.name = "Shutter"
        bpy.ops.wm.save_as_mainfile(filepath=str(model))
        before = digest(model)
        config = {
            "schema": 1, "units": "m", "mode": "daylight", "datum": "Synthetic local test frame",
            "render": {"pixels": [64, 48], "samples": 4},
            "light": {"sun_direction": [1, 1, 2], "sun_energy": 2.5, "sky_strength": .2, "sun_angle_rad": .05},
            "neutral_material": {"linear_rgb": [.65, .65, .65], "roughness": .7},
            "views": [{"id": "fixed", "eye": [7, -7, 5], "aim": [0, 0, 1], "exposure_ev": 0}],
            "cases": [
                {"id": "open", "source": "fixture.blend", "visibility": {"Shutter": True}},
                {"id": "covered", "source": "fixture.blend", "visibility": {"Shutter": False}},
            ],
        }
        output = temp/"daylight"
        run(config, temp, output)
        study = json.loads((output/"study.json").read_text(encoding="utf-8"))
        assert study["cases"]["open"]["sha256"] == before == digest(model)
        assert digest(output/"open/fixed.png") != digest(output/"covered/fixed.png")
        for case in ("open", "covered"):
            image = bpy.data.images.load(str(output/case/"fixed.png"))
            assert tuple(image.size) == (64, 48)
            bpy.data.images.remove(image)
        config["cases"][1]["interior_poses"] = {"fixed": {"eye": [2, 0, 2]}}
        try:
            run(config, temp, temp/"invalid")
        except ValueError as error:
            assert "share all camera" in str(error)
        else:
            raise AssertionError("Daylight case silently moved the camera")
    print("Blender shell export, source preservation, two rendered controls and invalid control: passed")


if __name__ == "__main__":
    smoke()
