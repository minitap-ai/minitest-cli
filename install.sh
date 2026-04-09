#!/usr/bin/env bash
# install.sh — Install minitest-cli using pipx (or pip as fallback)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/minitap-ai/minitest-cli/main/install.sh | bash
#
set -euo pipefail

PACKAGE="minitest-cli"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33mWarning:\033[0m %s\n' "$*"; }
error() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; }

# -------------------------------------------------------------------
# 1. Prefer pipx (isolated environment), fall back to pip
# -------------------------------------------------------------------
if command -v pipx &>/dev/null; then
  info "Installing $PACKAGE with pipx…"
  pipx install "$PACKAGE" --force
elif command -v pip &>/dev/null; then
  warn "pipx not found — falling back to pip."
  info "Installing $PACKAGE with pip…"
  pip install --user "$PACKAGE"
elif command -v pip3 &>/dev/null; then
  warn "pipx not found — falling back to pip3."
  info "Installing $PACKAGE with pip3…"
  pip3 install --user "$PACKAGE"
else
  error "Neither pipx nor pip found. Please install Python 3.10+ first."
  error "  macOS:  brew install pipx && pipx ensurepath"
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
