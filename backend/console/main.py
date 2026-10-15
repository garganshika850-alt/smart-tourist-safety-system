"""Interactive console for the PostgreSQL-backed safety system."""

from __future__ import annotations

import threading
from typing import Callable

from backend.db.connection import close_db_pool
from backend.db.repositories import (
    ContactRepository,
    EmergencyRepository,
    LogRepository,
    ResourceRepository,
    TouristRepository,
)
from backend.emergency.process_manager import ProcessManager
from backend.resource_manager.resource_manager import ResourceManager
from backend.scheduler.priority_queue import EmergencyPriorityQueue


def _read_float(label: str, minimum: float, maximum: float) -> float:
    value = float(input(label).strip())
    if not minimum <= value <= maximum:
        raise ValueError(f"Value must be between {minimum} and {maximum}.")
    return value


def build_manager() -> ProcessManager:
    manager = ProcessManager(EmergencyPriorityQueue(), ResourceManager())
    manager.recover_pending()
    return manager


def _show_queue(manager: ProcessManager) -> None:
    events = manager.queue.get_all_events()
    if not events:
        print("Emergency queue is empty.")
        return
    print("Pending incidents (priority queue order):")
    for event in events:
        print(f"  INC{event.incident_id:03d}  priority={event.priority}  {event.event_type}")


def _register_tourist() -> None:
    name = input("Tourist name: ").strip()
    phone = input("Tourist phone: ").strip()
    email = input("Email (required by existing schema): ").strip()
    tourist = TouristRepository.create_tourist(name=name, phone=phone, email=email)
    print(f"Tourist registered: T{tourist['tourist_id']:03d} {tourist['name']}")
    contact_name = input("Emergency contact name: ").strip()
    contact_phone = input("Emergency contact phone: ").strip()
    if contact_name and contact_phone:
        ContactRepository.add_contact(
            tourist_id=tourist["tourist_id"], name=contact_name,
            phone=contact_phone, relationship="Emergency contact",
        )


def _create_emergency(manager: ProcessManager) -> None:
    tourist_id = int(input("Tourist ID: ").strip())
    print("Types: ACCIDENT, SOS, DANGEROUS_ZONE, SAFETY_ALERT, GPS_UPDATE")
    incident_type = input("Emergency type: ").strip().upper()
    latitude = _read_float("Latitude: ", -90, 90)
    longitude = _read_float("Longitude: ", -180, 180)
    description = input("Description: ").strip()
    incident = manager.create_emergency(
        tourist_id, incident_type, latitude, longitude, description
    )
    print(f"INC{incident['incident_id']:03d} created and queued at priority {incident['priority']}.")


def _process_one(manager: ProcessManager) -> None:
    outcome = manager.process_next()
    print(f"{outcome['event_type']} INC{outcome['incident_id']:03d}: "
          f"{outcome['status']} — {outcome.get('transaction', outcome.get('reason'))}")
    if outcome.get("resource"):
        print(f"  Resource: {outcome['resource']}")
    if outcome.get("team"):
        print(f"  Rescue team: {outcome['team']}")


def _resolve_incident(manager: ProcessManager) -> None:
    incident_id = int(input("Incident ID to resolve: ").strip())
    result = manager.resources.resolve_incident_transaction(incident_id)
    print(f"INC{incident_id:03d}: {result['status']}; released "
          f"{result['released_assignments']} assignment(s); transaction {result['transaction']}.")


def _simulate(manager: ProcessManager) -> None:
    tourists = TouristRepository.get_tourists(limit=1)
    if not tourists:
        print("Register a tourist before simulating emergencies.")
        return
    tourist_id = tourists[0]["tourist_id"]
    incidents = []
    failures = []
    types = ["GPS_UPDATE", "SOS", "ACCIDENT", "DANGEROUS_ZONE"]

    def submit(kind: str) -> None:
        try:
            incidents.append(manager.create_emergency(
                tourist_id, kind, 15.5, 73.8, f"Concurrent simulation: {kind}"
            ))
        except Exception as exc:
            failures.append((kind, str(exc)))

    producers = [threading.Thread(target=submit, args=(kind,), name=f"Producer-{i + 1}")
                 for i, kind in enumerate(types)]
    for producer in producers:
        producer.start()
    for producer in producers:
        producer.join()
    print(f"Created {len(incidents)} emergencies concurrently from {len(producers)} producer threads.")
    for kind, message in failures:
        print(f"  {kind} failed: {message}")
    _show_queue(manager)


def run_console(input_fn: Callable[[str], str] = input) -> None:
    manager = build_manager()
    actions = {
        "1": _register_tourist,
        "2": lambda: _create_emergency(manager),
        "3": lambda: _show_queue(manager),
        "4": lambda: print(EmergencyRepository.get_incidents(limit=50)),
        "5": lambda: print(ResourceRepository.get_all_resources()),
        "6": lambda: print(LogRepository.get_recent_logs(limit=50)),
        "7": lambda: _simulate(manager),
        "8": lambda: _process_one(manager),
        "9": lambda: manager.start(),
        "10": lambda: manager.stop(),
        "11": lambda: _resolve_incident(manager),
    }
    try:
        while True:
            print("\n=== SMART TOURIST SAFETY SYSTEM ===")
            print("1 Register tourist   2 Create emergency   3 View priority queue")
            print("4 View incidents     5 View resources      6 View emergency logs")
            print("7 Concurrent simulation  8 Process next  9 Start workers  10 Stop workers")
            print("11 Resolve incident and release resources  0 Exit")
            choice = input_fn("Choice: ").strip()
            if choice == "0":
                break
            action = actions.get(choice)
            if action is None:
                print("Choose a listed menu number.")
                continue
            try:
                action()
            except Exception as exc:
                print(f"Operation failed: {exc}")
    finally:
        manager.stop()
        close_db_pool()


if __name__ == "__main__":
    run_console()
