#!/usr/bin/env bash
# New-monorepo MTK entry. --check validates selection/IIG without a build.
set -euo pipefail
MTK_HAKIOS_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
export MTK_HAKIOS_ROOT
exec "$MTK_HAKIOS_ROOT/xnu-src/xnu-8796.121.2/tools/mt6762/build.sh" "$@"
