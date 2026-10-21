"""Tests du socle IA, sans Ollama : on remplace le calcul des vecteurs par un vecteur déterministe."""

import pytest

from app import kb
from app.config import settings


@pytest.fixture
def fake_kb(tmp_path, monkeypatch):
    import chromadb

    monkeypatch.setattr(settings, "chroma_dir", tmp_path)
    kb._client.cache_clear()
    vectors = {"donnees": [1.0, 0.0, 0.0], "bus": [0.0, 1.0, 0.0]}
    monkeypatch.setattr(kb, "embed", lambda text: vectors["bus" if "bus" in text else "donnees"])

    col = chromadb.PersistentClient(path=str(tmp_path)).get_or_create_collection(
        "kb_reglementaire", metadata={"hnsw:space": "cosine"})
    col.add(
        ids=["CMR-DP-001-0", "CMR-TRA-002-0"],
        documents=["Les données à caractère personnel ne peuvent être traitées que…", "Les lignes de bus urbaines…"],
        embeddings=[vectors["donnees"], vectors["bus"]],
        metadatas=[
            {"doc_id": "CMR-DP-001", "titre": "Loi données personnelles", "reference": "Loi n° 2024/017",
             "article": "Article 5", "domaine": "donnees_personnelles", "country": "Cameroun"},
            {"doc_id": "CMR-TRA-002", "titre": "PNMU", "reference": "PNMU 2019", "article": "",
             "domaine": "transport_urbain", "country": "Cameroun"},
        ],
    )
    yield
    kb._client.cache_clear()


def test_search_renvoie_la_source_exacte(fake_kb):
    passages = kb.search("Peut-on utiliser ces données ?", n=1)
    assert passages[0].doc_id == "CMR-DP-001"
    assert passages[0].article == "Article 5"
    assert passages[0].score == pytest.approx(1.0)


def test_filtre_par_domaine(fake_kb):
    passages = kb.search("Peut-on utiliser ces données ?", n=2, domaine="transport_urbain")
    assert [p.doc_id for p in passages] == ["CMR-TRA-002"]


def test_collection_absente_renvoie_liste_vide(fake_kb):
    assert kb.search("question", collection="kb_manques") == []


def test_stats(fake_kb):
    assert kb.stats() == {"kb_reglementaire": 2, "kb_framework": 0, "kb_manques": 0}
