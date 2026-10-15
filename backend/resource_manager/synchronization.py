# ============================================================
# Smart Tourist Safety and Emergency Response System
# OS Concept: Synchronization (Mutex Locks & Semaphores) (Phase 12)
# ============================================================

import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator
from backend.utils.logger import logger

class SynchronizationManager:
    """
    Manages concurrency control for shared resources.
    Demonstrates OS synchronization primitives:
      - Mutex Lock (threading.Lock): Guarantees mutual exclusion when updating resource matrices.
      - Counting Semaphore (threading.Semaphore): Limits the maximum number of concurrent
        emergency dispatchers competing for physical apparatus.
    """

    def __init__(self, max_concurrent_allocations: int = 5):
        # Mutex lock protecting Banker's algorithm shared state and matrices
        self._mutex: threading.Lock = threading.Lock()

        # Counting semaphore throttling simultaneous dispatches
        self._dispatch_semaphore: threading.Semaphore = threading.Semaphore(max_concurrent_allocations)
        self.max_concurrent_allocations = max_concurrent_allocations

        # Telemetry metrics
        self._contention_count: int = 0
        self._total_locks_acquired: int = 0
        self._active_allocations: int = 0

    @contextmanager
    def critical_section(self) -> Generator[None, None, None]:
        """
        Context manager for atomic critical section access using Mutex Lock.
        Tracks lock contention and ensures safe release in finally block.
        """
        # Check if already locked to measure contention
        if self._mutex.locked():
            self._contention_count += 1
            logger.debug("[SyncManager] Lock contention detected. Thread waiting for Mutex...")

        t_start = time.perf_counter()
        acquired = self._mutex.acquire(blocking=True)
        try:
            wait_duration = time.perf_counter() - t_start
            self._total_locks_acquired += 1
            if wait_duration > 0.05:
                logger.debug(f"[SyncManager] Lock acquired after {wait_duration:.4f}s delay.")
            yield
        finally:
            if acquired:
                self._mutex.release()

    @contextmanager
    def acquire_dispatch_permit(self, timeout: float = 5.0) -> Generator[bool, None, None]:
        """
        Context manager using Counting Semaphore to control concurrent allocations.
        Guarantees that no more than N threads simultaneously dispatch vehicles.
        """
        permit_acquired = self._dispatch_semaphore.acquire(blocking=True, timeout=timeout)
        if not permit_acquired:
            logger.warning("[SyncManager] Dispatch permit timed out: system at maximum capacity.")
            yield False
            return

        try:
            with self._mutex:
                self._active_allocations += 1
            yield True
        finally:
            with self._mutex:
                self._active_allocations = max(0, self._active_allocations - 1)
            self._dispatch_semaphore.release()

    def get_sync_metrics(self) -> Dict[str, Any]:
        """Returns synchronization metrics for monitoring and examiner demonstration."""
        with self._mutex:
            return {
                "mutex_locked": self._mutex.locked(),
                "contention_count": self._contention_count,
                "total_locks_acquired": self._total_locks_acquired,
                "active_allocations": self._active_allocations,
                "max_concurrent_allocations": self.max_concurrent_allocations,
            }

# Global shared instance of synchronization manager
sync_manager: SynchronizationManager = SynchronizationManager()
