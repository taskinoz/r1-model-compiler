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
// Offline TFORevive sessions have no loadout data, so the core script returns a
// null pilot settings file and the local player never spawns. Fall back to a
// stock settings file only when the original lookup fails. R1Delta has no such
// script function and needs no fallback.
if ( "GetPlayerPilotSetFile" in getroottable() )
{
    ::R1C_OriginalPilotSetFile <- GetPlayerPilotSetFile
    ::GetPlayerPilotSetFile <- function( self )
    {
        local file = null
        try { file = R1C_OriginalPilotSetFile( self ) } catch ( e ) {}
        if ( file == null )
            file = "pilot_male_fastest"
        return file
    }
}
function R1C_OnSpawn( player )
{
    if ( R1C_STARTED ) return
    R1C_STARTED = true
    thread R1C_Run( player )
}
function R1C_Run( player )
{
    wait 2.0
    // Classic MP spawns the player into a dropship; wait until they are free.
    for ( local t = 0; IsValid( player ) && player.GetParent() != null && t < 60; t++ )
        wait 1.0
    if ( IsValid( player ) ) { R1C_Log( "PLAYER parent=" + player.GetParent() + " origin=" + player.GetOrigin() ); wait 2.0 }
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
        if ( hasPlayer )
        {
            // Rest each prop on the ground below its slot so it is not buried in sloping terrain.
            local ground = TraceLine( pos + Vector(0,0,96), pos - Vector(0,0,512), ignore, TRACE_MASK_SOLID, TRACE_COLLISION_GROUP_NONE )
            if ( ground.fraction < 1.0 ) pos = ground.endPos
        }
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
    if ( hasPlayer && IsValid( player ) )
    {
        // Level the camera on the props, then let the harness capture the window.
        player.SetVelocity( Vector( 0, 0, 0 ) )
        player.SetAngles( Vector( 8, yaw, 0 ) )
        wait 1.5
        R1C_Log( "VIEW 0" )
        wait 2.5
    }
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


def internal_name(path):
    """The model name stored in the MDL: the extended header's full name, else the
    64-byte header name (which retail truncates to 62 characters)."""
    data=Path(path).read_bytes()
    if len(data)<0x198 or data[:4]!=b'IDST':
        raise ValueError(f'{path}: not an MDL')
    hdr2=int.from_bytes(data[0x190:0x194],'little')
    if 0x198<=hdr2<=len(data)-0x18:
        offset=hdr2+int.from_bytes(data[hdr2+0x14:hdr2+0x18],'little',signed=True)
        if hdr2<offset<len(data) and b'\0' in data[offset:]:
            name=data[offset:data.index(b'\0',offset)].decode('utf-8','replace')
            if name: return name.replace('\\','/')
    return data[12:76].split(b'\0',1)[0].decode('utf-8','replace').replace('\\','/')


def parse_mount(value):
    source,sep,target=value.partition('=')
    if not sep:
        raise ValueError('model argument must be local.mdl=models/test/name.mdl')
    path=Path(source).resolve(strict=True)
    if path.suffix.lower()!='.mdl':
        raise ValueError('source must be a .mdl')
    target=game_path(target)
    # The client finds a model's VVD/VTX through the name stored in the MDL, not
    # the path it was loaded from. A model mounted elsewhere still loads, animates
    # and collides on the server, but the client draws nothing.
    expected='models/'+internal_name(path)
    if target.lower()!=expected.lower():
        raise ValueError(f'{path.name} must be mounted at its $modelname path {expected}, not {target}')
    return path,target


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


def prepare(game,mounts,run_id,sequence='idle',attachment='',physics=False,dedicated=False,extra=()):
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
        (scripts/'r1c_model_test.nut').write_text(script(run_id,[t for _,t in mounts if (_,t) not in extra],sequence,attachment,physics,dedicated),encoding='utf-8')
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


# The graphics driver sometimes crashes TFO while it starts: a stack overflow in
# nvwgf2umx.dll (0xC00000FD) or an access violation in d3d11.dll (0xC0000005).
STARTUP_CRASHES={0xC00000FD,0xC0000005}


def should_retry(exit_code,text,run_id):
    """A launch is retried only when it crashed before the test script logged
    anything, so a crash while precaching the test models is never retried."""
    return exit_code is not None and (exit_code & 0xffffffff) in STARTUP_CRASHES and f'[R1C:{run_id}]' not in text


CRASH_HANDLERS=('crashpad_handler.exe','messagebox-win.exe')


def owned_crash_handlers(entries,root,executables):
    """Selects the crash handlers a crashed launch left behind.

    entries are (pid, parent pid, image name, image path) tuples. A handler is
    owned when it descends from the launched process (crashpad may start the
    dialog) and runs from this install's Bin folder; others are left alone.
    """
    owned={}
    tree={root}
    changed=True
    while changed:
        changed=False
        for pid,parent,name,path in entries:
            if parent in tree and pid not in tree and name.casefold() in executables:
                if path is not None and path.casefold()==executables[name.casefold()]:
                    tree.add(pid)
                    owned[pid]=name
                    changed=True
    return owned


def close_crash_handlers(game,root,settle=8.0):
    """Closes the TFORevive crash dialog and handler started by a crashed launch.
    Returns the closed (pid, name) pairs."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),('heap',ctypes.c_size_t),
                  ('module',wintypes.DWORD),('threads',wintypes.DWORD),('parent',wintypes.DWORD),
                  ('priority',wintypes.LONG),('flags',wintypes.DWORD),('name',wintypes.WCHAR*260)]

    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    executables={name:str((Path(game)/'Bin'/name).resolve()).casefold() for name in CRASH_HANDLERS}

    def image(pid):
        handle=kernel.OpenProcess(0x1000,False,pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle: return None
        try:
            buffer=ctypes.create_unicode_buffer(32768)
            length=wintypes.DWORD(len(buffer))
            return buffer.value if kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(length)) else None
        finally:
            kernel.CloseHandle(handle)

    def snapshot():
        handle=kernel.CreateToolhelp32Snapshot(2,0)
        if handle==wintypes.HANDLE(-1).value: return []
        rows=[]
        try:
            entry=Entry()
            entry.size=ctypes.sizeof(entry)
            found=kernel.Process32FirstW(handle,ctypes.byref(entry))
            while found:
                rows.append((entry.pid,entry.parent,entry.name))
                found=kernel.Process32NextW(handle,ctypes.byref(entry))
        finally:
            kernel.CloseHandle(handle)
        return [(pid,parent,name,image(pid) if name.casefold() in executables else None) for pid,parent,name in rows]

    closed=[]
    seen=set()
    # The dialog appears a moment after the crash; keep looking briefly.
    deadline=time.monotonic()+settle
    while time.monotonic()<deadline:
        for pid,name in owned_crash_handlers(snapshot(),root,executables).items():
            if pid in seen: continue
            seen.add(pid)
            handle=kernel.OpenProcess(0x100001,False,pid)  # SYNCHRONIZE | PROCESS_TERMINATE
            if handle:
                try:
                    if kernel.TerminateProcess(handle,1):
                        kernel.WaitForSingleObject(handle,5000)
                        closed.append((pid,name))
                finally:
                    kernel.CloseHandle(handle)
        if any(name.casefold()=='messagebox-win.exe' for _,name in closed): break
        time.sleep(0.5)
    return closed


def capture_window(pid,path):
    """Saves the client area of the game's main window as a 24-bit BMP.

    The DirectX window gives a blank PrintWindow image, so the window is raised
    and the screen is read instead. Returns a description of the capture or None.
    """
    import ctypes
    from ctypes import wintypes
    user32=ctypes.WinDLL('user32',use_last_error=True)
    gdi32=ctypes.WinDLL('gdi32',use_last_error=True)
    user32.GetDC.restype=wintypes.HDC
    user32.GetDC.argtypes=[wintypes.HWND]
    user32.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
    gdi32.CreateCompatibleDC.restype=wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes=[wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype=wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int]
    gdi32.SelectObject.restype=wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes=[wintypes.HDC,wintypes.HGDIOBJ]
    gdi32.BitBlt.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.HDC,ctypes.c_int,ctypes.c_int,wintypes.DWORD]
    gdi32.GetDIBits.argtypes=[wintypes.HDC,wintypes.HBITMAP,wintypes.UINT,wintypes.UINT,ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT]
    gdi32.DeleteObject.argtypes=[wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes=[wintypes.HDC]
    windows=[]
    @ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def visit(hwnd,_):
        owner=wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and user32.IsWindowVisible(hwnd):
            rect=wintypes.RECT()
            user32.GetClientRect(hwnd,ctypes.byref(rect))
            name=ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd,name,256)
            windows.append((hwnd,rect.right,rect.bottom,name.value))
        return True
    user32.EnumWindows(visit,0)
    # Prefer the engine window over the launcher's web UI windows.
    candidates=[w for w in windows if w[1]>=640 and w[2]>=360]
    candidates.sort(key=lambda w:(not w[3].startswith(('Respawn','Valve')),-w[1]*w[2]))
    if not candidates: return None
    hwnd,width,height,name=candidates[0]
    # Windows lets a background process raise a window only after a key event.
    user32.keybd_event(0x12,0,0,0)
    user32.keybd_event(0x12,0,2,0)
    user32.ShowWindow(hwnd,9)
    user32.SetWindowPos(hwnd,wintypes.HWND(-1),0,0,0,0,0x0003)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.6)
    corner=wintypes.POINT(0,0)
    user32.ClientToScreen(hwnd,ctypes.byref(corner))
    screen=user32.GetDC(None)
    memory=gdi32.CreateCompatibleDC(screen)
    bitmap=gdi32.CreateCompatibleBitmap(screen,width,height)
    old=gdi32.SelectObject(memory,bitmap)
    try:
        gdi32.BitBlt(memory,0,0,width,height,screen,corner.x,corner.y,0x00CC0020)
        stride=(width*3+3)&~3
        header=(ctypes.c_uint32*10)(40,width,height,1|(24<<16),0,stride*height,0,0,0,0)
        pixels=ctypes.create_string_buffer(stride*height)
        if not gdi32.GetDIBits(memory,bitmap,0,height,pixels,header,0):
            return None
    finally:
        gdi32.SelectObject(memory,old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(None,screen)
        user32.SetWindowPos(hwnd,wintypes.HWND(-2),0,0,0,0,0x0003)
    data=bytes(header)+pixels.raw
    Path(path).write_bytes(b'BM'+(14+len(data)).to_bytes(4,'little')+b'\0\0\0\0'+(54).to_bytes(4,'little')+data)
    return {'window_class':name,'width':width,'height':height}


def read_runtime_log(path,original_size,original_prefix):
    if not path.exists(): return ''
    data=path.read_bytes()
    offset=original_size if len(data)>=original_size and data[:len(original_prefix)]==original_prefix else 0
    return data[offset:].decode('utf-8',errors='replace')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models',nargs='+')
    parser.add_argument('--mount-only',action='append',default=[],help='also mount this local.mdl=models/... without spawning it (e.g. included animation models); repeatable')
    parser.add_argument('--game',type=Path,default=os.environ.get('TITANFALL_ONLINE_DIR'))
    parser.add_argument('--map',default='mp_nexus')
    parser.add_argument('--sequence',default='idle')
    parser.add_argument('--attachment',default='')
    parser.add_argument('--min-attachment-displacement',type=float,default=0.,help='minimum sampled world-space displacement in inches')
    parser.add_argument('--require-trace',type=int,action='append',default=[],help='require the trace for this model index to hit its prop; repeatable')
    parser.add_argument('--physics',action='store_true')
    parser.add_argument('--dedicated',action='store_true',help='server-only loading/animation/physics checks; no rendering claim')
    parser.add_argument('--timeout',type=float,default=150)
    parser.add_argument('--attempts',type=int,default=3,help='relaunch this many times when TFO crashes before the test script starts')
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true',help='prepare and inspect temporary files without launching; not a runtime pass')
    parser.add_argument('--keep-mod',action='store_true',help='keep the owned temporary mod for debugging')
    parser.add_argument('--cwd-bin',action='store_true',help='launch with Bin as the working directory for older TFO builds')
    parser.add_argument('--compiler',type=Path,default=Path(os.environ.get('R1C_COMPILER',Path(__file__).resolve().parents[1]/'build/r1studiomdl.exe')),help='compiler binary recorded for provenance; inputs are not recompiled')
    args=parser.parse_args(argv)
    if args.game is None: parser.error('--game or TITANFALL_ONLINE_DIR is required')
    if not re.fullmatch('[A-Za-z0-9_]+',args.map): parser.error('invalid map')
    if not 1<=args.timeout<=600: parser.error('timeout must be 1..600 seconds')
    if not 1<=args.attempts<=10: parser.error('attempts must be 1..10')
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
        extra=[parse_mount(m) for m in args.mount_only]
        if not args.prepare_only and os.name=='nt':
            for image in ('TFO.exe','tfods.exe'):
                tasks=subprocess.check_output(['tasklist','/FO','CSV','/NH','/FI','IMAGENAME eq '+image],text=True)
                if any(row and row[0].lower()==image.lower() for row in csv.reader(tasks.splitlines())):
                    raise ValueError(image+' is already running; close it before starting an isolated harness run')
        mod,evidence,base_hash=prepare(game,mounts+extra,run_id,args.sequence,args.attachment,args.physics,args.dedicated,extra)
        report.update(models=evidence,mod=str(mod),base_mapspawn_sha256=base_hash,
                      harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      reader_sha256=hashlib.sha256(Path(mdl52.__file__).read_bytes()).hexdigest())
        if args.prepare_only:
            report.update(status='prepared',issues=['prepare-only: game was not launched'])
            return 0
        logs=game/('Logs/tforevive_dedi.log' if args.dedicated else 'Logs/tforevive.log')
        command=launch_command(game,args.map,args.dedicated)
        report['command']=command
        report['executable_sha256']=hashlib.sha256(Path(command[0]).read_bytes()).hexdigest()
        output=args.report.with_suffix('.process.log')
        screenshots={}
        screenshot_roots=[game/'Local/screenshots',game/'screenshots',game/'Data/screenshots']
        for directory in screenshot_roots:
            if directory.exists():
                screenshots.update({str(p):p.stat().st_mtime_ns for p in directory.glob('*') if p.is_file()})
        report['attempts']=[]
        report['window_captures']=[]
        capture_issues=[]
        for attempt in range(args.attempts):
            previous_log=logs.read_bytes() if logs.exists() else b''
            offset=len(previous_log)
            prefix=previous_log[:256]
            captured=set()
            with output.open('ab') as stream:
                process=subprocess.Popen(command,cwd=game/'Bin' if args.cwd_bin else game,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if args.dedicated and os.name=='nt' else 0)
                report.update(status='running',pid=process.pid)
                deadline=time.monotonic()+args.timeout
                text=''
                while time.monotonic()<deadline:
                    if logs.exists():
                        text=read_runtime_log(logs,offset,prefix)
                        if 'SCRIPT ERROR' in text and 'r1c_model_test.nut' in text:
                            break
                        if not args.dedicated and os.name=='nt':
                            for view in re.findall(rf'\[R1C:{run_id}\] VIEW (\d+)',text):
                                if view not in captured:
                                    captured.add(view)
                                    path=args.report.with_name(f'{args.report.stem}.view{view}.bmp')
                                    info=capture_window(process.pid,path)
                                    if info:
                                        report['window_captures'].append({'view':int(view),'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),**info})
                                    else:
                                        capture_issues.append(f'view {view}: no game window to capture')
                        if f'[R1C:{run_id}] DONE' in text:
                            time.sleep(3)
                            break
                    if process.poll() is not None: break
                    time.sleep(0.5)
                if logs.exists():
                    text=read_runtime_log(logs,offset,prefix)
                exit_code=process.poll()
                report['attempts'].append({'pid':process.pid,'exit_code':exit_code})
                if exit_code not in (None,0) and os.name=='nt':
                    closed=close_crash_handlers(game,process.pid)
                    report['attempts'][-1]['closed_crash_handlers']=[{'pid':pid,'name':name} for pid,name in closed]
                if attempt+1<args.attempts and should_retry(exit_code,text,run_id):
                    print(f'attempt {attempt+1}: TFO crashed at startup (0x{exit_code & 0xffffffff:08X}), retrying',flush=True)
                    continue
                break
        result=evaluate(text,run_id,len(mounts),args.sequence,args.attachment,args.physics,[t for _,t in mounts],args.require_trace,args.min_attachment_displacement)
        report.update(result,status='passed' if result['passed'] else 'failed')
        if capture_issues:
            report['issues'].extend(capture_issues)
            report.update(passed=False,status='failed')
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
