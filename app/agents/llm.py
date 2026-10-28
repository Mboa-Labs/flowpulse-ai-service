"""Accès au modèle de langage local (Ollama). Aucune donnée n'est envoyée à un service externe."""

from __future__ import annotations

from app.config import settings


def get_llm(json_mode: bool = False):
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_url,
        temperature=0,
        format="json" if json_mode else None,
    )
