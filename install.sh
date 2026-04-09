#!/usr/bin/env bash
# install.sh — Install minitest-cli (brew → pipx → pip fallback)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/minitap-ai/minitest-cli/main/install.sh | bash
#
set -euo pipefail

PACKAGE="minitest-cli"
BREW_TAP="minitap-ai/tap/minitest-cli"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33mWarning:\033[0m %s\n' "$*"; }
error() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; }

# -------------------------------------------------------------------
# 1. Prefer brew (cleanest), then pipx, then pip as last resort
# -------------------------------------------------------------------
if command -v brew &>/dev/null; then
  info "Installing $PACKAGE with Homebrew…"
  brew install "$BREW_TAP"
elif command -v pipx &>/dev/null; then
  info "Installing $PACKAGE with pipx…"
  pipx install "$PACKAGE" --force
elif command -v pip &>/dev/null; then
  warn "brew and pipx not found — falling back to pip."
  info "Installing $PACKAGE with pip…"
  pip install --user "$PACKAGE"
elif command -v pip3 &>/dev/null; then
  warn "brew and pipx not found — falling back to pip3."
  info "Installing $PACKAGE with pip3…"
  pip3 install --user "$PACKAGE"
else
  error "No supported package manager found (brew, pipx, or pip)."
  error "  macOS:  Install Homebrew → https://brew.sh"
  error "  Linux:  sudo apt install pipx && pipx ensurepath"
  exit 1
fi

# -------------------------------------------------------------------
# 2. Verify installation
# -------------------------------------------------------------------
if command -v minitest &>/dev/null; then
  info "minitest-cli installed successfully! 🎉"
  minitest --version
  echo ""
  info "Next steps:"
  echo "  minitest auth login       # authenticate"
  echo "  minitest apps list        # list your apps"
  echo "  minitest --help           # see all commands"
else
  warn "Installation completed, but 'minitest' is not on your PATH."
  warn "You may need to restart your shell or add ~/.local/bin to your PATH."
fi
