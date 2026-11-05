"""Regression tests for the native v52 decompiler and round-trip runner."""
from pathlib import Path
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import decompile52 as dc  # noqa: E402
import mdl52  # noqa: E402
import mdl52layout  # noqa: E402
import roundtrip52  # noqa: E402


def q48(q):
    x, y, z, w = q
    return struct.pack('<3H', round(x*32768+32768), round(y*32768+32768), (round(z*16384+16384) & 0x7FFF) | (0x8000 if w < 0 else 0))


def v48(v):
    return struct.pack('<3e', *v)


class DecompileV52(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = Path(os.environ.get('R1C_COMPILER', ROOT/'build/r1studiomdl.exe')).resolve()
        if not cls.compiler.exists():
            raise RuntimeError('build r1studiomdl before running decompiler tests')

    def setUp(self):
        (ROOT/'test-output').mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=ROOT/'test-output')
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def compile(self, qc_path, output):
        result = subprocess.run([str(self.compiler), '-quiet', '-o', str(output), str(qc_path)],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        mdl52.inspect(output, decode=True)
        return output

    def roundtrip(self, original):
        qc = dc.decompile(str(original), str(self.work/(original.stem + '_dc')))
        rebuilt = self.compile(qc, self.work/(original.stem + '_dc')/'recompiled.mdl')
        return roundtrip52.compare(roundtrip52.summary(str(original)), roundtrip52.summary(str(rebuilt)))

    def test_example_models_round_trip(self):
        for source in sorted((ROOT/'examples').rglob('*.qc')):
            with self.subTest(source=source.name):
                qc = re.sub(r'"([^"]+\.smd)"', lambda m: '"' + (source.parent/m[1]).as_posix() + '"', source.read_text())
                path = self.work/(source.stem + '.qc')
                path.write_text(qc, encoding='utf-8')
                original = self.compile(path, self.work/(source.stem + '.mdl'))
                self.assertEqual(self.roundtrip(original), [])

    def test_single_frame_flag_and_unused_texture(self):
        (self.work/'body.smd').write_text('\n'.join([
            'version 1', 'nodes', '0 "root" -1', 'end', 'skeleton', 'time 0', '0 0 0 0 0 0 0', 'end',
            'triangles', 'test/material', '0 0 0 0 0 0 1 0 0 1 0 1', '0 1 0 0 0 0 1 1 0 1 0 1',
            '0 0 1 0 0 0 1 0 1 1 0 1', 'end']) + '\n')
        lines = ['version 1', 'nodes', '0 "root" -1', 'end', 'skeleton']
        for t in range(4):
            lines += ['time %d' % t, '0 %d 0 0 0 0 0' % t]
        (self.work/'move.smd').write_text('\n'.join(lines + ['end']) + '\n')
        qc = self.work/'flags.qc'
        qc.write_text('$modelname "flags.mdl"\n$body body "body.smd"\n$texture "test/unused"\n'
                      '$singleframeflag\n$sequence idle "body.smd"\n$sequence move "move.smd"\n')
        model = mdl52layout.Model(self.compile(qc, self.work/'flags.mdl').read_bytes())
        h = model.hdr
        flags = [struct.unpack_from('<i', model.data, h['localseqindex'] + i * 0xD4 + 12)[0] for i in range(2)]
        self.assertEqual([bool(f & 0x80000) for f in flags], [True, False])
        textures = [mdl52layout.cstr(model.data, h['textureindex'] + i*0x40 + struct.unpack_from('<i', model.data, h['textureindex'] + i*0x40)[0])
                    for i in range(h['numtextures'])]
        self.assertEqual(textures, ['test/material', 'test/unused'])
        self.assertEqual(self.roundtrip(self.work/'flags.mdl'), [])

    def ref_smd(self, name='ref.smd'):
        (self.work/name).write_text('\n'.join([
            'version 1', 'nodes', '0 "root" -1', '1 "child" 0', 'end', 'skeleton', 'time 0', '0 0 0 0 0 0 0',
            '1 1 0 0 0 0 0', 'end', 'triangles', 'test/material', '1 0 0 0 0 0 1 0 0 1 1 1',
            '1 1 0 0 0 0 1 1 0 1 1 1', '1 0 1 0 0 0 1 0 1 1 1 1', 'end']) + '\n')

    def test_source_bone_transform_offset_is_from_file_start(self):
        self.ref_smd()
        qc = self.work/'src.qc'
        values = ' '.join(str(v) for v in [1, 0, 0, 2, 0, 1, 0, 3, 0, 0, 1, 4] * 2)
        qc.write_text('$modelname "src.mdl"\n$body body "ref.smd"\n$sequence idle "ref.smd"\n'
                      '$srcbonetransform "child" %s\n' % values)
        data = self.compile(qc, self.work/'src.mdl').read_bytes()
        hdr2 = struct.unpack_from('<i', data, 0x190)[0]
        count, index = struct.unpack_from('<2i', data, hdr2)
        self.assertEqual(count, 1)
        self.assertEqual(mdl52layout.cstr(data, index + struct.unpack_from('<i', data, index)[0]), 'child')
        self.assertEqual(struct.unpack_from('<4f', data, index + 4), (1., 0., 0., 2.))
        self.assertEqual(self.roundtrip(self.work/'src.mdl'), [])

    def test_stale_companion_is_ignored(self):
        self.ref_smd()
        qc = self.work/'stale.qc'
        qc.write_text('$modelname "stale.mdl"\n$body body "ref.smd"\n$sequence idle "ref.smd"\n')
        model = self.compile(qc, self.work/'stale.mdl')
        checksum = struct.unpack_from('<i', model.read_bytes(), 8)[0]
        vtx = model.with_suffix('.dx11.vtx')
        self.assertIsNotNone(mdl52layout.companion(str(model), '.dx11.vtx', checksum))
        data = bytearray(vtx.read_bytes())
        struct.pack_into('<i', data, 16, checksum + 1)
        vtx.write_bytes(data)
        self.assertIsNone(mdl52layout.companion(str(model), '.dx11.vtx', checksum))

    def test_large_scale_animation_widens_the_scale_step(self):
        self.ref_smd()
        lines = ['version 1', 'nodes', '0 "root" -1', '1 "child" 0', 'end', 'skeleton']
        for t, scale in enumerate((1., 500., 1000.)):
            lines += ['time %d' % t, '0 0 0 0 0 0 0', '1 1 0 0 0 0 0 %g %g %g' % (scale, scale, scale)]
        (self.work/'grow.smd').write_text('\n'.join(lines + ['end']) + '\n')
        qc = self.work/'grow.qc'
        qc.write_text('$modelname "grow.mdl"\n$body body "ref.smd"\n$sequence idle "ref.smd"\n$sequence grow "grow.smd"\n')
        path = self.compile(qc, self.work/'grow.mdl')
        model = mdl52layout.Model(path.read_bytes())
        bones = model.bones()
        self.assertGreater(bones[1]['scalescale'][0], 1 / 2048)
        self.assertEqual(bones[0]['scalescale'][0], 1 / 2048)
        pose = dc.decode_anim(model.data, model, bones, 1, [2], with_scale=True)[2][0]
        self.assertAlmostEqual(pose[1][2][0], 1000., delta=bones[1]['scalescale'][0])

    def anim_smd(self, name, frames):
        """frames: list of (child position, child roll/pitch/yaw radians)."""
        lines = ['version 1', 'nodes', '0 "root" -1', '1 "child" 0', 'end', 'skeleton']
        for t, (pos, rot) in enumerate(frames):
            lines += ['time %d' % t, '0 0 0 0 0 0 0', '1 %s %s' % (' '.join('%.9g' % v for v in pos), ' '.join('%.9g' % v for v in rot))]
        (self.work/name).write_text('\n'.join(lines + ['end']) + '\n')

    def child_track(self, path, anim):
        model = mdl52layout.Model(path.read_bytes())
        bones = model.bones()
        frames = dc.decode_anim(model.data, model, bones, anim)[2]
        independent = mdl52.Model(path.read_bytes())
        return model, [f[1] for f in frames], [independent.decode_frame(anim, f)[1] for f in range(len(frames))]

    def test_frame_encoded_output_matches_source(self):
        self.ref_smd()
        # rotations stay below ~115 degrees: near 180 the derived w of Quaternion48 is coarse
        frames = [((1 + t * 0.37, 2000.5 + t * 13.25, -3.0), (0.05 * t, -0.025 * t, 0.2)) for t in range(40)]
        self.anim_smd('walk.smd', frames)
        qc = self.work/'walk.qc'
        qc.write_text('$modelname "walk.mdl"\n$body body "ref.smd"\n$sequence idle "ref.smd"\n'
                      '$animation walk "walk.smd" frameanim\n$sequence walk walk\n')
        path = self.compile(qc, self.work/'walk.mdl')
        model, track, independent = self.child_track(path, 1)
        o = model.hdr['localanimindex'] + 0x64
        self.assertTrue(struct.unpack_from('<i', model.data, o + 12)[0] & 0x40)
        for (pos, rot), (got_pos, got_rot), other in zip(frames, track, independent):
            want = struct.unpack('<3f', struct.pack('<3f', *pos))  # inexact at half precision: stored as floats
            self.assertEqual(got_pos, want)
            self.assertLess(max(abs(a - b) for row_a, row_b in zip(got_rot, dc.angle_matrix(rot)) for a, b in zip(row_a, row_b)), 5e-4)  # Quaternion48 steps: 1/32768 (x, y), 1/16384 (z)
            self.assertEqual(other['pos'], want)

    def test_half_turn_roll_is_exact(self):
        # A roll of pi is the quaternion (1, 0, 0, 0); +1 overflows the packed formats
        # unless the sign is flipped.
        self.ref_smd()
        frames = [((1., 0., 0.), (math.pi, 0., 0.))] * 3 + [((1., 0., 0.), (0.5, 0., 0.))] * 3
        self.anim_smd('roll.smd', frames)
        qc = self.work/'roll.qc'
        qc.write_text('$modelname "roll.mdl"\n$body body "ref.smd"\n$sequence idle "ref.smd"\n'
                      '$animation rle "roll.smd"\n$animation frames "roll.smd" frameanim\n$sequence rle rle\n$sequence frames frames\n')
        path = self.compile(qc, self.work/'roll.mdl')
        for anim in (1, 2):
            with self.subTest(anim=anim):
                _, track, _ = self.child_track(path, anim)
                self.assertLess(max(abs(a - b) for row_a, row_b in zip(track[0][1], dc.angle_matrix((math.pi, 0, 0)))
                                    for a, b in zip(row_a, row_b)), 1e-4)

    def test_constant_channels_are_stored_raw(self):
        self.ref_smd()
        frames = [((5000.0, -2048.0, 0.25), (0.3, 0.2, 0.1))] * 8
        self.anim_smd('hold.smd', frames)
        qc = self.work/'hold.qc'
        qc.write_text('$modelname "hold.mdl"\n$body body "ref.smd"\n$sequence idle "ref.smd"\n$sequence hold "hold.smd"\n')
        path = self.compile(qc, self.work/'hold.mdl')
        model, track, independent = self.child_track(path, 1)
        source = dc.AnimData(model.data, model.hdr)
        buf, start = source.sections(1)[0]
        flags = {bone: f for _, bone, f in dc.rle_records(buf, start, 2)}
        self.assertEqual(flags[1] & 0x21, 0x21)  # raw Quaternion64 rotation and Vector48 position
        self.assertEqual(track[0][0], (5000.0, -2048.0, 0.25))
        self.assertEqual(independent[0]['pos'], (5000.0, -2048.0, 0.25))

    def test_stored_position_step_is_kept(self):
        self.ref_smd()
        step = 0.0123
        frames = [((step * 1000 * k, 0., 0.), (0., 0., 0.)) for k in range(5)]
        self.anim_smd('slide.smd', frames)
        qc = self.work/'slide.qc'
        qc.write_text('$modelname "slide.mdl"\n$body body "ref.smd"\n$sequence idle "ref.smd"\n'
                      '$boneposscale "child" %.9g 0.01 0.01\n$sequence slide "slide.smd"\n' % step)
        path = self.compile(qc, self.work/'slide.mdl')
        bones = mdl52layout.Model(path.read_bytes()).bones()
        self.assertAlmostEqual(bones[1]['posscale'][0], step, places=7)

    def test_flat_collision_is_a_closed_zero_volume_surface(self):
        self.ref_smd()
        cases = {'tri': [(0, 0, 0), (4, 0, 0), (0, 2, 0)],
                 'quad': [(0, 0, 0), (4, 0, 0), (4, 2, 0), (0, 2, 0)]}
        expected = {'tri': [(0, 1, 2), (1, 0, 2)]}
        for name, corners in cases.items():
            with self.subTest(case=name):
                lines = ['version 1', 'nodes', '0 "root" -1', 'end', 'skeleton', 'time 0', '0 0 0 0 0 0 0', 'end', 'triangles']
                for tri in ([0, 1, 2], [0, 2, 3]) if len(corners) == 4 else ([0, 1, 2],):
                    lines.append('phys')
                    lines += ['0 %g %g %g 0 0 1 0 0 1 0 1' % corners[i] for i in tri]
                (self.work/(name + '_phys.smd')).write_text('\n'.join(lines + ['end']) + '\n')
                qc = self.work/(name + '.qc')
                qc.write_text('$modelname "%s.mdl"\n$body body "ref.smd"\n$sequence idle "ref.smd"\n'
                              '$collisionmodel "%s_phys.smd" { $mass 1 }\n' % (name, name))
                path = self.compile(qc, self.work/(name + '.mdl'))
                import phy
                solid = phy.parse_phy(path.with_suffix('.phy').read_bytes())['solids'][0]
                ledge = [L for L in solid['ledges'] if not L['has_children']][0]
                tris = [tuple(e['start'] for e in t['edges']) for t in ledge['tris']]
                self.assertEqual(len(solid['points']), len(corners))
                self.assertEqual(len(tris), 2 * (len(corners) - 2))
                edges = {}
                for t in tris:
                    for k in range(3):
                        edges[(t[k], t[(k + 1) % 3])] = edges.get((t[k], t[(k + 1) % 3]), 0) + 1
                self.assertTrue(all(count == 1 and edges.get((b, a)) == 1 for (a, b), count in edges.items()))  # closed
                if name in expected:
                    self.assertEqual(tris, expected[name])

    def test_include_only_model_without_bones(self):
        qc = self.work/'include.qc'
        qc.write_text('$modelname "include.mdl"\n$includemodel "test/other.mdl"\n')
        model = mdl52layout.Model(self.compile(qc, self.work/'include.mdl').read_bytes())
        self.assertEqual((model.hdr['numbones'], model.hdr['numincludemodels'], model.hdr['numlocalseq']), (0, 1, 0))

    def test_repeated_material_entries_are_kept(self):
        lines = ['version 1', 'nodes', '0 "root" -1', 'end', 'skeleton', 'time 0', '0 0 0 0 0 0 0', 'end', 'triangles']
        for k, material in enumerate(('shared/grid', 'shared/grid_copy1')):
            lines.append(material)
            lines += ['0 %d 0 0 0 0 1 0 0 1 0 1' % (2 * k), '0 %d 1 0 0 0 1 0 0 1 0 1' % (2 * k + 1), '0 %d 0 1 0 0 1 0 0 1 0 1' % (2 * k)]
        (self.work/'two.smd').write_text('\n'.join(lines + ['end']) + '\n')
        qc = self.work/'two.qc'
        qc.write_text('$modelname "two.mdl"\n$body body "two.smd"\n$renamematerial "shared/grid_copy1" "shared/grid"\n'
                      '$sequence idle "two.smd"\n')
        path = self.compile(qc, self.work/'two.mdl')
        model = mdl52layout.Model(path.read_bytes())
        h = model.hdr
        names = [mdl52layout.cstr(model.data, h['textureindex'] + i*0x40 + struct.unpack_from('<i', model.data, h['textureindex'] + i*0x40)[0])
                 for i in range(h['numtextures'])]
        self.assertEqual(names, ['shared/grid', 'shared/grid'])
        self.assertEqual(self.roundtrip(path), [])

    def test_gimbal_locked_attachment_keeps_its_rotation(self):
        # Retail viewmodel hand attachments are axis permutations (pitch -90); written
        # as six-decimal Euler angles their yaw and roll no longer rebuild the matrix.
        self.ref_smd()
        qc = self.work/'hand.qc'
        qc.write_text('$modelname "hand.mdl"\n$body body "ref.smd"\n$sequence idle "ref.smd"\n'
                      '$attachment "R_HAND" "child" 0 0 0 matrix -5.96046448e-08 1 0 0 5.96046448e-08 '
                      '2.98023224e-08 0.999999881 3.81469727e-06 0.999999881 8.94069672e-08 0 0\n'  # retail ptpov_smr
                      '$attachment "TILT" "child" 0 0 0 rotate 10 20 30\n')
        path = self.compile(qc, self.work/'hand.mdl')
        self.assertEqual(self.roundtrip(path), [])
        original = roundtrip52.summary(str(path))['attachments'][0][2]
        rebuilt = roundtrip52.summary(str(self.work/'hand_dc'/'recompiled.mdl'))['attachments'][0][2]
        self.assertLess(max(abs(a - b) for a, b in zip(original, rebuilt)), 1e-6)

    def test_rotation_at_both_ends_of_the_range(self):
        # -pi picks Valve's negative-side scale; a value just under +pi then rounds
        # one step past the positive limit and must still compile.
        lines = ['version 1', 'nodes', '0 "root" -1', '1 "child" 0', 'end', 'skeleton']
        for t, angle in enumerate((-3.14159265, 3.1415925, 0.0)):
            lines += ['time %d' % t, '0 0 0 0 0 0 0', '1 1 0 0 %.9g 0 0' % angle]
        (self.work/'spin.smd').write_text('\n'.join(lines + ['end']) + '\n')
        (self.work/'ref.smd').write_text('\n'.join([
            'version 1', 'nodes', '0 "root" -1', '1 "child" 0', 'end', 'skeleton', 'time 0', '0 0 0 0 0 0 0',
            '1 1 0 0 0 0 0', 'end', 'triangles', 'test/material', '1 0 0 0 0 0 1 0 0 1 1 1',
            '1 1 0 0 0 0 1 1 0 1 1 1', '1 0 1 0 0 0 1 0 1 1 1 1', 'end']) + '\n')
        qc = self.work/'spin.qc'
        qc.write_text('$modelname "spin.mdl"\n$body body "ref.smd"\n$sequence idle "ref.smd"\n$sequence spin "spin.smd"\n')
        self.compile(qc, self.work/'spin.mdl')

    def test_frame_encoded_animation(self):
        bones = [{'pos': (1., 2., 3.), 'rot': (0., 0., 0.), 'scale': (1., 1., 1.), 'parent': -1},
                 {'pos': (4., 5., 6.), 'rot': (0., 0., 0.), 'scale': (1., 1., 1.), 'parent': 0}]
        half_turn = (0., 0., math.sqrt(.5), math.sqrt(.5))
        # bone 0: rotation and Vector48 position every frame; bone 1: constant rotation
        # and full-precision position (0x40)
        flags = bytes([0x18, 0x43])
        table = struct.pack('<4H', 0, 0, 12, 0)
        constants = q48(half_turn) + struct.pack('<3f', 7.25, -8.5, 9.125)
        frames = [q48((0., 0., 0., 1.)) + v48((10., 20., 30.)), q48(half_turn) + v48((-1., -2., -3.))]
        header_size = 24 + len(flags)
        table_at = (header_size + 3) & ~3
        const_at = table_at + len(table)
        frame_at = const_at + len(constants)
        block = struct.pack('<6i', const_at, frame_at, 12, 0, table_at, 0) + flags
        block += b'\0' * (table_at - len(block)) + table + constants + b''.join(frames)
        for frame, expected in enumerate(((10., 20., 30.), (-1., -2., -3.))):
            pose = dc._frame_pose(block, 0, frame, bones, False)
            self.assertEqual(pose[0][0], expected)
            self.assertEqual(pose[1][0], (7.25, -8.5, 9.125))
            self.assertAlmostEqual(pose[1][1][0][1], -1., places=4)  # 90 degree yaw
        self.assertAlmostEqual(dc._frame_pose(block, 0, 0, bones, False)[0][1][0][0], 1., places=4)

    def test_rle_raw_channels(self):
        bone = {'pos': (0., 0., 0.), 'rot': (0., 0., 0.), 'scale': (1., 1., 1.),
                'posscale': (1., 1., 1.), 'rotscale': (1., 1., 1.), 'scalescale': (1., 1., 1.), 'parent': -1}
        record = struct.pack('<BBh', 0, 0x02 | 0x01 | 0x40, 0) + q48((0., 0., 0., 1.)) + v48((1.5, -2., 3.)) + v48((2., 2., .5))
        pose = dc._rle_pose(record + struct.pack('<BBh', 255, 0, 0), 0, 0, [bone], False)
        self.assertEqual(pose[0][0], (1.5, -2., 3.))
        self.assertEqual(pose[0][2], (2., 2., .5))

    def test_vvd_fixups(self):
        header = struct.pack('<4i8i4i', 0x56534449, 4, 0, 2, 5, 3, 0, 0, 0, 0, 0, 0, 2, 64, 88, 88 + 5*48)
        fixups = struct.pack('<3i3i', 1, 0, 2, 0, 3, 3)
        vvd = header + fixups
        self.assertEqual(mdl52layout.vvd_ids(vvd), [0, 1, 3, 4, 5])


if __name__ == '__main__':
    unittest.main()
