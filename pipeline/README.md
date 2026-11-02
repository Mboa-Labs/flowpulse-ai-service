# Pipeline de données D4D-Sénégal

Prépare le dataset D4D-Sénégal (Orange, 2013) pour FlowPulse : exploration, nettoyage, sélection de la région de Dakar et agrégation par arrondissement et par heure.

- Les fichiers bruts sont lus **en place, en lecture seule**, sans être décompressés ni copiés.
- Seuls des **agrégats par zone** sortent du pipeline : aucune donnée individuelle.
- Les données brutes et les sorties ne vont **jamais sur GitHub** (`pipeline/sortie/` est ignoré par git).

## Ce qu'il faut

| Élément | Détail |
| --- | --- |
| Le disque du dataset | Branché, avec le dossier `data` qui contient `SET1`, `SET2`, `SET3` et `ContextData` (par exemple `E:\data`) |
| Python 3.11 ou plus | `python --version` |
| Espace libre | Environ 1 Go sur le disque du PC pour les sorties |

## Étape 1 : préparer l'environnement (une seule fois)

Dans PowerShell :

```powershell
cd "C:\Users\tiome\Desktop\AI For Good\flowpulse-ai-service"
```

Si le dossier `.venv` n'existe pas encore :

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Puis installer l'outil du pipeline (DuckDB, environ 20 Mo) :

```powershell
.venv\Scripts\python -m pip install --default-timeout=120 --retries 10 -r pipeline\requirements.txt
```

Sur Mac ou Linux, remplacer `.venv\Scripts\python` par `.venv/bin/python`.

## Étape 2 : vérifier le disque

1. Brancher le disque et l'ouvrir dans l'Explorateur.
2. Noter la lettre du lecteur (par exemple `E:`) et vérifier qu'il contient `data\SET1`, `data\SET2` et `data\ContextData`.

Si le disque n'apparaît pas dans l'Explorateur, ne jamais accepter « Initialiser » ou « Formater » : cela effacerait les données.

## Étape 3 : explorer les données

```powershell
cd "C:\Users\tiome\Desktop\AI For Good\flowpulse-ai-service"
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python -I pipeline\d4d.py explorer --source E:\data
```

Remplacer `E:\data` par l'emplacement du dossier `data` s'il est ailleurs.

- **Durée :** environ 10 minutes (lecture des 12 mois d'appels, puis de la première période de trajets).
- **Dans le terminal :** `SET1 voix (lecture des 12 mois…)`, puis `SET2 (période 1)…`, puis `Rapport : …`.
- **Ne pas fermer le terminal** pendant le traitement. Pour l'interrompre : `Ctrl + C`.

### Où sont les résultats

Dans `flowpulse-ai-service\pipeline\sortie\` :

| Fichier | Contenu |
| --- | --- |
| `exploration_d4d.md` | Le rapport : antennes et arrondissements de Dakar, volumes par mois, heures manquantes, valeurs suspectes, rythme de l'activité à Dakar (heures, jours, jours exceptionnels), doublons des trajets, décisions de nettoyage |
| `set1v_heure_antenne.parquet` | Résumé des appels par heure et par antenne émettrice (environ 15 millions de lignes au lieu de plus d'un milliard), réutilisé par l'étape d'agrégation |

Le rapport s'ouvre dans VS Code (clic droit → *Open Preview* pour l'afficher mis en forme).

## Étape 4 : nettoyage et agrégation

À venir : `pipeline\d4d.py agreger`, qui produira les séries par arrondissement de Dakar et par heure (activité, arrivées, départs, flux entre zones) utilisées par le modèle de prévision.

## En cas de problème

| Message | Cause | Solution |
| --- | --- | --- |
| `No module named 'duckdb'` | Étape 1 non faite | Refaire l'étape 1 |
| `No files found that match the pattern` | Mauvais chemin du disque | Vérifier la lettre du lecteur et le dossier `data` |
| `Out of Memory` | Mémoire du PC insuffisante | Fermer les autres applications et relancer |
| Caractères bizarres dans le terminal | Encodage de la console | Vérifier la ligne `$env:PYTHONIOENCODING = "utf-8"` |
