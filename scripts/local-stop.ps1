[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$LocalBackendEnv = Join-Path $ProjectRoot "backend\.env.local"
$ComposeFile = Join-Path $ProjectRoot "docker-compose.local.yml"
$RuntimeRoot = Join-Path $ProjectRoot "tmp\local-dev"
$StatePath = Join-Path $RuntimeRoot "processes.json"
$ComposeProject = "mymanito-local"

function Stop-VerifiedProcessTree {
    param([int]$ProcessId)
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if (-not $processInfo) {
        return
    }
    $commandLine = [string]$processInfo.CommandLine
    $executablePath = [string]$processInfo.ExecutablePath
    if (-not $commandLine.Contains($ProjectRoot) -and -not $executablePath.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to stop PID $ProcessId because it is not a MyManito local process."
    }

    $pending = New-Object System.Collections.Queue
    $pending.Enqueue($ProcessId)
    $processIds = New-Object System.Collections.Generic.List[int]
    while ($pending.Count -gt 0) {
        $parentId = [int]$pending.Dequeue()
        $processIds.Add($parentId)
        foreach ($child in Get-CimInstance Win32_Process -Filter "ParentProcessId = $parentId" -ErrorAction SilentlyContinue) {
            $pending.Enqueue([int]$child.ProcessId)
        }
    }
    for ($index = $processIds.Count - 1; $index -ge 0; $index--) {
        Stop-Process -Id $processIds[$index] -Force -ErrorAction SilentlyContinue
    }
}

Set-Location -LiteralPath $ProjectRoot

if (Test-Path -LiteralPath $StatePath) {
    $state = Get-Content -LiteralPath $StatePath -Encoding utf8 | ConvertFrom-Json
    if ([System.IO.Path]::GetFullPath([string]$state.project_root) -ne $ProjectRoot) {
        throw "Refusing to use a process state file from another workspace."
    }
    foreach ($processId in @($state.frontend_pid, $state.backend_pid)) {
        if ($processId) {
            Stop-VerifiedProcessTree -ProcessId ([int]$processId)
        }
    }
    $resolvedStatePath = [System.IO.Path]::GetFullPath($StatePath)
    if (-not $resolvedStatePath.StartsWith($RuntimeRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove an unexpected state file: $resolvedStatePath"
    }
    Remove-Item -LiteralPath $resolvedStatePath -Force
}

$composeArgs = @("compose", "--project-name", $ComposeProject)
if (Test-Path -LiteralPath $LocalBackendEnv) {
    $composeArgs += @("--env-file", $LocalBackendEnv)
}
$composeArgs += @("-f", $ComposeFile, "stop")
& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw "docker compose stop failed with exit code $LASTEXITCODE"
}

Write-Output "MyManito local development stack is stopped. Local database data was preserved."
