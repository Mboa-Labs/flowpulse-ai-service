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
import csv
import sys
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


def duree(secondes: float) -> str:
    secondes = int(secondes)
    return f"{secondes // 60} min {secondes % 60:02d} s" if secondes >= 60 else f"{secondes} s"


def millions(n: int) -> str:
    return f"{n / 1e6:.1f} M".replace(".", ",")


class Avancement:
    """Affiche l'étape en cours, une barre de progression, le temps écoulé et le temps restant estimé."""

    def __init__(self, total: int) -> None:
        self.total, self.n, self.t0, self.debut = total, 0, time.time(), time.time()

    def etape(self, titre: str) -> None:
        self.n += 1
        self.debut = time.time()
        print(f"\n[{self.n}/{self.total}] {titre}", flush=True)

    def info(self, texte: str) -> None:
        print(f"      · {texte}", flush=True)

    def barre(self, fait: int, total: int, detail: str) -> None:
        pct = fait / total
        plein = round(pct * 24)
        ecoule = time.time() - self.debut
        suite = f"reste ≈ {duree(ecoule / fait * (total - fait))}" if fait < total else f"en {duree(ecoule)}"
        print(f"      [{'█' * plein}{'░' * (24 - plein)}] {pct:4.0%}  {fait}/{total}  {detail}  · {suite}", flush=True)

    def fin(self, detail: str = "") -> None:
        print(f"      ✓ terminé en {duree(time.time() - self.debut)}" + (f" · {detail}" if detail else ""), flush=True)

    def total_ecoule(self) -> str:
        return duree(time.time() - self.t0)


# ---------------------------------------------------------------------------------------- Exploration

def explorer(source: Path) -> None:
    av = Avancement(5)
    av.etape("Contexte : antennes et arrondissements")
    con = connect(source)
    SORTIE.mkdir(exist_ok=True)
    rapport = ["# Exploration du dataset D4D-Sénégal", "",
               f"Source : `{source}` (lecture seule). Généré par `pipeline/d4d.py explorer`.", ""]

    nb_sites = con.execute("SELECT count(*) FROM sites").fetchone()[0]
    dakar = con.execute(f"SELECT a.ARR_ID, a.ARR, count(s.site_id) FROM arr a LEFT JOIN sites s ON s.arr_id = a.ARR_ID "
                    f"WHERE a.ARR_ID IN {DAKAR} GROUP BY ALL ORDER BY 1").fetchall()
    rapport += ["## Contexte", "",
                f"- {nb_sites} antennes (sites), {con.execute('SELECT count(*) FROM arr').fetchone()[0]} arrondissements.",
                f"- Région de Dakar : {len(dakar)} arrondissements, {sum(r[2] for r in dakar)} antennes.", "",
                md_table(dakar, ["ARR_ID", "Arrondissement", "Antennes"]), ""]
    av.fin(f"{nb_sites} antennes, dont {sum(r[2] for r in dakar)} dans la région de Dakar")

    # SET1 voix : chaque mois est lu une seule fois et résumé par heure et par antenne émettrice
    fichiers = sorted((source / "SET1").glob("SET1V_*.CSV.gz"))
    if not fichiers:
        sys.exit(f"Aucun fichier SET1V_*.CSV.gz dans {source / 'SET1'} : vérifier le chemin --source.")
    av.etape(f"SET1 voix : lecture des {len(fichiers)} mois d'appels (environ 30 s par mois)")
    cols = ", ".join(f"'{k}': '{v}'" for k, v in SET1V.items())
    total_lignes = 0
    for i, f in enumerate(fichiers, 1):
        src = f"read_csv('{f.as_posix()}', header = false, columns = {{{cols}}})"
        con.execute(("CREATE TABLE v AS " if i == 1 else "INSERT INTO v ") + f"""
        SELECT strptime(ts, '%Y-%m-%d %H') AS t, site_out,
               count(*)::BIGINT AS lignes,
               sum(appels)::BIGINT AS appels,
               sum(CASE WHEN duree >= 3600 THEN 1 ELSE 0 END)::BIGINT AS duree_plafonnee,
               sum(CASE WHEN duree <= 0 THEN 1 ELSE 0 END)::BIGINT AS duree_nulle,
               sum(CASE WHEN site_out = site_in THEN appels ELSE 0 END)::BIGINT AS appels_meme_site,
               sum(CASE WHEN site_in NOT IN (SELECT site_id FROM sites) THEN 1 ELSE 0 END)::BIGINT AS dest_inconnue
        FROM {src} GROUP BY 1, 2""")
        lignes = con.execute(f"SELECT sum(lignes) FROM v WHERE month(t) = {int(f.name[6:8])}").fetchone()[0] or 0
        total_lignes += lignes
        av.barre(i, len(fichiers), f"{f.name.split('.')[0]} : {millions(lignes)} lignes")
    con.execute(f"COPY v TO '{(SORTIE / 'set1v_heure_antenne.parquet').as_posix()}' (FORMAT parquet)")
    av.fin(f"{millions(total_lignes)} lignes résumées en {millions(con.execute('SELECT count(*) FROM v').fetchone()[0])}")

    av.etape("SET1 voix : statistiques et rythme de l'activité à Dakar")
    av.info("volumes par mois, antennes inconnues, part de Dakar")
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
    av.info(f"heures absentes de l'année : {len(manquantes)}")
    av.info("profil par heure et par jour, jours exceptionnels, antennes silencieuses")
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
    av.fin()

    # SET2 : trajectoires fines, une période pour l'exploration
    av.etape("SET2 : trajets des usagers échantillonnés (période 1 sur 25)")
    av.info("lecture de SET2_P01")
    con.execute(f"CREATE TABLE p01 AS SELECT * FROM {lire(source, 'SET2/SET2_P01.CSV.gz', SET2)}")
    av.info(f"{millions(con.execute('SELECT count(*) FROM p01').fetchone()[0])} positions lues ; doublons et usagers de Dakar")
    p01 = "p01"
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
    nombre = lambda n: f"{n:,}".replace(",", " ")
    av.fin(f"{nombre(s2[1])} usagers, dont {nombre(s2_dakar[0])} vus à Dakar")

    av.etape("Rapport et tableaux")
    # Tableaux courts en CSV (séparateur « ; », ouvrables dans Excel) pour les graphiques du rapport
    tableaux = {
        "exploration_mois.csv": (["mois", "lignes", "heures_presentes", "heures_attendues", "appels",
                                  "duree_plafonnee", "duree_nulle", "appels_meme_site"], mois),
        "exploration_dakar_par_heure.csv": (["heure", "appels_moyens"], profil),
        "exploration_dakar_par_jour.csv": (["jour", "appels_moyens"], [(jours[j], n) for j, n in semaine]),
        "exploration_dakar_jours.csv": (["date", "appels"], extremes),
    }
    for nom, (entetes, lignes) in tableaux.items():
        with (SORTIE / nom).open("w", encoding="utf-8-sig", newline="") as fh:
            csv.writer(fh, delimiter=";").writerows([entetes, *lignes])
    av.info(f"{len(tableaux)} tableaux CSV")

    rapport += ["## Décisions de nettoyage et de sélection", "",
                "- Garder la région de Dakar (arrondissements 1 à 10), qui correspond aux zones de FlowPulse.",
                "- SET1 : activité par antenne émettrice ; écarter les lignes dont l'antenne est inconnue ; "
                "les durées plafonnées ne servent pas (on compte des appels, pas des minutes).",
                "- SET2 : supprimer les doublons exacts ; un déplacement = deux positions successives du même usager "
                "dans deux arrondissements différents, à moins de 2 heures d'écart.",
                "- Heures manquantes : laissées absentes et signalées, jamais inventées.", "",
                f"_Durée de l'exploration : {av.total_ecoule()}._", ""]

    (SORTIE / "exploration_d4d.md").write_text("\n".join(rapport), encoding="utf-8")
    av.fin()
    print(f"\nExploration terminée en {av.total_ecoule()}. Résultats dans {SORTIE} :")
    for f in sorted(SORTIE.glob("*")):
        print(f"  - {f.name} ({f.stat().st_size / 1e6:.1f} Mo)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("etape", choices=["explorer"])
    parser.add_argument("--source", type=Path, required=True, help="dossier data du disque (contient SET1, SET2, ContextData)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # barres et accents corrects dans la console Windows
    {"explorer": explorer}[args.etape](args.source)


if __name__ == "__main__":
    main()
