[CmdletBinding()]
param(
    [ValidateSet("Start", "Preflight", "Status", "Check", "Stop")]
    [string]$Action = "Start",
    [string]$ProjectId,
    [string]$EnvFile,
    [string]$PythonPath,
    [ValidateSet("real", "synthetic", "disabled")]
    [string]$AgentMode,
    [int]$FrontPort = 4317,
    [int]$BackPort = 8000,
    [int]$ReadyTimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"

$script:CompareRoot = $PSScriptRoot
$script:FrontRoot = Join-Path $script:CompareRoot "Front"
$script:BackRoot = Join-Path $script:CompareRoot "Back"

function Write-Result {
    param([string]$Name, [string]$Status, [string]$Detail)
    $color = switch ($Status) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
        default { "Gray" }
    }
    Write-Host ("[{0}] {1}: {2}" -f $Status, $Name, $Detail) -ForegroundColor $color
}

function Test-PathWithin {
    param([string]$Path, [string]$Parent)
    $resolvedPath = [IO.Path]::GetFullPath($Path).TrimEnd('\') + '\'
    $resolvedParent = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    return $resolvedPath.StartsWith($resolvedParent, [StringComparison]::OrdinalIgnoreCase)
}

function Import-CompareEnvFile {
    param([string]$Path)
    if (-not $Path) { return }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Configuration file does not exist: $Path"
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        if ($trimmed -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            throw "Configuration file contains an invalid line (only KEY=VALUE is supported): $trimmed"
        }
        $name = $matches[1]
        $value = $matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Resolve-PythonExecutable {
    $candidates = @(
        $PythonPath,
        $env:COMPARE_PYTHON_PATH,
        (Join-Path $script:BackRoot ".venv\Scripts\python.exe"),
        (Join-Path (Split-Path -Parent $script:CompareRoot) "Back\.venv\Scripts\python.exe")
    ) | Where-Object { $_ }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Python runtime was not found. Create Compare\Back\.venv or set COMPARE_PYTHON_PATH."
}

function Get-ListeningProcessId {
    param([int]$Port)
    $listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Get-ProcessRecord {
    param([int]$ProcessId)
    if (-not $ProcessId) { return $null }
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
}

function Invoke-JsonRequest {
    param([string]$Uri, [hashtable]$Headers = @{}, [int]$TimeoutSec = 5)
    return Invoke-RestMethod -Uri $Uri -Headers $Headers -TimeoutSec $TimeoutSec
}

function Test-BackReady {
    param([switch]$Quiet)
    try {
        $health = Invoke-JsonRequest "$($script:BackUrl)/health"
        $projects = Invoke-JsonRequest "$($script:BackUrl)/api/v1/projects"
        $cors = Invoke-WebRequest -UseBasicParsing -Uri "$($script:BackUrl)/health" -Headers @{ Origin = $script:FrontUrl } -TimeoutSec 5
        $allowedOrigin = $cors.Headers["Access-Control-Allow-Origin"]
        if ($health.data.status -ne "ok") { throw "health.status is not ok" }
        if (-not $projects.data -or $projects.data.Count -lt 1) { throw "Project directory is empty" }
        if ($allowedOrigin -ne $script:FrontUrl) { throw "CORS does not allow $($script:FrontUrl)" }
        if (-not $Quiet) { Write-Result "Back readiness" "PASS" "health ok; projects $($projects.data.Count); CORS ok" }
        return $true
    } catch {
        if (-not $Quiet) { Write-Result "Back readiness" "FAIL" $_.Exception.Message }
        return $false
    }
}

function Test-FrontReady {
    param([switch]$Quiet)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "$($script:FrontUrl)/" -TimeoutSec 5
        if ($response.StatusCode -ne 200) { throw "HTTP $($response.StatusCode)" }
        if ($response.Content -notmatch 'Signal Council') { throw "Response is not the Signal Council Front" }
        if (-not $Quiet) { Write-Result "Front readiness" "PASS" "HTTP 200; Signal Council page identified" }
        return $true
    } catch {
        if (-not $Quiet) { Write-Result "Front readiness" "FAIL" $_.Exception.Message }
        return $false
    }
}

function Show-MaterialRuntimeStatus {
    try {
        $projects = (Invoke-JsonRequest "$($script:BackUrl)/api/v1/projects").data
        $materials = (Invoke-JsonRequest "$($script:BackUrl)/api/v1/projects/$($projects[0].projectId)/materials").data
        $availableCount = @($materials | Where-Object { $_.originalAccess.available }).Count
        $statusSummary = @($materials | Group-Object { $_.originalAccess.status } | ForEach-Object { "$($_.Name):$($_.Count)" }) -join ", "
        if ($availableCount -gt 0) {
            Write-Result "Material runtime" "PASS" "Readable originals in first project: $availableCount; $statusSummary"
        } elseif ($statusSummary -match 'not_configured') {
            Write-Result "Material runtime" "WARN" "External materials are not configured; core system remains available and originals are unavailable; $statusSummary"
        } else {
            Write-Result "Material runtime" "WARN" "External materials are configured but the current database/archive has no readable binding; $statusSummary"
        }
    } catch {
        Write-Result "Material runtime" "WARN" "Status read failed: $($_.Exception.Message)"
    }
}

function Invoke-Preflight {
    $errors = [Collections.Generic.List[string]]::new()
    Write-Host "Signal Council local-reference preflight (does not install dependencies or start services)"

    try {
        $script:ResolvedPython = Resolve-PythonExecutable
        $pythonVersion = & $script:ResolvedPython -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
        $parts = $pythonVersion.Split('.')
        if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) { throw "Python >= 3.11 is required; current version is $pythonVersion" }
        & $script:ResolvedPython -c "import fastapi, uvicorn" 2>$null
        if ($LASTEXITCODE -ne 0) { throw "The current Python environment lacks FastAPI/Uvicorn dependencies" }
        Write-Result "Python" "PASS" "$pythonVersion；$($script:ResolvedPython)"
    } catch { $errors.Add($_.Exception.Message); Write-Result "Python" "FAIL" $_.Exception.Message }

    try {
        $nodeCommand = Get-Command node -ErrorAction Stop
        $nodeVersion = (& node --version).TrimStart('v')
        $nodeParts = $nodeVersion.Split('.')
        if ([int]$nodeParts[0] -lt 22 -or ([int]$nodeParts[0] -eq 22 -and [int]$nodeParts[1] -lt 13)) { throw "Node >= 22.13 is required; current version is $nodeVersion" }
        Get-Command npm.cmd -ErrorAction Stop | Out-Null
        if (-not (Test-Path -LiteralPath (Join-Path $script:FrontRoot "node_modules"))) { throw "Front/node_modules does not exist; install dependencies from the lockfile first" }
        Write-Result "Node/npm" "PASS" "Node $nodeVersion; npm.cmd available; dependencies installed"
    } catch { $errors.Add($_.Exception.Message); Write-Result "Node/npm" "FAIL" $_.Exception.Message }

    if (-not $env:COMPARE_DATABASE_PATH) {
        $env:COMPARE_DATABASE_PATH = Join-Path (Split-Path -Parent $script:RuntimeRoot) "compare.db"
    }
    if (-not $env:COMPARE_IMPORT_ROOT) {
        $env:COMPARE_IMPORT_ROOT = Join-Path (Split-Path -Parent $script:RuntimeRoot) "imports"
    }
    foreach ($pair in @(@("database", $env:COMPARE_DATABASE_PATH), @("import", $env:COMPARE_IMPORT_ROOT), @("deployment", $script:RuntimeRoot))) {
        try {
            if (Test-PathWithin -Path $pair[1] -Parent $script:CompareRoot) { throw "$($pair[0]) path must stay outside the repository: $($pair[1])" }
            Write-Result "$($pair[0]) root" "PASS" $pair[1]
        } catch { $errors.Add($_.Exception.Message); Write-Result "$($pair[0]) root" "FAIL" $_.Exception.Message }
    }

    if ($env:COMPARE_MATERIAL_ROOT) {
        try {
            if (-not [IO.Path]::IsPathRooted($env:COMPARE_MATERIAL_ROOT)) { throw "COMPARE_MATERIAL_ROOT must be an absolute path" }
            $nativeRoot = Join-Path $env:COMPARE_MATERIAL_ROOT "native-material-packs"
            if (-not (Test-Path -LiteralPath $nativeRoot -PathType Container)) { throw "External root does not contain native-material-packs" }
            Write-Result "Material root" "PASS" "Configured and required layout exists"
        } catch { $errors.Add($_.Exception.Message); Write-Result "Material root" "FAIL" $_.Exception.Message }
    } else {
        Write-Result "Material root" "WARN" "Not configured; the core system can start and original reads will honestly be unavailable"
    }

    # Public, credential-free startup is deterministic synthetic by default.
    # Real providers remain available only through explicit -AgentMode real or
    # COMPARE_AGENT_MODE=real configuration.
    $effectiveAgentMode = if ($AgentMode) { $AgentMode } elseif ($env:COMPARE_AGENT_MODE) { $env:COMPARE_AGENT_MODE } else { "synthetic" }
    $env:COMPARE_AGENT_MODE = $effectiveAgentMode
    if ($effectiveAgentMode -eq "real") {
        $provider = if ($env:COMPARE_AGENT_PROVIDER) { $env:COMPARE_AGENT_PROVIDER } else { "glm_cli" }
        $model = if ($env:COMPARE_AGENT_MODEL) { $env:COMPARE_AGENT_MODEL } else { "glm-5.2" }
        if ($provider -ne "glm_cli") {
            $message = "The local launcher preflights glm_cli only; current provider=$provider"
            $errors.Add($message); Write-Result "Agent provider" "FAIL" $message
        } else {
            try {
                if ($model -ne "glm-5.2") { throw "real glm_cli must be frozen to glm-5.2; current model is $model" }
                foreach ($roleVariable in "COMPARE_AGENT_BUSINESS_MODEL", "COMPARE_AGENT_RISK_MODEL", "COMPARE_AGENT_LEADERSHIP_MODEL") {
                    $roleModel = [Environment]::GetEnvironmentVariable($roleVariable, "Process")
                    if ($roleModel -and $roleModel -ne "glm-5.2") { throw "$roleVariable must be glm-5.2" }
                }
                $cliName = if ($env:COMPARE_AGENT_GLM_CLI_EXECUTABLE) { $env:COMPARE_AGENT_GLM_CLI_EXECUTABLE } else { "claude.cmd" }
                $cli = Get-Command $cliName -ErrorAction Stop
                $auth = (& $cli.Source auth status | ConvertFrom-Json)
                if (-not $auth.loggedIn) { throw "GLM CLI is not authenticated" }
                Write-Result "GLM CLI" "PASS" "CLI available; authentication ready; model glm-5.2"
            } catch { $errors.Add($_.Exception.Message); Write-Result "GLM CLI" "FAIL" $_.Exception.Message }
            if ($env:COMPARE_AGENT_BUDGET_APPROVED -eq "true") {
                Write-Result "GLM budget" "PASS" "Budget authorisation was explicitly confirmed by the operator"
            } else {
                $message = "Provider balance cannot be read automatically; real mode requires COMPARE_AGENT_BUDGET_APPROVED=true before start"
                $errors.Add($message); Write-Result "GLM budget" "FAIL" $message
            }
        }
    } else {
        Write-Result "Agent provider" "WARN" "Agent mode=$effectiveAgentMode; it will not impersonate real GLM"
    }

    foreach ($port in $BackPort, $FrontPort) {
        $listenerProcessId = Get-ListeningProcessId -Port $port
        if ($listenerProcessId) { Write-Result "Port $port" "WARN" "Already listening under PID $listenerProcessId; Start validates and reuses it only, never terminates it" }
        else { Write-Result "Port $port" "PASS" "Available" }
    }
    if (-not (Get-ListeningProcessId -Port $FrontPort)) {
        $frontPattern = [regex]::Escape($script:FrontRoot)
        $otherFront = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match $frontPattern -and $_.CommandLine -match 'vinext|vite' } |
            Select-Object -First 1
        if ($otherFront) {
            $message = "The same Front directory already has a dev server (PID $($otherFront.ProcessId)); vinext does not allow parallel starts in one directory and this script will not terminate it"
            $errors.Add($message); Write-Result "Front instance" "FAIL" $message
        }
    }

    if ($errors.Count -gt 0) { throw "Preflight failed ($($errors.Count) item(s)). Fix FAIL results and retry." }
    Write-Result "Preflight" "PASS" "Prerequisites satisfied"
}

function Wait-Ready {
    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
    do {
        if ((Test-BackReady -Quiet) -and (Test-FrontReady -Quiet)) { return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Front/Back did not become ready within $ReadyTimeoutSeconds seconds. Logs: $($script:LogRoot)"
}

function Save-InstanceState {
    param([bool]$BackOwned, [bool]$FrontOwned)
    $backPid = Get-ListeningProcessId -Port $BackPort
    $frontPid = Get-ListeningProcessId -Port $FrontPort
    $state = [ordered]@{
        schemaVersion = 1
        createdAt = (Get-Date).ToString("o")
        frontPort = $FrontPort
        backPort = $BackPort
        frontPid = $frontPid
        backPid = $backPid
        frontOwned = $FrontOwned
        backOwned = $BackOwned
        logRoot = $script:LogRoot
    }
    New-Item -ItemType Directory -Force -Path $script:RuntimeRoot | Out-Null
    $state | ConvertTo-Json | Set-Content -LiteralPath $script:StatePath -Encoding UTF8
}

function Start-Compare {
    Invoke-Preflight
    New-Item -ItemType Directory -Force -Path $script:LogRoot | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $env:COMPARE_DATABASE_PATH) | Out-Null
    New-Item -ItemType Directory -Force -Path $env:COMPARE_IMPORT_ROOT | Out-Null
    $env:COMPARE_CORS_ORIGINS = "$($script:FrontUrl),http://localhost:$FrontPort"
    $env:VITE_COMPARE_API_BASE = "$($script:BackUrl)/api/v1"
    $env:VITE_COMPARE_GATEWAY = "http"

    $backOwned = $false
    $frontOwned = $false
    if (Get-ListeningProcessId -Port $BackPort) {
        if (-not (Test-BackReady -Quiet)) { throw "Port $BackPort is occupied but is not a reusable Signal Council API; an unknown process will not be terminated." }
        Write-Result "Back start" "WARN" "Reusing an existing healthy service; this script does not own the process"
    } else {
        Start-Process -FilePath $script:ResolvedPython -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackPort") -WorkingDirectory $script:BackRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $script:LogRoot "back.stdout.log") -RedirectStandardError (Join-Path $script:LogRoot "back.stderr.log") | Out-Null
        $backOwned = $true
    }

    if (Get-ListeningProcessId -Port $FrontPort) {
        if (-not (Test-FrontReady -Quiet)) { throw "Port $FrontPort is occupied but is not a reusable Signal Council Front; an unknown process will not be terminated." }
        Write-Result "Front start" "WARN" "Reusing an existing Compare page; this script does not own the process"
    } else {
        Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontPort", "--strictPort") -WorkingDirectory $script:FrontRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $script:LogRoot "front.stdout.log") -RedirectStandardError (Join-Path $script:LogRoot "front.stderr.log") | Out-Null
        $frontOwned = $true
    }

    try { Wait-Ready }
    catch {
        Write-Result "Startup" "FAIL" $_.Exception.Message
        Get-Content -LiteralPath (Join-Path $script:LogRoot "back.stderr.log") -Tail 30 -ErrorAction SilentlyContinue
        Get-Content -LiteralPath (Join-Path $script:LogRoot "front.stderr.log") -Tail 30 -ErrorAction SilentlyContinue
        if ($frontOwned) {
            $startedFrontPid = Get-ListeningProcessId -Port $FrontPort
            Stop-OwnedProcess -Name "Front" -Port $FrontPort -ExpectedPid ([int]$startedFrontPid) -Owned $true
        }
        if ($backOwned) {
            $startedBackPid = Get-ListeningProcessId -Port $BackPort
            Stop-OwnedProcess -Name "Back" -Port $BackPort -ExpectedPid ([int]$startedBackPid) -Owned $true
        }
        throw
    }
    Save-InstanceState -BackOwned $backOwned -FrontOwned $frontOwned
    Test-BackReady | Out-Null
    Test-FrontReady | Out-Null
    Show-MaterialRuntimeStatus

    $projects = (Invoke-JsonRequest "$($script:BackUrl)/api/v1/projects").data
    $selectedProject = if ($ProjectId) { $projects | Where-Object { $_.projectId -eq $ProjectId } | Select-Object -First 1 }
    if (-not $selectedProject) { $selectedProject = $projects | Select-Object -First 1 }
    $projectUrl = "$($script:FrontUrl)/?project=$([uri]::EscapeDataString($selectedProject.projectId))&from=group"
    Write-Host ""
    Write-Host "Signal Council local reference run is ready." -ForegroundColor Green
    Write-Host "Front:   $($script:FrontUrl)/"
    Write-Host "Back:    $($script:BackUrl)/health"
    Write-Host "Project: $projectUrl"
    Write-Host "Logs:    $($script:LogRoot)"
}

function Show-Status {
    $backPid = Get-ListeningProcessId -Port $BackPort
    $frontPid = Get-ListeningProcessId -Port $FrontPort
    Write-Result "Back port" $(if ($backPid) { "PASS" } else { "FAIL" }) $(if ($backPid) { "PID $backPid" } else { "Not listening" })
    Write-Result "Front port" $(if ($frontPid) { "PASS" } else { "FAIL" }) $(if ($frontPid) { "PID $frontPid" } else { "Not listening" })
    Test-BackReady | Out-Null
    Test-FrontReady | Out-Null
    Show-MaterialRuntimeStatus
    if (Test-Path -LiteralPath $script:StatePath) { Write-Result "State" "PASS" $script:StatePath }
    else { Write-Result "State" "WARN" "No instance state was saved by this script; Stop will not touch an unknown process" }
}

function Stop-OwnedProcess {
    param([string]$Name, [int]$Port, [int]$ExpectedPid, [bool]$Owned)
    if (-not $Owned) { Write-Result "$Name stop" "WARN" "Process was not started by this script and was preserved"; return }
    $listenerPid = Get-ListeningProcessId -Port $Port
    if (-not $listenerPid) { Write-Result "$Name stop" "PASS" "Port is already stopped"; return }
    if ($listenerPid -ne $ExpectedPid) { Write-Result "$Name stop" "WARN" "Listening PID changed; refusing to terminate"; return }
    $record = Get-ProcessRecord -ProcessId $listenerPid
    $command = if ($record) { [string]$record.CommandLine } else { "" }
    $expected = if ($Name -eq "Back") { 'uvicorn|app\.main:app' } else { 'vinext|vite' }
    if ($command -notmatch $expected) { Write-Result "$Name stop" "WARN" "Process command does not match; refusing to terminate"; return }
    Stop-Process -Id $listenerPid -ErrorAction Stop
    Write-Result "$Name stop" "PASS" "Stopped PID $listenerPid"
}

function Stop-Compare {
    if (-not (Test-Path -LiteralPath $script:StatePath)) {
        Write-Result "Stop" "WARN" "No instance state exists; no process was terminated for safety"
        return
    }
    $state = Get-Content -Raw -LiteralPath $script:StatePath | ConvertFrom-Json
    Stop-OwnedProcess -Name "Front" -Port $FrontPort -ExpectedPid ([int]$state.frontPid) -Owned ([bool]$state.frontOwned)
    Stop-OwnedProcess -Name "Back" -Port $BackPort -ExpectedPid ([int]$state.backPid) -Owned ([bool]$state.backOwned)
    $ownedListenerRemains = (([bool]$state.frontOwned -and (Get-ListeningProcessId -Port $FrontPort)) -or
        ([bool]$state.backOwned -and (Get-ListeningProcessId -Port $BackPort)))
    if ($ownedListenerRemains) {
        Write-Result "Stop state" "WARN" "A script-owned port remains listening; state file was retained for diagnosis and no force-stop occurred"
    } else {
        Remove-Item -LiteralPath $script:StatePath -Force
    }
}

if (-not $EnvFile) {
    $candidateEnv = Join-Path $script:BackRoot ".env"
    if (Test-Path -LiteralPath $candidateEnv) { $EnvFile = $candidateEnv }
}
Import-CompareEnvFile -Path $EnvFile
$script:RuntimeRoot = if ($env:COMPARE_DEPLOY_RUNTIME_ROOT) {
    [IO.Path]::GetFullPath($env:COMPARE_DEPLOY_RUNTIME_ROOT)
} elseif ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "CompareWorkbench\deployment"
} else {
    Join-Path $env:TEMP "CompareWorkbench\deployment"
}
$script:InstanceName = "$FrontPort-$BackPort"
$script:StatePath = Join-Path $script:RuntimeRoot "instance-$($script:InstanceName).json"
$script:LogRoot = Join-Path $script:RuntimeRoot "logs\$($script:InstanceName)"
$script:FrontUrl = "http://127.0.0.1:$FrontPort"
$script:BackUrl = "http://127.0.0.1:$BackPort"

switch ($Action) {
    "Preflight" { Invoke-Preflight }
    "Start" { Start-Compare }
    "Status" { Show-Status }
    "Check" {
        $backOk = Test-BackReady
        $frontOk = Test-FrontReady
        Show-MaterialRuntimeStatus
        if (-not ($backOk -and $frontOk)) { throw "Signal Council readiness check failed." }
    }
    "Stop" { Stop-Compare }
}
