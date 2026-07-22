#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Windows preflight checks for rag-fresh project readiness.
.DESCRIPTION
    Static:  deterministic checks for tools, versions, lock files, Git/WSL state,
             host path shape, and Docker Compose config validation.
    Tests:   run focused no-service contract/integration tests with no pytest cache.
    Live:    read-only health probes for Docker, core compose services, and bot
             import/startup (no polling, no Telegram/CRM writes, no secret access).
.PARAMETER Mode
    Static | Tests | Live  (default: Static)
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows_preflight.ps1 -Mode Static
#>

param(
    [ValidateSet('Static', 'Tests', 'Live')]
    [string]$Mode = 'Static'
)

$ErrorActionPreference = 'Stop'
$script:failed = $false

function Write-Pass  { Write-Host "  PASS  $args" -ForegroundColor Green }
function Write-Fail  { Write-Host "  FAIL  $args" -ForegroundColor Red; $script:failed = $true }
function Write-Warn  { Write-Host "  WARN  $args" -ForegroundColor Yellow }
function Write-Info  { Write-Host "  INFO  $args" -ForegroundColor White }

# ── helpers ──────────────────────────────────────────────────────────────────

function Get-Root { (Get-Item $PSScriptRoot).Parent.FullName }

function Test-Tool([string]$Name, [scriptblock]$VersionCmd) {
    $out = & $VersionCmd 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Pass "$Name available" }
    else { Write-Fail "$Name NOT available" }
}

# ── Static ───────────────────────────────────────────────────────────────────

function Invoke-Static {
    $root = Get-Root
    Write-Host "`n=== Static Preflight ===`n" -ForegroundColor Cyan

    Write-Host "[Tools]" -ForegroundColor White
    Test-Tool "uv"     { & uv version }
    Test-Tool "docker" { & docker --version }
    Test-Tool "git"    { & git --version }

    Write-Host "`n[Lock files]" -ForegroundColor White
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Push-Location $root
    & uv lock --check 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Pass "root: uv.lock valid" }
    else { Write-Fail "root: uv.lock check FAILED" }
    Pop-Location

    Push-Location (Join-Path $root "telegram_bot")
    & uv lock --check 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Pass "telegram_bot: uv.lock valid" }
    else { Write-Fail "telegram_bot: uv.lock check FAILED" }
    Pop-Location

    Push-Location (Join-Path $root "services/bge-m3-api")
    & uv lock --check 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Pass "bge-m3: uv.lock valid" }
    else { Write-Fail "bge-m3: uv.lock check FAILED" }
    Pop-Location
    $ErrorActionPreference = $eap

    Write-Host "`n[Python via uv]" -ForegroundColor White
    $pv = & uv run --no-sync python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        if ($pv -match 'Python 3\.12\.') { Write-Pass "python: $pv" }
        else { Write-Fail "expected Python 3.12.x, got: $pv" }
    } else { Write-Fail "uv run python failed" }

    Write-Host "`n[Git and WSL]" -ForegroundColor White
    $sl = & git config core.symlinks 2>&1
    if ($LASTEXITCODE -eq 0 -and $sl.Trim() -eq 'false') {
        Write-Warn "git core.symlinks=false -- possible cross-platform mode drift"
    } else { Write-Pass "git symlinks OK ($($sl.Trim()))" }

    $wtOut = & git worktree list 2>&1
    if ($LASTEXITCODE -eq 0) {
        $wslPaths = $wtOut | Where-Object { $_ -match '/mnt/' -or $_ -match '\\\\wsl' }
        if ($wslPaths) {
            Write-Warn "WSL worktree paths -- may be stale:"
            $wslPaths | ForEach-Object { Write-Host "         $_" -ForegroundColor Yellow }
        } else { Write-Pass "no stale WSL worktree paths" }
    } else { Write-Fail "git worktree list failed" }

    Write-Host "`n[Host filesystem]" -ForegroundColor White
    if ($env:OS -match 'Windows') {
        Write-Pass "Windows host"
        if ($root -match '^[A-Za-z]:\\') { Write-Pass "native NTFS path: $root" }
        else { Write-Info "repo path: $root" }
    } else { Write-Info "non-Windows host: $($env:OS)" }

    Write-Host "`n[Docker Compose config]" -ForegroundColor White
    $envFile = [System.IO.Path]::Combine($root, "tests", "fixtures", "compose.ci.env")
    if (Test-Path $envFile) {
        Push-Location $root
        & docker compose --env-file $envFile -f compose.yml -f compose.dev.yml config --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { Pop-Location; Write-Pass "compose config validates" }
        else {
            $err = & docker compose --env-file $envFile -f compose.yml -f compose.dev.yml config 2>&1
            Pop-Location; Write-Fail "compose config failed: $err"
        }
    } else { Write-Fail "compose.ci.env missing at $envFile" }
}

# ── Tests ────────────────────────────────────────────────────────────────────

function Invoke-Tests {
    $root = Get-Root
    Write-Host "`n=== Tests Mode ===`n" -ForegroundColor Cyan

    $env:PYTHON_DOTENV_DISABLED = 'true'
    $env:RAG_TESTING = 'true'

    Write-Host "`n[Focused no-service tests (card_900e0851197d)]" -ForegroundColor White
    $testPaths = @(
        [System.IO.Path]::Combine($root, "tests", "unit", "core")
        [System.IO.Path]::Combine($root, "tests", "unit", "runtime")
        [System.IO.Path]::Combine($root, "tests", "contract", "test_runtime_no_telegram_bot_coupling_contract.py")
    )
    $testArgs = @(
        'run', '--no-sync', '--python', '3.12',
        'python', '-m', 'pytest',
        '-q', '-n', '0',
        '-p', 'no:cacheprovider',
        '--maxfail=1',
        '-m', 'not requires_extras and not slow'
    ) + $testPaths

    Write-Host "  Running: uv run --no-sync --python 3.12 python -m pytest tests/unit/core tests/unit/runtime test_runtime_no_telegram_bot_coupling_contract.py ..." -ForegroundColor White
    Push-Location $root
    $out = & uv $testArgs 2>&1
    $ec = $LASTEXITCODE
    Pop-Location

    $out -split "`n" | ForEach-Object { Write-Host "    $_" }
    if ($ec -eq 0) { Write-Pass "all focused tests passed" }
    else { Write-Fail "focused tests failed (exit=$ec)" }
}

# ── Live ──────────────────────────────────────────────────────────────────────

function Invoke-Live {
    $root = Get-Root
    Write-Host "`n=== Live Preflight ===`n" -ForegroundColor Cyan

    Write-Host "[Docker engine]" -ForegroundColor White
    $di = & docker info --format '{{.ServerVersion}}' 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Pass "Docker engine: $di" }
    else { Write-Fail "docker info failed -- is Docker Desktop running?"; return }

    Write-Host "`n[Core compose services (qdrant, redis, bge-m3)]" -ForegroundColor White
    $envFile = [System.IO.Path]::Combine($root, "tests", "fixtures", "compose.ci.env")
    # Use COMPOSE_PROJECT_NAME env override, fall back to dev
    $projectName = if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { 'dev' }
    $composeArgs = @(
        '--env-file', $envFile,
        '-f', (Join-Path $root "compose.yml"),
        '-f', (Join-Path $root "compose.dev.yml"),
        '-p', $projectName,
        'ps', '--format', 'json',
        '--filter', 'status=running',
        'qdrant', 'redis', 'bge-m3'
    )
    Push-Location $root
    $psOut = & docker compose $composeArgs 2>&1
    $ec = $LASTEXITCODE
    Pop-Location

    if ($ec -ne 0) {
        Write-Fail "docker compose discovery failed (exit=$ec)"
        return
    }

    $svcs = $psOut | Where-Object { $_.Trim() -ne '' } | ConvertFrom-Json 2>$null
    $required = @{ 'qdrant' = $false; 'redis' = $false; 'bge-m3' = $false }
    $byName = @{}

    if ($svcs) {
        $arr = if ($svcs -is [array]) { $svcs } else { @($svcs) }
        foreach ($s in $arr) { $byName[$s.Service] = $s }
    }

    $presentCount = 0
    foreach ($name in $required.Keys) {
        if ($byName.ContainsKey($name)) {
            $s = $byName[$name]
            $health = if ($s.Health) { $s.Health } else { 'none' }
            if ($health -eq 'healthy') {
                Write-Pass "${name}: $($s.State) (healthy)"
                $presentCount++
            } else {
                Write-Fail "${name}: $($s.State) ($health)"
            }
        } else {
            Write-Fail "${name}: not running"
        }
    }

    if ($presentCount -lt $required.Count) {
        Write-Warn "$($required.Count - $presentCount) required service(s) missing -- check 'docker compose -f compose.yml -f compose.dev.yml up -d'"
        return
    }

    Write-Host "`n[Bot import verification]" -ForegroundColor White

    $dummyVars = @{
        'PYTHON_DOTENV_DISABLED' = 'true'
        'RAG_TESTING' = 'true'
        'TELEGRAM_BOT_TOKEN' = 'preflight-dummy'
        'REDIS_PASSWORD' = 'preflight-dummy'
        'POSTGRES_PASSWORD' = 'preflight-dummy'
        'BGE_M3_ONNX_MODEL_HOST_DIR' = 'preflight-dummy'
    }
    $priorEnv = @{}
    foreach ($kv in $dummyVars.GetEnumerator()) {
        $name = $kv.Key
        if (Test-Path "Env:$name") { $priorEnv[$name] = (Get-Item "Env:$name").Value }
        Set-Item "Env:$name" -Value $kv.Value
    }
    try {
        Push-Location $root
        $importOut = & uv run --no-sync --python 3.12 python -c "from telegram_bot.config import BotConfig; import src.runtime.integrations.polling_lock; import telegram_bot.main; print('OK')" 2>&1
        $ec2 = $LASTEXITCODE
        Pop-Location
        if ($ec2 -eq 0) { Write-Pass "bot modules importable (no startup)" }
        else { Write-Fail "bot import check: $importOut" }
    } finally {
        $priorEnv.GetEnumerator() | ForEach-Object { Set-Item "Env:$($_.Key)" -Value $_.Value }
        $dummyVars.Keys | Where-Object { -not $priorEnv.ContainsKey($_) } | ForEach-Object { Remove-Item "Env:$_" -ErrorAction SilentlyContinue }
    }
}

# ── Entry ────────────────────────────────────────────────────────────────────

Write-Host "=== Windows Preflight [$Mode] ===" -ForegroundColor Cyan
Write-Host "Repo: $((Get-Item $PSScriptRoot).Parent.FullName)" -ForegroundColor White

try {
    switch ($Mode) {
        'Static' { Invoke-Static }
        'Tests'  { Invoke-Tests }
        'Live'   { Invoke-Live }
    }
} catch {
    Write-Host "  UNEXPECTED ERROR: $_" -ForegroundColor Red
    $script:failed = $true
}

Write-Host ""
if ($script:failed) {
    Write-Host "Result: FAILED" -ForegroundColor Red
    exit 1
} else {
    Write-Host "Result: PASSED" -ForegroundColor Green
    exit 0
}
