"""Lieux réels de Yaoundé pour les simulations : grands axes, ponts, carrefours, stades et marchés.

Source : OpenStreetMap (© contributeurs OSM, licence ODbL), extrait par l'API Overpass. Chaque lieu est rattaché
à la commune qui le contient ; un axe qui traverse plusieurs communes garde la part de sa longueur dans chacune,
pour répartir l'effet d'une fermeture. Résultat : pipeline/yaounde_lieux.geojson, lu par le service IA.

    python pipeline/yaounde_lieux.py --telecharger          # interroge Overpass puis construit le fichier
    python pipeline/yaounde_lieux.py --osm chemin/osm.json  # à partir d'un extrait déjà téléchargé
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ICI = Path(__file__).resolve().parent
COMMUNES = ICI / "yaounde_communes.geojson"
SORTIE = ICI / "yaounde_lieux.geojson"
CADRE = "3.76,11.42,3.97,11.60"  # sud, ouest, nord, est
REQUETE = f"""[out:json][timeout:200];
(way["highway"~"^(trunk|primary|secondary)$"]["name"]({CADRE});
 way["bridge"="yes"]["highway"~"^(trunk|primary|secondary|tertiary)$"]({CADRE});
 way["junction"="roundabout"]["name"]({CADRE});
 nwr["leisure"="stadium"]["name"]({CADRE});
 nwr["amenity"="marketplace"]["name"]({CADRE}););
out geom;"""
SERVEURS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
# Sélection : lieux connus de tous à Yaoundé. Clé = nom affiché ; valeur = noms OpenStreetMap correspondants.
AXES = {
    "Boulevard du 20 Mai": ["Boulevard du 20 Mai 1972"],
    "Boulevard de la Réunification": ["Boulevard de la Réunification"],
    "Boulevard du Président Paul Biya": ["Boulevard du Président Paul Biya"],
    "Boulevard Saint Jean Paul II": ["Boulevard Saint Jean Paul II"],
    "Boulevard Rodolphe Manga Bell": ["Boulevard Rodolph Manga Bell", "Boulevard Rodolphe Manga Bell"],
    "Boulevard de l'OCAM": ["Boulevard de l'OCAM"],
    "Avenue Charles Atangana": ["Avenue Charles Atangana"],
    "Avenue John Ngu Foncha": ["Avenue John Ngu Foncha"],
    "Route de Douala": ["Route de Douala"],
    "Ancienne route de Douala": ["Ancienne Route de Douala"],
    "Route de Kribi": ["Route de Kribi", "Route Yaoundé-Kribi"],
    "Route de Mbalmayo": ["Route de Mbalmayo", "Yaoundé-Mbalmayo"],
    "Route d'Obala": ["Yaounde - Obala"],
    "Route de Ngousso": ["Route de Ngousso"],
    "Nouvelle route Bastos": ["Nouvelle Route Bastos"],
    "Avenue de Biyem-Assi": ["Avenue de Biyeme Assi"],
    "Rue de Kondengui": ["Rue de Kondengui"],
}
# Ponts : ouvrages repérés sur ces axes (on garde le plus long tronçon en pont de chaque axe)
PONTS = {
    "Pont de la route de Douala": "Route de Douala",
    "Pont de l'ancienne route de Douala": "Ancienne Route de Douala",
    "Pont de la route de Kribi": "Route de Kribi",
    "Pont de Biyem-Assi": "Avenue de Biyeme Assi",
    "Pont de Kondengui": "Rue de Kondengui",
    "Pont de la nouvelle route Bastos": "Nouvelle Route Bastos",
    "Pont de l'avenue Marc Vivien Foé": "Avenue Marc Vivien Foe",
    "Pont de Mvolyé": "Avenue de Mvolye",
}
CARREFOURS = ["Place de l'Indépendance", "Place du 20 Mai", "Place Ahmadou Ahidjo", "Place John F Kennedy", "Rond-Point Bastos",
              "Rond-Point de Nlongkak", "Carrefour Vogt", "Carrefour Trois Statues", "Carrefour de la Chapelle",
              "Ekié Carrefour Six Morts", "Carrefour Messamendongo", "Tropicana Carrefour"]
STADES = {"Stade Ahmadou Ahidjo (Mfandena)": "Stade Ahmadou Ahidjo", "Stade Paul Biya (Olembé)": "Stade Omnisport Paul Biya"}
MARCHES = {"Marché Mokolo": ["Marché Mokolo"], "Marché Central": ["Marché Central", "Central Market"],
           "Marché Mfoundi": ["Marché Mfoundi A"], "Marché Mvog-Mbi": ["Marché de Mvog Mbi"],
           "Marché Mvog-Betsi": ["Marché Mvog-Betsi", "Marche Mvog betsi"], "Marché d'Essos": ["Marché d'Essos"],
           "Marché d'Ekounou": ["Marché d'Ekounou"], "Marché de Melen": ["Marché De Melen"], "Marché Acacia": ["Marché Acacia"],
           "Grand marché de Biyem-Assi": ["Grand Marché de Biyem-Assi"], "Marché de Nkolbisson": ["Marché De Nkolbisson"],
           "Marché Obili": ["Marché Obili"]}


def telecharger() -> dict:
    corps = urllib.parse.urlencode({"data": REQUETE}).encode()
    for url in SERVEURS:
        print(f"Téléchargement depuis {url}…", flush=True)
        try:
            req = urllib.request.Request(url, data=corps, headers={"User-Agent": "FlowPulse/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # serveur saturé : on essaie le suivant
            print(f"  échec : {e}", flush=True)
    sys.exit("Overpass indisponible. Réessayez plus tard, ou passez un extrait avec --osm.")


def dans(pt: tuple[float, float], anneau: list) -> bool:
    """Point dans un polygone (lancer de rayon). pt = (lon, lat)."""
    x, y = pt
    dedans = False
    for (x1, y1), (x2, y2) in zip(anneau, anneau[1:] + anneau[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            dedans = not dedans
    return dedans


def commune(pt, communes) -> str | None:
    return next((nom for nom, anneau in communes if dans(pt, anneau)), None)


def km(a, b) -> float:
    return math.hypot((a[0] - b[0]) * 111.3 * math.cos(math.radians(a[1])), (a[1] - b[1]) * 111.3)


def ident(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:70]


def construire(osm: dict) -> dict:
    geo = json.loads(COMMUNES.read_text(encoding="utf-8"))
    communes = [(f["properties"]["zone"], f["geometry"]["coordinates"][0]) for f in geo["features"]]
    routes: dict[str, list] = defaultdict(list)  # nom OSM → tronçons
    ponts: dict[str, list] = defaultdict(list)  # nom de l'axe OSM → tronçons en pont
    points: dict[str, list] = defaultdict(list)  # nom OSM → centres (carrefours, stades, marchés)

    for e in osm["elements"]:
        t = e.get("tags", {})
        nom = t.get("name")
        if not nom:
            continue
        if e["type"] == "node":
            pts = [(e["lon"], e["lat"])]
        elif "geometry" in e:
            pts = [(p["lon"], p["lat"]) for p in e["geometry"] if p]
        elif "bounds" in e:  # relation : centre de son emprise
            b = e["bounds"]
            pts = [((b["minlon"] + b["maxlon"]) / 2, (b["minlat"] + b["maxlat"]) / 2)]
        else:
            continue
        if not pts:
            continue
        centre = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        if t.get("leisure") == "stadium" or t.get("amenity") == "marketplace" or t.get("junction") == "roundabout":
            points[nom].append(centre)
        if t.get("bridge") == "yes":
            ponts[nom].append(pts)
        elif "highway" in t and t.get("junction") != "roundabout":
            routes[nom].append(pts)

    lieux = []

    def ajouter(nom, type_, geometrie, parts):
        parts = {c: p for c, p in parts.items() if c}
        if not parts:
            print(f"  ignoré (hors des communes) : {nom}")
            return
        total = sum(parts.values())
        parts = {c: round(p / total, 2) for c, p in sorted(parts.items(), key=lambda x: -x[1]) if p / total >= 0.05}
        lieux.append({"type": "Feature", "geometry": geometrie, "properties": {
            "id": ident(f"{type_}-{nom}"), "nom": nom, "type": type_, "zone": next(iter(parts)), "parts": parts}})

    def ligne(morceaux):
        return {"type": "MultiLineString", "coordinates": [[[round(x, 5), round(y, 5)] for x, y in m] for m in morceaux]}

    def parts_ligne(morceaux):
        parts = defaultdict(float)
        for m in morceaux:
            for a, b in zip(m, m[1:]):
                parts[commune(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), communes)] += km(a, b)
        return parts

    def point(nom, type_, noms_osm):
        centres = [c for n in noms_osm for c in points.get(n, [])]
        if not centres:
            print(f"  absent d'OpenStreetMap : {nom}")
            return
        c = centres[0]
        ajouter(nom, type_, {"type": "Point", "coordinates": [round(c[0], 5), round(c[1], 5)]}, {commune(c, communes): 1.0})

    for nom, noms_osm in AXES.items():
        morceaux = [m for n in noms_osm for m in routes.get(n, [])]
        if morceaux:
            # On ne garde que les tronçons dans les communes (une route nationale sort de la ville)
            dedans = [m for m in morceaux if any(commune(p, communes) for p in m)]
            ajouter(nom, "route", ligne(dedans), parts_ligne(dedans))
        else:
            print(f"  absent d'OpenStreetMap : {nom}")
    for nom, axe in PONTS.items():
        morceaux = ponts.get(axe, [])
        if not morceaux:
            print(f"  absent d'OpenStreetMap : {nom}")
            continue
        plus_long = max(morceaux, key=lambda m: sum(km(a, b) for a, b in zip(m, m[1:])))
        ajouter(nom, "pont", ligne([plus_long]), parts_ligne([plus_long]))
    for nom in CARREFOURS:
        point(nom, "carrefour", [nom])
    for nom, osm_nom in STADES.items():
        point(nom, "stade", [osm_nom])
    for nom, noms_osm in MARCHES.items():
        point(nom, "marche", noms_osm)

    return {"type": "FeatureCollection",
            "attribution": "© contributeurs OpenStreetMap, licence ODbL (openstreetmap.org/copyright)",
            "features": lieux}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--telecharger", action="store_true", help="interroger Overpass")
    g.add_argument("--osm", type=Path, help="extrait Overpass déjà téléchargé (JSON)")
    args = ap.parse_args()
    osm = telecharger() if args.telecharger else json.loads(args.osm.read_text(encoding="utf-8"))
    geo = construire(osm)
    SORTIE.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    par_type = defaultdict(list)
    for f in geo["features"]:
        par_type[f["properties"]["type"]].append(f"{f['properties']['nom']} ({f['properties']['zone']})")
    for t, noms in par_type.items():
        print(f"{t} ({len(noms)}) : " + " ; ".join(noms))
    print(f"Écrit : {SORTIE} ({SORTIE.stat().st_size // 1024} ko)")


if __name__ == "__main__":
    main()
