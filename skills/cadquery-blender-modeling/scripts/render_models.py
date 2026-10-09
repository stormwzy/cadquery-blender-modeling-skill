"""Run with Blender --background --factory-startup --python SCRIPT -- ..."""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def local_file(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f'Missing or out-of-directory scene mesh: {relative}')
    return path


def material(name, color):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    shader = result.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Roughness'].default_value = .5
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene_json', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--resolution', type=int, default=1000)
    parser.add_argument('--samples', type=int, default=24)
    parser.add_argument('--views', default='front,back,side')
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(argv)
    if not bpy.app.background:
        raise RuntimeError('Use a separate background Blender process')
    if args.resolution < 64 or args.samples < 1:
        raise ValueError('Resolution must be at least 64 and samples positive')
    data = json.loads(args.scene_json.read_text(encoding='utf-8-sig'))
    if data.get('units') != 'mm' or not data.get('instances'):
        raise ValueError('Scene requires mm units and mesh instances')
    directions = {'front': (1, -1.4, 1.0), 'back': (-1, 1.4, 1.0),
                  'side': (1.6, 0, .6)}
    views = args.views.split(',')
    if any(v not in directions for v in views) or len(views) != len(set(views)):
        raise ValueError('Views must be unique names from front,back,side')
    args.out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'MILLIMETERS'
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = round(args.resolution * .75)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'AgX'
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.65, .7, .8, 1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .35
    objects, checks = [], []
    root = args.scene_json.resolve().parent
    for entry in data['instances']:
        role = entry.get('role', 'PRINT')
        if role not in ('PRINT', 'REFERENCE'):
            raise ValueError('Scene role must be PRINT or REFERENCE')
        before = set(bpy.data.objects)
        try:
            bpy.ops.wm.stl_import(filepath=str(local_file(root, entry['file'])),
                                  global_scale=.001, use_scene_unit=False,
                                  forward_axis='Y', up_axis='Z')
        except (AttributeError, RuntimeError) as error:
            raise RuntimeError('Blender STL import unavailable; check version/API') from error
        added = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
        if not added:
            raise ValueError('STL importer created no mesh')
        for obj in added:
            obj.name = f'{role} {entry.get("name", Path(entry["file"]).stem)}'
            obj['role'] = role
            obj['source_file'] = entry['file']
            bpy.context.view_layer.update()
            imported_dimensions = [v * 1000 for v in obj.dimensions]
            obj.location = tuple(v * .001 for v in entry.get('translation_mm', [0, 0, 0]))
            obj.rotation_euler = tuple(math.radians(v) for v in entry.get('rotation_deg', [0, 0, 0]))
            obj.data.materials.append(material(obj.name, entry.get('color', [.12, .19, .25])))
            for polygon in obj.data.polygons:
                polygon.use_smooth = False
            objects.append(obj)
            checks.append({'name': obj.name, 'role': role,
                           'imported_dimensions_mm': imported_dimensions})
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    lower = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    upper = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    center = (lower + upper) / 2
    size = max((upper - lower).length, .01)
    bpy.ops.mesh.primitive_plane_add(size=size * 6, location=(center.x, center.y, lower.z - .001))
    floor = bpy.context.object
    floor.name = 'REFERENCE studio floor'
    floor['role'] = 'REFERENCE'
    floor.data.materials.append(material('studio', [.68, .7, .72]))
    for name, direction, power in [('Key', (1, -2, 3), 8), ('Fill', (-2, -1, 1), 4),
                                    ('Rim', (0, 2, 2), 8)]:
        bpy.ops.object.light_add(type='AREA', location=center + Vector(direction) * size)
        light = bpy.context.object
        light.name = name
        light.data.energy = power * (size / .1) ** 2
        light.data.shape = 'DISK'
        light.data.size = size * 2
        light.rotation_euler = (center - light.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    scene.camera = camera
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = size * 1.6
    camera.data.clip_start = .0001
    camera.data.clip_end = max(10, size * 20)
    first_rotation, first_location = None, None
    for view in views:
        camera.location = center + Vector(directions[view]).normalized() * size * 3
        camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
        if first_location is None:
            first_location = camera.location.copy()
            first_rotation = camera.rotation_euler.copy()
        scene.render.filepath = str((args.out / f'preview_{view}.png').resolve())
        bpy.ops.render.render(write_still=True)
    camera.location, camera.rotation_euler = first_location, first_rotation
    scene['units_conversion'] = 'CAD millimetres to Blender metres: factor 0.001 once'
    scene['verification_scope'] = 'Preview only; no physical fit or load certification'
    bpy.ops.wm.save_as_mainfile(filepath=str((args.out / 'assembly_preview.blend').resolve()))
    (args.out / 'render_checks.json').write_text(json.dumps(
        {'blender_version': bpy.app.version_string, 'unit_scale': .001,
         'objects': checks, 'views': views}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
