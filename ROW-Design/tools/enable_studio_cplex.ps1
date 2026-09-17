<#!
Makes the project's pip CPLEX Python wrapper use the locally installed
CPLEX Studio 22.2.0 native library.  The pip library is retained as a
`.community.dll` backup, so this operation is reversible.

Run from the repository root:
  powershell -ExecutionPolicy Bypass -File tools\enable_studio_cplex.ps1
#>
param(
  [string]$StudioRoot = 'C:\Program Files\IBM\ILOG\CPLEX_Studio222'
)

$target = Join-Path $PSScriptRoot '..\.venv\Lib\site-packages\cplex\_internal\cplex2220.dll'
$target = [IO.Path]::GetFullPath($target)
$backup = "$target.community.dll"
$source = Join-Path $StudioRoot 'cplex\bin\x64_win64\cplex2220.dll'
if (-not (Test-Path -LiteralPath $target)) { throw "CPLEX Python package not found: $target" }
if (-not (Test-Path -LiteralPath $source)) { throw "CPLEX Studio DLL not found: $source" }
if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $target -Destination $backup }
Copy-Item -LiteralPath $source -Destination $target -Force
Write-Output "Enabled CPLEX Studio native DLL. Community backup: $backup"
