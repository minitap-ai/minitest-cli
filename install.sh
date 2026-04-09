#!/usr/bin/env bash
# install.sh — Install minitest-cli (brew → pipx → python3 -m pip fallback)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/minitap-ai/minitest-cli/main/install.sh | bash
#
set -euo pipefail

PACKAGE="minitest-cli"
BREW_TAP="minitap-ai/tap/minitest-cli"
INSTALLED_VIA=""

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33mWarning:\033[0m %s\n' "$*"; }
error() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; }

# -------------------------------------------------------------------
# 1. Try installers in order: brew → pipx → python3 -m pip
#    Each attempt is conditional — failure falls through to the next.
# -------------------------------------------------------------------
if command -v brew &>/dev/null; then
  info "Installing $PACKAGE with Homebrew…"
  if brew install "$BREW_TAP"; then
    INSTALLED_VIA="brew"
  else
    warn "Homebrew install failed — trying next method."
  fi
fi

if [[ -z "$INSTALLED_VIA" ]] && command -v pipx &>/dev/null; then
  info "Installing $PACKAGE with pipx…"
  if pipx install "$PACKAGE" --force; then
    INSTALLED_VIA="pipx"
  else
    warn "pipx install failed — trying next method."
  fi
fi

if [[ -z "$INSTALLED_VIA" ]] && command -v python3 &>/dev/null; then
  info "Installing $PACKAGE with python3 -m pip…"
  if python3 -m pip install --user "$PACKAGE"; then
    INSTALLED_VIA="pip"
  else
    warn "pip install failed."
  fi
fi

if [[ -z "$INSTALLED_VIA" ]]; then
  error "All install methods failed or no supported package manager found."
  error "  macOS:  Install Homebrew → https://brew.sh"
  error "  Linux:  sudo apt install pipx && pipx ensurepath"
  exit 1
fi

# -------------------------------------------------------------------
# 2. Verify installation
# -------------------------------------------------------------------
if command -v minitest &>/dev/null; then
  info "minitest-cli installed successfully via $INSTALLED_VIA! 🎉"
  minitest --version
  echo ""
  info "Next steps:"
  echo "  minitest auth login       # authenticate"
  echo "  minitest apps list        # list your apps"
  echo "  minitest --help           # see all commands"
else
  warn "Installation completed, but 'minitest' is not on your PATH."
  if [[ "$INSTALLED_VIA" == "brew" ]]; then
    warn "Try restarting your shell or check: brew --prefix"
  else
    warn "You may need to restart your shell or add ~/.local/bin to your PATH."
  fi
fi
