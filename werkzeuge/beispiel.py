#!/usr/bin/env python3
"""Beispieldaten erzeugen, um die Verarbeitung ohne Hardware zu pruefen.

    python werkzeuge/beispiel.py
    python werkzeuge/aufbereiten.py

Legt Rohpakete unter roh/ ab, genau im Format des Geraets.

Die Werte entstehen aus einer MISCHUNGSBILANZ, nicht aus einer passend
hingebogenen Kurve: Zwei Menschen geben CO2 und Wasserdampf in einen Raum
bekannter Groesse ab, solange sie da sind, und der Luftwechsel traegt
beides wieder hinaus.

    dC/dt = G / V * 1e6  -  n * (C - C_aussen)

    C         ppm im Raum          G   m3/h CO2-Abgabe
    C_aussen  ppm draussen         V   m3 Raumvolumen
    n         Luftwechsel je h

Die Feuchte laeuft durch dieselbe Bilanz, nur in g/m3, und wird erst zum
Schluss in relative Feuchte zurueckgerechnet. Dadurch sind die Testdaten in
sich physikalisch stimmig -- und damit auch brauchbar, um die Formeln in
luft.py gegen eine unabhaengige Rechnung zu halten.

Es sind erfundene Daten. Sie pruefen die Verarbeitung, sie sagen nichts
ueber echte Raumluft.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from luft import saettigungsdampfdruck

# Gerechnet wird in UTC, geschrieben in Ortszeit mit Versatz -- genau wie es
# das Geraet tut. Eine Minute in UTC ist immer eine Minute; in Ortszeit
# gerechnet verschluckt die Zeitumstellung sonst eine Stunde oder erzeugt
# sie doppelt, je nach Richtung.
try:
    from zoneinfo import ZoneInfo
    ZONE = ZoneInfo("Europe/Vienna")
except Exception as _grund:
    # Siehe aufbereiten.py: Windows ohne das Paket "tzdata".
    ZONE = datetime.now().astimezone().tzinfo
    print("HINWEIS: Zeitzone Europe/Vienna nicht ladbar (%s)." % _grund)
    print("         Die Beispieldaten nutzen die Zeitzone dieses Rechners.")

WURZEL = Path(__file__).resolve().parent.parent
ROH = WURZEL / "roh"

# --- Raum und Belegung -------------------------------------------------------
VOLUMEN_M3 = 35.0            # 3,5 x 4,0 x 2,5 m
PERSONEN = 2
CO2_JE_PERSON_M3_H = 0.015   # ruhender Erwachsener
WASSER_JE_PERSON_G_H = 30.0  # ruhender Erwachsener

LUFTWECHSEL_ZU = 0.45        # Fenster zu, je Stunde
LUFTWECHSEL_OFFEN = 5.0      # Fenster offen

CO2_AUSSEN_PPM = 420.0
AH_AUSSEN_G_M3 = 6.5         # Oktober, gemaessigt

# --- Tagesablauf -------------------------------------------------------------
#
# Der Raum ist abends und ueber Nacht belegt, tagsueber leer. Das ergibt
# einen Tagesgang, an dem sich die Auswertung pruefen laesst.
ANWESEND_VON = 17
ANWESEND_BIS = 8
# (Stunde, Minute, Dauer in Minuten)
LUEFTEN = [(8, 5, 20), (13, 0, 10), (20, 30, 15)]

TAGE_ANZAHL = 4
TAKT_MIN = 1

# Ein paar gestoerte Minuten einstreuen, damit auch die Fehlerpfade der
# Verarbeitung und des Dashboards einmal durchlaufen werden.
ANTEIL_SENSORFEHLER = 0.0015
ANTEIL_UNPLAUSIBEL = 0.0004


def relative_feuchte(ah_g_m3, temperatur_c):
    """Rueckrechnung absolute -> relative Feuchte."""
    dampfdruck = ah_g_m3 * (temperatur_c + 273.15) / 216.7
    return dampfdruck / saettigungsdampfdruck(temperatur_c) * 100.0


def luftwechsel_des_tages(zeit):
    """Jeder Tag ein etwas anderer Luftwechsel.

    In Wirklichkeit ist der nie zweimal gleich -- Tuer angelehnt, Fenster
    gekippt, Wind. Ohne diese Streuung saehen alle Tage identisch aus und
    die Vergleichsansicht liesse sich nicht beurteilen.
    """
    return LUFTWECHSEL_ZU * random.Random(
        4101 + zeit.toordinal()).uniform(0.6, 1.5)


def fenster_offen(zeit):
    for stunde, minute, dauer in LUEFTEN:
        beginn = zeit.replace(hour=stunde, minute=minute, second=0)
        if beginn <= zeit < beginn + timedelta(minutes=dauer):
            return True
    return False


def belegt(zeit):
    return zeit.hour >= ANWESEND_VON or zeit.hour < ANWESEND_BIS


def erzeugen():
    random.seed(4101)          # immer dieselben Daten
    ROH.mkdir(parents=True, exist_ok=True)

    ende = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    zeit_utc = (ende - timedelta(days=TAGE_ANZAHL)).replace(minute=0)

    co2 = CO2_AUSSEN_PPM + 90.0
    ah = AH_AUSSEN_G_M3 + 1.2
    dt_h = TAKT_MIN / 60.0

    zeilen = []
    while zeit_utc < ende:
        # Ortszeit nur zum Entscheiden und zum Aufschreiben.
        zeit = zeit_utc.astimezone(ZONE)

        offen = fenster_offen(zeit)
        n = LUFTWECHSEL_OFFEN if offen else luftwechsel_des_tages(zeit)
        leute = PERSONEN if belegt(zeit) else 0

        # Mischungsbilanz, Schritt fuer Schritt (Euler, 1 Minute)
        co2 += (leute * CO2_JE_PERSON_M3_H / VOLUMEN_M3 * 1e6
                - n * (co2 - CO2_AUSSEN_PPM)) * dt_h
        ah += (leute * WASSER_JE_PERSON_G_H / VOLUMEN_M3
               - n * (ah - AH_AUSSEN_G_M3)) * dt_h

        # Temperatur: traeger Tagesgang, beim Lueften faellt sie ab
        stunde = zeit.hour + zeit.minute / 60.0
        temperatur = 20.1 + 1.0 * math.sin((stunde - 10) / 24 * 2 * math.pi)
        if offen:
            temperatur -= 1.3
        temperatur += random.gauss(0, 0.04)

        rh = relative_feuchte(ah, temperatur)
        rh = min(99.0, max(10.0, rh + random.gauss(0, 0.25)))
        co2_gemessen = max(CO2_AUSSEN_PPM - 15.0, co2 + random.gauss(0, 6))

        # Ortszeit MIT Versatz, so wie das Geraet sie schreibt.
        stempel = zeit.strftime("%Y-%m-%d %H:%M:%S%z")

        wuerfel = random.random()
        if wuerfel < ANTEIL_SENSORFEHLER:
            # Lesefehler: Zeile bleibt, Werte fehlen
            zeilen.append("%s;sensor;;;" % stempel)
        elif wuerfel < ANTEIL_SENSORFEHLER + ANTEIL_UNPLAUSIBEL:
            # Werte da, aber ausserhalb des Erwartbaren
            zeilen.append("%s;unplausibel;%d;%.2f;%.2f"
                          % (stempel, 41000, temperatur, rh))
        else:
            zeilen.append("%s;ok;%d;%.2f;%.2f"
                          % (stempel, round(co2_gemessen), temperatur, rh))

        zeit_utc += timedelta(minutes=TAKT_MIN)

    # In Paketen zu 15 Zeilen ablegen, so wie das Geraet es tut -- mit
    # UTC-Dateinamen, damit sie auch in der Umstellungsnacht eindeutig sind.
    pakete = 0
    for i in range(0, len(zeilen), 15):
        stueck = zeilen[i:i + 15]
        erste = datetime.strptime(stueck[0][:24], "%Y-%m-%d %H:%M:%S%z")
        name = erste.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (ROH / ("%s.csv" % name)).write_text("\n".join(stueck) + "\n",
                                             encoding="utf-8")
        pakete += 1

    print("%d Zeilen in %d Rohpaketen unter %s" % (len(zeilen), pakete, ROH))
    print("Weiter mit: python werkzeuge/aufbereiten.py")


if __name__ == "__main__":
    erzeugen()
