Physical startup investigation, capture37
=========================================

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
that wait in LaunchServices; the physical wait still needs its own stack.

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
``tools/mt6762/hardware/storage/bulk-pio-evidence.json``. A new physical trial
and its retained logs are required before claiming a boot-time improvement
or a working home screen on this phone.
