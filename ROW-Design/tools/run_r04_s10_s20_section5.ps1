param([string]$Excel)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $repo 'src'
if (-not $Excel) {
  $match = Get-ChildItem -LiteralPath 'D:\Dropbox' -Recurse -Filter 'R04_Y1.xlsx' -File | Select-Object -First 1
  if ($null -eq $match) { throw 'Could not locate R04_Y1.xlsx under D:\Dropbox' }
  $Excel = $match.FullName
}
foreach ($set in @('S10','S20')) {
  $out = Join-Path $repo "results\R04_Y1_${set}_section5_5min"
  & $python (Join-Path $repo 'run_experiment.py') $Excel --instance R04_Y1 --methods BD-P BD-NR BD-P-NR --output $out --scenarios $set --mip-gap 0.01 --master-time-limit 180 --time-limit 300
  if ($LASTEXITCODE -ne 0) { throw "R04 $set comparison failed with exit code $LASTEXITCODE" }
}
