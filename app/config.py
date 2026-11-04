"""Configuration du service IA (variables d'environnement préfixées FLOWPULSE_)."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLOWPULSE_")

    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"  # 14b sur un serveur avec carte graphique
    embed_model: str = "nomic-embed-text"
    # Fils de calcul du modèle : à régler sur la limite de processeurs du conteneur Ollama. Par défaut, Ollama prend
    # tous les cœurs de la machine ; bridé à 3 cœurs, il ralentit alors fortement (mesuré : 1 jeton/s au lieu de 7).
    llm_threads: Optional[int] = None
    chroma_dir: Path = Path(__file__).resolve().parents[2] / "flowpulse-knowledge-base" / "chroma"
    backend_url: str = "http://localhost:8080"
    # PostgreSQL pour conserver traces, recommandations, manques et simulations ; vide = en mémoire
    database_url: str = ""
    # Territoire présenté : « yaounde » (profils de Dakar transposés, par défaut) ou « dakar » (données réelles brutes)
    territoire: str = "yaounde"
    # Sorties du pipeline D4D ; vide = déduit du territoire ; absentes = données de démonstration
    donnees_dir: Optional[Path] = None

    def dossier_donnees(self) -> Path:
        if self.donnees_dir:
            return self.donnees_dir
        sortie = Path(__file__).resolve().parents[1] / "pipeline" / "sortie"
        yaounde = sortie / "yaounde"
        return yaounde if self.territoire == "yaounde" and (yaounde / "serie_zone_heure.parquet").exists() else sortie


settings = Settings()
