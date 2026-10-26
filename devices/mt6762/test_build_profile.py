#!/usr/bin/env python3
"""Offline shell/profile tests. No make, kernel build, SDK setup or device I/O."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / 'xnu-src/xnu-8796.121.2'
spec = importlib.util.spec_from_file_location('build_inputs', Path(__file__).with_name('build_inputs.py'))
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def clean_env():
    return {k: v for k, v in os.environ.items() if not
            (k.startswith(('MTK_', 'XNU_', 'HAKIOS_')) or
             k in ('MACHINE', 'IIG', 'THEOS', 'MIG', 'MIGCOM', 'XNUDEPS'))}


def shell_environment(extra):
    result = subprocess.run(['bash', '-c', 'source "$1" && env -0', '_', str(ROOT / 'xnu-env.sh')],
                            env=clean_env() | extra, check=True, capture_output=True)
    return dict(x.decode().split('=', 1) for x in result.stdout.split(b'\0') if x)


class ProfileTests(unittest.TestCase):
    def test_other_board_defaults_unchanged(self):
        env = shell_environment({})
        self.assertEqual(env['THEOS'], str(Path.home() / 'theos'))
        self.assertEqual(env['XNU_SRC'], str(KERNEL))
        self.assertEqual(env['XNU_SDK_PATH'], str(ROOT / 'xnu-deps/sdk/iPhoneOS16.5.xnu.sdk'))
        self.assertNotIn('MTK_LLVM_BIN', env)
        self.assertNotIn('MIG', env)

    def test_mtk_selection_and_readonly_reuse_check(self):
        env = shell_environment({'MACHINE': 'MT6762'})
        self.assertEqual(env['XNU_SRC'], str(KERNEL))
        self.assertEqual(env['XNUDEPS'], str(ROOT / 'xnu-deps'))
        self.assertEqual(env['XNU_SDK_PATH'], str(ROOT / 'xnu-deps/sdk/iPhoneOS16.5.mt6762.sdk'))
        with patch.dict(os.environ, env, clear=True):
            profile.check_reuse()

    def test_actual_compiler_wrapper_forces_a53_last(self):
        with tempfile.TemporaryDirectory(prefix='mtk-profile-') as name:
            directory = Path(name)
            for compiler in ('clang', 'clang++'):
                p = directory / compiler
                p.write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
                p.chmod(0o755)
            env = clean_env() | {'MACHINE': 'MT6762', 'MTK_LLVM_BIN': name, 'THEOS': '/selected/theos'}
            for cpp in (False, True):
                wrapper = ROOT / 'xnu-deps/host/bin/xnu-clang'
                if cpp:
                    alias = directory / 'xnu-clang++'
                    alias.symlink_to(wrapper)
                    wrapper = alias
                result = subprocess.run([str(wrapper), '-mcpu=apple-m1', '-Werror', '-c', 'sample.c'],
                                        env=env, check=True, capture_output=True, text=True)
                args = json.loads(result.stdout)
                self.assertEqual(args[-1], '-mcpu=cortex-a53')
                self.assertIn('arm64-apple-ios16.5', args)
                self.assertIn('--ld-path=/selected/theos/toolchain/linux/iphone/bin/ld', args)
                self.assertNotIn('-Werror', args)
                self.assertEqual('-fno-use-cxa-atexit' in args, cpp)

    def test_placeholder_iig_rejected_before_any_output(self):
        with tempfile.TemporaryDirectory(prefix='mtk-iig-reject-') as name:
            directory = Path(name)
            result = subprocess.run([str(ROOT / 'xnu-deps/host/bin/iig'), '--def', 'OSObject.iig',
                                     '--header', str(directory / 'out.h'), '--impl', str(directory / 'out.cpp')],
                                    env=clean_env() | {'MACHINE': 'MT6762'}, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'fallback is forbidden', result.stderr)
            self.assertEqual(list(directory.iterdir()), [])

    def test_xcrun_cannot_fallback_iig_but_selects_host_tool(self):
        env = shell_environment({'MACHINE': 'MT6762'})
        command = [str(ROOT / 'xnu-deps/host/bin/xcrun'), '-sdk', 'iphoneos', '-find']
        result = subprocess.run(command + ['iig'], env=env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'')
        result = subprocess.run(command + ['migcom'], env=env, check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), env['MTK_HOST_TOOLS'] + '/migcom')

    def test_replay_selection_rejects_old_tree_and_unpinned_inputs(self):
        env = shell_environment({'MACHINE': 'MT6762'})
        env.update(IIG=str(KERNEL / 'tools/mt6762/iig/experimental_legacy_replay.py'),
                   MTK_IIG_XNU=str(KERNEL), MTK_IIG_OUTPUT_ROOT=str(KERNEL / 'BUILD'),
                   MTK_IIG_INPUTS='/inputs', MTK_IIG_GENERATED='/generated',
                   MTK_IIG_INPUT_SHA256='1' * 64, MTK_IIG_GENERATION_SHA256='2' * 64,
                   MTK_IIG_CANDIDATE='/candidate', MTK_IIG_CANDIDATE_SHA256='3' * 64)
        # Only mock the generator verification; selection is the actual code.
        with patch.dict(os.environ, env, clear=True), patch.object(profile.subprocess, 'run') as verify:
            profile.check_iig()
            verify.assert_called_once_with([env['IIG'], 'verify'], check=True)
        for override in ({'XNU_SRC': str(ROOT.parent / 'xnu')},
                         {'MTK_IIG_XNU': str(ROOT.parent / 'xnu')},
                         {'MTK_IIG_OUTPUT_ROOT': str(ROOT.parent / 'xnu/BUILD')},
                         {'IIG': str(ROOT / 'xnu-deps/host/bin/iig')},
                         {'MTK_IIG_INPUT_SHA256': ''}, {'MTK_IIG_CANDIDATE_SHA256': ''}):
            with self.subTest(override=override), patch.dict(os.environ, env | override, clear=True), \
                    patch.object(profile.subprocess, 'run') as verify:
                with self.assertRaises(ValueError):
                    profile.check_iig()
                verify.assert_not_called()

    def test_actual_make_wrapper_mtk_overrides_and_other_board_defaults(self):
        with tempfile.TemporaryDirectory(prefix='mtk-make-selection-') as name:
            directory = Path(name)
            for script in ('xnu-env.sh', 'xnu-build.sh'):
                p = directory / script
                p.write_bytes((ROOT / script).read_bytes()); p.chmod(0o755)
            binary = directory / 'bin'; binary.mkdir()
            (binary / 'python3').write_text('#!/bin/sh\n# Admission mocked only in this make-argument fixture.\nexit 0\n')
            (binary / 'make').write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            for p in binary.iterdir(): p.chmod(0o755)
            kernel = directory / 'kernel'; kernel.mkdir()
            obj = directory / 'xnu-deps/build/ath11k/out/ath11k.o'
            obj.parent.mkdir(parents=True); obj.write_bytes(b'Qualcomm fixture only')
            env = clean_env() | {'PATH': str(binary) + ':' + os.environ['PATH'],
                'XNU_SRC': str(kernel), 'MTK_LLVM_BIN': str(binary), 'IIG': '/verified/replay'}
            args = ['HAKIOS_OBJECTS=/injected/qualcomm.o', 'MACHINE_CONFIGS=OTHER', 'CC=/wrong', 'IIG=/wrong']
            result = subprocess.run([str(directory / 'xnu-build.sh'), *args], env=env | {'MACHINE': 'MT6762'},
                                    check=True, capture_output=True, text=True)
            selected = dict(arg.split('=', 1) for arg in json.loads(result.stdout) if '=' in arg)
            self.assertEqual(selected['HAKIOS_OBJECTS'], '')
            self.assertEqual(selected['MACHINE_CONFIGS'], 'MT6762')
            self.assertEqual(selected['IIG'], '/verified/replay')
            self.assertEqual(selected['CC'], str(directory / 'xnu-deps/host/bin/xnu-clang'))
            result = subprocess.run([str(directory / 'xnu-build.sh')], env=env,
                                    check=True, capture_output=True, text=True)
            selected = dict(arg.split('=', 1) for arg in json.loads(result.stdout) if '=' in arg)
            self.assertEqual(selected['HAKIOS_OBJECTS'], str(obj))
            self.assertEqual(selected['MACHINE_CONFIGS'], 'BCM2837')
            self.assertEqual(selected['CC'], 'xnu-clang')
            self.assertFalse((kernel / 'BUILD').exists())

    def test_actual_fresh_build_marker_rejects_changed_profile(self):
        source = (KERNEL / 'tools/mt6762/build.sh').read_text()
        code = source.split("<<'PYPROFILE'\n", 1)[1].split('\nPYPROFILE', 1)[0]
        with tempfile.TemporaryDirectory(prefix='mtk-build-markers-') as name:
            directory = Path(name)
            build = directory / 'BUILD'
            iig = directory / 'iig.json'; iig.write_text('{"iig":1}')
            inputs = directory / 'inputs.json'; inputs.write_text('{"compiler":1}')
            args = ['python3', '-c', code, str(build), str(iig), str(inputs)]
            subprocess.run(args, check=True, capture_output=True)
            subprocess.run(args, check=True, capture_output=True)
            original = (build / '.mt6762-build-inputs.json').read_bytes()
            inputs.write_text('{"compiler":2}')
            result = subprocess.run(args, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((build / '.mt6762-build-inputs.json').read_bytes(), original)
            for p in build.iterdir(): p.unlink()
            (build / 'unmarked-object.o').write_bytes(b'preserve')
            result = subprocess.run(args, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((build / 'unmarked-object.o').read_bytes(), b'preserve')
            self.assertEqual(len(list(build.iterdir())), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
