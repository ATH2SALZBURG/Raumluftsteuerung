#!/usr/bin/env python3
"""Regressionstest: Die Nacht der Zeitumstellung darf nichts verlieren.

    python werkzeuge/test_zeitumstellung.py

Am letzten Oktobersonntag springt die Uhr um 03:00 MESZ auf 02:00 MEZ
zurueck. Die Ortszeiten 02:00:00 bis 02:59:59 kommen dann ZWEIMAL vor, mit
verschiedenen Messwerten. Dieser Tag hat 25 Stunden.

Dieser Fall hat schon einmal zugeschlagen: Solange die Zeitstempel ohne
Zeitzonenversatz geschrieben wurden, hat die zweite Stunde die erste
ueberschrieben -- 60 Minuten still falscher Werte, lautlos, einmal im Jahr.
Behoben durch den Versatz am Zeitstempel ("...02:30:00+0200").

Der Test arbeitet in einem TEMPORAEREN Ordner. Er kann das echte Archiv
unter tage/ nicht anfassen -- ein Test, der Messdaten loeschen koennte,
waere schlimmer als gar keiner.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

WERKZEUGE = Path(__file__).resolve().parent

fehler = []


def pruefe(bedingung, text):
    print(("  ok   " if bedingung else "  FEHL ") + text)
    if not bedingung:
        fehler.append(text)


def zeilen_der_umstellungsnacht():
    """Der Zeitraum um die Umstellung, wie das Geraet ihn schreiben wuerde."""
    zeilen = []
    co2 = [600]

    def block(start, anzahl, versatz):
        z = start
        for _ in range(anzahl):
            co2[0] += 7
            zeilen.append("%s%s;ok;%d;19.50;52.00"
                          % (z.strftime("%Y-%m-%d %H:%M:%S"), versatz, co2[0]))
            z += timedelta(minutes=1)

    block(datetime(2026, 10, 24, 22, 0), 240, "+0200")   # 22:00 bis 01:59
    block(datetime(2026, 10, 25, 2, 0), 60, "+0200")     # 02:00 bis 02:59 MESZ
    block(datetime(2026, 10, 25, 2, 0), 60, "+0100")     # noch einmal, MEZ
    block(datetime(2026, 10, 25, 3, 0), 240, "+0100")    # 03:00 bis 06:59
    return zeilen


def main():
    zeilen = zeilen_der_umstellungsnacht()
    print("Die Umstellungsnacht umfasst %d Minuten." % len(zeilen))

    with tempfile.TemporaryDirectory(prefix="raumluft-test-") as tmp:
        spielwiese = Path(tmp)
        shutil.copytree(WERKZEUGE, spielwiese / "werkzeuge")
        (spielwiese / "roh").mkdir()

        # Auf zwei Pakete verteilt, mit UTC-Namen wie das Geraet sie vergibt
        (spielwiese / "roh" / "20261024T200000Z.csv").write_text(
            "\n".join(zeilen[:240]) + "\n", encoding="utf-8")
        (spielwiese / "roh" / "20261025T000000Z.csv").write_text(
            "\n".join(zeilen[240:]) + "\n", encoding="utf-8")

        lauf = subprocess.run(
            [sys.executable, str(spielwiese / "werkzeuge" / "aufbereiten.py")],
            cwd=spielwiese, capture_output=True, text=True)
        if lauf.returncode != 0:
            print("aufbereiten.py ist gescheitert:")
            print(lauf.stdout)
            print(lauf.stderr)
            sys.exit(1)

        archiv = []
        for tag in ("2026-10-24", "2026-10-25"):
            pfad = spielwiese / "tage" / ("%s.csv" % tag)
            if pfad.exists():
                archiv += pfad.read_text(encoding="utf-8").splitlines()[1:]

        print("Pruefungen")
        pruefe(len(archiv) == len(zeilen),
               "keine Zeile verloren: %d von %d im Archiv"
               % (len(archiv), len(zeilen)))

        doppelte = [z for z in archiv if z.startswith("2026-10-25 02:0")]
        pruefe(len(doppelte) == 20,
               "die doppelte Stunde steht zweimal da (02:00-02:09: %d statt 20)"
               % len(doppelte))

        mesz = [i for i, z in enumerate(archiv)
                if z.startswith("2026-10-25 02:") and "+0200" in z]
        mez = [i for i, z in enumerate(archiv)
               if z.startswith("2026-10-25 02:") and "+0100" in z]
        pruefe(bool(mesz) and bool(mez) and max(mesz) < min(mez),
               "Reihenfolge stimmt: Sommerzeitstunde vor Winterzeitstunde")

        tageswerte = json.loads(
            (spielwiese / "tage.json").read_text(encoding="utf-8"))
        tag = tageswerte.get("2026-10-25")
        pruefe(tag is not None, "der 25.10. ist ausgewertet")
        if tag:
            # 00:00-01:59 (120) + zweimal 02:00-02:59 (120) + 03:00-06:59 (240)
            pruefe(tag["minuten"] == 480,
                   "der 25.10. zaehlt 480 Minuten, die doppelte Stunde "
                   "eingerechnet (sind %d)" % tag["minuten"])
            pruefe(tag["co2_min"] < tag["co2_max"],
                   "Minimum und Maximum des Tages sind verschieden")

    print()
    if fehler:
        print("%d Pruefung(en) fehlgeschlagen:" % len(fehler))
        for f in fehler:
            print("  - %s" % f)
        sys.exit(1)
    print("Alle Pruefungen bestanden.")


if __name__ == "__main__":
    main()
