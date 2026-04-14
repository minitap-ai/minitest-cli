# install.ps1 — Install minitest-cli via uv (installs uv if not installed)
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

function Install-WithUv {
    Write-Info "Installing $Package with uv..."
    try {
        uv tool install $Package --force 2>&1 | Write-Host
        $script:InstalledVia = "uv"
        return $true
    } catch {
        Write-Warn "uv tool install failed."
        return $false
    }
}

function Install-Uv {
    Write-Info "Installing uv package manager..."
    try {
        & ([scriptblock]::Create((Invoke-RestMethod "https://astral.sh/uv/install.ps1")))
        # Refresh PATH so uv is available in this session
        $uvPath = "$env:USERPROFILE\.local\bin"
        if ($env:PATH -notlike "*$uvPath*") {
            $env:PATH = "$uvPath;$env:PATH"
        }
        # Also check cargo bin (uv may install there on some setups)
        $cargoPath = "$env:USERPROFILE\.cargo\bin"
        if ($env:PATH -notlike "*$cargoPath*") {
            $env:PATH = "$cargoPath;$env:PATH"
        }
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
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Install-WithUv | Out-Null
}

# 2. No uv — bootstrap it
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
    # Check common uv tool bin locations
    $uvBin = "$env:USERPROFILE\.local\bin\minitest.exe"
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
