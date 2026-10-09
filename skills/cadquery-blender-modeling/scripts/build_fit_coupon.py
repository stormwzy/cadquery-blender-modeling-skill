"""Build a generic short teardrop bore with an upward-open hex-nut slot."""
import argparse
import json
import math
from pathlib import Path

import cadquery as cq


DEFAULTS = {'body_width_mm': 26., 'body_depth_mm': 30., 'body_height_mm': 20.,
            'bore_diameter_mm': 4.4, 'bore_axis_height_mm': 10.,
            'bearing_length_mm': 10., 'slot_width_mm': 7.6,
            'slot_axis_depth_mm': 10., 'slot_floor_mm': 5.5,
            'nut_across_flats_mm': 7., 'nut_thickness_mm': 3.2}


def build(parameters, out):
    p = {**DEFAULTS, **parameters}
    if set(parameters) - set(DEFAULTS):
        raise ValueError('Unknown parameter keys')
    if any(not math.isfinite(v) or v <= 0 for v in p.values()):
        raise ValueError('All dimensions must be finite and positive')
    width, depth, height = (p[k] for k in ('body_width_mm', 'body_depth_mm', 'body_height_mm'))
    radius, axis_z = p['bore_diameter_mm'] / 2, p['bore_axis_height_mm']
    bearing, slot_depth, floor = p['bearing_length_mm'], p['slot_axis_depth_mm'], p['slot_floor_mm']
    af, nut_thickness = p['nut_across_flats_mm'], p['nut_thickness_mm']
    if not (width > p['slot_width_mm'] > af > p['bore_diameter_mm']
            and depth > bearing + slot_depth and slot_depth > nut_thickness + .1
            and 0 < floor < axis_z - af / math.sqrt(3)
            and radius < axis_z and axis_z + max(af / math.sqrt(3), radius * math.sqrt(2)) < height):
        raise ValueError('Dimensions do not retain clear nut space and surrounding material')
    part = cq.Workplane('XY').box(width, depth, height, centered=(True, False, False))
    # Plane local +v points downward; the negative-v roof points to print +Z.
    drill = cq.Plane(origin=(0, 0, axis_z), xDir=(1, 0, 0), normal=(0, 1, 0))
    bore = cq.Workplane(drill).circle(radius).extrude(bearing + .01)
    roof = [(-radius / math.sqrt(2), -radius / math.sqrt(2)),
            (0, -radius * math.sqrt(2)), (radius / math.sqrt(2), -radius / math.sqrt(2))]
    bore = bore.union(cq.Workplane(drill).polyline(roof).close().extrude(bearing + .01))
    slot = cq.Workplane('XY').box(p['slot_width_mm'], slot_depth, height - floor + 1,
                                 centered=(True, False, False)).translate((0, bearing, floor))
    part = part.cut(bore).cut(slot)
    if not part.val().isValid() or len(part.val().Solids()) != 1:
        raise ValueError('Coupon is invalid or disconnected')
    seat_plane = cq.Plane(origin=(0, bearing + .05, axis_z), xDir=(1, 0, 0), normal=(0, 1, 0))
    hex_radius = af / math.sqrt(3)
    # Rotate hex vertices 30 degrees: parallel flats lie at x=+-af/2.
    vertices = [(hex_radius * math.cos(math.radians(30 + 60 * i)),
                 hex_radius * math.sin(math.radians(30 + 60 * i))) for i in range(6)]
    nut = cq.Workplane(seat_plane).polyline(vertices).close().extrude(nut_thickness)
    insertion = cq.Workplane('XY').box(af, nut_thickness, height + af,
                                      centered=(True, False, False)).translate(
                                          (0, bearing + .05, axis_z - hex_radius))
    seat = cq.Workplane(drill).circle(af / 2).circle(radius).extrude(.2).translate((0, bearing - .2, 0))
    # Account for the roof notch when comparing the retained bearing face.
    support = part.val().intersect(seat.val()).Volume() / seat.val().Volume()
    checks = {'nominal_nut_collision_mm3': part.val().intersect(nut.val()).Volume(),
              'vertical_insertion_obstruction_mm3': part.val().intersect(insertion.val()).Volume(),
              'bearing_annulus_supported_fraction': support,
              'physical_print_tested': False, 'load_tested': False}
    if checks['nominal_nut_collision_mm3'] > .001 or checks['vertical_insertion_obstruction_mm3'] > .001 or support < .9:
        raise ValueError(f'Nut installation or bearing check failed: {checks}')
    out.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(part, str(out / 'fit_coupon.step'))
    cq.exporters.export(part, str(out / 'fit_coupon.stl'), tolerance=.03, angularTolerance=.05)
    manifest = {'units': 'mm', 'dimension_tolerance_mm': .05, 'relative_volume_tolerance': .01,
                'parts': [{'id': 'fit_coupon', 'stl': 'fit_coupon.stl', 'step': 'fit_coupon.step',
                           'quantity': 1, 'print_on_bed': True,
                           'expected_dimensions_mm': [width, depth, height],
                           'bores': [{'origin_mm': [0, 0, axis_z], 'axis': [0, 1, 0],
                                      'diameter_mm': p['bore_diameter_mm'], 'axial_span_mm': [0, bearing]}]}],
                'delivery_files': ['fit_coupon.stl', 'fit_coupon.step', 'parameters.json',
                                   'example_checks.json', 'model_manifest.json', 'scene.json',
                                   'audit.json', 'print_notes.md']}
    scene = {'units': 'mm', 'instances': [{'file': 'fit_coupon.stl', 'name': 'fit coupon',
                                          'role': 'PRINT', 'color': [.17, .24, .30]}]}
    for name, data in [('parameters.json', p), ('example_checks.json', checks),
                       ('model_manifest.json', manifest), ('scene.json', scene)]:
        (out / name).write_text(json.dumps(data, indent=2), encoding='utf-8')
    (out / 'print_notes.md').write_text(
        '# Generic fit coupon\n\nPrint one piece in millimetres at 100%, in the supplied bed pose. '
        'Keep the nut slot open upward. It is a process sample, not an assembly part. '
        'Verify slicing, bore clearance and your actual nut; no physical print or load test was performed.\n',
        encoding='utf-8')
    print(json.dumps({'built': str(out), 'checks': checks}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--parameters', type=Path)
    args = parser.parse_args()
    parameters = json.loads(args.parameters.read_text(encoding='utf-8-sig')) if args.parameters else {}
    build(parameters, args.out)


if __name__ == '__main__':
    main()
