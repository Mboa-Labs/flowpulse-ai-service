"""Console interactive du superviseur (reprend le mode conversation de agent-ai/main.py).

Usage : python -m app.cli
"""

from app.agents import orchestrator, store


def main() -> None:
    print("=" * 65)
    print(" Superviseur FlowPulse ")
    print("=" * 65)
    print("Exemple : « Vérifie le trafic à Grand Dakar et propose des bus si besoin ».")
    print("Tapez « quitter » pour fermer la session.\n")
    while True:
        try:
            question = input("[Gestionnaire / Opérateur] > ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if question.lower() in ("quitter", "exit", "quit"):
            break
        if not question:
            continue
        try:
            answer = orchestrator.ask(question)
        except Exception as e:
            print(f"\nErreur : {e} (Ollama est-il lancé avec le modèle configuré ?)\n")
            continue
        for call in answer.outils:
            print(f"   [outil] {call['name']} {call['args']}")
        print(f"\n[FlowPulse] {answer.reponse}\n")
        for rid in answer.recommandations:
            r = store.RECOMMENDATIONS[rid]
            print(f"   [recommandation {r.id}] {r.statut} · {r.conformite} · {r.description}")
        print(f"   [trace] {answer.trace_id}\n")
    print("Fermeture de la session FlowPulse.")


if __name__ == "__main__":
    main()
