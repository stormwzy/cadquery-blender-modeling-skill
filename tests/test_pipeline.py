"""Behavior checks for exports, false positives, failure reports and packaging."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import cadquery as cq
import trimesh


SCRIPTS = Path(__file__).resolve().parents[1] / 'skills' / 'cadquery-blender-modeling' / 'scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit, coupon, package = [load(name) for name in ('audit_models', 'build_fit_coupon', 'package_delivery')]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        coupon.build({}, self.root)
        self.manifest = self.root / 'model_manifest.json'

    def test_valid_export_and_archive(self):
        report = audit.run(self.manifest)
        self.assertTrue(report['passed'], report)
        (self.root / 'audit.json').write_text(json.dumps(report), encoding='utf-8')
        output = self.root / 'delivery.zip'
        package.package(self.manifest, output)
        with zipfile.ZipFile(output) as archive:
            hashes = json.loads(archive.read('SHA256SUMS.json'))
            self.assertIn('fit_coupon.step', hashes['files'])
            self.assertEqual(archive.read('fit_coupon.stl'), (self.root / 'fit_coupon.stl').read_bytes())

    def test_open_mesh_is_rejected(self):
        path = self.root / 'fit_coupon.stl'
        mesh = trimesh.load(path, force='mesh')
        broken = trimesh.Trimesh(mesh.vertices, mesh.faces[:-1], process=False)
        broken.export(path)
        self.assertFalse(audit.run(self.manifest)['passed'])

    def test_wrong_hole_position_is_rejected(self):
        data = json.loads(self.manifest.read_text())
        data['parts'][0]['bores'][0]['origin_mm'][0] = 2
        self.manifest.write_text(json.dumps(data))
        self.assertFalse(audit.run(self.manifest)['passed'])

    def test_shifted_print_pose_is_rejected(self):
        shape = cq.importers.importStep(str(self.root / 'fit_coupon.step')).translate((0, 0, 2))
        cq.exporters.export(shape, str(self.root / 'fit_coupon.step'))
        cq.exporters.export(shape, str(self.root / 'fit_coupon.stl'), tolerance=.03)
        report = audit.run(self.manifest)
        self.assertFalse(report['passed'])
        self.assertIn('bed', report['parts'][0]['error'])

    def test_outer_cylinder_is_not_a_hole(self):
        boss = cq.Workplane('XY').circle(2.2).extrude(10).val()
        spec = {'origin_mm': [0, 0, 0], 'axis': [0, 0, 1],
                'diameter_mm': 4.4, 'axial_span_mm': [0, 10]}
        with self.assertRaisesRegex(ValueError, 'occupied'):
            audit.inspect_bore(boss, spec, .05)

    def test_package_fails_for_missing_or_outside_files(self):
        data = json.loads(self.manifest.read_text())
        data['delivery_files'] = ['missing.stl']
        self.manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            package.package(self.manifest, self.root / 'bad.zip')
        nested = self.root / 'nested'
        nested.mkdir()
        escaped = nested / 'manifest.json'
        escaped.write_text(json.dumps({'delivery_files': ['../fit_coupon.stl']}))
        with self.assertRaises(ValueError):
            package.package(escaped, self.root / 'bad.zip')
        self.assertFalse((self.root / 'bad.zip').exists())

    def test_parameters_change_actual_exports(self):
        out = self.root / 'changed'
        coupon.build({'body_width_mm': 32, 'body_depth_mm': 35,
                      'body_height_mm': 24}, out)
        report = audit.run(out / 'model_manifest.json')
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['parts'][0]['dimensions_mm'], [32, 35, 24])


if __name__ == '__main__':
    unittest.main()
