param(
  [Parameter(Mandatory=$true)][string]$Excel,
  [string]$OutputRoot = 'results\R04_Y1_S30_strategy_comparison'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$configs = @('ordinary','cutset','pareto','pareto_cutset')
$env:PYTHONPATH = Join-Path $repo 'src'
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
foreach ($strategy in $configs) {
  $out = Join-Path $OutputRoot $strategy
  & $python -m row.cli $Excel --config (Join-Path $repo "configs\r04_s30_$strategy.json") --out $out
  if ($LASTEXITCODE -ne 0) { throw "Strategy $strategy failed with exit code $LASTEXITCODE" }
}
$rows = foreach ($strategy in $configs) {
  $s = Get-Content (Join-Path $OutputRoot "$strategy\summary.json") -Raw | ConvertFrom-Json
  [PSCustomObject]@{strategy=$strategy; objective=$s.objective; UB=$s.UB; LB=$s.LB; gap=$s.gap; iterations=$s.iterations; cuts=$s.cuts; ordinary_cuts=$s.ordinary_cuts; pareto_cuts=$s.pareto_cuts; fallback_cuts=$s.fallback_cuts; seconds=$s.seconds; stopped_by_time_limit=$s.stopped_by_time_limit}
}
$rows | Export-Csv (Join-Path $OutputRoot 'comparison.csv') -NoTypeInformation -Encoding utf8
$rows | ConvertTo-Json | Set-Content (Join-Path $OutputRoot 'comparison.json') -Encoding utf8
