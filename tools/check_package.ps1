param([string]$Archive = (Join-Path $PSScriptRoot '..\dist\r1-model-compiler-win64.zip'))
# Extracts the release ZIP into a new folder and checks it on its own: the packaged
# executable matches build\r1studiomdl.exe, and every authored example compiles,
# decompiles and recompiles with the packaged tools, matching in every compared field.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$work = Join-Path ([IO.Path]::GetTempPath()) ('r1c-package-' + [guid]::NewGuid().ToString('N'))
try {
    Expand-Archive -LiteralPath $Archive -DestinationPath $work
    $exe = Join-Path $work 'r1studiomdl.exe'
    $built = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'build\r1studiomdl.exe')).Hash
    if ((Get-FileHash -LiteralPath $exe).Hash -ne $built) { throw 'The packaged executable differs from build\r1studiomdl.exe.' }
    $out = Join-Path $work 'out'
    $models = @()
    foreach ($qc in Get-ChildItem -LiteralPath (Join-Path $work 'examples') -Recurse -Filter *.qc) {
        $model = Join-Path $out ($qc.BaseName + '.mdl')
        & $exe -quiet -o $model $qc.FullName
        if ($LASTEXITCODE) { throw "Compiling $($qc.Name) failed." }
        $models += $model
    }
    if ($models.Count -lt 3) { throw 'Expected the three authored examples.' }
    # -I: run the packaged tools without the user's site packages or environment.
    & python -I (Join-Path $work 'tools\roundtrip52.py') --compiler $exe --out (Join-Path $work 'roundtrip') @models
    if ($LASTEXITCODE) { throw 'The packaged examples did not round-trip.' }
    Write-Output "Package check passed: $($models.Count) examples"
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
