param(
    [ValidateSet('doctor', 'inputs', 'status')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Project Python is missing. See planning/platform.md to restore the environment.'
}
Push-Location -LiteralPath $projectRoot
try {
    & $projectPython -B (Join-Path $PSScriptRoot 'inspect_inputs.py') $Action
    if ($LASTEXITCODE -ne 0) { throw "Project command failed: $Action (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}
