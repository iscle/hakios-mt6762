Physical startup investigation, captures37 through39
===================================================

Capture38 measures the bulk-read fix on the phone: window-server readiness is
62.674 seconds, versus 279.715 seconds in capture37. All eight physical cores
start. Active transport throughput is 10.632 MiB/s (549,228,544 bytes over
49.266 seconds), versus 1.529 MiB/s before. No storage admission error is
recorded. After its 60-second transport sample, the controller spends only
0.36% of the remaining measured interval reading. This is an observed physical
before/after with different observer helpers, not a controlled benchmark.

The remaining wait is now sampled directly. SpringBoard's main thread remains
at the same LaunchServices lock from uptime73.989 to354.235 seconds, with
unchanged CPU times. Its owner is thread476, Mach port0x200b, waiting for a
synchronous XPC reply. In lsd, thread718 waits inside MobileGestalt at all three
worker samples (75.025,135.074,195.095 seconds). The exact20F66 cache resolves
this to ``WifiAddressData``: ``/chosen/mac-address-wifi0`` is missing, so it
falls back to IONetworkController matching. The outer semaphore has no deadline.
The notification worker uses repeated five-second runloop calls; the reason
those did not complete the fallback is not yet established.

The physical image producer deliberately stripped lab MAC/chip identities,
but had not replaced the Wi-Fi property with this phone's factory value.
QEMU retains its synthetic property and progresses past this query. The
targeted correction accepts six raw factory MAC bytes as an explicit build
input, validates them, and publishes OSData in the physical device tree.
The existing factory dump provides the address in nvdata's
``/APCFG/APRDEB/WIFI`` at offset4, matching the MediaTek BSP structure.
This grants no network hardware access and does not establish a Wi-Fi driver.
The raw factory address stays outside the public source/evidence repository.
Removing only the Wi-Fi property in a separate360-second QEMU experiment
reproduces all ten image-relative frames of both the physical waiter and its
runloop worker. The positive reference has neither matching stack.

Capture39 verifies Image45 execution with the factory Wi-Fi property. Its lsd
worker is running, with no MobileGestalt frame in the sampled threads. Its
read totals rise from5.23 to18.30 to31.65 MB across the first three samples,
matching active app enumeration rather than the previous identity wait.
The log ends at130.660 seconds after an early restart. Both captures38 and39
contain the Apple logo in the framebuffer, not home; panel visibility at the
capture instant is unconfirmed. A full-duration retry of the same image is
required to determine whether SpringBoard finishes startup.

Original baseline
-----------------

Image43/kernel56/helper2 starts all eight physical cores. Its retained log
reports window-server readiness at 279.715 seconds and the SpringBoard shell
connection at 284.542 seconds. The text console is released and the display
driver copies drawable layers. The recovered framebuffer contains a white
Apple logo on black. This establishes rendered memory contents; visibility on
the physical panel at that late point was not independently confirmed.

Cold storage is the measured early bottleneck. During the first 270.004 seconds,
417,271,296 bytes were read, taking 260.312 seconds inside the serialized
transport: 96.4% of elapsed time and 1.529 MiB/s of active-read throughput.
The inherited controller runs at approximately 48 MHz, but the original BSD
adapter splits a 128 KiB APFS request into 256 single-sector commands, each
with card-state and admission checks. Eight online cores cannot parallelize
that one-controller request path. These measurements do not establish maximum
CPU frequency or sustained utilization.

There is also an unresolved later wait. SpringBoard's last recorded main-thread
message is at 287.231 seconds. Storage activity drops sharply after roughly
360 seconds, yet the captured UI has not reached home by about 797 seconds.
The successful kernel56 emulator run pauses at the same SpringBoard milestone
for approximately 241 seconds, then proceeds. Subsequent emulator samples locate
that wait in LaunchServices. Capture38 supplies the physical stack above.

Implemented and tested
----------------------

The new native transport batches up to 256 sectors using CMD13, CMD23, CMD18,
CMD13. It preserves the inherited clocks, tuning and read-only media policy.
A bounded 128 KiB bounce buffer keeps failed reads from publishing partial
output. The local QEMU experiment models this same command sequence and checks
actual bytes, final completion, range errors and terminal faults. Neither
model throughput nor host protocol tests establish physical performance.

Kernel57 passes its full build and 205 runtime IIG checks with all eight cores.
In a 600-second emulator run, the graphics server starts at 44.570 seconds,
versus 214.634 seconds for kernel56 with the same observer/helper4. SpringBoard
reports startup finished at 290.915 seconds, versus 600.020 seconds. The final
frame shows home icons, dock and wallpaper; widget tiles remain blank. The
model completes 31,830 CMD23/CMD18 reads with exact backing-image bytes and no
backend errors or rejected commands. The original system/helper/fixture remain
unchanged. These overlapping host runs are mechanism checks, not a controlled
physical benchmark; the model's 50-microsecond command delay is synthetic.

``bootdiag.c`` is linked only into MT6762 project libraries for SpringBoard and
lsd. It observes its own main thread every 20 seconds for at most 32 samples,
recording run state, CPU time, PC/LR and a bounded frame-pointer walk through
the read-only VM API. It never explicitly suspends the thread. Register and
stack observations are non-atomic and may differ when the thread is running.
At three sample points it also records up to 32 other threads in its own task.
The SpringBoard worker reads ``kern.apfs_stats`` without resetting counters.
No Apple executable or library is rebuilt or modified by this diagnostic.

Helper6 additionally reads the eight-byte LaunchServices session lock, guarded
by the exact 20F66 shared-cache UUID and mapped address bounds. The 200-second
emulator trial matches the reconstructed owner port to a SpringBoard worker
waiting in synchronous XPC. At the same time, an lsd worker is in
``getattrlistbulk`` through ``TraverseDirectoryWithPostTraversal``. This supports
database/content enumeration as the downstream wait, rather than an absent lsd
service. The kernel56 and kernel57 trials eventually leave this wait.

The current project init creates a fresh ramfs at ``/private/var`` on each boot.
Its normal MT6762 profile does not restore a persistent variable-data store.
Application database and cache regeneration therefore repeats. The donor's
flash-specific ``var_store`` path has not been enabled for this device.

Evidence
--------

``physical-build43-capture37.json`` binds the physical observations and source
log hash. ``qemu-build56-smp8-long.json`` records the previous emulator desktop
success. ``qemu-build57-bulk.json`` binds the new emulator comparison and observer
trial. The private binary analysis is under
``hardware/hakios-migration-20261026/launchservices-wait``. Bulk-PIO host evidence
lives in the nested kernel's
``tools/mt6762/hardware/storage/bulk-pio-evidence.json``.
``physical-build44-capture38.json`` binds the physical storage improvement and
remaining MobileGestalt wait. Exact binary analysis is retained privately in
``hardware/hakios-migration-20261026/mobilegestalt-wait38``.
``qemu-no-wifi-identity.json`` records the one-property reproduction;
``physical-build45-capture39.json`` records physical progress after correction.
A full-duration physical trial remains necessary before claiming home.
