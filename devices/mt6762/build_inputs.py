#!/usr/bin/env python3
"""MT6762 build admission/provenance; never generates RPCs or invokes make."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / 'xnu-src/xnu-8796.121.2'
REVISIONS = {
    'XNU_LIBDISPATCH_SOURCE': 'a641558f447659d90ad002ef0ee6f0212273fbfc',
    'XNU_LIBPTHREAD_SOURCE': 'a6c70ca0e544347a0377babf748f831577ec24f9',
    'MTK_AVAILABILITY_SOURCE': '5d9baee345b3bc72b26c71adc65f94f2d5e9ced2',
}
SDK_REVISION = '0222fd5413cf4b9af096f37b4621afa2688572f7'
HOST_TOOLS = ('mig', 'migcom', 'unifdef', 'tcsh', 'unzbm')
CCTOOLS = ('ld', 'nm', 'otool', 'strip', 'lipo', 'libtool', 'nmedit',
           'ctf_insert', 'codesign_allocate', 'install_name_tool')


def env_path(name):
    value = os.environ.get(name)
    if not value:
        raise ValueError('missing required setting: ' + name)
    return Path(value).resolve()


def selection():
    if os.environ.get('MACHINE') != 'MT6762':
        raise ValueError('this profile requires MACHINE=MT6762')
    if env_path('XNU_SRC') != KERNEL.resolve():
        raise ValueError('XNU_SRC must select this monorepo kernel, not the frozen old tree')
    if env_path('XNUDEPS') != (ROOT / 'xnu-deps').resolve():
        raise ValueError('XNUDEPS must select the new monorepo build rules')


def check_iig():
    selection()
    replay = env_path('IIG')
    allowed = {KERNEL / 'tools/mt6762/iig' / name for name in
               ('replay.py', 'experimental_legacy_replay.py')}
    if replay not in {p.resolve() for p in allowed} or not os.access(replay, os.X_OK):
        raise ValueError('IIG must be the selected new-tree verified replay, never the SDK-header shim')
    if env_path('MTK_IIG_XNU') != KERNEL.resolve():
        raise ValueError('MTK_IIG_XNU must match the new kernel checkout')
    if env_path('MTK_IIG_OUTPUT_ROOT') != (KERNEL / 'BUILD').resolve():
        raise ValueError('MTK_IIG_OUTPUT_ROOT must be the new kernel BUILD')
    for name in ('MTK_IIG_INPUTS', 'MTK_IIG_GENERATED', 'MTK_IIG_INPUT_SHA256',
                 'MTK_IIG_GENERATION_SHA256'):
        if not os.environ.get(name):
            raise ValueError('missing pinned IIG setting: ' + name)
    if replay.name == 'experimental_legacy_replay.py':
        for name in ('MTK_IIG_CANDIDATE', 'MTK_IIG_CANDIDATE_SHA256'):
            if not os.environ.get(name):
                raise ValueError('missing legacy-candidate setting: ' + name)
    subprocess.run([str(replay), 'verify'], check=True)


def git_revision(path, expected):
    actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != expected:
        raise ValueError('unexpected dependency revision: ' + str(path))
    if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=no']):
        raise ValueError('tracked dependency inputs changed: ' + str(path))


def tool_files():
    compiler, host = env_path('MTK_LLVM_BIN'), env_path('MTK_HOST_TOOLS')
    cctools = env_path('THEOS') / 'toolchain/linux/iphone/bin'
    return ([compiler / n for n in ('clang', 'clang++', 'dsymutil')] +
            [host / n for n in HOST_TOOLS] + [cctools / n for n in CCTOOLS])


def check_reuse():
    selection()
    if os.environ.get('XNU_HOST_OS') != 'Linux':
        raise ValueError('the reused MTK host binaries are a Linux profile')
    for path in tool_files():
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError('missing executable: ' + str(path))
    for name, revision in REVISIONS.items():
        git_revision(env_path(name), revision)
    sdk = env_path('THEOS') / 'sdks'
    git_revision(sdk, SDK_REVISION)
    if not (sdk / 'iPhoneOS16.5.sdk/usr/include').is_dir():
        raise ValueError('missing reused iPhoneOS16.5 SDK headers')
    expected_overlay = ROOT / 'xnu-deps/sdk/iPhoneOS16.5.mt6762.sdk'
    if env_path('XNU_SDK_PATH') != expected_overlay.resolve() or expected_overlay.is_symlink():
        raise ValueError('MTK requires its separate monorepo SDK overlay')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def snapshot():
    check_reuse()
    # Hash actual source/tool inputs; omit generated SDK archives/objects that
    # this build intentionally replaces. Kernel/IIG inputs have own snapshots.
    files = set(tool_files())
    files.update(ROOT / name for name in ('xnu-env.sh', 'xnu-build.sh',
        'xnu-deps/setup.sh', 'xnu-deps/build/pthread/build.sh',
        'xnu-deps/host/bin/xnu-clang', 'xnu-deps/host/bin/xcrun', 'xnu-deps/host/bin/iig'))
    files.update(ROOT / 'devices/mt6762' / name for name in ('build_inputs.py', 'build-kernel.sh'))
    files.update(p for p in (ROOT / 'xnu-deps/host/bin').iterdir() if p.is_file())
    files.update(KERNEL / 'tools/mt6762' / name for name in ('build.sh', 'bootstrap.sh',
        'source_snapshot.py', 'iig_snapshot.py'))
    for directory in (ROOT / 'xnu-deps/hostinc', ROOT / 'xnu-deps/build/pthread/inc'):
        files.update(p for p in directory.rglob('*') if p.is_file() and
                     not p.is_relative_to(ROOT / 'xnu-deps/hostinc/mach-o'))
    for name in REVISIONS:
        directory = env_path(name)
        paths = subprocess.check_output(['git', '-C', str(directory), 'ls-files', '-z']).decode().split('\0')
        files.update(directory / p for p in paths if p and (directory / p).is_file())
    sdk = env_path('THEOS') / 'sdks/iPhoneOS16.5.sdk'
    files.update(p for p in sdk.rglob('*') if p.is_file())
    hashes = {str(p): digest(p) for p in sorted(files)}
    selected = {k: os.environ[k] for k in ('MACHINE', 'XNU_SRC', 'XNUDEPS', 'THEOS',
        'MTK_LLVM_BIN', 'MTK_HOST_TOOLS', 'XNU_SDK_PATH', *REVISIONS)}
    record = {'format': 1, 'monorepo': str(ROOT), 'selected_environment': selected,
              'files': hashes, 'resolved_tools': {str(p): str(p.resolve()) for p in tool_files()}}
    record['sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return record


def main():
    try:
        if sys.argv[1:] == ['check-iig']:
            check_iig()
        elif sys.argv[1:] == ['check-reuse']:
            check_reuse()
            print('MT6762 reuse profile validated; no build or source mutation')
        elif len(sys.argv) == 3 and sys.argv[1] == 'snapshot':
            Path(sys.argv[2]).write_text(json.dumps(snapshot(), indent=2) + '\n')
        else:
            raise ValueError('usage: build_inputs.py check-iig|check-reuse|snapshot OUTPUT')
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('MT6762 build profile rejected: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
