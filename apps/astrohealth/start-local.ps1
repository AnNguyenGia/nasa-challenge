$ErrorActionPreference = 'Stop'
$env:ASTRO_BIND_PORT = '8002'
Set-Location -LiteralPath (Join-Path $PSScriptRoot 'astrohealth-backend')
$pythonPath = Join-Path $PWD '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    py -3.12 -m venv .venv
    & $pythonPath -m pip install --no-cache-dir -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
}
& $pythonPath -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
& $pythonPath scripts\build_demo_models.py
& $pythonPath -m app.cli seed
Write-Host 'AstroHealth local console: http://127.0.0.1:8002 | API: /docs'
Write-Host 'First account: .venv\Scripts\python.exe -m app.cli bootstrap medical'
& $pythonPath -m app.cli serve
