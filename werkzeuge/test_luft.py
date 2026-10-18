#!/usr/bin/env python3
"""Selbsttest der Luftformeln.

    python werkzeuge/test_luft.py

Prueft nicht, ob die Zahlen "irgendwie plausibel" aussehen, sondern gegen
Eigenschaften, die physikalisch gelten muessen. Eine Formel, die diese Tests
besteht, kann noch falsch sein -- eine, die sie nicht besteht, ist es sicher.
"""

from __future__ import annotations

import sys

import luft

fehler = []


def pruefe(bedingung, beschreibung):
    if bedingung:
        print("  ok   %s" % beschreibung)
    else:
        print("  FEHL %s" % beschreibung)
        fehler.append(beschreibung)


def nahe(a, b, toleranz, beschreibung):
    pruefe(a is not None and abs(a - b) <= toleranz,
           "%s (ist %s, erwartet %s +- %s)" % (beschreibung, a, b, toleranz))


print("Saettigungsdampfdruck")
#
# Verglichen wird mit den EXAKTEN Werten (Wagner/Pruss, IAPWS). Die
# Magnus-Formel ist eine Naeherung und liegt im Zimmertemperaturbereich
# rund 0,3 % darunter -- das ist bekannt und liegt innerhalb der fuer
# diesen Koeffizientensatz angegebenen 0,4 %.
#
# Dass das hier genuegt, zeigt ein Vergleich mit dem Sensor: Der SCD41
# misst die relative Feuchte auf +-6 %rF genau. Gegen diese 6 % ist eine
# Formelabweichung von 0,3 % bedeutungslos. Eine "genauere" Formel wuerde
# nichts verbessern, nur Genauigkeit vortaeuschen.
def relativ(ist, exakt, grenze_prozent, beschreibung):
    abweichung = abs(ist - exakt) / exakt * 100.0
    pruefe(abweichung <= grenze_prozent,
           "%s (ist %.3f, exakt %.3f, Abweichung %.2f %% <= %.2f %%)"
           % (beschreibung, ist, exakt, abweichung, grenze_prozent))

relativ(luft.saettigungsdampfdruck(0), 6.1121, 0.05, "bei 0 degC")
relativ(luft.saettigungsdampfdruck(20), 23.393, 0.4, "bei 20 degC")
relativ(luft.saettigungsdampfdruck(30), 42.455, 0.4, "bei 30 degC")
relativ(luft.saettigungsdampfdruck(-5), 4.2148, 0.4, "bei -5 degC")

pruefe(luft.saettigungsdampfdruck(25) > luft.saettigungsdampfdruck(20),
       "steigt mit der Temperatur")

print("Taupunkt")
# Die schaerfste Probe: Bei 100 % Feuchte IST die Lufttemperatur der
# Taupunkt. Trifft die Umkehrformel das nicht, passen die Koeffizienten
# der Hin- und Rueckrichtung nicht zusammen.
for t in (-5.0, 0.0, 5.0, 12.5, 20.0, 25.0, 35.0):
    nahe(luft.taupunkt(t, 100.0), t, 0.01,
         "bei %.1f degC und 100 %%rF ist der Taupunkt die Temperatur" % t)

pruefe(luft.taupunkt(20.0, 50.0) < 20.0,
       "unter 100 %rF liegt der Taupunkt unter der Temperatur")
pruefe(luft.taupunkt(20.0, 0.0) is None,
       "bei 0 %rF ist der Taupunkt nicht bestimmbar (None)")

# Der Taupunkt haengt nur am Wassergehalt. Zwei Zustaende mit gleichem
# Dampfdruck muessen denselben Taupunkt haben, auch bei anderer Temperatur.
e = luft.dampfdruck(20.0, 50.0)
rh_bei_25 = e / luft.saettigungsdampfdruck(25.0) * 100.0
nahe(luft.taupunkt(25.0, rh_bei_25), luft.taupunkt(20.0, 50.0), 0.01,
     "gleicher Dampfdruck bei anderer Temperatur gibt gleichen Taupunkt")

print("Absolute Feuchte")
nahe(luft.absolute_feuchte(20.0, 50.0), 8.63, 0.05,
     "20 degC / 50 %rF rund 8,6 g/m3")
nahe(luft.absolute_feuchte(0.0, 100.0), 4.85, 0.05,
     "0 degC / 100 %rF rund 4,85 g/m3")
nahe(luft.absolute_feuchte(20.0, 0.0), 0.0, 1e-9,
     "0 %rF bedeutet 0 g/m3")

pruefe(luft.absolute_feuchte(20.0, 50.0) > luft.absolute_feuchte(10.0, 50.0),
       "waermere Luft fasst bei gleicher relativer Feuchte mehr Wasser")

# Kalte Winterluft mit hoher relativer Feuchte ist TROCKENER als warme
# Raumluft mit mittlerer. Genau diese Eigenschaft macht die relative
# Feuchte als Vergleichsgroesse unbrauchbar.
pruefe(luft.absolute_feuchte(-5.0, 90.0) < luft.absolute_feuchte(20.0, 50.0),
       "-5 degC bei 90 %rF ist trockener als 20 degC bei 50 %rF")

print("Rundung und fehlende Werte")
pruefe(luft.ableiten(None, 50.0) == (None, None),
       "fehlende Temperatur gibt (None, None)")
pruefe(luft.ableiten(20.0, None) == (None, None),
       "fehlende Feuchte gibt (None, None)")
ah, td = luft.ableiten(19.43, 49.80)
nahe(ah, 8.30, 0.01, "Beispielwert absolute Feuchte")
nahe(td, 8.67, 0.01, "Beispielwert Taupunkt")

print()
if fehler:
    print("%d von den Pruefungen fehlgeschlagen:" % len(fehler))
    for f in fehler:
        print("  - %s" % f)
    sys.exit(1)
print("Alle Pruefungen bestanden.")
