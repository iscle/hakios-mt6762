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
source "$MTK_WORKSPACE/toolchain/iig-legacy-build57.env"
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
installed and fully readback verified. Capture44 now contains a visible physical
Home screen with icons, dock, wallpaper and widgets; the user reports working
touch, and retained events reach apps and system gestures. This does not yet
validate every bottom-edge gesture path.
See [physical-build47-capture44.json](physical-build47-capture44.json).
See [physical-build47-trial.json](physical-build47-trial.json).

The phone has 6 GiB of DRAM; the current admitted VM range is about 3838 MiB.
Full RAM reclamation, coordinated performance/voltage control, complete charging
and fuel-gauge policy remain open work. Capture44 finds no published battery service and no valid gauge measurements,
explaining the empty icon. The PSC charger reports charging (status0x10), but
this is not a current measurement or a complete native charging policy. Existing physical input
observations cover touch and all three power/volume buttons.

Native Wi-Fi integration targets the stock CONSYS_6765/CONNAC soc1_0 AXI-DMA
driver and per-phone firmware/calibration. The factory MAC property supplies
identity only; no scan, association or Wi-Fi traffic is established yet.
The existing HakiOS station/network interface can be reused above a new
MediaTek connectivity backend.

The profile scripts build local artifacts and run emulator trials. They do not
flash the phone. Image50/kernel58/helper6 is now installed with a verified
full boot-partition readback; physical execution is pending. The physical trials use a separate guarded
installer and retained-log reader with manual Power-button restarts.

The native connectivity work now includes stock firmware/calibration parsers,
WMT/STP framing and a bounded BTIF PIO query transport, a reset-held CONN power
core, and a live-FDT memory planner. Host tests pass; these components have not
yet brought up the physical radio. Image49 is staged with a read-only
connectivity survey and the D22 `thin-bezel` property, but is not installed.
Image50 supersedes that staged candidate. Kernel58 adds a recurring native
battery observer and optional coherent current/Coulomb samples. Charger
control and remaining percentage are still unavailable. The180-second QEMU
boot and host suites pass; see [validation-build58.json](validation-build58.json)
and [physical-build50-trial.json](physical-build50-trial.json).

Kernel59 adds a narrowly scoped fresh-voltage observer. Its loader validates
the live battery ADC route and records clock/reset/test/data-reuse settings;
the consumer permits one channel1 request and rejects stale results. The
stock preloader enables a data-reuse bit whose channel1 interaction remains
unproven, so the new path may refuse voltage sampling while retaining its
diagnostics. The build, host fault tests and180-second eight-core QEMU smoke
pass. Image51/normal42 is packaged and **not installed**; Image50 remains
installed awaiting its first physical test. See
[validation-build59.json](validation-build59.json) and
[physical-build51-trial.json](physical-build51-trial.json).

The source also contains a separately tested conditional SOC model and
reset-held BT/Wi-Fi/MCU firmware staging core. Neither is integrated into
physical operation. Percentage, complete charging policy and active Wi-Fi
remain unfinished; emulator results do not establish those capabilities.
