[CmdletBinding()]
param(
    [switch]$RefreshDbFromNas,
    [int]$PostgresPort = 55432,
    [int]$RedisPort = 56379,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$NasTunnelPort = 15432
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BackendRoot = Join-Path $ProjectRoot "backend"
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$LocalBackendEnv = Join-Path $BackendRoot ".env.local"
$LocalFrontendEnv = Join-Path $FrontendRoot ".env.local"
$ProductionBackendEnv = Join-Path $BackendRoot ".env"
$ComposeFile = Join-Path $ProjectRoot "docker-compose.local.yml"
$LocalPostgresData = Join-Path $ProjectRoot "data\local-postgres"
$BackupRoot = Join-Path $ProjectRoot "data\local-db-backups"
$RuntimeRoot = Join-Path $ProjectRoot "tmp\local-dev"
$StatePath = Join-Path $RuntimeRoot "processes.json"
$ComposeProject = "mymanito-local"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8File {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
}

function Read-DotEnv {
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $values
    }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding utf8) {
        if ($line -match "^\s*([^#=\s]+)\s*=\s*(.*)\s*$") {
            $value = $matches[2]
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $values[$matches[1]] = $value
        }
    }
    return $values
}

function New-RandomSecret {
    $bytes = New-Object byte[] 48
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
}

function Invoke-Native {
    param([string]$FilePath, [string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

function Set-ProcessEnvironment {
    param([hashtable]$Values)
    foreach ($entry in $Values.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
    }
}

function Test-TcpPort {
    param([int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        return $result.AsyncWaitHandle.WaitOne(250) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-ForPort {
    param([int]$Port, [string]$Name)
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (Test-TcpPort -Port $Port) {
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not open port $Port"
}

function Assert-LocalPostgresTarget {
    param([string[]]$ComposeArguments)
    $containerId = (& docker @ComposeArguments ps -q postgres).Trim()
    if (-not $containerId) {
        throw "Local PostgreSQL container was not found."
    }
    $containerInfo = (& docker inspect $containerId | ConvertFrom-Json)[0]
    $projectLabel = [string]$containerInfo.Config.Labels."com.docker.compose.project"
    if ($projectLabel -ne $ComposeProject) {
        throw "Refusing database operation on unexpected Compose project: $projectLabel"
    }
    $mountSource = [string]($containerInfo.Mounts | Where-Object { $_.Destination -eq "/var/lib/postgresql/data" } | Select-Object -First 1).Source
    $expectedSource = [System.IO.Path]::GetFullPath($LocalPostgresData)
    if ([System.IO.Path]::GetFullPath($mountSource) -ne $expectedSource) {
        throw "Refusing database operation on unexpected data path: $mountSource"
    }
}

function Assert-NasSshTunnel {
    param([int]$Port)
    $listener = Get-NetTCPConnection -State Listen -LocalAddress "127.0.0.1" -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) {
        throw "NAS SSH tunnel is not reachable at 127.0.0.1:$Port"
    }
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if (-not $owner -or $owner.ProcessName -ne "ssh") {
        $ownerName = if ($owner) { $owner.ProcessName } else { "unknown" }
        throw "Refusing NAS dump because 127.0.0.1:$Port is owned by $ownerName, not an SSH tunnel."
    }
}

function Stop-LocalProcess {
    param([System.Diagnostics.Process]$Process)
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
}

Set-Location -LiteralPath $ProjectRoot

foreach ($directory in @($LocalPostgresData, $BackupRoot, $RuntimeRoot)) {
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory | Out-Null
    }
}

if (-not (Test-Path -LiteralPath $ProductionBackendEnv)) {
    throw "backend/.env is required to copy the existing Kakao development credentials."
}

$productionEnv = Read-DotEnv -Path $ProductionBackendEnv
if (-not (Test-Path -LiteralPath $LocalBackendEnv)) {
    $localBackendLines = @(
        "DJANGO_SECRET_KEY=$(New-RandomSecret)",
        "JWT_SIGNING_KEY=$(New-RandomSecret)",
        "DJANGO_DEBUG=true",
        "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1",
        "CHANNEL_REDIS_URL=redis://127.0.0.1:$RedisPort/0",
        "POSTGRES_DB=mymanito_local",
        "POSTGRES_USER=mymanito_local",
        "POSTGRES_PASSWORD=$(New-RandomSecret)",
        "POSTGRES_HOST=127.0.0.1",
        "POSTGRES_PORT=$PostgresPort",
        "POSTGRES_CONNECT_TIMEOUT=5",
        "LOCAL_POSTGRES_PORT=$PostgresPort",
        "LOCAL_REDIS_PORT=$RedisPort",
        "KAKAO_REST_API_KEY=$($productionEnv['KAKAO_REST_API_KEY'])",
        "KAKAO_CLIENT_SECRET=$($productionEnv['KAKAO_CLIENT_SECRET'])",
        "KAKAO_REDIRECT_URI=http://localhost:$FrontendPort/auth/kakao/callback",
        "MYMANITO_APP_URL=http://localhost:$FrontendPort",
        "FIREBASE_SERVICE_ACCOUNT_JSON=",
        "FIREBASE_SERVICE_ACCOUNT_FILE=",
        "IOS_WEB_PUSH_VAPID_PRIVATE_KEY=",
        "IOS_WEB_PUSH_VAPID_SUBJECT=",
        "SCHEDULER_ENABLED=false",
        "OUTBOUND_NOTIFICATIONS_ENABLED=false"
    )
    Write-Utf8File -Path $LocalBackendEnv -Content (($localBackendLines -join "`n") + "`n")
}

if (-not (Test-Path -LiteralPath $LocalFrontendEnv)) {
    $localFrontendLines = @(
        "VITE_API_BASE_URL=/api",
        "VITE_REALTIME_URL=",
        "VITE_KAKAO_REDIRECT_URI=http://localhost:$FrontendPort/auth/kakao/callback",
        "VITE_IOS_WEB_PUSH_VAPID_PUBLIC_KEY="
    )
    Write-Utf8File -Path $LocalFrontendEnv -Content (($localFrontendLines -join "`n") + "`n")
}

$localEnv = Read-DotEnv -Path $LocalBackendEnv
$expectedLocalValues = @{
    POSTGRES_HOST = "127.0.0.1"
    POSTGRES_PORT = "$PostgresPort"
    LOCAL_POSTGRES_PORT = "$PostgresPort"
    LOCAL_REDIS_PORT = "$RedisPort"
    CHANNEL_REDIS_URL = "redis://127.0.0.1:$RedisPort/0"
    SCHEDULER_ENABLED = "false"
    OUTBOUND_NOTIFICATIONS_ENABLED = "false"
}
foreach ($entry in $expectedLocalValues.GetEnumerator()) {
    if ($localEnv[$entry.Key] -ne $entry.Value) {
        throw "backend/.env.local must set $($entry.Key)=$($entry.Value)"
    }
}

Set-ProcessEnvironment -Values $localEnv
$env:DJANGO_ENV_FILE = $LocalBackendEnv

if (Test-Path -LiteralPath $StatePath) {
    $previousState = Get-Content -LiteralPath $StatePath -Encoding utf8 | ConvertFrom-Json
    $runningPids = @($previousState.backend_pid, $previousState.frontend_pid) | Where-Object { $_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue) }
    if ($runningPids.Count -gt 0) {
        throw "Local development processes are already running. Run scripts\local-stop.cmd first."
    }
    Remove-Item -LiteralPath $StatePath -Force
}

Invoke-Native -FilePath "docker" -Arguments @("info", "--format", "{{.ServerVersion}}")
$composeArgs = @(
    "compose",
    "--project-name", $ComposeProject,
    "--env-file", $LocalBackendEnv,
    "-f", $ComposeFile
)
Invoke-Native -FilePath "docker" -Arguments ($composeArgs + @("up", "-d", "--wait"))
Assert-LocalPostgresTarget -ComposeArguments $composeArgs

$localDatabase = $localEnv["POSTGRES_DB"]
$localDatabaseUser = $localEnv["POSTGRES_USER"]

if ($RefreshDbFromNas) {
    if ($NasTunnelPort -eq $PostgresPort) {
        throw "NAS source port and local PostgreSQL port must be different."
    }
    Assert-NasSshTunnel -Port $NasTunnelPort
    foreach ($requiredKey in @("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")) {
        if (-not $productionEnv[$requiredKey]) {
            throw "backend/.env is missing $requiredKey for the NAS dump."
        }
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $dumpName = "nas-$timestamp.dump"
    $dumpPath = Join-Path $BackupRoot $dumpName
    $mountArgument = "${BackupRoot}:/backup"
    $previousPgPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $productionEnv["POSTGRES_PASSWORD"]
        Invoke-Native -FilePath "docker" -Arguments @(
            "run", "--rm",
            "-e", "PGPASSWORD",
            "-e", "PGOPTIONS=-c default_transaction_read_only=on",
            "-v", $mountArgument,
            "postgres:17-alpine",
            "pg_dump",
            "-h", "host.docker.internal",
            "-p", "$NasTunnelPort",
            "-U", $productionEnv["POSTGRES_USER"],
            "-d", $productionEnv["POSTGRES_DB"],
            "-Fc", "--no-owner", "--no-acl",
            "-f", "/backup/$dumpName"
        )
    } finally {
        if ($null -eq $previousPgPassword) {
            Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        } else {
            $env:PGPASSWORD = $previousPgPassword
        }
    }
    if (-not (Test-Path -LiteralPath $dumpPath) -or (Get-Item -LiteralPath $dumpPath).Length -eq 0) {
        throw "NAS dump was not created."
    }
    Invoke-Native -FilePath "docker" -Arguments @(
        "run", "--rm", "-v", $mountArgument,
        "postgres:17-alpine", "pg_restore", "--list", "/backup/$dumpName"
    )

    Assert-LocalPostgresTarget -ComposeArguments $composeArgs
    Invoke-Native -FilePath "docker" -Arguments ($composeArgs + @(
        "exec", "-T", "postgres", "dropdb", "-U", $localDatabaseUser, "--if-exists", "--force", $localDatabase
    ))
    Invoke-Native -FilePath "docker" -Arguments ($composeArgs + @(
        "exec", "-T", "postgres", "createdb", "-U", $localDatabaseUser, $localDatabase
    ))
    Invoke-Native -FilePath "docker" -Arguments ($composeArgs + @(
        "exec", "-T", "postgres", "pg_restore", "-U", $localDatabaseUser, "-d", $localDatabase,
        "--no-owner", "--no-acl", "/backups/$dumpName"
    ))

}

$python = Join-Path $BackendRoot "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend virtual environment was not found at $python"
}
$managePy = Join-Path $BackendRoot "manage.py"
Invoke-Native -FilePath $python -Arguments @($managePy, "migrate", "--noinput")
Invoke-Native -FilePath $python -Arguments @($managePy, "check")

Assert-LocalPostgresTarget -ComposeArguments $composeArgs
$sanitizeSql = @"
TRUNCATE TABLE accounts_webpushdevice, accounts_ioswebpushsubscription RESTART IDENTITY;
UPDATE accounts_user
SET kakao_notification_enabled = FALSE,
    kakao_access_token = '',
    kakao_refresh_token = '',
    kakao_access_token_expires_at = NULL,
    kakao_scopes = '[]'::jsonb;
"@
Invoke-Native -FilePath "docker" -Arguments ($composeArgs + @(
    "exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", $localDatabaseUser,
    "-d", $localDatabase, "-c", $sanitizeSql
))

$unsafeNotificationRows = (& docker @composeArgs exec -T postgres psql -U $localDatabaseUser -d $localDatabase -Atc @"
SELECT
    (SELECT COUNT(*) FROM accounts_webpushdevice)
  + (SELECT COUNT(*) FROM accounts_ioswebpushsubscription)
  + (SELECT COUNT(*) FROM accounts_user WHERE kakao_notification_enabled OR kakao_access_token <> '' OR kakao_refresh_token <> '' OR jsonb_array_length(kakao_scopes) > 0);
"@).Trim()
if ($unsafeNotificationRows -ne "0") {
    throw "Local database still contains enabled notification credentials: $unsafeNotificationRows"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backendStdout = Join-Path $RuntimeRoot "backend-$timestamp.out.log"
$backendStderr = Join-Path $RuntimeRoot "backend-$timestamp.err.log"
$frontendStdout = Join-Path $RuntimeRoot "frontend-$timestamp.out.log"
$frontendStderr = Join-Path $RuntimeRoot "frontend-$timestamp.err.log"
$backendProcess = $null
$frontendProcess = $null

try {
    $backendStart = @{
        FilePath = $python
        ArgumentList = @("manage.py", "runserver", "127.0.0.1:$BackendPort", "--noreload")
        WorkingDirectory = $BackendRoot
        WindowStyle = "Hidden"
        RedirectStandardOutput = $backendStdout
        RedirectStandardError = $backendStderr
        PassThru = $true
    }
    $backendProcess = Start-Process @backendStart

    $viteScript = Join-Path $FrontendRoot "node_modules\vite\bin\vite.js"
    if (-not (Test-Path -LiteralPath $viteScript)) {
        throw "Frontend dependencies are missing. Run npm install in frontend first."
    }
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    $frontendStart = @{
        FilePath = $node
        ArgumentList = @($viteScript, "--host", "127.0.0.1", "--port", "$FrontendPort")
        WorkingDirectory = $FrontendRoot
        WindowStyle = "Hidden"
        RedirectStandardOutput = $frontendStdout
        RedirectStandardError = $frontendStderr
        PassThru = $true
    }
    $frontendProcess = Start-Process @frontendStart

    $state = [ordered]@{
        project_root = $ProjectRoot
        backend_pid = $backendProcess.Id
        frontend_pid = $frontendProcess.Id
        backend_port = $BackendPort
        frontend_port = $FrontendPort
        postgres_port = $PostgresPort
        redis_port = $RedisPort
        started_at = (Get-Date).ToString("o")
    }
    Write-Utf8File -Path $StatePath -Content (($state | ConvertTo-Json) + "`n")

    Wait-ForPort -Port $BackendPort -Name "Backend"
    Wait-ForPort -Port $FrontendPort -Name "Frontend"
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort" -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -ne 200) {
        throw "Frontend health check returned HTTP $($response.StatusCode)"
    }
} catch {
    Stop-LocalProcess -Process $frontendProcess
    Stop-LocalProcess -Process $backendProcess
    Invoke-Native -FilePath "docker" -Arguments ($composeArgs + @("stop"))
    throw
}

Write-Output "MyManito local development stack is running."
Write-Output "Frontend: http://localhost:$FrontendPort"
Write-Output "Backend:  http://localhost:$BackendPort"
Write-Output "Postgres: 127.0.0.1:$PostgresPort"
Write-Output "Redis:    127.0.0.1:$RedisPort"
Write-Output "Logs:     $RuntimeRoot"
