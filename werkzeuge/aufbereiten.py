#!/usr/bin/env python3
"""Rohpakete des Geraets einarbeiten und die Daten fuers Dashboard bauen.

    python werkzeuge/aufbereiten.py

Ablauf:
    1. roh/*.csv einlesen
    2. in tage/JJJJ-MM-TT.csv einsortieren, Dubletten ueberschreiben
    3. verarbeitete Rohdateien loeschen
    4. betroffene Tage neu auswerten (tage.json)
    5. dashboard.json schreiben

Gemessen und bewertet wird ueber den ganzen Tag. Es gibt keine
Sonderbehandlung einzelner Tageszeiten.

Das Archiv unter tage/ enthaelt nur GEMESSENE Werte. Die absolute Feuchte
wird hier gerechnet und wandert nur in dashboard.json -- siehe die
Begruendung in luft.py.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from luft import absolute_feuchte

# Das Geraet schreibt oesterreichische Ortszeit, die GitHub-Action laeuft in
# UTC. Ohne Umrechnung waeren alle Zeitfenster um zwei Stunden verschoben.
try:
    from zoneinfo import ZoneInfo
    ZONE = ZoneInfo("Europe/Vienna")
except Exception as _grund:
    # Windows bringt keine Zeitzonendatenbank mit; ohne das Paket "tzdata"
    # schlaegt das hier fehl. Dann gilt die Zeitzone DIESES Rechners -- in
    # Mitteleuropa also dasselbe Ergebnis.
    #
    # Der Hinweis muss trotzdem sein: Es ist eine Annahme, und auf einem
    # Rechner in einer anderen Zeitzone waeren alle Tagesgrenzen verschoben,
    # ohne dass irgendetwas kaputt aussieht.
    ZONE = None
    print("HINWEIS: Zeitzone Europe/Vienna nicht ladbar (%s)." % _grund)
    print("         Es gilt die Zeitzone dieses Rechners. Abstellen mit:")
    print("         python -m pip install tzdata")


def jetzt():
    """Jetzt, MIT Zeitzone.

    Zwingend mit: Die Zeitstempel des Geraets tragen ihren Versatz, und eine
    Mischung aus Zeitangaben mit und ohne Zone laesst Python beim Vergleich
    mit einem TypeError stehen -- was besser ist, als wenn es stillschweigend
    irgendetwas annaehme.
    """
    return datetime.now().astimezone() if ZONE is None else datetime.now(ZONE)


WURZEL = Path(__file__).resolve().parent.parent
ROH = WURZEL / "roh"
TAGE = WURZEL / "tage"
TAGE_JSON = WURZEL / "tage.json"
DASHBOARD_JSON = WURZEL / "dashboard.json"

SPALTEN = ["zeit", "status", "co2", "t", "rh"]

# Ortszeit MIT Zeitzonenversatz: "2026-10-25 02:30:00+0200".
#
# Der Versatz ist der Grund, warum die Nacht der Zeitumstellung nicht
# verlorengeht. Dann springt die Uhr von 03:00 auf 02:00 zurueck, und die
# Ortszeiten 02:00:00 bis 02:59:59 kommen zweimal vor -- einmal mit +0200,
# einmal mit +0100. Ohne den Versatz waeren das dieselben Zeitstempel, und
# da hier nach Zeitstempel abgelegt wird, wuerde die zweite Stunde die erste
# ueberschreiben: 60 Minuten still falscher Werte, einmal im Jahr.
#
# Die Stellen 0 bis 18 bleiben unveraendert, das Datum laesst sich also
# weiterhin durch Abschneiden gewinnen.
ZEITFORM = "%Y-%m-%d %H:%M:%S%z"

# Nur fuer die Anzeige, ohne Versatz.
ANZEIGEFORM = "%Y-%m-%d %H:%M:%S"


def augenblick(zeitstempel):
    """Zeitstempel als echter Zeitpunkt -- zum Sortieren und Vergleichen.

    Nach der Zeichenkette zu sortieren waere in der Umstellungsnacht falsch:
    "02:30:00+0100" liegt eine Stunde NACH "02:30:00+0200", als Text aber
    davor.
    """
    return datetime.strptime(zeitstempel, ZEITFORM)


# ------------------------------------------------------------ Bewertung ----
#
# CO2-Schwellen nach der dreistufigen hygienischen Bewertung des
# Umweltbundesamts (Ad-hoc-Arbeitsgruppe Innenraumrichtwerte 2008,
# fortgefuehrt in "Hygienische Leitwerte fuer die Innenraumluft"):
#
#     unter 1000 ppm   hygienisch unbedenklich
#     1000 bis 2000    hygienisch auffaellig  -> lueften
#     ueber 2000 ppm   hygienisch inakzeptabel -> lueften, Raum pruefen
#
# Frischluft im Freien liegt derzeit bei rund 420 ppm.
CO2_GELB = 1000
CO2_ROT = 2000

# Relative Feuchte: 40 bis 60 % gelten als Wohlfuehlbereich. Dauerhaft ueber
# 60 % beguenstigt Schimmelwachstum, unter 30 % wird die Luft unangenehm
# trocken. Das sind Komfort- und Bauschutzwerte, keine Gesundheitsgrenzen --
# deshalb hier bewusst grosszuegiger gestuft als beim CO2.
RH_GUT_VON, RH_GUT_BIS = 40.0, 60.0
RH_ROT_VON, RH_ROT_BIS = 30.0, 70.0

# Temperatur: Komfortbereich, ebenfalls keine Gesundheitsgrenze.
T_GUT_VON, T_GUT_BIS = 20.0, 24.0
T_ROT_VON, T_ROT_BIS = 18.0, 26.0

# Verlaufskurven: Name -> (Stunden zurueck, Raster in Minuten)
#
# Die volle Minutenaufloesung gibt es fuer den laufenden Tag. Darueber
# hinaus wird gemittelt -- sonst waere dashboard.json nach einem Jahr
# unbrauchbar gross, und sie wird bei JEDEM Seitenaufruf uebertragen.
VERLAEUFE = {
    "tag": (24, 1),
    "woche": (24 * 7, 15),
    "monat": (24 * 30, 60),
}

# Nur diese Status liefern verwertbare Zahlen. "unplausibel" bringt zwar
# Werte mit, aber ausdruecklich fragwuerdige -- die gehoeren nicht in einen
# Mittelwert. Sie bleiben im Archiv und sind dort gekennzeichnet.
STATUS_VERWERTBAR = ("ok",)


# ------------------------------------------------------------------ lesen ---

def zahl(text):
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def satz_lesen(zeile):
    """Eine CSV-Zeile zu einem Satz, oder None wenn unbrauchbar."""
    teile = zeile.rstrip("\n").split(";")
    if len(teile) != len(SPALTEN):
        return None
    satz = dict(zip(SPALTEN, teile))
    if satz["zeit"] in ("", "zeit") or satz["zeit"].startswith("#"):
        return None
    try:
        datetime.strptime(satz["zeit"], ZEITFORM)
    except ValueError:
        return None
    return satz


def datei_lesen(pfad):
    if not pfad.exists():
        return []
    saetze = []
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        satz = satz_lesen(zeile)
        if satz:
            saetze.append(satz)
    return saetze


def tag_lesen(tag):
    return datei_lesen(TAGE / ("%s.csv" % tag))


def vorhandene_tage():
    if not TAGE.exists():
        return []
    tage = []
    for pfad in TAGE.glob("*.csv"):
        try:
            datetime.strptime(pfad.stem, "%Y-%m-%d")
        except ValueError:
            continue
        tage.append(pfad.stem)
    return sorted(tage)


# ----------------------------------------------------------- einsortieren ---

def rohdaten_einsammeln():
    dateien = sorted(ROH.rglob("*.csv")) if ROH.exists() else []
    saetze, verworfen = [], 0
    for pfad in dateien:
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            if not zeile.strip():
                continue
            satz = satz_lesen(zeile)
            if satz:
                saetze.append(satz)
            else:
                verworfen += 1
    return saetze, dateien, verworfen


def in_tagesdateien(saetze):
    """Saetze nach Tagen einsortieren. Rueckgabe: geaenderte Tage."""
    TAGE.mkdir(exist_ok=True)
    nach_tag = defaultdict(list)
    for satz in saetze:
        nach_tag[satz["zeit"][:10]].append(satz)

    for tag, neue in nach_tag.items():
        pfad = TAGE / ("%s.csv" % tag)
        # Nach Zeitstempel ablegen: Ein doppelt hochgeladenes Paket
        # ueberschreibt sich selbst, statt die Datei zu verdoppeln.
        bestand = {s["zeit"]: s for s in datei_lesen(pfad)}
        for satz in neue:
            bestand[satz["zeit"]] = satz
        zeilen = [";".join(SPALTEN)]
        zeilen += [";".join(bestand[z][s] for s in SPALTEN)
                   for z in sorted(bestand, key=augenblick)]
        pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")

    return sorted(nach_tag)


# ------------------------------------------------------------- Messpunkte ---

def punkt(satz):
    """Ein Satz mit gerechneter absoluter Feuchte."""
    brauchbar = satz["status"] in STATUS_VERWERTBAR
    co2 = zahl(satz["co2"]) if brauchbar else None
    t = zahl(satz["t"]) if brauchbar else None
    rh = zahl(satz["rh"]) if brauchbar else None
    ah = None
    if t is not None and rh is not None:
        ah = round(absolute_feuchte(t, rh), 2)
    return {"z": satz["zeit"], "c": co2, "t": t, "rh": rh, "ah": ah,
            "s": satz["status"]}


FELDER = ("c", "t", "rh", "ah")


def mittel(werte):
    gueltig = [w for w in werte if w is not None]
    return round(sum(gueltig) / len(gueltig), 2) if gueltig else None


def zusammenfassen(gruppe, zeit):
    """Mehrere Punkte zu einem. Behaelt die CO2-Spitze.

    Beim Mitteln ueber eine Stunde verschwindet eine kurze Spitze sonst
    vollstaendig -- und beim CO2 sind gerade die Spitzen das Interessante.
    """
    ergebnis = {"z": zeit}
    for feld in FELDER:
        ergebnis[feld] = mittel([p[feld] for p in gruppe])
    spitzen = [p["c"] for p in gruppe if p["c"] is not None]
    ergebnis["cmax"] = round(max(spitzen)) if spitzen else None
    ergebnis["s"] = "ok" if all(p["s"] == "ok" for p in gruppe) else "luecke"
    return ergebnis


def rastern(punkte, minuten):
    if minuten <= 1 or not punkte:
        return punkte
    eimer = defaultdict(list)
    for p in punkte:
        z = augenblick(p["z"])
        if minuten < 60:
            z = z.replace(minute=z.minute // minuten * minuten, second=0)
        else:
            schritt = minuten // 60
            z = z.replace(hour=z.hour // schritt * schritt, minute=0, second=0)
        eimer[z].append(p)
    return [zusammenfassen(eimer[k], k.strftime(ZEITFORM))
            for k in sorted(eimer)]


def punkte_ab(stunden_zurueck):
    grenze = jetzt() - timedelta(hours=stunden_zurueck)
    ab_tag = (grenze - timedelta(days=1)).strftime("%Y-%m-%d")
    punkte = []
    for tag in vorhandene_tage():
        if tag < ab_tag:
            continue
        for satz in tag_lesen(tag):
            if augenblick(satz["zeit"]) >= grenze:
                punkte.append(punkt(satz))
    punkte.sort(key=lambda p: augenblick(p["z"]))
    return punkte


# ------------------------------------------------------------ Tageswerte ----

def tag_auswerten(tag):
    """Kennzahlen eines Kalendertags."""
    punkte = [punkt(s) for s in tag_lesen(tag)]
    if not punkte:
        return None
    co2 = [p["c"] for p in punkte if p["c"] is not None]
    temperaturen = [p["t"] for p in punkte if p["t"] is not None]
    feuchten = [p["rh"] for p in punkte if p["rh"] is not None]
    if not co2:
        return None

    # Bei Minutentakt ist jede Zeile eine Minute -- "Minuten ueber der
    # Schwelle" ist damit schlicht ein Abzaehlen. Fehlt eine Minute, zaehlt
    # sie nicht mit; das ist richtig, gemessen wurde da nichts.
    return {
        "tag": tag,
        "minuten": len(punkte),
        "messwerte": len(co2),
        "co2_mittel": round(sum(co2) / len(co2)),
        "co2_max": round(max(co2)),
        "co2_min": round(min(co2)),
        "min_ueber_gelb": sum(1 for w in co2 if w > CO2_GELB),
        "min_ueber_rot": sum(1 for w in co2 if w > CO2_ROT),
        "t_mittel": mittel(temperaturen),
        "t_min": min(temperaturen) if temperaturen else None,
        "t_max": max(temperaturen) if temperaturen else None,
        "rh_mittel": mittel(feuchten),
        "rh_min": min(feuchten) if feuchten else None,
        "rh_max": max(feuchten) if feuchten else None,
        "ah_mittel": mittel([p["ah"] for p in punkte]),
        "luecken": sum(1 for p in punkte if p["s"] not in STATUS_VERWERTBAR),
    }


def tage_fortschreiben(geaenderte_tage):
    """Tageswerte laden, geaenderte Tage neu rechnen, zurueckschreiben.

    Neu gerechnet wird nur, was sich geaendert hat. Sonst muesste die Action
    mit wachsender Historie jedes Mal laenger rechnen -- bei 96 Laeufen am
    Tag faellt das nach einem Jahr ins Gewicht.
    """
    try:
        bestand = json.loads(TAGE_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        bestand = {}

    betroffen = set(geaenderte_tage)
    # Dazu alles, was noch nie gerechnet wurde. So faellt auch ein
    # nachtraeglich von Hand eingespielter Tag nicht durch.
    betroffen |= {t for t in vorhandene_tage() if t not in bestand}

    for tag in sorted(betroffen):
        ergebnis = tag_auswerten(tag)
        if ergebnis:
            bestand[tag] = ergebnis
        elif tag in bestand:
            del bestand[tag]

    # Tage, deren Datei verschwunden ist, fliegen raus.
    vorhanden = set(vorhandene_tage())
    for tag in list(bestand):
        if tag not in vorhanden:
            del bestand[tag]

    TAGE_JSON.write_text(
        json.dumps(bestand, ensure_ascii=False, separators=(",", ":"),
                   sort_keys=True), encoding="utf-8")
    return bestand


# --------------------------------------------------------------- Dashboard ---

def dashboard_bauen(tageswerte):
    verlauf = {}
    for name, (stunden, raster) in VERLAEUFE.items():
        verlauf[name] = rastern(punkte_ab(stunden), raster)

    letzter = None
    for p in reversed(verlauf["tag"]):
        if p["c"] is not None:
            letzter = p
            break

    reihe = [tageswerte[t] for t in sorted(tageswerte)]
    daten = {
        "erzeugt": jetzt().strftime(ANZEIGEFORM),
        "schwellen": {
            "co2_gelb": CO2_GELB,
            "co2_rot": CO2_ROT,
            "rh_gut": [RH_GUT_VON, RH_GUT_BIS],
            "rh_rot": [RH_ROT_VON, RH_ROT_BIS],
            "t_gut": [T_GUT_VON, T_GUT_BIS],
            "t_rot": [T_ROT_VON, T_ROT_BIS],
        },
        "jetzt": letzter,
        "heute": reihe[-1] if reihe else None,
        "verlauf": verlauf,
        "tage": reihe,
        "dateien": vorhandene_tage(),
        "summe": {
            "tage": len(reihe),
            "erster_tag": sorted(tageswerte)[0] if tageswerte else None,
            "minuten": sum(t["minuten"] for t in reihe),
            "min_ueber_gelb": sum(t["min_ueber_gelb"] for t in reihe),
            "min_ueber_rot": sum(t["min_ueber_rot"] for t in reihe),
        },
    }
    DASHBOARD_JSON.write_text(
        json.dumps(daten, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    return daten


# ---------------------------------------------------------------- Hauptteil ---

def hauptprogramm():
    # Die Ordner muessen existieren, bevor irgendetwas anderes passiert:
    # GitHub entfernt leere Ordner, und "git add roh" scheitert dann mit
    # Exitcode 128, weil der Pfad fehlt.
    for ordner in (TAGE, ROH):
        ordner.mkdir(exist_ok=True)
        (ordner / ".gitkeep").write_text("", encoding="utf-8")

    saetze, rohdateien, verworfen = rohdaten_einsammeln()
    print("%d Saetze aus %d Rohpaketen, %d Zeilen verworfen."
          % (len(saetze), len(rohdateien), verworfen))

    geaendert = in_tagesdateien(saetze) if saetze else []
    if geaendert:
        print("Tagesdateien geschrieben: %s" % ", ".join(geaendert))

    for pfad in rohdateien:
        pfad.unlink()
    (ROH / ".gitkeep").write_text("", encoding="utf-8")

    tageswerte = tage_fortschreiben(geaendert)
    print("Tage ausgewertet: %d" % len(tageswerte))

    daten = dashboard_bauen(tageswerte)
    groesse = DASHBOARD_JSON.stat().st_size // 1024
    print("dashboard.json: Tag %d, Woche %d, Monat %d Punkte, %d KB"
          % (len(daten["verlauf"]["tag"]), len(daten["verlauf"]["woche"]),
             len(daten["verlauf"]["monat"]), groesse))


if __name__ == "__main__":
    hauptprogramm()
