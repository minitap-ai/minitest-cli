# install.ps1 - Install minitest-cli via uv (installs uv if not installed)
#
# Usage:
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/minitap-ai/minitest-cli/main/install.ps1 | iex"
#

$ErrorActionPreference = "Stop"
$Package = "minitest-cli"
$InstalledVia = ""

function Write-Info  { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Blue }
function Write-Ok    { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Green }
function Write-Warn  { param([string]$Message) Write-Host "Warning: $Message" -ForegroundColor Yellow }
function Write-Err   { param([string]$Message) Write-Host "Error: $Message" -ForegroundColor Red }

function Resolve-Uv {
    # Prefer a uv already resolvable on PATH. Restrict to Application so an
    # alias/function named uv (whose .Path is empty) can't shadow the exe.
    $cmd = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Path }
    # Otherwise look in the known install locations. A freshly bootstrapped uv
    # is on disk but not yet reliably resolvable by name in this session
    # (PowerShell caches command lookups), so we call it by full path.
    $candidates = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:USERPROFILE\.cargo\bin\uv.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Get-UvToolBinDir {
    $uv = Resolve-Uv
    if ($uv) {
        $dir = & $uv tool dir --bin 2>$null
        if ($dir) { return $dir }
    }
    return "$env:USERPROFILE\.local\bin"
}

function Add-PathEntryIfMissing {
    param([string]$Entry)
    $normalizedEntry = $Entry.TrimEnd('\')
    $pathEntries = ($env:PATH -split ';' | Where-Object { $_ }) | ForEach-Object { $_.TrimEnd('\') }
    if (-not ($pathEntries | Where-Object { $_ -ieq $normalizedEntry })) {
        $env:PATH = "$Entry;$env:PATH"
    }
}

function Install-WithUv {
    Write-Info "Installing $Package with uv..."
    $uv = Resolve-Uv
    if (-not $uv) {
        Write-Warn "uv executable could not be located."
        return $false
    }
    try {
        & $uv tool install $Package --force 2>&1 | Write-Host
        if ($LASTEXITCODE -eq 0) {
            $script:InstalledVia = "uv"
            return $true
        }
        Write-Warn "uv tool install failed with exit code $LASTEXITCODE."
        return $false
    } catch {
        Write-Warn "uv tool install failed: $($_.Exception.Message)"
        return $false
    }
}

function Install-Uv {
    Write-Info "Installing uv package manager..."
    try {
        & ([scriptblock]::Create((Invoke-RestMethod "https://astral.sh/uv/install.ps1")))
        # Refresh PATH so uv is available in this session
        $uvPath = "$env:USERPROFILE\.local\bin"
        Add-PathEntryIfMissing -Entry $uvPath
        # Also check cargo bin (uv may install there on some setups)
        $cargoPath = "$env:USERPROFILE\.cargo\bin"
        Add-PathEntryIfMissing -Entry $cargoPath
        return $true
    } catch {
        Write-Warn "Failed to install uv."
        return $false
    }
}

# -------------------------------------------------------------------
# Main: use uv if available, otherwise bootstrap it
# -------------------------------------------------------------------

# 1. uv already installed? Use it
if (Resolve-Uv) {
    Install-WithUv | Out-Null
}

# 2. No uv - bootstrap it
if (-not $InstalledVia) {
    if (Install-Uv) {
        Install-WithUv | Out-Null
    }
}

if (-not $InstalledVia) {
    Write-Err "Installation failed."
    Write-Err "Please install manually:"
    Write-Err "  powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`""
    Write-Err "  uv tool install $Package"
    exit 1
}

# -------------------------------------------------------------------
# Verify installation
# -------------------------------------------------------------------
if (Get-Command minitest -ErrorAction SilentlyContinue) {
    Write-Ok "minitest-cli installed successfully!"
    minitest --version
    Write-Host ""
    Write-Info "Next steps:"
    Write-Host "  minitest auth login       # authenticate"
    Write-Host "  minitest apps list        # list your apps"
    Write-Host "  minitest --help           # see all commands"
} else {
    # Check uv tool bin directory
    $toolBinDir = Get-UvToolBinDir
    $uvBin = Join-Path $toolBinDir "minitest.exe"
    if (Test-Path $uvBin) {
        Write-Ok "minitest-cli installed successfully!"
        & $uvBin --version
        Write-Host ""
        Write-Warn "minitest is not on your PATH in this session."
        Write-Warn "Close and reopen your terminal, then run:"
        Write-Host "  minitest --help"
    } else {
        Write-Err "Installation reported success, but 'minitest' binary was not found."
        Write-Err "Please try reinstalling:"
        Write-Err "  uv tool install $Package"
        exit 1
    }
}
