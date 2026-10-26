# MT6762 userland profile

`build-userland.sh` builds the refactored HakiOS helpers around the existing iOS
16.5 **20F66 / iPhone10,3 and iPhone10,6 arm64** extraction. Apple's executables,
frameworks and dyld cache remain binary inputs. The script does not download,
patch or rebuild them, install anything on the phone, or change the system APFS.

Run from the monorepo, with a new output directory:

```sh
devices/mt6762/build-userland.sh \
    /home/iscle/mt6762-ios-port/boot/hakios-userland-build3
```

The output directory must not already exist. Failed outputs are left for
inspection; use another new directory after correcting a failure. Compilation
uses the local LLVM and ld64 toolchain directly, with
`--target=arm64-apple-ios16.5 -mcpu=cortex-a53 -mno-outline-atomics`.
It does not use `prebuilt/userland`, invoke the generic userland builder, or
modify toolchain configuration. Python 3 with Capstone and Unicorn, a host C
compiler, zlib and OpenSSL development libraries are required for verification.

The default workspace is the monorepo's parent. These environment variables can
relocate local inputs; the exact admitted system and root-configuration hashes
are still checked:

| Variable | Default relative to the workspace |
| --- | --- |
| `MTK_WORKSPACE` | Parent of this monorepo |
| `MTK_IOS` | `runtime/ios165` |
| `MTK_SYSTEM_APFS` | `runtime/userland/system.apfs` |
| `MTK_ROOT_TEMPLATE` | `boot/desktop-bootstrap-build2-root/root` |
| `MTK_LLVM_BIN` | Directory containing the resolved `toolchain/bin/clang` |
| `MTK_LD64` | `toolchain/theos/toolchain/linux/iphone/bin/ld` |
| `MTK_IOS_SDK` | `toolchain/theos/sdks/iPhoneOS16.5.sdk` |

The root template is a bounded compatibility input: only its 403 Apple job
definitions, eight preference files, `etc/var.skel`, and `share/pattern.bin` are
copied. Their aggregate SHA-256 is
`45d3f861cd0ab4e46e4361eba147c1801978bebc088f72b8a114cc44d7753f60`.
No old project program, library, service, firmware, or key is inherited.
Changing this baseline intentionally requires reviewing and updating the
profile. The script reads the extracted `SystemVersion.plist` and verifies
20F66, then verifies the Apple `launchd` inside the admitted system image against
the extracted Apple executable.

## Boot contract

This image is for the migrated MT6762 kernel and its native eMMC slice, including
the QEMU model of that path. The small APFS volume is named **`redwood`**, and
the existing `/redwood` filesystem prefix stays intact:

1. Boot with this small APFS as the initial root and `rd=md0`.
2. Its freshly compiled `/sbin/launchd` is the MT6762 bootstrap. It mounts the
   read-only `/dev/mtkios0` at `/newroot`.
3. It calls `kern.hakios_switch_root` with `/newroot redwood`, moving the helper
   root under the system's `/redwood`, then execs `/redwood/sbin/init`.
4. The new HakiOS `init` sets up its memory-backed writable directories and
   injection configuration, then execs the unchanged Apple `/sbin/launchd.ios`.

The unchanged system image is **2,491,162,624 bytes**, SHA-256:

```text
9329e9c9bf46d6890798bb15d0d0036ec8c9235abf7d77edbacdd346992454a0
```

It is the existing image installed in the MT6762 iOS slice. This profile does
not produce another system image. The old project `stage0` still present at that
image's `/sbin/launchd` is not executed by this boot sequence. The generic
upstream `stage0`, which mounts `/dev/md1`, is not interchangeable with the
MT6762 bootstrap. A generic RAM-only boot needs a separate image/entry recipe.

Do not mix this root with an old kernel exposing `kern.redwood` or
`/dev/redwood-touch`. The new helpers use `/dev/hakios-touch`, `kern.hakios`,
`libhakios*.dylib`, and `com.hakios.demo`. Input record definitions are checked
against the migrated kernel header before building. There is no renaming of
Apple jobs, filesystem prefix, or Apple bundle identifiers.

## Contents and policy

The new source builds `init`, `child`, the MT6762 bootstrap, `hello_dyn`,
`svc_test`, `surf_test`, `rwtouch`, the read-only MT6762 `battery_probe`, and the
five HakiOS injection libraries for backboardd/container managers, SpringBoard,
mediaserverd, Sileo and Preferences. The existing software CoreAnimation path
is used; no Mesa/Adreno library or hardware GPU grant is introduced.

`com.hakios.demo` runs only twelve read-only battery-publication samples one
second apart. These numbers are a count and interval, not a requested battery
percentage. The actual new SpringBoard battery functions are host-tested with
unknown SOC and with an existing power-source service: they preserve unknown
readings and defer to Apple's power-source path. Nothing supplies a synthetic
100% battery, measured current, absolute gauge calibration, or charging grant.

The old project `varstore`, Wi-Fi and thermal-notification jobs are omitted.
There is no MT6762 data-persistence partition profile or radio configuration in
this image, and the new upstream source has no corresponding thermal helper.
Omitting that userland notification daemon does not change the native kernel's
thermal policy. Writable user data remains memory-backed for this trial.

## Outputs and checks

| Output | Purpose |
| --- | --- |
| `root.apfs` | New 4 MiB helper APFS for the physical-style boot path |
| `root/` | Exact staged filesystem for review |
| `userland-evidence.json` | Input/output hashes, compiler commands, system identity, checks and limitations |
| `bootstrap-entry-test.json` | Actual Mach-O startup executed through the first console syscall with 18 initial SP cases |
| `root-census.txt` | Full readback by the migrated kernel APFS code compiled as a host reader |
| `source/`, `obj/` | Private source copies and build/test artifacts |

The profile rejects stale runtime namespaces, arm64e Mach-O targets, missing
injection libraries, unexpected system/configuration inputs, source changes
during the build, and readback differences. The native APFS census compares
every path, type, owner, mode, length and content hash with the staged tree;
external `apfsck` is not invoked and no package is fetched for it.

The Cortex-A53 compiler target is supplemented by a disassembly check for
post-ARMv8.0 atomics, pointer-authentication operations, and several newer
instruction families. This blacklist is not a complete CPU emulator. LLVM's
`__builtin_return_address` emits three `XPACLRI` encodings in `libhakios.dylib`
and one in `libhakios.media.dylib`;
the exact `d50320ff` HINT encoding is recorded and admitted because its System
decode is NOP without FEAT_PAuth. XPACI/XPACD are different encodings and stay
rejected. See [Arm's architecture reference, XPAC System decode, p. 1078](https://documentation-service.arm.com/static/67e40f3398aa3c3b6eea6a85).

Validated local build:

```text
/home/iscle/mt6762-ios-port/boot/hakios-userland-build2/root.apfs
size:   4194304
sha256: f461deda77d2ea9bd58bf548af62fbf9d1f377a90cad2930d72fe1e7e0632723
```

This build passed the native APFS census, 18 bootstrap alignment cases, new
touch-header ABI comparison, actual battery-hook unknown-value test, namespace
and instruction scan, and unchanged system/source checks. The new helper image
has not been booted on the phone. A matching migrated kernel build and the
physical-style QEMU trial remain necessary before claiming desktop behavior.
