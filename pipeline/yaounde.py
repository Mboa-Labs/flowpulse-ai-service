"""Transposition des profils de mobilité de Dakar sur les 7 communes d'arrondissement de Yaoundé.

Aucune donnée d'opérateur camerounais n'est accessible : FlowPulse est validé sur les données réelles et ouvertes
du D4D-Sénégal (Dakar, 2013), puis présenté sur Yaoundé. Chaque commune reçoit le profil horaire réel d'un
arrondissement de Dakar au rôle urbain comparable. Seuls les profils et l'indice de tension (relatif à chaque zone)
sont repris ; les volumes ne sont pas ajustés et ne décrivent pas Yaoundé. Les positions sont approximatives.
"""

# Commune de Yaoundé → (arrondissement de Dakar dont le profil est repris, rôle urbain, longitude, latitude)
CORRESPONDANCE = {
    "Yaoundé I": ("DAKAR PLATEAU", "Centre administratif et d'affaires (Nlongkak, Bastos, ministères)", 11.515, 3.890),
    "Yaoundé II": ("GRAND DAKAR", "Marchés et quartiers denses (Mokolo, Tsinga, Briqueterie)", 11.495, 3.880),
    "Yaoundé III": ("ALMADIES", "Mixte administratif et résidentiel (Efoulan, Nsimeyong, Obili)", 11.500, 3.830),
    "Yaoundé IV": ("PIKINE DAGOUDANE", "Grande périphérie très peuplée (Kondengui, Mvan, Ekounou)", 11.540, 3.835),
    "Yaoundé V": ("PARCELLES ASSAINIES", "Résidentiel dense (Essos, Mimboman, Ngousso)", 11.545, 3.875),
    "Yaoundé VI": ("GUEDIAWAYE", "Résidentiel populaire (Biyem-Assi, Mendong, Etoug-Ebe)", 11.470, 3.835),
    "Yaoundé VII": ("RUFISQUE", "Périphérie en développement (Nkolbisson, Oyom-Abang)", 11.450, 3.875),
}

# Flotte, lignes et arrêts de démonstration : aucun exploitant n'a fourni de données
FLOTTE = {
    "Yaoundé I": (["Ligne 1 Poste centrale – Mvan", "Ligne 4 Poste centrale – Nkolbisson"], 4),
    "Yaoundé II": (["Ligne 2 Mokolo – Essos", "Ligne 4 Poste centrale – Nkolbisson"], 3),
    "Yaoundé III": (["Ligne 5 Efoulan – Poste centrale"], 2),
    "Yaoundé IV": (["Ligne 1 Poste centrale – Mvan", "Ligne 6 Ekounou – Mokolo"], 4),
    "Yaoundé V": (["Ligne 2 Mokolo – Essos"], 3),
    "Yaoundé VI": (["Ligne 3 Biyem-Assi – Poste centrale"], 3),
    "Yaoundé VII": (["Ligne 4 Poste centrale – Nkolbisson"], 2),
}

ARRETS = [
    {"arret": "Poste centrale", "zone": "Yaoundé I", "ligne": "Ligne 1 Poste centrale – Mvan", "demande_par_heure": 590, "bus_par_heure": 7},
    {"arret": "Carrefour Warda", "zone": "Yaoundé I", "ligne": "Ligne 4 Poste centrale – Nkolbisson", "demande_par_heure": 415, "bus_par_heure": 6},
    {"arret": "Marché Mokolo", "zone": "Yaoundé II", "ligne": "Ligne 2 Mokolo – Essos", "demande_par_heure": 455, "bus_par_heure": 8},
    {"arret": "Mvan", "zone": "Yaoundé IV", "ligne": "Ligne 1 Poste centrale – Mvan", "demande_par_heure": 355, "bus_par_heure": 7},
    {"arret": "Ekounou", "zone": "Yaoundé IV", "ligne": "Ligne 6 Ekounou – Mokolo", "demande_par_heure": 250, "bus_par_heure": 6},
    {"arret": "Essos", "zone": "Yaoundé V", "ligne": "Ligne 2 Mokolo – Essos", "demande_par_heure": 180, "bus_par_heure": 5},
    {"arret": "Biyem-Assi", "zone": "Yaoundé VI", "ligne": "Ligne 3 Biyem-Assi – Poste centrale", "demande_par_heure": 130, "bus_par_heure": 4},
    {"arret": "Nkolbisson", "zone": "Yaoundé VII", "ligne": "Ligne 4 Poste centrale – Nkolbisson", "demande_par_heure": 95, "bus_par_heure": 4},
]

# Journées proposées : les dates sont celles de Dakar en 2013 ; le libellé dit quel profil est rejoué
JOURNEES = [
    {"t": "2013-11-12T18:00", "libelle": "Mardi ordinaire, pointe du soir"},
    {"t": "2013-11-12T12:00", "libelle": "Mardi ordinaire, mi-journée"},
    {"t": "2013-12-31T21:00", "libelle": "Soirée du 31 décembre"},
    {"t": "2013-12-22T20:00", "libelle": "Grand rassemblement religieux (profil : Magal 2013)"},
    {"t": "2013-10-15T12:00", "libelle": "Fête religieuse (profil : Tabaski 2013)"},
    {"t": "2013-08-08T12:00", "libelle": "Fête de fin de jeûne (profil : Korité 2013)"},
]

MENTION = ("Profils de mobilité réels de Dakar (D4D-Sénégal, 2013) transposés sur les 7 communes de Yaoundé, "
           "en attendant les données d'un opérateur camerounais")
