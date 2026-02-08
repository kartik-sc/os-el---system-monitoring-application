# ebpf/loaders/syscall_loader.py
"""
SyscallLoader - attaches eBPF syscall tracer and pushes events into the EventBus.

This version uses BCC's standard ring buffer API:
  - bpf["events"].open_ring_buffer(callback)
  - bpf.ring_buffer_poll(timeout)

It avoids ring_buffer_read_into_user_ringbuf(), which is not available
in older BCC versions.
"""

import asyncio
import logging
from typing import Any, Dict

from bcc import BPF

from ingestion.event_bus import EventBus, Event, EventType

logger = logging.getLogger(__name__)


class SyscallLoader:
    """
    Loads and manages the syscall-tracing eBPF program.
    """

    def __init__(self, event_bus: EventBus, poll_interval: float = 0.1):
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self.bpf: BPF | None = None
        self._running = False

    def _load_program(self) -> None:
        """
        Compile and attach the eBPF program.
        Assumes ebpf/programs/syscall_trace.bpf.c exists and is valid.
        """
        logger.info("Compiling syscall tracing eBPF program...")

        with open("ebpf/programs/syscall_trace.bpf.c", "r") as f:
            source = f.read()

        # Compile
        self.bpf = BPF(text=source)

        # Attach to sys_enter (example; adjust if your program uses different hooks)
        # This should match the SEC() / kprobe names in syscall_trace.bpf.c
        try:
            self.bpf.attach_kprobe(
                event="__x64_sys_openat",
                fn_name="trace_sys_enter"
            )
        except Exception as e:
            logger.warning("Failed to attach kprobe __x64_sys_openat: %s", e)

        # Open ring buffer on map named "events"
        try:
            rb = self.bpf["events"]

            def _callback(cpu: int, data: Any, size: int) -> None:
                self._handle_event(data, size)

            rb.open_ring_buffer(_callback)
            logger.info("✓ eBPF program compiled and attached")
        except Exception as e:
            logger.error("Failed to open ring buffer: %s", e, exc_info=True)
            raise

    def _handle_event(self, data: Any, size: int) -> None:
        """
        Parse raw event data from eBPF into a Python dict and publish.
        This must match the struct layout in syscall_trace.bpf.c.
        """

        # Example unpacking; adjust fields to match your actual C struct
        class SyscallEvent(self.bpf["events"].event_t):  # type: ignore[attr-defined]
            pass

        evt = SyscallEvent(data)

        event_data: Dict[str, Any] = {
            "pid": evt.pid,
            "tgid": getattr(evt, "tgid", 0),
            "syscall_id": evt.syscall_id,
            "latency_us": getattr(evt, "latency_us", 0),
        }

        # Optional fields (if present in C struct)
        if hasattr(evt, "comm"):
            event_data["comm"] = evt.comm.decode("utf-8", "replace").rstrip("\x00")

        asyncio.create_task(
            self.event_bus.publish(
                Event(
                    event_type=EventType.SYSCALL,
                    data=event_data,
                )
            )
        )

    async def _poll_loop(self) -> None:
        """
        Poll ring buffer in an asyncio-friendly loop.
        """
        assert self.bpf is not None
        self._running = True

        try:
            while self._running:
                # timeout in milliseconds
                self.bpf.ring_buffer_poll(int(self.poll_interval * 1000))
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            logger.info("SyscallLoader poll loop cancelled")
        except Exception as e:
            logger.error("SyscallLoader poll loop error: %s", e, exc_info=True)
        finally:
            self._running = False

    async def start(self) -> None:
        """
        Public entrypoint: load program and start polling.
        """
        try:
            if self.bpf is None:
                self._load_program()
            await self._poll_loop()
        except asyncio.CancelledError:
            logger.info("Syscall loader cancelled")
        except Exception as e:
            logger.error("Failed to load eBPF program: %s", e, exc_info=True)

    async def stop(self) -> None:
        """
        Stop polling and detach.
        """
        self._running = False
        if self.bpf is not None:
            try:
                self.bpf.cleanup()
            except Exception:
                pass
        logger.info("Syscall loader stopped")
