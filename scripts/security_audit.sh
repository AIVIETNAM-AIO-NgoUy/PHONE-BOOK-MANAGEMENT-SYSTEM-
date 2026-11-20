#!/usr/bin/env bash
# ==============================================================================
# T105: Security Audit & Django Production Deployment Check Script
# ==============================================================================
# Runs:
#   1. Django deployment check: manage.py check --deploy --fail-level WARNING
#   2. Bandit SAST scan across apps/ and config/ (excluding migrations & tests)
#   3. Safety dependency vulnerability scan (if installed)
#
# Usage:
#   ./scripts/security_audit.sh           # Run all available security checks
#   ./scripts/security_audit.sh --strict  # Fail if bandit or safety is missing
# ==============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

STRICT_MODE=false
for arg in "$@"; do
    case "${arg}" in
        --strict)
            STRICT_MODE=true
            ;;
        -h|--help)
            cat <<'EOF'
Usage: security_audit.sh [--strict]

Options:
  --strict   Exit non-zero if optional SAST/SCA tools (bandit, safety) are missing.
  -h, --help Show this help message and exit.
EOF
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: ${arg}" >&2
            exit 1
            ;;
    esac
done

if [[ -x "${PROJECT_ROOT}/venv/bin/python" ]]; then
    PYTHON_BIN="${PROJECT_ROOT}/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "ERROR: Python interpreter not found." >&2
    exit 1
fi

# Provide safe ephemeral fallback values if .env does not exist or lacks them,
# so `manage.py check --deploy` can execute reliably in clean environments.
if [[ -z "${SECRET_KEY:-}" ]]; then
    if [[ ! -f "${PROJECT_ROOT}/.env" ]] || ! grep -q '^SECRET_KEY=' "${PROJECT_ROOT}/.env"; then
        export SECRET_KEY
        SECRET_KEY="$("${PYTHON_BIN}" -c "import secrets; print(secrets.token_urlsafe(48))")"
    fi
fi

if [[ -z "${ALLOWED_HOSTS:-}" ]]; then
    if [[ ! -f "${PROJECT_ROOT}/.env" ]] || ! grep -q '^ALLOWED_HOSTS=' "${PROJECT_ROOT}/.env"; then
        export ALLOWED_HOSTS="localhost,127.0.0.1"
    fi
fi

DEPLOY_STATUS="FAIL"
BANDIT_STATUS="NOT_INSTALLED"
SAFETY_STATUS="NOT_INSTALLED"
HAS_FAILURE=false
HAS_MISSING=false

echo "=== [1/3] Django Production Deployment Check ==="
if DJANGO_SETTINGS_MODULE=config.settings.production \
    PYTHONPATH="${PROJECT_ROOT}/backend" \
    "${PYTHON_BIN}" "${PROJECT_ROOT}/backend/manage.py" check --deploy --fail-level WARNING; then
    DEPLOY_STATUS="PASS"
else
    DEPLOY_STATUS="FAIL"
    HAS_FAILURE=true
fi

echo ""
echo "=== [2/3] Bandit SAST Scan (backend/apps/ & backend/config/) ==="
BANDIT_BIN=""
if [[ -x "${PROJECT_ROOT}/venv/bin/bandit" ]]; then
    BANDIT_BIN="${PROJECT_ROOT}/venv/bin/bandit"
elif command -v bandit >/dev/null 2>&1; then
    BANDIT_BIN="$(command -v bandit)"
fi

if [[ -n "${BANDIT_BIN}" ]]; then
    if "${BANDIT_BIN}" -r "${PROJECT_ROOT}/backend/apps" "${PROJECT_ROOT}/backend/config" -x '*/migrations/*,*/tests/*' -ll; then
        BANDIT_STATUS="PASS"
    else
        BANDIT_STATUS="FAIL"
        HAS_FAILURE=true
    fi
else
    echo "WARNING: 'bandit' is not installed in ./venv/bin or PATH."
    echo "Action : Install with './venv/bin/pip install bandit' to enable SAST scanning."
    BANDIT_STATUS="MISSING"
    HAS_MISSING=true
fi

echo ""
echo "=== [3/3] Safety Dependency Vulnerability Scan ==="
SAFETY_BIN=""
if [[ -x "${PROJECT_ROOT}/venv/bin/safety" ]]; then
    SAFETY_BIN="${PROJECT_ROOT}/venv/bin/safety"
elif command -v safety >/dev/null 2>&1; then
    SAFETY_BIN="$(command -v safety)"
fi

if [[ -n "${SAFETY_BIN}" ]]; then
    if "${SAFETY_BIN}" check -r "${PROJECT_ROOT}/backend/requirements.txt"; then
        SAFETY_STATUS="PASS"
    else
        SAFETY_STATUS="FAIL"
        HAS_FAILURE=true
    fi
else
    echo "WARNING: 'safety' is not installed in ./venv/bin or PATH."
    echo "Action : Install with './venv/bin/pip install safety' to enable dependency CVE scanning."
    SAFETY_STATUS="MISSING"
    HAS_MISSING=true
fi

echo ""
echo "=== Security Audit Summary ==="
echo "Django check --deploy : ${DEPLOY_STATUS}"
echo "Bandit SAST           : ${BANDIT_STATUS}"
echo "Safety CVE scan       : ${SAFETY_STATUS}"

if [[ "${HAS_FAILURE}" == "true" ]]; then
    echo "Result: FAILED (one or more security checks reported issues)." >&2
    exit 1
fi

if [[ "${STRICT_MODE}" == "true" && "${HAS_MISSING}" == "true" ]]; then
    echo "Result: FAILED (--strict mode requires bandit and safety to be installed)." >&2
    exit 2
fi

if [[ "${HAS_MISSING}" == "true" ]]; then
    echo "Result: PARTIAL PASS (Django check --deploy passed; missing optional tools reported above)."
else
    echo "Result: PASSED"
fi
