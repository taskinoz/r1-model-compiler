"""Survey native v52 layouts without copying or modifying retail model files."""
from collections import Counter
from pathlib import Path
import argparse
import hashlib
import json
import mdl52


def survey(root):
    counts=Counter()
    errors=[]
    examples={}
    for path in sorted(root.rglob('*.mdl')):
        counts['models']+=1
        try:
            m=mdl52.Model(path.read_bytes())
            info=mdl52.inspect(path)
            counts['structural_pass']+=1
            counts['bones']+=len(m.bones)
            for peer in info['peers']:
                counts['peer'+peer]+=1
            for a in m.animations:
                encoding='external' if a['block'] else 'frame' if a['flags']&0x40 else 'rle'
                counts['animations_'+encoding]+=1
            examples.setdefault(str(len(m.bones)),str(path.relative_to(root)))
        except (ValueError,OSError) as error:
            errors.append({'model':str(path.relative_to(root)),'error':str(error)})
    return {'root':str(root),'counts':dict(counts),'errors':errors,'bone_count_examples':examples,
            'reader_sha256':hashlib.sha256(Path(mdl52.__file__).read_bytes()).hexdigest(),
            'scope':'Structural reader and companion checksum checks only. Not a compiler roundtrip or in-game validation.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    report=survey(args.root)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'counts':report['counts'],'errors':report['errors'][:10],'error_count':len(report['errors'])},indent=2))
