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

# Two standalone stacks - the production file is not an overlay, so it takes a
# single -f. Do not combine them.
$Compose = @('docker', 'compose', '-f', 'docker-compose.yml')
$ComposeProd = @('docker', 'compose', '-f', 'docker-compose.prod.yml')
# Postgres runs inside both stacks, so every database task goes through
# `compose exec postgres` and talks over the container's local socket. There is
# no host-side DSN to assemble any more, and nothing has to satisfy the
# production server's TLS requirement to run psql.

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

  Database (Postgres runs in Docker, in both stacks)
    migrate         alembic upgrade head
    revision "msg"  Autogenerate a migration
    seed-admin      Create/promote the first admin account
    psql            psql session against the dev database
    backup          Compressed pg_dump of the dev database into .\backups
    db-bootstrap    Re-apply runtime-role grants (already run on first start)

  Quality
    test            Backend + frontend tests
    test-backend    pytest
    test-frontend   vitest
    lint            ruff + mypy + tsc
    audit           pip-audit + npm audit

  Production (run on the VPS) - one command brings up everything
    prod-up         Start db, cache, api, worker, ui and proxy; migrations and
                    the first admin are applied by the one-shot 'init' service
    prod-down       Stop it (volumes, and the database, are kept)
    prod-ps         Container status
    prod-logs       Tail logs
    prod-migrate    Apply migrations by hand
    prod-seed-admin Create/promote the first admin by hand
    prod-psql       psql session against the PRODUCTION database
    prod-backup     Compressed pg_dump of the production database

  Danger
    clean           Stop everything and DELETE local volumes (the LOCAL dev
                    database only - production uses a separate project name,
                    so its database is not reachable from here)
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
    # Postgres runs inside both stacks now, so these go through `compose exec`
    # instead of a throwaway client container joined to the network by hand.
    # That also means psql uses the container's local socket and never has to
    # satisfy the server's TLS requirement.
    # PGPASSWORD is needed even inside the container: POSTGRES_INITDB_ARGS sets
    # --auth-local=scram-sha-256, so the Unix socket asks for a password too.
    # It is read from the container's own environment, never passed in argv.
    'psql' {
        Invoke-Cmd ($Compose + @('exec', 'postgres', 'sh', '-c',
            'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'))
    }
    'prod-psql' {
        Invoke-Cmd ($ComposeProd + @('exec', 'postgres', 'sh', '-c',
            'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'))
    }
    'db-bootstrap' {
        Write-Host 'Re-applying the runtime-role grants (already applied on first start).' -ForegroundColor Cyan
        Invoke-Cmd ($Compose + @('exec', 'postgres', 'sh', '-c',
            'PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v app_user="$APP_DB_USER" -v app_password="$APP_DB_PASSWORD" -f /bootstrap/10-roles.sql'))
    }
    { $_ -in 'backup', 'prod-backup' } {
        # pg_dump runs inside the postgres container over its local socket, so
        # no client image and no TLS negotiation are involved.
        $stack = if ($Task -eq 'prod-backup') { $ComposeProd } else { $Compose }
        $which = if ($Task -eq 'prod-backup') { 'production' } else { 'development' }
        New-Item -ItemType Directory -Force -Path 'backups' | Out-Null
        $stamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'
        $file = "backups/geo_audit-$which-$stamp.sql"
        Write-Host "Dumping the $which database" -ForegroundColor DarkGray
        & $stack[0] @($stack[1..($stack.Length - 1)]) exec -T postgres sh -c `
            'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' `
            | Set-Content -Path $file -Encoding utf8
        if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }
        Compress-Archive -Path $file -DestinationPath "$file.zip" -Force
        Remove-Item $file
        Write-Host "Wrote $file.zip" -ForegroundColor Green
        Write-Host 'A dump on the same machine as the database is not a backup - copy it off the box.' -ForegroundColor Yellow
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

    'prod-up' {
        Invoke-Cmd ($ComposeProd + @('up', '-d', '--build'))
        Write-Host ''
        Write-Host "Migrations and the first admin are applied by the one-shot 'init' service." -ForegroundColor Green
        Write-Host 'Watch it with: .\geo.ps1 prod-logs init' -ForegroundColor Green
    }
    'prod-down'       { Invoke-Cmd ($ComposeProd + @('down')) }
    'prod-ps'         { Invoke-Cmd ($ComposeProd + @('ps')) }
    'prod-migrate'    { Invoke-Cmd ($ComposeProd + @('exec', 'backend', 'alembic', 'upgrade', 'head')) }
    'prod-seed-admin' { Invoke-Cmd ($ComposeProd + @('exec', 'backend', 'python', '-m', 'app.scripts.seed_admin')) }
    'prod-logs'       { Invoke-Cmd ($ComposeProd + @('logs', '-f', '--tail=120') + $Rest) }

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
