"""Préparation du dataset D4D-Sénégal (Orange, 2013) pour FlowPulse.

Étapes, chacune relançable seule :
  explorer   volumes, période couverte, heures manquantes, valeurs suspectes (rapport Markdown)
  agreger    nettoyage, sélection de la région de Dakar, agrégation par arrondissement et par heure
  indice     recalcule seulement l'indice de tension des séries déjà agrégées (sans le disque)
  transposer profils de Dakar transposés sur les 7 communes de Yaoundé (sortie/yaounde, sans le disque)
  entrainer  modèle de prévision de l'indice de tension à 1 h et 2 h (sans le disque)

Les fichiers bruts sont lus en place, compressés, sans jamais être modifiés ni copiés.
Seuls des agrégats par zone sortent de ce script : aucune donnée individuelle.

Usage :
  python pipeline/d4d.py explorer --source E:/data
  python pipeline/d4d.py agreger  --source E:/data
  python pipeline/d4d.py entrainer
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


JOURS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]


def nombre(n: int) -> str:
    return f"{n or 0:,}".replace(",", " ")


def pourcent(x: float, decimales: int = 1) -> str:
    return f"{x * 100:.{decimales}f} %".replace(".", ",")


def taille(octets: int) -> str:
    return f"{octets / 1e6:.1f} Mo".replace(".", ",") if octets >= 1e5 else f"{max(1, round(octets / 1e3))} Ko"


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
                f"- Part des appels émis depuis la région de Dakar : {pourcent(part_dakar)}",
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
    jours = JOURS
    extremes_txt = lambda rows: ", ".join(f"{d:%Y-%m-%d} ({JOURS[int(d.strftime('%w'))]}, {nombre(n)})" for d, n in rows)
    extremes = con.execute("""
        SELECT d, n FROM (SELECT date_trunc('day', t) AS d, sum(appels)::BIGINT AS n FROM vd GROUP BY 1)
        ORDER BY n""").fetchall()
    silences = con.execute(f"""
        SELECT count(*) FROM (SELECT s.site_id FROM sites s LEFT JOIN vd ON vd.site_out = s.site_id
                              WHERE s.arr_id IN {DAKAR} GROUP BY 1 HAVING count(DISTINCT date_trunc('day', vd.t)) < 300)""").fetchone()[0]
    rapport += ["### Rythme de l'activité à Dakar", "",
                md_table(profil, ["Heure", "Appels moyens émis depuis Dakar"]), "",
                md_table([(jours[j], n) for j, n in semaine], ["Jour", "Appels moyens par jour"]), "",
                "Jours les plus calmes : " + extremes_txt(extremes[:5]), "",
                "Jours les plus chargés : " + extremes_txt(extremes[-5:]), "",
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
                f"- {nombre(s2[0])} positions, {nombre(s2[1])} usagers, du {s2[2]} au {s2[3]}.",
                f"- Doublons exacts (même usager, même minute, même antenne) : {nombre(s2[4])} ({pourcent(s2[4] / s2[0])}).",
                f"- Positions sur une antenne inconnue : {nombre(s2[5])}.",
                f"- Usagers vus au moins une fois dans la région de Dakar : {nombre(s2_dakar[0])} "
                f"({pourcent(s2_dakar[0] / s2[1], 0)}), {nombre(s2_dakar[1])} positions.", ""]
    av.fin(f"{nombre(s2[1])} usagers, dont {nombre(s2_dakar[0])} vus à Dakar")

    av.etape("Rapport et tableaux")
    # Tableaux courts en CSV (séparateur « ; », ouvrables dans Excel) pour les graphiques du rapport
    tableaux = {
        "exploration_mois.csv": (["mois", "lignes", "heures_presentes", "heures_attendues", "appels",
                                  "duree_plafonnee", "duree_nulle", "appels_meme_site"], mois),
        "exploration_dakar_par_heure.csv": (["heure", "appels_moyens"], profil),
        "exploration_dakar_par_jour.csv": (["jour", "appels_moyens"], [(jours[j], n) for j, n in semaine]),
        "exploration_dakar_jours.csv": (["date", "appels"], [(f"{d:%Y-%m-%d}", n) for d, n in extremes]),
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
        print(f"  - {f.name} ({taille(f.stat().st_size)})")


# ---------------------------------------------------------------------------------------- Indice de tension

FENETRE_REPERE = "28 days"  # le niveau haut de référence d'une zone : ses 4 dernières semaines
SEMAINES_HABITUEL = 8  # le niveau habituel : même jour et même heure, sur les 8 semaines précédentes


def calculer_indice(con: duckdb.DuckDBPyConnection) -> None:
    """Crée la table « serie » à partir de « base » (t, arr_id, zone, appels, …) en ajoutant l'indice de tension.

    Les repères ne regardent que le passé de chaque heure : le 99e centile des appels de la zone sur les
    4 semaines précédentes (niveau haut récent) et la médiane des 8 mêmes créneaux précédents (niveau habituel).
    L'indice suit ainsi la croissance du nombre d'abonnés au fil de l'année, et ne révèle rien de l'avenir.
    """
    con.execute(f"""
        CREATE OR REPLACE TABLE serie AS
        WITH r AS (
            SELECT *,
                   quantile_cont(appels, 0.99) OVER recent AS p99_recent,
                   count(*) OVER recent AS heures_recentes,
                   median(appels) OVER (PARTITION BY arr_id, dayofweek(t), hour(t) ORDER BY t
                                        ROWS BETWEEN {SEMAINES_HABITUEL} PRECEDING AND 1 PRECEDING) AS mediane_habituelle
            FROM base
            WINDOW recent AS (PARTITION BY arr_id ORDER BY t
                              RANGE BETWEEN INTERVAL '{FENETRE_REPERE}' PRECEDING AND INTERVAL 1 HOUR PRECEDING)),
        debut AS (  -- premières semaines de l'année, sans assez d'historique : repère des 4 premières semaines
            SELECT arr_id, quantile_cont(appels, 0.99) AS p99_debut FROM base
            WHERE t < (SELECT min(t) FROM base) + INTERVAL '{FENETRE_REPERE}' GROUP BY 1)
        SELECT t, arr_id, zone, appels, antennes_actives, presents_echantillon, arrivees, departs,
               least(100, round(100 * appels / CASE WHEN heures_recentes >= 7 * 24 THEN p99_recent ELSE p99_debut END))::INTEGER
                   AS indice_tension,
               round(appels / nullif(mediane_habituelle, 0), 3) AS ecart_habituel
        FROM r JOIN debut USING (arr_id)
        ORDER BY t, arr_id""")


def indice(source: Path | None) -> None:
    """Recalcule seulement l'indice de tension des séries déjà agrégées (quelques secondes, sans le disque)."""
    fichier = SORTIE / "serie_zone_heure.parquet"
    if not fichier.exists():
        sys.exit("Séries introuvables : lancer d'abord l'étape « agreger ».")
    av = Avancement(2)
    av.etape("Recalcul de l'indice de tension à partir des séries agrégées")
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    con.execute(f"""CREATE TABLE base AS SELECT t, arr_id, zone, appels, antennes_actives, presents_echantillon, arrivees, departs
                    FROM read_parquet('{fichier.as_posix()}')""")
    calculer_indice(con)
    part = con.execute("SELECT avg(CASE WHEN indice_tension >= 85 THEN 1 ELSE 0 END), "
                       "avg(CASE WHEN indice_tension >= 75 THEN 1 ELSE 0 END) FROM serie").fetchone()
    av.fin(f"{pourcent(part[0])} des heures-zones à 85 ou plus, {pourcent(part[1])} à 75 ou plus")
    av.etape("Écriture des séries")
    con.execute(f"COPY serie TO '{fichier.as_posix()}' (FORMAT parquet)")
    con.execute(f"COPY serie TO '{(SORTIE / 'serie_zone_heure.csv').as_posix()}' (HEADER, DELIMITER ';')")
    av.fin()
    print(f"\nIndice recalculé en {av.total_ecoule()}. Fichiers mis à jour : serie_zone_heure.parquet, serie_zone_heure.csv")


# ---------------------------------------------------------------------------------------- Agrégation

JOURS_EXCLUS = ("2013-03-29",)  # panne de collecte constatée à l'exploration (journée presque vide)
ECART_MAX_DEPLACEMENT = "2 hours"  # au-delà, deux positions successives ne forment pas un déplacement


def agreger(source: Path) -> None:
    """Nettoie, garde la région de Dakar et produit des séries par arrondissement et par heure."""
    av = Avancement(5)
    resume_set1 = SORTIE / "set1v_heure_antenne.parquet"
    if not resume_set1.exists():
        sys.exit("Résumé SET1 introuvable : lancer d'abord l'étape « explorer ».")
    periodes = sorted((source / "SET2").glob("SET2_P*.CSV.gz"))
    if not periodes:
        sys.exit(f"Aucun fichier SET2_P*.CSV.gz dans {source / 'SET2'} : vérifier le chemin --source.")

    av.etape("Zones : arrondissements de Dakar et position de leurs antennes")
    con = connect(source)
    con.create_function("titre", lambda t: t.title(), ["VARCHAR"], "VARCHAR")  # « GRAND DAKAR » → « Grand Dakar »
    con.execute(f"""
        CREATE TABLE zones AS
        SELECT a.ARR_ID AS arr_id, titre(a.ARR) AS zone, a.DEPT AS departement, count(s.site_id)::INTEGER AS antennes,
               round(avg(s.lon), 5) AS lon, round(avg(s.lat), 5) AS lat
        FROM arr a JOIN sites s ON s.arr_id = a.ARR_ID WHERE a.ARR_ID IN {DAKAR} GROUP BY ALL ORDER BY 1""")
    # Toute antenne hors de la région de Dakar est rangée dans une zone 0 « hors Dakar »
    con.execute(f"CREATE TABLE site_zone AS SELECT site_id, CASE WHEN arr_id IN {DAKAR} THEN arr_id ELSE 0 END AS arr_id FROM sites")
    av.fin(f"{con.execute('SELECT count(*) FROM zones').fetchone()[0]} arrondissements")

    av.etape("SET1 voix : appels par arrondissement et par heure")
    con.execute(f"""
        CREATE TABLE activite AS
        SELECT v.t, z.arr_id, sum(v.appels)::BIGINT AS appels, count(DISTINCT v.site_out)::INTEGER AS antennes_actives
        FROM read_parquet('{resume_set1.as_posix()}') v JOIN site_zone z ON z.site_id = v.site_out
        WHERE z.arr_id > 0 AND strftime(v.t, '%Y-%m-%d') NOT IN {JOURS_EXCLUS + ('',)}
        GROUP BY 1, 2""")
    av.fin(f"{nombre(con.execute('SELECT count(*) FROM activite').fetchone()[0])} heures-zones")

    av.etape(f"SET2 : présences et déplacements, {len(periodes)} périodes de 2 semaines (environ 30 s par période)")
    con.execute("CREATE TABLE presence (t TIMESTAMP, arr_id INTEGER, presents BIGINT)")
    con.execute("CREATE TABLE flux (t TIMESTAMP, origine INTEGER, destination INTEGER, deplacements BIGINT)")
    doublons = positions = 0
    for i, f in enumerate(periodes, 1):
        # Nettoyage : antenne → arrondissement, doublons exacts supprimés
        con.execute(f"""
            CREATE OR REPLACE TABLE pos AS
            SELECT DISTINCT p.user_id, p.ts, z.arr_id
            FROM {lire(source, 'SET2/' + f.name, SET2)} p JOIN site_zone z ON z.site_id = p.site_id""")
        lus = con.execute(f"SELECT count(*) FROM {lire(source, 'SET2/' + f.name, SET2)}").fetchone()[0] if i == 1 else None
        n = con.execute("SELECT count(*) FROM pos").fetchone()[0]
        if lus is not None:
            doublons, positions = lus - n, lus
        con.execute("""
            INSERT INTO presence
            SELECT date_trunc('hour', ts), arr_id, count(DISTINCT user_id) FROM pos WHERE arr_id > 0 GROUP BY 1, 2""")
        # Déplacement : deux positions successives du même usager, dans deux zones différentes, à moins de 2 h
        con.execute(f"""
            INSERT INTO flux
            SELECT date_trunc('hour', ts), origine, arr_id, count(*) FROM (
                SELECT ts, arr_id,
                       lag(arr_id) OVER w AS origine, lag(ts) OVER w AS ts_prec
                FROM pos WINDOW w AS (PARTITION BY user_id ORDER BY ts))
            WHERE origine IS NOT NULL AND origine <> arr_id AND ts - ts_prec <= INTERVAL '{ECART_MAX_DEPLACEMENT}'
              AND (origine > 0 OR arr_id > 0)
            GROUP BY 1, 2, 3""")
        av.barre(i, len(periodes), f"{f.name.split('.')[0]} : {millions(n)} positions après nettoyage")
    con.execute("DROP TABLE pos")
    av.fin(f"{nombre(con.execute('SELECT sum(deplacements) FROM flux').fetchone()[0])} déplacements entre zones")

    av.etape("Séries par zone et indice de tension")
    con.execute("""
        CREATE TABLE base AS
        SELECT a.t, a.arr_id, z.zone, a.appels, a.antennes_actives,
               coalesce(p.presents, 0) AS presents_echantillon,
               coalesce(arr.n, 0) AS arrivees, coalesce(dep.n, 0) AS departs
        FROM activite a
        JOIN zones z USING (arr_id)
        LEFT JOIN presence p USING (t, arr_id)
        LEFT JOIN (SELECT t, destination AS arr_id, sum(deplacements) AS n FROM flux GROUP BY 1, 2) arr USING (t, arr_id)
        LEFT JOIN (SELECT t, origine AS arr_id, sum(deplacements) AS n FROM flux GROUP BY 1, 2) dep USING (t, arr_id)""")
    calculer_indice(con)
    qualite = con.execute(f"""
        SELECT count(*), count(DISTINCT t), min(t), max(t),
               sum(CASE WHEN indice_tension >= 85 THEN 1 ELSE 0 END), sum(CASE WHEN indice_tension >= 75 THEN 1 ELSE 0 END)
        FROM serie""").fetchone()
    av.fin(f"{nombre(qualite[0])} lignes, {nombre(qualite[1])} heures")

    av.etape("Fichiers et rapport")
    con.execute(f"COPY zones TO '{(SORTIE / 'zones_dakar.csv').as_posix()}' (HEADER, DELIMITER ';')")
    con.execute(f"COPY serie TO '{(SORTIE / 'serie_zone_heure.parquet').as_posix()}' (FORMAT parquet)")
    con.execute(f"COPY serie TO '{(SORTIE / 'serie_zone_heure.csv').as_posix()}' (HEADER, DELIMITER ';')")
    con.execute(f"""COPY (SELECT f.* FROM flux f WHERE strftime(t, '%Y-%m-%d') NOT IN {JOURS_EXCLUS + ('',)} ORDER BY 1, 2, 3)
                    TO '{(SORTIE / 'flux_zone_heure.parquet').as_posix()}' (FORMAT parquet)""")

    par_zone = con.execute("""
        SELECT zone, round(avg(appels))::BIGINT, round(avg(presents_echantillon))::BIGINT,
               sum(arrivees)::BIGINT, sum(departs)::BIGINT,
               round(avg(indice_tension))::INTEGER, sum(CASE WHEN indice_tension >= 85 THEN 1 ELSE 0 END)::BIGINT
        FROM serie GROUP BY zone, arr_id ORDER BY arr_id""").fetchall()
    profil = con.execute("""
        SELECT hour(t), round(avg(indice_tension))::INTEGER FROM serie WHERE dayofweek(t) BETWEEN 1 AND 5
        GROUP BY 1 ORDER BY 1""").fetchall()
    od = con.execute("""
        SELECT coalesce(o.zone, 'Hors Dakar'), coalesce(d.zone, 'Hors Dakar'), sum(f.deplacements)::BIGINT AS n
        FROM flux f LEFT JOIN zones o ON o.arr_id = f.origine LEFT JOIN zones d ON d.arr_id = f.destination
        GROUP BY 1, 2 ORDER BY n DESC LIMIT 10""").fetchall()
    rapport = [
        "# Agrégation du dataset D4D-Sénégal : région de Dakar", "",
        f"Source : `{source}` (lecture seule). Généré par `pipeline/d4d.py agreger`.", "",
        "## Nettoyage et sélection appliqués", "",
        "- Région de Dakar seulement : 10 arrondissements ; les autres antennes forment une zone « hors Dakar » "
        "utilisée uniquement pour les déplacements qui entrent dans la région ou en sortent.",
        f"- Journées exclues (panne de collecte) : {', '.join(JOURS_EXCLUS)}.",
        f"- SET2, période 1 : {nombre(doublons)} doublons supprimés sur {nombre(positions)} positions "
        f"({pourcent(doublons / positions if positions else 0)}) ; même règle sur les 25 périodes.",
        f"- Déplacement : deux positions successives du même usager, dans deux zones différentes, à moins de {ECART_MAX_DEPLACEMENT.replace('hours', 'heures')}.",
        "- Aucune donnée individuelle dans les fichiers produits : uniquement des totaux par zone et par heure.", "",
        "## Séries produites", "",
        f"- {nombre(qualite[0])} lignes (zone × heure), {nombre(qualite[1])} heures, du {qualite[2]} au {qualite[3]}.",
        f"- Heures-zones en tension forte (indice ≥ 85) : {nombre(qualite[4])} ; en tension (≥ 75) : {nombre(qualite[5])}.", "",
        md_table(par_zone, ["Zone", "Appels moyens par heure", "Présents moyens (échantillon)", "Arrivées (année)",
                            "Départs (année)", "Indice moyen", "Heures ≥ 85"]), "",
        "### Indice de tension moyen par heure (jours ouvrés)", "",
        md_table(profil, ["Heure", "Indice moyen"]), "",
        "### Principaux déplacements entre zones (échantillon SET2, toute l'année)", "",
        md_table(od, ["Origine", "Destination", "Déplacements"]), "",
        "## Définitions", "",
        "- `appels` : appels émis depuis les antennes de la zone pendant l'heure (tous les abonnés Orange, SET1).",
        "- `presents_echantillon` : usagers de l'échantillon SET2 vus dans la zone pendant l'heure.",
        "- `arrivees`, `departs` : déplacements de l'échantillon SET2 qui entrent dans la zone ou en sortent pendant l'heure.",
        "- `indice_tension` (0 à 100) : activité de l'heure rapportée au haut niveau récent de la zone "
        "(99e centile de ses appels sur les 4 semaines précédentes). Il ne regarde que le passé et suit la croissance "
        "du nombre d'abonnés. C'est un indicateur de tension de mobilité, pas une mesure du trafic routier.",
        "- `ecart_habituel` : activité rapportée à la médiane de la zone pour le même jour de la semaine et la même heure, "
        "sur les 8 semaines précédentes (1 = habituel, 1,5 = 50 % au-dessus) ; sert à repérer les événements.", "",
        f"_Durée de l'agrégation : {av.total_ecoule()}._", ""]
    (SORTIE / "agregation_d4d.md").write_text("\n".join(rapport), encoding="utf-8")
    av.fin()
    print(f"\nAgrégation terminée en {av.total_ecoule()}. Résultats dans {SORTIE} :")
    for nom in ("agregation_d4d.md", "zones_dakar.csv", "serie_zone_heure.csv", "serie_zone_heure.parquet", "flux_zone_heure.parquet"):
        print(f"  - {nom} ({taille((SORTIE / nom).stat().st_size)})")


# ---------------------------------------------------------------------------------------- Transposition sur Yaoundé

def transposer(_source: Path | None) -> None:
    """Profils réels de Dakar transposés sur les 7 communes de Yaoundé (dossier sortie/yaounde), sans le disque."""
    import json

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import yaounde

    serie_f, zones_f, flux_f = SORTIE / "serie_zone_heure.parquet", SORTIE / "zones_dakar.csv", SORTIE / "flux_zone_heure.parquet"
    if not serie_f.exists() or not zones_f.exists():
        sys.exit("Séries de Dakar introuvables : lancer d'abord l'étape « agreger ».")
    dossier = SORTIE / "yaounde"
    dossier.mkdir(exist_ok=True)
    av = Avancement(3)

    av.etape("Correspondance des communes de Yaoundé avec les arrondissements de Dakar")
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    con.execute(f"CREATE TABLE zd AS SELECT * FROM read_csv('{zones_f.as_posix()}', delim = ';', header = true)")
    dakar = {z.upper(): a for a, z in con.execute("SELECT arr_id, zone FROM zd").fetchall()}
    lignes = []
    for commune, (source, role, lon, lat) in yaounde.CORRESPONDANCE.items():
        arr_id = dakar[source]
        lignes.append((arr_id, commune, "Mfoundi", None, lon, lat, source.title(), role))
        av.info(f"{commune} ← {source.title()} : {role}")
    con.execute("CREATE TABLE zy (arr_id INTEGER, zone VARCHAR, departement VARCHAR, antennes INTEGER, lon DOUBLE, "
                "lat DOUBLE, profil_dakar VARCHAR, role VARCHAR)")
    con.executemany("INSERT INTO zy VALUES (?, ?, ?, ?, ?, ?, ?, ?)", lignes)
    av.fin(f"{len(lignes)} communes")

    av.etape("Séries et flux transposés")
    # L'identifiant interne reste celui de l'arrondissement source : le modèle reconnaît la zone dont il a appris le profil
    con.execute(f"""COPY (SELECT s.* EXCLUDE (zone), y.zone FROM read_parquet('{serie_f.as_posix()}') s JOIN zy y USING (arr_id)
                          ORDER BY t, arr_id) TO '{(dossier / 'serie_zone_heure.parquet').as_posix()}' (FORMAT parquet)""")
    if flux_f.exists():
        # Déplacements vers ou depuis un arrondissement sans équivalent : rangés dans la zone 0 (hors des 7 communes)
        con.execute(f"""COPY (
            SELECT t, CASE WHEN origine IN (SELECT arr_id FROM zy) THEN origine ELSE 0 END AS origine,
                      CASE WHEN destination IN (SELECT arr_id FROM zy) THEN destination ELSE 0 END AS destination,
                      sum(deplacements)::BIGINT AS deplacements
            FROM read_parquet('{flux_f.as_posix()}') GROUP BY ALL HAVING origine > 0 OR destination > 0 ORDER BY 1, 2, 3)
            TO '{(dossier / 'flux_zone_heure.parquet').as_posix()}' (FORMAT parquet)""")
    con.execute(f"COPY zy TO '{(dossier / 'zones.csv').as_posix()}' (HEADER, DELIMITER ';')")
    n = con.execute(f"SELECT count(*) FROM read_parquet('{(dossier / 'serie_zone_heure.parquet').as_posix()}')").fetchone()[0]
    av.fin(f"{nombre(n)} heures-zones")

    av.etape("Description du territoire")
    territoire = {
        "nom": "Yaoundé", "pays": "Cameroun", "mention": yaounde.MENTION,
        "flotte": {k: {"lignes_actives": v[0], "bus_en_reserve": v[1], "capacite": 60} for k, v in yaounde.FLOTTE.items()},
        "arrets": yaounde.ARRETS, "journees": yaounde.JOURNEES,
        "correspondance": {k: {"profil_dakar": v[0].title(), "role": v[1]} for k, v in yaounde.CORRESPONDANCE.items()},
    }
    (dossier / "territoire.json").write_text(json.dumps(territoire, ensure_ascii=False, indent=2), encoding="utf-8")
    (dossier / "LISEZMOI.md").write_text("\n".join([
        "# FlowPulse sur Yaoundé : profils transposés", "", yaounde.MENTION + ".", "",
        "| Commune | Profil repris (Dakar) | Rôle urbain |", "| --- | --- | --- |",
        *[f"| {k} | {v[0].title()} | {v[1]} |" for k, v in yaounde.CORRESPONDANCE.items()], "",
        "- Repris : les profils horaires réels (rythme de la journée, de la semaine, des fêtes) et l'indice de tension, "
        "relatif à chaque zone.",
        "- Non repris : les volumes (appels, déplacements), qui décrivent Dakar et non Yaoundé. Positions des communes approximatives.",
        "- Flotte, lignes et arrêts : données de démonstration (aucun exploitant n'a fourni de données).",
        "- Dates : celles de Dakar en 2013 ; les libellés des journées indiquent le profil rejoué.",
        "- Pour un déploiement réel : les mêmes étapes du pipeline sur les données d'un opérateur camerounais (MTN, Orange), "
        "dans le cadre de la loi n° 2024/017 sur les données personnelles.", ""]), encoding="utf-8")
    av.fin()
    print(f"\nTransposition terminée en {av.total_ecoule()}. Résultats dans {dossier}.")
    print("Étape suivante : python -I pipeline\\d4d.py entrainer --sortie pipeline\\sortie\\yaounde")


def entrainer(_source: Path | None) -> None:
    """Prévision de l'indice de tension par zone, à partir des séries agrégées (le disque n'est plus nécessaire)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import modele

    av = Avancement(3)
    dossier = modele.entrainer(SORTIE, av)
    print(f"\nEntraînement terminé en {av.total_ecoule()}. Résultats dans {dossier} :")
    for f in sorted(dossier.glob("*")):
        print(f"  - {f.name} ({taille(f.stat().st_size)})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("etape", choices=["explorer", "agreger", "indice", "transposer", "entrainer"])
    parser.add_argument("--source", type=Path, help="dossier data du disque (contient SET1, SET2, ContextData) ; "
                                                     "inutile pour « entrainer »")
    parser.add_argument("--sortie", type=Path, default=SORTIE, help=f"dossier des résultats (défaut : {SORTIE})")
    args = parser.parse_args()
    if args.etape in ("explorer", "agreger") and args.source is None:
        parser.error(f"l'étape « {args.etape} » a besoin de --source (le dossier data du disque)")
    globals()["SORTIE"] = args.sortie
    sys.stdout.reconfigure(encoding="utf-8")  # barres et accents corrects dans la console Windows
    {"explorer": explorer, "agreger": agreger, "indice": indice, "transposer": transposer, "entrainer": entrainer}[args.etape](args.source)


if __name__ == "__main__":
    main()
