<#
.SYNOPSIS
Membangun Ground Station menjadi satu executable menggunakan PyInstaller.
#>

Write-Host "Mempersiapkan proses build MDI_Ground.exe" -ForegroundColor Cyan

# Pindah ke Root Folder (Prototype)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
Set-Location -Path $RootDir

# Cek Installasi
if (-not (Get-Command "pyinstaller" -ErrorAction SilentlyContinue)) {
    Write-Warning "Pyinstaller tidak tersedia. Pastikan .venv aktif dan jalankan: pip install pyinstaller"
    exit
}

# Bersihkan sisa build sebelumnya
if (Test-Path ".\build") { Remove-Item -Recurse -Force ".\build" }
if (Test-Path ".\dist") { Remove-Item -Recurse -Force ".\dist" }
if (Test-Path ".\MDI_Ground.spec") { Remove-Item -Force ".\MDI_Ground.spec" }

Write-Host "Sedang mengemas MDI_Ground..." -ForegroundColor Yellow

# Proses PyInstaller
# --onefile : Jadikan satu file
# --windowed : Hilangkan Background Terminal (console) karena pakai PyQt
# --uac-admin : Auto "Run As Administrator" (Wajib untuk PowerShell Static IP adapter)
# --add-data : Masukkan asset file statis (.qss UI Themes)

pyinstaller --noconfirm `
    --onefile `
    --name "MDI_Ground" `
    --uac-admin `
    --hidden-import="uvicorn" `
    --hidden-import="uvicorn.logging" `
    --hidden-import="uvicorn.loops" `
    --hidden-import="uvicorn.loops.auto" `
    --hidden-import="uvicorn.protocols" `
    --hidden-import="uvicorn.protocols.http" `
    --hidden-import="uvicorn.protocols.http.auto" `
    --hidden-import="uvicorn.protocols.websockets" `
    --hidden-import="uvicorn.protocols.websockets.auto" `
    --hidden-import="uvicorn.lifespan" `
    --hidden-import="uvicorn.lifespan.on" `
    --hidden-import="fastapi" `
    --hidden-import="pydantic" `
    --hidden-import="starlette" `
    --hidden-import="anyio" `
    --hidden-import="h11" `
    --add-data "darat/ui/styles/mdi_theme.qss;darat/ui/styles" `
    darat/main.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build Berhasil! Aplikasi MDI_Ground.exe dapat ditemukan di folder 'dist'." -ForegroundColor Green
} else {
    Write-Host "Build gagal. Periksa log error sebelumnya." -ForegroundColor Red
}
