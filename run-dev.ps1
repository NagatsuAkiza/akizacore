<#
.SYNOPSIS
    Menjalankan AkizaCore dalam mode development (Bot, Backend API, dan React Dashboard).

.DESCRIPTION
    Script ini membungkus scripts/dev.py untuk menjalankan Bot, Uvicorn (FastAPI),
    dan Vite (React Dashboard) dalam satu jendela terminal.
    Cukup tekan Ctrl + C untuk mematikan semua service secara bersih.

.EXAMPLE
    .\run-dev.ps1
    Menjalankan Bot, API, dan Dashboard bersamaan.

.EXAMPLE
    .\run-dev.ps1 -NoBot
    Hanya menjalankan Backend API dan Dashboard.

.EXAMPLE
    .\run-dev.ps1 -ApiOnly
    Hanya menjalankan Backend API.
#>

param(
    [switch]$NoBot,
    [switch]$NoApi,
    [switch]$NoDashboard,
    [switch]$ApiOnly,
    [switch]$BotOnly,
    [switch]$DashboardOnly,
    [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    Write-Host "[ERROR] Virtualenv Python tidak ditemukan di $VenvPy" -ForegroundColor Red
    Write-Host "Silakan buat venv terlebih dahulu: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

$ArgsList = @("scripts\dev.py")
if ($NoBot) { $ArgsList += "--no-bot" }
if ($NoApi) { $ArgsList += "--no-api" }
if ($NoDashboard) { $ArgsList += "--no-dashboard" }
if ($ApiOnly) { $ArgsList += "--api-only" }
if ($BotOnly) { $ArgsList += "--bot-only" }
if ($DashboardOnly) { $ArgsList += "--dashboard-only" }
if ($ApiPort -ne 8000) { $ArgsList += @("--api-port", $ApiPort) }

& $VenvPy @ArgsList
