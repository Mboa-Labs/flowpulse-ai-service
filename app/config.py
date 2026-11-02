"""Configuration du service IA (variables d'environnement préfixées FLOWPULSE_)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLOWPULSE_")

    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"  # 14b sur un serveur avec carte graphique
    embed_model: str = "nomic-embed-text"
    chroma_dir: Path = Path(__file__).resolve().parents[2] / "flowpulse-knowledge-base" / "chroma"
    backend_url: str = "http://localhost:8080"
    # PostgreSQL pour conserver traces, recommandations, manques et simulations ; vide = en mémoire
    database_url: str = ""
    # Sorties du pipeline D4D (séries, zones, modèles) ; absentes = données de démonstration
    donnees_dir: Path = Path(__file__).resolve().parents[1] / "pipeline" / "sortie"


settings = Settings()
