from __future__ import annotations

"""Core architecture package for GenomeAI AgroAnimals.

New application/domain/infra code should be added here.
Legacy modules under ``genomeai.*`` remain for backward compatibility and
progressively become thin wrappers around this package.
"""

__all__ = [
    "application",
    "artifacts",
    "audit",
    "commercial_packaging",
    "commercial_readiness_gate",
    "common",
    "customer_upgrade_discipline",
    "domain",
    "economics",
    "explainability",
    "health",
    "infra",
    "interoperability",
    "migrations",
    "operational",
    "performance",
    "pilot_adoption_metrics",
    "pilot_framework",
    "release",
    "reporting",
    "recovery",
    "reproduction",
    "security",
    "support_sla_incident",
    "workflow",
]
