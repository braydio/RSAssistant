"""Fidelity shadow adapter: the generic snapshot adapter fixed to ``fidelity``.

A live Zendriver-backed adapter (extracted from the GPL-3.0 auto-rsa fork; see
PROVENANCE.md) is a separate, human-gated step.
"""

from __future__ import annotations

from pathlib import Path

from rsassistant.integrations.brokers.snapshot import (  # noqa: F401
    SnapshotBrokerAdapter, compare_positions)


class FidelitySnapshotAdapter(SnapshotBrokerAdapter):
    def __init__(self, snapshot_path: str | Path, *, broker_name: str = "fidelity"):
        super().__init__(snapshot_path, broker_name=broker_name)
