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
crash still prevents rendering validation. Physics control geometry differs from
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
