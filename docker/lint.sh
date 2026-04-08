#!/usr/bin/env bash
# Validation statique des Dockerfiles R2BEWI
#
# Deux étapes :
#   1. Présence     — vérifie que chaque Dockerfile attendu existe bien.
#   2. hadolint     — analyse chaque Dockerfile selon les bonnes pratiques
#                     Docker et les règles shellcheck intégrées.
#
# La configuration des règles ignorées se trouve dans :
#   docker/.hadolint.yaml
#
# Usage :
#   bash docker/lint.sh
#
# Prérequis :
#   hadolint (disponible dans le container containers-build)

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/docker/ros"
HADOLINT_CONFIG="${ROOT_DIR}/docker/.hadolint.yaml"

# Services attendus — doit rester cohérent avec les répertoires dans docker/ros/
SERVICES=(core motion perception)

PASS=0
FAIL=0

_pass() { echo "  [PASS] $1"; ((PASS++)); }
_fail() { echo "  [FAIL] $1 — voir détail ci-dessus"; ((FAIL++)); }

# ── 1. Présence des Dockerfiles ───────────────────────────────────────────────
# Vérifie que chaque service déclaré dispose bien d'un Dockerfile.
# Un Dockerfile manquant ferait échouer silencieusement le build sans
# ce contrôle explicite.

echo "[ présence Dockerfiles ]"
echo ""

for svc in "${SERVICES[@]}"; do
    path="${SRC_DIR}/${svc}/Dockerfile"
    if [[ -f "$path" ]]; then
        _pass "${svc}/Dockerfile existe"
    else
        echo "  fichier attendu : ${path}"
        _fail "${svc}/Dockerfile manquant"
    fi
done

# ── 2. hadolint ───────────────────────────────────────────────────────────────
# Analyse chaque Dockerfile individuellement.
# Les violations sont affichées au format parseable :
#   <fichier>:<ligne> <code> <message>
#
# Les règles ignorées pour ce projet sont déclarées dans .hadolint.yaml.
# Toute autre violation est considérée comme un échec.

echo ""
echo "[ hadolint ]"
echo ""

if ! command -v hadolint > /dev/null 2>&1; then
    echo "  [SKIP] hadolint non disponible"
else
    for svc in "${SERVICES[@]}"; do
        path="${SRC_DIR}/${svc}/Dockerfile"
        [[ -f "$path" ]] || continue

        output="$(
            hadolint \
                --config "${HADOLINT_CONFIG}" \
                --format tty \
                "${path}" 2>&1
        )"
        if [[ $? -eq 0 ]]; then
            _pass "hadolint: ${svc}"
        else
            echo "${output}"
            echo ""
            _fail "hadolint: ${svc}"
        fi
    done
fi

# ── Résumé ────────────────────────────────────────────────────────────────────

echo ""
echo "─────────────────────────────────"
echo "Résultats : ${PASS} ok, ${FAIL} échec(s)"
echo "─────────────────────────────────"
[[ $FAIL -eq 0 ]]
