"""Round-trip test: decompile retail v52 models, recompile with r1studiomdl, compare.

usage: python tools/roundtrip52.py [--compiler build/r1studiomdl.exe] [--out DIR] [--limit N] model.mdl|dir ...
Prints one line per model and a summary; writes results.json in the output dir.
"""
import argparse
import collections
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decompile52 as dc  # noqa: E402
import mdl52layout  # noqa: E402
import phy as phylib  # noqa: E402


def checkpoint(path, value):
    """Replace the report atomically so an interrupted run keeps its last result."""
    temporary = path + '.tmp'
    with open(temporary, 'w') as report:
        json.dump(value, report, indent=1)
    # Windows can briefly deny the replace while another process (antivirus, indexer)
    # holds the report open; retry rather than abort a long run.
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.25)


def run_signature(compiler):
    paths = [compiler, __file__, dc.__file__, mdl52layout.__file__, phylib.__file__]
    return {os.path.basename(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}


def world_positions(bones, frame):
    out = []
    mats = []
    for i, (pos, rm) in enumerate(frame):
        m = [row[:] for row in rm]
        for k in range(3):
            m[k][3] = pos[k]
        if bones[i]['parent'] >= 0:
            m = dc.concat(mats[bones[i]['parent']], m)
        mats.append(m)
        out.append((m[0][3], m[1][3], m[2][3]))
    return out


def companion(path, suffix, checksum):
    return mdl52layout.companion(path, suffix, checksum)


def summary(path):
    with open(path, 'rb') as source:
        d = source.read()
    m = mdl52layout.Model(d)
    h = m.hdr
    vvd, vtx, phy = (companion(path, x, h['checksum']) for x in ('.vvd', '.dx11.vtx', '.phy'))
    source = dc.AnimData(d, h, companion(path, '.ani', h['checksum']) if h['numanimblocks'] else None)
    bones = m.bones()
    s = {'name': m.full_name(), 'flags': h['flags'] & ~0x800000, 'bones': [(b['name'], b['parent']) for b in bones]}
    s['bind'] = [tuple(b['pos']) + tuple(b['rot']) for b in bones]
    tex = []
    for i in range(h['numtextures']):
        o = h['textureindex'] + i * 0x40
        tex.append(mdl52layout.cstr(d, o + struct.unpack_from('<i', d, o)[0]).lower().replace('/', chr(92)))
    s['textures'] = sorted(tex)
    tris = []
    geometry = collections.Counter()
    if vtx and vvd:
        t = mdl52layout.parse_vtx(vtx, 0)
        vh = mdl52layout.u(mdl52layout.VVD_HDR, vvd, 0)
        stored = mdl52layout.vvd_ids(vvd)
        sz = mdl52layout.size(mdl52layout.BODYPART_FIELDS)
        for bpi, bp in enumerate(t['bodyparts']):
            bo = h['bodypartindex'] + bpi * sz
            mdl_bp = mdl52layout.u(mdl52layout.BODYPART_FIELDS, d, bo)
            for mi, md in enumerate(bp['models']):
                mo = bo + mdl_bp['modelindex'] + mi * 0x94
                mm = mdl52layout.u(mdl52layout.MODEL_FIELDS, d, mo)
                meshes = [mdl52layout.u(mdl52layout.MESH_FIELDS, d, mo + mm['meshindex'] + k * 0x74) for k in range(mm['nummeshes'])]
                for li, ld in enumerate(md['lods']):
                    tris.append(sum(sg['numIndices'] // 3 for me in ld['meshes'] for sg in me['stripgroups']))
                    if li:
                        continue
                    # LOD 0 corner positions (a multiset; vertex order and splits may differ)
                    for ei, me in enumerate(ld['meshes']):
                        for sg in me['stripgroups']:
                            go = sg['_off']
                            ids = [struct.unpack_from('<H', vtx, go + sg['vertOffset'] + 9 * k + 4)[0] for k in range(sg['numVerts'])]
                            for index in struct.unpack_from('<%dH' % sg['numIndices'], vtx, go + sg['indexOffset']):
                                v = mm['vertexindex'] // 48 + meshes[ei]['vertexoffset'] + ids[index]
                                pos = struct.unpack_from('<3f', vvd, vh['vertexDataStart'] + 48 * stored[v] + 16)
                                geometry[tuple(round(c, 2) + 0.0 for c in pos)] += 1
    s['tris'] = tris
    s['geometry'] = hashlib.sha256(repr(sorted(geometry.items())).encode()).hexdigest()
    seqs = []
    for i in range(h['numlocalseq']):
        o = h['localseqindex'] + i * 0xD4
        q = mdl52layout.u(mdl52layout.SEQDESC_FIELDS, d, o)
        keys = ()
        if q['posekeyindex'] and (q['groupsize'][0] > 1 or q['groupsize'][1] > 1):
            n = q['groupsize'][0] + q['groupsize'][1]
            keys = tuple(round(k, 2) for k in struct.unpack_from('<%df' % n, d, o + q['posekeyindex']))
        weights = ()
        if q['weightlistindex']:
            weights = tuple(round(w, 3) for w in struct.unpack_from('<%df' % len(bones), d, o + q['weightlistindex']))
        animations = struct.unpack_from('<%dh' % (q['groupsize'][0] * q['groupsize'][1]), d, o + q['animindexindex'])
        seqs.append((mdl52layout.cstr(d, o + q['szlabelindex']), q['numevents'], q['groupsize'][0], q['groupsize'][1],
                     q['flags'], keys, weights, q['numikrules'], animations))
    s['seqs'] = seqs
    anims = []
    for ai in range(h['numlocalanim']):
        a = source.desc(ai)[1]
        nf = a['numframes']
        sample = sorted({0, nf // 2, nf - 1}) if nf > 0 else []
        a, name, frames = dc.decode_anim(d, m, bones, ai, sample, with_scale=True, source=source)
        scales = {f: [tuple(e[2]) for e in pose] for f, pose in zip(sample, frames)}
        frames = [[(e[0], e[1]) for e in pose] for pose in frames]
        fms = dc.decode_frame_movement(d, m, ai, sample)
        if fms is not None and not (a['flags'] & 4):
            frames = [dc.apply_root_motion(bones, fr, fm) for fr, fm in zip(frames, fms)]
        delta = bool(a['flags'] & 4)

        # Delta animations are compared as raw local values (they are added onto a pose):
        # the translation plus the rotation's basis vectors at a 50-unit lever.
        def local_delta(pose):
            return [tuple(p) + tuple(50 * rm[r][c] for r in range(3) for c in range(3)) for p, rm in pose]
        ik = []
        for r in dc.decode_ik_rules(d, h, ai):
            rng = (r['start'], r['peak'], r['tail'], r['end'], r['contact'])
            errs = []
            if r['compressedikerrorindex'] and nf > 1:
                first = r['iStart']
                last = first + int(round((r['end'] - r['start']) * (nf - 1)))
                for f in sorted({first, (first + last) // 2, last}):
                    e = dc.decode_ik_error(d, r, f)
                    errs.append(e[0] + tuple(50 * v for v in e[1]))  # angles at a 50-unit lever
            ik.append({'key': (r['index'], r['type'], r['chain'], r['bone'], r['slot'], r['attachment'],
                               tuple(round(v, 3) for v in rng), round(r['height'], 2), round(r['radius'], 2),
                               round(r['floor'], 2), round(r['endHeight'], 2)),
                       'pos': tuple(r['pos']), 'errors': errs})
        anims.append({'name': name, 'frames': nf, 'delta': delta, 'flags': a['flags'],
                      'scale': scales, 'ik': ik,
                      'world': {f: (local_delta(pose) if delta else world_positions(bones, pose))
                                for f, pose in zip(sample, frames)}})
    s['anims'] = anims
    if phy:
        p = phylib.parse_phy(phy)
        vols = [float(v) for v in re.findall(r'"volume"\s+"([^"]+)"', p['text'])]
        s['phy'] = {'solids': p['solidCount'], 'volume': sum(vols)}
    s['attach'] = h['numlocalattachments']
    s['hitboxsets'] = h['numhitboxsets']
    s['pertri'] = h['perTriAABBLeafCount']

    def flat(v):
        if isinstance(v, dict):
            return tuple(flat(x) for x in v.values())
        if isinstance(v, (list, tuple)):
            return tuple(flat(x) for x in v)
        return round(v, 3) if isinstance(v, float) else v
    s['proc'] = [(b['name'], b['proctype'], b['jiggle']['flags'] if b['proctype'] == 5 and b.get('jiggle') else 0,
                  tuple(round(v, 3) for k, v in b['jiggle'].items() if k != 'flags') if b['proctype'] == 5 and b.get('jiggle')
                  else flat(dc.decode_procedural(d, h, i, b)))
                 for i, b in enumerate(bones) if b['proctype']]
    return s


def compare(a, b):
    issues = []
    if a['name'] != b['name']:
        issues.append('model name %s vs %s' % (a['name'], b['name']))
    if a['flags'] != b['flags']:
        issues.append('header flags %#x vs %#x' % (a['flags'], b['flags']))
    if a['bones'] != b['bones']:
        issues.append('bones differ (%d vs %d)' % (len(a['bones']), len(b['bones'])))
    else:
        worst = 0
        for x, y in zip(a['bind'], b['bind']):
            worst = max(worst, max(abs(p - q) for p, q in zip(x[:3], y[:3])))
        if worst > 0.01:
            issues.append('bind pose off by %.3f' % worst)
    if a['textures'] != b['textures']:
        issues.append('textures differ')
    if a['tris'] != b['tris']:
        issues.append('triangle counts %s vs %s' % (a['tris'][:6], b['tris'][:6]))
    elif a['geometry'] != b['geometry']:
        issues.append('LOD 0 triangle corner positions differ')
    if [x[0] for x in a['seqs']] != [x[0] for x in b['seqs']]:
        issues.append('sequence names differ')
    elif [x[4:] for x in a['seqs']] != [x[4:] for x in b['seqs']]:
        bad = [x[0] for x, y in zip(a['seqs'], b['seqs']) if x[4:] != y[4:]]
        issues.append('sequence flags/pose keys/weights/animations differ (%d, e.g. %s)' % (len(bad), bad[0]))
    if len(a['anims']) != len(b['anims']):
        issues.append('anim count %d vs %d' % (len(a['anims']), len(b['anims'])))
    elif a['bones'] == b['bones']:
        worst, worst_anim = 0.0, ""
        for x, y in zip(a['anims'], b['anims']):
            if x['frames'] != y['frames']:
                issues.append('anim frames %d vs %d' % (x['frames'], y['frames']))
                break
            if x['delta'] != y['delta']:
                issues.append('delta flag differs on an animation')
                break
            if x.get('flags') != y.get('flags'):
                issues.append('animation flags %s vs %s' % (hex(x.get('flags') or 0), hex(y.get('flags') or 0)))
                break
            for f in x['world']:
                for p, q in zip(x['world'][f], y['world'][f]):
                    distance = math.dist(p, q)
                    if distance > worst:
                        worst, worst_anim = distance, x['name']
        if worst > 0.25:
            issues.append('anim world positions off by %.2f (%s)' % (worst, worst_anim))
        ikbad, ikworst = None, 0.0
        for x, y in zip(a['anims'], b['anims']):
            xi, yi = x.get('ik', []), y.get('ik', [])
            if [r['key'] for r in xi] != [r['key'] for r in yi]:
                ikbad = ikbad or (len(xi), len(yi), next((p['key'], q['key']) for p, q in zip(xi + [{'key': None}], yi + [{'key': None}]) if p['key'] != q['key']))
                continue
            for p, q in zip(xi, yi):
                ikworst = max([ikworst, math.dist(p['pos'], q['pos'])] +
                              [math.dist(u, v) for u, v in zip(p['errors'], q['errors'])])
        if ikbad:
            issues.append('ik rules differ (%d vs %d rules, e.g. %s vs %s)' % (ikbad[0], ikbad[1], ikbad[2][0], ikbad[2][1]))
        elif ikworst > 0.25:
            issues.append('ik rule targets/errors off by %.2f' % ikworst)
        sworst = 0.0
        for x, y in zip(a['anims'], b['anims']):
            for f in x.get('scale', {}):
                for p, q in zip(x['scale'][f], y.get('scale', {}).get(f, [])):
                    sworst = max(sworst, max(abs(u - v) for u, v in zip(p, q)))
        if sworst > 0.01:
            issues.append('bone scale off by %.3f' % sworst)
    if 'phy' in a:
        if 'phy' not in b:
            issues.append('phy missing')
        else:
            if a['phy']['solids'] != b['phy']['solids']:
                issues.append('phy solids %d vs %d' % (a['phy']['solids'], b['phy']['solids']))
            va, vb = a['phy']['volume'], b['phy']['volume']
            if va > 0 and abs(va - vb) / va > 0.02:
                issues.append('phy volume %.1f vs %.1f' % (va, vb))
    if a.get('proc', []) != b.get('proc', []):
        pa, pb = a.get('proc', []), b.get('proc', [])
        issues.append('procedural bones differ (%d vs %d, e.g. %s)' % (len(pa), len(pb), next(
            (x[0] for x, y in zip(pa + [('',)], pb + [('',)]) if x != y), '')))
    if a['attach'] != b['attach']:
        issues.append('attachments %d vs %d' % (a['attach'], b['attach']))
    if a['hitboxsets'] != b['hitboxsets']:
        issues.append('hitbox sets %d vs %d' % (a['hitboxsets'], b['hitboxsets']))
    return issues


def owned_workdir(work, root, source):
    folder=Path(work).resolve(); root=Path(root).resolve()
    if folder.parent != root:
        raise ValueError('refusing to discard sources outside the output directory')
    folder.mkdir(parents=True,exist_ok=True)
    marker=folder/'.r2c-generated'
    identity=str(Path(source).resolve())
    if marker.exists():
        if marker.read_text()!=identity: raise ValueError('work directory belongs to a different input')
    elif any(folder.iterdir()):
        raise ValueError('refusing to discard an existing, unmarked work directory')
    else: marker.write_text(identity)
    return folder


def discard_work_sources(folder):
    for child in folder.iterdir():
        if child.name.startswith('recompiled.') or child.name == '.r2c-generated': continue
        if child.is_symlink(): child.unlink()
        elif child.is_dir():
            if not child.resolve().is_relative_to(folder):
                raise ValueError('refusing cleanup outside the generated work directory')
            shutil.rmtree(child)
        else: child.unlink()


def process_model(job):
    compiler, source, work, stamp = job[:4]
    discard=bool(job[4]) if len(job)>4 else False
    folder=None
    try:
        if discard: folder=owned_workdir(work,job[5],source)
        qc = dc.decompile(source, work)
        outmdl = os.path.join(work, 'recompiled.mdl')
        run = subprocess.run([compiler, '-quiet', '-o', outmdl, qc], capture_output=True, encoding='latin-1', timeout=600)
        if run.returncode:
            lines = (run.stdout + run.stderr).strip().splitlines()
            result = {'status': 'compile-failed', 'error': lines[-1] if lines else ''}
        else:
            issues = compare(summary(source), summary(outmdl))
            result = {'status': 'diff' if issues else 'ok', 'issues': issues}
    except Exception as error:
        result = {'status': 'exception', 'error': repr(error), 'trace': traceback.format_exc()}
    if folder is not None:
        try: discard_work_sources(folder)
        except (OSError,ValueError) as error: result['cleanup_error']=str(error)
    result['input_stamp'] = stamp
    return source, result


def main():
    ap = argparse.ArgumentParser()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument('--compiler', default=os.path.join(root, 'build', 'r1studiomdl.exe'))
    ap.add_argument('--out', default=os.path.join(root, 'test-output', 'roundtrip52'))
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--jobs', type=int, default=1, help='number of independent model workers')
    ap.add_argument('--resume', action='store_true', help='skip saved results with unchanged inputs and tools')
    ap.add_argument('--discard-sources',action='store_true',help='retain rebuilt models and delete generated input exports in marked work folders')
    ap.add_argument('inputs', nargs='+')
    a = ap.parse_args()
    if a.jobs < 1:
        ap.error('--jobs must be at least 1')
    files = []
    for i in a.inputs:
        if os.path.isdir(i):
            for dp, dn, fn in os.walk(i):
                files += [os.path.join(dp, f) for f in fn if f.endswith('.mdl')]
        else:
            files.append(i)
    files = sorted(set(os.path.abspath(f) for f in files))
    if a.limit:
        files = files[:a.limit]
    os.makedirs(a.out, exist_ok=True)
    report = os.path.join(a.out, 'results.json')
    manifest = os.path.join(a.out, 'run.json')
    signature = run_signature(a.compiler)
    signature['discard_sources']=a.discard_sources
    results = {}
    if a.resume and os.path.exists(report):
        if not os.path.exists(manifest) or json.loads(Path(manifest).read_text()) != signature:
            ap.error('cannot resume: compiler or test tools changed; use a new --out directory or omit --resume')
        results = json.loads(Path(report).read_text())
    # Clear an old report before installing a new signature, including when the
    # first model is interrupted before producing a result.
    checkpoint(report, results)
    checkpoint(manifest, signature)
    names = collections.Counter(os.path.splitext(os.path.basename(f))[0] for f in files)
    reused = 0
    jobs = []
    for f in files:
        stamp = [os.stat(f).st_size, os.stat(f).st_mtime_ns]
        if a.resume and f in results and results[f].get('input_stamp') == stamp:
            reused += 1
            continue
        results.pop(f, None)
        name = os.path.splitext(os.path.basename(f))[0]
        # Different model folders can contain the same basename.
        suffix = '-' + hashlib.sha256(f.encode()).hexdigest()[:12] if names[name] > 1 else ''
        work = os.path.join(a.out, name + suffix)
        jobs.append((a.compiler, f, work, stamp, a.discard_sources, str(Path(a.out).resolve())))

    def record(completed):
        for source, result in completed:
            results[source] = result
            checkpoint(report, results)
            detail = '; '.join(result.get('issues', [])) or result.get('error', '')
            print('%-14s%-50s %s' % (result['status'].upper(), Path(source).stem, detail[:160]), flush=True)

    if a.jobs == 1:
        record(map(process_model, jobs))
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=a.jobs) as pool:
            pending = [pool.submit(process_model, job) for job in jobs]
            record(future.result() for future in concurrent.futures.as_completed(pending))
    ok = sum(results[f]['status'] == 'ok' for f in files)
    print('\n%d/%d identical in the compared fields (%d resumed)' % (ok, len(files), reused))
    return 0 if ok == len(files) else 1


if __name__ == '__main__':
    raise SystemExit(main())
