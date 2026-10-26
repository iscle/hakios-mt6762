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

The paired kernel56/helper-build2 booted through the migrated HakiOS interfaces
into Apple's launchd. The initial 180-second smoke reached SpringBoard startup
but no frame submission; it remains recorded separately in
[qemu-build56-smoke.json](qemu-build56-smoke.json).

The subsequent **eight-core, 600-second QEMU trial reached a visible SpringBoard
home screen**, with app icons and the dock. Retained markers show valid frame
submissions, text-console release and completed pixel copies. All seven secondary
cores were online, no kernel panic or terminal storage error was observed, and
the original system image and helper root were unchanged. See
[qemu-build56-smp8-long.json](qemu-build56-smp8-long.json).

Graphics remain incomplete: the final image has a magenta wallpaper with artifacts
and blank widget tiles. The donor helper requested automatic unlock; no synthetic
touch or power input was injected, so this run does not prove touch-driven
unlocking. It validates software rendering and presentation in the custom QEMU
machine, not physical display behavior or GPU acceleration.

Reproduce the eight-core trial with explicit matching artifacts and a fresh output:

```sh
devices/mt6762/run-qemu.sh \
    --kernel "$MTK_WORKSPACE/boot/native-desktop-build56/kernel.macho" \
    --kernel-build-report "$MTK_WORKSPACE/boot/native-desktop-build56/build.json" \
    --userland "$MTK_WORKSPACE/boot/hakios-userland-build2" \
    --out "$MTK_WORKSPACE/boot/new-hakios-qemu-trial" --cpus 8 --seconds 600
```

The default is an eight-core, 120-second bootstrap smoke; it does not promise a
visible desktop. Use `--prepare-only` to create the experiment without launching
QEMU. The runner uses the custom MT6762 machine and a private read-only eMMC
fixture. These synthetic peripheral results do not establish physical operation.

Physical Image45/kernel57/helper6 reaches the graphical interface: the user
observed Control Center, captured touch routing includes several open apps,
and SpringBoard reported completed startup. All eight cores have been observed
online. The final capture40 framebuffer shows the shutdown spinner because the
Power-button restart happened before collection; it is not a Home-screen
screenshot. See [physical-build45-capture40.json](physical-build45-capture40.json).

Bulk eMMC reads and the factory Wi-Fi identity handoff resolved two separate
startup delays. The physical window server now becomes ready at about63seconds,
down from280seconds; this is not the time to a finished Home screen. LaunchServices
still rebuilds its databases in the fresh RAM-backed data volume. See
[BOOT-PERFORMANCE.rst](BOOT-PERFORMANCE.rst).

Bottom-edge navigation now has a tested policy correction: the missing
`/buttons/home-button-type` made iOS assume a physical Home key. Setting it to2
selects gesture navigation. Three matching D22 artwork traits also let UIKit
resolve its existing bounding-path asset; the asset itself was already present.
An earlier candidate with only HomeButtonType2 was rejected before installation.

Native QEMU touch tests now show app-to-Home navigation, the app switcher and
top-right Control Center. Some swipe paths remain inconsistent and one leaves
partially rendered Clock content. See [qemu-build57-gestures.json](qemu-build57-gestures.json).
Image47 carries the four UI properties with the same kernel57/helper6. It is
installed and fully readback verified; physical gesture validation is pending.
See [physical-build47-trial.json](physical-build47-trial.json).

The phone has 6 GiB of DRAM; the current admitted VM range is about 3838 MiB.
Full RAM reclamation, coordinated performance/voltage control, complete charging
and fuel-gauge policy remain open work. The inherited charger state is not
evidence of a complete charging implementation. Existing physical input
observations cover touch and all three power/volume buttons.

Native Wi-Fi integration targets the stock CONSYS_6765/CONNAC soc1_0 AXI-DMA
driver and per-phone firmware/calibration. The factory MAC property supplies
identity only; no scan, association or Wi-Fi traffic is established yet.
The existing HakiOS station/network interface can be reused above a new
MediaTek connectivity backend.

The profile scripts build local artifacts and run emulator trials. They do not
flash the phone. Image47/kernel57/helper6 is installed with a verified
full boot-partition readback. The physical trials use a separate guarded
installer and retained-log reader with manual Power-button restarts.
