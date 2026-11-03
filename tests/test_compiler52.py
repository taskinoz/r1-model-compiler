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
import mdl52
import phy


class NativeV52(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = Path(os.environ.get('R1C_COMPILER', ROOT/'build/r1studiomdl.exe')).resolve()
        if not cls.compiler.exists():
            raise RuntimeError('build r1studiomdl before running compiler tests')

    def setUp(self):
        (ROOT/'test-output').mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=ROOT/'test-output')
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def compile(self, qc, output='test.mdl', success=True):
        path = self.work/'test.qc'
        path.write_text(qc,encoding='utf-8')
        destination = self.work/output
        result = subprocess.run([str(self.compiler),'-quiet','-o',str(destination),str(path)],capture_output=True,text=True,timeout=40)
        if success:
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            mdl52.inspect(destination,decode=True)
        else:
            self.assertNotEqual(result.returncode,0)
        return destination,result

    def smd(self, frames, name='anim.smd'):
        lines=['version 1','nodes','0 "root" -1','1 "child" 0','end','skeleton']
        for index, (position,rotation,scale) in enumerate(frames):
            lines += [f'time {index}','0 0 0 0 0 0 0',f'1 {position:.9g} 0 0 0 0 {rotation:.9g} {scale:.9g} {scale:.9g} {scale:.9g}']
        lines += ['end','triangles','test/material','1 0 0 0 0 0 1 0 0 1 1 1',
                  '1 1 0 0 0 0 1 1 0 1 1 1','1 0 1 0 0 0 1 0 1 1 1 1','end']
        path=self.work/name
        path.write_text('\n'.join(lines)+'\n',encoding='ascii')
        return path

    def authored_qc(self, extra=''):
        self.smd([(10.,0.,1.)], 'body.smd')
        return '$modelname "test.mdl"\n$body body "body.smd"\n$sequence idle "body.smd"\n'+extra

    def test_native_headers_and_companions(self):
        p,_=self.compile(self.authored_qc())
        m=mdl52.Model(p.read_bytes())
        self.assertEqual(m.name,'test.mdl')
        self.assertEqual(m.integer(0x190),0x198)
        self.assertEqual(m.models[0]['vertices'],3)
        self.assertTrue(p.with_suffix('.vvd').exists())
        self.assertTrue(p.with_suffix('.dx11.vtx').exists())
        self.assertFalse(p.with_suffix('.phy').exists())
        self.assertEqual(m.bones[1]['scale'],(1.,1.,1.))

    def test_all_example_models(self):
        for source in sorted((ROOT/'examples').rglob('*.qc')):
            with self.subTest(source=source.name):
                qc=re.sub(r'"([^"]+\.smd)"',lambda match:'"'+(source.parent/match[1]).as_posix()+'"',source.read_text())
                p,_=self.compile(qc,source.stem+'.mdl')
                self.assertEqual(mdl52.Model(p.read_bytes()).integer(4),52)
                if p.with_suffix('.phy').exists():
                    physical=phy.parse_phy(p.with_suffix('.phy').read_bytes())
                    self.assertGreater(physical['solidCount'],0)

    def test_translation_rotation_scale_every_frame(self):
        qc=self.authored_qc()
        frames=[(10.+i*.123, i*.013,1.+i/100.) for i in range(21)]
        self.smd(frames)
        p,_=self.compile(qc+'$sequence moving "anim.smd" fps 30\n')
        m=mdl52.Model(p.read_bytes())
        for index,expected in enumerate(frames):
            pose=m.decode_frame(1,index)[1]
            self.assertAlmostEqual(pose['pos'][0],expected[0],delta=.003)
            self.assertAlmostEqual(pose['rot'][2],expected[1],delta=.0001)
            self.assertAlmostEqual(pose['scale'][0],expected[2],delta=.00025)

    def test_bone_position_scale_shared_between_animations(self):
        qc=self.authored_qc()
        self.smd([(10.,0.,1.),(10000.,0.,1.)], 'big.smd')
        self.smd([(10.,0.,1.),(20.,0.,1.)], 'small.smd')
        p,_=self.compile(qc+'$sequence big "big.smd"\n$sequence small "small.smd"\n')
        m=mdl52.Model(p.read_bytes())
        step=m.bones[1]['posscale'][0]
        self.assertGreater(step,.3)
        for a,want in [(1,10000.),(2,20.)]:
            self.assertAlmostEqual(m.decode_frame(a,1)[1]['pos'][0],want,delta=step/2+.001)

    def test_sectioned_animation_all_boundaries(self):
        qc=self.authored_qc()
        frames=[(10.+i*.123,i*.003,1.) for i in range(132)]
        self.smd(frames)
        p,_=self.compile(qc+'$sectionframes 30 120\n$sequence moving "anim.smd"\n')
        m=mdl52.Model(p.read_bytes())
        self.assertEqual(m.animations[1]['sectionframes'],30)
        for index,frame in enumerate(frames):
            pose=m.decode_frame(1,index)[1]
            self.assertAlmostEqual(pose['pos'][0],frame[0],delta=.003)
            self.assertAlmostEqual(pose['rot'][2],frame[1],delta=.0001)

    def test_dmx_binary_and_keyvalues2(self):
        for name in ('cube_arm.dmx','cube_arm_kv2.dmx'):
            with self.subTest(input=name):
                path=(ROOT/'tests/dmx'/name).as_posix()
                p,_=self.compile(f'$modelname "dmx.mdl"\n$body body "{path}"\n$sequence idle "{path}"\n')
                m=mdl52.Model(p.read_bytes())
                self.assertGreaterEqual(len(m.bones),1)
                self.assertGreater(m.models[0]['vertices'],0)

    def test_checksum_mismatch_rejected(self):
        p,_=self.compile(self.authored_qc())
        peer=p.with_suffix('.vvd')
        data=bytearray(peer.read_bytes())
        struct.pack_into('<i',data,8,123)
        peer.write_bytes(data)
        with self.assertRaisesRegex(mdl52.FormatError,'checksum'):
            mdl52.inspect(p)

    def test_missing_companion_rejected(self):
        p,_=self.compile(self.authored_qc())
        p.with_suffix('.dx11.vtx').unlink()
        with self.assertRaisesRegex(mdl52.FormatError,'companion'):
            mdl52.inspect(p)

    def test_stale_optional_companions_removed(self):
        qc=self.authored_qc()
        p,_=self.compile(qc)
        p.with_suffix('.phy').write_bytes(b'old physics')
        p.with_suffix('.vvc').write_bytes(b'old vertex colours')
        self.compile(qc)
        self.assertFalse(p.with_suffix('.phy').exists())
        self.assertFalse(p.with_suffix('.vvc').exists())

    def test_sequence_has_no_v53_singleframe_marker(self):
        p,_=self.compile(self.authored_qc())
        model=mdl52.Model(p.read_bytes())
        seq=model.integer(0xc0)
        self.assertEqual(model.integer(seq+12)&0x80000,0)

    def test_corrupt_model_offsets_rejected(self):
        p,_=self.compile(self.authored_qc())
        data=bytearray(p.read_bytes())
        struct.pack_into('<i',data,0xa0,len(data)+1)
        with self.assertRaises(mdl52.FormatError):
            mdl52.Model(data)

    def test_corrupt_vtx_index_rejected(self):
        p,_=self.compile(self.authored_qc())
        path=p.with_suffix('.dx11.vtx')
        data=bytearray(path.read_bytes())
        b=mdl52.Binary(data)
        bp=b.integer(32)
        model=bp+b.integer(bp+4)
        lod=model+b.integer(model+4)
        mesh=lod+b.integer(lod+4)
        group=mesh+b.integer(mesh+4)
        index=group+b.integer(group+12)
        struct.pack_into('<H',data,index,65535)
        path.write_bytes(data)
        with self.assertRaisesRegex(mdl52.FormatError,'index out of range'):
            mdl52.inspect(p)

    def test_native_ik_rule_layout_and_error_samples(self):
        lines=['version 1','nodes','0 "root" -1','1 "hip" 0','2 "knee" 1','3 "foot" 2','end','skeleton']
        for index in range(5):
            lines += [f'time {index}','0 0 0 0 0 0 0','1 0 0 30 0 0 0','2 0 0 -15 0 0 0','3 0 0 -15 0 0 0']
        lines += ['end','triangles','test/material','3 0 0 0 0 0 1 0 0 1 3 1',
                  '3 1 0 0 0 0 1 1 0 1 3 1','3 0 1 0 0 0 1 0 1 1 3 1','end']
        (self.work/'leg.smd').write_text('\n'.join(lines)+'\n')
        errors=[(i*.25,-i*.5,0,i*.125,0,0) for i in range(5)]
        (self.work/'stored.ikerr').write_text('.25 .5 0 .125 0 0\n'+''.join(' '.join(map(str,row))+'\n' for row in errors))
        qc=('$modelname "leg.mdl"\n$body body "leg.smd"\n$ikchain leg foot knee 1 0 0\n'
            '$animation move "leg.smd" ikrule leg footstep range 0 1 3 4 contact 1 '
            'storedtarget 123 -456 0 0 0 0 1 errors "stored.ikerr"\n$sequence move move\n')
        path,_=self.compile(qc)
        model=mdl52.Model(path.read_bytes())
        anim=model.animations[0]['offset']
        self.assertEqual(model.integer(anim+0x3c),1)
        rule=anim+model.integer(anim+0x40)
        self.assertEqual(model.integer(rule+4),3)
        self.assertEqual(model.read('3f',rule+0x20),(123.,-456.,0.))
        self.assertEqual(model.read('4f',rule+0x4c),(0.,.25,.75,1.))
        self.assertEqual(model.read('f',rule+0x60)[0],.25)
        self.assertEqual(model.read('f',rule+0x7c)[0],-100.)
        error=rule+model.integer(rule+0x3c)
        scales=model.read('6f',error)
        offsets=model.read('6h',error+24)
        for frame,expected in enumerate(errors):
            decoded=tuple(scales[c]*mdl52.rle_value(model,error+offsets[c],frame) if offsets[c] else 0. for c in range(6))
            self.assertEqual(decoded,expected)

    def test_v53_ui_feature_rejected(self):
        panel='$uipanel "screen" { parent "root" vertex 0 0 0 0 vertex 0 0 1 0 vertex 0 1 1 0 face 0 1 2 bounds 0 1 1 0 0 0 1 1 }\n'
        _,result=self.compile(self.authored_qc(panel),success=False)
        self.assertIn('v52 RUI',result.stdout+result.stderr)


if __name__=='__main__':
    unittest.main()
