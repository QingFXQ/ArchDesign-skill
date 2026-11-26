"""Convert design_check shell mesh output to an editable Blender massing file."""
import argparse
import json
from pathlib import Path
import sys

import bpy


def export(data, output):
    if data.get("units") != "m" or not data.get("meshes"):
        raise ValueError("Provide metre-based shell output with at least one mesh")
    if output.suffix.lower() != ".blend" or output.exists():
        raise ValueError("Choose a new .blend file, preserving any prior model")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    for group, parts in data["meshes"].items():
        collection = bpy.data.collections.new(group)
        scene.collection.children.link(collection)
        for i, part in enumerate(parts, start=1):
            name = f"{group}/{i}"
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(part["vertices_m"], [], part["faces"])
            if mesh.validate():
                raise ValueError(f"{name}: invalid generated mesh")
            mesh.update()
            obj = bpy.data.objects.new(name, mesh)
            collection.objects.link(obj)
    result = bpy.ops.wm.save_as_mainfile(filepath=str(output))
    if "FINISHED" not in result or not output.is_file():
        raise RuntimeError("Blender failed to save the shell model")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    export(json.loads(args.input.read_text(encoding="utf-8-sig")), args.output.resolve())


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
