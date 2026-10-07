$ErrorActionPreference = 'Stop'
$servicePath = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Get-Command python -ErrorAction Stop

if (-not (Test-Path (Join-Path $servicePath '.env'))) {
    Copy-Item (Join-Path $servicePath '.env.example') (Join-Path $servicePath '.env')
    Write-Host 'Created service/.env. Edit AI_BRIDGE_TOKEN before starting.' -ForegroundColor Yellow
}

if (-not (Test-Path (Join-Path $servicePath '.venv'))) {
    & $python.Source -m venv (Join-Path $servicePath '.venv')
}

Write-Host 'Python environment is ready. This service uses only the Python standard library.' -ForegroundColor Green
Write-Host 'Install Ollama separately, then run: ollama pull qwen3:4b' -ForegroundColor Cyan
