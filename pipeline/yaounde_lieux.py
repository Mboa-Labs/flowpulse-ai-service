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
NB_AXES = 14
NB_PAR_TYPE = 8


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
    routes: dict[str, list] = defaultdict(list)
    ponts, ronds, stades, marches = {}, {}, {}, {}

    for e in osm["elements"]:
        t = e.get("tags", {})
        nom = t.get("name")
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
        if t.get("leisure") == "stadium" and nom:
            stades[nom] = centre
        elif t.get("amenity") == "marketplace" and nom:
            marches[nom] = centre
        elif t.get("junction") == "roundabout" and nom:
            ronds[nom] = centre
        elif t.get("bridge") == "yes":
            pont = nom if nom and "pont" in nom.lower() else (f"Pont, {t['name']}" if nom else None)
            if pont:
                ponts.setdefault(pont, []).append(pts)
        elif nom:
            routes[nom].append(pts)

    lieux = []

    def ajouter(nom, type_, geometrie, parts):
        parts = {c: p for c, p in parts.items() if c}
        if not parts:
            return
        total = sum(parts.values())
        parts = {c: round(p / total, 2) for c, p in sorted(parts.items(), key=lambda x: -x[1]) if p / total >= 0.05}
        lieux.append({"type": "Feature", "geometry": geometrie, "properties": {
            "id": ident(f"{type_}-{nom}"), "nom": nom, "type": type_, "zone": next(iter(parts)), "parts": parts}})

    def ligne(morceaux):
        coords = [[[round(x, 5), round(y, 5)] for x, y in m] for m in morceaux]
        return {"type": "MultiLineString", "coordinates": coords}

    def parts_ligne(morceaux):
        parts = defaultdict(float)
        for m in morceaux:
            for a, b in zip(m, m[1:]):
                parts[commune(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), communes)] += km(a, b)
        return parts

    longueurs = {n: sum(km(a, b) for m in ms for a, b in zip(m, m[1:])) for n, ms in routes.items()}
    for nom in sorted(longueurs, key=lambda n: -longueurs[n])[:NB_AXES]:
        ajouter(nom, "route", ligne(routes[nom]), parts_ligne(routes[nom]))
    for nom, ms in list(ponts.items())[:NB_PAR_TYPE]:
        ajouter(nom, "pont", ligne(ms), parts_ligne(ms))
    for type_, groupe in (("carrefour", ronds), ("stade", stades), ("marche", marches)):
        for nom, c in list(groupe.items())[:NB_PAR_TYPE]:
            ajouter(nom, type_, {"type": "Point", "coordinates": [round(c[0], 5), round(c[1], 5)]}, {commune(c, communes): 1.0})

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
