"""Compare rebuilt models with the originals inside R1Delta, driven through its MCP server.

Each pair (an original and its rebuild, compiled under another $modelname) is
spawned side by side in a running local match. The script compares, through the
server VM: bounds; every attachment, relative to each prop's origin, at several
times of up to three sequences (both props are set to the same time with
Anim_Play + Anim_SetInitialTime in one call); a grid of downward collision
traces; and, for physics props, where a dropped copy comes to rest. It also
takes a screenshot of each pair from a noclip camera for visual review.

The models must already be mounted (stage an addon before the game starts, e.g.
with ingame_test_r1delta.py prepare) and the game started with
-usemcp +mcp_start_http, in a loaded map.

  python tools/r1delta_compare.py --pairs pairs.json --report report.json

pairs.json: {"preload": ["models/..."], "pairs": [{"name": ..., "kind": "static" |
"animated" | "character" | "physics", "retail": "models/...", "rebuilt": "models/...",
"attachments": [...], "sequences": [[name, seconds], ...], "extent": inches}]}
"""
import argparse
import json
import math
import re
import time
from pathlib import Path

import r1delta_mcp

VEC = r'\(vector : \(([-0-9.e+]+), ([-0-9.e+]+), ([-0-9.e+]+)\)\)'


def angle_matrix(pitch, yaw, roll):
    """Source AngleMatrix for QAngle degrees: rows are the forward, left and up axes."""
    sp, cp = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
    sy, cy = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    sr, cr = math.sin(math.radians(roll)), math.cos(math.radians(roll))
    return [(cp * cy, cp * sy, -sp),
            (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, sr * cp),
            (cr * sp * cy + sr * sy, cr * sp * sy - sr * cy, cr * cp)]


def vec(text):
    m = re.search(VEC, text)
    return tuple(float(v) for v in m.groups()) if m else None


class Session:
    def __init__(self, client):
        self.c = client

    def run(self, code):
        """Runs server code; returns {key: [values]} from lines 'R1CMP key value'."""
        try:
            out = self.c.squirrel('server', code)
            error = None
        except RuntimeError as e:
            out, error = str(e), str(e)
        values = {}
        for line in out.splitlines():
            m = re.search(r'R1CMP (\S+) (.*)$', line)
            if m:
                values.setdefault(m.group(1), []).append(m.group(2).strip())
        if error and 'SCRIPT ERROR' in error:
            values.setdefault('error', []).append(error[error.find('SCRIPT ERROR'):][:300])
        return values


SETUP = r'''
::R1CMP_props <- {}
::R1CMP_Out <- function( key, value ) { printl( "R1CMP " + key + " " + value ) }
'''


def quote(s):
    if not re.fullmatch(r'[A-Za-z0-9_./\\-]+', s):
        raise ValueError('unexpected characters in %r' % s)
    return '"%s"' % s.replace('\\', '/')


def compare_pair(s, pair, base, report_dir, client):
    result = {'name': pair['name'], 'kind': pair['kind'], 'issues': []}
    extent = max(48.0, float(pair.get('extent', 64)))
    gap = extent * 1.3
    pos = {'retail': (base[0], base[1] - gap / 2, base[2]), 'rebuilt': (base[0], base[1] + gap / 2, base[2])}
    spawn = []
    for side in ('retail', 'rebuilt'):
        x, y, z = pos[side]
        spawn.append('''
local p = CreatePropDynamic( %s, Vector(%f, %f, %f), Vector(0, 180, 0), 6 )
::R1CMP_props[%s] <- p
R1CMP_Out( "spawn_%s", IsValid(p) )
R1CMP_Out( "mins_%s", p.GetBoundingMins() )
R1CMP_Out( "maxs_%s", p.GetBoundingMaxs() )
R1CMP_Out( "origin_%s", p.GetOrigin() )''' % (quote(pair[side]), x, y, z, quote(side), side, side, side, side))
    v = s.run('\n'.join(spawn))
    if 'error' in v:
        result['issues'].append('spawn: ' + v['error'][0])
        return result
    for side in ('retail', 'rebuilt'):
        if v.get('spawn_' + side) != ['true']:
            result['issues'].append(side + ' did not spawn')
    if result['issues']:
        return result
    origin = {side: vec(v['origin_' + side][0]) for side in ('retail', 'rebuilt')}
    bounds = {side: (vec(v['mins_' + side][0]), vec(v['maxs_' + side][0])) for side in ('retail', 'rebuilt')}
    result['bounds'] = bounds
    bound_diff = max(abs(a - b) for k in range(2) for a, b in zip(bounds['retail'][k], bounds['rebuilt'][k]))
    result['bounds_difference'] = bound_diff
    if bound_diff > 0.01:
        result['issues'].append('bounds differ by %.4f' % bound_diff)

    # attachments across sequence times
    worst_pos = worst_ang = motion = 0.0
    worst_att = None
    samples = 0
    for sequence, seconds in pair.get('sequences', [])[:3]:
        for fraction in (0.0, 0.37, 0.71):
            t = seconds * fraction
            play = '\n'.join('''
::R1CMP_props[%s].Anim_Play( %s )
::R1CMP_props[%s].Anim_SetInitialTime( %f )''' % (quote(side), quote(sequence), quote(side), t) for side in ('retail', 'rebuilt'))
            r = s.run(play)
            if 'error' in r:
                result['issues'].append('sequence %s: %s' % (sequence, r['error'][0]))
                break
            time.sleep(0.15)  # let the server think one frame at that time
            reads = []
            for side in ('retail', 'rebuilt'):
                for name in pair.get('attachments', []):
                    reads.append('''
{ local p = ::R1CMP_props[%s]; local id = p.LookupAttachment( %s )
  if ( id > 0 ) { R1CMP_Out( "att_%s_%s", p.GetAttachmentOrigin( id ) + " " + p.GetAttachmentAngles( id ) ) } }''' % (
                        quote(side), quote(name), side, name))
            r = s.run('\n'.join(reads)) if reads else {}
            for name in pair.get('attachments', []):
                a, b = r.get('att_retail_' + name), r.get('att_rebuilt_' + name)
                if not a and not b:
                    continue
                if not a or not b:
                    result['issues'].append('attachment %s missing on one side' % name)
                    continue
                pa = [x - o for x, o in zip(vec(a[0]), origin['retail'])]
                pb = [x - o for x, o in zip(vec(b[0]), origin['rebuilt'])]
                worst_pos = max(worst_pos, math.dist(pa, pb))
                # compare orientations, not Euler angles: near pitch +-90 one
                # orientation has many Euler forms (gimbal lock)
                ma = angle_matrix(*[float(x) for x in re.findall(VEC, a[0])[1]])
                mb = angle_matrix(*[float(x) for x in re.findall(VEC, b[0])[1]])
                difference = max(abs(x - y) for ra, rb in zip(ma, mb) for x, y in zip(ra, rb))
                angle = math.degrees(2 * math.asin(min(1.0, difference / math.sqrt(2))))  # bound on the rotation between them
                if angle > worst_ang:
                    worst_ang, worst_att = angle, name
                motion = max(motion, math.dist(pa, [0, 0, 0]))
                samples += 1
    result.update(attachment_samples=samples, attachment_position_difference=worst_pos,
                  attachment_angle_difference=worst_ang, worst_angle_attachment=worst_att)
    if worst_pos > 0.05:
        result['issues'].append('attachments differ by %.4f in' % worst_pos)
    if worst_ang > 0.1:
        result['issues'].append('attachment %s orientation differs by %.4f deg' % (worst_att, worst_ang))

    # collision: a grid of downward traces against each prop
    trace = []
    mn, mx = bounds['retail']
    for side in ('retail', 'rebuilt'):
        o = origin[side]
        for i in range(3):
            for j in range(3):
                x = o[0] + mn[0] + (mx[0] - mn[0]) * (i + 0.5) / 3
                y = o[1] + mn[1] + (mx[1] - mn[1]) * (j + 0.5) / 3
                trace.append('''
{ local tr = TraceLine( Vector(%f, %f, %f), Vector(%f, %f, %f), null, TRACE_MASK_SHOT, TRACE_COLLISION_GROUP_NONE )
  R1CMP_Out( "trace_%s_%d", (tr.hitEnt == ::R1CMP_props[%s]) + " " + (tr.endPos.z - %f) ) }''' % (
                    x, y, o[2] + mx[2] + 16, x, y, o[2] + mn[2] - 16, side, i * 3 + j, quote(side), o[2]))
    r = s.run('\n'.join(trace))
    hits = {}
    for side in ('retail', 'rebuilt'):
        hits[side] = [r.get('trace_%s_%d' % (side, k), ['? 0'])[0].split() for k in range(9)]
    worst_trace = 0.0
    mismatched = 0
    for a, b in zip(hits['retail'], hits['rebuilt']):
        if a[0] != b[0]:
            mismatched += 1
        elif a[0] == 'true':
            worst_trace = max(worst_trace, abs(float(a[1]) - float(b[1])))
    result.update(trace_hits=[a[0] == 'true' for a in hits['retail']], trace_hit_mismatches=mismatched,
                  trace_height_difference=worst_trace)
    if mismatched:
        result['issues'].append('%d of 9 traces hit only one copy' % mismatched)
    if worst_trace > 0.05:
        result['issues'].append('trace heights differ by %.4f' % worst_trace)

    # screenshot from a camera in front of the pair
    distance = max(120.0, extent * 2.2)
    cam = (base[0] - distance, base[1], base[2] + extent * 0.35)
    # setpos places the eye; a script SetOrigin did not move a noclipping player
    client.console('setpos %.1f %.1f %.1f' % cam, capture=False)
    pitch = math.degrees(math.atan2(extent * 0.35 - extent * 0.3, distance))
    client.console('setang %.2f 0 0' % pitch, capture=False)
    time.sleep(1.5)
    shots = Path(r'D:/Games/Titanfall/r1/screenshots')
    before = {p.name for p in shots.glob('*.tga')} if shots.exists() else set()
    client.console('screenshot', capture=False)
    for _ in range(20):
        time.sleep(0.5)
        new = sorted({p.name for p in shots.glob('*.tga')} - before)
        if new:
            result['screenshot'] = str(shots / new[0])
            break

    # physics: drop each copy in turn at the same spot beside the player's start and
    # compare where it rests (same ground, same height, same start)
    if pair['kind'] == 'physics':
        gx, gy, gz = pair['ground']
        rest = {}
        for side in ('retail', 'rebuilt'):
            r = s.run('''{ local g = TraceLine( Vector(%f, %f, %f), Vector(%f, %f, %f), null, TRACE_MASK_SOLID, TRACE_COLLISION_GROUP_NONE )
  local e = CreateEntity( "prop_physics" ); e.kv.model = %s; e.SetOrigin( g.endPos + Vector(0, 0, 100) )
  DispatchSpawn( e ); ::R1CMP_props[%s] <- e
  R1CMP_Out( "drop", g.endPos.z + " " + IsValid(e) ) }''' % (gx + 80, gy, gz + 64, gx + 80, gy, gz - 200, quote(pair[side]), quote('drop_' + side)))
            ground_z, valid = (r.get('drop') or ['0 false'])[0].split()[:2]
            if valid != 'true':
                rest[side] = 'not spawnable as prop_physics'
                continue
            time.sleep(5)
            r = s.run('''{ local e = ::R1CMP_props[%s]
  R1CMP_Out( "rest", IsValid(e) ? (e.GetOrigin().z + "") : "gone" )
  if ( IsValid(e) ) e.Destroy() }''' % quote('drop_' + side))
            value = (r.get('rest') or ['gone'])[0]
            rest[side] = 'gone' if value == 'gone' else float(value) - float(ground_z)
        result['physics_rest_height'] = rest
        if rest['retail'] == 'not spawnable as prop_physics':
            result['physics_note'] = 'the original is not a spawnable physics prop either; not compared'
            if rest['rebuilt'] != rest['retail']:
                result['issues'].append('rebuilt spawns as prop_physics although the original does not')
        elif not isinstance(rest['rebuilt'], float):
            result['issues'].append('rebuilt physics copy: %s' % rest['rebuilt'])
        elif not isinstance(rest['retail'], float):
            result['issues'].append('original physics copy: %s' % rest['retail'])
        else:
            result['physics_rest_difference'] = abs(rest['retail'] - rest['rebuilt'])
            if result['physics_rest_difference'] > 1.0:
                result['issues'].append('copies rest %.2f in apart in height' % result['physics_rest_difference'])

    s.run('foreach ( k, p in ::R1CMP_props ) { if ( IsValid( p ) ) p.Destroy() }\n::R1CMP_props <- {}')
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--pairs', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--port', type=int, default=8765)
    a = p.parse_args(argv)
    spec = json.loads(a.pairs.read_text())
    client = r1delta_mcp.R1DeltaMCP(a.port)
    client.connect()
    for command in ('developer 1', 'sv_cheats 1'):
        client.console(command, capture=False)
    s = Session(client)
    s.run(SETUP)
    client.squirrel('ui', 'CloseAllMenus()')
    # included animation models first: R1Delta fails to precache a model whose includes are not loaded
    precache = {}
    for model in spec.get('preload', []) + [m for pair in spec['pairs'] for m in (pair['retail'], pair['rebuilt'])]:
        r = s.run('PrecacheModel( %s )\nR1CMP_Out( "ok", 1 )' % quote(model))
        precache[model] = 'ok' in r and 'error' not in r
    # a fixed point on the ground: the map's first human spawn point, traced down
    # (the player may already be in the air from an earlier run's noclip camera)
    start = vec(s.run('''local o = GetEntArrayByClass_Expensive( "info_spawnpoint_human" )[0].GetOrigin()
local g = TraceLine( o + Vector(0, 0, 32), o - Vector(0, 0, 512), null, TRACE_MASK_SOLID, TRACE_COLLISION_GROUP_NONE )
R1CMP_Out( "ground", g.endPos )''')['ground'][0])
    for command in ('noclip', 'r_drawviewmodel 0', 'cl_drawhud 0'):
        client.console(command, capture=False)
    base = (start[0], start[1], start[2] + 700)
    results = []
    for pair in spec['pairs']:
        if not (precache.get(pair['retail']) and precache.get(pair['rebuilt'])):
            results.append({'name': pair['name'], 'kind': pair['kind'],
                            'issues': ['precache failed: retail %s, rebuilt %s' % (precache.get(pair['retail']), precache.get(pair['rebuilt']))]})
        else:
            pair = dict(pair, ground=start)
            results.append(compare_pair(s, pair, base, a.report.parent, client))
        r = results[-1]
        print('%-6s %-34s %s' % ('OK' if not r['issues'] else 'ISSUE', r['name'], '; '.join(r['issues'])), flush=True)
    report = {'precache': precache, 'results': results, 'passed': sum(not r['issues'] for r in results), 'total': len(results)}
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=1))
    print('%d/%d pairs without issues' % (report['passed'], report['total']))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
