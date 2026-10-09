"""Audit delivered millimetre STEP/STL files and explicitly requested bores."""
import argparse
import json
import math
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh


def local_file(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'File leaves model directory: {relative}')
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def vector(value, label):
    result = np.asarray(value, dtype=float)
    require(result.shape == (3,) and np.isfinite(result).all(), f'Invalid {label}')
    return result


def inspect_bore(shape, spec, tolerance):
    origin = vector(spec['origin_mm'], 'bore origin')
    direction = vector(spec['axis'], 'bore axis')
    require(np.linalg.norm(direction) > 0, 'Bore axis is zero')
    direction /= np.linalg.norm(direction)
    radius = float(spec['diameter_mm']) / 2
    start, end = map(float, spec['axial_span_mm'])
    require(math.isfinite(radius) and radius > 0 and math.isfinite(start)
            and math.isfinite(end) and end > start, 'Invalid bore dimensions')
    found = []
    for face in shape.Faces():
        if face.geomType() != 'CYLINDER':
            continue
        cylinder = face._geomAdaptor().Cylinder()
        location = np.asarray(cylinder.Axis().Location().Coord())
        axis = np.asarray(cylinder.Axis().Direction().Coord())
        delta = location - origin
        distance = np.linalg.norm(delta - np.dot(delta, direction) * direction)
        if abs(cylinder.Radius() - radius) > tolerance or distance > tolerance:
            continue
        if abs(np.dot(axis, direction)) < 1 - 1e-8:
            continue
        projections = [np.dot(np.asarray(v.toTuple()) - origin, direction)
                       for v in face.Vertices()]
        if not projections:
            continue
        span = [float(min(projections)), float(max(projections))]
        if max(abs(span[0] - start), abs(span[1] - end)) <= tolerance:
            found.append(span)
    require(bool(found), 'Expected cylindrical surface position/diameter/span absent')
    # A matching cylinder can be an external boss. Also require a clear
    # inscribed cylinder along the specified interval, slightly inset to
    # avoid coincident BRep boundaries at the two ends.
    length = end - start
    inset = min(tolerance, length / 100)
    plane = cq.Plane(origin=tuple(origin + direction * (start + inset)),
                     normal=tuple(direction))
    envelope = cq.Workplane(plane).circle(radius * .99).extrude(length - 2 * inset).val()
    obstruction = shape.intersect(envelope).Volume()
    allowed = max(1e-5, envelope.Volume() * 1e-7)
    require(obstruction <= allowed, f'Bore occupied by {obstruction:.6g} mm3 of material')
    return {'diameter_mm': radius * 2, 'actual_axial_spans_mm': found,
            'clearance_obstruction_mm3': obstruction}


def inspect_part(root, part, tolerance, volume_tolerance):
    step = cq.importers.importStep(str(local_file(root, part['step']))).val()
    require(step.isValid(), 'Invalid STEP shape')
    solids = len(step.Solids())
    expected_solids = int(part.get('expected_solids', 1))
    require(solids == expected_solids and solids > 0, 'Unexpected STEP solid count')
    mesh = trimesh.load(local_file(root, part['stl']), force='mesh', process=True)
    require(isinstance(mesh, trimesh.Trimesh) and len(mesh.faces) > 0, 'Empty/non-mesh STL')
    require(np.isfinite(mesh.vertices).all(), 'Non-finite STL coordinates')
    require(mesh.is_watertight, 'STL has an open surface')
    require(mesh.is_winding_consistent, 'STL winding inconsistent')
    require(mesh.is_volume and mesh.volume > 0, 'STL is not a positive oriented volume')
    components = len(mesh.split(only_watertight=False))
    require(components == int(part.get('expected_mesh_components', expected_solids)),
            'Unexpected disconnected STL component count')
    box = step.BoundingBox()
    cad_bounds = np.array([[box.xmin, box.ymin, box.zmin],
                           [box.xmax, box.ymax, box.zmax]])
    bounds_error = float(np.max(np.abs(mesh.bounds - cad_bounds)))
    require(bounds_error <= tolerance, f'STEP/STL bounds differ by {bounds_error:g} mm')
    cad_volume = step.Volume()
    require(cad_volume > 0, 'STEP volume is not positive')
    volume_error = abs(mesh.volume - cad_volume) / cad_volume
    require(volume_error <= volume_tolerance,
            f'STEP/STL relative volume difference {volume_error:.3%}')
    if 'expected_dimensions_mm' in part:
        expected = vector(part['expected_dimensions_mm'], 'expected dimensions')
        require((expected > 0).all(), 'Expected dimensions must be positive')
        require(np.max(np.abs(mesh.extents - expected)) <= tolerance,
                'Dimensions differ from independent expectation')
    if part.get('print_on_bed', False):
        require(abs(mesh.bounds[0, 2]) <= tolerance, 'Printable mesh not on z=0 bed')
    bores = [inspect_bore(step, spec, tolerance) for spec in part.get('bores', [])]
    return {'id': part['id'], 'passed': True, 'step_solids': solids,
            'stl_components': components, 'stl_watertight': True,
            'dimensions_mm': mesh.extents.tolist(), 'volume_mm3': float(mesh.volume),
            'minimum_print_z_mm': float(mesh.bounds[0, 2]),
            'step_stl_bounds_max_error_mm': bounds_error,
            'step_stl_relative_volume_error': float(volume_error), 'bores': bores}


def run(manifest_path):
    root = manifest_path.resolve().parent
    data = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    require(data.get('units') == 'mm', 'Manifest must explicitly declare mm units')
    require(bool(data.get('parts')), 'Manifest has no parts')
    tolerance = float(data.get('dimension_tolerance_mm', .1))
    volume_tolerance = float(data.get('relative_volume_tolerance', .01))
    require(math.isfinite(tolerance) and tolerance > 0, 'Invalid dimension tolerance')
    require(math.isfinite(volume_tolerance) and 0 < volume_tolerance < 1,
            'Invalid relative volume tolerance')
    ids = [p['id'] for p in data['parts']]
    require(len(ids) == len(set(ids)), 'Duplicate part identifiers')
    report = {'passed': True, 'units': 'mm', 'parts': [],
              'scope': 'Exported STEP/STL topology, dimensions, bed pose and specified bores',
              'not_tested': ['assembly collision and pose', 'hardware and tool paths',
                             'slicing', 'physical fit', 'load, creep and temperature']}
    for part in data['parts']:
        try:
            report['parts'].append(inspect_part(root, part, tolerance, volume_tolerance))
        except Exception as error:
            report['passed'] = False
            report['parts'].append({'id': part.get('id'), 'passed': False,
                                    'error': str(error)})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.manifest)
    except Exception as error:
        report = {'passed': False, 'error': str(error)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
