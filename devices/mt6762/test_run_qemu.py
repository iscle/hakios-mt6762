#!/usr/bin/env python3
"""No QEMU launch: test image isolation and smoke/admission failure semantics."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('run_qemu',HERE/'run_qemu.py')
run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)

class RunTests(unittest.TestCase):
 def test_readonly_slice_bytes_and_existing_output_refusal(self):
  with tempfile.TemporaryDirectory() as temporary:
   directory=Path(temporary);source=directory/'system';fixture=directory/'emmc'
   data=bytes(range(256))*4;source.write_bytes(data)
   self.assertEqual(run.copy_slice(source,fixture,8,2),run.sha(source))
   result=fixture.read_bytes()
   self.assertEqual(len(result),10*512)
   self.assertEqual(result[:8*512],bytes(8*512))
   self.assertEqual(result[8*512:],data)
   self.assertEqual(source.read_bytes(),data)
   with self.assertRaises(FileExistsError):run.copy_slice(source,fixture,8,2)
   with self.assertRaises(ValueError):run.copy_slice(source,directory/'bad',8,3)
   self.assertFalse((directory/'bad').exists())
 def test_kernel_rejects_frozen_old_tree_tampering_and_unstable_inputs(self):
  with tempfile.TemporaryDirectory() as temporary:
   directory=Path(temporary);kernel=directory/'kernel';report=directory/'result.json'
   kernel.write_bytes(b'fixed-test-kernel')
   record=dict(artifact_ready=True,new_link_observed=True,source_unchanged_during_build=True,
    build_inputs_unchanged_during_build=True,iig_inputs_unchanged_during_build=True,
    macho_arm64_executable=True,build_monorepo=str(run.REPO),sha256=run.sha(kernel))
   report.write_text(json.dumps(record));run.validate_kernel(kernel,report)
   for key,value in [('build_monorepo','/old/xnu'),('sha256','0'*64),
                     ('artifact_ready',False),('source_unchanged_during_build',False),
                     ('iig_inputs_unchanged_during_build',False)]:
    report.write_text(json.dumps({**record,key:value}))
    with self.subTest(key=key),self.assertRaises(ValueError):run.validate_kernel(kernel,report)
 def test_old_userland_profile_and_tampered_root_refused(self):
  with tempfile.TemporaryDirectory() as temporary:
   directory=Path(temporary);root=directory/'root.apfs';root.write_bytes(b'root')
   report=directory/'userland-evidence.json'
   report.write_text(json.dumps({'profile':'redwood','result':'PASS'}))
   with self.assertRaisesRegex(ValueError,'migrated'):run.validate_userland(directory)
   good=dict(profile=run.PROFILE,result='PASS',source_inputs_stable=True,system_rebuilt=False,
    apple_binaries_modified=False,namespace='kern.hakios',touch_device='/dev/hakios-touch',
    root_apfs=str(root),root_sha256='0'*64,root_bytes=4)
   report.write_text(json.dumps(good))
   with self.assertRaisesRegex(ValueError,'root changed'):run.validate_userland(directory)
 def test_smoke_requires_all_cpus_bootstrap_and_no_terminal_error(self):
  log='\n'.join(['MT6762_DESKTOP bootstrap ready','MT6762_DESKTOP system_mounted result=0',
    'MT6762_DESKTOP system root active; starting existing init',
    '=== init: process 1, started as /redwood/sbin/init ===',
    *[f'arm_cpu_init(): cpu {n} online' for n in range(1,8)]])
  models={'run_completed':True}
  self.assertTrue(run.check_smoke(log,models,8)['passed'])
  self.assertFalse(run.check_smoke(log.replace('cpu 7 online','cpu 9 online'),models,8)['passed'])
  self.assertFalse(run.check_smoke(log+'\npanic(cpu 0)',models,8)['passed'])
  self.assertFalse(run.check_smoke(log,{'run_completed':False},8)['passed'])
  self.assertFalse(run.check_smoke(log,{**models,'terminal_storage_failure_observed':True},8)['passed'])
  self.assertFalse(run.check_smoke(log.replace('system_mounted result=0','system_mounted result=5'),models,8)['passed'])
  self.assertFalse(run.check_smoke(log,models,8)['desktop_proven'])
if __name__=='__main__':unittest.main()
