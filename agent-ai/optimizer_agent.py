import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# 1. Outil pour récupérer l'état des bus et des flottes disponibles
@tool
def get_bus_fleet_status(zone_name: str) -> str:
    """Récupère l'état des bus disponibles en réserve et les lignes desservant une zone donnée."""
    bus_database = {
        "Grand Dakar": {"lignes_actives": ["Ligne 03", "Ligne 14"], "bus_en_reserve": 4, "capacite_moyenne_bus": 60},
        "Dakar Plateau": {"lignes_actives": ["Ligne 01", "Ligne 05"], "bus_en_reserve": 2, "capacite_moyenne_bus": 60},
        "Almadies": {"lignes_actives": ["Ligne 08"], "bus_en_reserve": 5, "capacite_moyenne_bus": 60}
    }
    
    data = bus_database.get(zone_name)
    if not data:
        return f"Aucune information de flotte pour la zone {zone_name}."
    
    return (f"Zone: {zone_name} | Lignes présentes: {', '.join(data['lignes_actives'])} | "
            f"Bus disponibles en réserve: {data['bus_en_reserve']} | "
            f"Capacité par bus: {data['capacite_moyenne_bus']} passagers")

# 2. Outil pour simuler l'action de réaffectation (qui pourrait mettre à jour la base de données)
@tool
def apply_fleet_reallocation(zone_name: str, num_bus_to_add: int, target_line: str) -> str:
    """Déclenche le déplacement de bus de la réserve vers une ligne en tension dans une zone."""
    return (f"succès : {num_bus_to_add} bus ont été redéployés avec succès vers la {target_line} "
            f"à {zone_name} pour absorber le pic d'affluence.")

if __name__ == "__main__":
    print("--- Démarrage de l'Agent d'Optimisation des Transports (FlowPulse) ---")
    
    # 3. Initialisation du LLM
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    # 4. Association des outils à l'agent
    tools = [get_bus_fleet_status, apply_fleet_reallocation]
    llm_with_tools = llm.bind_tools(tools)
    
    # 5. Scénario de test : Suite à l'alerte sur Grand Dakar, l'agent doit réagir
    query = (
        "Une alerte critique de congestion a été levée à 'Grand Dakar'. "
        "Analyse l'état de la flotte de bus pour cette zone, calcule combien de bus de réserve "
        "nous devons envoyer sur la ligne la plus saturée (ex: Ligne 03), et exécute l'action de réaffectation."
    )
    
    print(f"\nRequête pour l'Agent d'Optimisation : {query}")
    response = llm_with_tools.invoke(query)
    
    # Gestion de l'appel des outils par l'agent
    if response.tool_calls:
        print("\n[L'agent d'optimisation utilise ses outils :]")
        for tool_call in response.tool_calls:
            print(f"Outil appelé : {tool_call['name']} avec les arguments {tool_call['args']}")
            
            if tool_call['name'] == "get_bus_fleet_status":
                tool_result = get_bus_fleet_status.invoke(tool_call['args'])
                print(f"[Résultat Flotte :] {tool_result}")
            elif tool_call['name'] == "apply_fleet_reallocation":
                tool_result = apply_fleet_reallocation.invoke(tool_call['args'])
                print(f"[Résultat Action :] {tool_result}")
        
        # Synthèse finale de l'agent
        final_response = llm.invoke("L'action de réaffectation a été effectuée. Rédige un rapport de confirmation pour l'opérateur de transport.")
        print("\n--- Rapport Final de l'Agent d'Optimisation ---")
        print(final_response.content)
    else:
        print(response.content)