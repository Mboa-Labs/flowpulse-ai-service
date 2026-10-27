import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# 1. Définition des Outils Globaux de la Plateforme FlowPulse
@tool
def get_traffic_data(zone_name: str) -> str:
    """Récupère les métriques de trafic (vitesse, congestion, flux) pour une zone géographique."""
    traffic_database = {
        "Dakar Plateau": {"vitesse_moyenne": 12.5, "niveau_congestion": 88, "vehicules_par_heure": 4500},
        "Almadies": {"vitesse_moyenne": 35.0, "niveau_congestion": 30, "vehicules_par_heure": 1200},
        "Grand Dakar": {"vitesse_moyenne": 10.0, "niveau_congestion": 92, "vehicules_par_heure": 5100}
    }
    data = traffic_database.get(zone_name)
    if not data:
        return f"Aucune donnée trouvée pour la zone {zone_name}. Zones disponibles : Dakar Plateau, Almadies, Grand Dakar."
    return f"Zone: {zone_name} | Vitesse: {data['vitesse_moyenne']} km/h | Congestion: {data['niveau_congestion']}% | Flux: {data['vehicules_par_heure']} véh/h"

@tool
def get_bus_fleet_status(zone_name: str) -> str:
    """Récupère l'état des bus disponibles en réserve et les lignes pour une zone."""
    bus_database = {
        "Grand Dakar": {"lignes_actives": ["Ligne 03", "Ligne 14"], "bus_en_reserve": 4, "capacite": 60},
        "Dakar Plateau": {"lignes_actives": ["Ligne 01", "Ligne 05"], "bus_en_reserve": 2, "capacite": 60},
        "Almadies": {"lignes_actives": ["Ligne 08"], "bus_en_reserve": 5, "capacite": 60}
    }
    data = bus_database.get(zone_name)
    if not data:
        return f"Aucune information de flotte pour la zone {zone_name}."
    return f"Zone: {zone_name} | Lignes: {', '.join(data['lignes_actives'])} | Bus en réserve: {data['bus_en_reserve']}"

@tool
def apply_fleet_reallocation(zone_name: str, num_bus_to_add: int, target_line: str) -> str:
    """Déclenche le déplacement de bus de la réserve vers une ligne en tension dans une zone."""
    return f"Succès : {num_bus_to_add} bus ont été redéployés vers la {target_line} à {zone_name} pour absorber l'affluence."


if __name__ == "__main__":
    print("=" * 65)
    print(" système central FlowPulse ")
    print("=" * 65)
    print("Tapez vos instructions (ex: 'Vérifie le trafic à Grand Dakar et ajoute des bus si besoin').")
    print("Tapez 'quitter' ou 'exit' pour fermer la session.\n")
    
    # Initialisation du LLM et des outils
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = [get_traffic_data, get_bus_fleet_status, apply_fleet_reallocation]
    llm_with_tools = llm.bind_tools(tools)
    
    # Boucle de conversation interactive
    while True:
        try:
            user_query = input("\n[Gestionnaire / Opérateur] > ")
            if user_query.lower() in ["quitter", "exit", "quit"]:
                print("Fermeture de la session FlowPulse. À bientôt !")
                break
            
            if not user_query.strip():
                continue
                
            print("\n Analyse et traitement par l'Orchestrateur IA...")
            response = llm_with_tools.invoke(user_query)
            
            # Si l'agent décide d'appeler des outils
            if response.tool_calls:
                tool_results = []
                for tool_call in response.tool_calls:
                    print(f"   [Action Agent] Appel de l'outil : {tool_call['name']} ({tool_call['args']})")
                    
                    if tool_call['name'] == "get_traffic_data":
                        res = get_traffic_data.invoke(tool_call['args'])
                    elif tool_call['name'] == "get_bus_fleet_status":
                        res = get_bus_fleet_status.invoke(tool_call['args'])
                    elif tool_call['name'] == "apply_fleet_reallocation":
                        res = apply_fleet_reallocation.invoke(tool_call['args'])
                    else:
                        res = "Outil inconnu."
                        
                    print(f"  [Donnée reçue] : {res}")
                    tool_results.append(res)
                    
                # Synthèse finale de l'agent après exécution des outils
                final_prompt = (
                    f"L'utilisateur a demandé : '{user_query}'. "
                    f"Voici les résultats des actions menées par les sous-systèmes : {tool_results}. "
                    "Rédige une réponse claire, structurée et professionnelle pour l'opérateur humain."
                )
                final_response = llm.invoke(final_prompt)
                print(f"\n [FlowPulse Assistant] :\n{final_response.content}")
            else:
                # Réponse directe sans outil
                print(f"\n [FlowPulse Assistant] :\n{response.content}")
                
        except KeyboardInterrupt:
            print("\nFermeture de la session FlowPulse. À bientôt !")
            break
        except Exception as e:
            print(f"\n Une erreur est survenue : {e}")