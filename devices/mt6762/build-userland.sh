#!/usr/bin/env bash
# MT6762 physical /redwood helper image. Never writes a device or an Apple file.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
if [[ $# != 1 || $1 == --help ]]; then
    echo 'Usage: devices/mt6762/build-userland.sh NEW_OUTPUT_DIRECTORY'
    echo 'Local inputs: MTK_WORKSPACE, MTK_IOS, MTK_SYSTEM_APFS, MTK_ROOT_TEMPLATE,'
    echo '              MTK_LLVM_BIN, MTK_LD64, MTK_IOS_SDK (see USERLAND.md).'
    [[ ${1:-} == --help ]] && exit 0
    exit 2
fi
WORK=${MTK_WORKSPACE:-$(dirname "$REPO")}
export MTK_WORKSPACE="$WORK"
export MTK_LLVM_BIN=${MTK_LLVM_BIN:-$(dirname "$(readlink -f "$WORK/toolchain/bin/clang")")}
export MTK_LD64=${MTK_LD64:-$WORK/toolchain/theos/toolchain/linux/iphone/bin/ld}
export MTK_IOS_SDK=${MTK_IOS_SDK:-$WORK/toolchain/theos/sdks/iPhoneOS16.5.sdk}
exec python3 - "$REPO" "$1" <<'PY'
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import struct
import subprocess
import sys

repo, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).absolute()
work = Path(os.environ['MTK_WORKSPACE']).resolve()
ios = Path(os.environ.get('MTK_IOS', work / 'runtime/ios165')).resolve()
system = Path(os.environ.get('MTK_SYSTEM_APFS', work / 'runtime/userland/system.apfs')).resolve()
template = Path(os.environ.get('MTK_ROOT_TEMPLATE', work / 'boot/desktop-bootstrap-build2-root/root')).resolve()
llvm = Path(os.environ['MTK_LLVM_BIN']).resolve()
clang, ld = llvm / 'clang', Path(os.environ['MTK_LD64']).resolve()
sdk = Path(os.environ['MTK_IOS_SDK']).resolve()
xnu = repo / 'xnu-src/xnu-8796.121.2'

def require(ok, message):
    if not ok:
        raise SystemExit(message)

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def files(path):
    return sorted(p for p in path.rglob('*') if p.is_file() and not p.is_symlink())

require(not output.exists() and not output.is_symlink(), f'Refusing existing output: {output}')
require(output.resolve() not in (repo, work, ios, template), 'Output overlaps an input')
for path in (clang, ld, sdk / 'SDKSettings.plist', system, template / 'etc/var.skel'):
    require(path.is_file(), f'Missing local prerequisite: {path}')
version_path = ios / 'rootfs/System/Library/CoreServices/SystemVersion.plist'
version = plistlib.loads(version_path.read_bytes())
require((version.get('ProductVersion'), version.get('ProductBuildVersion')) == ('16.5', '20F66'),
        'Only the extracted iPhone10,3/6 iOS 16.5 20F66 profile is admitted')
system_sha = sha(system)
require(system_sha == '9329e9c9bf46d6890798bb15d0d0036ec8c9235abf7d77edbacdd346992454a0',
        'System image differs from the physically exercised 20F66 image; review a new profile first')
# Preserve exactly the existing Apple job selection, preferences, var template and test data.
# No old project executable, library, service or firmware is inherited.
config = [p for p in files(template) if str(p.relative_to(template)).startswith(
    ('LaunchDaemons/com.apple.', 'etc/var.skel', 'var/', 'share/pattern.bin'))]
config_record = [(str(p.relative_to(template)), sha(p)) for p in config]
config_sha = hashlib.sha256(json.dumps(config_record, separators=(',', ':')).encode()).hexdigest()
require(config_sha == '45d3f861cd0ab4e46e4361eba147c1801978bebc088f72b8a114cc44d7753f60',
        'Baseline root configuration differs from desktop-bootstrap-build2-root')
inputs = files(repo / 'userland/src') + files(repo / 'userland/libmini') + config
inputs += [repo / 'devices/mt6762/build-userland.sh', repo / 'userland/com.hakios.demo.plist',
           repo / 'devices/mt6762/bootdiag.c',
           repo / 'userland/rc.launchd', version_path, sdk / 'SDKSettings.plist',
           xnu / 'tools/mt6762/boot/desktop_bootstrap.c',
           xnu / 'tools/mt6762/boot/test_desktop_entry.py',
           xnu / 'tools/mt6762/hardware/power/battery_probe.c',
           xnu / 'bsd/sys/hakios.input.h', clang.resolve(), ld]
inputs += files(repo / 'tools/apfs') + files(xnu / 'bsd/miscfs/apfs')
inputs += list((xnu / 'bsd/vfs').glob('vfs_unicode*')) + [xnu / 'bsd/sys/unicode.h']
before = {str(p): sha(p) for p in inputs}
user_header = (repo / 'userland/src/hakios.input.h').read_text().split('#ifdef KERNEL')[0]
kernel_header = (xnu / 'bsd/sys/hakios.input.h').read_text().split('#ifdef KERNEL')[0]
require(user_header == kernel_header, 'Userland/kernel touch ABI differs')
require('kern.hakios_switch_root' in (xnu / 'tools/mt6762/boot/desktop_bootstrap.c').read_text(),
        'Bootstrap has not migrated to the HakiOS sysctl namespace')
output.mkdir(parents=True)
root, obj, source = output / 'root', output / 'obj', output / 'source'
for directory in ('sbin', 'bin', 'lib', 'etc', 'share', 'LaunchDaemons', 'dev',
                  'private/var', 'var', 'empty', 'xpc', 'hal', 'newroot'):
    (root / directory).mkdir(parents=True, exist_ok=True)
obj.mkdir()
shutil.copytree(repo / 'userland/src', source / 'src')
shutil.copytree(repo / 'userland/libmini', source / 'libmini')
shutil.copy2(repo / 'devices/mt6762/bootdiag.c', source / 'src/mt6762_bootdiag.c')
for name, path in [('desktop_bootstrap.c', xnu / 'tools/mt6762/boot/desktop_bootstrap.c'),
                   ('battery_probe.c', xnu / 'tools/mt6762/hardware/power/battery_probe.c')]:
    shutil.copy2(path, source / name)
for path in config:
    target = root / path.relative_to(template)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
commands = []

def run(args, **kwargs):
    args = [str(a) for a in args]
    commands.append(args)
    return subprocess.run(args, check=True, **kwargs)

common = [clang, '--target=arm64-apple-ios16.5', '-mcpu=cortex-a53', '-mno-outline-atomics',
          '-fno-stack-protector', '-Wall', '-Wextra']
static = common + ['-Os', '-ffreestanding', '-fno-builtin', '-nostdlib', '-I' + str(source / 'libmini')]
dynamic = common + ['--ld-path=' + str(ld), '-isysroot', sdk, '-O1']
for name in ('mini.c', 'start.S'):
    run(static + ['-c', source / 'libmini' / name, '-o', obj / (Path(name).stem + '.o')])
for name, target in [('init', root / 'sbin/init'), ('child', root / 'bin/child')]:
    run(static + ['-c', source / 'src' / (name + '.c'), '-o', obj / (name + '.o')])
    run([ld, '-arch', 'arm64', '-platform_version', 'ios', '16.5', '16.5', '-static',
         '-e', '_start', '-pagezero_size', '0x100000000', '-o', target,
         obj / (name + '.o'), obj / 'mini.o', obj / 'start.o'])
run(static + ['-Werror', '-c', source / 'desktop_bootstrap.c', '-o', obj / 'desktop_bootstrap.o'])
run([ld, '-arch', 'arm64', '-platform_version', 'ios', '16.5', '16.5', '-static',
     '-e', '_start', '-pagezero_size', '0x100000000', '-o', root / 'sbin/launchd',
     obj / 'desktop_bootstrap.o'])
for name, frameworks in [('hello_dyn', []), ('rwtouch', []),
                         ('svc_test', ['CoreFoundation']), ('surf_test', ['CoreFoundation', 'IOSurface'])]:
    flags = [part for fw in frameworks for part in ('-framework', fw)]
    run(dynamic + flags + ['-o', root / 'bin' / name, source / 'src' / (name + '.c')])
run(dynamic + ['-framework', 'CoreFoundation', '-framework', 'IOKit', '-o',
               root / 'bin/battery_probe', source / 'battery_probe.c'])
libraries = [
    ('libhakios.bootdiag.dylib', ['mt6762_bootdiag.c'], [], False),
    ('libhakios.dylib', ['inject.c'], ['CoreFoundation', 'IOKit'], True),
    ('libhakios.sb.dylib', ['inject_sb.c', 'mt6762_bootdiag.c'], ['CoreFoundation', 'IOKit'], True),
    ('libhakios.media.dylib', ['inject_media.c', 'camera_device.c', 'camera_isp.c'],
     ['CoreFoundation', 'CoreMedia', 'CoreVideo', 'IOSurface'], True),
    ('libhakios.app.dylib', ['inject_app.c'], [], True),
    ('libhakios.tweaks.dylib', ['inject_tweaks.c'], ['CoreFoundation'], True),
]
for name, names, frameworks, objc in libraries:
    flags = [part for fw in frameworks for part in ('-framework', fw)] + (['-lobjc'] if objc else [])
    run(dynamic + ['-dynamiclib', '-install_name', '/redwood/lib/' + name] + flags +
        ['-o', root / 'lib' / name] + [source / 'src' / n for n in names])
shutil.copy2(repo / 'userland/com.hakios.demo.plist', root / 'LaunchDaemons/com.hakios.demo.plist')
shutil.copy2(repo / 'userland/rc.launchd', root / 'etc/rc')
(root / 'etc/motd').write_text('HakiOS MT6762 / iOS 16.5 20F66 / Cortex-A53\n')
(root / 'etc/rc.jobs').write_text('# Read-only battery publication: 12 samples at 1000 ms, never a SOC setting.\n'
                                  '/redwood/bin/battery_probe 12 1000 &\n')
(root / 'etc/inject.conf').write_text(
    '/redwood/lib/libhakios.dylib backboardd containermanagerd containermanagerd_system\n'
    '/redwood/lib/libhakios.sb.dylib SpringBoard\n'
    '/redwood/lib/libhakios.bootdiag.dylib lsd\n'
    '/redwood/lib/libhakios.media.dylib mediaserverd\n'
    '/redwood/lib/libhakios.app.dylib Sileo\n'
    '/redwood/lib/libhakios.tweaks.dylib Preferences\n')
# Check the actual new SpringBoard hook functions with an unknown native battery,
# both with and without a registered IOPMPowerSource. This runs host C, not iOS.
sb = (source / 'src/inject_sb.c').read_text()
def function(name, result):
    start = sb.index('\n' + name + '(') + 1
    end = sb.index('\n}', start) + 2
    return result + ' ' + sb[start:end]
test = '''#include <assert.h>
#include <string.h>
typedef void *id; typedef void *SEL;
static int soc=-1, charging=-1, present=-1, plugged=-1, power_source;
static float (*original_battery_level)(id,SEL);
static long (*original_battery_state)(id,SEL);
static int battery_power_source(void){return power_source;}
static int sysctl_int(const char *n){
 if(!strcmp(n,"kern.hakios.battery_soc"))return soc;
 if(!strcmp(n,"kern.hakios.battery_charging"))return charging;
 if(!strcmp(n,"kern.hakios.battery_present"))return present;
 if(!strcmp(n,"kern.hakios.battery_charger_present"))return plugged;
 assert(0);return -1;}
static float old_level(id s,SEL c){(void)s;(void)c;return -1.0f;}
static long old_state(id s,SEL c){(void)s;(void)c;return 0;}
'''+function('battery_level','static float')+'\n'+function('battery_state','static long')+'''
int main(void){
 for(power_source=0;power_source<2;power_source++){
  assert(battery_level(0,0)==-1.0f);assert(battery_state(0,0)==0);
  original_battery_level=old_level;original_battery_state=old_state;
  assert(battery_level(0,0)==-1.0f);assert(battery_state(0,0)==0);
 }
 power_source=0;present=plugged=charging=1;
 soc=101;assert(battery_level(0,0)==-1.0f);assert(battery_state(0,0)==0);
 soc=50;assert(battery_level(0,0)==0.5f);assert(battery_state(0,0)==2);
 soc=100;assert(battery_level(0,0)==1.0f);assert(battery_state(0,0)==3);
 power_source=1;assert(battery_level(0,0)==-1.0f);assert(battery_state(0,0)==0);
 return 0;}
'''
(obj / 'battery-hooks-test.c').write_text(test)
run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', obj / 'battery-hooks-test.c', '-o', obj / 'battery-hooks-test'])
run([obj / 'battery-hooks-test'])
run([sys.executable, xnu / 'tools/mt6762/boot/test_desktop_entry.py', root / 'sbin/launchd',
     '--output', output / 'bootstrap-entry-test.json'])
# Every shipped project binary must be ordinary arm64, use the migrated names,
# and contain no instructions outside the Cortex-A53's ARMv8.0 target.
import capstone
decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
instruction_counts = {}
hint_nops = []
for path in files(root):
    data = path.read_bytes()
    for stale in (b'kern.redwood', b'/dev/redwood-touch', b'libredwood', b'com.redwood'):
        require(stale not in data, f'Stale runtime namespace in {path}: {stale!r}')
    if data[:4] != b'\xcf\xfa\xed\xfe':
        continue
    header = struct.unpack_from('<8I', data)
    require(header[1:3] == (0x100000c, 0), f'Expected generic arm64, not arm64e: {path}')
    offset, count = 32, 0
    for _ in range(header[4]):
        cmd, size = struct.unpack_from('<II', data, offset)
        if cmd == 0x19:
            nsects = struct.unpack_from('<I', data, offset + 64)[0]
            for i in range(nsects):
                section = offset + 72 + 80 * i
                flags = struct.unpack_from('<I', data, section + 64)[0]
                if not flags & 0x80000000:  # S_ATTR_PURE_INSTRUCTIONS
                    continue
                address, length, fileoff = struct.unpack_from('<QQI', data, section + 32)
                for insn in decoder.disasm(data[fileoff:fileoff+length], address):
                    # LLVM emits XPACLRI for __builtin_return_address even for
                    # cortex-a53. This exact HINT #7 encoding executes as NOP
                    # without FEAT_PAuth (Arm DDI0487, XPACLRI System decode).
                    # XPACI/XPACD use different encodings and remain rejected.
                    if insn.mnemonic == 'xpaclri' and insn.bytes == bytes.fromhex('ff2003d5'):
                        hint_nops.append(dict(path=str(path.relative_to(root)), pc=hex(insn.address),
                                              encoding='d50320ff', behavior_on_a53='NOP'))
                        count += 1
                        continue
                    require(not re.match(r'^(cas|swp|ldadd|ldclr|ldeor|ldset|ldsmax|ldsmin|ldumax|ldumin|'
                                         r'stadd|stclr|steor|stset|stsmax|stsmin|stumax|stumin|'
                                         r'pac|aut|xpac|retaa|retab|braa|brab|blraa|blrab|bti|'
                                         r'ldra|ldapr|stg|ldg|irg|addg|subg|cfinv|rmif|setf)', insn.mnemonic),
                            f'Unsupported A53 instruction in {path}: {insn.mnemonic}')
                    count += 1
        offset += size
    require(count > 0, f'No executable instructions inspected: {path}')
    instruction_counts[str(path.relative_to(root))] = count
for line in (root / 'etc/inject.conf').read_text().splitlines():
    library = line.split()[0]
    require(library.startswith('/redwood/') and (root / library[9:]).is_file(), 'Missing injection library')
run([sys.executable, repo / 'tools/apfs/mkapfs.py', '-z', '-o', output / 'root.apfs', 'redwood=' + str(root)])
# Build only the host APFS reader, with the migrated driver sources. No kernel build,
# downloads, dependency setup, or global apfs-work mutation is involved.
run([repo / 'tools/apfs/build-tool.sh', obj / 'apfs-tool'])
run(['cc', '-O2', repo / 'tools/apfs/fnvsum.c', '-o', obj / 'fnvsum'])
spec = importlib.util.spec_from_file_location('check_image', repo / 'tools/apfs/check-image.py')
sys.path.insert(0, str(repo / 'tools/apfs'))
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
checker.FNVSUM = str(obj / 'fnvsum')
want = checker.expected(checker.mkapfs.read_tree(str(root)))
result = run([obj / 'apfs-tool', 'census', output / 'root.apfs'], capture_output=True, text=True)
got = {line.split('\t')[0]: line for line in result.stdout.splitlines() if line}
require(got == want, 'APFS driver readback differs from the staged root')
(output / 'root-census.txt').write_text(result.stdout)
# Verify the system-side contract by reading the existing image, without replacing
# /sbin/launchd or any Apple program in it. Our physical bootstrap directly execs init.
apple_launchd = ios / 'rootfs/sbin/launchd'
result = run([obj / 'apfs-tool', 'cat', system, '/sbin/launchd.ios'], capture_output=True)
require(hashlib.sha256(result.stdout).hexdigest() == sha(apple_launchd), 'Apple launchd differs')
require(sha(system) == system_sha, 'System APFS changed during build')
require(all(sha(path) == digest for path, digest in before.items()), 'A source/input changed during build')
report = dict(profile='MT6762-20F66-hakios-userland-v1', result='PASS',
    root_apfs=str(output / 'root.apfs'), root_sha256=sha(output / 'root.apfs'),
    root_bytes=(output / 'root.apfs').stat().st_size,
    system_apfs=str(system), system_sha256=system_sha, system_rebuilt=False,
    apple_build=version, apple_launchd_sha256=sha(apple_launchd), apple_binaries_modified=False,
    root_configuration_sha256=config_sha, preserved_configuration_files=config_record,
    runtime_prefix='/redwood', touch_device='/dev/hakios-touch', namespace='kern.hakios',
    source_inputs_stable=True, inputs_sha256=before, commands=commands,
    target='arm64-apple-ios16.5 -mcpu=cortex-a53 -mno-outline-atomics',
    startup_observer=dict(processes=['SpringBoard','lsd'], samples=32, interval_seconds=20,
                          other_threads_maximum=32, other_threads_sample_indices=[0,3,6],
                          suspends_threads=False, apple_code_modified=False, atomic_stack=False),
    project_binary_instruction_counts=instruction_counts,
    a53_compatible_hint_nops=hint_nops,
    tests=dict(battery_unknown_hooks='PASS', touch_header_abi='PASS', bootstrap_sp_alignment='PASS',
               native_apfs_readback_entries=len(got), arm64_namespace_instruction_scan='PASS'),
    phone_written=False, physical_boot_tested=False, rendering='existing CoreAnimation software path',
    omitted_project_services=['wifi', 'varstore', 'thermald'],
    limitations=['Requires the migrated HakiOS MT6762 kernel and existing readonly mtkios0 slice',
                 'No absolute battery/SOC calibration or charging-control grant',
                 'Native physical desktop and new helper behavior remain untested',
                 'Instruction blacklist supplements the Cortex-A53 compiler target; not a CPU emulator',
                 'APFS driver census passed; external apfsck was not run'])
(output / 'userland-evidence.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: report[key] for key in ('result','root_apfs','root_sha256','root_bytes','system_apfs',
                                              'system_rebuilt','phone_written','physical_boot_tested')}, indent=2))
PY
