<#
.SYNOPSIS
    Task runner for the CheckGEO.ai stack on Windows (PowerShell equivalent of the Makefile).

.EXAMPLE
    .\geo.ps1 up
    .\geo.ps1 migrate
    .\geo.ps1 seed-admin
    .\geo.ps1 logs backend
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Task = 'help',

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$Compose = @('docker', 'compose')
$ComposeProd = @('docker', 'compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.prod.yml')
# Postgres client for one-off work against the managed database. Joining the
# compose network lets the same command reach the dev container by hostname.
$PgImage = 'postgres:16-alpine'
$PgNetwork = 'geo-audit_internal'

# Reads .env into a hashtable, expanding ${VAR} references against values
# defined earlier in the file - the same thing Docker Compose does when it
# loads the file, so DATABASE_URL-style composed values resolve here too.
function Read-DotEnv([string]$Path = '.env') {
    $values = @{}
    if (-not (Test-Path $Path)) { throw "$Path not found - copy .env.example and fill it in." }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
        $split = $trimmed.IndexOf('=')
        if ($split -lt 1) { continue }
        $key = $trimmed.Substring(0, $split).Trim()
        $value = $trimmed.Substring($split + 1).Trim()
        $value = [regex]::Replace($value, '\$\{(\w+)\}', {
            param($m)
            $name = $m.Groups[1].Value
            if ($values.ContainsKey($name)) { $values[$name] } else { '' }
        })
        $values[$key] = $value
    }
    return $values
}

# libpq DSN for the owner role - used by psql and the role bootstrap.
function Get-OwnerDsn {
    $env_ = Read-DotEnv
    foreach ($required in 'POSTGRES_HOST', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB') {
        if (-not $env_[$required]) { throw "$required is not set in .env" }
    }
    $port = if ($env_['POSTGRES_PORT']) { $env_['POSTGRES_PORT'] } else { '5432' }
    # An explicit POSTGRES_SSLMODE always wins. Otherwise: the throwaway dev
    # container serves plain TCP, so requiring TLS there just fails to connect;
    # anything else is remote and must be encrypted.
    $localHosts = @('postgres', 'localhost', '127.0.0.1', '::1')
    $ssl = if ($env_['POSTGRES_SSLMODE']) {
        $env_['POSTGRES_SSLMODE']
    } elseif ($localHosts -contains $env_['POSTGRES_HOST']) {
        'disable'
    } else {
        'require'
    }
    return @{
        Dsn = "postgresql://$($env_['POSTGRES_USER']):$($env_['POSTGRES_PASSWORD'])@$($env_['POSTGRES_HOST']):$port/$($env_['POSTGRES_DB'])?sslmode=$ssl"
        AppUser = $env_['APP_DB_USER']
        AppPassword = $env_['APP_DB_PASSWORD']
        Host_ = $env_['POSTGRES_HOST']
    }
}

# Environment assignments whose value must never be echoed. The command is
# printed so you can see what ran; a connection string with the database
# password in it does not belong in that transcript, or in a CI log scraping it.
$SecretArgPattern = '^(PGDSN|APP_DB_PASSWORD|POSTGRES_PASSWORD|PGPASSWORD)='

function Format-CmdArg([string]$Value) {
    if ($Value -match $SecretArgPattern) { return "$($Matches[1])=********" }
    return $Value
}

# NOTE: the parameter is deliberately not called $Args - that is a PowerShell
# automatic variable, and shadowing it makes the binding silently produce an
# empty array instead of the command line you passed.
function Invoke-Cmd([string[]]$CommandArgs) {
    $shown = $CommandArgs | ForEach-Object { Format-CmdArg $_ }
    Write-Host "> $($shown -join ' ')" -ForegroundColor DarkGray
    & $CommandArgs[0] @($CommandArgs[1..($CommandArgs.Length - 1)])
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
}

function Show-Help {
    @"
GEO Audit task runner

  Setup
    init            Copy .env.example to .env and fill in generated secrets
    secrets         Print freshly generated secret values

  Development
    up              Start the dev stack (hot reload)  -> http://localhost:8080
    down            Stop the dev stack
    restart         Restart backend + worker
    build           Rebuild all images
    logs [service]  Tail logs
    ps              Container status
    shell           Bash shell in the backend container

  Database (external / managed Postgres)
    db-bootstrap    ONE-TIME on first deploy: create the runtime role
    migrate         alembic upgrade head
    revision "msg"  Autogenerate a migration
    seed-admin      Create/promote the first admin account
    psql            psql session against the configured database
    backup          Compressed pg_dump into .\backups

  Quality
    test            Backend + frontend tests
    test-backend    pytest
    test-frontend   vitest
    lint            ruff + mypy + tsc
    audit           pip-audit + npm audit

  Production (run on the VPS)
    prod-up         Start the production stack
    prod-down       Stop it
    prod-migrate    Apply migrations
    prod-logs       Tail logs

  Danger
    clean           Stop everything and DELETE local volumes
                    (the LOCAL dev database only - the managed one is untouched)
"@ | Write-Host
}

# Cryptographically secure randomness, written to work on both Windows
# PowerShell 5.1 and PowerShell 7+.
function Get-RandomBytes([int]$Count) {
    $bytes = New-Object 'byte[]' $Count
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return $bytes
}

function New-FernetKey {
    # A Fernet key is 32 random bytes, url-safe base64 encoded.
    [Convert]::ToBase64String((Get-RandomBytes 32)).Replace('+', '-').Replace('/', '_')
}

function New-HexSecret([int]$Bytes = 32) {
    ((Get-RandomBytes $Bytes) | ForEach-Object { $_.ToString('x2') }) -join ''
}

function New-Password([int]$Length = 32) {
    # Ambiguous glyphs (0/O, 1/l/I) removed so passwords survive being retyped.
    $chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $bytes = Get-RandomBytes $Length
    -join (0..($Length - 1) | ForEach-Object { $chars[$bytes[$_] % $chars.Length] })
}

switch ($Task) {
    'help' { Show-Help }

    'secrets' {
        Write-Host "JWT_SECRET_KEY=$(New-HexSecret 32)"
        Write-Host "ENCRYPTION_KEY=$(New-FernetKey)"
        Write-Host "POSTGRES_PASSWORD=$(New-Password 32)"
        Write-Host "APP_DB_PASSWORD=$(New-Password 32)"
        Write-Host "FIRST_ADMIN_PASSWORD=$(New-Password 20)"
    }

    'init' {
        if (Test-Path '.env') {
            Write-Host '.env already exists - not overwriting.' -ForegroundColor Yellow
            break
        }
        $content = Get-Content '.env.example' -Raw
        $content = $content -replace 'JWT_SECRET_KEY=.*', "JWT_SECRET_KEY=$(New-HexSecret 32)"
        $content = $content -replace 'ENCRYPTION_KEY=.*', "ENCRYPTION_KEY=$(New-FernetKey)"
        $content = $content -replace 'POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$(New-Password 32)"
        $content = $content -replace 'APP_DB_PASSWORD=.*', "APP_DB_PASSWORD=$(New-Password 32)"
        $content = $content -replace 'FIRST_ADMIN_PASSWORD=.*', "FIRST_ADMIN_PASSWORD=$(New-Password 20)"
        Set-Content -Path '.env' -Value $content -NoNewline -Encoding utf8
        Write-Host '.env created with freshly generated secrets.' -ForegroundColor Green
        Write-Host 'Review FIRST_ADMIN_EMAIL and FIRST_ADMIN_PASSWORD before running seed-admin.'
    }

    'up' {
        Invoke-Cmd ($Compose + @('up', '-d', '--build'))
        Write-Host ''
        Write-Host 'App:  http://localhost:8080' -ForegroundColor Green
        Write-Host 'Docs: http://localhost:8080/docs' -ForegroundColor Green
    }
    'down'    { Invoke-Cmd ($Compose + @('down')) }
    'restart' { Invoke-Cmd ($Compose + @('restart', 'backend', 'worker')) }
    'build'   { Invoke-Cmd ($Compose + @('build')) }
    'ps'      { Invoke-Cmd ($Compose + @('ps')) }
    'logs'    { Invoke-Cmd ($Compose + @('logs', '-f', '--tail=120') + $Rest) }
    'shell'   { Invoke-Cmd ($Compose + @('exec', 'backend', 'bash')) }

    'migrate'    { Invoke-Cmd ($Compose + @('exec', 'backend', 'alembic', 'upgrade', 'head')) }
    'revision'   { Invoke-Cmd ($Compose + @('exec', 'backend', 'alembic', 'revision', '--autogenerate', '-m', ($Rest -join ' '))) }
    'seed-admin' { Invoke-Cmd ($Compose + @('exec', 'backend', 'python', '-m', 'app.scripts.seed_admin')) }
    'psql' {
        $db = Get-OwnerDsn
        Write-Host "Connecting to $($db.Host_)" -ForegroundColor DarkGray
        # The DSN goes in through the environment, never argv, so it cannot be
        # read out of the process list.
        Invoke-Cmd @('docker', 'run', '--rm', '-it', '--network', $PgNetwork,
            '-e', "PGDSN=$($db.Dsn)", $PgImage, 'sh', '-c', 'psql "$PGDSN"')
    }
    'db-bootstrap' {
        $db = Get-OwnerDsn
        if (-not $db.AppUser -or -not $db.AppPassword) {
            throw 'APP_DB_USER and APP_DB_PASSWORD must be set in .env before bootstrapping.'
        }
        Write-Host "Creating the least-privilege runtime role on $($db.Host_)" -ForegroundColor Cyan
        Invoke-Cmd @('docker', 'run', '--rm', '-i', '--network', $PgNetwork,
            '-e', "PGDSN=$($db.Dsn)",
            '-e', "APP_DB_USER=$($db.AppUser)", '-e', "APP_DB_PASSWORD=$($db.AppPassword)",
            # Forward slashes so the Windows path survives Docker's own parsing
            # of the colon-delimited -v argument.
            '-v', "$($PWD.Path -replace '\\', '/')/infra/postgres/bootstrap:/bootstrap:ro",
            $PgImage, 'sh', '-c',
            'psql "$PGDSN" -v app_user="$APP_DB_USER" -v app_password="$APP_DB_PASSWORD" -f /bootstrap/10-roles.sql')
    }
    'backup' {
        New-Item -ItemType Directory -Force -Path 'backups' | Out-Null
        $db = Get-OwnerDsn
        $stamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'
        $file = "backups/geo_audit-$stamp.sql"
        Write-Host "Dumping $($db.Host_)" -ForegroundColor DarkGray
        docker run --rm -i --network $PgNetwork -e "PGDSN=$($db.Dsn)" $PgImage `
            sh -c 'pg_dump "$PGDSN" --clean --if-exists' | Set-Content -Path $file -Encoding utf8
        if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }
        Compress-Archive -Path $file -DestinationPath "$file.zip" -Force
        Remove-Item $file
        Write-Host "Wrote $file.zip" -ForegroundColor Green
    }

    'test'          { Invoke-Cmd ($Compose + @('exec', 'backend', 'pytest', '-q')); Invoke-Cmd ($Compose + @('exec', 'frontend', 'npm', 'run', 'test')) }
    'test-backend'  { Invoke-Cmd ($Compose + @('exec', 'backend', 'pytest', '-q') + $Rest) }
    'test-frontend' { Invoke-Cmd ($Compose + @('exec', 'frontend', 'npm', 'run', 'test')) }
    'lint' {
        Invoke-Cmd ($Compose + @('exec', 'backend', 'ruff', 'check', 'app', 'tests'))
        Invoke-Cmd ($Compose + @('exec', 'backend', 'mypy', 'app'))
        Invoke-Cmd ($Compose + @('exec', 'frontend', 'npm', 'run', 'typecheck'))
    }
    'audit' {
        Invoke-Cmd ($Compose + @('exec', 'backend', 'pip-audit', '--strict', '--requirement', 'requirements.txt'))
        Invoke-Cmd ($Compose + @('exec', 'frontend', 'npm', 'run', 'audit:check'))
    }

    'prod-up'      { Invoke-Cmd ($ComposeProd + @('up', '-d', '--build')) }
    'prod-down'    { Invoke-Cmd ($ComposeProd + @('down')) }
    'prod-migrate' { Invoke-Cmd ($ComposeProd + @('exec', 'backend', 'alembic', 'upgrade', 'head')) }
    'prod-logs'    { Invoke-Cmd ($ComposeProd + @('logs', '-f', '--tail=120') + $Rest) }

    'clean' {
        Write-Host 'This deletes the LOCAL dev database, Redis data and stored PDF reports.' -ForegroundColor Red
        Write-Host 'The managed database is not touched.' -ForegroundColor Yellow
        $answer = Read-Host "Type 'yes' to continue"
        if ($answer -eq 'yes') { Invoke-Cmd ($Compose + @('down', '-v')) } else { Write-Host 'Aborted.' }
    }

    default {
        Write-Host "Unknown task '$Task'." -ForegroundColor Red
        Show-Help
        exit 1
    }
}
