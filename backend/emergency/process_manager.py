"""Priority-driven emergency intake and threaded dispatch processing."""

import queue
import threading
from typing import Any, Dict, Optional

from backend.db.repositories import EmergencyRepository
from backend.resource_manager.resource_manager import ResourceManager, resource_manager
from backend.scheduler.priority_queue import (
    EVENT_TYPE_PRIORITIES,
    EmergencyEvent,
    EmergencyPriorityQueue,
    scheduler,
)
from backend.utils.logger import logger


class ProcessManager:
    """Connects persisted incidents to the shared priority queue and workers."""

    def __init__(self, event_queue: Optional[EmergencyPriorityQueue] = None,
                 resources: Optional[ResourceManager] = None):
        self.queue = event_queue or scheduler
        self.resources = resources or resource_manager
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._results: list[Dict[str, Any]] = []
        self._results_lock = threading.Lock()
        self._recovered = False

    def create_emergency(self, tourist_id: int, incident_type: str, latitude: float,
                         longitude: float, description: str = "") -> Dict[str, Any]:
        """Persist, audit, and enqueue a typed emergency."""
        incident_type = incident_type.strip().upper()
        if incident_type == "ACCIDENT":
            incident_type = "CRITICAL_ACCIDENT"
        if incident_type not in EVENT_TYPE_PRIORITIES:
            raise ValueError(f"Invalid emergency type: {incident_type}")
        incident = EmergencyRepository.create_incident(
            tourist_id=tourist_id,
            incident_type=incident_type,
            priority=EVENT_TYPE_PRIORITIES[incident_type],
            latitude=latitude,
            longitude=longitude,
            description=description,
            status="QUEUED",
        )
        self.enqueue_existing(incident, update_status=False)
        return incident

    def recover_pending(self) -> int:
        """Reload durable queued incidents after a server restart."""
        if self._recovered:
            return 0
        pending = []
        for status in ("QUEUED", "RECEIVED"):
            pending.extend(EmergencyRepository.get_incidents(status=status, limit=100))
        for incident in pending:
            self.enqueue_existing(incident, update_status=False)
        self._recovered = True
        return len(pending)

    def enqueue_existing(self, incident: Dict[str, Any], update_status: bool = True) -> EmergencyEvent:
        """Queue an already persisted incident, optionally adding a queue audit row."""
        if update_status:
            EmergencyRepository.update_incident_status(
                incident_id=int(incident["incident_id"]),
                status="QUEUED",
                action="PRIORITY_ENQUEUED",
                details=f"Added to thread-safe queue at priority {incident['priority']}.",
                performed_by="ProcessManager",
            )
        return self.queue.enqueue_from_incident(incident)

    def process_next(self, block: bool = False, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Remove the queue head and run its database dispatch transaction."""
        event = self.queue.dequeue(block=block, timeout=timeout)
        if event.incident_id is None:
            return {"status": "processed", "event_id": event.event_id,
                    "event_type": event.event_type, "transaction": "NOT_REQUIRED"}
        try:
            outcome = self.resources.dispatch_incident_transaction(
                event.incident_id, event.event_type
            )
        except Exception:
            # A failed DB transaction leaves the incident queued in PostgreSQL;
            # put its in-memory event back so a transient failure is retryable.
            self.queue.enqueue(event)
            raise
        if outcome.get("status") == "QUEUED":
            self.queue.enqueue(event)
        outcome["priority"] = event.priority
        outcome["event_type"] = event.event_type
        outcome["worker"] = threading.current_thread().name
        with self._results_lock:
            self._results.append(outcome)
        return outcome

    def start(self, worker_count: int = 3) -> None:
        """Start worker threads that consume and dispatch queued incidents."""
        if self._threads:
            return
        if worker_count < 1:
            raise ValueError("worker_count must be at least one")
        self.recover_pending()
        self._stop.clear()
        for index in range(worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"EmergencyWorker-{index + 1}",
                daemon=True,
            )
            self._threads.append(worker)
            worker.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        for worker in self._threads:
            worker.join(timeout)
        self._threads.clear()

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_next(block=True, timeout=0.25)
            except queue.Empty:
                continue
            except Exception as exc:
                logger.exception("Emergency worker failed; rolled-back event was requeued: %s", exc)
                self._stop.wait(0.5)

    def results(self) -> list[Dict[str, Any]]:
        with self._results_lock:
            return list(self._results)


process_manager = ProcessManager()
