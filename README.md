# FlowPulse — Service IA

Service IA de [FlowPulse](https://github.com/Mboa-Labs/flowpulse) : FastAPI, Ollama (LLM local), ChromaDB.

Il accueille le pipeline de données, les modèles et les agents (Watcher, Optimizer, Simulator, Policy, Orchestrator). Le socle actuel expose :

- `GET /health` : état du service, d'Ollama et de la base de connaissances
- `GET /ai/kb/search` : passages de la base de connaissances avec document et article, pour que les agents citent leurs sources

La base de connaissances est construite par le dépôt [flowpulse-knowledge-base](https://github.com/Mboa-Labs/flowpulse-knowledge-base).

## Lancer

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows (Linux/macOS : source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload                       # http://localhost:8000/docs
pytest
```

Variables (préfixe `FLOWPULSE_`) : `OLLAMA_URL`, `LLM_MODEL`, `EMBED_MODEL`, `CHROMA_DIR`, `BACKEND_URL`.
Par défaut, `CHROMA_DIR` pointe vers le dépôt voisin `../flowpulse-knowledge-base/chroma`.
