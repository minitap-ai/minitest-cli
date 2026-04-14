#!/usr/bin/env bash
# install.sh — Install minitest-cli via uv (installs uv if not installed)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/minitap-ai/minitest-cli/main/install.sh | bash
#
set -euo pipefail

PACKAGE="minitest-cli"
INSTALLED_VIA=""
UV_BIN_DIR="${HOME}/.local/bin"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33mWarning:\033[0m %s\n' "$*"; }
error() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; }

# -------------------------------------------------------------------
# ensure_on_path — make sure a directory is on PATH now + in shell rc
# -------------------------------------------------------------------
ensure_on_path() {
  local dir="$1"
  case ":${PATH}:" in
    *":${dir}:"*) return 0 ;;  # already on PATH
  esac
  export PATH="${dir}:${PATH}"

  # Patch shell rc files so new terminals pick it up
  local rc_files=()
  [[ -f "${HOME}/.zshrc" ]]    && rc_files+=("${HOME}/.zshrc")
  [[ -f "${HOME}/.bashrc" ]]   && rc_files+=("${HOME}/.bashrc")
  [[ -f "${HOME}/.profile" ]]  && rc_files+=("${HOME}/.profile")
  # If none exist, create .zshrc on macOS, .bashrc on Linux
  if [[ ${#rc_files[@]} -eq 0 ]]; then
    if [[ "$(uname)" == "Darwin" ]]; then
      rc_files=("${HOME}/.zshrc")
    else
      rc_files=("${HOME}/.bashrc")
    fi
  fi

  local line="export PATH=\"${dir}:\$PATH\""
  # Also check for the $HOME-relative form and .local/bin/env (uv's pattern)
  local dir_relative="${dir/#${HOME}/\$HOME}"
  for rc in "${rc_files[@]}"; do
    if grep -qF "${dir}" "${rc}" 2>/dev/null \
       || grep -qF "${dir_relative}" "${rc}" 2>/dev/null \
       || grep -q "local/bin/env" "${rc}" 2>/dev/null; then
      :  # already has a PATH entry for this dir
    else
      info "Adding ${dir} to PATH in ${rc}"
      printf '\n# Added by minitest-cli installer\n%s\n' "${line}" >> "${rc}"
    fi
  done
}

# -------------------------------------------------------------------
# install_with_uv — use uv tool install (~1 second)
# -------------------------------------------------------------------
install_with_uv() {
  info "Installing ${PACKAGE} with uv…"
  if uv tool install "${PACKAGE}" --force 2>&1; then
    INSTALLED_VIA="uv"
    ensure_on_path "${UV_BIN_DIR}"
    return 0
  fi
  warn "uv tool install failed."
  return 1
}

# -------------------------------------------------------------------
# bootstrap_uv — install uv itself, then use it to install minitest
# -------------------------------------------------------------------
bootstrap_uv() {
  info "Installing uv package manager…"
  if curl -LsSf https://astral.sh/uv/install.sh | sh 2>&1; then
    ensure_on_path "${UV_BIN_DIR}"
    install_with_uv
    return $?
  fi
  warn "Failed to install uv."
  return 1
}

# -------------------------------------------------------------------
# Main: use uv if available, otherwise bootstrap it
# -------------------------------------------------------------------

# 1. uv already installed? Use it
if command -v uv &>/dev/null; then
  install_with_uv || true
fi

# 2. No uv — bootstrap it
if [[ -z "${INSTALLED_VIA}" ]]; then
  bootstrap_uv || true
fi

if [[ -z "${INSTALLED_VIA}" ]]; then
  error "Installation failed."
  error "Please install manually:"
  error "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  error "  uv tool install ${PACKAGE}"
  exit 1
fi

# -------------------------------------------------------------------
# Verify installation
# -------------------------------------------------------------------
if command -v minitest &>/dev/null; then
  ok "minitest-cli installed successfully!"
  minitest --version
  echo ""
  info "Next steps:"
  echo "  minitest auth login       # authenticate"
  echo "  minitest apps list        # list your apps"
  echo "  minitest --help           # see all commands"
else
  # minitest binary exists but shell doesn't see it yet (current session)
  if [[ -x "${UV_BIN_DIR}/minitest" ]]; then
    ok "minitest-cli installed successfully!"
    "${UV_BIN_DIR}/minitest" --version
    echo ""
    warn "Run this to use minitest in your current terminal:"
    echo "  export PATH=\"${UV_BIN_DIR}:\$PATH\""
    echo ""
    info "It will work automatically in new terminals."
    echo ""
    info "Next steps:"
    echo "  minitest auth login       # authenticate"
    echo "  minitest apps list        # list your apps"
    echo "  minitest --help           # see all commands"
  else
    error "Installation reported success, but 'minitest' binary was not found."
    error "Please try reinstalling:"
    error "  uv tool install ${PACKAGE}"
    exit 1
  fi
fi
