#!/usr/bin/env python3
"""Abgeleitete Luftgroessen aus Temperatur und relativer Feuchte.

Der SCD41 misst CO2, Temperatur und relative Feuchte. Absolute Feuchte und
Taupunkt sind daraus gerechnet -- und sie werden HIER gerechnet, nicht auf
dem Geraet.

Das ist Absicht und hat zwei Gruende:

  1. Das Archiv speichert nur, was tatsaechlich gemessen wurde. Gerechnete
     Werte, die einmal in einer Datei stehen, sind eingefroren. Stellt sich
     die Formel spaeter als verbesserungswuerdig heraus, laesst sich ein
     Archiv aus Rohwerten neu durchrechnen -- ein Archiv aus Ergebnissen
     nicht mehr.

  2. Es spart rund ein Viertel der uebertragenen Datenmenge.

Formel nach Magnus mit den Koeffizienten von Sonntag (1990), dem ueblichen
Satz fuer Temperaturen ueber 0 degC:

    E_s(T) = 6.112 * exp(17.62 * T / (243.12 + T))   [hPa]
    E      = RH / 100 * E_s(T)                       [hPa]
    AH     = 216.7 * E / (T + 273.15)                [g/m3]
    T_d    = 243.12 * v / (17.62 - v),  v = ln(E / 6.112)

Selbsttest:  python werkzeuge/test_luft.py
"""

from __future__ import annotations

import math

# Koeffizienten nach Sonntag
A = 17.62
B = 243.12
E0 = 6.112          # Saettigungsdampfdruck bei 0 degC, hPa
RHO = 216.7         # M_wasser / R = 18.016 / 8.3145 * 100, gerundet


def saettigungsdampfdruck(temperatur_c: float) -> float:
    """Saettigungsdampfdruck in hPa."""
    return E0 * math.exp(A * temperatur_c / (B + temperatur_c))


def dampfdruck(temperatur_c: float, relative_feuchte: float) -> float:
    """Tatsaechlicher Dampfdruck in hPa."""
    return relative_feuchte / 100.0 * saettigungsdampfdruck(temperatur_c)


def absolute_feuchte(temperatur_c: float, relative_feuchte: float) -> float:
    """Wassergehalt der Luft in g je m3.

    Anders als die relative Feuchte haengt dieser Wert nicht an der
    Temperatur. Nur damit laesst sich Raumluft mit Aussenluft vergleichen.
    """
    return RHO * dampfdruck(temperatur_c, relative_feuchte) / (
        temperatur_c + 273.15)


def taupunkt(temperatur_c: float, relative_feuchte: float):
    """Taupunkt in degC, oder None wenn nicht bestimmbar.

    Bei 0 % relativer Feuchte gibt es keinen Taupunkt -- der Logarithmus von
    null ist nicht definiert. Dann None, nicht irgendeine Zahl.
    """
    if relative_feuchte <= 0.0:
        return None
    v = math.log(dampfdruck(temperatur_c, relative_feuchte) / E0)
    nenner = A - v
    if abs(nenner) < 1e-9:
        return None
    return B * v / nenner


def ableiten(temperatur_c, relative_feuchte):
    """(absolute_feuchte, taupunkt) oder (None, None) bei fehlender Eingabe."""
    if temperatur_c is None or relative_feuchte is None:
        return None, None
    return (round(absolute_feuchte(temperatur_c, relative_feuchte), 2),
            None if taupunkt(temperatur_c, relative_feuchte) is None
            else round(taupunkt(temperatur_c, relative_feuchte), 2))
