"""Independent, bounds-checked reader for Titanfall 1 / Online MDL v52.

This is a structural checker and RLE decoder, not an in-game compatibility claim.
"""
from pathlib import Path
import argparse
import json
import math
import struct


class FormatError(ValueError):
    pass


class Binary:
    def __init__(self, data):
        self.data = data

    def span(self, offset, length):
        if offset < 0 or length < 0 or offset + length > len(self.data):
            raise FormatError(f'out-of-bounds span {offset:#x} + {length:#x}')
        return self.data[offset:offset + length]

    def read(self, fmt, offset):
        self.span(offset, struct.calcsize('<' + fmt))
        return struct.unpack_from('<' + fmt, self.data, offset)

    def integer(self, offset):
        return self.read('i', offset)[0]

    def string(self, offset):
        self.span(offset, 1)
        end = self.data.find(b'\0', offset)
        if end < 0:
            raise FormatError('unterminated string')
        return self.data[offset:end].decode('utf-8', errors='replace')

    def table(self, offset, count, stride):
        if count < 0:
            raise FormatError('negative count')
        self.span(offset, count * stride)
        return range(offset, offset + count * stride, stride)


def rle_value(binary, offset, frame):
    for _ in range(frame + 1):
        valid, total = binary.read('BB', offset)
        if not 0 < valid <= total:
            raise FormatError('invalid RLE span')
        binary.span(offset + 2, valid * 2)
        if frame < total:
            return binary.read('h', offset + 2 + 2 * min(frame, valid - 1))[0]
        frame -= total
        offset += 2 + valid * 2
    raise FormatError('invalid RLE frame')


class Model(Binary):
    def __init__(self, data):
        super().__init__(data)
        if self.span(0, 4) != b'IDST' or self.integer(4) != 52:
            raise FormatError('expected Titanfall MDL v52')
        self.span(0, 0x198)
        if self.integer(0x4c) != len(data):
            raise FormatError('MDL declared length does not match file')
        self.checksum = self.integer(8)
        self.name = self.span(12, 64).split(b'\0', 1)[0].decode('utf-8', errors='replace')
        self.hdr2 = self.integer(0x190)
        self.span(self.hdr2, 0xd0)
        self.flags = self.integer(0x98)
        self.bones = []
        for offset in self.table(self.integer(0xa0), self.integer(0x9c), 0xd8):
            bone = {'offset': offset, 'name': self.string(offset + self.integer(offset)),
                    'parent': self.integer(offset + 4)}
            for key, field in [('pos',0x20), ('rot',0x3c), ('posscale',0x48), ('rotscale',0x54),
                               ('scale',0xbc), ('scalescale',0xc8)]:
                bone[key] = self.read('3f', offset + field)
                if not all(math.isfinite(x) for x in bone[key]):
                    raise FormatError('nonfinite bone transform')
            self.bones.append(bone)
        for index, bone in enumerate(self.bones):
            seen = {index}
            parent = bone['parent']
            while parent != -1:
                if parent in seen or not 0 <= parent < len(self.bones):
                    raise FormatError('invalid or cyclic bone parent')
                seen.add(parent)
                parent = self.bones[parent]['parent']
        self.animations = []
        for offset in self.table(self.integer(0xb8), self.integer(0xb4), 0x64):
            self.animations.append({'offset': offset, 'name': self.string(offset + self.integer(offset + 4)),
                                    'fps': self.read('f',offset+8)[0], 'flags':self.integer(offset+12),
                                    'frames':self.integer(offset+16), 'block':self.integer(offset+0x34),
                                    'data':self.integer(offset+0x38), 'section':self.integer(offset+0x50),
                                    'sectionframes':self.integer(offset+0x54)})
        self.sequences = []
        for offset in self.table(self.integer(0xc0), self.integer(0xbc), 0xd4):
            self.sequences.append(self.string(offset + self.integer(offset + 4)))
        self.textures = [self.string(o+self.integer(o)) for o in self.table(self.integer(0xd0),self.integer(0xcc),0x40)]
        self.models = []
        self.bodypart_model_counts = []
        for bp in self.table(self.integer(0xec),self.integer(0xe8),16):
            self.bodypart_model_counts.append(self.integer(bp+4))
            for offset in self.table(bp+self.integer(bp+12),self.integer(bp+4),0x94):
                meshes = []
                for mo in self.table(offset+self.integer(offset+0x4c),self.integer(offset+0x48),0x74):
                    material, modelrel, count, start = self.read('4i',mo)
                    if modelrel + mo != offset or not 0 <= material < len(self.textures):
                        raise FormatError('invalid mesh model/material reference')
                    meshes.append({'material':material,'vertices':count,'start':start})
                self.models.append({'name':self.span(offset,64).split(b'\0',1)[0].decode('utf-8',errors='replace'),
                                    'vertices':self.integer(offset+0x50),'meshes':meshes})

    def check_render(self, vvd, vtx):
        """Check stored vertex buffers and the complete packed DX11 strip hierarchy."""
        lods=vvd.integer(12)
        if not 1 <= lods <= 8:
            raise FormatError('invalid VVD LOD count')
        counts=vvd.read('8i',16)
        total=sum(m['vertices'] for m in self.models)
        # The stored array may include vertices retained only by lower LODs.
        fixups=vvd.integer(48)
        vvd.table(vvd.integer(52),fixups,12)
        vertex_offset=vvd.integer(56)
        tangent_offset=vvd.integer(60)
        vvd.span(vertex_offset,total*48)
        vvd.span(tangent_offset,total*16)
        for i in range(total):
            offset=vertex_offset+i*48
            weights=vvd.read('3f',offset)
            bones=vvd.read('3B',offset+12)
            number=vvd.read('B',offset+15)[0]
            if not 1 <= number <= 3 or any(b>=len(self.bones) for b in bones[:number]):
                raise FormatError('invalid VVD skin bone index/count')
            if not all(math.isfinite(v) for v in weights+vvd.read('8f',offset+16)+vvd.read('4f',tangent_offset+16*i)):
                raise FormatError('nonfinite render vertex')
            if any(w<0 for w in weights) or abs(sum(weights)-1)>1e-4:
                raise FormatError('invalid normalized skin weights')
        for f in vvd.table(vvd.integer(52),fixups,12):
            lod,start,count=vvd.read('3i',f)
            if not 0 <= lod < lods or start<0 or count<0 or start+count>total:
                raise FormatError('invalid VVD fixup range')
        if vtx.integer(28)!=len(self.bodypart_model_counts):
            raise FormatError('VTX bodypart count mismatch')
        model_index=0
        triangle_indices=0
        for bi,bp in enumerate(vtx.table(vtx.integer(32),vtx.integer(28),8)):
            if vtx.integer(bp)!=self.bodypart_model_counts[bi]:
                raise FormatError('VTX model count mismatch')
            for mo in vtx.table(bp+vtx.integer(bp+4),vtx.integer(bp),8):
                model=self.models[model_index]
                model_index+=1
                for lo in vtx.table(mo+vtx.integer(mo+4),vtx.integer(mo),12):
                    if vtx.integer(lo)!=len(model['meshes']):
                        raise FormatError('VTX mesh count mismatch')
                    for mi,me in enumerate(vtx.table(lo+vtx.integer(lo+4),vtx.integer(lo),9)):
                        mesh=model['meshes'][mi]
                        for group in vtx.table(me+vtx.integer(me+4),vtx.integer(me),33):
                            nv,vo,ni,io,ns,so=vtx.read('6i',group)
                            for vertex in vtx.table(group+vo,nv,9):
                                original=vtx.read('H',vertex+4)[0]
                                if original>=mesh['vertices']:
                                    raise FormatError('VTX original mesh vertex out of range')
                            vtx.span(group+io,ni*2)
                            for index in range(ni):
                                if vtx.read('H',group+io+2*index)[0]>=nv:
                                    raise FormatError('VTX strip index out of range')
                            for strip in vtx.table(group+so,ns,35):
                                nindices,first,nverts,start=vtx.read('4i',strip)
                                if min(nindices,first,nverts,start)<0 or first+nindices>ni or start+nverts>nv:
                                    raise FormatError('invalid VTX strip range')
                            triangle_indices+=ni
        return {'stored_vertices':total,'lod0_vertices':counts[0],'strip_indices_all_lods':triangle_indices}

    def decode_frame(self, animation, frame):
        a = self.animations[animation]
        if not 0 <= frame < a['frames']:
            raise FormatError('frame outside animation')
        if a['block'] or a['flags'] & 0x40:
            raise FormatError('external or frame-encoded animation is not supported by this RLE decoder')
        delta = bool(a['flags'] & 4)
        pose = [{'pos':(0.,0.,0.) if delta else b['pos'],
                 'rot':(0.,0.,0.) if delta else b['rot'],
                 'scale':(1.,1.,1.) if delta else b['scale']} for b in self.bones]
        local = frame
        offset = a['offset'] + a['data']
        if a['sectionframes']:
            section = frame // a['sectionframes']
            if frame == a['frames'] - 1:
                section = (a['frames'] - 1) // a['sectionframes'] + 1
                local = 0
            else:
                local %= a['sectionframes']
            block, relative = self.read('2i',a['offset']+a['section']+8*section)
            if block:
                raise FormatError('external animation section')
            offset = a['offset'] + relative
        visited = set()
        for _ in range(len(self.bones) + 1):
            bone, flags, next_offset = self.read('BBh',offset)
            if bone == 255:
                break
            if bone >= len(self.bones) or bone in visited:
                raise FormatError('invalid/duplicate animation bone')
            visited.add(bone)
            if flags & (1|2|0x20|0x40):
                raise FormatError('raw channels are not supported by this RLE decoder yet')
            ptr = offset + 4
            for key, mask, scale_key in [('rot',8,'rotscale'),('pos',4,'posscale'),('scale',0x80,'scalescale')]:
                if flags & mask:
                    values = self.read('3h',ptr)
                    base = (0.,0.,0.) if flags & 0x10 else self.bones[bone][key]
                    pose[bone][key] = tuple(base[c] + (rle_value(self,ptr+values[c],local) if values[c] else 0)*self.bones[bone][scale_key][c] for c in range(3))
                    ptr += 6
            if next_offset == 0:
                break
            if next_offset < 4:
                raise FormatError('invalid animation chain link')
            offset += next_offset
        else:
            raise FormatError('unterminated animation chain')
        return pose


def inspect(path, decode=False):
    path = Path(path)
    model = Model(path.read_bytes())
    peers = {}
    binaries = {}
    for ext, magic, version, ckoff in [('.vvd',b'IDSV',4,8),('.vvc',b'IDCV',1,8),('.dx11.vtx',None,7,16),('.phy',None,None,12)]:
        peer = path.with_suffix(ext)
        if not peer.exists():
            continue
        data = Binary(peer.read_bytes())
        if magic and data.span(0,4) != magic:
            raise FormatError(f'{ext}: invalid magic')
        if version is not None and data.integer(4 if magic else 0) != version:
            raise FormatError(f'{ext}: invalid version')
        if data.integer(ckoff) != model.checksum:
            raise FormatError(f'{ext}: mismatched checksum')
        peers[ext] = len(data.data)
        binaries[ext] = data
    if any(m['vertices'] for m in model.models) and not all(e in peers for e in ('.vvd','.dx11.vtx')):
        raise FormatError('missing render companion file')
    render = model.check_render(binaries['.vvd'],binaries['.dx11.vtx']) if '.vvd' in binaries and '.dx11.vtx' in binaries else {}
    frames = 0
    if decode:
        for index,a in enumerate(model.animations):
            for frame in range(a['frames']):
                model.decode_frame(index,frame)
                frames += 1
    return {'name':model.name,'version':52,'bones':len(model.bones),'models':len(model.models),
            'animations':len(model.animations),'sequences':model.sequences,'peers':peers,'render':render,'decoded_frames':frames}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mdl',type=Path)
    parser.add_argument('--decode',action='store_true',help='decode every RLE frame; raw/frame/external encodings currently unsupported')
    args = parser.parse_args()
    print(json.dumps(inspect(args.mdl,args.decode),indent=2))
