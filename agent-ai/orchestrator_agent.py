import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# 1. Outils pour l'orchestrateur
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
        return f"Aucune donnée trouvée pour la zone {zone_name}."
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
    return f"Succès : {num_bus_to_add} bus ont été redéployés vers la {target_line} à {zone_name}."


if __name__ == "__main__":
    print("--- Démarrage de l'Agent Orchestrateur FlowPulse (Superviseur) ---")
    
    # 2. Initialisation du LLM central
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    # 3. L'orchestrateur a accès à TOUS les outils
    tools = [get_traffic_data, get_bus_fleet_status, apply_fleet_reallocation]
    llm_with_tools = llm.bind_tools(tools)
    
    # 4. Requête globale de l'utilisateur
    user_query = (
        "Bonjour, j'aimerais que tu vérifies la situation à 'Grand Dakar'. "
        "Si la congestion est trop forte, regarde l'état de nos bus en réserve et "
        "prends la décision de réaffecter des bus sur la ligne la plus adaptée pour régler le problème."
    )
    
    print(f"\n[Utilisateur / Gestionnaire] : {user_query}\n")
    response = llm_with_tools.invoke(user_query)
    
    # 5. Boucle d'exécution des outils si l'orchestrateur décide d'agir
    if response.tool_calls:
        print("[L'Orchestrateur coordonne les actions et appelle les outils :]")
        
        tool_results = []
        for tool_call in response.tool_calls:
            print(f"-> Appel de l'outil : {tool_call['name']} avec {tool_call['args']}")
            
            if tool_call['name'] == "get_traffic_data":
                res = get_traffic_data.invoke(tool_call['args'])
            elif tool_call['name'] == "get_bus_fleet_status":
                res = get_bus_fleet_status.invoke(tool_call['args'])
            elif tool_call['name'] == "apply_fleet_reallocation":
                res = apply_fleet_reallocation.invoke(tool_call['args'])
            else:
                res = "Outil inconnu."
                
            print(f"   [Résultat] : {res}")
            tool_results.append(res)
            
        # 6. Génération de la réponse finale de synthèse
        final_prompt = (
            f"L'utilisateur a demandé : '{user_query}'. "
            f"Voici les résultats des actions menées par les sous-systèmes : {tool_results}. "
            "Rédige une réponse claire, professionnelle et de synthèse pour l'opérateur humain."
        )
        final_response = llm.invoke(final_prompt)
        print("\n--- Réponse Finale de l'Orchestrateur ---")
        print(final_response.content)
    else:
        print(response.content)