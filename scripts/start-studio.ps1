$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$studioLogs = Join-Path $studioRoot 'output\logs'
New-Item -ItemType Directory -Path $studioLogs -Force | Out-Null

function Test-StudioUrl([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}

$services = @(
    @{
        Name = 'backend-8000'
        Url = 'http://127.0.0.1:8000/api/projects'
        Executable = Join-Path $studioRoot '.venv\Scripts\python.exe'
        Arguments = @('-m', 'uvicorn', 'server.api.app:app', '--host', '127.0.0.1', '--port', '8000')
        Directory = $studioRoot
    },
    @{
        Name = 'frontend-5173'
        Url = 'http://127.0.0.1:5173/'
        Executable = (Get-Command node -ErrorAction Stop).Source
        Arguments = @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5173', '--strictPort')
        Directory = Join-Path $studioRoot 'web'
    }
)

foreach ($service in $services) {
    if (Test-StudioUrl $service.Url) {
        Write-Host "$($service.Name) is already running."
        continue
    }
    $logPrefix = Join-Path $studioLogs ($service.Name + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Start-Process -FilePath $service.Executable -ArgumentList $service.Arguments `
        -WorkingDirectory $service.Directory -WindowStyle Hidden `
        -RedirectStandardOutput "$logPrefix.stdout.log" `
        -RedirectStandardError "$logPrefix.stderr.log" | Out-Null
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (Test-StudioUrl $service.Url) { $ready = $true; break }
        Start-Sleep -Milliseconds 300
    }
    if (-not $ready) {
        throw "$($service.Name) failed to start. See $logPrefix.stderr.log"
    }
    Write-Host "$($service.Name) started."
}
Write-Host 'Open http://127.0.0.1:5173/ (keep this computer running).'
