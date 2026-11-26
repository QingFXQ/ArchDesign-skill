"""Run Blender in background for historical comparison or controlled daylight views."""
import argparse
import hashlib
import json
from math import asin, atan2, pi
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from design_input import keyed, number, position
from project_state import ID


def local_path(base, value):
    return (base / value).resolve()


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def rgb(value, label):
    color = position(value, 3, label)
    if any(not 0 <= channel <= 1 for channel in color):
        raise ValueError(f"{label}: use linear RGB values between 0 and 1")
    return color


def configure_sources(source, scene_name):
    if source.suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
    elif source.suffix.lower() == ".glb":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(source))
    else:
        raise ValueError(f"{source.name}: only .blend or .glb models are accepted")
    scene = bpy.data.scenes.get(scene_name) if scene_name else bpy.context.scene
    if scene is None:
        raise ValueError(f"{source.name}: scene {scene_name!r} not present")
    bpy.context.window.scene = scene
    return scene


def setup(scene, settings, light):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = settings["samples"]
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = settings["pixels"]
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    scene.render.use_border = False
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "None"
    scene.view_settings.gamma = 1
    for obj in scene.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True
    world = bpy.data.worlds.new("Study sky")
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    background = next(n for n in nodes if n.type == "BACKGROUND")
    direction = Vector(position(light["sun_direction"], 3, "sun_direction"))
    if direction.length == 0:
        raise ValueError("sun_direction must point from the site toward the sun")
    direction.normalize()
    sky = nodes.new("ShaderNodeTexSky")
    types = {item.identifier for item in sky.bl_rna.properties["sky_type"].enum_items}
    sky.sky_type = "MULTIPLE_SCATTERING" if "MULTIPLE_SCATTERING" in types else "NISHITA"
    sky.sun_disc = False
    if direction.z <= 0:
        raise ValueError("sun_direction must be above the horizon for this study")
    sky.sun_elevation = asin(direction.z)
    sky.sun_rotation = atan2(direction.y, direction.x)
    world.node_tree.links.new(sky.outputs["Color"], background.inputs["Color"])
    background.inputs["Strength"].default_value = number(light["sky_strength"], "sky_strength", 0)
    sun = bpy.data.lights.new("Study sun", "SUN")
    sun.energy = number(light["sun_energy"], "sun_energy", 0)
    angle = number(light["sun_angle_rad"], "sun_angle_rad", 0)
    if angle > pi:
        raise ValueError("sun_angle_rad must be in [0, pi]")
    sun.angle = angle
    sun.color = rgb(light.get("sun_color", [1, 1, 1]), "sun_color")
    obj = bpy.data.objects.new("Study sun", sun)
    scene.collection.objects.link(obj)
    obj.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()


def neutralize(scene, policy):
    if policy is None:
        return
    neutral = bpy.data.materials.new("Study neutral")
    neutral.use_nodes = True
    surface = next(node for node in neutral.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    surface.inputs["Base Color"].default_value = (*rgb(policy["linear_rgb"], "neutral"), 1)
    roughness = number(policy["roughness"], "roughness", 0)
    if roughness > 1:
        raise ValueError("roughness must be in [0, 1]")
    surface.inputs["Roughness"].default_value = roughness
    preserve = set(policy.get("keep_materials", [])) | {neutral.name}
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        if not obj.material_slots:
            obj.data.materials.append(neutral)
        for slot in obj.material_slots:
            if slot.material is None or slot.material.name not in preserve:
                # Per-object overrides avoid inherited slot changes on linked meshes.
                slot.link = "OBJECT"
                slot.material = neutral


def camera_for(scene, specification, eye, aim):
    location = Vector(position(eye, 3, "camera eye"))
    target = Vector(position(aim, 3, "camera aim"))
    if (target - location).length < 1e-9:
        raise ValueError("Camera eye and aim must differ")
    camera = bpy.data.cameras.new("Study camera")
    obj = bpy.data.objects.new("Study camera", camera)
    scene.collection.objects.link(obj)
    scene.camera = obj
    obj.location = location
    obj.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
    camera.lens = number(specification.get("lens_mm", 35), "lens_mm", 1)
    camera.sensor_width = 36
    camera.clip_start = number(specification.get("clip_start_m", .05), "clip_start_m", .001)
    camera.clip_end = number(specification.get("clip_end_m", 1000), "clip_end_m", camera.clip_start)
    if "ortho_width_m" in specification:
        camera.type = "ORTHO"
        camera.ortho_scale = number(specification["ortho_width_m"], "ortho_width_m", .01)
    scene.view_settings.exposure = number(specification["exposure_ev"], "exposure_ev")
    return obj


def visibility_for(scene, visibility, variant):
    for name, hidden in visibility.items():
        obj = scene.objects.get(name)
        if obj is None or obj.type not in {"MESH", "CURVE", "SURFACE"} or type(hidden) is not bool:
            raise ValueError(f"{variant}: visibility requires a real mesh, curve or surface and a boolean: {name}")
        obj.hide_render = hidden


def run(config, base, dest):
    mode = config.get("mode")
    if config.get("schema") != 1 or config.get("units") != "m" or mode not in {"history", "daylight"}:
        raise ValueError("Use schema 1, metre coordinates and mode history or daylight")
    if not isinstance(config.get("datum"), str) or not config["datum"].strip():
        raise ValueError("Describe the common project datum and orientation")
    settings = config["render"]
    values = [*settings["pixels"], settings["samples"]]
    if len(settings["pixels"]) != 2 or not all(type(n) is int and n > 0 for n in values):
        raise ValueError("Provide positive integer pixel dimensions and sample count")
    cases = keyed(config["cases"], "case")
    views = keyed(config["views"], "view")
    if not cases or not views or (mode == "daylight" and len(cases) < 2):
        raise ValueError("Provide nonempty views/cases and at least two cases for daylight")
    if not all(ID.fullmatch(identifier) for identifier in (*cases, *views)):
        raise ValueError("Case and view ids must be simple portable file names")
    paths = {k: local_path(base, c["source"]) for k, c in cases.items()}
    hashes = {p: digest(p) for p in set(paths.values())}
    if mode == "daylight":
        if len({(paths[k], c.get("scene")) for k, c in cases.items()}) != 1:
            raise ValueError("All daylight variants must use the same source file and scene")
        if any(c.get("interior_poses") for c in cases.values()):
            raise ValueError("Daylight variants must share all camera positions")
        changed_names = [set(c["visibility"]) for c in cases.values()]
        if not changed_names[0] or any(names != changed_names[0] for names in changed_names):
            raise ValueError("Declare the visibility of the same variable objects in all variants")
        if len({tuple(sorted(c["visibility"].items())) for c in cases.values()}) < 2:
            raise ValueError("Daylight variants must have distinct visibility values")
    result = {
        "mode": mode, "units": "m", "datum": config["datum"], "renderer": bpy.app.version_string,
        "render": settings, "light": config["light"], "material_policy": config.get("neutral_material"),
        "cases": {}, "manual": ["Review actual views and model sections; PNG brightness is not illuminance"],
    }
    dest.mkdir(parents=True, exist_ok=False)
    try:
        for name, case in cases.items():
            if mode == "history" and case.get("visibility"):
                raise ValueError(f"{name}: history comparison preserves source geometry visibility")
            scene = configure_sources(paths[name], case.get("scene"))
            neutralize(scene, config.get("neutral_material"))
            setup(scene, settings, config["light"])
            visibility_for(scene, case.get("visibility", {}), name)
            poses = case.get("interior_poses", {})
            if any(key not in views for key in poses):
                raise ValueError(f"{name}: unknown per-case camera")
            subset = dest / name
            subset.mkdir()
            entry = {"source": case["source"], "sha256": hashes[paths[name]], "scene": scene.name,
                     "visibility": case.get("visibility", {}), "views": {}}
            for key, spec in views.items():
                pose = poses.get(key, {})
                if pose and (spec.get("scope") != "interior" or not pose.get("reason")
                             or set(pose) != {"eye", "aim", "reason"}):
                    raise ValueError(f"{name}/{key}: only interior eye/aim overrides with a reason are allowed")
                eye, aim = pose.get("eye", spec["eye"]), pose.get("aim", spec["aim"])
                camera = camera_for(scene, spec, eye, aim)
                path = subset / f"{key}.png"
                scene.render.filepath = str(path)
                response = bpy.ops.render.render(write_still=True, scene=scene.name)
                if "FINISHED" not in response or not path.is_file():
                    raise RuntimeError(f"Render did not produce {name}/{key}")
                bpy.data.objects.remove(camera, do_unlink=True)
                entry["views"][key] = {**spec, **pose, "file": path.relative_to(dest).as_posix()}
            result["cases"][name] = entry
    finally:
        if any(digest(p) != v for p, v in hashes.items()):
            raise RuntimeError("Source model hash changed during the study")
    (dest / "study.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    run(config, args.config.resolve().parent, args.output.resolve())


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
