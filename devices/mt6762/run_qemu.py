#!/usr/bin/env python3
"""Bounded migrated-userland smoke on the custom MT6762 QEMU machine.

Requires an explicit successful new-monorepo kernel build report and migrated
userland evidence. --prepare-only never starts QEMU. The original system image
is read only; a fresh sparse eMMC fixture contains an exact copy of its bytes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
XNU = REPO / 'xnu-src/xnu-8796.121.2'
SYSTEM_SHA = '9329e9c9bf46d6890798bb15d0d0036ec8c9235abf7d77edbacdd346992454a0'
SYSTEM_BYTES = 2491162624
SLICE_START = 12566528
SLICE_COUNT = 4865552
PROFILE = 'MT6762-20F66-hakios-userland-v1'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular(path):
    path = Path(path).resolve(strict=True)
    require(path.is_file(), 'Not a regular file: ' + str(path))
    require(',' not in str(path) and not any(ord(c) < 32 for c in str(path)),
            'Ambiguous QEMU file path: ' + str(path))
    return path


def validate_kernel(path, report_path):
    kernel, report_path = regular(path), regular(report_path)
    report = json.loads(report_path.read_text())
    require(report.get('artifact_ready') is True and report.get('new_link_observed') is True,
            'Kernel report does not establish a fresh accepted link')
    for key in ('source_unchanged_during_build', 'build_inputs_unchanged_during_build',
                'iig_inputs_unchanged_during_build', 'macho_arm64_executable'):
        require(report.get(key) is True, 'Kernel report failed: ' + key)
    require(Path(report.get('build_monorepo', '')).resolve() == REPO,
            'Kernel report selects a different/old monorepo')
    require(report.get('sha256') == sha(kernel), 'Kernel bytes differ from build report')
    return kernel, report


def validate_userland(directory):
    directory = Path(directory).resolve(strict=True)
    evidence_path = regular(directory / 'userland-evidence.json')
    evidence = json.loads(evidence_path.read_text())
    require(evidence.get('profile') == PROFILE and evidence.get('result') == 'PASS',
            'Requires the migrated MT6762 helper-root profile')
    require(evidence.get('source_inputs_stable') is True and
            evidence.get('system_rebuilt') is False and
            evidence.get('apple_binaries_modified') is False,
            'Userland source/original Apple image verification failed')
    require(evidence.get('namespace') == 'kern.hakios' and
            evidence.get('touch_device') == '/dev/hakios-touch', 'Old helper ABI rejected')
    root = regular(directory / 'root.apfs')
    require(Path(evidence.get('root_apfs', '')).resolve() == root,
            'Userland manifest root path differs from selected root')
    require(sha(root) == evidence.get('root_sha256') and root.stat().st_size == evidence.get('root_bytes'),
            'Migrated helper root changed after validation')
    # Bind selected source helpers to this monorepo, not an old root bearing a new label.
    inputs = evidence.get('inputs_sha256', {})
    for relative in ('devices/mt6762/build-userland.sh', 'devices/mt6762/bootdiag.c', 'userland/src/init.c',
                     'userland/src/inject.c', 'userland/src/inject_sb.c',
                     'userland/src/hakios.input.h',
                     'xnu-src/xnu-8796.121.2/bsd/sys/hakios.input.h',
                     'xnu-src/xnu-8796.121.2/tools/mt6762/boot/desktop_bootstrap.c'):
        path = REPO / relative
        require(inputs.get(str(path)) == sha(path), 'Userland source binding differs: ' + relative)
    system = regular(evidence['system_apfs'])
    require(evidence.get('system_sha256') == SYSTEM_SHA and system.stat().st_size == SYSTEM_BYTES
            and sha(system) == SYSTEM_SHA, 'Original 20F66 system APFS differs')
    return root, system, evidence


def copy_slice(system, fixture, start, count):
    """Create a new raw fixture; never overwrite or open source writable."""
    require(system.stat().st_size == count * 512, 'System length does not match slice')
    digest = hashlib.sha256()
    with fixture.open('xb') as target, system.open('rb') as source:
        target.truncate((start + count) * 512)
        target.seek(start * 512)
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            target.write(block)
            digest.update(block)
    return digest.hexdigest()


def check_smoke(log, models, cpus):
    required = ['MT6762_DESKTOP bootstrap ready', 'MT6762_DESKTOP system_mounted result=0',
                'MT6762_DESKTOP system root active; starting existing init',
                '=== init: process 1, started as /redwood/sbin/init ===']
    missing = [marker for marker in required if marker not in log]
    online = sorted(set(int(n) for n in re.findall(r'arm_cpu_init\(\): cpu (\d+) online', log)))
    absent_cpus = [n for n in range(1, cpus) if n not in online]
    errors = [value for value in ('panic(', 'MT6762_DESKTOP stopped', 'pid 1 exited') if value in log]
    if models.get('kernel_panic_observed'):
        errors.append('capture observed panic')
    if models.get('terminal_storage_failure_observed'):
        errors.append('capture observed terminal storage failure')
    if not models.get('run_completed'):
        errors.append('bounded capture did not complete')
    return dict(passed=not missing and not absent_cpus and not errors,
                missing_markers=missing, secondary_cpus_online=online,
                missing_secondary_cpus=absent_cpus, errors=errors,
                desktop_proven=False, physical_hardware_tested=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel', type=Path, required=True)
    p.add_argument('--kernel-build-report', type=Path, required=True)
    p.add_argument('--userland', type=Path, required=True, help='Fresh build-userland.sh output directory')
    p.add_argument('--out', type=Path, required=True, help='New, nonexistent output directory')
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--cpus', type=int, choices=(1, 2, 4, 8), default=8)
    p.add_argument('--seconds', type=int, default=120, help='Bounded smoke: 15..600 seconds, default120')
    work = Path(os.environ.get('MTK_WORKSPACE', REPO.parent))
    llvm = Path(os.environ.get('MTK_LLVM_BIN', work / 'toolchain/bin'))
    p.add_argument('--qemu', type=Path, default=work / 'qemu/build/qemu-system-aarch64')
    p.add_argument('--linux-dtb', type=Path, default=work / 'firmware/boot.bin.dtb')
    p.add_argument('--clang', type=Path, default=llvm / 'clang')
    p.add_argument('--objcopy', type=Path, default=llvm / 'llvm-objcopy')
    a = p.parse_args()
    require(15 <= a.seconds <= 600, 'Smoke duration must be 15..600 seconds')
    output = a.out.absolute()
    require(not output.exists() and not output.is_symlink(), 'Refusing existing output directory')
    # Checking inputs first does not create or mutate any build/kernel/root artifact.
    kernel, build = validate_kernel(a.kernel, a.kernel_build_report)
    root, system, userland = validate_userland(a.userland)
    tools = {name: regular(getattr(a, name)) for name in ('qemu', 'linux_dtb', 'clang', 'objcopy')}
    for name in ('qemu', 'clang', 'objcopy'):
        require(os.access(tools[name], os.X_OK), 'Tool is not executable: ' + name)
    output.mkdir(parents=True)
    kernel_copy = output / 'kernel.macho'
    shutil.copyfile(kernel, kernel_copy)
    require(sha(kernel_copy) == build['sha256'], 'Kernel changed while being copied')
    fixture = output / 'emmc-readonly.img'
    require(copy_slice(system, fixture, SLICE_START, SLICE_COUNT) == SYSTEM_SHA,
            'System changed while constructing synthetic read-only eMMC')
    fixture.chmod(0o444)
    boot = XNU / 'tools/mt6762/boot'
    prepare = [sys.executable, str(boot / 'prepare.py'), '--kernel', str(kernel_copy),
               '--out', str(output / 'payload'), '--ramdisk', str(root), '--memory-mib', '3840',
               '--cpus', str(a.cpus), '--framebuffer', '--native-lab-i2c', '--native-lab-power',
               '--native-lab-gauge', '--native-lab-display', '--native-lab-msdc-image', str(fixture),
               '--native-lab-ios-slice', str(SLICE_START), str(SLICE_COUNT), '--cmdline',
               f'debug=0x14e serial=3 keepsyms=1 -v -enable_kprintf_spam cpus={a.cpus} rd=md0 systrace=1 systrace_name=launchd applog=1']
    for name, value in tools.items():
        prepare += ['--' + name.replace('_', '-'), str(value)]
    capture = [sys.executable, str(boot / 'capture.py'), str(output / 'payload/manifest.json'),
               '--seconds', str(a.seconds), '--label', 'smoke', '--stop-on-panic',
               '--stop-on-storage-error', '--host-scheduling']
    record = dict(format=1, profile='MT6762-hakios-qemu-smoke-v1', synthetic_only=True,
                  prepare_only=a.prepare_only, seconds=a.seconds, cpus=a.cpus,
                  kernel_sha256=build['sha256'], kernel_build_report_sha256=sha(a.kernel_build_report),
                  userland_evidence_sha256=sha(a.userland / 'userland-evidence.json'),
                  root_sha256=userland['root_sha256'], system_sha256=SYSTEM_SHA,
                  system_original=str(system), system_modified=False, fixture=str(fixture),
                  slice_start=SLICE_START, slice_count=SLICE_COUNT,
                  tools={name:dict(path=str(path),sha256=sha(path)) for name,path in tools.items()},
                  prepare_command=prepare, capture_command=capture,
                  limits=['Synthetic device fixtures do not prove physical support',
                          'Smoke markers do not prove desktop presentation or full Apple startup',
                          'The original system and fixture backend are read-only'])
    (output / 'run-inputs.json').write_text(json.dumps(record, indent=2) + '\n')
    with (output / 'prepare.log').open('w') as log:
        subprocess.run(prepare, stdout=log, stderr=subprocess.STDOUT, check=True)
    manifest = json.loads((output / 'payload/manifest.json').read_text())
    require(manifest['kernel_sha256'] == build['sha256'], 'Prepared kernel identity differs')
    disks = [r for r in manifest['regions'] if r['name'] == 'RAMDisk']
    require(len(disks) == 1 and disks[0]['source_sha256'] == userland['root_sha256'],
            'Prepared helper root identity differs')
    require(manifest['native_lab_msdc_image']['readonly'] is True and
            manifest['native_lab_ios_slice'] == [SLICE_START, SLICE_COUNT], 'Prepared eMMC contract differs')
    if a.prepare_only:
        print(json.dumps({'prepared':str(output/'payload/manifest.json'), 'qemu_started':False}))
        return
    result = subprocess.run(capture, check=False)
    models_path = output / 'payload/smoke.models.json'
    models = json.loads(models_path.read_text()) if models_path.is_file() else {}
    serial = output / 'payload/smoke.serial.log'
    evidence = check_smoke(serial.read_text(errors='replace') if serial.is_file() else '', models, a.cpus)
    evidence.update(capture_exit_code=result.returncode, kernel_sha256=build['sha256'],
                    serial_sha256=sha(serial) if serial.is_file() else None,
                    original_system_unchanged=sha(system) == SYSTEM_SHA,
                    helper_root_unchanged=sha(root) == userland['root_sha256'],
                    fixture_unchanged=sha(fixture) == manifest['native_lab_msdc_image']['sha256'])
    evidence['passed'] &= (result.returncode == 0 and evidence['original_system_unchanged']
                           and evidence['helper_root_unchanged'] and evidence['fixture_unchanged'])
    (output / 'smoke-result.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
    if not evidence['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
