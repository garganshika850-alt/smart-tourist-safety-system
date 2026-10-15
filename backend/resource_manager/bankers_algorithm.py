# ============================================================
# Smart Tourist Safety and Emergency Response System
# OS Concept: Banker's Algorithm (Deadlock Avoidance) (Phase 14)
# ============================================================

from typing import Any, Dict, List, Optional, Tuple
from backend.utils.logger import logger

# The 3 OS resource types representing physical emergency apparatus
RESOURCE_TYPES = ["AMBULANCE", "RESCUE_TEAM", "HELICOPTER"]

# Default maximum resource claims based on emergency severity
DEFAULT_MAX_CLAIMS = {
    "CRITICAL_ACCIDENT": {"AMBULANCE": 2, "RESCUE_TEAM": 2, "HELICOPTER": 1},
    "SOS": {"AMBULANCE": 1, "RESCUE_TEAM": 1, "HELICOPTER": 0},
    "DANGEROUS_ZONE": {"AMBULANCE": 0, "RESCUE_TEAM": 1, "HELICOPTER": 0},
    "SAFETY_ALERT": {"AMBULANCE": 0, "RESCUE_TEAM": 0, "HELICOPTER": 0},
}

class BankersAlgorithm:
    """
    Classical Banker's Algorithm implementation for Deadlock Avoidance.
    Tracks Available, Max, Allocation, and Need matrices.
    Evaluates safety state before any resource grant to ensure the system
    never enters an unsafe state that could cause circular-wait deadlocks.
    """

    def __init__(self, initial_available: Optional[Dict[str, int]] = None):
        # Available[j]: Available units of resource class j
        self.available: Dict[str, int] = {
            r: initial_available.get(r, 0) if initial_available else 0
            for r in RESOURCE_TYPES
        }
        # If no initial capacities provided, set reasonable real-world fleet defaults
        if not initial_available:
            self.available = {"AMBULANCE": 4, "RESCUE_TEAM": 5, "HELICOPTER": 2}

        # Total system fleet capacity (Available + Sum of all current allocations)
        self.total_capacity: Dict[str, int] = dict(self.available)

        # Max[i][j]: Maximum demand of process i
        self.max_claim: Dict[int, Dict[str, int]] = {}

        # Allocation[i][j]: Current resources allocated to process i
        self.allocation: Dict[int, Dict[str, int]] = {}

        # Need[i][j] = Max[i][j] - Allocation[i][j]
        self.need: Dict[int, Dict[str, int]] = {}

    def register_process(
        self,
        process_id: int,
        max_demand: Optional[Dict[str, int]] = None,
        incident_type: Optional[str] = None
    ) -> None:
        """
        Registers an active emergency process with its maximum resource claim.
        """
        if max_demand is None:
            max_demand = DEFAULT_MAX_CLAIMS.get(
                incident_type or "SOS",
                {"AMBULANCE": 1, "RESCUE_TEAM": 1, "HELICOPTER": 0}
            )

        # Clean demand mapping
        clean_max = {r: max(0, int(max_demand.get(r, 0))) for r in RESOURCE_TYPES}

        self.max_claim[process_id] = clean_max
        self.allocation[process_id] = {r: 0 for r in RESOURCE_TYPES}
        self.need[process_id] = dict(clean_max)

        logger.info(
            f"[Banker's] Registered Process #{process_id} with Max Claim: {clean_max}"
        )

    def unregister_process(self, process_id: int) -> Dict[str, int]:
        """
        Unregisters an incident process and releases all its allocated resources back to Available.
        """
        released = {r: 0 for r in RESOURCE_TYPES}
        if process_id in self.allocation:
            for r in RESOURCE_TYPES:
                alloc = self.allocation[process_id].get(r, 0)
                self.available[r] += alloc
                released[r] = alloc

            del self.allocation[process_id]
            self.max_claim.pop(process_id, None)
            self.need.pop(process_id, None)
            logger.info(
                f"[Banker's] Unregistered Process #{process_id}. Reclaimed: {released}. Available now: {self.available}"
            )
        return released

    def is_safe_state(self) -> Tuple[bool, List[int]]:
        """
        Dijkstra's Safety Algorithm.
        Returns (is_safe, safe_sequence).
        If state is safe, returns a valid execution order of processes that avoids deadlock.
        """
        work = dict(self.available)
        finish = {p: False for p in self.max_claim.keys()}
        safe_sequence: List[int] = []

        processes = list(self.max_claim.keys())
        num_processes = len(processes)

        while len(safe_sequence) < num_processes:
            found_process = False

            for p in processes:
                if not finish[p]:
                    # Check if Need[p][r] <= Work[r] for all resource types
                    can_satisfy = all(self.need[p][r] <= work[r] for r in RESOURCE_TYPES)

                    if can_satisfy:
                        # Process can finish and release its resources
                        for r in RESOURCE_TYPES:
                            work[r] += self.allocation[p][r]
                        finish[p] = True
                        safe_sequence.append(p)
                        found_process = True
                        break

            # If in this iteration no process could finish, system is unsafe
            if not found_process:
                break

        is_safe = (len(safe_sequence) == num_processes)
        return is_safe, safe_sequence

    def request_resources(
        self,
        process_id: int,
        request_vector: Dict[str, int]
    ) -> Tuple[bool, str, Optional[List[int]]]:
        """
        Resource-Request Algorithm:
        1. If Request_i <= Need_i, go to step 2; else error (exceeded max claim).
        2. If Request_i <= Available, go to step 3; else process must wait.
        3. Pretend to allocate requested resources.
        4. Run Safety Algorithm.
        5. If safe, grant resources. If unsafe, rollback pretend allocation and deny.
        """
        if process_id not in self.max_claim:
            return False, f"Process #{process_id} is not registered in Banker's algorithm.", None

        clean_req = {r: int(request_vector.get(r, 0)) for r in RESOURCE_TYPES}

        # Step 1: Request <= Need
        for r in RESOURCE_TYPES:
            if clean_req[r] > self.need[process_id][r]:
                return (
                    False,
                    f"Error: Process #{process_id} exceeded its maximum claim for {r} "
                    f"(Requested: {clean_req[r]}, Need: {self.need[process_id][r]}).",
                    None
                )

        # Step 2: Request <= Available
        for r in RESOURCE_TYPES:
            if clean_req[r] > self.available[r]:
                return (
                    False,
                    f"Resources unavailable: {r} (Requested: {clean_req[r]}, Available: {self.available[r]}). Process must wait.",
                    None
                )

        # Step 3: Tentatively allocate (simulate allocation)
        for r in RESOURCE_TYPES:
            self.available[r] -= clean_req[r]
            self.allocation[process_id][r] += clean_req[r]
            self.need[process_id][r] -= clean_req[r]

        # Step 4: Run Safety Algorithm
        is_safe, safe_sequence = self.is_safe_state()

        if is_safe:
            # Grant resource allocation
            logger.info(
                f"[Banker's] Allocation APPROVED for Process #{process_id}: {clean_req}. "
                f"Safe Sequence: {safe_sequence}. Remaining Available: {self.available}"
            )
            return True, "Safe state confirmed. Resources allocated successfully.", safe_sequence
        else:
            # Rollback tentative allocation (prevent deadlock!)
            for r in RESOURCE_TYPES:
                self.available[r] += clean_req[r]
                self.allocation[process_id][r] -= clean_req[r]
                self.need[process_id][r] += clean_req[r]

            logger.warning(
                f"[Banker's] Allocation REJECTED for Process #{process_id}: {clean_req}. "
                f"Leads to UNSAFE state (potential deadlock). Rollback executed."
            )
            return (
                False,
                "Deadlock Avoidance: Request would lead to an UNSAFE state. Allocation denied to prevent deadlock.",
                None
            )

    def release_resources(
        self,
        process_id: int,
        release_vector: Dict[str, int]
    ) -> Tuple[bool, str]:
        """
        Releases allocated resources back to the available pool.
        """
        if process_id not in self.allocation:
            return False, f"Process #{process_id} not found."

        clean_rel = {r: int(release_vector.get(r, 0)) for r in RESOURCE_TYPES}

        for r in RESOURCE_TYPES:
            if clean_rel[r] > self.allocation[process_id][r]:
                return (
                    False,
                    f"Cannot release more {r} than currently allocated "
                    f"({clean_rel[r]} > {self.allocation[process_id][r]})."
                )

        for r in RESOURCE_TYPES:
            self.allocation[process_id][r] -= clean_rel[r]
            self.available[r] += clean_rel[r]
            self.need[process_id][r] += clean_rel[r]

        logger.info(
            f"[Banker's] Released {clean_rel} from Process #{process_id}. Available now: {self.available}"
        )
        return True, "Resources released successfully."

    def get_state(self) -> Dict[str, Any]:
        """
        Returns full snapshot of Banker's Algorithm data structures
        for telemetry, authority dashboard, and academic evaluation.
        """
        is_safe, safe_seq = self.is_safe_state()
        return {
            "resource_types": list(RESOURCE_TYPES),
            "available": dict(self.available),
            "total_capacity": dict(self.total_capacity),
            "max_matrix": {str(k): dict(v) for k, v in self.max_claim.items()},
            "allocation_matrix": {str(k): dict(v) for k, v in self.allocation.items()},
            "need_matrix": {str(k): dict(v) for k, v in self.need.items()},
            "active_processes_count": len(self.max_claim),
            "is_safe": is_safe,
            "safe_sequence": safe_seq,
        }
