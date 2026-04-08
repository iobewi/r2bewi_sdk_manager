#!/usr/bin/env bash
# r2bewi — installateur R2BEWI autoporteur
# Ce fichier est un wrapper shell contenant le moteur Python embarqué en payload base64.
# Ne pas modifier manuellement — généré par : make build-py
set -euo pipefail

SELF="${BASH_SOURCE[0]:-$0}"

# ── Nettoyage à la sortie ─────────────────────────────────────────────────────
_TMP_DIR=""
_cleanup() {
    [ -n "${_TMP_DIR}" ] && rm -rf "${_TMP_DIR}"
}
trap _cleanup EXIT

# ── Vérifications préliminaires ───────────────────────────────────────────────
_require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "r2bewi: doit être exécuté avec sudo ou en root" >&2
        exit 1
    fi
}

_require_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        echo "r2bewi: python3 est requis mais absent" >&2
        exit 1
    fi
}

# ── Bootstrap dépendances Python ──────────────────────────────────────────────
_ensure_python_deps() {
    local missing=()
    python3 -c "import yaml"   2>/dev/null || missing+=("python3-yaml")
    python3 -c "import jinja2" 2>/dev/null || missing+=("python3-jinja2")

    if [ "${#missing[@]}" -gt 0 ]; then
        echo "[r2bewi] Dépendances Python manquantes : ${missing[*]}" >&2
        echo "[r2bewi] Installation via apt..." >&2
        apt-get update -q
        apt-get install -y "${missing[@]}"
    fi
}

# ── Extraction du payload ─────────────────────────────────────────────────────
_extract_pyz() {
    _TMP_DIR="$(mktemp -d)"
    local pyz="${_TMP_DIR}/r2bewi.pyz"
    awk '/^__R2BEWI_PYZ_BELOW__$/{found=1; next} found{print}' "${SELF}" \
        | base64 -d > "${pyz}"
    chmod 700 "${pyz}"
    echo "${pyz}"
}

# ── Helpers ───────────────────────────────────────────────────────────────────
_is_help_request() {
    # Retourne 0 (vrai) si le premier argument est --help ou -h
    case "${1:-}" in
        --help|-h) return 0 ;;
        *) return 1 ;;
    esac
}

# ── Point d'entrée ────────────────────────────────────────────────────────────
_main() {
    _require_python
    # --help/-h : pas de root ni de dépendances apt (CI, introspection, onboarding)
    if _is_help_request "$@"; then
        local pyz
        pyz="$(_extract_pyz)"
        exec env R2BEWI_SELF="$(realpath "${SELF}")" python3 "${pyz}" "$@"
    fi
    _require_root
    _ensure_python_deps
    local pyz
    pyz="$(_extract_pyz)"
    exec env R2BEWI_SELF="$(realpath "${SELF}")" python3 "${pyz}" "$@"
}

_main "$@"
exit 0

# ── Payload embarqué (base64) ─────────────────────────────────────────────────
__R2BEWI_PYZ_BELOW__
