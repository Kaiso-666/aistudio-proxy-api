# Waits for tools/login_capture.py to finish and its browser to close, then
# starts the proxy headless against the captured session.
#
# Why the wait matters: login_capture writes the state file a moment before
# its browser exits, and the proxy launches its own Camoufox on port 9222.
# Starting too early collides on that port.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$state = Join-Path $root 'auth_profiles\active\login.json'
$log = Join-Path $env:TEMP 'opencode\autostart.log'

function Note($msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss') $msg"
    Add-Content -Path $log -Value $line
}

Note 'watcher started; waiting for login capture to finish'

$deadline = (Get-Date).AddMinutes(20)
while ((Get-Date) -lt $deadline) {
    $alive = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*login_capture*' }
    if (-not $alive) { break }
    Start-Sleep -Seconds 3
}

if (-not (Test-Path $state)) {
    Note 'ABORT: no auth state captured (login window closed without a session)'
    exit 1
}

Note ("session found: {0:N0} bytes" -f (Get-Item $state).Length)

# Give the capture browser a moment to fully release port 9222.
Start-Sleep -Seconds 5

$py = Join-Path $root '.venv\Scripts\python.exe'
$out = Join-Path $env:TEMP 'opencode\server_out.log'
$err = Join-Path $env:TEMP 'opencode\server_err.log'

Note 'starting proxy on 2048'
Start-Process -FilePath $py `
    -ArgumentList 'launch_camoufox.py', '--headless', '--active-auth-json', $state, '--server-port', '2048', '--stream-port', '3120' `
    -RedirectStandardOutput $out -RedirectStandardError $err `
    -NoNewWindow

$healthy = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:2048/health' -TimeoutSec 3 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $healthy = $true; break }
    } catch { }
}

if ($healthy) { Note 'HEALTHY: http://127.0.0.1:2048/v1 is up' }
else { Note 'WARN: server did not answer /health within 180s (see server_err.log)' }
