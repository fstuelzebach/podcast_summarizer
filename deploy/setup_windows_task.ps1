# -----------------------------------------------------------------------------
# Registers "Podcast-Ingest" on the always-on Windows PC (standby for the VPS).
#
# Run from an elevated PowerShell prompt:
#   cd D:\podcast_summarizer
#   .\deploy\setup_windows_task.ps1                    # standby (default)
#   .\deploy\setup_windows_task.ps1 -Primary           # PC takes over transcription
#
# Before the first run, once:
#   git clone https://github.com/fstuelzebach/financial_research_data.git D:\financial_research_data
#   python -m venv .venv ; .venv\Scripts\pip install -e .
# and create .env (see .env.example) with DATA_DIR=D:\financial_research_data, PUBLISH=1.
#
# Standby: the task wakes the PC at 04:30 and 16:30, pulls the data repo and exits
# within seconds if the primary (VPS) has published in the last STANDBY_AFTER_HOURS.
# Otherwise it ingests itself. -Primary sets HOST_ROLE=primary in .env; then also
# set HOST_ROLE=standby on the VPS (or remove its cron line).
#
# WakeToRun wakes the PC from sleep (not shutdown); "Allow wake timers" must be
# Enabled in the power plan (same prerequisite as Olymp-Weekly).
# -----------------------------------------------------------------------------
param(
    [switch]$Primary,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$Python = "$ProjectRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Python not found at $Python - create the venv first (see header)."
    exit 1
}

$EnvFile = "$ProjectRoot\.env"
$Role = if ($Primary) { "primary" } else { "standby" }
if (Test-Path $EnvFile) {
    $lines = Get-Content $EnvFile | Where-Object { $_ -notmatch '^HOST_ROLE=' }
    Set-Content $EnvFile (@($lines) + "HOST_ROLE=$Role") -Encoding utf8
} else {
    Write-Warning ".env missing - copy .env.example and fill DATA_DIR/PUBLISH/NTFY_TOPIC."
}

# Fixed local wall-clock times (see olymp-capital: offsets pin triggers to UTC across DST)
function Local-Time($Trigger) {
    foreach ($t in @($Trigger)) { $t.StartBoundary = ([datetime]$t.StartBoundary).ToString("s") }
    return $Trigger
}
$Triggers = @(
    (Local-Time (New-ScheduledTaskTrigger -Daily -At "04:30")),
    (Local-Time (New-ScheduledTaskTrigger -Daily -At "16:30"))
)

$Action = New-ScheduledTaskAction -Execute $Python `
    -Argument "-m podcast_summarizer ingest" -WorkingDirectory $ProjectRoot
$Settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

Unregister-ScheduledTask -TaskName "Podcast-Ingest" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "Podcast-Ingest" -Action $Action -Trigger $Triggers `
    -Settings $Settings -Principal $Principal `
    -Description "podcast_summarizer ingest ($Role) - transcripts to financial_research_data" | Out-Null

Write-Host "[OK] Podcast-Ingest registered as $Role (04:30 + 16:30, WakeToRun)."
Write-Host "     Test now:  Start-ScheduledTask Podcast-Ingest ; Get-Content logs\ingest.log -Tail 20"
