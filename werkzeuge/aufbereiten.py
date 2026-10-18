#!/usr/bin/env python3
"""Rohpakete des Geraets einarbeiten und die Daten fuers Dashboard bauen.

    python werkzeuge/aufbereiten.py

Ablauf:
    1. roh/*.csv einlesen
    2. in tage/JJJJ-MM-TT.csv einsortieren, Dubletten ueberschreiben
    3. verarbeitete Rohdateien loeschen
    4. betroffene NAECHTE neu auswerten (naechte.json)
    5. dashboard.json schreiben

Die Rechengroesse ist die NACHT, nicht der Kalendertag. Eine Nacht laeuft
ueber Mitternacht -- im Schlafzimmer ist das der ganze Punkt. Eine Nacht
traegt das Datum ihres MORGENS: Die Nacht "2026-10-18" reicht vom 17.10.
22:00 bis zum 18.10. 07:00. So heisst sie auch im Gespraech ("die Nacht
auf den 18.").

Das Archiv unter tage/ enthaelt nur GEMESSENE Werte. Absolute Feuchte und
Taupunkt werden hier gerechnet und wandern nur in dashboard.json -- siehe
die Begruendung in luft.py.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from luft import ableiten

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
    # Rechner in einer anderen Zeitzone waeren alle Nachtfenster verschoben,
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
NAECHTE_JSON = WURZEL / "naechte.json"
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
# Die Stellen 0 bis 18 bleiben unveraendert, Datum und Stunde lassen sich
# also weiterhin durch Abschneiden gewinnen.
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

# Nachtfenster: 22:00 bis 07:00.
NACHT_VON = 22
NACHT_BIS = 7

# CO2-Schwellen in ppm.
#
# 1000 ppm ist der Pettenkofer-Wert, seit 1858 die gaengige Grenze fuer
# "hygienisch einwandfreie" Raumluft. Ab rund 1400 ppm gilt sie allgemein
# als nicht mehr akzeptabel. Frischluft liegt heute bei etwa 420 ppm.
SCHWELLE_GELB = 1000
SCHWELLE_ROT = 1400

# Verlaufskurven: Name -> (Stunden zurueck, Raster in Minuten)
#
# Die volle Minutenaufloesung gibt es nur fuer die letzte Nacht -- das ist
# die Ansicht, in der man Einzelminuten wirklich ansieht. Der Tagesueberblick
# im 5-Minuten-Raster sieht praktisch gleich aus, spart aber rund 100 KB,
# die sonst bei JEDEM Seitenaufruf uebertragen wuerden.
VERLAEUFE = {
    "tag": (24, 5),
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
    """Ein Satz mit gerechneter absoluter Feuchte und Taupunkt."""
    brauchbar = satz["status"] in STATUS_VERWERTBAR
    co2 = zahl(satz["co2"]) if brauchbar else None
    t = zahl(satz["t"]) if brauchbar else None
    rh = zahl(satz["rh"]) if brauchbar else None
    ah, td = ableiten(t, rh)
    return {"z": satz["zeit"], "c": co2, "t": t, "rh": rh,
            "ah": ah, "td": td, "s": satz["status"]}


FELDER = ("c", "t", "rh", "ah", "td")


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


# ----------------------------------------------------------------- Naechte ---

def ist_nachtstunde(stunde):
    return stunde >= NACHT_VON or stunde < NACHT_BIS


def naechte_eines_tages(tag):
    """Welche Naechte koennen Daten dieses Tages enthalten?

    Der Abend (ab 22:00) gehoert zur Nacht auf den FOLGETAG, der fruehe
    Morgen (bis 07:00) zur Nacht auf diesen Tag.
    """
    d = datetime.strptime(tag, "%Y-%m-%d")
    return {tag, (d + timedelta(days=1)).strftime("%Y-%m-%d")}


def nacht_saetze(nacht):
    """Alle Saetze einer Nacht, ueber Mitternacht hinweg zusammengesucht."""
    d = datetime.strptime(nacht, "%Y-%m-%d")
    vorabend = (d - timedelta(days=1)).strftime("%Y-%m-%d")
    saetze = [s for s in tag_lesen(vorabend)
              if int(s["zeit"][11:13]) >= NACHT_VON]
    saetze += [s for s in tag_lesen(nacht)
               if int(s["zeit"][11:13]) < NACHT_BIS]
    saetze.sort(key=lambda s: augenblick(s["zeit"]))
    return saetze


def nacht_auswerten(nacht):
    punkte = [punkt(s) for s in nacht_saetze(nacht)]
    co2 = [p["c"] for p in punkte if p["c"] is not None]
    if not co2:
        return None

    # Bei Minutentakt ist jede Zeile eine Minute -- "Minuten ueber der
    # Schwelle" ist damit schlicht ein Abzaehlen. Fehlt eine Minute, zaehlt
    # sie nicht mit; das ist richtig, gemessen wurde da nichts.
    return {
        "nacht": nacht,
        "minuten": len(punkte),
        "messwerte": len(co2),
        "co2_mittel": round(sum(co2) / len(co2)),
        "co2_max": round(max(co2)),
        "co2_anfang": round(co2[0]),
        "co2_ende": round(co2[-1]),
        # Wie viel sich ueber die Nacht angesammelt hat. Der aussagekraef-
        # tigste Einzelwert: Er haengt an Belegung und Luftwechsel, nicht am
        # Ausgangsniveau.
        "anstieg": round(max(co2) - co2[0]),
        "min_ueber_gelb": sum(1 for w in co2 if w > SCHWELLE_GELB),
        "min_ueber_rot": sum(1 for w in co2 if w > SCHWELLE_ROT),
        "t_mittel": mittel([p["t"] for p in punkte]),
        "t_min": min((p["t"] for p in punkte if p["t"] is not None),
                     default=None),
        "rh_mittel": mittel([p["rh"] for p in punkte]),
        "ah_mittel": mittel([p["ah"] for p in punkte]),
        "td_max": max((p["td"] for p in punkte if p["td"] is not None),
                      default=None),
        "luecken": sum(1 for p in punkte if p["s"] not in STATUS_VERWERTBAR),
    }


def naechte_fortschreiben(geaenderte_tage):
    """Nur die betroffenen Naechte neu rechnen, der Rest bleibt stehen."""
    try:
        bestand = json.loads(NAECHTE_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        bestand = {}

    # Neu gerechnet wird nur, was sich geaendert hat. Sonst muesste die
    # Action mit wachsender Historie jedes Mal laenger rechnen -- bei 96
    # Laeufen am Tag faellt das nach einem Jahr ins Gewicht.
    betroffen = set()
    for tag in geaenderte_tage:
        betroffen |= naechte_eines_tages(tag)

    # Dazu alles, was noch nie gerechnet wurde. So faellt auch ein
    # nachtraeglich von Hand eingespielter Tag nicht durch.
    for tag in vorhandene_tage():
        betroffen |= {n for n in naechte_eines_tages(tag) if n not in bestand}

    for nacht in sorted(betroffen):
        ergebnis = nacht_auswerten(nacht)
        if ergebnis:
            bestand[nacht] = ergebnis
        elif nacht in bestand:
            del bestand[nacht]

    NAECHTE_JSON.write_text(
        json.dumps(bestand, ensure_ascii=False, separators=(",", ":"),
                   sort_keys=True), encoding="utf-8")
    return bestand


# --------------------------------------------------------------- Dashboard ---

def letzte_nacht(naechte):
    """Die juengste ausgewertete Nacht."""
    return sorted(naechte)[-1] if naechte else None


def nacht_verlauf(nacht):
    return [punkt(s) for s in nacht_saetze(nacht)] if nacht else []


def dashboard_bauen(naechte):
    verlauf = {}
    for name, (stunden, raster) in VERLAEUFE.items():
        verlauf[name] = rastern(punkte_ab(stunden), raster)

    nacht = letzte_nacht(naechte)
    verlauf["nacht"] = nacht_verlauf(nacht)

    letzter = None
    for p in reversed(verlauf["tag"]):
        if p["c"] is not None:
            letzter = p
            break

    reihe = [naechte[n] for n in sorted(naechte)]
    daten = {
        "erzeugt": jetzt().strftime(ANZEIGEFORM),
        "schwellen": {"gelb": SCHWELLE_GELB, "rot": SCHWELLE_ROT},
        "nachtfenster": {"von": NACHT_VON, "bis": NACHT_BIS},
        "jetzt": letzter,
        "letzte_nacht": naechte.get(nacht) if nacht else None,
        "verlauf": verlauf,
        "naechte": reihe,
        "tage": vorhandene_tage(),
        "summe": {
            "naechte": len(reihe),
            "erste_nacht": sorted(naechte)[0] if naechte else None,
            "min_ueber_gelb": sum(n["min_ueber_gelb"] for n in reihe),
            "min_ueber_rot": sum(n["min_ueber_rot"] for n in reihe),
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

    naechte = naechte_fortschreiben(geaendert)
    print("Naechte ausgewertet: %d" % len(naechte))

    daten = dashboard_bauen(naechte)
    groesse = DASHBOARD_JSON.stat().st_size // 1024
    print("dashboard.json: Nacht %d, Tag %d, Woche %d, Monat %d Punkte, %d KB"
          % (len(daten["verlauf"]["nacht"]), len(daten["verlauf"]["tag"]),
             len(daten["verlauf"]["woche"]), len(daten["verlauf"]["monat"]),
             groesse))


if __name__ == "__main__":
    hauptprogramm()
