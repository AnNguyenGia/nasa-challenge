param(
    [ValidateSet('start', 'stop', 'status', 'logs', 'account')]
    [string]$Action = 'start',
    [string]$Username = 'medical'
)

$ErrorActionPreference = 'Stop'
$composeFile = Join-Path $PSScriptRoot 'astrohealth-backend/compose.yaml'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI chưa được cài. Hãy cài và mở Docker Desktop.'
}

try { docker info --format '{{.ServerVersion}}' *> $null } catch { }
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Engine chưa chạy. Hãy mở Docker Desktop và chờ trạng thái Running.'
}

$composeArgs = @('compose', '-f', $composeFile)
switch ($Action) {
    'start' {
        & docker @composeArgs config -q
        if ($LASTEXITCODE -ne 0) { throw 'Cấu hình Docker Compose không hợp lệ.' }
        & docker @composeArgs up --build -d
        if ($LASTEXITCODE -ne 0) { throw 'Không khởi động được AstroHealth.' }
        Write-Host 'AstroHealth: http://127.0.0.1:8000'
        Write-Host 'Swagger offline: http://127.0.0.1:8000/docs'
        Write-Host 'Tạo tài khoản: .\run-docker.ps1 account medical'
    }
    'stop' {
        & docker @composeArgs down
        if ($LASTEXITCODE -ne 0) { throw 'Không dừng được AstroHealth.' }
        Write-Host 'Đã dừng. Docker volume astro-data vẫn được giữ.'
    }
    'status' { & docker @composeArgs ps }
    'logs' { & docker @composeArgs logs --tail 100 -f backend }
    'account' {
        if ($Username -notmatch '^[a-zA-Z0-9_.-]{3,64}$') {
            throw 'Tên tài khoản phải dài 3-64 ký tự và chỉ dùng chữ, số, _, . hoặc -.'
        }
        & docker @composeArgs exec backend python -m app.cli bootstrap $Username
        if ($LASTEXITCODE -ne 0) { throw 'Không tạo được tài khoản.' }
    }
}
