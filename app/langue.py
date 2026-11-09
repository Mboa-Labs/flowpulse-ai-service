"""Langue des contenus produits par les agents (réponses, plans, descriptions, justifications).

Le frontend envoie l'en-tête Accept-Language (en ou fr), que le backend transmet au service IA.
Sans en-tête, le français reste la langue par défaut (appels internes, tests).
"""

from __future__ import annotations

from contextvars import ContextVar

LANGUE: ContextVar[str] = ContextVar("langue", default="fr")


def depuis_entete(valeur: str | None) -> str:
    return "en" if (valeur or "").strip().lower().startswith("en") else "fr"


def actuelle() -> str:
    return LANGUE.get()


def tr(fr: str, en: str) -> str:
    """Choisit le texte selon la langue de la requête en cours."""
    return en if LANGUE.get() == "en" else fr


def nom_langue() -> str:
    return "English" if LANGUE.get() == "en" else "français"
