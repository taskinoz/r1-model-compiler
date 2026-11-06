param([string]$OutputDirectory = (Join-Path $PSScriptRoot '..\dist'))
# Builds dist\r1-model-compiler-win64.zip from build\r1studiomdl.exe, the Python
# tools, documentation and authored examples. No game files are packaged.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$compiler = Join-Path $projectRoot 'build\r1studiomdl.exe'
if (!(Test-Path -LiteralPath $compiler)) { throw 'Run build.bat before packaging.' }
$package = Join-Path $OutputDirectory 'r1-model-compiler'
# A stale folder would be packed along with the new files.
if (Test-Path -LiteralPath $package) { Remove-Item -LiteralPath $package -Recurse -Force }
New-Item -ItemType Directory -Path $package -Force | Out-Null
Copy-Item -LiteralPath $compiler -Destination $package
foreach ($file in @('README.md', 'LICENSE', 'VALIDATION.md')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $file) -Destination $package
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'examples') -Destination $package -Recurse
$docs = Join-Path $package 'docs'
New-Item -ItemType Directory -Path $docs -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\mdl-v52-format.md') -Destination $docs
$toolDestination = Join-Path $package 'tools'
New-Item -ItemType Directory -Path $toolDestination -Force | Out-Null
foreach ($tool in @('decompile52.py', 'mdl52.py', 'mdl52layout.py', 'phy.py', 'roundtrip52.py', 'survey52.py',
                    'ingame_test52.py', 'ingame_test_r1delta.py', 'r1delta_mcp.py', 'r1delta_compare.py')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot "tools\$tool") -Destination $toolDestination
}
$archive = Join-Path $OutputDirectory 'r1-model-compiler-win64.zip'
if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
Compress-Archive -Path (Join-Path $package '*') -DestinationPath $archive
$sums = Join-Path $OutputDirectory 'SHA256SUMS.txt'
$lines = foreach ($item in @($archive, $compiler)) {
    '{0}  {1}' -f (Get-FileHash -LiteralPath $item -Algorithm SHA256).Hash.ToLower(), (Split-Path $item -Leaf)
}
[IO.File]::WriteAllText($sums, ($lines -join "`n") + "`n")
Get-Content -LiteralPath $sums
