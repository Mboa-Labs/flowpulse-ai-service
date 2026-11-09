"""Tests des agents sans Ollama : le modèle de langage est remplacé par un faux modèle scripté."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app import kb
from app.agents import data, llm, optimizer, orchestrator, policy, store, watcher
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
    # Sans texte applicable : verdict NON_COUVERT et un seul manque (les deux zones relèvent des mêmes textes)
    assert all(r.conformite == "NON_COUVERT" for r in recos)
    assert len(store.GAPS) == 1
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


def test_inventaire_de_la_base_de_connaissances(tmp_path, monkeypatch):
    # Inventaire fictif : le test ne dépend pas du dépôt de la base de connaissances
    entetes = "id,dossier,fichier,titre,reference,type,autorite,date_adoption,domaine,pays,url_source,statut,responsable,notes"
    (tmp_path / "sources.csv").write_text(
        entetes + "\nSEN-DP-001,Senegal,loi.pdf,Loi sur les données personnelles,Loi 2008-12,LOI,État,2008-01-25,"
        "donnees_personnelles,Sénégal,https://exemple.sn,collecte,,\n", encoding="utf-8")
    monkeypatch.setattr(kb.settings, "chroma_dir", tmp_path / "chroma")
    kb._client.cache_clear()
    try:
        d = TestClient(app).get("/ai/kb/documents").json()
    finally:
        kb._client.cache_clear()
    assert [x["id"] for x in d["documents"]] == ["SEN-DP-001"] and d["documents"][0]["passages"] == 0
    assert d["indexation"]["etat"] in ("inactive", "en_cours", "terminee", "echec")


def test_une_seule_recommandation_en_attente_par_zone(no_kb):
    client = TestClient(app)
    premiere = {a["zone"]: a["recommendation_id"] for a in client.post("/ai/watcher/run").json()["alertes"]}
    seconde = {a["zone"]: a["recommendation_id"] for a in client.post("/ai/watcher/run").json()["alertes"]}
    recos = {r["id"]: r for r in client.get("/ai/recommendations").json()}
    for zone, rid in premiere.items():
        assert recos[rid]["statut"] == "REMPLACEE" and seconde[zone] in recos[rid]["justification"]
        assert recos[seconde[zone]]["statut"] == "PROPOSEE"
    assert sum(r["statut"] == "PROPOSEE" for r in recos.values()) == 2
    # Une recommandation remplacée ne peut plus être appliquée
    assert client.post(f"/ai/recommendations/{premiere['Grand Dakar']}/decision", json={"decision": "appliquer"}).status_code == 409


@pytest.fixture
def donnees_reelles(tmp_path, monkeypatch):
    """Petites sorties de pipeline fictives : 2 zones, 3 jours, sans modèle de prévision."""
    import pandas as pd

    t = pd.date_range("2013-11-11", "2013-11-13 23:00", freq="h")
    lignes = []
    for arr_id, zone, pic in ((3, "Grand Dakar", 92), (4, "Dakar Plateau", 70)):
        indice = [pic if h.hour == 18 else 40 for h in t]
        lignes.append(pd.DataFrame({"t": t, "arr_id": arr_id, "zone": zone, "appels": [i * 100 for i in indice],
                                    "antennes_actives": 70, "presents_echantillon": 500, "arrivees": 50, "departs": 40,
                                    "indice_tension": indice, "ecart_habituel": 1.0}))
    pd.concat(lignes).to_parquet(tmp_path / "serie_zone_heure.parquet", index=False)
    (tmp_path / "zones_dakar.csv").write_text(
        "arr_id;zone;departement;antennes;lon;lat\n3;Grand Dakar;DAKAR;73;-17.45;14.70\n4;Dakar Plateau;DAKAR;74;-17.43;14.67\n",
        encoding="utf-8")
    (tmp_path / "territoire.json").write_text(json.dumps({
        "nom": "Yaoundé", "pays": "Cameroun", "mention": "Profils transposés",
        "flotte": {"Grand Dakar": {"lignes_actives": ["Ligne 1 Poste centrale – Mvan"], "bus_en_reserve": 3, "capacite": 60}},
        "journees": [{"t": "2013-11-12T18:00", "libelle": "Mardi ordinaire"}]}), encoding="utf-8")
    assert data.activer(tmp_path)
    yield
    monkeypatch.setattr(data, "REEL", None)


def test_donnees_reelles_et_horloge(no_kb, donnees_reelles):
    client = TestClient(app)
    horloge = client.get("/ai/horloge").json()
    assert horloge["source"] == "d4d" and horloge["territoire"] == "Yaoundé" and horloge["journees"][0]["libelle"] == "Mardi ordinaire"
    assert data.fleet("Grand Dakar")["lignes_actives"] == ["Ligne 1 Poste centrale – Mvan"]
    assert client.post("/ai/horloge", json={"t": "2013-11-12T18:00"}).json()["t"] == "2013-11-12T18:00"
    zones = {z["zone"]: z for z in client.get("/ai/zones").json()}
    assert zones["Grand Dakar"]["niveau_congestion"] == 92 and zones["Grand Dakar"]["lon"] == -17.45
    alertes = client.post("/ai/watcher/run").json()["alertes"]
    assert [a["zone"] for a in alertes] == ["Grand Dakar"] and alertes[0]["heure"] == "2013-11-12T18:00"
    # Hors période ou heure inconnue : refusé
    assert client.post("/ai/horloge", json={"t": "2013-06-01T10:00"}).status_code == 422
    serie = client.get("/ai/zones/serie", params={"zone": "Grand Dakar", "heures": 3}).json()
    assert [p["observe"] for p in serie] == [40, 40, 40, 92]


def test_verdict_reutilise_pour_un_meme_type_de_decision(monkeypatch):
    monkeypatch.setattr(kb, "search", lambda *a, **k: [passage(), passage(), passage(), passage("CMR-TEL-001", 0.7)])
    fake = FakeLLM([AIMessage(content=json.dumps({"verdict": "CONFORME", "justification": "Article 12.", "citations": [1]}))])
    monkeypatch.setattr(llm, "get_llm", lambda json_mode=False: fake)
    store.start_trace("test")
    premier = policy.check("Renfort de 2 bus à Grand Dakar", "reaffectation_bus_reserve")
    second = policy.check("Renfort de 3 bus à Almadies", "reaffectation_bus_reserve")
    assert premier.verdict == second.verdict == "CONFORME" and second.citations == premier.citations
    assert len(fake.received) == 1  # le modèle n'a lu les textes qu'une fois
    assert store.current_trace().etapes[-1].action == "verdict_reutilise"
    # Au plus 2 extraits d'un même document
    retenus = policy._selection([passage(), passage(), passage(), passage("CMR-TEL-001", 0.7)])
    assert [p.doc_id for p in retenus] == ["CMR-DEC-001", "CMR-DEC-001", "CMR-TEL-001"]


def test_objets_d_un_autre_territoire_masques(no_kb, donnees_reelles):
    store.set_state("derniere_surveillance", {"trace_id": "T-ancien", "alertes": [
        {"zone": "Almadies", "niveau": "SATURE", "congestion": 90}, {"zone": "Grand Dakar", "niveau": "SATURE", "congestion": 92}]})
    client = TestClient(app)
    alertes = client.get("/ai/watcher/last").json()["alertes"]
    assert [a["zone"] for a in alertes] == ["Grand Dakar"]  # Almadies n'existe pas dans ce territoire
    zone = {z["zone"]: z for z in client.get("/ai/zones").json()}["Grand Dakar"]
    assert zone["volumes_representatifs"] is True  # pas de transposition dans ce jeu de test
    assert isinstance(zone["tendance_1h"], int)



def test_simulation_sur_un_lieu_reel(no_kb, monkeypatch):
    a, b = data.zones()[:2]  # zones du territoire chargé (démonstration ou jeu de test)
    axe = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
           "properties": {"id": "route-corniche", "nom": "Route de la Corniche", "type": "route", "zone": a,
                          "parts": {a: 0.7, b: 0.3}}}
    monkeypatch.setattr(data, "lieux", lambda: [axe])
    client = TestClient(app)
    assert client.get("/ai/lieux").json()["features"][0]["properties"]["id"] == "route-corniche"
    sim = client.post("/ai/simulations", json={"type": "fermeture", "zone": b, "lieu": "route-corniche"}).json()
    assert sim["scenario"]["zone"] == a  # la zone découle du lieu
    assert "Route de la Corniche" in sim["libelle"]
    assert any(f"{a} (70 %)" in h for h in sim["hypotheses"])
    assert any("OpenStreetMap" in h for h in sim["hypotheses"])
    assert client.post("/ai/simulations", json={"type": "fermeture", "zone": a, "lieu": "inconnu"}).status_code == 422


def test_vue_d_ensemble_classe_les_zones_de_la_plus_tendue_a_la_plus_calme():
    from app.agents import tools
    out = tools.get_city_overview.invoke({})
    lignes = [l for l in out.splitlines() if l.startswith("- ")]
    assert len(lignes) == len(data.zones())
    valeurs = [int(l.split(" : ")[1].split("/")[0]) for l in lignes]
    assert valeurs == sorted(valeurs, reverse=True)
    assert lignes[0].startswith("- Grand Dakar")


def test_renfort_a_zero_bus_remplace_par_le_besoin_calcule(no_kb):
    reco = optimizer.propose("Grand Dakar", None, 0)
    assert reco.nb_bus == 3


def test_aucun_renfort_propose_sous_le_seuil(no_kb, monkeypatch):
    zone = data.zones()[0]
    monkeypatch.setattr(data, "traffic", lambda z: {"niveau_congestion": 50, "prevision_1h": 60})
    with pytest.raises(ValueError, match="Aucune réaffectation"):
        optimizer.propose(zone)
    assert not store.RECOMMENDATIONS


def test_justification_redigee_pour_le_type_de_decision():
    # Le verdict est réutilisé pour toutes les zones : la justification ne doit nommer ni zone ni ligne
    assert "sans nommer de zone, de ligne" in policy.PROMPT


def test_contenus_en_anglais_quand_la_requete_le_demande(no_kb):
    from app import langue
    jeton = langue.LANGUE.set("en")
    try:
        plan = watcher.contingence("Grand Dakar", "SATURE", 2)
        assert plan[0].startswith("Notify the operator") and any("reserve buses" in p for p in plan)
        reco = optimizer.propose("Grand Dakar")
        assert reco.description.startswith("Move ")
    finally:
        langue.LANGUE.reset(jeton)
    assert watcher.contingence("Grand Dakar", "SATURE", 2)[0].startswith("Prévenir")


def test_langue_lue_dans_l_entete():
    from app import langue
    client = TestClient(app)
    r = client.post("/ai/simulations", json={"type": "renfort", "zone": "Grand Dakar", "nb_bus": 2}, headers={"Accept-Language": "en-GB,en;q=0.9"})
    assert r.status_code == 200 and r.json()["libelle"].startswith("Reinforcement of 2 buses")
    assert langue.depuis_entete("fr-FR") == "fr" and langue.depuis_entete(None) == "fr"


def test_consignes_en_anglais_pour_l_interface_anglaise(monkeypatch):
    from app import langue
    monkeypatch.setattr(kb, "search", lambda *a, **k: [passage()])
    fake = FakeLLM([AIMessage(content=json.dumps({"verdict": "CONFORME", "justification": "Article 12.", "citations": [1]}))])
    monkeypatch.setattr(llm, "get_llm", lambda json_mode=False: fake)
    jeton = langue.LANGUE.set("en")
    try:
        policy.check("Move 2 buses", "type_test")
    finally:
        langue.LANGUE.reset(jeton)
    assert fake.received[0].startswith("You are the regulatory compliance agent")
    assert "Always answer in English" in orchestrator.SYSTEM_EN
