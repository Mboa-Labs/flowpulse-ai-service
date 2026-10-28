"""Tests des agents sans Ollama : le modèle de langage est remplacé par un faux modèle scripté."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app import kb
from app.agents import llm, optimizer, orchestrator, policy, store, watcher
from app.main import app


class FakeLLM:
    """Renvoie des réponses prédéfinies, dans l'ordre, et garde les messages reçus."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.received = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.received.append(list(messages) if isinstance(messages, list) else messages)
        return self.replies.pop(0)


def passage(doc_id="CMR-DEC-001", score=0.8):
    return kb.Passage("La Communauté urbaine organise le transport public…", score, doc_id, "Code général des CTD", "Loi n° 2019/024", "Article 12", "kb_reglementaire")


@pytest.fixture(autouse=True)
def clean_store():
    store.reset()
    yield
    store.reset()


@pytest.fixture
def no_kb(monkeypatch):
    monkeypatch.setattr(kb, "search", lambda *a, **k: [])


def test_renfort_calcule_dans_la_limite_de_la_reserve():
    assert optimizer.buses_needed(92, 4) == 3
    assert optimizer.buses_needed(88, 2) == 2
    assert optimizer.buses_needed(65, 5) == 0


def test_watcher_alerte_et_propose_sans_jamais_appliquer(no_kb):
    trace_id, alerts = watcher.run()
    assert {a.zone: a.niveau for a in alerts} == {"Dakar Plateau": "SATURE", "Grand Dakar": "SATURE"}
    recos = list(store.RECOMMENDATIONS.values())
    assert len(recos) == 2
    assert all(r.statut == "PROPOSEE" for r in recos)
    assert {r.zone: r.nb_bus for r in recos} == {"Dakar Plateau": 2, "Grand Dakar": 3}
    # Sans texte applicable : verdict NON_COUVERT et manque réglementaire enregistré
    assert all(r.conformite == "NON_COUVERT" for r in recos)
    assert len(store.GAPS) == 2
    assert store.TRACES[trace_id].etapes


def test_policy_rend_un_verdict_source(monkeypatch):
    monkeypatch.setattr(kb, "search", lambda *a, **k: [passage(), passage("CMR-DP-001", 0.2)])
    fake = FakeLLM([AIMessage(content=json.dumps({"verdict": "CONFORME_SOUS_RESERVE", "justification": "Article 12 du Code des CTD.", "citations": [1]}))])
    monkeypatch.setattr(llm, "get_llm", lambda json_mode=False: fake)
    result = policy.check("Déplacer 2 bus vers la ligne 03")
    assert result.verdict == "CONFORME_SOUS_RESERVE"
    # Le passage sous le seuil de pertinence n'est pas transmis au modèle
    assert [c["doc_id"] for c in result.citations] == ["CMR-DEC-001"]


def test_policy_reponse_illisible_donne_non_couvert(monkeypatch):
    monkeypatch.setattr(kb, "search", lambda *a, **k: [passage()])
    monkeypatch.setattr(llm, "get_llm", lambda json_mode=False: FakeLLM([AIMessage(content="pas du json")]))
    assert policy.check("Déplacer 2 bus").verdict == "NON_COUVERT"


def test_orchestrator_renvoie_les_resultats_des_outils_au_modele(monkeypatch, no_kb):
    fake = FakeLLM([
        AIMessage(content="", tool_calls=[{"name": "get_traffic_data", "args": {"zone_name": "Grand Dakar"}, "id": "c1"}]),
        AIMessage(content="", tool_calls=[
            {"name": "get_bus_fleet_status", "args": {"zone_name": "Grand Dakar"}, "id": "c2"},
            {"name": "propose_fleet_reallocation", "args": {"zone_name": "Grand Dakar", "target_line": "Ligne 03", "num_bus_to_add": 3}, "id": "c3"},
        ]),
        AIMessage(content="Congestion de 92 % à Grand Dakar : je propose 3 bus sur la Ligne 03, à valider par l'opérateur."),
    ])
    monkeypatch.setattr(llm, "get_llm", lambda json_mode=False: fake)

    answer = orchestrator.ask("Vérifie le trafic à Grand Dakar et propose des bus si besoin")

    second_call = fake.received[1]
    tool_msgs = [m for m in second_call if isinstance(m, ToolMessage)]
    assert tool_msgs and "Congestion: 92%" in tool_msgs[0].content
    assert [c["name"] for c in answer.outils] == ["get_traffic_data", "get_bus_fleet_status", "propose_fleet_reallocation"]
    reco = store.RECOMMENDATIONS[answer.recommandations[0]]
    assert reco.statut == "PROPOSEE" and reco.nb_bus == 3
    assert "valider" in answer.reponse
    assert len(store.TRACES[answer.trace_id].etapes) >= 5


def test_seule_la_decision_humaine_applique(no_kb):
    client = TestClient(app)
    alerts = client.post("/ai/watcher/run").json()["alertes"]
    reco_id = alerts[0]["recommendation_id"]

    assert client.post(f"/ai/recommendations/{reco_id}/decision", json={"decision": "rejeter"}).status_code == 422
    applied = client.post(f"/ai/recommendations/{reco_id}/decision", json={"decision": "appliquer"})
    assert applied.json()["statut"] == "APPLIQUEE"
    assert client.post(f"/ai/recommendations/{reco_id}/decision", json={"decision": "appliquer"}).status_code == 409
    assert client.get(f"/ai/traces/{applied.json()['trace_id']}").status_code == 200
