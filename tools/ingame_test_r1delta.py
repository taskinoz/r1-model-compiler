"""R1Delta addon harness: prepare, collect fresh telemetry, and remove owned files.

Preparation is not a runtime pass. Launch R1Delta normally, run the printed exec
command in a local match, and collect the report. No launcher/auth changes.

Unattended: launch R1Delta with `-usemcp +mcp_start_http` and drive it with
tools/r1delta_mcp.py (map, exec, console log, screenshots) instead of the console.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import uuid

import ingame_test52 as common
import mdl52


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def delta_script(run_id, models, sequence='', attachment='', physics=False, preload=()):
    """preload: mount-only models (e.g. included animation models) precached first.
    R1Delta's precache of a model whose included models are not loaded yet fails
    with "has not been precached"; loading the includes first succeeds."""
    for model in preload:
        common.game_path(model)  # validated relative models/...mdl path; safe to embed
    text = common.script(run_id, models, sequence, attachment, physics)
    if preload:
        text = text.replace('foreach ( model in R1C_PATHS )',
                            ''.join('PrecacheModel( "%s" )\n' % m for m in preload) + 'foreach ( model in R1C_PATHS )', 1)
    text = text.replace('foreach ( model in R1C_PATHS )','R1C_Log( "BEGIN" )\nforeach ( model in R1C_PATHS )')
    text = text.replace('if ( hasPlayer ) ClientCommand( player, "screenshot" )','if ( hasPlayer ) ServerCommand( "screenshot" )')
    text = text.replace('    wait 2.0\n    local props', '    wait 1.0\n    local props')
    text = text.replace('origin + fwd *', 'origin + Vector(0,0,80) + fwd *')
    text = text.replace('ServerCommand( "quit" )', 'R1C_Log( "READY_FOR_VISUAL" ); ServerCommand( "condump" )')
    text = text.replace('    thread R1C_Run( player )', '    thread R1C_Grounded( player )')
    text += '''
function R1C_Grounded( player )
{
    WaittillGameStateOrHigher( eGameState.Playing )
    wait 12.0
    if ( !IsValid(player) ) { R1C_Log("FAIL player lost before scene"); return }
    ClientCommand(player, "setang 0 " + player.EyeAngles().y + " 0")
    wait 1.0
    R1C_Run(player)
}
function R1C_Attach()
{
    WaittillGameStateOrHigher( eGameState.Playing )
    while ( GetPlayerArray().len() == 0 ) wait 0.5
    R1C_OnSpawn(GetPlayerArray()[0])
}
thread R1C_Attach()
'''
    # Independent global namespace allows several diagnostic addons side by side.
    return 'if (IsLobby()) return\n' + text.replace('R1C_', 'R1C_'+run_id+'_')


def prepare(game, mounts, sequence='', attachment='', physics=False, extra=()):
    """extra: further mounts staged but not spawned (e.g. included animation models)."""
    game = Path(game).resolve(strict=True)
    root = game/'r1'
    if not root.is_dir():
        raise ValueError('expected the Titanfall install containing r1/')
    spawned = list(mounts)
    mounts = spawned + list(extra)
    if not spawned or len({t.lower() for _, t in mounts}) != len(mounts):
        raise ValueError('expected unique model mounts')
    run_id = uuid.uuid4().hex
    compiler = Path(__file__).resolve().parents[1]/'build/r1studiomdl.exe'
    script = delta_script(run_id, [t for _,t in spawned], sequence, attachment, physics, [t for _,t in extra])
    evidence = []
    for source,target in mounts:
        source = Path(source).resolve(strict=True)
        common.game_path(target)
        inspection = mdl52.inspect(source)
        files = [{'source':str(source.with_suffix(s)), 'mount':str(Path(target).with_suffix(s)).replace('\\','/'),
                  'sha256':digest(source.with_suffix(s))} for s in common.SUFFIXES if source.with_suffix(s).exists()]
        evidence.append({'source':str(source), 'mount':target, 'inspection':inspection, 'files':files})
    addon = root/'addons'/('R1CompilerTest.'+run_id)
    cfg = root/'cfg'/('r1c_'+run_id+'.cfg')
    listing = root/'addonlist.txt'
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (listing,cfg,addon,addon.parent,cfg.parent)):
        raise ValueError('refusing linked harness paths')
    listing_existed = listing.exists()
    original = listing.read_text(encoding='utf-8-sig') if listing.exists() else '"AddonList"\n{\n}\n'
    if not re.fullmatch(r'\s*"AddonList"\s*\{[^{}]*\}\s*', original, re.I):
        raise ValueError('unsupported addon list; refusing to rewrite it')
    addon.parent.mkdir(parents=True,exist_ok=True)
    addon.mkdir()
    (addon/common.OWNER).write_text(json.dumps({'run_id':run_id}),encoding='utf-8')
    try:
        for item in evidence:
            for f in item['files']:
                dest = addon/f['mount']
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(f['source'], dest)
                if digest(dest) != f['sha256']: raise ValueError('mounted file hash mismatch')
        (addon/'addoninfo.txt').write_text('"AddonInfo"\n{\n"addontitle" "R1 Compiler Test '+run_id+'"\n"addonversion" "1"\n"addonauthor" "r1-model-compiler"\n"addonContent_Script" "1"\n"addonContent_Model" "1"\n}\n',encoding='utf-8')
        # Explicit IncludeScript avoids startup races and console command truncation.
        scripts = addon/'scripts/vscripts'
        scripts.mkdir(parents=True)
        script_path = scripts/('r1c_'+run_id+'.nut')
        script_path.write_text(script,encoding='utf-8')
        cfg.parent.mkdir(parents=True,exist_ok=True)
        cfg.write_text('developer 1\nsv_cheats 1\nscript IncludeFile("r1c_'+run_id+'")\ntoggleconsole\n',encoding='utf-8')
        updated = original[:original.rfind('}')]+'"'+addon.name+'" "1"\n'+original[original.rfind('}'):]
        listing.write_text(updated,encoding='utf-8')
        staged_only = [e for e in evidence if e['mount'] in {t for _,t in extra}]
        evidence = [e for e in evidence if e not in staged_only]
        return {'run_id':run_id,'game':str(game),'addon':str(addon),'cfg':str(cfg),'mounted_only':staged_only,
                'command':'exec '+cfg.stem,'sequence':sequence,'attachment':attachment,'physics':physics,
                'prepared_at_ns':time.time_ns(),'models':evidence,'script_sha256':digest(script_path),'cfg_sha256':digest(cfg),
                'compiler_sha256':digest(compiler) if compiler.exists() else None,
                'harness_sha256':digest(__file__),'reader_sha256':digest(mdl52.__file__),
                'common_harness_sha256':digest(common.__file__),
                'addonlist_created':not listing_existed,
                'passed':False,'visual_passed':False,'status':'prepared'}
    except BaseException:
        common.safe_cleanup(addon,addon.parent,run_id)
        if cfg.exists(): cfg.unlink()
        if listing.exists() and listing.read_text(encoding='utf-8-sig') == locals().get('updated'):
            if listing_existed: listing.write_text(original,encoding='utf-8')
            else: listing.unlink()
        raise


def collect(session, text):
    marker = '[R1C:'+session['run_id']+'] BEGIN'
    lines = text.splitlines(keepends=True)
    starts = [i for i,line in enumerate(lines) if marker in line]
    if starts: text = ''.join(lines[starts[-1]:])
    result = common.evaluate(text,session['run_id'],len(session['models']),
                             sequence=session['sequence'],attachment=session['attachment'],
                             physics=session['physics'],paths=[m['mount'] for m in session['models']])
    if not starts: result['issues'].append('run BEGIN boundary missing')
    if len(starts) > 1: result['issues'].append('run ID reused; prepare a fresh session')
    if 'READY_FOR_VISUAL' not in result['events']:
        result['issues'].append('scene did not finish screenshot request')
    for index in range(len(session['models'])):
        for sample in range(5):
            if not any(e.startswith(f'POSE {index} sample={sample} ') for e in result['events']):
                result['issues'].append(f'model {index} missing pose sample {sample}')
    result.pop('passed')
    result['server_passed'] = not result['issues']
    result['visual_passed'] = False
    result['passed'] = False
    result['coverage'] = 'server smoke probes only; visual inspection is required separately'
    result['log_sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return result


def cleanup(session):
    run_id = session['run_id']
    if not re.fullmatch('[a-f0-9]{32}', run_id): raise ValueError('invalid session ID')
    root = Path(session['game']).resolve()/'r1'
    addon = root/'addons'/('R1CompilerTest.'+run_id)
    cfg = root/'cfg'/('r1c_'+run_id+'.cfg')
    if str(addon) != session['addon'] or str(cfg) != session['cfg']:
        raise ValueError('session ownership path mismatch')
    listing = root/'addonlist.txt'
    if listing.is_symlink(): raise ValueError('linked addon list')
    text = listing.read_text(encoding='utf-8-sig') if listing.exists() else ''
    pattern = r'(?m)^[ \t]*"'+re.escape(addon.name)+r'"\s+"[01]"[ \t]*\n?'  # R1Delta indents entries with tabs
    updated,n = re.subn(pattern,'',text)
    if n != 1: raise ValueError('owned addon entry missing or ambiguous')
    if cfg.is_symlink() or digest(cfg) != session['cfg_sha256']:
        raise ValueError('owned cfg changed; refusing removal')
    common.safe_cleanup(addon,addon.parent,run_id)
    cfg.unlink()
    listing.write_text(updated,encoding='utf-8')
    # Keep the small addon list: other tools may now rely on its existence.


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action',required=True)
    stage = sub.add_parser('prepare')
    stage.add_argument('--game',type=Path,required=True)
    stage.add_argument('--session',type=Path,required=True)
    stage.add_argument('--sequence',default='')
    stage.add_argument('--attachment',default='')
    stage.add_argument('--physics',action='store_true')
    stage.add_argument('--mount-only',action='append',default=[],help='also stage local.mdl=models/... without spawning it; repeatable')
    stage.add_argument('models',nargs='+')
    read = sub.add_parser('collect')
    read.add_argument('--session',type=Path,required=True)
    read.add_argument('--log',type=Path,help='Explicit console dump; otherwise watch fresh run-specific condump output')
    read.add_argument('--timeout',type=float,default=90)
    read.add_argument('--report',type=Path,required=True)
    clean = sub.add_parser('cleanup')
    clean.add_argument('--session',type=Path,required=True)
    a = p.parse_args(argv)
    if a.action == 'prepare':
        if a.session.exists(): p.error('session already exists')
        session = prepare(a.game,[common.parse_mount(m) for m in a.models],a.sequence,a.attachment,a.physics,
                          [common.parse_mount(m) for m in a.mount_only])
        a.session.parent.mkdir(parents=True,exist_ok=True)
        a.session.write_text(json.dumps(session,indent=2),encoding='utf-8')
        print('In a local R1Delta match: '+session['command'])
        print('If the addon is not mounted yet, restart the match once, then repeat that command.')
        print('The cfg closes the console. Scene waits until Playing plus 12 seconds; keep the game open.')
        return 0
    session = json.loads(a.session.read_text(encoding='utf-8'))
    if a.action == 'cleanup':
        cleanup(session)
        print('Removed owned addon and cfg; preserved console dumps and screenshots.')
        return 0
    if not 0 <= a.timeout <= 3600: p.error('timeout must be between 0 and 3600 seconds')
    path = a.log or Path(session['game'])/'r1'/('r1c_'+session['run_id']+'.log')
    deadline = time.monotonic()+a.timeout
    while True:
        if not a.log:
            candidates = [f for f in (Path(session['game'])/'r1').glob('condump*.txt') if f.stat().st_mtime_ns > session['prepared_at_ns']]
            matches = [f for f in candidates if '[R1C:'+session['run_id']+'] BEGIN' in f.read_text(encoding='utf-8',errors='replace')]
            if matches: path = max(matches,key=lambda f:f.stat().st_mtime_ns)
        text = path.read_text(encoding='utf-8',errors='replace') if path.exists() else ''
        result = collect(session,text)
        if result['server_passed'] or time.monotonic() >= deadline or a.log: break
        time.sleep(0.5)
    screenshots = []
    for directory in (Path(session['game'])/'r1/screenshots',Path(session['game'])/'screenshots'):
        if directory.is_dir():
            for capture in directory.iterdir():
                if capture.is_file() and capture.suffix.lower() in ('.tga','.jpg','.png') and capture.stat().st_mtime_ns > session['prepared_at_ns']:
                    screenshots.append({'path':str(capture),'sha256':digest(capture),'reviewed':False})
    report = {**session,**result,'status':'collected','log':str(path),'screenshots':screenshots,
              'collector_sha256':digest(__file__),'raw_log_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest()}
    a.report.parent.mkdir(parents=True,exist_ok=True)
    snapshot = a.report.with_suffix('.console.txt')
    snapshot.write_text(text,encoding='utf-8')
    report['console_snapshot'] = str(snapshot)
    a.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('server_passed','visual_passed','passed','issues')}))
    return 0 if result['server_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
