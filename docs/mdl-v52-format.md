# Native Titanfall MDL v52 notes

These notes describe the first native writer and observations from local Titanfall
Online data. Layouts were independently implemented using retail bytes and
consult-only [rmdlconv v52 structs](https://github.com/r-ex/rmdlconv/blob/main/src/studio/studio.h).
They do not establish complete game compatibility.

| Structure | Native v52 size | Important difference from v53 |
|---|---:|---|
| studiohdr_t | 0x198 | name at 0x0C; length at 0x4C; extended-header pointer at 0x190 |
| studiohdr2_t | 0xD0 | separate, pointers relative to this header |
| bone | 0xD8 | position scales at 0x48, bind scale at 0xBC |
| animation descriptor | 0x64 | animblock/data at 0x34/0x38; section table at 0x50 |
| animation section | 8 | animblock followed by descriptor-relative data offset |
| sequence descriptor | 0xD4 | no v53 trailing extension |
| IK chain | 0x10 | links still 0x1C each |
| IK rule | 0x98 | iStart at 0x44; phases at 0x4C; attachment at 0x78 |
| texture | 0x40 | larger reserved area than v53 |
| model / mesh | 0x94 / 0x74 | the initial writer uses the shared layout |

The original header's name is 64 bytes. The extended header's logical-name pointer
is relative to the extended header, as are source-bone transforms, linear bones and
the per-triangle collision tree. Render/physics companions are separate files.
VVD v4 and VVC v1 have checksums at +8; DX11 VTX v7 at +16; PHY at +12.

Bones store position at 0x20, quaternion at 0x2C, Euler angles at 0x3C,
position compression scales at 0x48, rotation scales at 0x54, inverse bind matrix
at 0x60, alignment quaternion at 0x90, flags at 0xA0, procedure type/index at
0xA4/0xA8, physics bone at 0xAC, surface property at 0xB0, contents at 0xB4,
bind scale at 0xBC and scale compression scales at 0xC8.

RLE records start with `{u8 bone; u8 flags; i16 next}`. Flags are raw position 1,
raw Quaternion48 2, animated position 4, animated rotation 8, delta 16,
raw Quaternion64 32, raw scale 64 and animated scale 128. Animated groups use
three signed 16-bit offsets relative to their own pointer group; zero means a
zero channel. The writer emits rotation, position and scale groups in that order.
Position scales are shared by all animations on a bone, unlike v53's record scale.
Each RLE span has u8 valid/total counts followed by valid signed 16-bit samples.

The compiler deliberately omits optional linear-bone optimization data for now.
It emits internal RLE animations only. Native frame-encoded and external ANI
reading, decompile/recompile validation, RUI representation and runtime testing
remain future work. The inherited triangle-tree layout is version 2; its runtime
behaviour on both v52 games still requires verification.


Static-prop DX11 VTX vertex records store numBones=0 at byte +3, although their
VVD records retain the static bone's unit weight. Static VTX strips also have no
hardware bone palette. The initial inherited writer incorrectly emitted
numBones=1 for these VTX vertices. All 7,539,027 examined VTX vertices in 3,097
native Online static models store zero, with no parse failures. Non-static
vertices retain their actual skin influence count. Runtime confirmation of the
corrected writer is tracked in VALIDATION.md.

The Titanfall Online client loads a model's VVD and VTX through the name stored
in the MDL (the extended header's name, mirrored at 0x0C), not the path the MDL
was opened from. A model file renamed or moved after compiling still loads on the
server, but the client finds no render data and draws nothing, without an error.
Compile with the `$modelname` the model will be shipped under.
