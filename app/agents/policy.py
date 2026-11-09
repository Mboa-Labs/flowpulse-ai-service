"""Agent Politique et Conformité (nœud P de Y.3172).

Vérifie une décision proposée au regard des textes de la base de connaissances et rend un
verdict sourcé. Quand aucun texte ne couvre la décision, il enregistre un manque réglementaire
au lieu d'inventer une règle.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Optional

from app import kb
from app.agents import llm, store
from app import langue

VERDICTS = ("CONFORME", "CONFORME_SOUS_RESERVE", "NON_CONFORME", "NON_COUVERT")
MIN_SCORE = 0.35  # en dessous, un passage n'est pas considéré comme pertinent
NB_EXTRAITS = 3  # extraits lus par le modèle : moins de texte à lire, réponse 2 fois plus rapide sur processeur
PAR_DOCUMENT = 2  # au plus 2 extraits d'un même document, pour qu'un gros recueil ne masque pas les autres textes
LONGUEUR_EXTRAIT = 450  # caractères par extrait
DUREE_CACHE = 6 * 3600  # un verdict par type de décision reste valable 6 heures (la base de textes change rarement)

PROMPT = """Tu es l'agent de conformité réglementaire de FlowPulse.
Décision proposée : {decision}

Extraits des textes en vigueur (n'utilise QUE ces extraits) :
{passages}

Réponds uniquement en JSON avec les clés :
"verdict" : l'une de {verdicts},
"justification" : 2 phrases maximum, en {langue}, qui citent le document et l'article. Ce verdict vaut pour toutes les décisions du même type : justifie le type de mesure, sans nommer de zone, de ligne, de lieu ni d'horaire,
"citations" : liste des numéros d'extraits utilisés (ex. [1, 3]).
Si aucun extrait ne permet de conclure, réponds "NON_COUVERT"."""


@dataclass
class PolicyResult:
    verdict: str
    justification: str
    citations: list[dict]


def _cite(p: kb.Passage) -> dict:
    return {"doc_id": p.doc_id, "titre": p.titre, "reference": p.reference, "article": p.article, "extrait": p.texte[:300], "score": p.score}


def _selection(passages: list[kb.Passage]) -> list[kb.Passage]:
    """Les meilleurs extraits pertinents, sans qu'un seul document les accapare."""
    retenus, par_doc = [], {}
    for p in passages:
        if p.score < MIN_SCORE or par_doc.get(p.doc_id, 0) >= PAR_DOCUMENT:
            continue
        par_doc[p.doc_id] = par_doc.get(p.doc_id, 0) + 1
        retenus.append(p)
        if len(retenus) == NB_EXTRAITS:
            break
    return retenus


def check(decision: str, type_decision: Optional[str] = None) -> PolicyResult:
    """Verdict sourcé sur une décision.

    type_decision regroupe les décisions qui relèvent des mêmes textes (par exemple toute réaffectation de bus
    de réserve, quelle que soit la zone) : le premier verdict est réutilisé pour les suivantes, avec ses citations,
    ce qui évite de refaire lire les mêmes articles au modèle pour chaque zone.
    """
    started = time.perf_counter()
    if type_decision:
        type_decision = f"{type_decision}:{langue.actuelle()}"  # un verdict par langue
        cache = store.POLICY_CACHE.get(type_decision)
        if cache and time.time() - cache["date"] < DUREE_CACHE:
            result = PolicyResult(cache["verdict"], cache["justification"], cache["citations"])
            store.record("policy", "verdict_reutilise", decision,
                         {"verdict": result.verdict, "type_decision": type_decision, "verifie_pour": cache["decision"]},
                         started, result.citations)
            return result
    result = _verifier(decision, started)
    # On ne garde pas un échec technique (base ou modèle indisponible) : la prochaine décision retentera
    if type_decision and not result.justification.startswith(("Vérification impossible", "Base de connaissances indisponible")):
        store.POLICY_CACHE[type_decision] = {**asdict(result), "decision": decision, "date": time.time()}
    return result


def _verifier(decision: str, started: float) -> PolicyResult:
    try:
        passages = _selection(kb.search(decision, n=NB_EXTRAITS * 4))
    except Exception as e:  # base vide, Ollama arrêté…
        store.record("policy", "recherche_kb", decision, f"indisponible : {e}", started)
        return PolicyResult("NON_COUVERT", f"Base de connaissances indisponible ({e}) : validation humaine obligatoire.", [])

    if not passages:
        result = PolicyResult(
            "NON_COUVERT",
            langue.tr("Aucun texte de la base de connaissances ne couvre cette décision : validation humaine obligatoire.",
                      "No text in the knowledge base covers this decision: human approval required."),
            [],
        )
        trace = store.current_trace()
        # Une même décision non couverte n'est inscrite qu'une fois au registre
        if not any(g.decision_concernee == decision for g in store.GAPS.values()):
            gap = store.Gap(store.new_id("GAP"), "VIDE_JURIDIQUE", "Aucun texte indexé ne couvre cette décision.", decision, trace.id if trace else None)
            store.put_gap(gap)
        store.record("policy", "verdict", decision, result.verdict, started)
        return result

    listing = "\n".join(f"[{i + 1}] {p.titre} ({p.reference}) {p.article} : {p.texte[:LONGUEUR_EXTRAIT]}" for i, p in enumerate(passages))
    try:
        raw = llm.get_llm(json_mode=True).invoke(PROMPT.format(decision=decision, passages=listing, verdicts=", ".join(VERDICTS), langue=langue.nom_langue())).content
        data = json.loads(raw)
        verdict = data.get("verdict") if data.get("verdict") in VERDICTS else "NON_COUVERT"
        used = [passages[i - 1] for i in data.get("citations", []) if isinstance(i, int) and 1 <= i <= len(passages)] or passages[:1]
        result = PolicyResult(verdict, str(data.get("justification", "")).strip(), [_cite(p) for p in used])
    except Exception as e:
        result = PolicyResult("NON_COUVERT", f"Vérification impossible ({e}) : validation humaine obligatoire.", [_cite(p) for p in passages[:2]])

    store.record("policy", "verdict", decision, {"verdict": result.verdict, "justification": result.justification}, started, result.citations)
    return result
