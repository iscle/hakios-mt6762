#!/usr/bin/env bash
# Export only a committed, reviewed board delta; retain upstream files unchanged.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$HERE/../.." && pwd)
TARGET=${1:-${XNU_SRC:-$ROOT/xnu-src/xnu-8796.121.2}}
python3 - "$HERE" "$TARGET" <<'PY'
import hashlib, json, os, subprocess, sys
from pathlib import Path
out=Path(sys.argv[1]); kernel=Path(sys.argv[2])
def git(*args):
    return subprocess.check_output(['git','-C',str(kernel),*args])
base='a3f439bb4e66cb753e4f92dc5177b4e7f7780fcd'
upstream_tree='61151a1354e38aa9659db555ddba9200a3d8127b'
if git('status','--porcelain','--untracked-files=no').strip():
    raise SystemExit('Commit kernel changes before exporting the MT6762 delta')
if git('rev-parse',base+'^{tree}').decode().strip()!=upstream_tree:
    raise SystemExit('Unexpected HakiOS base tree')
patch=git('diff','--binary','--full-index','--no-ext-diff','--no-textconv',base,'HEAD','--')
manifest=dict(format=1, upstream_repository='https://github.com/oosexgang/hackios-xnu-kernel.git',
    upstream_commit='88513176b1e96ecf0b764cd62c6f4e6ac71345e3',
    apple_tag='xnu-8796.121.2', apple_commit='c54f35ca767986246321eb901baf8f5ff7923f6a',
    upstream_import=base, upstream_tree=upstream_tree,
    kernel_commit=git('rev-parse','HEAD').decode().strip(),
    result_tree=git('rev-parse','HEAD^{tree}').decode().strip(),
    patch_sha256=hashlib.sha256(patch).hexdigest(),
    status='MT6762 source delta; see README.md for build and hardware validation limits')
for name,data in [('xnu.patch',patch),('kernel-source.json',(json.dumps(manifest,indent=2)+'\n').encode())]:
    tmp=out/('.'+name+'.tmp'); tmp.write_bytes(data); os.replace(tmp,out/name)
print(json.dumps(manifest,indent=2))
PY
