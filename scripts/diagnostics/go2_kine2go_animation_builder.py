"""Build the calibrated Kine2Go Idle/Walk actions and render previews.

The P4.1 input file is opened by Blender and never overwritten. The script
uses rigid FK Empty rotations only; it does not create an Armature, skinning,
mesh deformation, or world XY locomotion.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
from pathlib import Path
from typing import Any

import bpy
import numpy as np
from mathutils import Quaternion, Vector


JOINTS = (
    "FR_hip", "FR_thigh", "FR_calf",
    "FL_hip", "FL_thigh", "FL_calf",
    "RR_hip", "RR_thigh", "RR_calf",
    "RL_hip", "RL_thigh", "RL_calf",
)
AXIS_INDEX = {"hip": 0, "thigh": 1, "calf": 1}
SOURCE_DEFAULT = np.array((0.0, 0.8, -1.5, 0.0, 0.8, -1.5, 0.0, 1.0, -1.5, 0.0, 1.0, -1.5))
SOURCE_COLUMNS = (7, 11, 15, 6, 10, 14, 9, 13, 17, 8, 12, 16)
LIMITS = {
    "FR_hip": (-1.0472, 1.0472), "FR_thigh": (-1.5708, 3.4907), "FR_calf": (-2.7227, -0.83776),
    "FL_hip": (-1.0472, 1.0472), "FL_thigh": (-1.5708, 3.4907), "FL_calf": (-2.7227, -0.83776),
    "RR_hip": (-1.0472, 1.0472), "RR_thigh": (-0.5236, 4.5379), "RR_calf": (-2.7227, -0.83776),
    "RL_hip": (-1.0472, 1.0472), "RL_thigh": (-0.5236, 4.5379), "RL_calf": (-2.7227, -0.83776),
}
FPS = 60
CYCLE_START = 402
CYCLE_END = 443
BLEND_FRAMES = 6
IDLE_ACTION_START = 1
IDLE_ACTION_END = 61
IDLE_NLA_START = 1
WALK_NLA_START = 101


def parse_args() -> argparse.Namespace:
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--motion", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output-blend", type=Path, required=True)
    parser.add_argument("--output-glb", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--report-md", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path, required=True)
    return parser.parse_args(raw)


def joint_object_name(name: str) -> str:
    leg, link = name.split("_")
    return f"FK_{leg}_{link.upper()}_JOINT"


def smooth_loop_tail(values: np.ndarray, blend_frames: int) -> np.ndarray:
    """Replace the tail with a Hermite transition back to sample zero."""

    if values.ndim != 2 or len(values) <= blend_frames + 2:
        raise ValueError("Not enough samples for loop blending")
    result = values.copy()
    anchor = len(result) - blend_frames - 1
    p0 = result[anchor].copy()
    p1 = result[0].copy()
    m0 = (result[anchor] - result[anchor - 1]) * blend_frames
    m1 = (result[1] - result[0]) * blend_frames
    for step in range(1, blend_frames + 1):
        t = step / blend_frames
        h00 = 2 * t**3 - 3 * t**2 + 1
        h10 = t**3 - 2 * t**2 + t
        h01 = -2 * t**3 + 3 * t**2
        h11 = t**3 - t**2
        result[anchor + step] = h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1
    return result


def source_body_channels(motion: np.ndarray) -> np.ndarray:
    values = []
    for row in motion:
        w, x, y, z = (float(value) for value in row[51:55])
        euler = Quaternion((w, x, y, z)).to_euler("XYZ")
        values.append((float(row[50]), float(euler.x), float(euler.y)))
    result = np.array(values)
    result -= result.mean(axis=0, keepdims=True)
    return result


def validate_limits(q: np.ndarray) -> dict[str, Any]:
    result = {}
    for index, name in enumerate(JOINTS):
        lower, upper = LIMITS[name]
        values = q[:, index]
        bad = np.where((values < lower) | (values > upper))[0]
        result[name] = {
            "status": "PASS" if not bad.size else "FAIL",
            "min_rad": float(values.min()), "max_rad": float(values.max()),
            "lower_rad": lower, "upper_rad": upper,
            "violation_count": int(bad.size),
            "first_violation_output_frame": int(bad[0]) if bad.size else None,
        }
    return result


def clear_animation_data() -> None:
    for obj in bpy.data.objects:
        if obj.animation_data:
            obj.animation_data_clear()
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def add_curve(action: bpy.types.Action, data_path: str, index: int, values: np.ndarray, frames: np.ndarray) -> None:
    curve = action.fcurves.new(data_path=data_path, index=index)
    for frame, value in zip(frames, values, strict=True):
        point = curve.keyframe_points.insert(float(frame), float(value), options={"FAST"})
        point.interpolation = "LINEAR"
    curve.update()


def create_action(
    obj: bpy.types.Object,
    action_name: str,
    rotations: np.ndarray,
    locations: np.ndarray | None = None,
) -> bpy.types.Action:
    action = bpy.data.actions.new(f"{action_name}__{obj.name}")
    frames = np.arange(1, len(rotations) + 1)
    action.use_frame_range = True
    action.frame_start = 1
    action.frame_end = len(rotations)
    for axis in range(3):
        add_curve(action, "rotation_euler", axis, rotations[:, axis], frames)
    if locations is not None:
        for axis in range(3):
            add_curve(action, "location", axis, locations[:, axis], frames)
    return action


def add_strip(obj: bpy.types.Object, track_name: str, action: bpy.types.Action, start: int) -> bpy.types.NlaStrip:
    animation_data = obj.animation_data_create()
    track = animation_data.nla_tracks.new()
    track.name = track_name
    strip = track.strips.new(track_name, start, action)
    strip.action_frame_start = action.frame_start
    strip.action_frame_end = action.frame_end
    strip.frame_start = start
    strip.frame_end = start + (action.frame_end - action.frame_start)
    strip.extrapolation = "NOTHING"
    strip.repeat = 1.0
    return strip


def build_actions(walk_q: np.ndarray, body_channels: np.ndarray) -> dict[str, Any]:
    clear_animation_data()
    body = bpy.data.objects.get("BODY")
    if body is None:
        raise RuntimeError("Missing BODY")
    neutral_body_rotation = np.array(body.rotation_euler, dtype=float)
    neutral_body_location = np.array(body.location, dtype=float)
    strips = {"Idle": [], "Walk": []}

    for index, name in enumerate(JOINTS):
        obj = bpy.data.objects.get(joint_object_name(name))
        if obj is None:
            raise RuntimeError(f"Missing FK joint: {joint_object_name(name)}")
        neutral = np.array(obj.rotation_euler, dtype=float)
        axis = AXIS_INDEX[name.split("_")[1]]
        idle_rotations = np.repeat(neutral[None, :], IDLE_ACTION_END, axis=0)
        idle_rotations[:, axis] += SOURCE_DEFAULT[index]
        walk_rotations = np.repeat(neutral[None, :], len(walk_q), axis=0)
        walk_rotations[:, axis] += walk_q[:, index]
        strips["Idle"].append(add_strip(obj, "Idle", create_action(obj, "Idle", idle_rotations), IDLE_NLA_START))
        strips["Walk"].append(add_strip(obj, "Walk", create_action(obj, "Walk", walk_rotations), WALK_NLA_START))

    idle_body_rotations = np.repeat(neutral_body_rotation[None, :], IDLE_ACTION_END, axis=0)
    idle_body_locations = np.repeat(neutral_body_location[None, :], IDLE_ACTION_END, axis=0)
    walk_body_rotations = np.repeat(neutral_body_rotation[None, :], len(body_channels), axis=0)
    walk_body_rotations[:, 0] += body_channels[:, 1]
    walk_body_rotations[:, 1] += body_channels[:, 2]
    walk_body_locations = np.repeat(neutral_body_location[None, :], len(body_channels), axis=0)
    walk_body_locations[:, 2] += body_channels[:, 0]
    strips["Idle"].append(add_strip(body, "Idle", create_action(body, "Idle", idle_body_rotations, idle_body_locations), IDLE_NLA_START))
    strips["Walk"].append(add_strip(body, "Walk", create_action(body, "Walk", walk_body_rotations, walk_body_locations), WALK_NLA_START))

    bpy.context.scene.render.fps = FPS
    bpy.context.scene.frame_start = IDLE_NLA_START
    bpy.context.scene.frame_end = WALK_NLA_START + len(walk_q) - 1
    bpy.context.scene.frame_set(IDLE_NLA_START)
    bpy.context.view_layer.update()
    return strips


def parse_glb(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise RuntimeError(f"Not a GLB: {path}")
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20 : 20 + json_length].decode("utf-8").rstrip(" \t\r\n\0"))
    return {
        "animations": [
            {"name": animation.get("name"), "channels": len(animation.get("channels", [])), "samplers": len(animation.get("samplers", []))}
            for animation in document.get("animations", [])
        ],
        "mesh_count": len(document.get("meshes", [])),
        "material_count": len(document.get("materials", [])),
        "skin_count": len(document.get("skins", [])),
        "node_count": len(document.get("nodes", [])),
    }


def export_glb(path: Path) -> None:
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", export_animation_mode="ACTIONS",
        export_merge_animation="NLA_TRACK", export_nla_strips=True,
        export_animations=True, export_apply=False, export_image_format="AUTO",
        export_cameras=False, export_lights=False,
    )


def sample_foot_plane(walk_frames: int) -> dict[str, Any]:
    samples = []
    for offset in range(walk_frames):
        bpy.context.scene.frame_set(WALK_NLA_START + offset)
        bpy.context.view_layer.update()
        samples.append([float(bpy.data.objects[f"{leg}_foot"].matrix_world.translation.z) for leg in ("FR", "FL", "RR", "RL")])
    values = np.array(samples)
    ground = float(np.median(values.min(axis=1)))
    penetration = np.maximum(ground - values, 0.0)
    return {
        "ground_z": ground,
        "max_origin_penetration_m": float(penetration.max()),
        "contact_frames_per_leg_10mm": {
            leg: int(np.sum(np.abs(values[:, index] - ground) <= 0.01))
            for index, leg in enumerate(("FR", "FL", "RR", "RL"))
        },
        "foot_origin_z_min": values.min(axis=0).tolist(),
        "foot_origin_z_max": values.max(axis=0).tolist(),
    }


def look_at(camera: bpy.types.Object, target: tuple[float, float, float]) -> None:
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


def add_preview_scene(ground_z: float) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    bpy.ops.mesh.primitive_plane_add(size=6.0, location=(0.0, 0.0, ground_z))
    ground = bpy.context.object
    ground.name = "PREVIEW_GROUND"
    material = bpy.data.materials.new("Preview Ground")
    material.diffuse_color = (0.035, 0.045, 0.055, 1.0)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled:
        principled.inputs["Base Color"].default_value = material.diffuse_color
        principled.inputs["Roughness"].default_value = 0.82
    ground.data.materials.append(material)

    lights = []
    for name, location, energy, size in (
        ("PREVIEW_KEY", (1.5, -1.5, 2.0), 320.0, 4.0),
        ("PREVIEW_FILL", (-1.2, -0.5, 1.0), 110.0, 3.0),
        ("PREVIEW_RIM", (0.0, 1.4, 1.5), 180.0, 2.5),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        obj = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = location
        look_at(obj, (0.0, 0.0, -0.1))
        lights.append(obj)

    camera_data = bpy.data.cameras.new("PREVIEW_CAMERA")
    camera = bpy.data.objects.new("PREVIEW_CAMERA", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera_data.lens = 50
    bpy.context.scene.camera = camera
    return camera, [ground, *lights]


def configure_render() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.008, 0.012, 0.018)
    scene.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "AgX - Medium High Contrast Look", "Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    scene.view_settings.exposure = -1.25
    scene.view_settings.gamma = 1.0


def render_previews(args: argparse.Namespace, strips: dict[str, list[bpy.types.NlaStrip]], ground_z: float) -> dict[str, Any]:
    args.preview_dir.mkdir(parents=True, exist_ok=True)
    configure_render()
    camera, _ = add_preview_scene(ground_z)
    target = (0.0, 0.0, ground_z + 0.24)
    views = {
        "front": (1.8, 0.0, ground_z + 0.72),
        "side": (0.0, -1.85, ground_z + 0.72),
        "three_quarter": (1.5, 1.5, ground_z + 0.95),
    }
    stills = {}
    bpy.context.scene.frame_set(WALK_NLA_START + 10)
    for name, position in views.items():
        camera.location = position
        look_at(camera, target)
        path = args.preview_dir / f"go2_kine2go_{name}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        stills[name] = str(path)

    phase_stills = []
    camera.location = views["three_quarter"]
    look_at(camera, target)
    for index, offset in enumerate((0, 10, 20, 30)):
        bpy.context.scene.frame_set(WALK_NLA_START + offset)
        path = args.preview_dir / f"go2_kine2go_phase_{index}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        phase_stills.append(str(path))

    preview_frames = FPS * 5
    action_duration = CYCLE_END - CYCLE_START
    repeats = math.ceil((preview_frames - 1) / action_duration)
    for strip in strips["Walk"]:
        strip.repeat = repeats
        strip.frame_end = WALK_NLA_START + repeats * action_duration
    scene = bpy.context.scene
    scene.frame_start = WALK_NLA_START
    scene.frame_end = WALK_NLA_START + preview_frames - 1
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    video_path = args.preview_dir / "go2_kine2go_walk_preview.mp4"
    scene.render.filepath = str(video_path)
    bpy.ops.render.render(animation=True)
    return {"stills": stills, "phase_stills": phase_stills, "video": str(video_path), "duration_s": 5.0}


def write_report(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Go2 Kine2Go Animation Report", ""]
    for key in (
        "WALK_ACTION", "IDLE_ACTION", "WALK_LOOP", "JOINT_LIMIT",
        "FOOT_CONTACT_VISUAL", "MESH_COLLISION_VISUAL", "GLB_EXPORT",
        "GLB_ANIMATIONS", "READY_FOR_FLUTTER",
    ):
        lines.append(f"- `{key}`: **{report[key]}**")
    lines.extend([
        "", "## Animation", "",
        f"- Source: `{report['source']}`",
        f"- Source frames: `{report['source_frames']}`",
        f"- Output frames: `{report['walk_output_frames']}` at `{FPS} FPS`",
        f"- Loop metrics: `{report['loop_metrics']}`",
        f"- GLB animations: `{report['glb']['animations']}`",
        "", "Visual statuses remain PARTIAL until the rendered stills/video are inspected.",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
    required = ("ZERO_OFFSET_MODEL", "SIGN_MODEL", "FOOT_POSITION_VALIDATION", "LEGAL_STABLE_CYCLE_FOUND")
    if any(calibration.get(key) != "PASS" for key in required):
        raise RuntimeError(f"Calibration is not ready: {[(key, calibration.get(key)) for key in required]}")
    if tuple(calibration["SOURCE_DOF_COLUMN_MAPPING"][name] for name in JOINTS) != SOURCE_COLUMNS:
        raise RuntimeError("Calibration DOF columns do not match the locked mapping")

    motion = np.load(args.motion, allow_pickle=False)
    source = motion[CYCLE_START : CYCLE_END + 1]
    raw_q = source[:, list(SOURCE_COLUMNS)]
    raw_body = source_body_channels(source)
    walk_q = smooth_loop_tail(raw_q, BLEND_FRAMES)
    body_channels = smooth_loop_tail(raw_body, BLEND_FRAMES)
    limits = validate_limits(walk_q)
    idle_limits = validate_limits(SOURCE_DEFAULT[None, :])
    if any(item["status"] != "PASS" for item in (*limits.values(), *idle_limits.values())):
        raise RuntimeError("Generated animation violates the Genesis URDF limits")

    loop_metrics = {
        "pose_seam_rms_rad": float(np.linalg.norm(walk_q[-1] - walk_q[0]) / math.sqrt(12)),
        "velocity_seam_rms_rad_per_frame": float(np.linalg.norm((walk_q[-1] - walk_q[-2]) - (walk_q[1] - walk_q[0])) / math.sqrt(12)),
        "body_seam_rms": float(np.linalg.norm(body_channels[-1] - body_channels[0]) / math.sqrt(3)),
        "blend_frames": BLEND_FRAMES,
    }
    if loop_metrics["pose_seam_rms_rad"] > 1e-6 or loop_metrics["body_seam_rms"] > 1e-6:
        raise RuntimeError(f"Loop closure failed: {loop_metrics}")

    strips = build_actions(walk_q, body_channels)
    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend), check_existing=False)
    export_glb(args.output_glb)
    glb = parse_glb(args.output_glb)
    animation_names = [item["name"] for item in glb["animations"]]
    glb_pass = set(animation_names) == {"Idle", "Walk"} and glb["skin_count"] == 0
    foot_plane = sample_foot_plane(len(walk_q))

    report = {
        "source": "Kine2Go Go2-retargeted AI4Animation dog_walk00 trajectory",
        "source_motion": str(args.motion),
        "source_frames": [CYCLE_START, CYCLE_END],
        "walk_output_frames": len(walk_q),
        "fps": FPS,
        "mapping": dict(zip(JOINTS, SOURCE_COLUMNS)),
        "zero_model": "Blender local rotation = source absolute q",
        "signs": dict.fromkeys(JOINTS, 1.0),
        "idle_pose": "Kine2Go RobotConfig legal static standing pose",
        "WALK_ACTION": "PASS", "IDLE_ACTION": "PASS",
        "WALK_LOOP": "PASS", "loop_metrics": loop_metrics,
        "JOINT_LIMIT": "PASS", "walk_joint_limits": limits, "idle_joint_limits": idle_limits,
        "foot_plane_analysis": foot_plane,
        "FOOT_CONTACT_VISUAL": "PARTIAL", "MESH_COLLISION_VISUAL": "PARTIAL",
        "BLENDER_EXPORT": "PASS", "output_blend": str(args.output_blend),
        "GLB_EXPORT": "PASS" if glb_pass else "FAIL", "output_glb": str(args.output_glb),
        "GLB_ANIMATIONS": "PASS" if glb_pass else "FAIL", "glb": glb,
        "READY_FOR_FLUTTER": "PARTIAL",
        "preview": {},
    }
    write_report(report, args.report_json, args.report_md)
    report["preview"] = render_previews(args, strips, foot_plane["ground_z"])
    write_report(report, args.report_json, args.report_md)
    print(json.dumps({key: report[key] for key in ("WALK_ACTION", "IDLE_ACTION", "WALK_LOOP", "JOINT_LIMIT", "GLB_EXPORT", "GLB_ANIMATIONS", "READY_FOR_FLUTTER")}, indent=2))


if __name__ == "__main__":
    main()
