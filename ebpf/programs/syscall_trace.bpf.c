# ebpf/programs/syscall_trace.bpf.c
/*
Extended BPF program for tracing system calls.
Attaches to raw_tracepoint:sys_enter and sys_exit.
Extracts: syscall number, arguments, return value, latency.
*/

#include <uapi/linux/ptrace.h>
#include <linux/sched.h>

struct syscall_event {
    __u32 pid;
    __u32 tid;
    __u32 syscall_nr;
    __u64 ts_enter_ns;
    __u64 ts_exit_ns;
    __u64 latency_ns;
    __s64 ret;
    char comm[16];
};

BPF_RINGBUF_OUTPUT(syscall_events, 256);

struct syscall_latency_key {
    __u32 pid;
    __u32 tid;
    __u32 syscall_nr;
};

BPF_HASH(syscall_times, struct syscall_latency_key, __u64);

struct syscall_count_key {
    __u32 syscall_nr;
};

BPF_HASH(syscall_counts, struct syscall_count_key, __u64);

TRACEPOINT_PROBE(raw_syscalls, sys_enter) {
    __u64 pid_tgid = bpf_get_current_pid_tgid();
    __u32 pid = pid_tgid >> 32;
    __u32 tid = pid_tgid & 0xFFFFFFFF;
    __u32 syscall_nr = args->id;
    __u64 ts_ns = bpf_ktime_get_ns();
    
    struct syscall_latency_key key = {
        .pid = pid,
        .tid = tid,
        .syscall_nr = syscall_nr,
    };
    syscall_times.update(&key, &ts_ns);
    
    struct syscall_count_key count_key = { .syscall_nr = syscall_nr };
    __u64 *count = syscall_counts.lookup_or_init(&count_key, &(__u64){0});
    if (count) __sync_fetch_and_add(count, 1);
    
    return 0;
}

TRACEPOINT_PROBE(raw_syscalls, sys_exit) {
    __u64 pid_tgid = bpf_get_current_pid_tgid();
    __u32 pid = pid_tgid >> 32;
    __u32 tid = pid_tgid & 0xFFFFFFFF;
    __u32 syscall_nr = args->id;
    __s64 ret = args->ret;
    __u64 ts_exit_ns = bpf_ktime_get_ns();
    
    struct syscall_latency_key key = {
        .pid = pid,
        .tid = tid,
        .syscall_nr = syscall_nr,
    };
    __u64 *ts_enter = syscall_times.lookup(&key);
    
    if (!ts_enter) {
        return 0;
    }
    
    __u64 latency_ns = ts_exit_ns - *ts_enter;
    
    char comm[16];
    bpf_get_current_comm(&comm, sizeof(comm));
    
    struct syscall_event event = {
        .pid = pid,
        .tid = tid,
        .syscall_nr = syscall_nr,
        .ts_enter_ns = *ts_enter,
        .ts_exit_ns = ts_exit_ns,
        .latency_ns = latency_ns,
        .ret = ret,
    };
    bpf_probe_read_kernel_str(&event.comm, sizeof(comm), &comm);
    
    syscall_events.ringbuf_output(&event, sizeof(event), 0);
    
    syscall_times.delete(&key);
    
    return 0;
}
