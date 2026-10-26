/* Bounded observation of SpringBoard/lsd startup, only in the MT6762 build.
 * Reads its own threads without explicitly suspending them or changing Apple code.
 * Samples are not atomic backtraces: registers/stack may move between reads.
 */
#include <dlfcn.h>
#include <errno.h>
#include <mach/mach.h>
#include <mach/mach_time.h>
#include <mach/arm/thread_status.h>
#include <pthread.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <time.h>
#include <unistd.h>

static mach_port_t startup_thread;
static uint64_t startup_tid;
static mach_timebase_info_data_t timebase;
static const char *observed_process;
static uintptr_t session_lock;
extern const void *_dyld_get_shared_cache_range(size_t *length);

static void
session_lock_location(void)
{
    /* Only the exact 20F66 arm64 cache reviewed with ipsw is admitted. This
     * address is an observation target, never a lock acquisition or write. */
    const unsigned char expected[16] = {0xe5,0x42,0x0d,0xb3,0x30,0xd0,0x33,0xaa,
        0x8b,0x7e,0x05,0xb5,0x03,0x8b,0xb4,0x6d};
    unsigned char uuid[16] = {0};
    bool (*get_uuid)(unsigned char *) = dlsym(RTLD_DEFAULT, "_dyld_get_shared_cache_uuid");
    size_t length = 0;
    uintptr_t base = (uintptr_t)_dyld_get_shared_cache_range(&length);
    const uintptr_t offset = UINT64_C(0x61ee64b8);
    bool match = get_uuid && get_uuid(uuid) && memcmp(uuid, expected, sizeof(uuid)) == 0;
    if (match && base && base <= UINTPTR_MAX - offset - 8 &&
        length >= 8 && offset <= length - 8) session_lock = base + offset;
    char line[240];
    int n = snprintf(line, sizeof(line),
        "MT6762_BOOT_CACHE proc=%s base=%#llx bytes=%zu uuid20F66=%d session_lock=%#llx readonly=1\n",
        observed_process, (unsigned long long)base, length, match,
        (unsigned long long)session_lock);
    if (n > 0) write(STDERR_FILENO, line, (size_t)n < sizeof(line) ? (size_t)n : sizeof(line)-1);
}

static void
session_lock_sample(unsigned sample)
{
    if (!session_lock) return;
    uint32_t words[2] = {0};
    vm_size_t got = 0;
    kern_return_t result = vm_read_overwrite(mach_task_self(), session_lock,
        sizeof(words), (vm_address_t)(uintptr_t)words, &got);
    uint32_t owner = result == KERN_SUCCESS && got == sizeof(words) &&
        words[0] != 0 && words[0] != UINT32_MAX ? words[0] | 3u : 0;
    char line[240];
    int n = snprintf(line, sizeof(line),
        "MT6762_BOOT_LSLOCK proc=%s sample=%u result=%d bytes=%zu word=%#x recursion=%u owner_port_candidate=%#x non_atomic=1\n",
        observed_process, sample, result, (size_t)got, words[0], words[1], owner);
    if (n > 0) write(STDERR_FILENO, line, (size_t)n < sizeof(line) ? (size_t)n : sizeof(line)-1);
}

static void
filesystem_sample(unsigned sample)
{
    char text[16384];
    size_t size = sizeof(text);
    int result = sysctlbyname("kern.apfs_stats", text, &size, NULL, 0);
    int saved_errno = result ? errno : 0;
    char line[128];
    int n = snprintf(line, sizeof(line),
        "MT6762_APFS_SAMPLE sample=%u result=%d errno=%d bytes=%zu readonly=1\n",
        sample, result, saved_errno, size);
    if (n > 0) write(STDERR_FILENO, line, (size_t)n < sizeof(line) ? (size_t)n : sizeof(line)-1);
    if (!result && size && size <= sizeof(text)) {
        write(STDERR_FILENO, text, strnlen(text, size));
    }
}

static void
address_line(unsigned sample, uint64_t tid, unsigned frame, uintptr_t address)
{
    Dl_info info = {0};
    char line[512];
    const char *image = "?", *symbol = "?";
    if (dladdr((void *)address, &info)) {
        if (info.dli_fname) {
            const char *base = strrchr(info.dli_fname, '/');
            image = base ? base + 1 : info.dli_fname;
        }
        if (info.dli_sname) symbol = info.dli_sname;
    }
    int n = snprintf(line, sizeof(line),
        "MT6762_BOOT_FRAME proc=%s sample=%u tid=%llu frame=%u pc=%#llx image=%s base=%#llx symbol=%s offset=%#llx\n",
        observed_process, sample, (unsigned long long)tid, frame, (unsigned long long)address, image,
        (unsigned long long)(uintptr_t)info.dli_fbase, symbol,
        (unsigned long long)(info.dli_saddr ? address - (uintptr_t)info.dli_saddr : 0));
    if (n > 0) write(STDERR_FILENO, line, (size_t)n < sizeof(line) ? (size_t)n : sizeof(line)-1);
}

static void
sample_thread(mach_port_t thread, unsigned sample, unsigned frames, int main_thread)
{
        thread_identifier_info_data_t identifier = {0};
        mach_msg_type_number_t id_count = THREAD_IDENTIFIER_INFO_COUNT;
        kern_return_t id_result = thread_info(thread, THREAD_IDENTIFIER_INFO,
            (thread_info_t)&identifier, &id_count);
        uint64_t tid = id_result == KERN_SUCCESS ? identifier.thread_id : 0;
        arm_thread_state64_t state = {0};
        mach_msg_type_number_t count = ARM_THREAD_STATE64_COUNT;
        kern_return_t result = thread_get_state(thread, ARM_THREAD_STATE64,
            (thread_state_t)&state, &count);
        thread_basic_info_data_t basic = {0};
        mach_msg_type_number_t basic_count = THREAD_BASIC_INFO_COUNT;
        kern_return_t basic_result = thread_info(thread, THREAD_BASIC_INFO,
            (thread_info_t)&basic, &basic_count);
        uint64_t ticks = mach_absolute_time();
        uint64_t ns = ticks / timebase.denom * timebase.numer +
            ticks % timebase.denom * timebase.numer / timebase.denom;
        char line[640];
        int n = snprintf(line, sizeof(line),
            "MT6762_BOOT_SAMPLE proc=%s pid=%d sample=%u uptime_ms=%llu main=%d tid=%llu port=%#x handle=%#llx id_result=%d state_result=%d info_result=%d run=%d suspend=%d user_us=%llu system_us=%llu pc=%#llx lr=%#llx fp=%#llx non_atomic=1\n",
            observed_process, getpid(), sample, (unsigned long long)(ns / 1000000), main_thread,
            (unsigned long long)tid, thread, (unsigned long long)identifier.thread_handle, id_result,
            result, basic_result, basic.run_state, basic.suspend_count,
            (unsigned long long)basic.user_time.seconds * 1000000 + basic.user_time.microseconds,
            (unsigned long long)basic.system_time.seconds * 1000000 + basic.system_time.microseconds,
            (unsigned long long)arm_thread_state64_get_pc(state),
            (unsigned long long)arm_thread_state64_get_lr(state),
            (unsigned long long)arm_thread_state64_get_fp(state));
        if (n > 0) write(STDERR_FILENO, line, (size_t)n < sizeof(line) ? (size_t)n : sizeof(line)-1);
        if (result != KERN_SUCCESS || count != ARM_THREAD_STATE64_COUNT) return;
        address_line(sample, tid, 0, (uintptr_t)arm_thread_state64_get_pc(state));
        address_line(sample, tid, 1, (uintptr_t)arm_thread_state64_get_lr(state));
        uintptr_t fp = (uintptr_t)arm_thread_state64_get_fp(state);
        uintptr_t sp = (uintptr_t)arm_thread_state64_get_sp(state);
        for (unsigned frame = 2; frame < frames; frame++) {
            if ((fp & 15) || fp < sp || fp - sp > 8 * 1024 * 1024 ||
                fp > UINTPTR_MAX - 16) break;
            uint64_t pair[2] = {0};
            vm_size_t got = 0;
            result = vm_read_overwrite(mach_task_self(), fp, sizeof(pair),
                (vm_address_t)(uintptr_t)pair, &got);
            if (result != KERN_SUCCESS || got != sizeof(pair)) break;
            if (pair[1]) address_line(sample, tid, frame, (uintptr_t)pair[1]);
            if (pair[0] <= fp) break;
            fp = (uintptr_t)pair[0];
        }
}

static void
sample_other_threads(unsigned sample)
{
    thread_act_array_t threads = NULL;
    mach_msg_type_number_t count = 0;
    kern_return_t result = task_threads(mach_task_self(), &threads, &count);
    char line[160];
    int n = snprintf(line, sizeof(line),
        "MT6762_BOOT_THREADS proc=%s sample=%u result=%d count=%u limit=32\n",
        observed_process, sample, result, count);
    if (n > 0) write(STDERR_FILENO, line, (size_t)n < sizeof(line) ? (size_t)n : sizeof(line)-1);
    if (result != KERN_SUCCESS) return;
    mach_port_t me = mach_thread_self();
    for (unsigned i = 0; i < count && i < 32; i++) {
        if (threads[i] != startup_thread && threads[i] != me)
            sample_thread(threads[i], sample, 10, 0);
    }
    for (unsigned i = 0; i < count; i++) mach_port_deallocate(mach_task_self(), threads[i]);
    vm_deallocate(mach_task_self(), (vm_address_t)threads, count * sizeof(*threads));
    mach_port_deallocate(mach_task_self(), me);
}

static void *
sample_startup(void *unused)
{
    (void)unused;
    for (unsigned sample = 0; sample < 32; sample++) {
        struct timespec delay = {20, 0};
        while (nanosleep(&delay, &delay) != 0) {
            if (errno != EINTR) goto finished;
        }
        session_lock_sample(sample);
        sample_thread(startup_thread, sample, 18, 1);
        if (sample == 0 || sample == 3 || sample == 6) sample_other_threads(sample);
        if (strcmp(observed_process, "SpringBoard") == 0) filesystem_sample(sample);
    }
finished:
    mach_port_deallocate(mach_task_self(), startup_thread);
    return NULL;
}

__attribute__((constructor)) static void
observe_startup(void)
{
    observed_process = getprogname();
    if (!observed_process || (strcmp(observed_process, "SpringBoard") != 0 &&
        strcmp(observed_process, "lsd") != 0) || !pthread_main_np()) return;
    if (mach_timebase_info(&timebase) != KERN_SUCCESS || !timebase.denom) return;
    session_lock_location();
    startup_thread = mach_thread_self();
    if (pthread_threadid_np(NULL, &startup_tid) != 0) startup_tid = 0;
    pthread_t worker;
    int result = pthread_create(&worker, NULL, sample_startup, NULL);
    if (result == 0) pthread_detach(worker);
    else mach_port_deallocate(mach_task_self(), startup_thread);
    char line[192];
    int n = snprintf(line, sizeof(line),
        "MT6762_BOOT_DIAG proc=%s start=%d tid=%llu samples=32 interval_s=20 timebase=%u/%u suspend=0\n",
        observed_process, result, (unsigned long long)startup_tid, timebase.numer, timebase.denom);
    if (n > 0) write(STDERR_FILENO, line, (size_t)n < sizeof(line) ? (size_t)n : sizeof(line)-1);
}
