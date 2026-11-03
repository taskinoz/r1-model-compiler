"""Isolated Titanfall Online (TFORevive) native-v52 model smoke-test harness.

Mounts a temporary mod; never edits core mods. Runtime reports are fail-closed:
preparing files or reaching a menu is not a model-validation pass.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import time
import uuid

import mdl52

SUFFIXES = ('.mdl', '.vvd', '.dx11.vtx', '.vvc', '.phy')
OWNER = '.r1c-harness-owner.json'

SERVER = r'''
R1C_PATHS <- %MODELS%
R1C_STARTED <- false
function R1C_Log( message ) { printl( "[R1C:%RUN%] " + message ) }
function R1C_OnSpawn( player )
{
    if ( R1C_STARTED ) return
    R1C_STARTED = true
    thread R1C_Run( player )
}
function R1C_Run( player )
{
    wait 2.0
    local props = []
    local starts = []
    local hasPlayer = IsValid( player )
    local origin = hasPlayer ? player.GetOrigin() : Vector(0,0,128)
    if ( !hasPlayer )
    {
        local points = GetEntArrayByClass_Expensive( "info_spawnpoint_titan" )
        if ( points.len() == 0 ) points = GetEntArrayByClass_Expensive( "info_spawnpoint_human" )
        if ( points.len() == 0 ) { R1C_Log( "FAIL no map spawn point" ); ServerCommand( "quit" ); return }
        origin = points[0].GetOrigin() + Vector(0,0,16)
    }
    local yaw = hasPlayer ? player.EyeAngles().y : 0
    local ignore = []
    if ( hasPlayer ) ignore.append( player )
    local fwd = Vector( 0, yaw, 0 ).AnglesToForward()
    local right = Vector( 0, yaw, 0 ).AnglesToRight()
    for ( local i = 0; i < R1C_PATHS.len(); i++ )
    {
        local model = R1C_PATHS[i]
        local pos = origin + fwd * (hasPlayer ? 180 : 0) + right * ( (i - (R1C_PATHS.len()-1)*0.5)*100 - (hasPlayer ? 70 : 0) )
        local prop
        if ( %PHYSICS% )
        {
            prop = CreateEntity( "prop_physics" )
            prop.kv.model = model
            prop.SetOrigin( pos + Vector( 0, 0, 120 ) )
            prop.SetAngles( Vector( 0, yaw+180, 0 ) )
            DispatchSpawn( prop )
        }
        else
            prop = CreatePropDynamic( model, pos, Vector( 0, yaw+180, 0 ), 6 )
        if ( !IsValid( prop ) )
        {
            R1C_Log( "FAIL spawn " + i )
            continue
        }
        props.append( prop )
        starts.append( prop.GetOrigin() )
        R1C_Log( "SPAWN " + i + " model=" + prop.GetModelName() + " origin=" + prop.GetOrigin() )
        if ( !%PHYSICS% && "%SEQ%" != "" )
        {
            local seq = prop.LookupSequence( "%SEQ%" )
            if ( seq < 0 ) R1C_Log( "FAIL sequence " + i )
            else
            {
                prop.Anim_Play( "%SEQ%" )
                R1C_Log( "ANIM " + i + " sequence=%SEQ% index=" + seq )
            }
        }
        local tr = TraceLine( prop.GetOrigin() + Vector(0,0,prop.GetBoundingMaxs().z+4), prop.GetOrigin() + Vector(0,0,prop.GetBoundingMins().z-4), ignore, TRACE_MASK_SHOT, TRACE_COLLISION_GROUP_NONE )
        R1C_Log( "TRACE " + i + " hit=" + ( tr.hitEnt == prop ) + " z=" + (tr.endPos.z-prop.GetOrigin().z) )
    }
    for ( local sample = 0; sample < 5; sample++ )
    {
        wait 0.35
        for ( local i = 0; i < props.len(); i++ )
        {
            local prop = props[i]
            if ( !IsValid( prop ) ) { R1C_Log( "FAIL lost " + i ); continue }
            R1C_Log( "POSE " + i + " sample=" + sample + " origin=" + prop.GetOrigin() )
            if ( "%ATTACH%" != "" )
            {
                local a = prop.LookupAttachment( "%ATTACH%" )
                if ( a <= 0 ) R1C_Log( "FAIL attachment " + i )
                else R1C_Log( "ATTACH " + i + " sample=" + sample + " pos=" + prop.GetAttachmentOrigin(a) + " ang=" + prop.GetAttachmentAngles(a) )
            }
        }
    }
    if ( %PHYSICS% )
        for ( local i = 0; i < props.len(); i++ )
            R1C_Log( "PHYSICS " + i + " drop=" + (starts[i].z-props[i].GetOrigin().z) )
    R1C_Log( "DONE" )
    if ( hasPlayer ) ClientCommand( player, "screenshot" )
    wait 2.0
    ServerCommand( "quit" )
}
foreach ( model in R1C_PATHS )
{
    PrecacheModel( model )
    R1C_Log( "PRECACHE " + model )
}
AddCallback_OnPlayerRespawned( R1C_OnSpawn )
R1C_Log( "INIT" )
function R1C_Headless()
{
    FlagWait( "EntitiesDidLoad" )
    R1C_STARTED = true
    R1C_Run( null )
}
if ( %DEDICATED% ) thread R1C_Headless()
'''


def game_path(value):
    value=value.replace('\\','/')
    p=PurePosixPath(value)
    if p.is_absolute() or any(part in ('..','.') for part in p.parts) or ':' in value or not value.startswith('models/') or p.suffix.lower()!='.mdl':
        raise ValueError('mount must be a relative models/.../*.mdl path')
    if not re.fullmatch(r'[A-Za-z0-9_./-]+',value):
        raise ValueError('unsupported character in mounted model path')
    return value


def parse_mount(value):
    source,sep,target=value.partition('=')
    if not sep:
        raise ValueError('model argument must be local.mdl=models/test/name.mdl')
    path=Path(source).resolve(strict=True)
    if path.suffix.lower()!='.mdl':
        raise ValueError('source must be a .mdl')
    return path,game_path(target)


def script(run_id,models,sequence,attachment,physics,dedicated=False):
    if not re.fullmatch(r'[a-f0-9]{32}',run_id):
        raise ValueError('invalid run ID')
    for label,value in [('sequence',sequence),('attachment',attachment)]:
        if not re.fullmatch(r'[A-Za-z0-9_./-]*',value):
            raise ValueError(f'invalid {label}')
    return (SERVER.replace('%MODELS%',json.dumps(models)).replace('%RUN%',run_id)
            .replace('%SEQ%',sequence).replace('%ATTACH%',attachment)
            .replace('%PHYSICS%','true' if physics else 'false').replace('%DEDICATED%','true' if dedicated else 'false'))


def safe_cleanup(mod,mods,run_id):
    mod=Path(mod)
    mods=Path(mods).resolve()
    if mod.is_symlink() or (hasattr(mod,'is_junction') and mod.is_junction()):
        raise ValueError('refusing linked harness directory')
    if mod.resolve().parent!=mods:
        raise ValueError('cleanup target outside Mods')
    marker=json.loads((mod/OWNER).read_text(encoding='utf-8'))
    if marker.get('run_id')!=run_id:
        raise ValueError('harness ownership mismatch')
    for parent,dirs,files in os.walk(mod,followlinks=False):
        for entry in dirs+files:
            path=Path(parent)/entry
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
                raise ValueError('refusing cleanup through a linked child')
    shutil.rmtree(mod)


def prepare(game,mounts,run_id,sequence='idle',attachment='',physics=False,dedicated=False):
    if not re.fullmatch(r'[a-f0-9]{32}',run_id):
        raise ValueError('invalid run ID')
    mods=game/'Mods'
    base=mods/'TFORevive.Core/mod/scripts/vscripts/_mapspawn.nut'
    if not (game/'Bin/TFO.exe').is_file() or not base.is_file():
        raise ValueError('expected a TFORevive install with Bin/TFO.exe and TFORevive.Core scripts')
    if len({target.lower() for _,target in mounts})!=len(mounts):
        raise ValueError('duplicate model mount')
    # Validate everything before writing into the game directory.
    evidence=[]
    for source,target in mounts:
        info=mdl52.inspect(source)
        companions=[]
        for suffix in SUFFIXES:
            path=source.with_suffix(suffix)
            if path.exists():
                companions.append((path,Path(target).with_suffix(suffix)))
        evidence.append({'source':str(source),'mount':target,'inspection':info,
                         'files':[{'source':str(p),'mount':str(t).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p,t in companions]})
    mod=mods/f'R1CompilerTest.{run_id}'
    mod.mkdir()
    (mod/OWNER).write_text(json.dumps({'run_id':run_id}),encoding='utf-8')
    try:
        manifest={'Name':f'R1CompilerTest.{run_id}','Description':'Temporary native v52 model validation',
                  'Authors':['r1-model-compiler'],'Version':'1','LoadPriority':1000,'RequiredOnClient':False}
        (mod/'mod.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        tree=mod/'mod'
        for item in evidence:
            for file in item['files']:
                destination=tree/file['mount']
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(file['source'],destination)
                if hashlib.sha256(destination.read_bytes()).hexdigest()!=file['sha256']:
                    raise ValueError('mounted companion hash mismatch')
        scripts=tree/'scripts/vscripts'
        scripts.mkdir(parents=True,exist_ok=True)
        base_bytes=base.read_bytes()
        # The installed game script is used only in this temporary local override.
        # Proprietary script contents are never included in the repository/report.
        (scripts/'_mapspawn.nut').write_bytes(base_bytes+b'\nIncludeScript( "r1c_model_test", getroottable() )\n')
        (scripts/'r1c_model_test.nut').write_text(script(run_id,[t for _,t in mounts],sequence,attachment,physics,dedicated),encoding='utf-8')
        return mod,evidence,hashlib.sha256(base_bytes).hexdigest()
    except BaseException:
        safe_cleanup(mod,mods,run_id)
        raise


def evaluate(text,run_id,expected,sequence='idle',attachment='',physics=False,paths=None,required_traces=(),min_attachment_displacement=0.):
    marker=f'[R1C:{run_id}] '
    lines=[line.split(marker,1)[1].strip() for line in text.splitlines() if marker in line]
    issues=[]
    attachment_displacements={}
    if 'INIT' not in lines: issues.append('harness script did not initialize')
    if 'DONE' not in lines: issues.append('harness did not complete')
    for i in range(expected):
        if not any(l.startswith(f'SPAWN {i} ') for l in lines): issues.append(f'model {i} did not spawn')
        if paths is not None:
            if f'PRECACHE {paths[i]}' not in lines: issues.append(f'model {i} was not precached')
            if not any(l.startswith(f'SPAWN {i} model={paths[i]} ') for l in lines): issues.append(f'model {i} resolved to the wrong model path')
        if sequence and not physics and not any(l.startswith(f'ANIM {i} ') for l in lines): issues.append(f'model {i} did not play requested sequence')
        if not any(l.startswith(f'POSE {i} sample=4 ') for l in lines): issues.append(f'model {i} missing final pose sample')
        if attachment and not any(l.startswith(f'ATTACH {i} sample=4 ') for l in lines): issues.append(f'model {i} missing attachment sample')
        if physics:
            drops=[float(m[1]) for l in lines if (m:=re.fullmatch(rf'PHYSICS {i} drop=([-+0-9.eE]+)',l))]
            if not drops or drops[0]<=1: issues.append(f'model {i} did not demonstrate a physics drop')
    for index in required_traces:
        if not any(l.startswith(f'TRACE {index} hit=true ') for l in lines):
            issues.append(f'model {index} required collision trace did not hit')
    if attachment:
        for i in range(expected):
            points=[]
            for line in lines:
                if line.startswith(f'ATTACH {i} ') and ' pos=' in line:
                    vector=line.split(' pos=',1)[1].split(' ang=',1)[0]
                    values=re.findall(r'[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?',vector)
                    if len(values)==3:
                        point=tuple(map(float,values))
                        if all(math.isfinite(v) for v in point): points.append(point)
            displacement=max((math.dist(a,b) for a in points for b in points),default=0.)
            attachment_displacements[str(i)]=displacement
            if min_attachment_displacement>0 and displacement<min_attachment_displacement:
                issues.append(f'model {i} attachment did not demonstrate required motion')
    issues.extend(l for l in lines if l.startswith('FAIL '))
    for pattern in ('SCRIPT ERROR','AN ERROR HAS OCCURRED','Error loading model','checksum mismatch','wrong model version'):
        if pattern.lower() in text.lower(): issues.append('runtime diagnostic: '+pattern)
    return {'passed':not issues,'issues':issues,'events':lines,'attachment_displacements':attachment_displacements}


def launch_command(game,map_name,dedicated=False):
    if not re.fullmatch('[A-Za-z0-9_]+',map_name):
        raise ValueError('invalid map')
    if dedicated:
        command=[str(game/'Bin/tfods.exe'),'-noauth','-dedicated']
    else:
        # TFO.exe requires this argument even when the SDK's -noauth mode is used.
        # This literal is not a credential and is never replaced with an account token.
        command=[str(game/'Bin/TFO.exe'),'--authToken','r1c-local-noauth','-noauth',
                 '-novid','-windowed','-w','1280','-h','720']
    return command+['+sv_lan','1','+sv_cheats','1','+developer','1','+map',map_name]


def read_runtime_log(path,original_size,original_prefix):
    if not path.exists(): return ''
    data=path.read_bytes()
    offset=original_size if len(data)>=original_size and data[:len(original_prefix)]==original_prefix else 0
    return data[offset:].decode('utf-8',errors='replace')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models',nargs='+')
    parser.add_argument('--game',type=Path,default=os.environ.get('TITANFALL_ONLINE_DIR'))
    parser.add_argument('--map',default='mp_nexus')
    parser.add_argument('--sequence',default='idle')
    parser.add_argument('--attachment',default='')
    parser.add_argument('--min-attachment-displacement',type=float,default=0.,help='minimum sampled world-space displacement in inches')
    parser.add_argument('--require-trace',type=int,action='append',default=[],help='require the trace for this model index to hit its prop; repeatable')
    parser.add_argument('--physics',action='store_true')
    parser.add_argument('--dedicated',action='store_true',help='server-only loading/animation/physics checks; no rendering claim')
    parser.add_argument('--timeout',type=float,default=150)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true',help='prepare and inspect temporary files without launching; not a runtime pass')
    parser.add_argument('--keep-mod',action='store_true',help='keep the owned temporary mod for debugging')
    parser.add_argument('--cwd-bin',action='store_true',help='launch with Bin as the working directory for older TFO builds')
    parser.add_argument('--compiler',type=Path,default=Path(os.environ.get('R1C_COMPILER',Path(__file__).resolve().parents[1]/'build/r1studiomdl.exe')),help='compiler binary recorded for provenance; inputs are not recompiled')
    args=parser.parse_args(argv)
    if args.game is None: parser.error('--game or TITANFALL_ONLINE_DIR is required')
    if not re.fullmatch('[A-Za-z0-9_]+',args.map): parser.error('invalid map')
    if not 1<=args.timeout<=600: parser.error('timeout must be 1..600 seconds')
    if args.min_attachment_displacement<0 or not math.isfinite(args.min_attachment_displacement): parser.error('invalid displacement threshold')
    if args.min_attachment_displacement>0 and not args.attachment: parser.error('motion threshold requires --attachment')
    if any(i<0 or i>=len(args.models) for i in args.require_trace): parser.error('trace index outside model list')
    game=args.game.resolve(strict=True)
    run_id=uuid.uuid4().hex
    args.report.parent.mkdir(parents=True,exist_ok=True)
    report={'run_id':run_id,'engine':'TFORevive','date':datetime.now(timezone.utc).isoformat(),
            'game':str(game),'coverage':'server-only' if args.dedicated else 'client/listen-server','passed':False,'status':'preparing','issues':[],
            'test_options':{'map':args.map,'sequence':args.sequence,'attachment':args.attachment,'physics':args.physics,'cwd_bin':args.cwd_bin,'dedicated':args.dedicated,'required_traces':args.require_trace,'min_attachment_displacement':args.min_attachment_displacement}}
    if args.compiler.is_file():
        report['compiler']={'path':str(args.compiler.resolve()),'sha256':hashlib.sha256(args.compiler.read_bytes()).hexdigest(),
                            'note':'Binary available at run time; this harness does not recompile inputs.'}
    mod=None
    process=None
    try:
        mounts=[parse_mount(m) for m in args.models]
        if not args.prepare_only and os.name=='nt':
            for image in ('TFO.exe','tfods.exe'):
                tasks=subprocess.check_output(['tasklist','/FO','CSV','/NH','/FI','IMAGENAME eq '+image],text=True)
                if any(row and row[0].lower()==image.lower() for row in csv.reader(tasks.splitlines())):
                    raise ValueError(image+' is already running; close it before starting an isolated harness run')
        mod,evidence,base_hash=prepare(game,mounts,run_id,args.sequence,args.attachment,args.physics,args.dedicated)
        report.update(models=evidence,mod=str(mod),base_mapspawn_sha256=base_hash,
                      harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      reader_sha256=hashlib.sha256(Path(mdl52.__file__).read_bytes()).hexdigest())
        if args.prepare_only:
            report.update(status='prepared',issues=['prepare-only: game was not launched'])
            return 0
        logs=game/('Logs/tforevive_dedi.log' if args.dedicated else 'Logs/tforevive.log')
        previous_log=logs.read_bytes() if logs.exists() else b''
        offset=len(previous_log)
        prefix=previous_log[:256]
        command=launch_command(game,args.map,args.dedicated)
        report['command']=command
        report['executable_sha256']=hashlib.sha256(Path(command[0]).read_bytes()).hexdigest()
        output=args.report.with_suffix('.process.log')
        screenshots={}
        screenshot_roots=[game/'Local/screenshots',game/'screenshots',game/'Data/screenshots']
        for directory in screenshot_roots:
            if directory.exists():
                screenshots.update({str(p):p.stat().st_mtime_ns for p in directory.glob('*') if p.is_file()})
        with output.open('wb') as stream:
            process=subprocess.Popen(command,cwd=game/'Bin' if args.cwd_bin else game,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if args.dedicated and os.name=='nt' else 0)
            report.update(status='running',pid=process.pid)
            deadline=time.monotonic()+args.timeout
            text=''
            while time.monotonic()<deadline:
                if logs.exists():
                    text=read_runtime_log(logs,offset,prefix)
                    if 'SCRIPT ERROR' in text and 'r1c_model_test.nut' in text:
                        break
                    if f'[R1C:{run_id}] DONE' in text:
                        time.sleep(3)
                        break
                if process.poll() is not None: break
                time.sleep(1)
            if logs.exists():
                text=read_runtime_log(logs,offset,prefix)
            result=evaluate(text,run_id,len(mounts),args.sequence,args.attachment,args.physics,[t for _,t in mounts],args.require_trace,args.min_attachment_displacement)
            report.update(result,status='passed' if result['passed'] else 'failed')
            # Keep only run-specific telemetry and redacted diagnostic context.
            diagnostic=re.sub(r'(?i)(--authToken\s+|Bearer\s+)[^\s"\r\n]+',r'\1<redacted>',text)
            args.report.with_suffix('.game.log').write_text(diagnostic,encoding='utf-8')
            if process.poll() is None:
                report['terminated_by_harness']=True
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            report['exit_code']=process.returncode
            if process.returncode not in (0,None) and not report.get('terminated_by_harness'):
                report['issues'].append(f'game exited with code 0x{process.returncode & 0xffffffff:08X}')
                report['passed']=False
                report['status']='failed'
            report['screenshots']=[]
            for directory in screenshot_roots:
                if directory.exists():
                    for path in directory.glob('*'):
                        if path.is_file() and path.suffix.lower() in ('.tga','.png','.jpg') and path.stat().st_mtime_ns!=screenshots.get(str(path)):
                            report['screenshots'].append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            return 0 if report['passed'] else 1
    except Exception as error:
        report.update(status='error',issues=[str(error)])
        return 1
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        if mod is not None and not args.keep_mod:
            try:
                safe_cleanup(mod,game/'Mods',run_id)
                report['mod_removed']=True
            except Exception as error:
                report['passed']=False
                report['status']='error'
                report['cleanup_error']=str(error)
        args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'status':report['status'],'passed':report['passed'],'report':str(args.report),'issues':report['issues']},indent=2))
        if 'cleanup_error' in report:
            raise SystemExit(1)


if __name__=='__main__':
    raise SystemExit(main())
