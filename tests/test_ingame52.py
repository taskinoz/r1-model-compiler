from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import ingame_test52 as harness


class HarnessTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'test-output').mkdir(exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=ROOT/'test-output')
        self.addCleanup(temp.cleanup)
        self.work=Path(temp.name)
        self.game=self.work/'game'
        (self.game/'Bin').mkdir(parents=True)
        (self.game/'Bin/TFO.exe').write_bytes(b'not executable: preparation tests only')
        self.base=self.game/'Mods/TFORevive.Core/mod/scripts/vscripts/_mapspawn.nut'
        self.base.parent.mkdir(parents=True)
        self.original=b'// synthetic game script fixture\n'
        self.base.write_bytes(self.original)
        self.run='a'*32

    def compiled_model(self):
        compiler=Path(os.environ.get('R1C_COMPILER',ROOT/'build/r1studiomdl.exe')).resolve()
        output=self.work/'box.mdl'
        subprocess.run([str(compiler),'-quiet','-o',str(output),str(ROOT/'examples/static_prop/box.qc')],check=True,capture_output=True,timeout=30)
        return output

    def events(self):
        return '\n'.join(f'[R1C:{self.run}] '+message for message in [
            'PRECACHE models/test/box.mdl','INIT','SPAWN 0 model=models/test/box.mdl origin=<0,0,0>',
            'ANIM 0 sequence=idle index=0','POSE 0 sample=4 origin=<0,0,0>','DONE'])

    def test_companion_staging_and_owned_cleanup(self):
        model=self.compiled_model()
        unrelated=self.game/'Mods/UserMod'
        unrelated.mkdir()
        (unrelated/'keep.txt').write_text('keep')
        mod,evidence,_=harness.prepare(self.game,[(model,'models/test/box.mdl')],self.run)
        for suffix in ('.mdl','.vvd','.dx11.vtx','.phy'):
            self.assertEqual((mod/'mod/models/test/box.mdl').with_suffix(suffix).read_bytes(),model.with_suffix(suffix).read_bytes())
        self.assertEqual(len(evidence[0]['files']),4)
        self.assertEqual(self.base.read_bytes(),self.original)
        harness.safe_cleanup(mod,self.game/'Mods',self.run)
        self.assertFalse(mod.exists())
        self.assertTrue((unrelated/'keep.txt').exists())
        self.assertEqual(self.base.read_bytes(),self.original)

    def test_checksum_failure_before_game_mutation(self):
        model=self.compiled_model()
        model.with_suffix('.vvd').write_bytes(b'bad')
        with self.assertRaises(ValueError):
            harness.prepare(self.game,[(model,'models/test/box.mdl')],self.run)
        self.assertEqual([p.name for p in (self.game/'Mods').iterdir()],['TFORevive.Core'])

    def test_cleanup_rejects_foreign_owner(self):
        mod=self.game/'Mods/Foreign'
        mod.mkdir()
        (mod/harness.OWNER).write_text(json.dumps({'run_id':'b'*32}))
        with self.assertRaisesRegex(ValueError,'ownership'):
            harness.safe_cleanup(mod,self.game/'Mods',self.run)
        self.assertTrue(mod.exists())

    def test_cleanup_rejects_outside_mods(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            harness.safe_cleanup(self.work,self.game/'Mods',self.run)

    def test_traversal_and_script_injection_rejected(self):
        for path in ('../models/a.mdl','models/../../a.mdl','C:/models/a.mdl','/models/a.mdl','models/a.mdl;quit','models/a.txt'):
            with self.subTest(path=path),self.assertRaises(ValueError): harness.game_path(path)
        with self.assertRaises(ValueError): harness.script(self.run,['models/a.mdl'],'idle";quit','',False)

    def test_complete_telemetry_passes(self):
        result=harness.evaluate(self.events(),self.run,1,paths=['models/test/box.mdl'])
        self.assertTrue(result['passed'],result)

    def test_other_run_is_not_evidence(self):
        self.assertFalse(harness.evaluate(self.events(),'b'*32,1)['passed'])

    def test_partial_or_wrong_model_cannot_pass(self):
        for text in (self.events().replace('DONE',''),self.events().replace('POSE 0 sample=4','POSE 0 sample=3'),
                     self.events().replace('SPAWN 0 model=models/test/box.mdl','SPAWN 0 model=models/error.mdl')):
            with self.subTest(text=text):
                self.assertFalse(harness.evaluate(text,self.run,1,paths=['models/test/box.mdl'])['passed'])

    def test_runtime_error_after_done_fails(self):
        self.assertFalse(harness.evaluate(self.events()+'\nSCRIPT ERROR: unknown function',self.run,1)['passed'])

    def test_missing_attachment_or_physics_motion_fails(self):
        self.assertFalse(harness.evaluate(self.events(),self.run,1,attachment='probe')['passed'])
        self.assertFalse(harness.evaluate(self.events(),self.run,1,physics=True)['passed'])

    def test_prepare_only_is_explicitly_not_runtime_pass(self):
        model=self.compiled_model()
        report=self.work/'report.json'
        result=harness.main(['--game',str(self.game),'--prepare-only','--report',str(report),f'{model}=models/test/box.mdl'])
        self.assertEqual(result,0)
        data=json.loads(report.read_text())
        self.assertFalse(data['passed'])
        self.assertEqual(data['status'],'prepared')
        self.assertTrue(data['mod_removed'])


if __name__=='__main__': unittest.main()
