"""Stockage en mémoire des traces, recommandations et manques détectés.

Suffisant pour le prototype ; ces objets seront persistés par le backend
(tables agent_traces, recommandation, manque_reglementaire) lors de l'intégration.
"""

from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class Step:
    agent: str
    action: str
    entree: Any
    sortie: Any
    duree_ms: int
    sources: list[dict] = field(default_factory=list)


@dataclass
class Trace:
    id: str
    nature: str
    debut: float
    etapes: list[Step] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "nature": self.nature, "debut": self.debut, "etapes": [asdict(s) for s in self.etapes]}


@dataclass
class Recommendation:
    id: str
    zone: str
    ligne: str
    nb_bus: int
    description: str
    statut: str  # PROPOSEE, APPROUVEE, REJETEE, APPLIQUEE, BLOQUEE
    conformite: str  # CONFORME, CONFORME_SOUS_RESERVE, NON_CONFORME, NON_COUVERT
    justification: str
    citations: list[dict]
    trace_id: Optional[str]


@dataclass
class Gap:
    id: str
    categorie: str
    description: str
    decision_concernee: str
    trace_id: Optional[str]


TRACES: dict[str, Trace] = {}
RECOMMENDATIONS: dict[str, Recommendation] = {}
GAPS: dict[str, Gap] = {}

_current: ContextVar[Optional[Trace]] = ContextVar("current_trace", default=None)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def start_trace(nature: str) -> Trace:
    trace = Trace(id=new_id("T"), nature=nature, debut=time.time())
    TRACES[trace.id] = trace
    _current.set(trace)
    return trace


def current_trace() -> Optional[Trace]:
    return _current.get()


def record(agent: str, action: str, entree: Any, sortie: Any, started: float, sources: Optional[list[dict]] = None) -> None:
    """Ajoute une étape à la trace en cours (auditabilité : qui a fait quoi, avec quelles sources)."""
    trace = _current.get()
    if trace is None:
        return
    trace.etapes.append(Step(agent, action, entree, sortie, int((time.perf_counter() - started) * 1000), sources or []))


def reset() -> None:
    TRACES.clear()
    RECOMMENDATIONS.clear()
    GAPS.clear()
