"""Agent Politique et Conformité (nœud P de Y.3172).

Vérifie une décision proposée au regard des textes de la base de connaissances et rend un
verdict sourcé. Quand aucun texte ne couvre la décision, il enregistre un manque réglementaire
au lieu d'inventer une règle.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from app import kb
from app.agents import llm, store

VERDICTS = ("CONFORME", "CONFORME_SOUS_RESERVE", "NON_CONFORME", "NON_COUVERT")
MIN_SCORE = 0.35  # en dessous, un passage n'est pas considéré comme pertinent

PROMPT = """Tu es l'agent de conformité réglementaire de FlowPulse.
Décision proposée : {decision}

Extraits des textes en vigueur (n'utilise QUE ces extraits) :
{passages}

Réponds uniquement en JSON avec les clés :
"verdict" : l'une de {verdicts},
"justification" : 2 phrases maximum, en français, qui citent le document et l'article,
"citations" : liste des numéros d'extraits utilisés (ex. [1, 3]).
Si aucun extrait ne permet de conclure, réponds "NON_COUVERT"."""


@dataclass
class PolicyResult:
    verdict: str
    justification: str
    citations: list[dict]


def _cite(p: kb.Passage) -> dict:
    return {"doc_id": p.doc_id, "titre": p.titre, "reference": p.reference, "article": p.article, "extrait": p.texte[:300], "score": p.score}


def check(decision: str) -> PolicyResult:
    started = time.perf_counter()
    try:
        passages = [p for p in kb.search(decision, n=5) if p.score >= MIN_SCORE]
    except Exception as e:  # base vide, Ollama arrêté…
        passages = []
        store.record("policy", "recherche_kb", decision, f"indisponible : {e}", started)

    if not passages:
        result = PolicyResult(
            "NON_COUVERT",
            "Aucun texte de la base de connaissances ne couvre cette décision : validation humaine obligatoire.",
            [],
        )
        trace = store.current_trace()
        gap = store.Gap(store.new_id("GAP"), "VIDE_JURIDIQUE", "Aucun texte indexé ne couvre cette décision.", decision, trace.id if trace else None)
        store.GAPS[gap.id] = gap
        store.record("policy", "verdict", decision, result.verdict, started)
        return result

    listing = "\n".join(f"[{i + 1}] {p.titre} ({p.reference}) {p.article} : {p.texte[:600]}" for i, p in enumerate(passages))
    try:
        raw = llm.get_llm(json_mode=True).invoke(PROMPT.format(decision=decision, passages=listing, verdicts=", ".join(VERDICTS))).content
        data = json.loads(raw)
        verdict = data.get("verdict") if data.get("verdict") in VERDICTS else "NON_COUVERT"
        used = [passages[i - 1] for i in data.get("citations", []) if isinstance(i, int) and 1 <= i <= len(passages)] or passages[:1]
        result = PolicyResult(verdict, str(data.get("justification", "")).strip(), [_cite(p) for p in used])
    except Exception as e:
        result = PolicyResult("NON_COUVERT", f"Vérification impossible ({e}) : validation humaine obligatoire.", [_cite(p) for p in passages[:2]])

    store.record("policy", "verdict", decision, {"verdict": result.verdict, "justification": result.justification}, started, result.citations)
    return result
