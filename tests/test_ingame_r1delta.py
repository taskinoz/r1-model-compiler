from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import ingame_test_r1delta as delta


class DeltaHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'test-output')
        self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name)
        self.game=self.work/'game'
        (self.game/'r1').mkdir(parents=True)

    def model(self):
        output=self.work/'box.mdl'
        compiler=Path(os.environ.get('R1C_COMPILER',ROOT/'build/r1studiomdl.exe')).resolve()
        subprocess.run([str(compiler),'-quiet','-o',str(output),str(ROOT/'examples/static_prop/box.qc')],check=True,capture_output=True,timeout=30)
        return output

    def test_staging_cleanup_preserves_other_addons(self):
        listing=self.game/'r1/addonlist.txt'
        listing.write_text('"AddonList"\n{\n"UserMod" "1"\n}\n')
        session=delta.prepare(self.game,[(self.model(),'models/test/box.mdl')])
        addon=Path(session['addon'])
        self.assertTrue((addon/'models/test/box.mdl').exists())
        cfg=Path(session['cfg']).read_text()
        self.assertIn('toggleconsole',cfg)
        self.assertLess(max(map(len,cfg.splitlines())),248)
        script=next((addon/'scripts/vscripts').glob('*.nut')).read_text()
        self.assertIn('WaittillGameStateOrHigher( eGameState.Playing )',script)
        self.assertIn('wait 12.0',script)
        self.assertNotIn('ServerCommand( "quit" )',script)
        self.assertFalse(session['passed'])
        listing.write_text(listing.read_text().replace('"UserMod" "1"','"UserMod" "0"\n"LaterMod" "1"'))
        delta.cleanup(session)
        self.assertFalse(addon.exists())
        self.assertIn('"UserMod" "0"',listing.read_text())
        self.assertIn('"LaterMod" "1"',listing.read_text())
        self.assertNotIn(session['run_id'],listing.read_text())

    def test_foreign_cfg_prevents_cleanup(self):
        session=delta.prepare(self.game,[(self.model(),'models/test/box.mdl')])
        Path(session['cfg']).write_text('user changes')
        with self.assertRaisesRegex(ValueError,'changed'): delta.cleanup(session)
        self.assertTrue(Path(session['addon']).exists())

    def test_checksum_failure_does_not_stage(self):
        model=self.model()
        model.with_suffix('.vvd').write_bytes(b'bad')
        with self.assertRaises(ValueError): delta.prepare(self.game,[(model,'models/test/box.mdl')])
        self.assertEqual(list((self.game/'r1').iterdir()),[])

    def test_server_pass_does_not_claim_visual_validation(self):
        run='a'*32
        session={'run_id':run,'models':[{'mount':'models/test/box.mdl'}], 'sequence':'','attachment':'','physics':False}
        events=['INIT','PRECACHE models/test/box.mdl','SPAWN 0 model=models/test/box.mdl origin=<0,0,0>','DONE','READY_FOR_VISUAL']+[f'POSE 0 sample={i} origin=<0,0,0>' for i in range(5)]
        text='\n'.join('[R1C:'+run+'] '+e for e in events)
        result=delta.collect(session,text)
        self.assertTrue(result['server_passed'])
        self.assertFalse(result['visual_passed'])
        self.assertFalse(result['passed'])
        self.assertFalse(delta.collect(session,text.replace(run,'b'*32))['server_passed'])
        self.assertFalse(delta.collect(session,text+'\nSCRIPT ERROR')['server_passed'])
        self.assertFalse(delta.collect(session,text.replace('POSE 0 sample=2','OTHER'))['server_passed'])
        self.assertFalse(delta.collect(session,text.replace('READY_FOR_VISUAL','OTHER'))['server_passed'])


if __name__=='__main__': unittest.main()
