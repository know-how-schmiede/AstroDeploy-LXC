#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ $EUID -ne 0 ]]; then
  echo 'Bitte im Debian-Container als root starten: sudo bash bin/setup.sh' >&2
  exit 1
fi
if ! command -v python3 >/dev/null; then
  echo 'Python 3 fehlt. Bitte zuerst: apt-get update && apt-get install python3' >&2
  exit 1
fi
exec python3 lib/astrodeploy.py setup
