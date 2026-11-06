# Native v52 validation status

Initial implementation, 3 November 2026. This is an experimental compiler, not a
fully validated replacement for Respawn/Valve studiomdl.

## Compiler and tests

- Release x64 `build/r1studiomdl.exe` SHA-256:
  `f24f5c450464f67e9ca09c2270986999dd1e9196d886ac26e58c9ca60592c42f`.
- Independent reader `tools/mdl52.py` SHA-256:
  `0da97fb62ba116639f5fe890b87f9a4d2b6351c69650820caee6e137a6eb3a7e`.
- 30 Python regression tests pass (14 compiler, 16 harness). Both CTest groups pass. Locked uv route
  also passes, using the standard library only.
- Static, rigid physics and jointed/animated authored examples compile into native
  v52 MDL and separate companions. Generated PHY solids are independently parsed.
- Tests check native primary/extended-header pointers, bone/model/mesh tables,
  companion checksums, VVD skin weights/bone indices/fixups, DX11 strip/vertex
  index ranges, and stale optional-companion removal.
- Every frame is independently decoded for translation/rotation/scale tests,
  shared bone position scales, and 132-frame sectioned animation boundaries.
  Native IK phase/target/end-height fields and every stored error sample are tested.
- Corrupt model offsets, missing/mismatched companions and corrupt VTX indices
  are rejected. No comparison threshold was widened to make an input pass.

## Native retail observations

The local Titanfall Online `assets_dump/models` tree contains 3,514 models.
The initial header/table reader parsed their native v52 layouts. 3,412 complete
model sets passed the initial companion checks; 102 failed: 101 PHY checksum
mismatches and one VVD checksum mismatch. These remain failures, not exceptions
to the compiler's checksum contract. Their cause in the extracted data has not
been established. Report: ignored `test-output/tfo-structure.json`.

The initial survey predates the additional full VVD/VTX buffer checks; its reader
hash is recorded in that report. It is not evidence that all retail geometry passed
the later checker, and is not a compiler roundtrip.

The later reader's complete VVD/VTX checks pass these individual Online references:
`error.mdl`, `angel_city/angelapartments_sign_large_01.mdl`, and
`weapons/rspn101/ptpov_rspn101.mdl` (98 bones, 21 model/bodygroup entries).

An original Titanfall `error.mdl` and its VVD/VTX were extracted from the installed
`englishclient_mp_common.bsp.pak000_dir.vpk`; they pass native structure, companion
checksum and complete VVD/VTX checks. Report: `test-output/tf1-error-render-check.json`.
Only this small sample was extracted, not a second multi-gigabyte corpus.

The upstream `pg9182/tf2vpk` v0.0.4 extractor initially rejected native VPK entries.
An isolated research copy was adjusted to allow observed VVC/VVD flags and zero-byte
entries, including their size reserialization. File decompression and CRC checks
were retained. The modified extraction code is ignored and is not compiler code.

## Not yet validated or implemented

- Original Titanfall runtime, full TFO client rendering, and broader playback/physics coverage beyond the dedicated-server smoke tests below.
- Native retail decompile/recompile and full-frame/render/collision equivalence.
- Retail frame-encoded and external ANI animation decoding. The initial reader
  only decodes compiler-produced RLE, and rejects raw encodings explicitly.
- RUI authoring/import, bone followers and the optional linear-bone optimization.
- Native ragdoll constraints, procedural bones, LOD/skin variants, root movement
  and advanced QC options beyond the listed authored regressions.
- Direct compilation/import of compiled Portal/SFM MDLs or Source PHY files.

The TF2 validation history under `docs/reference/v53-validation.md` belongs only to
the parent v53 compiler; none of its corpus/runtime results establish v52 coverage.
Native runtime and corpus evidence are required before a stable release.

## Runtime harness work, 3 November 2026

- Added tools/ingame_test52.py for TFORevive. Native inspections and complete model
  companion staging/hashes are performed before launching. A unique owned mod is
  cleaned up after preparation, failure or completion. Core mod files are untouched.
- Added 11 harness regressions: staging/cleanup, checksum failure before mutation,
  foreign/outside cleanup rejection, path/script injection rejection, complete vs
  partial/wrong-run/wrong-model telemetry, runtime errors, required attachment/
  physics samples, and explicitly nonpassing prepare-only reports.
- Total: 25 Python tests pass (14 compiler + 11 harness); CTest and locked uv pass.
- A real preparation run mounted the freshly compiled static box and original TF1
  error-model control with all companions. Cleanup succeeded. This is staging
  evidence only: test-output/tfo-prepare.json.
- Real launch attempts: test-output/tfo-runtime-static.json and
  test-output/tfo-runtime-bin-cwd.json. The installed D:\Games\Titanfall Online\Bin\TFO.exe
  (SHA256 1569b5b66dba1773dd04c7a0122bbf99a836e34177c7efcfe078944cf1faad5f)
  exited with 0xC0000409 before creating fresh runtime logs. No INIT, spawn or pose
  telemetry was received. Both reports correctly fail and confirm mod cleanup.
- Installed R1Delta 2.14.15 was launched separately with its configured original
  Titanfall game root. It displayed R1Delta Launcher Error and exited before a map;
  the dialog disappeared before its body could be captured, so the exact cause is
  unconfirmed. No R1Delta model-validation pass is claimed.
- No game process or harness mod was left running. Neither native engine reached
  the actual model probes; Squirrel integration and runtime correctness remain
  unvalidated. Do not upgrade the compiler's experimental status from these runs.


## Successful TFO server runtime checks, 4 November 2026

This supersedes the earlier statement that no runtime reached the probes. The
initial direct client failure was an absent launcher argument: the installed
TFO.exe requires `--authToken` even when `-noauth` is used by the SDK. Supplying
the literal non-credential `r1c-local-noauth` with `-noauth` starts the engine and
mounts the temporary mod. No account token is read or required. The client then
crashes before the model probes with stack overflow 0xC00000FD in nvwgf2umx.dll.
No Windows security settings or game binaries were changed.

The dedicated adapter launches installed `Bin/tfods.exe -noauth -dedicated` with
local-server settings. It runs on mp_nexus without a player or renderer, waits for
EntitiesDidLoad, selects a real map spawn point and uses native TF1 vector methods.
The actual script execution exposed and fixed the original TF2-style vector call.

| Case | Runtime evidence | Report |
|---|---|---|
| Static | Compiled box and original TF1 error-model control both spawn; five pose samples each; compiled box trace hit at 64.0313 inches | tfo-dedicated-static-final.json |
| Animation | bend resolves as sequence 1; five probe samples move by up to 16.542787509626258 inches; model trace hit at 6.03125 inches | tfo-dedicated-animation.json |
| Physics | Compiled rigid model drops 135.535 inches and settles; native TFO domestic/pizza_box control drops 121.785 inches; five samples each | tfo-dedicated-physics.json |

All three reports pass with exit code 0 and mod_removed:true. The compiler binary
remains f24f5c450464f67e9ca09c2270986999dd1e9196d886ac26e58c9ca60592c42f.
Each report records the exact native executable, harness, reader and mounted
companion hashes. test-output/tfo-server-runtime-summary.json checks source hashes
again and re-evaluates preserved runtime logs using the final stricter evaluator:
required compiled-model trace hits and at least 1 inch of animated attachment motion.
Original runtime reports retain their original harness hashes; offline re-evaluation
is identified separately and does not masquerade as a new game run.

The first static server run used a broad trace at world origin, which hit map
geometry. That trace is not counted as collision evidence. The final static and
animation tests use spawn points and model-bounded traces, with positive hits.

These are SERVER-ONLY smoke tests, not visual proof, native retail roundtrips,
full-frame equivalence or complete ragdoll/procedural/LOD support. The client GPU
crash still prevented rendering validation at this point (client runs succeeded later; see below). Physics control geometry differs from
the authored box, so its drop distance is a functional control, not an equality test.

Updated R1Delta 3.0.4 was also tried. Direct Titanfall.exe explicitly requires its
launcher and reports Failed to start the launcher when called without that parent.
The normal desktop launch was subsequently observed to start after a delay, reaching
the main menu and private lobby. This corrects the initial observation that no game
window appeared. A uniquely owned addon under Titanfall/r1/addons was recognized
and enabled by the updated client. It contains the compiled box, native error-model
control and our server autorun probes; core game files are untouched. A local match
has not yet reached those probes, so no R1Delta model-rendering pass is claimed.
R1Delta menu rendering itself works; the GPU crash above belongs to TFORevive.

Four more harness regressions cover mandatory no-auth launcher arguments, headless
executable routing, required trace hits and required attachment motion; a fifth
covers log truncation/append freshness. Total 30 tests, CTest and locked uv pass.


## R1Delta listen-server investigation (4 November 2026)

The updated 3.0.4 client reached local mp_fracture matches. Its addon list was
initially disabled (0); enabling the uniquely owned addon and restarting allowed
its autorun probes to execute. The first callback ran during the dropship intro,
so its high-altitude placement is not counted as a visual test.

The listen-server run exposed a harness API error after DONE: server-side players
do not have the client-only ClientCommand method. The generator now uses the
native global ClientCommand(player, command), also used by the installed server
scripts. A regression covers the generated server call. Total: 31 Python tests,
locked uv, and both CTest groups pass. The compiler executable is unchanged.

A corrected replay at the grounded player position logs both exact model paths,
five pose samples per model, DONE and READY_FOR_VISUAL without the API error.
The compiled box's model-bounded trace hits at 64.0313 inches. The preserved
report is test-output/r1delta-grounded.json with its log, compiler, harness and
reader hashes. It explicitly evaluates the static run with no requested sequence;
the earlier failed startup is retained separately in r1delta-startup-console.txt.

Rendering is NOT validated: after both props were moved close to the camera and
above the terrain, the native ERROR control was visible but the compiled box was
not. Correct server model identity and collision therefore do not establish a
client-rendering pass. Four small diagnostic variants (material, header flag and
winding) are staged in the owned addon for investigation; they are not fixes or
passing evidence. A stable release remains blocked on this rendering fault and
the other coverage gaps above. No comparison threshold was changed.


## Static VTX correction and reusable R1Delta harness (4 November 2026)

The writer now emits zero hardware bone influences in static-prop VTX vertices,
matching all 7,539,027 examined vertices across 3,097 Online static models (zero
parse failures). VVD static unit weights are unchanged. The independent reader
rejects the previous nonzero static VTX value; a regression compiles both static
and dynamic meshes and rejects a deliberately corrupted static companion.

Compiler SHA-256:
`fdd9852c629b6caab26b930f90f6be7e8c333b961611481b8480a779ea6120a4`.
Direct Python and locked-uv suites pass 36 tests; both CTest groups pass.
For two diagnostic boxes, MDL/VVD files are byte-identical to the old outputs;
only 24 VTX vertex bone-count bytes change from one to zero. Reports remain in
`test-output/render-ab/fixed-comparison.json` and `fixed-runtime-stage.json`;
the fixed scene's initial console evidence is `fixed-runtime-console.txt`.

This change does not resolve the rendering failure. In the restarted local match,
the native ERROR model was visible while the fixed comparison boxes were still
not visible. The initial fixed run logged all four model paths and completed pose
samples, but that telemetry does not prove rendered geometry. A later attempted
console-script replay did not produce a fresh dump or recover the console, so it
is not counted as another successful runtime run. The format correction is
supported by native corpus evidence; client rendering remains a blocking gap.

The new `tools/ingame_test_r1delta.py` provides prepare/collect/cleanup commands,
unique addon/script/log IDs, companion hashes, delayed grounded placement,
side-by-side probes, screenshot requests and ownership-checked cleanup. Four new
regressions cover staging while preserving concurrent addon-list edits, refusing
changed cfg removal, validating inputs before game mutation, and keeping visual
validation false even when server telemetry passes. Preparation never counts as
a runtime pass. The new cfg/bootstrap and screenshot collection are staged for
live verification; they are not yet claimed to work unattended in R1Delta.


## Live R1Delta harness verification (4 November 2026)

The initial cfg did not execute server scripts because the restarted local match
had sv_cheats=0. Enabling developer=1 and sv_cheats=1 restored the server probe.
IncludeScript failed to load the loose source; the native IncludeFile helper
successfully loaded it. con_logfile accepted the filename but produced no file.
The corrected harness therefore uses IncludeFile and native ServerCommand calls
for screenshot and condump; it no longer refreshes addon search paths mid-match.
The earlier audio warning from that refresh is preserved in the failed bootstrap
console evidence. No core scripts or authentication settings were changed.

The corrected exec was observed at 778.957 seconds in the current listen server.
It logged BEGIN, both expected model paths, samples 0 through 4 for each model,
DONE, screenshot, READY_FOR_VISUAL and condump. The collector automatically found
condump007.txt and returned server_passed=true with no issues. It preserves the
raw console snapshot and hashes it separately from the portion beginning at the
explicit run boundary. Earlier failed bootstrap diagnostics remain in the raw
snapshot; diagnostics after BEGIN fail the run. Reused BEGIN boundaries also fail.

Evidence: test-output/r1delta-harness-report.json and its .console.txt snapshot;
test-output/r1delta-harness-live/scene.png is a viewable copy of the automatic TGA.
TGA SHA-256: d595a681e5b6599cfb70e6c14bdbff9039fb4d4e6c3fd1e3f1afffae3328aa9c.
The static box trace again hits at 64.0313 inches. The automatic screenshot was
inspected: native ERROR controls render, while the compiled box remains invisible.
The older diagnostic addon was still mounted, so several native controls remain
in the scene. This is a successful harness/server smoke test and a FAILED model
rendering test, not native compiler completion or an equivalence pass.

Compiler hash remains fdd9852c629b6caab26b930f90f6be7e8c333b961611481b8480a779ea6120a4.
The 36-test suite includes cfg developer-gate ordering, native IncludeFile loading,
automatic screenshot/dump generation and strict run-boundary regression checks.


## TFO client harness run (4 November 2026)

Following MRVN-Radiant's `tools/respawn/tfo_harness.py`, `ingame_test52.py` now
retries launches that crash in the GPU driver (0xC00000FD) before the test script
initializes, supplies the stock `pilot_male_fastest` settings file when offline
sessions return none, waits for the player to leave the dropship, rests each prop
on the ground and captures the game window. The engine `screenshot` command left
no file, so the window capture is the visual evidence.

Run `test-output/tfo-client/f0-run4.json` (mp_nexus, `--cwd-bin`): the first
attempt crashed with 0xC00000FD and the retry reached the probes. Both the fixed
static box `render-ab/f0.mdl` and the native ERROR control spawn with the expected
paths and five pose samples. The capture `f0-run4.view0.bmp` (SHA-256
5bf1ad8168e9f3fffcbb2e704efc7f590f5eaf974ae1b2e5240c515aa99579ed) shows the
ERROR control rendered and the compiled box absent. This matches the R1Delta
result, so the invisibility is not specific to R1Delta. The box's
model-bounded trace did not hit it on this run (end at its origin), so that run
gives no collision evidence. The report fails; no threshold was changed.

Two new regressions cover the pilot fallback/view ordering and the startup-crash
retry rule. Direct and locked-uv suites pass 38 tests.

Follow-up runs with fresh compiles of the examples (mp_nexus, TFO client):

| Case | Server telemetry | Window capture |
|---|---|---|
| Static: examples/static_prop box beside native domestic/ashcan_standing (static-s2.json) | both spawn; traces hit the box at 64.0312 and the ashcan at 33.8387 | ashcan renders; compiled box absent (0250495a76a35792e1afd3230a875ba0b2fed62f7c40c75f61fe50370e1a8364) |
| Animated: examples/animated_prop playing bend (anim-s1.json) | bend is sequence 1; probe moves up to 16.5427 inches; trace hit at 6.03125 | compiled model absent (ecbd109a2f536544c96859a9fea2d098aed920316c1156f391eaf7fca95df223) |

No ERROR model replaces the compiled models; they are simply not drawn. Both
rigid static and skinned dynamic models are affected, so the rendering fault
is not specific to the static-prop path. A d3d11.dll access violation
(0xC0000005) before any test marker is now also retried as a startup crash.


## Rendering root cause and passing client runs (4 November 2026)

The invisible-model failure was not in the compiler. The client finds a model's
VVD and VTX through the name stored in the MDL (`$modelname`), not the path
the MDL was loaded from. Every earlier client test mounted compiled models away
from that name (for example `r1c_examples/box.mdl` at `models/r1c_test/box_s2.mdl`).
The server still loaded, animated and collided with them, but the client had no
mesh to draw. Native controls rendered because the game's archives hold their
companions under their stored names. Field-by-field comparison with small native
static props (domestic/sign_beer, haven/dress_01, foliage/ivy_patch_flood_01) found
no header, bone, mesh, VVD or VTX difference that would stop drawing.

Both harnesses now reject a mount that does not match the model's stored name.
The earlier R1Delta and TFO "invisible" results above are superseded by this
cause; the static VTX bone-count correction remains a valid format fix.

| Case (TFO client, mp_nexus) | Telemetry | Window capture |
|---|---|---|
| examples/static_prop box and examples/animated_prop at their stored names (name-match.json) | traces hit at 64.0313 and 6.03125 | both drawn, textured (bad0c460e0985120e973fda26ec4e5c97d68fee2e9c08ae73420f81e44181920) |
| examples/physics_prop beside native domestic/pizza_box (physics-s3.json) | drops 118.65 and 106.81 inches | both drawn, at rest on the ground (6e8dca0eb1bfef81f54188f7ca3f5dc19dfaded99c5ff10d66cab7c2bce07648) |

Compiler SHA-256 unchanged: fdd9852c629b6caab26b930f90f6be7e8c333b961611481b8480a779ea6120a4. Python suites pass 39 tests. These are
smoke tests of the authored examples, not retail roundtrips or full-frame
animation equivalence.

Crash-dialog cleanup: each crashed launch had left a "TFORevive Crash Handler"
dialog open. The harness now closes the `messagebox-win.exe` and
`crashpad_handler.exe` descended from its own crashed launch. In
`test-output/tfo-client/cleanup-3.json`, three consecutive startup crashes
(0xC00000FD) each closed one handler and one dialog, and the fourth attempt
passed; no dialogs remained afterwards. A regression covers the ownership rules
(other launches' and other installs' handlers are left alone). Python suites pass
40 tests.


## Native v52 decompiler and retail corpus round trip (5 November 2026)

`tools/decompile52.py` and `tools/roundtrip52.py` (with `tools/mdl52layout.py`)
decompile, recompile and compare every model in the local Titanfall Online
`assets_dump/models` tree (3,514 models). Final run: `test-output/rt52-full3`,
compiler SHA-256 `86e4f2aa4f6ed5d23fe53d75d76b531c5661e4b98fc7fbdc25fc51da65bfb80d`, 12 jobs.

**3,486 / 3,514 identical in the compared fields.** No model that passed the
previous full run fails in this one. The 28 remaining differences are explained:

| Count | Difference | Cause |
|---:|---|---|
| 23 | Animation world positions off by 0.29-2.89 in (one 13.89 in) | Long cinematic and flight paths (`@cb_space_flyby_*`, `@at_hotdrop_*`, `@ca_Outpost_end_early_escape`). Retail stores them frame-encoded with floats or Vector48; the compiler only writes RLE, whose 16-bit steps over a bone's shared position range are coarser. Needs a frame-encoded writer. |
| 3 | Compile fails: flat or degenerate collision | Retail PHY is a flat hull (pen, fish skeleton, shotgun shell; the pen's is three points with zero volume). The compiler does not build flat hulls. |
| 1 | Compile fails: model has no bones | `weapons/arms/pov_male_anims.mdl` has no bones and only two `$includemodel` references. |
| 1 | Texture list | `worker_base_whistle_tower_holo` lists one material five times; the compiler merges slash/case-equal names. |

The comparison threshold (0.25 in world-space bone positions at the first, middle
and last frames) is the TF2 project's and was not changed.

Format and compiler findings from this work (details in docs/mdl-v52-format.md):

- Frame-encoded animations (descriptor flag 0x40, 9,657 retail animations): layout,
  bone flags (0x40 = float positions) and value order were derived from the corpus;
  decoded rotations are unit quaternions and frame 0 lands near the bind pose.
- `srcbonetransformindex` is file-relative in retail. The compiler wrote it
  relative to the extended header, so the engine would have read the wrong table;
  fixed, with a regression test.
- Scale steps now widen per bone beyond retail's 1/2048 when an animation scales
  more than 16x (1000x-scaled ships); rotation values one rounding step past the
  range edge are clamped, as Valve's scale choice implies; a stored rotation scale
  that the data exceeds is widened instead of failing.
- 24 foliage models have corrupt per-triangle collision blocks (heap addresses as
  vertices); they are rebuilt from the render mesh. `p_f_skits.dx11.vtx` is stale
  (checksum mismatch) and ignored.

Tests: 49 Python tests (including tests/test_decompile52.py) and both CTest groups pass.


## Frame-encoded animation writer and exact retail animation round trip (5 November 2026)

The compiler now writes retail's frame-encoded animation format (`frameanim`), and
its RLE writer stores section-constant channels raw as retail does. Final run
`test-output/rt52-full5`, compiler SHA-256 `e449d2e91cd3f8a802c28bf1f4dbcaa91d57f6cf9f82c15788b3e8ef8219f8ba`:

**3,509 / 3,514 identical in the compared fields** (previously 3,486). All 23
animation-position differences are resolved; no previously passing model fails.
Remaining: 3 flat retail collision hulls, 1 boneless include-only model, 1
duplicated texture name (see the table above).

Causes found and fixed while closing the animation differences:

- Retail cinematic paths store section-constant rotations as raw Quaternion64 and
  positions as raw Vector48; the RLE writer now does the same when a channel is
  constant over a section's own frames, not the bind pose, exact at half precision
  (positions) and accurate as a Quaternion64 (rotations near 180 degrees are not:
  their derived w loses precision, and retail keeps them on the animated grid).
- `$boneposscale` keeps a bone's retail position step (v52 shares one per bone).
  Stored rotation and position steps are kept when every quantized value fits,
  checking each side of the asymmetric -32768..32767 range and ignoring raw
  sections and frame-encoded animations.
- Quaternion48/64 packing overflowed for a component of +1 (for example a roll of
  exactly pi became 0.0156 rad off); the packer now uses -q, which is exact.
- Bind-pose tests compare quaternion components (dot products cannot resolve this
  in float32) and allow for QC angles passing through degrees; `$definebone` is
  decompiled at full precision.
- Float sine/cosine of right angles (about 4e-8) made exact positions inexact after
  the 90 degree root rotation; both the compiler and decompiler now use exact values.
- Some retail Quaternion48 values have x^2 + y^2 + z^2 > 1; both decoders normalize
  them rather than produce a non-orthonormal matrix.

The independent reader (`tools/mdl52.py`) now decodes frame-encoded blocks and raw
RLE channels itself. Tests: 53 Python tests and both CTest groups pass.


## Complete retail round trip (5 November 2026)

Final run `test-output/rt52-full6`, compiler SHA-256 `eb0b03953ebf9d7154f1e06c6fdbd769f837ec4e798582bed52b1f7fac9947cc`:
**3,514 / 3,514 identical in the compared fields.** The last five differences:

- Flat collision (pen, fish skeleton, shotgun shell): retail stores coplanar points
  as a closed zero-volume surface (three points: a two-sided triangle; four: a
  flattened tetrahedron). The compiler now builds the same surface when the points
  span a plane but no volume (front fanned from one corner, back from the next, so
  every edge has two triangles); points, triangles and masses match retail.
- `weapons/arms/pov_male_anims.mdl` has no bones and only includes two models; the
  compiler accepts a bone-less model when it has no bodies, animations or sequences.
- `worker_base_whistle_tower_holo` lists one material five times, one entry per
  mesh. The decompiler gives later copies distinct source names renamed back with
  `$renamematerial`, so the compiler keeps every entry.

Tests: 56 Python tests and both CTest groups pass.


## Original Titanfall corpus (5 November 2026)

Models were extracted from the original Titanfall install (`D:\Games\Titanfall\vpk`,
English `mp_common` and the 25 map VPKs) with pg9182's tf2vpk (sanity checks off for
retail TF1 metadata, CRC checks on): 14,846 model files, **4,131 unique by MDL
SHA-256**, of which 3,229 are byte-identical to Titanfall Online models and 902 are
TF1-only or differ from the Online build.

Run `test-output/rt52-tf1b`, compiler SHA-256 `eb0b03953ebf9d7154f1e06c6fdbd769f837ec4e798582bed52b1f7fac9947cc`:
**4,130 / 4,131 identical in the compared fields.** The same tools and compiler
rerun on Online (`test-output/rt52-full7`) stay at 3,514 / 3,514.

The comparison now also checks each sequence's animation indices.

- `vehicle/goblin_dropship/goblin_dropship_fleetscale_1000x.mdl` (TF1 only) is a
  retail defect: it has one animation but three of its four sequences name
  animations 1-3, past the animation table. A QC cannot express that; the
  decompiler writes those sequences with animation 0 and a comment, so the model
  is reported as differing (the substituted animation also takes the looping flag
  of `idle`).
- Found and fixed through the TF1 set: an empty retail mesh (no triangles) naming
  a material made the decompiler treat that material as used, dropping its
  material-table entry (`vistas/o2_se.mdl`, `debug/debugempty`).

Tests: 56 Python tests and both CTest groups pass.


## Rebuilt retail models in the TFO client (5 November 2026)

Retail models were decompiled, recompiled under `r1c_rebuilt/<original path>` (with
included animation models redirected to rebuilt copies, mounted with the new
`--mount-only` option) and spawned beside the originals in one TFO client scene on
mp_nexus. Reports and captures: `test-output/ig/*.json`, `*.view0.bmp`.

| Case | Result |
|---|---|
| Static: domestic/ashcan_standing | Retail and rebuilt render alike; traces hit both at 33.8387 in |
| Static: domestic/sign_beer | Both spawn; the small flat sign lies in grass and is not a usable visual check |
| Animated (RLE with raw channels): creatures/flyer/flyer_a + flyer_anims, `Idle` | Both render in the same pose; HEADSHOT attachment offset identical (0.00000 in), angles within 0.031 deg |
| Animated (frame-encoded): humans/imc_grunt/battle_rifle + six pete animation models, `CQB_Idle` | Both render in the same pose; R_HAND matches within 0.00005 in and 0.00002 deg over five samples while it moves 3.24 in |
| Physics: domestic/pizza_box | Both drop and settle (104.94 vs 109.25 in, on different terrain) |
| Flat collision: furniture/office_desk_accessories_pen | Both spawn; the downward trace misses both alike (retail is a flat static-only prop and cannot be a prop_physics) |

Python tests: 57 (one new for `--mount-only`); both CTest groups pass.


## Rebuilt original-Titanfall models in R1Delta (6 November 2026)

R1Delta 3.0.4 was launched with `-usemcp +mcp_start_http` and driven through its MCP
server with the new `tools/r1delta_mcp.py` (map load, scene scripts, console log,
camera and screenshots), in a local mp_fracture match. Models came from the original
game's VPKs and were rebuilt under `r1c_rebuilt/` paths beside the originals.
Reports: `test-output/r1d/*-report.json`; screenshots `D:\Games\Titanfall\r1\screenshots`
(`mp_fracture0002.tga` grunts, `mp_fracture0003.tga` ogre poses).

| Case | Result |
|---|---|
| humans/imc_grunt/battle_rifle with the six TF1 pete animation models (frame-encoded, all different from the Online builds), `CQB_Idle` | Both render in the same pose; R_HAND matches within 0.00049 in and 0.00002 deg over five samples while it moves 3.24 in |
| titans/ogre/OgrePoseOpen (TF1-only static, mp_wargames) | Both spawn and render alike; server probes pass |

Harness findings: the TFORevive pilot-settings fallback referenced a function R1Delta
lacks and stopped the scene script (now applied only when it exists); R1Delta indents
addon-list entries with tabs, which the cleanup pattern did not accept (fixed). The
grunt collection was evaluated from its last run boundary because a failed first
include left an earlier BEGIN in the same console session; the strict collector
correctly reported that reuse. Python tests: 60; both CTest groups pass.


## Wide R1Delta comparison of rebuilt original-Titanfall models (6 November 2026)

26 models from the original game (mp_common and mp_fracture), 17 of them TF1-only,
were rebuilt under `r1c_rebuilt/` names with 14 included animation models (the
pete, female and first-person sets, plus the bone-less `pov_male_anims`) and
compared with the originals in one R1Delta match by the new
`tools/r1delta_compare.py`. Report: `test-output/r1d-wide/report2.json`.

**26 / 26 pairs without differences.** All 66 models precached. Across 1871
attachment samples (up to three sequences, three times each, both props set to the
same time) positions agree within 0.00039 in and orientations within 0.00009
deg; bounds are identical; 9 downward traces per pair hit or miss both copies alike
(within 0.001 in). Physics props dropped at the same spot rest within 0.04 in of each
other (drop-pod doors, sentry turret, Titan arc rifle and rocket launcher); human
gibs, weapon world models and a projectile are not spawnable as physics props for
the original either. Categories: statics with LODs, vertex colours, translucency
and flat collision; viewmodels; a turret; a Titan rocket pod; first-person arms and
characters with included animation; physics props.

Screenshots show the originals and rebuilds alike side by side, except viewmodels
and a zero-bounds character, which R1Delta draws for neither copy (checked through
their attachments only), and very small models.

This run found a decompiler bug that the file comparison could not see: retail
viewmodel hand attachments are axis permutations at -90 deg pitch, and their
six-decimal Euler angles rebuilt a rotation up to 64 deg off (positions matched).
The decompiler now writes the stored matrix whenever the written angles do not
rebuild it within 1e-5, and the round trip compares every attachment's bone and
matrix. Under that stricter comparison the corpora stay at 3,514 / 3,514 (Online,
`rt52-full8`) and 4,130 / 4,131 (original, `rt52-tf1c`, the known retail defect).
Compiler SHA-256 `eb0b03953ebf9d7154f1e06c6fdbd769f837ec4e798582bed52b1f7fac9947cc` (unchanged). Python tests: 62; both CTest groups pass.
