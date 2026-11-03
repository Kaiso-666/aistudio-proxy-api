param(
    [ValidateSet('setup', 'debug', 'headless', 'verify', 'api')]
    [string]$Mode = 'debug',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = Join-Path $root '.venv\Scripts\python.exe'

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

switch ($Mode) {

    'setup' {
        Step 'Installing a CPython 3.12 runtime (uv, no admin required)'
        python -m uv python install 3.12

        Step 'Creating .venv'
        if (-not (Test-Path $py)) { python -m uv venv --python 3.12 .venv }

        Step 'Installing runtime dependencies'
        python -m uv pip install --python $py -r requirements.txt

        # `camoufox fetch` streams ~1.2 GB straight from the GitHub release CDN
        # with no resume; on a throttled link it stalls forever. If the archive
        # has already been fetched by other means, install from that instead.
        $browserZip = Join-Path $env:TEMP 'opencode\camoufox.zip'
        if (Test-Path $browserZip) {
            Step "Installing Camoufox from local archive: $browserZip"
            & $py tools\install_camoufox_zip.py $browserZip
        } else {
            Step 'Fetching the Camoufox browser build (~1.2 GB, no resume)'
            & $py -m camoufox fetch
        }

        $geoZip = Join-Path $env:TEMP 'opencode\geoip.zip'
        if (Test-Path $geoZip) {
            Step "Installing GeoIP database from local archive: $geoZip"
            & $py tools\install_geoip_zip.py $geoZip
        }

        Step 'Verifying the anti-detection surface'
        & $py tools\verify_stealth.py
    }

    'verify' {
        & $py tools\verify_stealth.py
    }

    'debug' {
        Step 'Starting in DEBUG mode - complete the Google login in the window'
        & $py launch_camoufox.py --debug @Rest
    }

    'headless' {
        Step 'Starting in HEADLESS mode (requires auth_profiles/active/)'
        & $py launch_camoufox.py --headless @Rest
    }

    'api' {
        Step 'Starting API server only (no browser) - config smoke test'
        $env:LAUNCH_MODE = 'direct_debug_no_browser'
        & $py server.py @Rest
    }
}
