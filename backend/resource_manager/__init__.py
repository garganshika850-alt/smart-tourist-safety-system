# ============================================================
# Smart Tourist Safety and Emergency Response System
# Resource Manager Package (OS Deadlock Avoidance & Synchronization)
# ============================================================

from backend.resource_manager.synchronization import (
    SynchronizationManager,
    sync_manager,
)
from backend.resource_manager.bankers_algorithm import (
    BankersAlgorithm,
    RESOURCE_TYPES,
    DEFAULT_MAX_CLAIMS,
)
from backend.resource_manager.resource_manager import (
    ResourceManager,
    resource_manager,
)

__all__ = [
    "SynchronizationManager",
    "sync_manager",
    "BankersAlgorithm",
    "RESOURCE_TYPES",
    "DEFAULT_MAX_CLAIMS",
    "ResourceManager",
    "resource_manager",
]
