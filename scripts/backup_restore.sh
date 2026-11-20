#!/usr/bin/env bash
# ==============================================================================
# T104: Automated PostgreSQL Backup & Restore Integrity Verification Script
# ==============================================================================
# Usage:
#   ./scripts/backup_restore.sh                     # Create compressed dump & verify restore
#   ./scripts/backup_restore.sh --dump [FILE]       # Export database to SQL or dump file
#   ./scripts/backup_restore.sh --restore [FILE]    # Restore SQL or dump file to database
#   ./scripts/backup_restore.sh --verify-only [FILE]# Verify existing backup in scratch DB
#
# Supports native PostgreSQL client tools (pg_dump, pg_restore, psql) and
# automatically falls back to `docker exec` against the running
# `phonebook_postgres` container when host CLI tools are unavailable.
# ==============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="verify"
FORMAT=""
TARGET_FILE=""

usage() {
    cat <<'EOF'
Usage: backup_restore.sh [OPTIONS]

Options:
  --dump [FILE]              Export database to a backup file (default: backups/phonebook_db.sql or backups/phonebook_db_<timestamp>.dump).
  --restore [FILE]           Restore backup file into active database (default: backups/phonebook_db.sql).
  --verify-only [FILE]       Skip backup creation and verify an existing backup file in a scratch DB.
  --format [sql|dump]        Backup format: 'sql' (plain-text SQL) or 'dump' (PostgreSQL custom archive).
  -f, --file FILE            Specify output/input file path.
  -h, --help                 Show this help message and exit.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dump)
            ACTION="dump"
            if [[ $# -gt 1 && "$2" != -* ]]; then
                TARGET_FILE="$2"
                shift
            fi
            shift
            ;;
        --restore)
            ACTION="restore"
            if [[ $# -gt 1 && "$2" != -* ]]; then
                TARGET_FILE="$2"
                shift
            fi
            shift
            ;;
        --verify-only)
            ACTION="verify-only"
            if [[ $# -gt 1 && "$2" != -* ]]; then
                TARGET_FILE="$2"
                shift
            fi
            shift
            ;;
        --format)
            if [[ $# -gt 1 && "$2" != -* ]]; then
                FORMAT="$2"
                shift
            else
                echo "ERROR: --format requires an argument ('sql' or 'dump')." >&2
                exit 1
            fi
            shift
            ;;
        -f|--file)
            if [[ $# -gt 1 && "$2" != -* ]]; then
                TARGET_FILE="$2"
                shift
            else
                echo "ERROR: -f/--file requires a file path argument." >&2
                exit 1
            fi
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

# Load .env variables without overriding values already exported in the environment.
load_env_file() {
    local env_file="${PROJECT_ROOT}/.env"
    [[ -f "${env_file}" ]] || return 0

    while IFS= read -r line || [[ -n "${line}" ]]; do
        line="${line#"${line%%[![:space:]]*}"}"
        [[ -z "${line}" || "${line}" == \#* ]] && continue
        if [[ "${line}" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local val="${BASH_REMATCH[2]}"
            if [[ "${val}" =~ ^\"(.*)\"$ || "${val}" =~ ^\'(.*)\'$ ]]; then
                val="${BASH_REMATCH[1]}"
            fi
            if [[ -z "${!key+x}" ]]; then
                export "${key}=${val}"
            fi
        fi
    done < "${env_file}"
}

load_env_file

DB_NAME="${DB_NAME:-phonebook_db}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
PG_CONTAINER="${PG_CONTAINER:-phonebook_postgres}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"

# Validate DB_NAME and DB_USER contain safe identifier characters.
if [[ ! "${DB_NAME}" =~ ^[A-Za-z0-9_]+$ || ! "${DB_USER}" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "ERROR: DB_NAME and DB_USER must contain only alphanumeric characters and underscores." >&2
    exit 1
fi

# Detect execution mode: native host tools or Docker container fallback.
USE_DOCKER=false
if command -v pg_dump >/dev/null 2>&1 \
    && command -v pg_restore >/dev/null 2>&1 \
    && command -v psql >/dev/null 2>&1; then
    USE_DOCKER=false
elif command -v docker >/dev/null 2>&1; then
    if [[ "$(docker inspect -f '{{.State.Running}}' "${PG_CONTAINER}" 2>/dev/null || true)" == "true" ]]; then
        USE_DOCKER=true
    else
        echo "ERROR: Native PostgreSQL tools not found and Docker container '${PG_CONTAINER}' is not running." >&2
        exit 1
    fi
else
    echo "ERROR: Neither PostgreSQL client tools (pg_dump, pg_restore, psql) nor docker CLI were found." >&2
    exit 1
fi

run_psql() {
    local target_db="$1"
    local sql_or_file="$2"
    if [[ -f "${sql_or_file}" ]]; then
        if [[ "${USE_DOCKER}" == "true" ]]; then
            docker exec -i -e PGPASSWORD="${DB_PASSWORD}" "${PG_CONTAINER}" \
                psql -U "${DB_USER}" -d "${target_db}" -v ON_ERROR_STOP=1 < "${sql_or_file}"
        else
            PGPASSWORD="${DB_PASSWORD}" \
                psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${target_db}" \
                -v ON_ERROR_STOP=1 -f "${sql_or_file}"
        fi
    else
        if [[ "${USE_DOCKER}" == "true" ]]; then
            docker exec -i -e PGPASSWORD="${DB_PASSWORD}" "${PG_CONTAINER}" \
                psql -U "${DB_USER}" -d "${target_db}" -v ON_ERROR_STOP=1 -tAc "${sql_or_file}"
        else
            PGPASSWORD="${DB_PASSWORD}" \
                psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${target_db}" \
                -v ON_ERROR_STOP=1 -tAc "${sql_or_file}"
        fi
    fi
}

run_pg_dump() {
    local out_file="$1"
    local fmt="${2:-dump}"
    if [[ "${fmt}" == "sql" || "${out_file}" == *.sql ]]; then
        if [[ "${USE_DOCKER}" == "true" ]]; then
            docker exec -e PGPASSWORD="${DB_PASSWORD}" "${PG_CONTAINER}" \
                pg_dump -U "${DB_USER}" -d "${DB_NAME}" --clean --if-exists --no-owner --no-privileges > "${out_file}"
        else
            PGPASSWORD="${DB_PASSWORD}" \
                pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
                --clean --if-exists --no-owner --no-privileges -f "${out_file}"
        fi
    else
        if [[ "${USE_DOCKER}" == "true" ]]; then
            docker exec -e PGPASSWORD="${DB_PASSWORD}" "${PG_CONTAINER}" \
                pg_dump -U "${DB_USER}" -Fc -d "${DB_NAME}" > "${out_file}"
        else
            PGPASSWORD="${DB_PASSWORD}" \
                pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -Fc -d "${DB_NAME}" -f "${out_file}"
        fi
    fi
}

run_pg_restore() {
    local target_db="$1"
    local in_file="$2"
    if [[ "${USE_DOCKER}" == "true" ]]; then
        docker exec -i -e PGPASSWORD="${DB_PASSWORD}" "${PG_CONTAINER}" \
            pg_restore -U "${DB_USER}" -d "${target_db}" --clean --if-exists --no-owner --no-acl --exit-on-error < "${in_file}"
    else
        PGPASSWORD="${DB_PASSWORD}" \
            pg_restore -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${target_db}" \
            --clean --if-exists --no-owner --no-acl --exit-on-error "${in_file}"
    fi
}

run_restore() {
    local target_db="$1"
    local in_file="$2"
    if [[ "${in_file}" == *.sql ]]; then
        run_psql "${target_db}" "${in_file}"
    else
        run_pg_restore "${target_db}" "${in_file}"
    fi
}

mkdir -p "${BACKUP_DIR}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# Determine format and file target based on action
if [[ -n "${TARGET_FILE}" ]]; then
    if [[ -z "${FORMAT}" ]]; then
        if [[ "${TARGET_FILE}" == *.sql ]]; then
            FORMAT="sql"
        else
            FORMAT="dump"
        fi
    fi
fi

if [[ "${ACTION}" == "dump" ]]; then
    if [[ -z "${TARGET_FILE}" ]]; then
        if [[ "${FORMAT}" == "dump" ]]; then
            TARGET_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
        else
            FORMAT="sql"
            TARGET_FILE="${BACKUP_DIR}/phonebook_db.sql"
        fi
    fi
elif [[ "${ACTION}" == "restore" ]]; then
    if [[ -z "${TARGET_FILE}" ]]; then
        if [[ -f "${BACKUP_DIR}/phonebook_db.sql" ]]; then
            TARGET_FILE="${BACKUP_DIR}/phonebook_db.sql"
        else
            TARGET_FILE="$(ls -1t "${BACKUP_DIR}"/*.sql "${BACKUP_DIR}"/*.dump 2>/dev/null | head -n 1 || true)"
        fi
    fi
    if [[ -z "${TARGET_FILE}" || ! -f "${TARGET_FILE}" ]]; then
        echo "ERROR: Backup file not found to restore: ${TARGET_FILE:-<none>}" >&2
        exit 1
    fi
    if [[ -z "${FORMAT}" ]]; then
        if [[ "${TARGET_FILE}" == *.sql ]]; then
            FORMAT="sql"
        else
            FORMAT="dump"
        fi
    fi
elif [[ "${ACTION}" == "verify-only" ]]; then
    if [[ -z "${TARGET_FILE}" ]]; then
        TARGET_FILE="$(ls -1t "${BACKUP_DIR}"/*.dump "${BACKUP_DIR}"/*.sql 2>/dev/null | head -n 1 || true)"
    fi
    if [[ -z "${TARGET_FILE}" || ! -f "${TARGET_FILE}" ]]; then
        echo "ERROR: No dump file found to verify in '${BACKUP_DIR}'." >&2
        exit 1
    fi
    if [[ -z "${FORMAT}" ]]; then
        if [[ "${TARGET_FILE}" == *.sql ]]; then
            FORMAT="sql"
        else
            FORMAT="dump"
        fi
    fi
else # ACTION == "verify"
    if [[ -z "${TARGET_FILE}" ]]; then
        if [[ "${FORMAT}" == "sql" ]]; then
            TARGET_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql"
        else
            FORMAT="dump"
            TARGET_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
        fi
    fi
fi

echo "=== PostgreSQL Backup & Restore Tool ==="
if [[ "${USE_DOCKER}" == "true" ]]; then
    echo "Mode       : Docker fallback (${PG_CONTAINER})"
else
    echo "Mode       : Native PostgreSQL client (${DB_HOST}:${DB_PORT})"
fi
echo "Database   : ${DB_NAME} (user: ${DB_USER})"
echo "Action     : ${ACTION}"
echo "Format     : ${FORMAT}"
echo "Target     : ${TARGET_FILE}"

if [[ "${ACTION}" == "dump" ]]; then
    echo "Exporting database '${DB_NAME}' to '${TARGET_FILE}'..."
    run_pg_dump "${TARGET_FILE}" "${FORMAT}"
    if [[ ! -s "${TARGET_FILE}" ]]; then
        echo "ERROR: Dump file '${TARGET_FILE}' is missing or empty." >&2
        exit 1
    fi
    DUMP_SIZE="$(wc -c < "${TARGET_FILE}" | tr -d '[:space:]')"
    echo "Database successfully exported to '${TARGET_FILE}' (${DUMP_SIZE} bytes)."
    exit 0
fi

if [[ "${ACTION}" == "restore" ]]; then
    if [[ ! -s "${TARGET_FILE}" ]]; then
        echo "ERROR: Backup file '${TARGET_FILE}' is missing or empty." >&2
        exit 1
    fi
    echo "Restoring '${TARGET_FILE}' into database '${DB_NAME}'..."
    run_restore "${DB_NAME}" "${TARGET_FILE}"

    echo "Verifying restored schema and table integrity in '${DB_NAME}'..."
    TABLE_COUNT="$(run_psql "${DB_NAME}" \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")"
    TABLE_COUNT="$(echo "${TABLE_COUNT}" | tr -d '[:space:]')"

    if [[ -z "${TABLE_COUNT}" || "${TABLE_COUNT}" -le 0 ]]; then
        echo "ERROR: Restored database '${DB_NAME}' contains ${TABLE_COUNT:-0} tables in 'public' schema." >&2
        exit 1
    fi

    run_psql "${DB_NAME}" "ANALYZE;" >/dev/null
    TOTAL_ROWS="$(run_psql "${DB_NAME}" \
        "SELECT COALESCE(SUM(n_live_tup), 0) FROM pg_stat_user_tables WHERE schemaname = 'public';")"
    TOTAL_ROWS="$(echo "${TOTAL_ROWS}" | tr -d '[:space:]')"

    MIGRATION_COUNT="$(run_psql "${DB_NAME}" \
        "SELECT CASE WHEN to_regclass('public.django_migrations') IS NOT NULL THEN (SELECT COUNT(*) FROM public.django_migrations) ELSE 0 END;")"
    MIGRATION_COUNT="$(echo "${MIGRATION_COUNT}" | tr -d '[:space:]')"

    echo "Restored tables     : ${TABLE_COUNT}"
    echo "Applied migrations  : ${MIGRATION_COUNT}"
    echo "Estimated live rows : ${TOTAL_ROWS}"
    echo "=== Database Restore Completed Successfully ==="
    exit 0
fi

# Verification mode (ACTION == "verify" or "verify-only") using scratch DB
SCRATCH_DB="${DB_NAME}_restore_verify_${TIMESTAMP}_$$"
SCRATCH_CREATED=false

cleanup() {
    local exit_code=$?
    if [[ "${SCRATCH_CREATED}" == "true" ]]; then
        echo "[cleanup] Dropping temporary verification database '${SCRATCH_DB}'..."
        run_psql "postgres" \
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${SCRATCH_DB}' AND pid <> pg_backend_pid();" \
            >/dev/null 2>&1 || true
        run_psql "postgres" "DROP DATABASE IF EXISTS \"${SCRATCH_DB}\";" >/dev/null 2>&1 || true
        echo "[cleanup] Temporary database '${SCRATCH_DB}' dropped."
    fi
    exit "${exit_code}"
}
trap cleanup EXIT

if [[ "${ACTION}" == "verify-only" ]]; then
    DUMP_FILE="${TARGET_FILE}"
    echo "Verify only: Using existing backup '${DUMP_FILE}'"
else
    DUMP_FILE="${TARGET_FILE}"
    echo "[1/4] Creating backup at '${DUMP_FILE}'..."
    run_pg_dump "${DUMP_FILE}" "${FORMAT}"
fi

if [[ ! -s "${DUMP_FILE}" ]]; then
    echo "ERROR: Backup file '${DUMP_FILE}' is missing or empty." >&2
    exit 1
fi

DUMP_SIZE="$(wc -c < "${DUMP_FILE}" | tr -d '[:space:]')"
echo "[2/4] Backup file verified non-empty (${DUMP_SIZE} bytes)."

echo "[3/4] Creating scratch database '${SCRATCH_DB}' and restoring backup..."
run_psql "postgres" "CREATE DATABASE \"${SCRATCH_DB}\";" >/dev/null
SCRATCH_CREATED=true
run_restore "${SCRATCH_DB}" "${DUMP_FILE}"

echo "[4/4] Verifying restored schema and table integrity..."
TABLE_COUNT="$(run_psql "${SCRATCH_DB}" \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")"
TABLE_COUNT="$(echo "${TABLE_COUNT}" | tr -d '[:space:]')"

if [[ -z "${TABLE_COUNT}" || "${TABLE_COUNT}" -le 0 ]]; then
    echo "ERROR: Restored database '${SCRATCH_DB}' contains ${TABLE_COUNT:-0} tables in 'public' schema." >&2
    exit 1
fi

run_psql "${SCRATCH_DB}" "ANALYZE;" >/dev/null
TOTAL_ROWS="$(run_psql "${SCRATCH_DB}" \
    "SELECT COALESCE(SUM(n_live_tup), 0) FROM pg_stat_user_tables WHERE schemaname = 'public';")"
TOTAL_ROWS="$(echo "${TOTAL_ROWS}" | tr -d '[:space:]')"

MIGRATION_COUNT="$(run_psql "${SCRATCH_DB}" \
    "SELECT CASE WHEN to_regclass('public.django_migrations') IS NOT NULL THEN (SELECT COUNT(*) FROM public.django_migrations) ELSE 0 END;")"
MIGRATION_COUNT="$(echo "${MIGRATION_COUNT}" | tr -d '[:space:]')"

echo "Restored tables     : ${TABLE_COUNT}"
echo "Applied migrations  : ${MIGRATION_COUNT}"
echo "Estimated live rows : ${TOTAL_ROWS}"
echo "=== Backup & Restore Verification PASSED ==="
