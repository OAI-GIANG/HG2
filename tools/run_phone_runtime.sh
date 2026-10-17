#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
umask 077

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
CONFIG_DIR="$HOME/.config/hg"
RUNTIME_ENV="$CONFIG_DIR/hg2-single-system.env"
SECRET_ENV="$CONFIG_DIR/secret.env"

[ -r "$RUNTIME_ENV" ] || { echo "HG2 runtime config missing" >&2; exit 20; }
if [ -r "$SECRET_ENV" ]; then
  set -a
  . "$SECRET_ENV"
  set +a
fi
set -a
. "$RUNTIME_ENV"
set +a

export HG_REQUIRE_BUILD_ID=1
cd "$ROOT"
exec python -m hg.server
