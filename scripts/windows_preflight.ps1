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
    Static | Tests | Live | Full  (default: Static)
#.PARAMETER Help
#    Print available modes without running checks.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows_preflight.ps1 -Mode Static
#>

param(
    [ValidateSet('Static', 'Tests', 'Live', 'Full')]
    [string]$Mode = 'Static',
    [string]$OperatorEnvFile,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
$script:failed = $false

if ($Help) {
    Write-Host "Usage: pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/windows_preflight.ps1 -Mode <Static|Tests|Live|Full>"
    Write-Host "Full runs uv sync --all-extras --all-groups before native venv checks."
    exit 0
}

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

function Get-DotenvValue([string]$Path, [string]$Name) {
    $line = Get-Content -LiteralPath $Path | Where-Object {
        $_ -match "^\s*(?:export\s+)?$([regex]::Escape($Name))\s*="
    } | Select-Object -First 1
    if ($null -eq $line) { return $null }

    $value = ($line -replace "^\s*(?:export\s+)?$([regex]::Escape($Name))\s*=", '').Trim()
    if ($value.Length -ge 2 -and $value[0] -eq $value[$value.Length - 1] -and
        ($value[0] -eq '"' -or $value[0] -eq "'")) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    return $value
}

function Test-OperatorReadiness([string]$Root, [string]$EnvFile) {
    Write-Host "`n[Operator configuration]" -ForegroundColor White
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        Write-Fail "operator env file missing: $EnvFile -- copy .env.example to .env and set BGE_M3_ONNX_MODEL_HOST_DIR"
        return
    }
    Write-Pass "operator env file: $EnvFile"

    $modelPath = Get-DotenvValue $EnvFile 'BGE_M3_ONNX_MODEL_HOST_DIR'
    if ([string]::IsNullOrWhiteSpace($modelPath)) {
        Write-Fail "BGE_M3_ONNX_MODEL_HOST_DIR missing in $EnvFile"
        return
    }
    if ($modelPath -match '^/mnt/' -or $modelPath -match '^\\\\wsl') {
        Write-Fail "BGE_M3_ONNX_MODEL_HOST_DIR must be a native Windows path, not '$modelPath'"
        return
    }

    $resolvedModelPath = if ([System.IO.Path]::IsPathRooted($modelPath)) {
        $modelPath
    } else {
        Join-Path $Root $modelPath
    }
    if (Test-Path -LiteralPath $resolvedModelPath -PathType Container) {
        Write-Pass "BGE-M3 model directory ready: $resolvedModelPath"
    } else {
        Write-Fail "BGE_M3_ONNX_MODEL_HOST_DIR does not exist: $resolvedModelPath"
    }

    foreach ($modelFile in @('model.int8.onnx', 'model.int8.onnx.data')) {
        $modelFilePath = Join-Path $resolvedModelPath $modelFile
        if (Test-Path -LiteralPath $modelFilePath -PathType Leaf) {
            Write-Pass "BGE-M3 model artifact ready: $modelFilePath"
        } else {
            Write-Fail "BGE-M3 model artifact missing: $modelFilePath"
        }
    }

    $gdrivePath = Get-DotenvValue $EnvFile 'GDRIVE_SYNC_DIR'
    if ([string]::IsNullOrWhiteSpace($gdrivePath)) {
        Write-Fail "GDRIVE_SYNC_DIR missing in $EnvFile"
        return
    }
    if ($gdrivePath -match '^/mnt/' -or $gdrivePath -match '^\\\\wsl') {
        Write-Fail "GDRIVE_SYNC_DIR must be a native Windows path, not '$gdrivePath'"
        return
    }
    $resolvedGdrivePath = if ([System.IO.Path]::IsPathRooted($gdrivePath)) {
        $gdrivePath
    } else {
        Join-Path $Root $gdrivePath
    }
    if (Test-Path -LiteralPath $resolvedGdrivePath -PathType Container) {
        Write-Pass "Google Drive sync directory ready: $resolvedGdrivePath"
    } else {
        Write-Fail "GDRIVE_SYNC_DIR does not exist: $resolvedGdrivePath"
    }
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

    $operatorEnv = if ($OperatorEnvFile) { $OperatorEnvFile } else { Join-Path $root '.env' }
    Test-OperatorReadiness $root $operatorEnv

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
        [System.IO.Path]::Combine($root, "tests", "contract", "test_windows_preflight_contract.py")
        [System.IO.Path]::Combine($root, "tests", "unit", "scripts", "test_cleanup_orphaned_worktree_volumes.py")
        [System.IO.Path]::Combine($root, "tests", "unit", "scripts", "test_smoke_zoo.py")
        [System.IO.Path]::Combine($root, "tests", "unit", "test_logging_config.py")
    )
    $testArgs = @(
        'run', '--no-sync', '--python', '3.12',
        'python', '-m', 'pytest',
        '-q', '-n', '0',
        '-p', 'no:cacheprovider',
        '--maxfail=1',
        '-m', 'not requires_extras and not slow'
    ) + $testPaths

    Write-Host "  Running focused core, runtime, Windows acceptance, and contract tests..." -ForegroundColor White
    Push-Location $root
    $out = & uv $testArgs 2>&1
    $ec = $LASTEXITCODE
    Pop-Location

    $out -split "`n" | ForEach-Object { Write-Host "    $_" }
    if ($ec -eq 0) { Write-Pass "all focused tests passed" }
    else { Write-Fail "focused tests failed (exit=$ec)" }
}

# ── Full test gate ───────────────────────────────────────────────────────────

function Invoke-Full {
    $root = Get-Root
    $python = Join-Path $root ".venv\Scripts\python.exe"
    $hadPycacheSetting = Test-Path Env:\PYTHONDONTWRITEBYTECODE
    $savedPycacheSetting = $env:PYTHONDONTWRITEBYTECODE
    $pushedLocation = $false

    try {
        $uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $uv) {
            Write-Fail "uv is required for Full mode; install it from https://docs.astral.sh/uv/"
            return
        }

        Push-Location $root
        $pushedLocation = $true
        & $uv.Path sync --all-extras --all-groups
        $syncExit = $LASTEXITCODE
        if ($syncExit -ne 0) {
            Write-Fail "uv sync failed (exit=$syncExit); resolve the error above and retry Full mode"
            return
        }

        if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
            Write-Fail "native venv Python missing at $python after uv sync"
            return
        }

        & $python -m pytest --version
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "pytest is unavailable in $python; run 'uv sync --all-extras --all-groups' first"
            return
        }

        & $python -m pytest -p xdist --version
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "pytest-xdist is unavailable in $python; run 'uv sync --all-extras --all-groups' first"
            return
        }

        & $python -m pytest -p pytest_timeout --version
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "pytest-timeout is unavailable in $python; run 'uv sync --all-extras --all-groups' first"
            return
        }

        $env:PYTHONDONTWRITEBYTECODE = "1"
        Write-Host "`nPhase 1/2: parallel-safe suites..." -ForegroundColor Cyan
        & $python -m pytest "tests/chaos/" "tests/contract/" "tests/unit/" "-n" "2" "--dist=worksteal" "--timeout=30"
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Phase 1 failed (exit=$LASTEXITCODE)"
            return
        }

        Write-Host "`nPhase 2/2: stateful/live suites sequentially..." -ForegroundColor Cyan
        & $python -m pytest "tests/e2e/" "tests/integration/" "tests/load/" "tests/smoke/" "--timeout=30"
        if ($LASTEXITCODE -eq 0) { Write-Pass "full test suite complete" }
        else { Write-Fail "Phase 2 failed (exit=$LASTEXITCODE)" }
    } finally {
        if ($hadPycacheSetting) {
            Set-Item -Path Env:\PYTHONDONTWRITEBYTECODE -Value $savedPycacheSetting
        } else {
            Remove-Item Env:\PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
        }
        if ($pushedLocation) { Pop-Location }
    }
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
        'Full'   { Invoke-Full }
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
