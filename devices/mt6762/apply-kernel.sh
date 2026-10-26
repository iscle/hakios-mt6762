#!/usr/bin/env bash
# Materialize the pinned HakiOS tree, then apply the MT6762 delta.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$HERE/../.." && pwd)
TARGET=${1:-${XNU_SRC:-$ROOT/xnu-src/xnu-8796.121.2}}
python3 - "$HERE" <<'PY'
import hashlib, json, sys
from pathlib import Path
p=Path(sys.argv[1]); m=json.loads((p/'kernel-source.json').read_text())
if hashlib.sha256((p/'xnu.patch').read_bytes()).hexdigest()!=m['patch_sha256']:
    raise SystemExit('MT6762 kernel patch does not match kernel-source.json')
PY
"$ROOT/xnu/apply.sh" "$TARGET"
git -C "$TARGET" add -A
python3 - "$HERE/kernel-source.json" "$TARGET" <<'PY'
import json, subprocess, sys
m=json.load(open(sys.argv[1])); tree=subprocess.check_output(['git','-C',sys.argv[2],'write-tree'],text=True).strip()
if tree!=m['upstream_tree']:
    raise SystemExit('HakiOS input tree differs from the pinned base; inspect target before retrying')
PY
git -C "$TARGET" apply --index --whitespace=nowarn "$HERE/xnu.patch"
python3 - "$HERE/kernel-source.json" "$TARGET" <<'PY'
import json, subprocess, sys
m=json.load(open(sys.argv[1])); tree=subprocess.check_output(['git','-C',sys.argv[2],'write-tree'],text=True).strip()
if tree!=m['result_tree']:
    raise SystemExit('MT6762 result tree differs from the exported kernel')
print('MT6762 source tree verified: '+tree)
PY
git -C "$TARGET" branch -m mt6762-hakios
printf 'Ready: %s\n' "$TARGET"
