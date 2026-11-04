"""Struct layouts for Titanfall 1 / Titanfall Online (v52) .mdl files and companions.

The same interface as the v53 layout module (field lists, `u`, `size`, `cstr`,
`parse_vtx`), so the decompiler and round-trip tools read both generations alike.
Offsets follow native v52 files and the compiler's writer (src/write/mdl_writer.cpp).
Extended-header offsets are converted to absolute file offsets.
"""
import struct


def _fmt(fields):
    return "<" + "".join(f for _, f in fields)


def unpack_fields(fields, data, off):
    fmt = _fmt(fields)
    vals = struct.unpack_from(fmt, data, off)
    out = {}
    i = 0
    for name, f in fields:
        digits = "".join(c for c in f if c.isdigit())
        kind = f[-1]
        n = int(digits) if digits and kind != "s" else 1
        if n == 1:
            v = vals[i]
            if kind == "s":
                v = v.split(b"\0", 1)[0].decode("latin1")
            out[name] = v
            i += 1
        else:
            out[name] = list(vals[i:i + n])
            i += n
    return out, struct.calcsize(fmt)


def u(fields, data, off):
    return unpack_fields(fields, data, off)[0]


def size(fields):
    return struct.calcsize(_fmt(fields))


def cstr(data, off):
    if off <= 0 or off >= len(data):
        return None
    end = data.find(b"\0", off)
    return data[off:end].decode("latin1")


HDR_FIELDS = [
    ("id", "i"), ("version", "i"), ("checksum", "i"), ("name", "64s"), ("length", "i"),
    ("eyeposition", "3f"), ("illumposition", "3f"), ("hull_min", "3f"), ("hull_max", "3f"),
    ("view_bbmin", "3f"), ("view_bbmax", "3f"),
    ("flags", "i"),
    ("numbones", "i"), ("boneindex", "i"),
    ("numbonecontrollers", "i"), ("bonecontrollerindex", "i"),
    ("numhitboxsets", "i"), ("hitboxsetindex", "i"),
    ("numlocalanim", "i"), ("localanimindex", "i"),
    ("numlocalseq", "i"), ("localseqindex", "i"),
    ("activitylistversion", "i"), ("eventsindexed", "i"),
    ("numtextures", "i"), ("textureindex", "i"),
    ("numcdtextures", "i"), ("cdtextureindex", "i"),
    ("numskinref", "i"), ("numskinfamilies", "i"), ("skinindex", "i"),
    ("numbodyparts", "i"), ("bodypartindex", "i"),
    ("numlocalattachments", "i"), ("localattachmentindex", "i"),
    ("numlocalnodes", "i"), ("localnodeindex", "i"), ("localnodenameindex", "i"),
    ("numflexdesc", "i"), ("flexdescindex", "i"),
    ("numflexcontrollers", "i"), ("flexcontrollerindex", "i"),
    ("numflexrules", "i"), ("flexruleindex", "i"),
    ("numikchains", "i"), ("ikchainindex", "i"),
    ("nummouths", "i"), ("mouthindex", "i"),
    ("numlocalposeparameters", "i"), ("localposeparamindex", "i"),
    ("surfacepropindex", "i"),
    ("keyvalueindex", "i"), ("keyvaluesize", "i"),
    ("numlocalikautoplaylocks", "i"), ("localikautoplaylockindex", "i"),
    ("mass", "f"), ("contents", "i"),
    ("numincludemodels", "i"), ("includemodelindex", "i"),
    ("virtualModel", "i"),
    ("szanimblocknameindex", "i"), ("numanimblocks", "i"), ("animblockindex", "i"), ("animblockModel", "i"),
    ("bonetablebynameindex", "i"),
    ("pVertexBase", "i"), ("pIndexBase", "i"),
    ("constdirectionallightdot", "B"), ("rootLOD", "B"), ("numAllowedRootLODs", "B"), ("unused0", "B"),
    ("fadeDistance", "f"),
    ("numflexcontrollerui", "i"), ("flexcontrolleruiindex", "i"),
    ("flVertAnimFixedPointScale", "f"), ("surfacepropLookup", "i"),
    ("studiohdr2index", "i"), ("sourceFilenameOffset", "i"),
]
assert size(HDR_FIELDS) == 0x198, hex(size(HDR_FIELDS))

# studiohdr2_t; indexes are relative to this header except srcbonetransformindex,
# which is from the start of the file (Source reads it through studiohdr_t)
HDR2_FIELDS = [
    ("numsrcbonetransform", "i"), ("srcbonetransformindex", "i"),
    ("illumpositionattachmentindex", "i"), ("flMaxEyeDeflection", "f"),
    ("linearboneindex", "i"), ("sznameindex", "i"),
    ("boneFlexDriverCount", "i"), ("boneFlexDriverIndex", "i"),
    ("perTriAABBIndex", "i"), ("perTriAABBNodeCount", "i"), ("perTriAABBLeafCount", "i"), ("perTriAABBVertCount", "i"),
    ("unkStringOffset", "i"),
]
HDR2_RELATIVE = ("linearboneindex", "sznameindex", "boneFlexDriverIndex",
                 "perTriAABBIndex", "unkStringOffset")

BONE_FIELDS = [
    ("sznameindex", "i"), ("parent", "i"), ("bonecontroller", "6i"),
    ("pos", "3f"), ("quat", "4f"), ("rot", "3f"),
    ("posscale", "3f"), ("rotscale", "3f"),
    ("poseToBone", "12f"), ("qAlignment", "4f"),
    ("flags", "i"), ("proctype", "i"), ("procindex", "i"), ("physicsbone", "i"),
    ("surfacepropidx", "i"), ("contents", "i"), ("surfacepropLookup", "i"),
    ("scale", "3f"), ("scalescale", "3f"), ("unused", "i"),
]
assert size(BONE_FIELDS) == 0xD8, hex(size(BONE_FIELDS))

ATTACH_FIELDS = [("sznameindex", "i"), ("flags", "I"), ("localbone", "i"), ("local", "12f"), ("unused", "8i")]
HBOXSET_FIELDS = [("sznameindex", "i"), ("numhitboxes", "i"), ("hitboxindex", "i")]
BBOX_FIELDS = [("bone", "i"), ("group", "i"), ("bbmin", "3f"), ("bbmax", "3f"), ("szhitboxnameindex", "i"),
               ("forceCritPoint", "i"), ("hitdataGroupOffset", "i"), ("unused", "6i")]
ANIMDESC_FIELDS = [
    ("baseptr", "i"), ("sznameindex", "i"), ("fps", "f"), ("flags", "i"), ("numframes", "i"),
    ("nummovements", "i"), ("movementindex", "i"), ("ikrulezeroframeindex", "i"), ("framemovementindex", "i"),
    ("unused1", "4i"), ("animblock", "i"), ("animindex", "i"),
    ("numikrules", "i"), ("ikruleindex", "i"), ("animblockikruleindex", "i"),
    ("numlocalhierarchy", "i"), ("localhierarchyindex", "i"),
    ("sectionindex", "i"), ("sectionframes", "i"),
    ("zeroframespan", "h"), ("zeroframecount", "h"), ("zeroframeindex", "i"), ("zeroframestalltime", "f"),
]
assert size(ANIMDESC_FIELDS) == 0x64, hex(size(ANIMDESC_FIELDS))
SEQDESC_FIELDS = [
    ("baseptr", "i"), ("szlabelindex", "i"), ("szactivitynameindex", "i"), ("flags", "i"),
    ("activity", "i"), ("actweight", "i"), ("numevents", "i"), ("eventindex", "i"),
    ("bbmin", "3f"), ("bbmax", "3f"), ("numblends", "i"), ("animindexindex", "i"),
    ("movementindex", "i"), ("groupsize", "2i"), ("paramindex", "2i"), ("paramstart", "2f"),
    ("paramend", "2f"), ("paramparent", "i"), ("fadeintime", "f"), ("fadeouttime", "f"),
    ("localentrynode", "i"), ("localexitnode", "i"), ("nodeflags", "i"), ("entryphase", "f"),
    ("exitphase", "f"), ("lastframe", "f"), ("nextseq", "i"), ("pose", "i"), ("numikrules", "i"),
    ("numautolayers", "i"), ("autolayerindex", "i"), ("weightlistindex", "i"), ("posekeyindex", "i"),
    ("numiklocks", "i"), ("iklockindex", "i"), ("keyvalueindex", "i"), ("keyvaluesize", "i"),
    ("cycleposeindex", "i"), ("activitymodifierindex", "i"), ("numactivitymodifiers", "i"),
    ("ikResetMask", "i"), ("unk_C4", "i"), ("unused", "3i"),
]
assert size(SEQDESC_FIELDS) == 0xD4, hex(size(SEQDESC_FIELDS))
TEXTURE_FIELDS = [("sznameindex", "i"), ("flags", "i"), ("used", "i"), ("unused", "13i")]
assert size(TEXTURE_FIELDS) == 0x40
BODYPART_FIELDS = [("sznameindex", "i"), ("nummodels", "i"), ("base", "i"), ("modelindex", "i")]
MODEL_FIELDS = [
    ("name", "64s"), ("type", "i"), ("boundingradius", "f"), ("nummeshes", "i"), ("meshindex", "i"),
    ("numvertices", "i"), ("vertexindex", "i"), ("tangentsindex", "i"), ("numattachments", "i"),
    ("attachmentindex", "i"), ("numeyeballs", "i"), ("eyeballindex", "i"), ("pad", "4i"),
    ("colorindex", "i"), ("uv2index", "i"), ("unused", "4i"),
]
assert size(MODEL_FIELDS) == 0x94
MESH_FIELDS = [
    ("material", "i"), ("modelindex", "i"), ("numvertices", "i"), ("vertexoffset", "i"),
    ("numflexes", "i"), ("flexindex", "i"), ("materialtype", "i"), ("materialparam", "i"),
    ("meshid", "i"), ("center", "3f"), ("modelvertexdata", "i"), ("numLODVertexes", "8i"),
    ("unk_54", "2i"), ("unused", "6i"),
]
assert size(MESH_FIELDS) == 0x74
IKCHAIN_FIELDS = [("sznameindex", "i"), ("linktype", "i"), ("numlinks", "i"), ("linkindex", "i")]
assert size(IKCHAIN_FIELDS) == 0x10
IKLINK_FIELDS = [("bone", "i"), ("kneeDir", "3f"), ("unused0", "3f")]
POSEPARAM_FIELDS = [("sznameindex", "i"), ("flags", "i"), ("start", "f"), ("end", "f"), ("loop", "f")]
JIGGLE_FIELDS = [("flags", "i")] + [(n, "f") for n in (
    "length tipMass yawStiffness yawDamping pitchStiffness pitchDamping alongStiffness alongDamping "
    "angleLimit minYaw maxYaw yawFriction yawBounce minPitch maxPitch pitchFriction pitchBounce "
    "baseMass baseStiffness baseDamping baseMinLeft baseMaxLeft baseLeftFriction baseMinUp baseMaxUp "
    "baseUpFriction baseMinForward baseMaxForward baseForwardFriction").split()]
EVENT_FIELDS = [("cycle", "f"), ("event", "i"), ("type", "i"), ("options", "64s"), ("szeventindex", "i")]
AUTOLAYER_FIELDS = [("iSequence", "h"), ("iPose", "h"), ("flags", "i"), ("start", "f"), ("peak", "f"),
                    ("tail", "f"), ("end", "f")]
IKRULE_FIELDS = [
    ("index", "i"), ("type", "i"), ("chain", "i"), ("bone", "i"), ("slot", "i"), ("height", "f"),
    ("radius", "f"), ("floor", "f"), ("pos", "3f"), ("q", "4f"), ("compressedikerrorindex", "i"),
    ("unused2", "i"), ("iStart", "i"), ("ikerrorindex", "i"), ("start", "f"), ("peak", "f"), ("tail", "f"),
    ("end", "f"), ("unused3", "i"), ("contact", "f"), ("drop", "f"), ("top", "f"), ("unused6", "i"),
    ("unused7", "i"), ("unused8", "i"), ("szattachmentindex", "i"), ("endHeight", "f"), ("unused", "6i"),
]
assert size(IKRULE_FIELDS) == 0x98, hex(size(IKRULE_FIELDS))

VTX_HDR = [("version", "i"), ("vertCacheSize", "i"), ("maxBonesPerStrip", "H"), ("maxBonesPerFace", "H"),
           ("maxBonesPerVert", "i"), ("checkSum", "i"), ("numLODs", "i"), ("materialReplacementListOffset", "i"),
           ("numBodyParts", "i"), ("bodyPartOffset", "i")]
VVD_HDR = [("id", "i"), ("version", "i"), ("checksum", "i"), ("numLODs", "i"), ("numLODVertexes", "8i"),
           ("numFixups", "i"), ("fixupTableStart", "i"), ("vertexDataStart", "i"), ("tangentDataStart", "i")]
VVC_HDR = [("id", "i"), ("version", "i"), ("checksum", "i"), ("numLODs", "i"), ("numLODVertexes", "8i"),
           ("colorDataStart", "i"), ("uv2DataStart", "i")]
VTX_BODYPART = [("numModels", "i"), ("modelOffset", "i")]
VTX_MODEL = [("numLODs", "i"), ("lodOffset", "i")]
VTX_LOD = [("numMeshes", "i"), ("meshOffset", "i"), ("switchPoint", "f")]
VTX_MESH = [("numStripGroups", "i"), ("stripGroupHeaderOffset", "i"), ("flags", "B")]
VTX_STRIPGROUP = [("numVerts", "i"), ("vertOffset", "i"), ("numIndices", "i"), ("indexOffset", "i"),
                  ("numStrips", "i"), ("stripOffset", "i"), ("flags", "B"), ("numTopologyIndices", "i"),
                  ("topologyOffset", "i")]
VTX_STRIP = [("numIndices", "i"), ("indexOffset", "i"), ("numVerts", "i"), ("vertOffset", "i"),
             ("numBones", "h"), ("flags", "B"), ("numBoneStateChanges", "i"), ("boneStateChangeOffset", "i"),
             ("numTopologyIndices", "i"), ("topologyOffset", "i")]
VTX_VERT = [("boneWeightIndex", "3B"), ("numBones", "B"), ("origMeshVertID", "H"), ("boneID", "3b")]
assert size(VTX_MESH) == 9 and size(VTX_STRIPGROUP) == 33 and size(VTX_STRIP) == 35 and size(VTX_VERT) == 9

STRIDE = {"bone": 0xD8, "anim": 0x64, "seq": 0xD4, "texture": 0x40, "attachment": 0x5C, "hitbox": 0x44,
          "ikchain": 0x10, "iklink": 0x1C, "ikrule": 0x98, "poseparam": 0x14, "event": 0x50}


class Model:
    """A v52 MDL with its header (extended-header fields merged, made absolute)."""

    def __init__(self, data):
        self.data = data
        h = u(HDR_FIELDS, data, 0)
        if h["id"] != 0x54534449 or h["version"] != 52:
            raise ValueError("not a v52 mdl: id=%x version=%d" % (h["id"], h["version"]))
        base = h["studiohdr2index"]
        h2 = u(HDR2_FIELDS, data, base) if base else {name: 0 for name, _ in HDR2_FIELDS}
        for name in HDR2_RELATIVE:
            if h2[name]:
                h2[name] += base
        h.update(h2)
        self.hdr = h

    def full_name(self):
        h = self.hdr
        return (cstr(self.data, h["sznameindex"]) if h["sznameindex"] else None) or h["name"]

    def bones(self):
        h = self.hdr
        out = []
        for i in range(h["numbones"]):
            o = h["boneindex"] + i * 0xD8
            b = u(BONE_FIELDS, self.data, o)
            b["name"] = cstr(self.data, o + b["sznameindex"])
            b["surfaceprop"] = cstr(self.data, o + b["surfacepropidx"])
            b["_offset"] = o
            if b["procindex"] and b["proctype"] == 5:
                b["jiggle"] = u(JIGGLE_FIELDS, self.data, o + b["procindex"])
            out.append(b)
        return out


def parse_vtx(data, base=0):
    """Nested dict tree of the VTX at offset base."""
    hdr = u(VTX_HDR, data, base)
    tree = {"hdr": hdr, "bodyparts": []}
    for bi in range(hdr["numBodyParts"]):
        bo = base + hdr["bodyPartOffset"] + bi * size(VTX_BODYPART)
        bp = u(VTX_BODYPART, data, bo)
        bp["models"] = []
        for mi in range(bp["numModels"]):
            mo = bo + bp["modelOffset"] + mi * size(VTX_MODEL)
            md = u(VTX_MODEL, data, mo)
            md["lods"] = []
            for li in range(md["numLODs"]):
                lo = mo + md["lodOffset"] + li * size(VTX_LOD)
                ld = u(VTX_LOD, data, lo)
                ld["meshes"] = []
                for ei in range(ld["numMeshes"]):
                    eo = lo + ld["meshOffset"] + ei * size(VTX_MESH)
                    me = u(VTX_MESH, data, eo)
                    me["stripgroups"] = []
                    for gi in range(me["numStripGroups"]):
                        go = eo + me["stripGroupHeaderOffset"] + gi * size(VTX_STRIPGROUP)
                        sg = u(VTX_STRIPGROUP, data, go)
                        sg["_off"] = go
                        sg["strips"] = [u(VTX_STRIP, data, go + sg["stripOffset"] + k * size(VTX_STRIP))
                                        for k in range(sg["numStrips"])]
                        me["stripgroups"].append(sg)
                    ld["meshes"].append(me)
                md["lods"].append(ld)
            bp["models"].append(md)
        tree["bodyparts"].append(bp)
    return tree


def vvd_ids(vvd):
    """Stored VVD vertex index of each MDL (LOD 0) vertex, with the fixup table applied.

    Vertex i is at vertexDataStart + 48 * ids[i] and tangentDataStart + 16 * ids[i];
    VVC colours and second UVs are stored parallel to the VVD's vertices."""
    h = u(VVD_HDR, vvd, 0)
    if not h["numFixups"]:
        return list(range(h["numLODVertexes"][0]))
    ids = []
    for k in range(h["numFixups"]):
        lod, source, count = struct.unpack_from("<3i", vvd, h["fixupTableStart"] + 12 * k)
        if lod >= 0:  # every fixup applies to LOD 0
            ids.extend(range(source, source + count))
    return ids


CHECKSUM_AT = {".vvd": 8, ".vvc": 8, ".dx11.vtx": 16, ".phy": 12}


def companion(mdl_path, suffix, checksum):
    """A companion file's bytes, or None when it is missing or belongs to another
    build (its checksum differs from the MDL's; some retail companions are stale)."""
    import os
    peer = os.path.splitext(mdl_path)[0] + suffix
    if not os.path.exists(peer):
        return None
    with open(peer, "rb") as f:
        data = f.read()
    at = CHECKSUM_AT.get(suffix)
    if at is not None and (len(data) < at + 4 or struct.unpack_from("<i", data, at)[0] != checksum):
        return None
    return data
