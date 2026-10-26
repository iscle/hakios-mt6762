#!/usr/bin/env bash
# Synthetic MT6762 lab only: no USB, physical device access or image flashing.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$HERE/run_qemu.py" "$@"
