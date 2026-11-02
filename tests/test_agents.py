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


def test_zones_et_derniere_surveillance(no_kb):
    client = TestClient(app)
    zones = {z["zone"]: z["niveau"] for z in client.get("/ai/zones").json()}
    assert zones == {"Dakar Plateau": "SATURE", "Almadies": "FLUIDE", "Grand Dakar": "SATURE"}
    client.post("/ai/watcher/run")
    assert len(client.get("/ai/watcher/last").json()["alertes"]) == 2


def test_simulation_fermeture_reporte_le_trafic_sans_rien_appliquer(no_kb):
    client = TestClient(app)
    sim = client.post("/ai/simulations", json={"type": "fermeture", "zone": "Almadies", "debut": "08:00", "fin": "12:00"}).json()
    avant = {z["zone"]: z["niveau_congestion"] for z in sim["avant"]}
    apres = {z["zone"]: z["niveau_congestion"] for z in sim["apres"]}
    assert apres["Almadies"] > avant["Almadies"]  # capacité réduite
    assert apres["Grand Dakar"] > avant["Grand Dakar"]  # report vers la zone voisine
    assert apres["Dakar Plateau"] == avant["Dakar Plateau"]  # zone non voisine
    assert sim["indicateurs"]["temps_parcours_pct"] > 0
    # Le scénario est vérifié par l'agent Politique ; sans texte applicable : NON_COUVERT
    assert sim["mesures"] and sim["mesures"][0]["verdict"] == "NON_COUVERT"
    assert not store.RECOMMENDATIONS  # bac à sable : aucune recommandation créée
    assert client.get(f"/ai/simulations/{sim['id']}").status_code == 200
    assert client.get(f"/ai/traces/{sim['trace_id']}").json()["nature"] == "simulation"


def test_simulation_renfort_evenement_et_validation(no_kb):
    client = TestClient(app)
    renfort = client.post("/ai/simulations", json={"type": "renfort", "zone": "Grand Dakar", "nb_bus": 4}).json()
    gd = lambda etats: next(z for z in etats if z["zone"] == "Grand Dakar")["niveau_congestion"]
    assert gd(renfort["apres"]) < gd(renfort["avant"])
    event = client.post("/ai/simulations", json={"type": "evenement", "zone": "Almadies", "participants": 20000}).json()
    assert event["indicateurs"]["personnes_concernees"] >= 20000
    assert client.post("/ai/simulations", json={"type": "fermeture", "zone": "Inconnue"}).status_code == 422
    assert client.post("/ai/simulations", json={"type": "fermeture", "zone": "Almadies", "debut": "25:00"}).status_code == 422


class MemoryBackend:
    """Stockage factice : garde les lignes comme le ferait PostgreSQL."""

    def __init__(self):
        self.rows = {}

    def load(self):
        return [(t, i, d) for (t, i), d in self.rows.items()]

    def save(self, rows):
        for t, i, d in rows:
            self.rows[(t, i)] = json.loads(json.dumps(d, default=str))


def test_tout_est_conserve_apres_un_redemarrage(no_kb):
    from app import persistence

    backend = MemoryBackend()
    persistence.init(backend)
    try:
        client = TestClient(app)
        reco_id = client.post("/ai/watcher/run").json()["alertes"][0]["recommendation_id"]
        client.post(f"/ai/recommendations/{reco_id}/decision", json={"decision": "rejeter", "motif": "Bus en maintenance"})
        sim_id = client.post("/ai/simulations", json={"type": "fermeture", "zone": "Almadies"}).json()["id"]
        kinds = {t for t, _ in backend.rows}
        assert kinds == {"trace", "recommandation", "manque", "simulation", "etat"}

        store.reset()  # redémarrage du service
        persistence.init(backend)
        assert store.RECOMMENDATIONS[reco_id].statut == "REJETEE"
        assert "Bus en maintenance" in store.RECOMMENDATIONS[reco_id].justification
        assert client.get(f"/ai/simulations/{sim_id}").status_code == 200
        assert len(client.get("/ai/watcher/last").json()["alertes"]) == 2
        trace_id = store.RECOMMENDATIONS[reco_id].trace_id
        assert client.get(f"/ai/traces/{trace_id}").json()["etapes"]
    finally:
        persistence.init(None)


def test_alerte_acquittee_puis_transmise_avec_plan(no_kb):
    client = TestClient(app)
    alerte = client.post("/ai/watcher/run").json()["alertes"][0]
    assert alerte["statut"] == "NOUVELLE" and alerte["plan_contingence"]
    url = f"/ai/alerts/{alerte['id']}/action"
    assert client.post(url, json={"action": "acquitter", "par": "gest@x"}).json()["statut"] == "ACQUITTEE"
    assert client.post(url, json={"action": "acquitter", "par": "gest@x"}).status_code == 409
    assert client.post(url, json={"action": "transmettre", "par": "gest@x"}).status_code == 422
    t = client.post(url, json={"action": "transmettre", "par": "gest@x", "destinataire": "Police municipale"}).json()
    assert t["statut"] == "TRANSMISE" and len(t["historique"]) == 2
    assert client.get("/ai/watcher/last").json()["alertes"][0]["statut"] == "TRANSMISE"
    assert client.post("/ai/alerts/A-inconnue/action", json={"action": "acquitter", "par": "x"}).status_code == 404


def test_tension_par_arret():
    arrets = TestClient(app).get("/ai/stops").json()
    assert arrets[0]["tension"] >= arrets[-1]["tension"]
    colobane = next(a for a in arrets if a["arret"] == "Rond-point Colobane")
    assert colobane["offre_par_heure"] == 7 * 60 and colobane["niveau"] == "SATURE"


def test_inventaire_de_la_base_de_connaissances():
    d = TestClient(app).get("/ai/kb/documents").json()
    assert len(d["documents"]) >= 20 and {"id", "statut", "passages"} <= set(d["documents"][0])
    assert d["indexation"]["etat"] in ("inactive", "en_cours", "terminee", "echec")
