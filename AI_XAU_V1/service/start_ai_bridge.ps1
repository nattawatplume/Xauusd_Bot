$ErrorActionPreference = 'Stop'
$servicePath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ollama = Get-Command ollama -ErrorAction Stop
$pythonExe = Join-Path $servicePath '.venv\Scripts\python.exe'

if (-not (Test-Path $pythonExe)) {
    throw 'Run setup_windows.ps1 first.'
}

try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null
} catch {
    Start-Process -FilePath $ollama.Source -ArgumentList 'serve' -WindowStyle Hidden
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        } catch { }
    }
    if (-not $ready) { throw 'Ollama did not become ready at http://127.0.0.1:11434.' }
}

$health = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
$modelName = 'qwen3:4b'
$modelFound = $false
foreach ($model in $health.models) {
    if ($model.name -eq $modelName) { $modelFound = $true; break }
}
if (-not $modelFound) { throw "Model $modelName is missing. Run 'ollama pull $modelName' first." }

Set-Location $servicePath
& $pythonExe (Join-Path $servicePath 'ai_bridge.py')
