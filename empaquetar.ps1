# Construye dist\cronica\cronica.exe (carpeta, no un solo fichero: así el arranque es rápido).
# Uso: powershell -File empaquetar.ps1 [-Ffmpeg <carpeta con ffmpeg.exe>]
param([string]$Ffmpeg = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m PyInstaller --noconfirm --clean --onedir --console --name cronica --icon assets\cronica.ico `
  --add-data "cronica/reproductor;cronica/reproductor" --collect-data playwright lanzador.py
if ($Ffmpeg) { Copy-Item (Join-Path $Ffmpeg "ffmpeg.exe") dist\cronica\ }
Write-Host "Listo: dist\cronica\cronica.exe"
