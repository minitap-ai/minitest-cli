#!/usr/bin/env bash
# install.sh — Install minitest-cli via uv (installs uv if not installed)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/minitap-ai/minitest-cli/main/install.sh | bash
#
set -euo pipefail

PACKAGE="minitest-cli"
INSTALLED_VIA=""

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33mWarning:\033[0m %s\n' "$*"; }
error() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; }

# Resolve the directory where uv installs tool executables.
# Respects UV_TOOL_BIN_DIR / XDG_BIN_HOME; falls back to ~/.local/bin.
get_uv_bin_dir() {
  uv tool dir --bin 2>/dev/null || printf '%s\n' "${UV_TOOL_BIN_DIR:-${XDG_BIN_HOME:-${HOME}/.local/bin}}"
}

# Resolve the target shell rc file based on $SHELL.
get_shell_rc() {
  case "${SHELL:-}" in
    */zsh)  printf '%s\n' "${HOME}/.zshrc" ;;
    */bash) printf '%s\n' "${HOME}/.bashrc" ;;
    *)      printf '%s\n' "${HOME}/.profile" ;;
  esac
}

# -------------------------------------------------------------------
# ensure_on_path — make sure a directory is on PATH now + in shell rc
# -------------------------------------------------------------------
ensure_on_path() {
  local dir="$1"
  case ":${PATH}:" in
    *":${dir}:"*) return 0 ;;  # already on PATH
  esac
  export PATH="${dir}:${PATH}"

  # Patch the user's shell rc file so new terminals pick it up
  local rc
  rc="$(get_shell_rc)"

  local line="export PATH=\"${dir}:\$PATH\""
  local dir_relative="${dir/#${HOME}/\$HOME}"
  if grep -qF "${dir}" "${rc}" 2>/dev/null \
     || grep -qF "${dir_relative}" "${rc}" 2>/dev/null \
     || grep -q "local/bin/env" "${rc}" 2>/dev/null; then
    :  # already has a PATH entry for this dir
  else
    info "Adding ${dir} to PATH in ${rc}"
    printf '\n# Added by minitest-cli installer\n%s\n' "${line}" >> "${rc}"
  fi
}

# -------------------------------------------------------------------
# install_with_uv — use uv tool install
# -------------------------------------------------------------------
install_with_uv() {
  info "Installing ${PACKAGE} with uv…"
  if uv tool install "${PACKAGE}" --force 2>&1; then
    INSTALLED_VIA="uv"
    local bin_dir
    bin_dir="$(get_uv_bin_dir)"
    ensure_on_path "${bin_dir}"
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
    # uv installer defaults to ~/.local/bin; add it so uv is available
    ensure_on_path "${HOME}/.local/bin"
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
  uv_bin_dir="$(get_uv_bin_dir)"
  if [[ -x "${uv_bin_dir}/minitest" ]]; then
    ok "minitest-cli installed successfully!"
    "${uv_bin_dir}/minitest" --version
    echo ""
    warn "Run this to use minitest in your current terminal:"
    echo "  export PATH=\"${uv_bin_dir}:\$PATH\""
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
