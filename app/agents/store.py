"""Stockage des traces, recommandations, manques détectés et simulations.

Les objets vivent en mémoire ; chaque création ou modification est notée, puis enregistrée
dans PostgreSQL après chaque requête (voir app/persistence.py) et rechargée au démarrage.
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
SIMULATIONS: dict[str, dict] = {}
STATE: dict[str, dict] = {}  # états divers, par exemple la dernière surveillance

_dirty: set[tuple[str, str]] = set()

_current: ContextVar[Optional[Trace]] = ContextVar("current_trace", default=None)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def start_trace(nature: str) -> Trace:
    trace = Trace(id=new_id("T"), nature=nature, debut=time.time())
    TRACES[trace.id] = trace
    mark("trace", trace.id)
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
    mark("trace", trace.id)


def mark(kind: str, obj_id: str) -> None:
    """Note qu'un objet a changé et doit être enregistré."""
    _dirty.add((kind, obj_id))


def put_recommendation(reco: Recommendation) -> None:
    RECOMMENDATIONS[reco.id] = reco
    mark("recommandation", reco.id)


def put_gap(gap: Gap) -> None:
    GAPS[gap.id] = gap
    mark("manque", gap.id)


def put_simulation(sim: dict) -> None:
    SIMULATIONS[sim["id"]] = sim
    mark("simulation", sim["id"])


def set_state(key: str, value: dict) -> None:
    STATE[key] = value
    mark("etat", key)


def _serialize(kind: str, obj_id: str) -> Optional[dict]:
    if kind == "trace":
        t = TRACES.get(obj_id)
        return t.to_dict() if t else None
    if kind == "recommandation":
        r = RECOMMENDATIONS.get(obj_id)
        return asdict(r) if r else None
    if kind == "manque":
        g = GAPS.get(obj_id)
        return asdict(g) if g else None
    if kind == "simulation":
        return SIMULATIONS.get(obj_id)
    return STATE.get(obj_id)


def pending() -> list[tuple[str, str, dict]]:
    """Objets modifiés depuis le dernier enregistrement, prêts à être écrits."""
    rows = []
    for kind, obj_id in sorted(_dirty):
        data = _serialize(kind, obj_id)
        if data is not None:
            rows.append((kind, obj_id, data))
    _dirty.clear()
    return rows


def requeue(rows: list[tuple[str, str, dict]]) -> None:
    """Remet en attente des objets dont l'enregistrement a échoué."""
    _dirty.update((kind, obj_id) for kind, obj_id, _ in rows)


def restore(rows: list[tuple[str, str, dict]]) -> None:
    """Recharge les objets enregistrés (au démarrage du service)."""
    for kind, obj_id, d in rows:
        if kind == "trace":
            TRACES[obj_id] = Trace(d["id"], d["nature"], d["debut"], [Step(**e) for e in d["etapes"]])
        elif kind == "recommandation":
            RECOMMENDATIONS[obj_id] = Recommendation(**d)
        elif kind == "manque":
            GAPS[obj_id] = Gap(**d)
        elif kind == "simulation":
            SIMULATIONS[obj_id] = d
        else:
            STATE[obj_id] = d


def reset() -> None:
    TRACES.clear()
    RECOMMENDATIONS.clear()
    GAPS.clear()
    SIMULATIONS.clear()
    STATE.clear()
    _dirty.clear()
