"""Préparation du dataset D4D-Sénégal (Orange, 2013) pour FlowPulse.

Étapes, chacune relançable seule :
  explorer   volumes, période couverte, heures manquantes, valeurs suspectes (rapport Markdown)
  agreger    nettoyage, sélection de la région de Dakar, agrégation par arrondissement et par heure

Les fichiers bruts sont lus en place, compressés, sans jamais être modifiés ni copiés.
Seuls des agrégats par zone sortent de ce script : aucune donnée individuelle.

Usage :
  python pipeline/d4d.py explorer --source E:/data
  python pipeline/d4d.py agreger  --source E:/data
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb

SORTIE = Path(__file__).resolve().parent / "sortie"
DAKAR = tuple(range(1, 11))  # ARR_ID des 10 arrondissements de la région de Dakar

SET1V = {"ts": "VARCHAR", "site_out": "INTEGER", "site_in": "INTEGER", "appels": "INTEGER", "duree": "INTEGER"}
SET1S = {"ts": "VARCHAR", "site_out": "INTEGER", "site_in": "INTEGER", "sms": "INTEGER"}
SET2 = {"user_id": "BIGINT", "ts": "TIMESTAMP", "site_id": "INTEGER"}


def connect(source: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    ctx = source / "ContextData"
    con.execute(f"CREATE TABLE arr AS SELECT * FROM read_csv('{(ctx / 'SENEGAL_ARR_V2.csv').as_posix()}', header = true)")
    con.execute(f"CREATE TABLE sites AS SELECT * FROM read_csv('{(ctx / 'SITE_ARR_LONLAT.CSV').as_posix()}', header = true)")
    return con


def lire(source: Path, motif: str, colonnes: dict) -> str:
    """Expression DuckDB qui lit tous les fichiers d'un jeu, avec le nom du fichier d'origine."""
    cols = ", ".join(f"'{k}': '{v}'" for k, v in colonnes.items())
    return f"read_csv('{(source / motif).as_posix()}', header = false, columns = {{{cols}}}, filename = true)"


def md_table(rows: list[tuple], headers: list[str]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(f"{v:,}".replace(",", " ") if isinstance(v, int) else str(v) for v in r) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------- Exploration

def explorer(source: Path) -> None:
    con = connect(source)
    SORTIE.mkdir(exist_ok=True)
    t0 = time.time()
    rapport = ["# Exploration du dataset D4D-Sénégal", "",
               f"Source : `{source}` (lecture seule). Généré par `pipeline/d4d.py explorer`.", ""]

    nb_sites = con.execute("SELECT count(*) FROM sites").fetchone()[0]
    dakar = con.execute(f"SELECT a.ARR_ID, a.ARR, count(s.site_id) FROM arr a LEFT JOIN sites s ON s.arr_id = a.ARR_ID "
                    f"WHERE a.ARR_ID IN {DAKAR} GROUP BY ALL ORDER BY 1").fetchall()
    rapport += ["## Contexte", "",
                f"- {nb_sites} antennes (sites), {con.execute('SELECT count(*) FROM arr').fetchone()[0]} arrondissements.",
                f"- Région de Dakar : {len(dakar)} arrondissements, {sum(r[2] for r in dakar)} antennes.", "",
                md_table(dakar, ["ARR_ID", "Arrondissement", "Antennes"]), ""]

    # SET1 voix : une seule lecture des 12 fichiers, résumée par heure et par antenne émettrice
    print("SET1 voix (lecture des 12 mois, quelques minutes)…", flush=True)
    con.execute(f"""
        CREATE TABLE v AS
        SELECT strptime(ts, '%Y-%m-%d %H') AS t, site_out,
               count(*)::BIGINT AS lignes,
               sum(appels)::BIGINT AS appels,
               sum(CASE WHEN duree >= 3600 THEN 1 ELSE 0 END)::BIGINT AS duree_plafonnee,
               sum(CASE WHEN duree <= 0 THEN 1 ELSE 0 END)::BIGINT AS duree_nulle,
               sum(CASE WHEN site_out = site_in THEN appels ELSE 0 END)::BIGINT AS appels_meme_site,
               sum(CASE WHEN site_in NOT IN (SELECT site_id FROM sites) THEN 1 ELSE 0 END)::BIGINT AS dest_inconnue
        FROM {lire(source, 'SET1/SET1V_*.CSV.gz', SET1V)} GROUP BY 1, 2""")
    con.execute(f"COPY v TO '{(SORTIE / 'set1v_heure_antenne.parquet').as_posix()}' (FORMAT parquet)")
    mois = con.execute("""
        SELECT strftime(t, '%Y-%m') AS mois, sum(lignes)::BIGINT, count(DISTINCT t)::BIGINT,
               (date_diff('day', min(date_trunc('day', t)), max(date_trunc('day', t))) + 1) * 24,
               sum(appels)::BIGINT, sum(duree_plafonnee)::BIGINT, sum(duree_nulle)::BIGINT, sum(appels_meme_site)::BIGINT
        FROM v GROUP BY 1 ORDER BY 1""").fetchall()
    inconnus = con.execute("SELECT sum(dest_inconnue) + sum(CASE WHEN site_out NOT IN (SELECT site_id FROM sites) "
                           "THEN lignes ELSE 0 END) FROM v").fetchone()[0]
    con.execute(f"CREATE TABLE vd AS SELECT v.* FROM v JOIN sites s ON s.site_id = v.site_out WHERE s.arr_id IN {DAKAR}")
    part_dakar = con.execute("SELECT (SELECT sum(appels) FROM vd) / sum(appels) FROM v").fetchone()[0]
    manquantes = con.execute("""
        WITH attendu AS (SELECT unnest(generate_series(TIMESTAMP '2013-01-01', TIMESTAMP '2013-12-31 23:00', INTERVAL 1 HOUR)) AS t)
        SELECT strftime(t, '%Y-%m-%d %H') FROM attendu WHERE t NOT IN (SELECT DISTINCT t FROM v) ORDER BY 1""").fetchall()
    rapport += ["## SET1 voix : appels entre antennes, par heure", "",
                md_table(mois, ["Mois", "Lignes", "Heures présentes", "Heures attendues", "Appels",
                                "Durée ≥ 3600 s", "Durée nulle", "Appels sur la même antenne"]), "",
                f"- Lignes dont une antenne est absente de la table des sites : {inconnus:,}".replace(",", " "),
                f"- Part des appels émis depuis la région de Dakar : {part_dakar:.1%}",
                f"- Heures totalement absentes de l'année : {len(manquantes)}"
                + (f" (exemples : {', '.join(m[0] for m in manquantes[:10])})" if manquantes else ""), ""]

    # Rythme de Dakar, pour vérifier que les données sont plausibles (pics, semaine, fêtes)
    profil = con.execute("""
        SELECT hour(t), round(avg(n))::BIGINT FROM (SELECT t, sum(appels) AS n FROM vd GROUP BY 1) GROUP BY 1 ORDER BY 1""").fetchall()
    semaine = con.execute("""
        SELECT dayofweek(d), round(avg(n))::BIGINT FROM (SELECT date_trunc('day', t) AS d, sum(appels) AS n FROM vd GROUP BY 1)
        GROUP BY 1 ORDER BY 1""").fetchall()
    jours = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]
    extremes = con.execute("""
        SELECT strftime(d, '%Y-%m-%d (%a)'), n FROM (SELECT date_trunc('day', t) AS d, sum(appels)::BIGINT AS n FROM vd GROUP BY 1)
        ORDER BY n""").fetchall()
    silences = con.execute(f"""
        SELECT count(*) FROM (SELECT s.site_id FROM sites s LEFT JOIN vd ON vd.site_out = s.site_id
                              WHERE s.arr_id IN {DAKAR} GROUP BY 1 HAVING count(DISTINCT date_trunc('day', vd.t)) < 300)""").fetchone()[0]
    rapport += ["### Rythme de l'activité à Dakar", "",
                md_table(profil, ["Heure", "Appels moyens émis depuis Dakar"]), "",
                md_table([(jours[j], n) for j, n in semaine], ["Jour", "Appels moyens par jour"]), "",
                "Jours les plus calmes : " + ", ".join(f"{d} ({n:,})".replace(",", " ") for d, n in extremes[:5]), "",
                "Jours les plus chargés : " + ", ".join(f"{d} ({n:,})".replace(",", " ") for d, n in extremes[-5:]), "",
                f"- Antennes de Dakar actives moins de 300 jours sur 365 : {silences}", ""]

    # SET2 : trajectoires fines, une période pour l'exploration
    print("SET2 (période 1)…", flush=True)
    p01 = lire(source, "SET2/SET2_P01.CSV.gz", SET2)
    s2 = con.execute(f"""
        SELECT count(*)::BIGINT, count(DISTINCT user_id)::BIGINT, min(ts), max(ts),
               (count(*) - (SELECT count(*) FROM (SELECT DISTINCT user_id, ts, site_id FROM {p01})))::BIGINT,
               sum(CASE WHEN site_id NOT IN (SELECT site_id FROM sites) THEN 1 ELSE 0 END)::BIGINT
        FROM {p01}""").fetchone()
    s2_dakar = con.execute(f"""
        SELECT count(DISTINCT user_id)::BIGINT, count(*)::BIGINT FROM {p01} p JOIN sites s ON s.site_id = p.site_id
        WHERE s.arr_id IN {DAKAR}""").fetchone()
    rapport += ["## SET2 : positions des usagers échantillonnés (période 1)", "",
                f"- {s2[0]:,} positions, {s2[1]:,} usagers, du {s2[2]} au {s2[3]}.".replace(",", " "),
                f"- Doublons exacts (même usager, même minute, même antenne) : {s2[4]:,} ({s2[4] / s2[0]:.1%}).".replace(",", " "),
                f"- Positions sur une antenne inconnue : {s2[5]:,}.".replace(",", " "),
                f"- Usagers vus au moins une fois dans la région de Dakar : {s2_dakar[0]:,} ({s2_dakar[0] / s2[1]:.0%}), "
                f"{s2_dakar[1]:,} positions.".replace(",", " "), ""]

    rapport += ["## Décisions de nettoyage et de sélection", "",
                "- Garder la région de Dakar (arrondissements 1 à 10), qui correspond aux zones de FlowPulse.",
                "- SET1 : activité par antenne émettrice ; écarter les lignes dont l'antenne est inconnue ; "
                "les durées plafonnées ne servent pas (on compte des appels, pas des minutes).",
                "- SET2 : supprimer les doublons exacts ; un déplacement = deux positions successives du même usager "
                "dans deux arrondissements différents, à moins de 2 heures d'écart.",
                "- Heures manquantes : laissées absentes et signalées, jamais inventées.", "",
                f"_Durée de l'exploration : {time.time() - t0:.0f} s._", ""]

    (SORTIE / "exploration_d4d.md").write_text("\n".join(rapport), encoding="utf-8")
    print(f"Rapport : {SORTIE / 'exploration_d4d.md'} ({time.time() - t0:.0f} s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("etape", choices=["explorer"])
    parser.add_argument("--source", type=Path, required=True, help="dossier data du disque (contient SET1, SET2, ContextData)")
    args = parser.parse_args()
    {"explorer": explorer}[args.etape](args.source)


if __name__ == "__main__":
    main()
