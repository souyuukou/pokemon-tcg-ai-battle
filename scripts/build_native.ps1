param([string]$BuildType = "Release")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
cmake -S $root -B "$root/build" -DCMAKE_BUILD_TYPE=$BuildType
cmake --build "$root/build" --config $BuildType --parallel
$built = Get-ChildItem "$root/build" -Recurse -File | Where-Object { $_.Name -match '^(lib)?pokemon_pvs\.(dll|so|dylib)$' } | Select-Object -First 1
if (-not $built) { throw "Native library was not produced" }
Copy-Item $built.FullName "$root/sample_submission/$($built.Name)" -Force
Copy-Item "$root/data/deck_catalog.json" "$root/sample_submission/deck_catalog.json" -Force
