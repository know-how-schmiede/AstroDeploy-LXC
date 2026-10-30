#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ $EUID -ne 0 ]]; then
  echo 'Bitte im Debian-Container als root starten: sudo bash bin/setup.sh' >&2
  exit 1
fi
if ! command -v python3 >/dev/null; then
  if [[ ! -r /etc/debian_version ]] || [[ $(cut -d. -f1 /etc/debian_version) != 13 ]]; then
    echo 'Dieses Setup benötigt Debian 13.' >&2
    exit 1
  fi
  echo 'Python 3 wird für das interaktive Setup benötigt und ist noch nicht installiert.'
  read -r -p 'Python 3 jetzt über Debian installieren? (ja/nein) [nein]: ' answer
  if [[ $answer != ja ]]; then
    exit 1
  fi
  apt-get update
  apt-get install -y python3
fi
exec python3 lib/astrodeploy.py setup
