"""Orchestrator : le superviseur conversationnel.

Boucle d'agent classique : le modèle choisit des outils, reçoit leurs résultats, et recommence
jusqu'à pouvoir répondre. Chaque étape est tracée ; les recommandations créées restent à valider.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.agents import llm, store
from app.agents.tools import TOOL_MAP, TOOLS

MAX_STEPS = 6

SYSTEM = """Tu es le superviseur de FlowPulse, plateforme d'aide à la décision pour la mobilité urbaine.
Tu aides les gestionnaires urbains et les opérateurs de bus.
Règles :
- Appuie-toi uniquement sur les résultats des outils ; n'invente aucun chiffre.
- Avant de proposer une réaffectation, consulte le trafic puis l'état de la flotte de la zone.
- Tu ne peux que PROPOSER une réaffectation (outil propose_fleet_reallocation). C'est l'opérateur qui l'applique.
- Pour toute question réglementaire, utilise search_regulations et cite le texte et l'article.
- Réponds en français, de façon brève et structurée, avec les chiffres et leurs unités."""


@dataclass
class AssistantAnswer:
    reponse: str
    trace_id: str
    outils: list[dict] = field(default_factory=list)
    recommandations: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)


def ask(question: str) -> AssistantAnswer:
    trace = store.start_trace("superviseur")
    before = set(store.RECOMMENDATIONS)
    model = llm.get_llm().bind_tools(TOOLS)
    messages = [SystemMessage(SYSTEM), HumanMessage(question)]
    called: list[dict] = []
    reply = None

    for _ in range(MAX_STEPS):
        started = time.perf_counter()
        reply = model.invoke(messages)
        messages.append(reply)
        store.record("orchestrator", "raisonnement", question if not called else "suite", [c["name"] for c in reply.tool_calls] or "réponse", started)
        if not reply.tool_calls:
            break
        for call in reply.tool_calls:
            tool = TOOL_MAP.get(call["name"])
            result = tool.invoke(call["args"]) if tool else f"Outil inconnu : {call['name']}"
            called.append({"name": call["name"], "args": call["args"]})
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
    else:
        reply = None

    text = reply.content if reply is not None and reply.content else "Je n'ai pas pu conclure en un nombre raisonnable d'étapes. Reformulez la demande ou précisez la zone."
    citations = [s for step in trace.etapes for s in step.sources]
    new_recos = [rid for rid in store.RECOMMENDATIONS if rid not in before]
    return AssistantAnswer(text, trace.id, called, new_recos, citations)
