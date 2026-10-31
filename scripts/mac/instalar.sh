#!/bin/bash
# Instala el job diario de la Mac. Se corre una sola vez, a mano, desde la copia de trabajo del repo:
#
#   bash scripts/mac/instalar.sh
#
# Antes hace falta:
#   1. Que exista la rama `datos` en GitHub (la crea la primera corrida del workflow "Cartelera").
#   2. Una deploy key con permiso de escritura para este repo. Si no existe, este script la genera
#      y muestra la parte pública para pegarla en GitHub: Settings → Deploy keys → Add deploy key,
#      con "Allow write access" marcado.
#
# Para desinstalar:
#   launchctl bootout gui/$(id -u)/io.github.danidlsa.cartelera
#   rm ~/Library/LaunchAgents/io.github.danidlsa.cartelera.plist
#   rm -rf ~/.cartelera-cultural

set -euo pipefail

REPO="git@github.com:danidlsa/cartelera-cultural.git"
DIR="${CARTELERA_DIR:-$HOME/.cartelera-cultural}"
LLAVE="${CARTELERA_LLAVE:-$HOME/.ssh/cartelera_deploy}"
LOG="$HOME/Library/Logs/cartelera-cultural.log"
ETIQUETA="io.github.danidlsa.cartelera"
PLIST="$HOME/Library/LaunchAgents/$ETIQUETA.plist"
AQUI="$(cd "$(dirname "$0")" && pwd)"
export GIT_SSH_COMMAND="ssh -i $LLAVE -o IdentitiesOnly=yes"

# 1. La deploy key: solo sirve para este repo.
if [ ! -f "$LLAVE" ]; then
  ssh-keygen -q -t ed25519 -N "" -C "cartelera-mac" -f "$LLAVE"
  echo
  echo "Se creó la deploy key. Pegá esta línea en GitHub (Settings → Deploy keys → Add deploy key,"
  echo "con \"Allow write access\") y volvé a correr este script:"
  echo
  cat "$LLAVE.pub"
  exit 0
fi

# 2. El clon dedicado: main para el código y, adentro, la rama datos en datos/.
if [ ! -d "$DIR/.git" ]; then
  git clone -q "$REPO" "$DIR"
fi
if [ ! -d "$DIR/datos/.git" ]; then
  git clone -q --branch datos --single-branch "$REPO" "$DIR/datos"
fi

# 3. El job de launchd, con la ruta del script del clon dedicado (siempre el código de main).
mkdir -p "$HOME/Library/LaunchAgents" "$(dirname "$LOG")"
sed -e "s|__CORRER__|$DIR/scripts/mac/correr.sh|" -e "s|__LOG__|$LOG|" "$AQUI/cartelera.plist" > "$PLIST"
launchctl bootout "gui/$(id -u)/$ETIQUETA" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Listo: el job corre los días de semana a las 11. El log queda en $LOG."
echo "Para probarlo ahora: launchctl kickstart gui/$(id -u)/$ETIQUETA"
