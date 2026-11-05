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
        self.assertLess(cfg.index('sv_cheats 1'),cfg.index('script IncludeFile'))
        self.assertIn('developer 1',cfg)
        self.assertNotIn('update_addon_paths',cfg)
        self.assertLess(max(map(len,cfg.splitlines())),248)
        script=next((addon/'scripts/vscripts').glob('*.nut')).read_text()
        self.assertIn('WaittillGameStateOrHigher( eGameState.Playing )',script)
        self.assertIn('wait 12.0',script)
        self.assertIn('ServerCommand( "condump" )',script)
        self.assertIn('ServerCommand( "screenshot" )',script)
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

    def test_mount_only_models_are_precached_first_and_not_spawned(self):
        model=self.model()
        anims=self.work/'anims.mdl'
        for suffix in ('.mdl','.vvd','.dx11.vtx','.phy'):
            if model.with_suffix(suffix).exists():
                anims.with_suffix(suffix).write_bytes(model.with_suffix(suffix).read_bytes())
        session=delta.prepare(self.game,[(model,'models/test/box.mdl')],extra=[(anims,'models/test/anims.mdl')])
        script=next((Path(session['addon'])/'scripts/vscripts').glob('r1c_*.nut')).read_text()
        self.assertLess(script.index('PrecacheModel( "models/test/anims.mdl" )'),script.index('foreach ( model in'))
        self.assertEqual([m['mount'] for m in session['models']],['models/test/box.mdl'])
        self.assertEqual([m['mount'] for m in session['mounted_only']],['models/test/anims.mdl'])
        self.assertTrue((Path(session['addon'])/'models/test/anims.mdl').exists())
        delta.cleanup(session)

    def test_cleanup_accepts_r1delta_tab_indented_addon_list(self):
        session=delta.prepare(self.game,[(self.model(),'models/test/box.mdl')])
        listing=self.game/'r1/addonlist.txt'
        name=Path(session['addon']).name
        listing.write_text('"AddonList"\n{\n\t"Other"\t\t"1"\n\t"%s"\t\t"1"\n}\n'%name,encoding='utf-8')
        delta.cleanup(session)
        self.assertEqual(listing.read_text(),'"AddonList"\n{\n\t"Other"\t\t"1"\n}\n')

    def test_mcp_client_negotiates_protocol_and_reads_event_streams(self):
        import http.server, threading
        import r1delta_mcp
        seen=[]

        class Fake(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append((body.get('method'),self.headers.get('MCP-Protocol-Version'),self.headers.get('Mcp-Session-Id')))
                if body.get('method')=='initialize':
                    reply={'jsonrpc':'2.0','id':body['id'],'result':{'protocolVersion':'2025-06-18','capabilities':{}}}
                elif body.get('method')=='tools/call':
                    reply={'jsonrpc':'2.0','id':body['id'],'result':{'content':[{'type':'text','text':'Game State:\n  In Game: Yes'}]}}
                else:
                    self.send_response(202); self.end_headers(); return
                data=('event: message\ndata: '+json.dumps(reply)+'\n\n').encode()
                self.send_response(200)
                self.send_header('Content-Type','text/event-stream')
                self.send_header('Mcp-Session-Id','s1')
                self.send_header('Content-Length',str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server=http.server.HTTPServer(('127.0.0.1',0),Fake)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.shutdown)
        client=r1delta_mcp.R1DeltaMCP(port=server.server_address[1])
        client.connect()
        self.assertIn('In Game: Yes',client.state())
        self.assertEqual(seen[0],('initialize',None,None))  # R1Delta rejects an unnegotiated version header
        self.assertEqual(seen[-1],('tools/call','2025-06-18','s1'))

    def test_compare_tool_measures_orientation_not_euler_angles(self):
        import r1delta_compare as cmp
        # pitch -90: only roll + yaw matters, so (yaw 135, roll 90) and (yaw 225, roll 0)
        # are one orientation with different Euler angles
        a=cmp.angle_matrix(-90,135,90); b=cmp.angle_matrix(-90,225,0)
        self.assertLess(max(abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb)),1e-9)
        c=cmp.angle_matrix(-90,135,0)
        self.assertGreater(max(abs(x-y) for ra,rc in zip(a,c) for x,y in zip(ra,rc)),0.5)
        self.assertEqual(cmp.vec('(vector : (1.5, -2, 3e-05))'),(1.5,-2.0,3e-05))

    def test_server_pass_does_not_claim_visual_validation(self):
        run='a'*32
        session={'run_id':run,'models':[{'mount':'models/test/box.mdl'}], 'sequence':'','attachment':'','physics':False}
        events=['BEGIN','INIT','PRECACHE models/test/box.mdl','SPAWN 0 model=models/test/box.mdl origin=<0,0,0>','DONE','READY_FOR_VISUAL']+[f'POSE 0 sample={i} origin=<0,0,0>' for i in range(5)]
        text='\n'.join('[R1C:'+run+'] '+e for e in events)
        result=delta.collect(session,text)
        self.assertTrue(result['server_passed'])
        self.assertFalse(result['visual_passed'])
        self.assertFalse(result['passed'])
        self.assertFalse(delta.collect(session,text.replace(run,'b'*32))['server_passed'])
        self.assertFalse(delta.collect(session,text+'\nSCRIPT ERROR')['server_passed'])
        self.assertFalse(delta.collect(session,text.replace('POSE 0 sample=2','OTHER'))['server_passed'])
        self.assertFalse(delta.collect(session,text.replace('READY_FOR_VISUAL','OTHER'))['server_passed'])
        self.assertFalse(delta.collect(session,text.replace('BEGIN','OTHER'))['server_passed'])
        self.assertFalse(delta.collect(session,text+'\n[R1C:'+run+'] BEGIN')['server_passed'])
        self.assertTrue(delta.collect(session,'SCRIPT ERROR before the run\n'+text)['server_passed'])


if __name__=='__main__': unittest.main()
