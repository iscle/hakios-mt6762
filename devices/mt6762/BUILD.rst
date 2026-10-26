MT6762 kernel build in the HakiOS monorepo
========================================

Use the nested merged source, never the frozen ``../xnu`` checkout. The board
entry is ``devices/mt6762/build-kernel.sh``. Other boards retain the upstream
default settings. This entry selects MACHINE=MT6762, Cortex-A53, the existing
Linux LLVM/cctools installation and a separate writable MTK SDK overlay. It
does not select Qualcomm firmware objects or invoke phone tools.

Prepare reusable dependencies once (no kernel build or downloads)::

  xnu-src/xnu-8796.121.2/tools/mt6762/bootstrap.sh --check
  xnu-src/xnu-8796.121.2/tools/mt6762/bootstrap.sh

The profile defaults to ``../toolchain/theos`` and individual tools/sources in
``../toolchain/hackios-build/xnu-deps``. MTK_WORKSPACE, MTK_LLVM_BIN,
MTK_HOST_TOOLS, MTK_REUSE_DEPS and THEOS can explicitly select existing paths.
No old kernel sources, generated DriverKit pairs or static archives are copied.
The pinned libdispatch/libpthread/AvailabilityVersions revisions and SDK are
verified, and tracked modifications are rejected. The actual selected input
files and tool bytes are recorded for each build.

After genuine IIG generation/review for this merged tree, source its pinned
environment bundle, then validate and build::

  source /path/to/reviewed-iig-environment.sh
  devices/mt6762/build-kernel.sh --check
  devices/mt6762/build-kernel.sh

IIG must point to this kernel's ``replay.py`` or
``experimental_legacy_replay.py`` with all required pinned MTK_IIG_* settings.
Validation runs before BUILD is changed and again through dependency header
export and final make. The SDK-header/empty-implementation fallback is refused
for MT6762. The experimental consumer remains explicitly experimental; genuine
Xcode output and the reviewed compatibility transform are separate inputs.

Build records include kernel-source, IIG, monorepo script, dependency-source,
SDK and host-tool fingerprints before and after the build. Changing IIG or
tool/profile inputs requires preserving the old BUILD and starting a fresh
one; an unmarked existing BUILD is never adopted. Source changes during the
build reject its artifact. Existing artifacts are preserved in the build log
directory before a new link. Known donor post-link export failures are reported
separately and never called a fully passing build.

The bootstrap writes only new-tree host-tool links and
``xnu-deps/sdk/iPhoneOS16.5.mt6762.sdk``. Dependencies are rebuilt against the
newly exported headers with ARM64_BOARD_CONFIG_MT6762. This does not rebuild
the Apple userspace.

Offline checks (no make or hardware)::

  python3 devices/mt6762/test_build_profile.py

The tests execute actual compiler/xcrun/IIG wrapper selection and BUILD-marker
logic using temporary fixtures. Generator verification is mocked only in the
path-selection unit test; a real ``--check`` separately validates the selected
genuine generated bundle. No full kernel build is run by these tests.
