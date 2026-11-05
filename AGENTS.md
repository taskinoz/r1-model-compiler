# Titanfall 1 compiler guide

This repository targets native Titanfall 1 / Titanfall Online MDL v52.
Read README.md, VALIDATION.md and docs/mdl-v52-format.md before changing the writer.

- Build with `build.bat`. Run both CTest groups and the Python/locked-uv regressions.
- Add native tests in tests/test_compiler52.py for every supported feature.
- tools/mdl52.py is an independent bounds/geometry reader and RLE decoder.
- tools/survey52.py surveys existing files; it is not a compiler roundtrip test.
- tools/decompile52.py turns a retail v52 model (+ .vvd/.dx11.vtx/.vvc/.phy/.ani
  beside it) into QC + SMD/DMX that r1studiomdl rebuilds, like the TF2 project's
  decompile53.py. tools/mdl52layout.py holds its struct layouts.
  tools/roundtrip52.py decompiles, recompiles and compares a corpus
  (`--jobs`, `--resume`, `--discard-sources`; results.json per model). Tests:
  tests/test_decompile52.py. A full Online corpus run takes about an hour at 12 jobs.
- Original Titanfall models: extract `models` from `vpk\englishclient_mp_*.bsp.pak000_dir.vpk`
  with pg9182's tf2vpk (`tf2vpk unpack <vpk> <out> --include models`, with
  `TF2VPKDEBUG=nosanitycheck`: retail TF1 metadata fails its sanity checks; CRC
  checks stay on). One folder per VPK, then keep one copy per MDL SHA-256 with its
  companions: 14,846 files give 4,131 unique models (3,229 identical to Online).
- Rebuilding build\r1studiomdl.exe while a corpus run uses it breaks that run; use
  build-dev.bat for experiments meanwhile.
- Retail format facts found by decompiling (frame-encoded animations, RLE raw
  channels, VVD fixups, anim blocks, file-relative srcbonetransformindex, stale
  companions) are in docs/mdl-v52-format.md. Check a new rule against the whole
  corpus before relying on it.
- R1Delta (original Titanfall) can be driven unattended: launch
  `%LOCALAPPDATA%\R1Delta\app-3.0.4\r1delta.exe -usemcp +mcp_start_http`, then use
  tools/r1delta_mcp.py (Streamable HTTP at 127.0.0.1:8765/; send no protocol header
  until initialize negotiates one). Its tools: execute_console_command,
  execute_squirrel (server/client/ui), get_game_state, get_console_log (last 50
  lines). PrecacheModel works mid-match, but a character fails until its included
  animation models are precached. Addon autorun scripts did not run on a listen
  server. R1Delta writes addonlist.txt entries indented with tabs.
- In R1Delta scripts: Anim_Play then Anim_SetInitialTime(t) sets an exact animation
  time; move a noclipping camera with the `setpos` console command (a script
  SetOrigin did not move it). Viewmodel (ptpov_*) models and characters with zero
  bounds are not drawn as world props, original or rebuilt. Weapon world models,
  gibs and projectiles are not spawnable prop_physics.
- Shell edits through a bash heredoc can mangle backslashes in Python strings; write
  patch scripts to a file instead.
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
