#!/bin/bash
# Corrida local diaria: corre las fuentes que solo responden desde Uruguay y sube su resultado
# a la rama `datos`. Lo ejecuta launchd (ver scripts/local/instalar.sh y docs/diseno.md).
#
# Corre siempre el código de `main` desde un clon propio, separado de tu copia de trabajo,
# y sube solo los archivos de sus fuentes (datos/fuentes/<fuente>.json).
#
# Variables (con sus valores por defecto):
#   CARTELERA_DIR      ~/.cartelera-cultural   clon dedicado del repo
#   CARTELERA_LLAVE    ~/.ssh/cartelera_deploy  deploy key con permiso de escritura, solo para este repo
#   CARTELERA_SIN_PUSH                          si vale 1, hace todo menos el push (para probar)

set -euo pipefail

# Todo va en una función: el paso 1 puede cambiar este mismo archivo, y así bash ya lo leyó entero.
correr() {
  DIR="${CARTELERA_DIR:-$HOME/.cartelera-cultural}"
  LLAVE="${CARTELERA_LLAVE:-$HOME/.ssh/cartelera_deploy}"
  export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin"
  export GIT_SSH_COMMAND="ssh -i $LLAVE -o IdentitiesOnly=yes"

  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="
  cd "$DIR"

  # 0. Si el equipo recién se despierta, el wifi tarda unos segundos: se espera la conexión (hasta 2 minutos).
  local intentos=0
  until git ls-remote -q origin main > /dev/null 2>&1; do
    intentos=$((intentos + 1))
    if [ "$intentos" -ge 24 ]; then
      echo "Sin conexión con GitHub después de 2 minutos; se intenta de nuevo en la próxima corrida."
      return 1
    fi
    sleep 5
  done
  if [ "$intentos" -gt 0 ]; then echo "Conexión lista después de $((intentos * 5)) segundos."; fi

  # 1. El código: siempre la última versión de main, nunca otra rama.
  git fetch -q origin main
  git checkout -q --detach origin/main

  # 2. Los datos: la última versión de la rama datos, para que cada fuente compare con su último resultado bueno.
  git -C datos fetch -q origin datos
  git -C datos checkout -q -B datos origin/datos

  # 3. Las fuentes locales. Si una falla, se conserva su último resultado bueno y se sigue.
  uv sync -q --locked --no-dev
  uv run python -m cartelera scrapear --donde local || echo "Alguna fuente falló; se conserva su último resultado bueno."

  # 4. Subir solo los archivos de estas fuentes.
  ARCHIVOS=$(uv run python -c 'import tomllib; c = tomllib.load(open("config/fuentes.toml", "rb")); print(" ".join(f"fuentes/{f}.json" for f, v in c.items() if v.get("corre_en") == "local"))')
  cd datos
  for archivo in $ARCHIVOS; do
    if [ -f "$archivo" ]; then git add -- "$archivo"; fi
  done
  if git diff --cached --quiet; then
    echo "Sin cambios en los datos."
    return
  fi
  git -c user.name="cartelera-local" -c user.email="cartelera-local@users.noreply.github.com" \
    commit -q -m "Datos locales $(date -u +%Y-%m-%dT%H:%MZ)"
  if [ "${CARTELERA_SIN_PUSH:-0}" = "1" ]; then
    echo "Prueba: commit hecho en $DIR/datos, sin push."
    return
  fi
  git pull -q --rebase origin datos
  git push -q origin HEAD:datos
  echo "Datos subidos."
}

correr
exit
