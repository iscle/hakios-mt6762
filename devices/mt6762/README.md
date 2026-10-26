# MT6762 port

This profile uses HakiOS commit `88513176b1e96ecf0b764cd62c6f4e6ac71345e3`
from `oosexgang/hackios-xnu-kernel` as its base. It keeps Apple's XNU
`xnu-8796.121.2` and the existing precompiled iPhone10,3/D22 iOS 16.5 build
20F66 userspace. No Apple userspace source build is required or performed.

`xnu.patch` contains our board delta against the exact upstream kernel tree;
`kernel-source.json` pins the upstream, Apple and resulting source identities.
The shared `xnu/hakios.patch` and `xnu/files` remain the upstream version.
The active kernel branch is `mt6762-hakios` in the Apple-derived
[XNU fork](https://github.com/iscle/xnu-mt6762). The previous stable base and
unfinished gauge/SSPM work are preserved separately; they are not silently
included in this migration.

## Rebuild

From this repository, create a new kernel checkout (the command refuses to
replace an existing directory):

```sh
devices/mt6762/apply-kernel.sh
```

The profile retains Cortex-A53 compiler settings, disables unsupported PAN,
and uses 16 KiB VM pages backed by 4 KiB hardware page tables. Genuine DriverKit
IIG outputs must be generated for this checkout's headers and explicitly pinned
before building. The MT6762 path rejects the generic placeholder generator.
See `xnu-src/xnu-8796.121.2/tools/mt6762/build-audit/iig/README.rst` and
`tools/mt6762/iig/LEGACY-CANDIDATE.rst` inside that checkout for generation and
the reviewed Xcode 26 / IIG440 compatibility path.

```sh
export MTK_WORKSPACE=/absolute/path/to/mt6762-ios-port
source "$MTK_WORKSPACE/toolchain/iig-legacy-build56.env"
xnu-src/xnu-8796.121.2/tools/mt6762/bootstrap.sh
devices/mt6762/build-kernel.sh
devices/mt6762/build-userland.sh "$MTK_WORKSPACE/boot/hakios-userland-build1"
```

The existing Linux toolchain, SDK and extracted IPSW are local inputs. The
example IIG environment is specific to this workspace: a different checkout
needs its own paths, source verification and generation manifests. Keep build
outputs outside tracked source. `build-userland.sh` requires a fresh output
directory and rebuilds project-owned helpers for A53; it retains Apple's
system image unchanged. See [USERLAND.md](USERLAND.md) for its input contract.

The new interfaces are `/dev/hakios-*`, `kern.hakios*`, `libhakios*` and
`com.hakios.*`. The upstream filesystem prefix remains `/redwood`. Pair the
new kernel with the newly built helper root; the previous project's helper
binaries use the old interfaces.

After changing and committing the nested kernel, regenerate this profile with
`devices/mt6762/export-kernel.sh`. It exports only the difference from the pinned
upstream tree. `apply-kernel.sh` verifies both input and output tree identities.

## Validation and remaining work

Kernel56 compiled and linked with all build checks passing. A fresh application
of the exported board delta reproduced the exact source tree. Migration host
checks passed for native input, display/brightness, PMIC/power, clocks, storage,
image construction and genuine IIG compatibility. The 8-core QEMU test passed
all 205 generated DriverKit checks. See [validation-build56.json](validation-build56.json).

The paired kernel56/helper-build2 desktop smoke booted through the new HakiOS
interfaces into Apple's launchd and started SpringBoard. That 180-second run
did not reach frame submission or a visible desktop. Its result is recorded in
[qemu-build56-smoke.json](qemu-build56-smoke.json). Reproduce a bounded trial
with the explicit matching artifacts:

```sh
devices/mt6762/run-qemu.sh \
    --kernel "$MTK_WORKSPACE/boot/native-desktop-build56/kernel.macho" \
    --kernel-build-report "$MTK_WORKSPACE/boot/native-desktop-build56/build.json" \
    --userland "$MTK_WORKSPACE/boot/hakios-userland-build2" \
    --out "$MTK_WORKSPACE/boot/new-hakios-qemu-trial" --cpus 2 --seconds 180
```

Use `--prepare-only` to create the experiment without launching QEMU. The
runner uses the custom MT6762 machine and a private read-only eMMC fixture.
These synthetic peripheral results do not establish physical operation.

The last physical capture on the previous base (Image41/kernel54, capture36)
reached “window server ready”, connected SpringBoard's system shell and delivered
native touch events to Apple backboardd, without a recorded terminal storage
failure. The recovered framebuffer still showed console text. This migration
fixes the MT6762 first-frame console release and adds bounded retained display
diagnostics; it has not yet established a visible physical desktop.

The phone has 6 GiB of DRAM; the current admitted VM range is about 3838 MiB.
Two physical CPU cores have been observed online. Full RAM reclamation, all
physical cores, coordinated performance/voltage control, complete charging and
fuel-gauge policy remain open work. The inherited charger state is not evidence
of a complete charging implementation. Existing physical input observations
cover touch and all three power/volume buttons.

The profile scripts build local artifacts and run emulator trials. They do not
flash the phone. The currently installed image remains the previous base until
a separately prepared device trial.
