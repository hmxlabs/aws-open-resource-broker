#!/usr/bin/env bash
# install.sh — Install and initialise Open Resource Broker (ORB)
#
# Usage:
#   ./install.sh [OPTIONS]
#
# Options:
#   --prefix DIR          Installation prefix (default: /usr/local or ~/.orb if non-root)
#   --venv-path DIR       Python venv path (default: PREFIX/lib/orb-venv)
#   --config-dir DIR      ORB config directory (default: ~/.config/orb)
#   --work-dir DIR        ORB working directory (default: ~/.local/share/orb)
#   --log-dir DIR         ORB log directory (default: ~/.local/share/orb/logs)
#   --scripts-dir DIR     Directory where ORB wrapper scripts are placed (default: PREFIX/bin)
#   --non-interactive     Suppress all prompts; fail on missing required inputs
#   --scheduler NAME      Scheduler backend: default|hostfactory (default: default)
#   --provider NAME       Cloud provider: aws (default: aws)
#
# Environment variable equivalents (all options):
#   ORB_INSTALL_PREFIX, ORB_VENV_PATH, ORB_CONFIG_DIR, ORB_WORK_DIR,
#   ORB_LOG_DIR, ORB_SCRIPTS_DIR, ORB_NON_INTERACTIVE, ORB_SCHEDULER,
#   ORB_PROVIDER
#
# HF integration mode:
#   Set --scripts-dir to the directory HostFactory expects ORB scripts in.
#   The installer places an `orb` wrapper there that activates the venv.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults (overridden by env vars, then by flags)
# ---------------------------------------------------------------------------

_is_root() { [[ "$(id -u)" -eq 0 ]]; }

if _is_root; then
    DEFAULT_PREFIX="/usr/local"
else
    DEFAULT_PREFIX="${HOME}/.orb"
fi

PREFIX="${ORB_INSTALL_PREFIX:-${DEFAULT_PREFIX}}"
VENV_PATH="${ORB_VENV_PATH:-}"
CONFIG_DIR="${ORB_CONFIG_DIR:-${HOME}/.config/orb}"
WORK_DIR="${ORB_WORK_DIR:-${HOME}/.local/share/orb}"
LOG_DIR="${ORB_LOG_DIR:-}"
SCRIPTS_DIR="${ORB_SCRIPTS_DIR:-}"
NON_INTERACTIVE="${ORB_NON_INTERACTIVE:-0}"
SCHEDULER="${ORB_SCHEDULER:-default}"
PROVIDER="${ORB_PROVIDER:-aws}"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)         PREFIX="$2";          shift 2 ;;
        --venv-path)      VENV_PATH="$2";       shift 2 ;;
        --config-dir)     CONFIG_DIR="$2";      shift 2 ;;
        --work-dir)       WORK_DIR="$2";        shift 2 ;;
        --log-dir)        LOG_DIR="$2";         shift 2 ;;
        --scripts-dir)    SCRIPTS_DIR="$2";     shift 2 ;;
        --non-interactive) NON_INTERACTIVE=1;   shift   ;;
        --scheduler)      SCHEDULER="$2";       shift 2 ;;
        --provider)       PROVIDER="$2";        shift 2 ;;
        --help|-h)
            sed -n '/^# Usage:/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "ERROR: unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Apply defaults that depend on PREFIX (after flags are parsed)
VENV_PATH="${VENV_PATH:-${PREFIX}/lib/orb-venv}"
SCRIPTS_DIR="${SCRIPTS_DIR:-${PREFIX}/bin}"
LOG_DIR="${LOG_DIR:-${WORK_DIR}/logs}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { echo "[orb-install] $*"; }
warn()  { echo "[orb-install] WARN: $*" >&2; }
die()   { echo "[orb-install] ERROR: $*" >&2; exit 1; }

confirm() {
    # confirm "message" — skipped (returns 0) in non-interactive mode
    if [[ "${NON_INTERACTIVE}" == "1" ]]; then
        return 0
    fi
    local answer
    read -r -p "$1 [y/N] " answer
    [[ "${answer,,}" == "y" ]]
}

require_cmd() {
    command -v "$1" &>/dev/null || die "'$1' not found in PATH. $2"
}

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------

case "${SCHEDULER}" in
    default|hostfactory) ;;
    *) die "unknown scheduler '${SCHEDULER}'. Valid values: default, hostfactory" ;;
esac

case "${PROVIDER}" in
    aws) ;;
    *) die "unknown provider '${PROVIDER}'. Valid values: aws" ;;
esac

# ---------------------------------------------------------------------------
# Step 1: Detect Python
# ---------------------------------------------------------------------------

info "detecting Python..."
PYTHON=""
for candidate in python3 python; do
    if command -v "${candidate}" &>/dev/null; then
        ver=$("${candidate}" -c 'import sys; print(sys.version_info >= (3,9))' 2>/dev/null || echo False)
        if [[ "${ver}" == "True" ]]; then
            PYTHON="${candidate}"
            break
        fi
    fi
done

if [[ -z "${PYTHON}" ]]; then
    die "Python 3.9+ not found. Install Python before running this script."
fi
info "using Python: $(command -v "${PYTHON}") ($("${PYTHON}" --version))"

# ---------------------------------------------------------------------------
# Step 2: Create directories
# ---------------------------------------------------------------------------

info "creating directories..."
mkdir -p "${VENV_PATH}"
mkdir -p "${CONFIG_DIR}"
mkdir -p "${WORK_DIR}"
mkdir -p "${LOG_DIR}"
mkdir -p "${SCRIPTS_DIR}"

# ---------------------------------------------------------------------------
# Step 3: Create or reuse venv
# ---------------------------------------------------------------------------

if [[ ! -f "${VENV_PATH}/bin/activate" ]]; then
    info "creating virtual environment at ${VENV_PATH}..."
    "${PYTHON}" -m venv "${VENV_PATH}"
else
    info "reusing existing virtual environment at ${VENV_PATH}"
fi

VENV_PIP="${VENV_PATH}/bin/pip"

# ---------------------------------------------------------------------------
# Step 4: pip install orb-py
# ---------------------------------------------------------------------------

info "installing orb-py..."
"${VENV_PIP}" install --quiet --upgrade pip
"${VENV_PIP}" install --quiet 'orb-py>=1.5.2,<2.0.0'

ORB_BIN="${VENV_PATH}/bin/orb"
[[ -x "${ORB_BIN}" ]] || die "orb binary not found at ${ORB_BIN} after install"

# ---------------------------------------------------------------------------
# Step 5: Place wrapper script in SCRIPTS_DIR
# ---------------------------------------------------------------------------

WRAPPER="${SCRIPTS_DIR}/orb"
info "writing wrapper script to ${WRAPPER}..."
cat > "${WRAPPER}" << EOF
#!/usr/bin/env bash
# ORB wrapper — activates the venv and delegates to the real orb binary.
# Generated by install.sh
exec "${ORB_BIN}" "\$@"
EOF
chmod +x "${WRAPPER}"

# ---------------------------------------------------------------------------
# Step 6: orb init
# ---------------------------------------------------------------------------

# Check if already initialised
if [[ -f "${CONFIG_DIR}/config.json" ]]; then
    info "ORB already initialised (${CONFIG_DIR}/config.json exists) — skipping orb init"
else
    info "running orb init..."
    INIT_ARGS=(
        "--config-dir" "${CONFIG_DIR}"
        "--work-dir"   "${WORK_DIR}"
        "--log-dir"    "${LOG_DIR}"
        "--provider"   "${PROVIDER}"
    )
    if [[ "${SCHEDULER}" != "default" ]]; then
        INIT_ARGS+=("--scheduler" "${SCHEDULER}")
    fi
    if [[ "${NON_INTERACTIVE}" == "1" ]]; then
        INIT_ARGS+=("--non-interactive")
    fi

    "${ORB_BIN}" init "${INIT_ARGS[@]}" || {
        warn "orb init exited non-zero. Configuration may be incomplete."
        warn "Re-run 'orb init' manually to complete setup."
    }
fi

# ---------------------------------------------------------------------------
# Step 7: Verify
# ---------------------------------------------------------------------------

info "verifying installation..."
VERSION=$("${WRAPPER}" --version 2>&1) || die "orb --version failed: ${VERSION}"
info "installed: ${VERSION}"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "ORB installation complete."
echo "  binary:     ${WRAPPER}"
echo "  venv:       ${VENV_PATH}"
echo "  config:     ${CONFIG_DIR}"
echo "  work dir:   ${WORK_DIR}"
echo "  log dir:    ${LOG_DIR}"
echo "  scheduler:  ${SCHEDULER}"
echo "  provider:   ${PROVIDER}"
echo ""

if [[ ":${PATH}:" != *":${SCRIPTS_DIR}:"* ]]; then
    echo "NOTE: ${SCRIPTS_DIR} is not in your PATH."
    echo "      Add it: export PATH=\"${SCRIPTS_DIR}:\$PATH\""
    echo ""
fi
