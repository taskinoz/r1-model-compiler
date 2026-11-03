# Titanfall 1 compiler guide

This repository targets native Titanfall 1 / Titanfall Online MDL v52.
Read README.md, VALIDATION.md and docs/mdl-v52-format.md before changing the writer.

- Build with `build.bat`. Run both CTest groups and the Python/locked-uv regressions.
- Add native tests in tests/test_compiler52.py for every supported feature.
- tools/mdl52.py is an independent bounds/geometry reader and RLE decoder.
- tools/survey52.py surveys existing files; it is not a compiler roundtrip test.
- Never widen comparison tolerances to make a model pass. Keep errors visible.
- Native retail files and generated outputs stay ignored in test-output/.
- Keep validation output small; preserve reports, remove regenerated meshes/models.
- tools/legacy_v53, tests/legacy_v53 and docs/reference are historical TF2 material.
  Do not run or cite them as native v52 validation without implementing that target.
- Public GPL/AGPL format references may be consulted, not copied into this MIT code.
- Native validation must cover both original Titanfall and Online, with explicit
  differences and representative in-game evidence before a stable release.
- A v52 version field or structural parse alone is not proof of runtime correctness.
- Research extractor modifications belong in ignored test-output, not the compiler.
- Test reports must identify the executable and reader hashes used for their run.

- R1Delta attach tests: tools/ingame_test_r1delta.py uses IncludeFile, not
  IncludeScript, for loose source. Local script commands silently do nothing with
  sv_cheats=0. Use developer=1 and sv_cheats=1 for this isolated local test.
- R1Delta con_logfile accepted a name but wrote no file. Listen-server
  ServerCommand("screenshot") and ServerCommand("condump") were verified;
  ClientCommand screenshot did not export one. Preserve raw dumps, then evaluate
  only the explicit run BEGIN boundary; never hide diagnostics within that run.
