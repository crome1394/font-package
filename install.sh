#!/usr/bin/env bash
# Distro-independent US English font install. See README.md.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
exec python3 "$PWD/install.py" "$@"
