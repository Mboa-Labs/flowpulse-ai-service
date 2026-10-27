import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# 1. Définition de l'outil avec le décorateur moderne @tool
@tool
def get_traffic_data(zone_name: str) -> str:
    """Récupère les métriques de trafic (vitesse, congestion, flux) pour une zone géographique donnée."""
    traffic_database = {
        "Dakar Plateau": {"vitesse_moyenne": 12.5, "niveau_congestion": 88, "vehicules_par_heure": 4500},
        "Almadies": {"vitesse_moyenne": 35.0, "niveau_congestion": 30, "vehicules_par_heure": 1200},
        "Grand Dakar": {"vitesse_moyenne": 10.0, "niveau_congestion": 92, "vehicules_par_heure": 5100}
    }
    
    data = traffic_database.get(zone_name)
    if not data:
        return f"Aucune donnée trouvée pour la zone {zone_name}."
    
    return (f"Zone: {zone_name} | Vitesse moyenne: {data['vitesse_moyenne']} km/h | "
            f"Taux de congestion: {data['niveau_congestion']}% | "
            f"Flux: {data['vehicules_par_heure']} véh/h")

if __name__ == "__main__":
    print("--- Démarrage de l'Agent de Détection FlowPulse ---")
    
    # 2. Initialisation du LLM
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    # 3. Association de l'outil au LLM (Bind tools)
    llm_with_tools = llm.bind_tools([get_traffic_data])
    
    # 4. Test d'appel direct avec l'agent/LLM
    query = "Analyse l'état du trafic à 'Grand Dakar' et dis-moi si une alerte de congestion critique doit être levée."
    
    print(f"\nRequête : {query}")
    response = llm_with_tools.invoke(query)
    
    # Vérification si le modèle veut appeler l'outil
    if response.tool_calls:
        print("\n[L'agent a décidé d'utiliser l'outil :]")
        for tool_call in response.tool_calls:
            print(f"Outil appelé : {tool_call['name']} avec les arguments {tool_call['args']}")
            
            # Exécution de l'outil simulé
            if tool_call['name'] == "get_traffic_data":
                tool_result = get_traffic_data.invoke(tool_call['args'])
                print(f"\n[Résultat récupéré :] {tool_result}")
                
                # Envoi du résultat final pour analyse
                final_response = llm.invoke(f"Voici les données de trafic pour la zone : {tool_result}. Rédige un rapport d'alerte critique pour la ville.")
                print("\n--- Rapport Final de l'Agent ---")
                print(final_response.content)
    else:
        print(response.content)