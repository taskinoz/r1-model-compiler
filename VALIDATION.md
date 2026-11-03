# Native v52 validation status

Initial implementation, 3 November 2026. This is an experimental compiler, not a
fully validated replacement for Respawn/Valve studiomdl.

## Compiler and tests

- Release x64 `build/r1studiomdl.exe` SHA-256:
  `f24f5c450464f67e9ca09c2270986999dd1e9196d886ac26e58c9ca60592c42f`.
- Independent reader `tools/mdl52.py` SHA-256:
  `0da97fb62ba116639f5fe890b87f9a4d2b6351c69650820caee6e137a6eb3a7e`.
- 14 native Python regression tests pass. Both CTest groups pass. Locked uv route
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

- Loading/rendering/playback/physics in original Titanfall and Titanfall Online.
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
