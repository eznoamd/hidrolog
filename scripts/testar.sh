#!/usr/bin/env bash
# Roda todos os testes do Hidrolog: backend (inclui o kit de conformidade nos
# plugins de teste de backend/tests) e frontend. Precisa dos venvs de backend/ e
# frontend/ (ver README); nenhum plugin de sensor real é necessário.
#
#   scripts/testar.sh
set -u
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
export QT_QPA_PLATFORM=offscreen
falhas=0

rodar() {
    local nome="$1"; shift
    printf '%-24s ' "$nome"
    if saida=$("$@" 2>&1); then
        echo "$saida" | tail -n 1
    else
        echo "FALHOU"
        echo "$saida" | tail -n 20
        falhas=$((falhas + 1))
    fi
}

cd "$RAIZ/backend"  && rodar "backend"            venv/bin/python -m pytest -q -p no:cacheprovider
cd "$RAIZ/frontend" && rodar "frontend"           venv/bin/python -m pytest -q -p no:cacheprovider

[ "$falhas" -eq 0 ] && echo "tudo certo" || { echo "$falhas suíte(s) falharam"; exit 1; }
