# FlowPulse — Service IA

Service IA de [FlowPulse](https://github.com/Mboa-Labs/flowpulse) : FastAPI, Ollama (modèle de langage local), ChromaDB.

Aucune donnée ne quitte le serveur : le modèle de langage tourne en local via Ollama.

## Agents

| Agent | Rôle | Modèle de langage |
| --- | --- | --- |
| Watcher (`app/agents/watcher.py`) | Surveille les zones, lève les alertes (dense ≥ 75 %, saturé ≥ 85 %) | Non : règles explicables |
| Optimizer (`app/agents/optimizer.py`) | Calcule une réaffectation de bus de réserve et la soumet à l'agent Politique | Non |
| Policy (`app/agents/policy.py`) | Vérifie la décision au regard des textes de la base de connaissances, cite le document et l'article, enregistre un manque réglementaire si aucun texte ne s'applique | Oui |
| Orchestrator (`app/agents/orchestrator.py`) | Superviseur conversationnel : choisit les outils, reçoit leurs résultats, répond | Oui |

Règle commune : **aucun agent n'applique de réaffectation**. Les agents créent des recommandations au statut `PROPOSEE` ; seule la décision humaine (`/ai/recommendations/{id}/decision`) les applique. Chaque étape est tracée (agent, action, entrées, sorties, durée, sources).

Les données de trafic et de flotte sont pour l'instant des données de démonstration (`app/agents/data.py`, zones de Dakar) ; le pipeline du dataset les remplacera.

## Routes

| Route | Rôle |
| --- | --- |
| `GET /health` | État du service, d'Ollama et de la base de connaissances |
| `GET /ai/kb/search` | Passages de la base de connaissances, avec document et article |
| `POST /ai/assistant` | Question au superviseur ; renvoie la réponse, les outils appelés, les recommandations créées, les citations et la trace |
| `POST /ai/watcher/run` | Passage de surveillance : alertes et recommandations |
| `GET /ai/recommendations`, `GET /ai/recommendations/{id}` | Recommandations |
| `POST /ai/recommendations/{id}/decision` | Décision humaine : `appliquer` ou `rejeter` (motif obligatoire) |
| `GET /ai/traces/{id}` | Raisonnement complet d'une réponse ou d'une alerte |
| `GET /ai/gaps` | Manques réglementaires détectés |

## Lancer

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

python -m venv .venv && .venv/Scripts/activate      # Windows (Linux/macOS : source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload                       # http://localhost:8000/docs
python -m app.cli                                   # superviseur en mode console
pytest                                              # tests sans Ollama (modèle simulé)
```

Variables (préfixe `FLOWPULSE_`) : `OLLAMA_URL`, `LLM_MODEL` (défaut `qwen2.5:7b`, `qwen2.5:14b` sur un serveur avec carte graphique), `EMBED_MODEL`, `CHROMA_DIR`, `BACKEND_URL`.
Par défaut, `CHROMA_DIR` pointe vers le dépôt voisin `../flowpulse-knowledge-base/chroma`.
