# Titanfall 1 model compiler

`r1studiomdl` is an experimental native **Titanfall 1 MDL v52** compiler for QC,
SMD and DMX sources. It is a separate project derived from the MIT-licensed
[r2-model-compiler](https://github.com/taskinoz/r2-model-compiler), retaining its
source frontend and build pipeline but writing the native v52 layouts.

Titanfall Online's locally inspected models also use v52. They are useful format
references, but matching that version does not establish runtime compatibility.
Selected **TFORevive dedicated-server loading, animation, collision and physics
smoke tests pass**. Client rendering and a native retail decompile/recompile corpus
remain pending.
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

The native animation writer currently emits RLE, not frame encoding or external
`.ani` blocks. The initial encoder supports at most 255 bones. `$uipanel` and bone
followers are rejected because their v52 representation is not implemented.
Inherited QC options are not all individually validated for TF1.

This is not a Portal/SFM compiler or a direct importer for their compiled MDLs.
Source models can be decompiled to QC/SMD/DMX and compiled for this target, subject
to differences in supported features. Direct Source `.phy` import is not implemented;
use its decompiled collision mesh. No proprietary game data is distributed.

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
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --sequence= --report test-output\tfo-static.json out\box.mdl=models/r1c_test/box.mdl
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --sequence bend --attachment probe --report test-output\tfo-animation.json out\animated.mdl=models/r1c_test/animated.mdl
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --physics --report test-output\tfo-physics.json out\physics.mdl=models/r1c_test/physics.mdl
```

Multiple model mappings allow a compiled model and native control side by side.
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

**Current runtime status (4 November 2026):** native dedicated-server tests pass for
the authored static, animated and physics examples. Client startup now gets past
the launcher argument gate but crashes in the GPU driver before the model tests.
R1Delta reaches local matches: the compiled static box passes spawn/pose/collision
probes, but remains invisible beside a visible native control. Client rendering
and native retail roundtrips remain unvalidated.

### Direct no-auth launch and dedicated tests

The installed TFO.exe requires an `--authToken` argument even when its SDK is using
`-noauth`. The harness supplies the literal non-credential `r1c-local-noauth` and
keeps `-noauth`; it does not read or use account tokens. Dedicated mode launches
the installed `Bin/tfods.exe` directly, with no client token or renderer.

```powershell
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --dedicated --sequence= --require-trace 0 --report test-output\tfo-static.json out\box.mdl=models/r1c_test/box.mdl
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --dedicated --sequence bend --attachment probe --min-attachment-displacement 1 --require-trace 0 --report test-output\tfo-animation.json out\animated.mdl=models/r1c_test/animated.mdl
python tools\ingame_test52.py --game "D:\Games\Titanfall Online" --dedicated --physics --report test-output\tfo-physics.json out\physics.mdl=models/r1c_test/physics.mdl
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
