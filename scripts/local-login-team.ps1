[CmdletBinding()]
param(
    [int]$TeamId = 7
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BackendRoot = Join-Path $ProjectRoot "backend"
$LocalBackendEnv = Join-Path $BackendRoot ".env.local"
$Python = Join-Path $BackendRoot "venv\Scripts\python.exe"
$LoginHelper = Join-Path $PSScriptRoot "local_login_team.py"
$ChromeCandidates = @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
)

if (-not (Test-Path -LiteralPath $LocalBackendEnv)) {
    throw "backend/.env.local was not found. Run scripts\local-start.cmd first."
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Backend virtual environment was not found at $Python"
}
if (-not (Test-Path -LiteralPath $LoginHelper)) {
    throw "Local login helper was not found at $LoginHelper"
}

try {
    $frontendResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5173" -TimeoutSec 5
    if ($frontendResponse.StatusCode -ne 200) {
        throw "Unexpected frontend status: $($frontendResponse.StatusCode)"
    }
} catch {
    throw "Local frontend is not running at http://127.0.0.1:5173"
}

$chrome = $ChromeCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $chrome) {
    throw "Google Chrome was not found."
}

$env:DJANGO_ENV_FILE = $LocalBackendEnv
$env:PYTHONIOENCODING = "utf-8"

Push-Location -LiteralPath $BackendRoot
try {
    $authJson = & $Python $LoginHelper "$TeamId"
    if ($LASTEXITCODE -ne 0) {
        throw "Local test JWT generation failed."
    }
} finally {
    Pop-Location
}

$auth = $authJson | ConvertFrom-Json
$storage = [ordered]@{
    accessToken = $auth.accessToken
    refreshToken = $auth.refreshToken
    kakaoProfile = $auth.kakaoProfile
} | ConvertTo-Json -Depth 6 -Compress
$storageLiteral = $storage | ConvertTo-Json -Compress
$teamCode = [Uri]::EscapeDataString([string]$auth.teamCode)
$targetUrl = "http://127.0.0.1:5173/teams/$teamCode/admin"
$targetLiteral = $targetUrl | ConvertTo-Json -Compress
$loginCommand = "localStorage.setItem('mymanito.auth', $storageLiteral); location.href = $targetLiteral;"
Set-Clipboard -Value $loginCommand

$chromeProfile = Join-Path $ProjectRoot "tmp\chrome-team-$TeamId"
if (-not (Test-Path -LiteralPath $chromeProfile)) {
    New-Item -ItemType Directory -Path $chromeProfile | Out-Null
}
Start-Process -FilePath $chrome -ArgumentList @(
    "--user-data-dir=$chromeProfile",
    "--no-first-run",
    "--no-default-browser-check",
    "http://127.0.0.1:5173"
) | Out-Null

Write-Output "Chrome local test profile is open."
Write-Output "Selected administrator: $($auth.adminName) (User ID $($auth.adminUserId))"
if ($null -ne $auth.participantId) {
    Write-Output "Team participant: $($auth.participantName) (ID $($auth.participantId), $($auth.score) points)"
}
Write-Output "In the new Chrome window, open DevTools Console, paste the clipboard, and press Enter."
Write-Output "If Chrome blocks pasting, type 'allow pasting' first."
