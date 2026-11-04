# Titanfall 1 model compiler

`r1studiomdl` is an experimental native **Titanfall 1 MDL v52** compiler for QC,
SMD and DMX sources. It is a separate project derived from the MIT-licensed
[r2-model-compiler](https://github.com/taskinoz/r2-model-compiler), retaining its
source frontend and build pipeline but writing the native v52 layouts.

Titanfall Online's locally inspected models also use v52. They are useful format
references, but matching that version does not establish runtime compatibility.
The authored examples pass **TFORevive dedicated-server and client** runs, and
**3,509 of 3,514 retail Titanfall Online models round-trip** through the v52
decompiler and compiler with every compared field matching.
See [VALIDATION.md](VALIDATION.md) for the precise evidence and limitations.

## Build and use

Install Visual Studio 2022 with C++ tools and CMake, then run:

```powershell
.\build.bat
.\build\r1studiomdl.exe examples\static_prop\box.qc
.\build\r1studiomdl.exe -o out\box.mdl examples\static_prop\box.qc
```

Output is a `.mdl` plus `.dx11.vtx` and `.vvd` for render geometry, `.phy` when
collision is present, and `.vvc` when vertex colours or a second UV set are used.
Keep companions together: their checksums must match. Recompilation removes stale
optional companions for that output basename. `-game`, `-outdir`, `-path`,
`-verbose` and `-quiet` are supported.

The initial implementation includes:

- QC parsing, SMD and DMX input inherited from the TF2 frontend.
- Native v52 primary and extended headers, bones, models, meshes and materials.
- Native four-byte bone animation records and eight-byte section table entries.
- Bone-level position scales shared across animations, rotation and scale RLE.
- Static triangle collision, authored rigid physics and jointed PHY output.
- Attachments, hitboxes, sequences, includes and native IK-rule serialization.

The animation writer emits RLE by default, storing channels that are constant over a
section raw (Quaternion64 rotations, Vector48 positions) as retail does. The
`frameanim` animation option writes retail's frame-encoded format instead. External
`.ani` blocks are not written. The initial encoder supports at most 255 bones. `$uipanel` and bone
followers are rejected because their v52 representation is not implemented.
Inherited QC options are not all individually validated for TF1.

This is not a Portal/SFM compiler or a direct importer for their compiled MDLs.
Source models can be decompiled to QC/SMD/DMX and compiled for this target, subject
to differences in supported features. Direct Source `.phy` import is not implemented;
use its decompiled collision mesh. No proprietary game data is distributed.

## Decompiling retail models

`tools/decompile52.py` turns a v52 model into a QC with SMD/DMX sources that
`r1studiomdl` rebuilds, as `decompile53.py` does for Titanfall 2. It reads the
companions beside the `.mdl`: `.vvd` (with fixup tables), `.dx11.vtx`, `.vvc`, `.phy`
and the external `.ani` holding animation blocks. It decodes every retail animation
encoding: RLE (raw Quaternion48/64 and Vector48 channels included), frame-encoded
animations, sections and animation blocks. Companions whose checksum does not
match the MDL are ignored, as the game would.

```powershell
python tools\decompile52.py "D:\path\to\models\robots\marvin\marvin.mdl" out\marvin
.\build\r1studiomdl.exe -o out\marvin\rebuilt.mdl out\marvin\marvin.qc
python tools\roundtrip52.py --jobs 12 --discard-sources --out test-output\rt52 "D:\path\to\models"
```

`roundtrip52.py` decompiles, recompiles and compares each model: name, header
flags, bones and bind pose, textures, triangle counts and LOD 0 corner positions,
sequences, animation world positions (0.25 in), IK rules, bone scale, PHY solids and
volume, attachments, hitbox sets and procedural bones. It checkpoints
`results.json`; `--resume` continues a run.

The decompiler writes these r1c QC extensions where retail cannot be derived:
`$singleframeflag` (sequence flag 0x80000 on single-frame sequences, set per model
by some retail builds), `$texture "name"` (material entries no mesh uses),
`$boneposscale` (a bone's retail position step, kept when the data fits it) and the
animation options `frameanim` (frame-encoded, as retail stored it) and `noscaleflag`
(scaled bones without HAS_SCALE).

## Tests and inspection

```powershell
Push-Location build
ctest --output-on-failure
Pop-Location
python -m unittest discover -s tests -p "test_*.py"
uv run --locked python -m unittest discover -s tests -p "test_*.py"
python tools\mdl52.py out\box.mdl --decode
python tools\survey52.py "D:\path\to\extracted\models" --out test-output\survey.json
```

Python 3.10+ and the standard library are sufficient. `R1C_COMPILER` selects an
alternate executable. The reader checks file bounds, native tables, companion
checksums, VVD vertex/skin/fixup data and packed DX11 strip indices. `--decode`
decodes every frame of compiler-produced RLE; raw, frame and external retail
animation encodings are not supported by that decoder yet.

`tools/legacy_v53`, `tests/legacy_v53` and `docs/reference` preserve the inherited
TF2 tools and evidence for reference. They are **not native v52 tools or validation**.
The old Northstar harness is TF2-specific and must not be used to claim TF1 results.

## Format references

- [r-ex/rmdlconv](https://github.com/r-ex/rmdlconv): consult-only v52 struct notes;
  no GPL conversion code is incorporated into this MIT project.
- [Valve Source SDK](https://github.com/ValveSoftware/source-sdk-2013): Source
  model ancestry and runtime semantics; Portal/SFM variants are not identical to v52.
- [Native format notes](docs/mdl-v52-format.md).

Avoid keeping repeated corpus rebuilds. Preserve small JSON/log reports and delete
recreatable output after a run; retail samples should remain outside version control.

## Titanfall Online runtime harness

`tools/ingame_test52.py` stages a temporary TFORevive mod, mounts every companion
with verified hashes, and appends a test-script include to a temporary copy of the
installed core map-spawn script. It does not edit the original core mod. It launches
the installed `Bin/TFO.exe` on a local map, collects run-specific telemetry and
removes its owned mod when finished. Close an existing TFO game before running it.

```powershell
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --sequence= --report test-output\tfo-static.json out\box.mdl=models/r1c_examples/box.mdl
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --sequence bend --attachment probe --report test-output\tfo-animation.json out\animated_prop.mdl=models/r1c_examples/animated_prop.mdl
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --physics --report test-output\tfo-physics.json out\physics_box.mdl=models/r1c_examples/physics_box.mdl
```

Multiple model mappings allow a compiled model and native control side by side.
**Mount each model at its `$modelname` path** (`models/` + the name stored in the
MDL); both harnesses reject any other path. The client finds a model's VVD and VTX
through that stored name, not the path the MDL was loaded from. A model mounted
elsewhere still precaches, animates and collides on the server, but the client
draws nothing and shows no error. Native controls are mounted at their own game
paths.
An empty `--sequence=` skips animation for static controls that have different
sequence names. `--prepare-only` validates staging without launching; its report
always has `passed: false`, and the mod is still cleaned up. `--keep-mod` retains
it for debugging. `--cwd-bin` tests older builds that expect Bin as their working
folder. `TITANFALL_ONLINE_DIR` can supply the game directory.

Reports contain native inspections, mounted SHA-256 hashes, executable/harness/
reader hashes, requested command, per-run events, exit code and cleanup outcome.
The script logs model precaches/spawns, sequence lookup/playback, traces, five pose
and optional attachment samples, and physics drop distances. New screenshots in
known screenshot folders are listed with hashes; visually inspect these separately.
A smoke-test pass is not full render/animation/collision equivalence.

Client runs (no `--dedicated`) should use `--cwd-bin`. The harness handles three
things the TFO client needs, learned from MRVN-Radiant's `tools/respawn/tfo_harness.py`:
- **Startup crashes:** the GPU driver sometimes overflows the stack (0xC00000FD)
  (0xC00000FD) or crashes in `d3d11.dll` (0xC0000005) while TFO starts. Such
  launches are retried, up to `--attempts` (default 3), only if the test script
  had logged nothing. After any crashed launch, the harness closes the
  "TFORevive Crash Handler" dialog (`messagebox-win.exe`) and `crashpad_handler.exe`
  that the launch started. Only handlers descended from that launch and running
  from this install's `Bin` are closed; each attempt records what it closed.
- **Offline spawning:** offline sessions have no loadout, so the core script's
  pilot settings file is null and the player never spawns. The test script falls
  back to the stock `pilot_male_fastest` only when the original lookup fails.
- **Screenshots:** the engine `screenshot` command leaves no file. After the
  player leaves the dropship, the script rests each prop on the ground, levels
  the camera and logs `VIEW 0`. The harness then raises the game window and saves
  its client area as `<report>.view0.bmp`, listed under `window_captures`.

```powershell
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --cwd-bin --sequence= --timeout 300 --report test-output\tfo-client.json out\box.mdl=models/r1c_examples/box.mdl <native ashcan_standing.mdl>=models/domestic/ashcan_standing.mdl
```

Only one TFO instance can run, and other tools (such as MRVN-Radiant's map
harness) share `Mods/` and `Logs/tforevive.log`; the harness refuses to start
while `TFO.exe` or `tfods.exe` is running. Window captures are for visual review
and are not counted as a pass.

**Current runtime status (4 November 2026):** the authored static, animated and
physics examples pass dedicated-server tests and full TFO client runs on mp_nexus,
and render beside native controls in the captured game window. The earlier
"invisible model" failure was the harness mounting models away from their
`$modelname` path. Native retail roundtrips remain unvalidated.

### Direct no-auth launch and dedicated tests

The installed TFO.exe requires an `--authToken` argument even when its SDK is using
`-noauth`. The harness supplies the literal non-credential `r1c-local-noauth` and
keeps `-noauth`; it does not read or use account tokens. Dedicated mode launches
the installed `Bin/tfods.exe` directly, with no client token or renderer.

```powershell
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --dedicated --sequence= --require-trace 0 --report test-output\tfo-static.json out\box.mdl=models/r1c_examples/box.mdl
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --dedicated --sequence bend --attachment probe --min-attachment-displacement 1 --require-trace 0 --report test-output\tfo-animation.json out\animated_prop.mdl=models/r1c_examples/animated_prop.mdl
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --dedicated --physics --report test-output\tfo-physics.json out\physics_box.mdl=models/r1c_examples/physics_box.mdl
```

The headless script waits for map entities to load and uses a real spawn point.
TF1 vector methods and model-bounded traces are used. `--require-trace INDEX`
requires a hit on that exact model. `--min-attachment-displacement N` requires the
sampled attachment to move at least N inches and records its maximum displacement.
These smoke-test requirements do not assert full animation/collision equivalence.

Recorded server results: static box hit at 64.0313 inches, animated probe movement
16.5427875 inches with a collision hit, compiled physics drop 135.535 inches, native
physics control drop 121.785 inches. All three final runs exit cleanly and remove
their temporary mods. See VALIDATION.md for source/report hashes and limitations.


## R1Delta local-match harness

`tools/ingame_test_r1delta.py` prepares an owned addon and a short console cfg for
an already running R1Delta client. It uses the normal launcher and local match;
it does not change authentication or core game files. Preparation enables only
its unique addon entry while preserving other entries. A newly mounted addon
may require one match restart.

```powershell
python tools\ingame_test_r1delta.py prepare --game "D:\Games\Titanfall" --session test-output\delta-session.json out\box.mdl=models/r1c_examples/box.mdl
# Run the printed exec r1c_<run-id> command in the game's local-match console.
python tools\ingame_test_r1delta.py collect --session test-output\delta-session.json --report test-output\delta-report.json
# After finishing the test (preferably after closing the game):
python tools\ingame_test_r1delta.py cleanup --session test-output\delta-session.json
```

The cfg enables `developer 1` and `sv_cheats 1` in the local match, loads the
run-specific source with `IncludeFile`, and closes the console. Addons must already
be mounted; restart the game after first preparation if necessary. The script
waits for Playing and another twelve
seconds before placing the models above nearby terrain, levels the camera, runs
five pose/attachment samples and collision/optional physics probes, requests a
screenshot, and leaves the scene open. `--sequence`, `--attachment`, and `--physics`
are prepare options. Use multiple mappings for a native control beside the rebuild.
Use a new session and a new `$modelname` for each compile to avoid engine model-cache reuse.

`collect --timeout 90` watches fresh native console dumps for that run's BEGIN
boundary. The listen-server script exports the dump automatically when finished.
`--log path/to/condump.txt`
can evaluate an explicitly saved console dump instead. Reports include staged
hashes, requested probes, exact model paths, and hashes of newly found screenshots.
`server_passed` records the smoke probes; `visual_passed` and overall `passed`
remain false because log events cannot establish visible geometry. Review the
screenshots separately. The one-command scene, automatic screenshot, console dump
and collection were
verified in a live R1Delta local match. Those R1Delta runs mounted the box away from
its `$modelname` path, which is why it was not drawn (see below).

Cleanup removes only the owned addon, its unchanged cfg and its addon-list entry;
other addon changes made during testing survive. It preserves logs/screenshots.
The cfg enables developer/cheat commands for this local test session; restore
your preferred `developer` and `sv_cheats` values afterward. This attach harness
does not claim unattended
launcher-to-match automation.
