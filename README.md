# Raumluft — Datenablage und Dashboard

Dieses Repository nimmt die Messdaten aus dem Schlafzimmer auf und zeigt sie
als Dashboard. Befüllt wird es vom ESP32, der alle 15 Minuten ein Paket
ablegt.

```
ESP32 ──WLAN──▶ roh/ ──GitHub Action──▶ tage/ + naechte.json ──▶ Dashboard
```

## Inhalt

| Datei / Ordner | Zweck |
|---|---|
| `roh/` | Rohpakete, wie das Gerät sie ablegt. Werden nach dem Einarbeiten gelöscht. |
| `tage/` | Eine CSV je Tag. **Das ist die Langzeitablage** — nur gemessene Werte. |
| `naechte.json` | Auswertung je Nacht. Wird fortgeschrieben, nicht neu gerechnet. |
| `dashboard.json` | Was die Seite lädt. Entsteht bei jedem Lauf neu, **nicht eingecheckt**. |
| `index.html` | Das Dashboard. Ohne Fremdbibliothek, die Diagramme sind handgezeichnetes SVG. |
| `werkzeuge/luft.py` | Absolute Feuchte und Taupunkt (Magnus-Formel). |
| `werkzeuge/test_luft.py` | 22 Selbsttests dazu. Laufen in der Action mit. |
| `werkzeuge/aufbereiten.py` | Rohpakete einarbeiten, Nächte auswerten, `dashboard.json` bauen. |
| `werkzeuge/beispiel.py` | Testdaten aus einer Mischungsbilanz, um alles ohne Hardware zu prüfen. |
| `.github/workflows/aufbereiten.yml` | Führt das aus und veröffentlicht die Seite. |

## Die Nacht ist die Recheneinheit

Nicht der Kalendertag. Eine Nacht läuft über Mitternacht, und im Schlafzimmer
ist genau das der Punkt — ein Tageswert von Mitternacht bis Mitternacht würde
jede Nacht in zwei Hälften zerschneiden.

Eine Nacht trägt das Datum ihres **Morgens**: Die Nacht `2026-10-18` reicht vom
17.10. 22:00 bis zum 18.10. 07:00. So heißt sie auch im Gespräch — „die Nacht
auf den 18.".

Der wichtigste Einzelwert je Nacht ist der **Anstieg**: wie viel ppm sich von
Beginn der Nacht bis zur Spitze angesammelt haben. Der hängt an Belegung und
Luftwechsel, nicht am Ausgangsniveau — zwei Nächte lassen sich damit
vergleichen, auch wenn der Abend unterschiedlich begonnen hat.

## Gerechnet wird hier, nicht auf dem Gerät

Das Archiv unter `tage/` enthält **nur, was der Sensor gemessen hat**: CO₂,
Temperatur, relative Feuchte. Absolute Feuchte und Taupunkt entstehen erst
beim Aufbereiten.

Das hat zwei Gründe:

1. **Ein Archiv aus Rohwerten lässt sich neu durchrechnen.** Stellt sich die
   Formel später als verbesserungswürdig heraus, bekommt die ganze Historie den
   besseren Wert. Ein Archiv aus Ergebnissen ist eingefroren.
2. Es spart rund ein Viertel der übertragenen Datenmenge.

## Einrichtung

### 1. Repository anlegen

Ein neues Repository auf GitHub erstellen und den **Inhalt dieses Ordners**
hineinlegen — nicht den Ordner selbst, `index.html` muss im Wurzelverzeichnis
liegen. Der Branch muss `main` heißen, sonst `GITHUB_BRANCH` in `config.h`
anpassen.

### 2. GitHub Pages einschalten

**Settings → Pages → Build and deployment → Source: GitHub Actions.**

Danach liegt das Dashboard unter
`https://<benutzername>.github.io/<repository>/`.

### 3. Zugriffstoken erzeugen

**Settings → Developer settings → Personal access tokens → Fine-grained tokens.**

- *Repository access*: nur dieses eine Repository
- *Permissions → Repository permissions → Contents*: **Read and write**
- sonst nichts

Das Token beginnt mit `github_pat_` und kommt in `raumluft/config.h` auf das
Gerät — **niemals in dieses Repository.** Die `.gitignore` fängt ein
versehentliches `config.h` ab.

## Ohne Hardware ausprobieren

Python ist installiert, aber nicht im PATH — daher der volle Pfad. Aus dem
Ordner `cloud/` heraus:

```bash
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" werkzeuge\test_luft.py
```

```bash
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" werkzeuge\beispiel.py
```

```bash
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" werkzeuge\aufbereiten.py
```

```bash
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m http.server 8778
```

Dann `http://localhost:8778/` öffnen.

`beispiel.py` erfindet keine Kurve, sondern rechnet eine **Mischungsbilanz**:
Zwei schlafende Menschen geben CO₂ und Wasserdampf in einen Raum von 35 m³ ab,
der Luftwechsel trägt beides wieder hinaus. Die Feuchte läuft durch dieselbe
Bilanz und wird erst zum Schluss in relative Feuchte zurückgerechnet — die
Testdaten sind dadurch in sich physikalisch stimmig. Jede Nacht bekommt einen
eigenen Luftwechsel, sonst sähen alle gleich aus.

> Es sind **erfundene** Daten. Vor dem ersten echten Betrieb `tage/*.csv`,
> `naechte.json` und `dashboard.json` löschen.

## Was das Dashboard zeigt

Es öffnet auf **der letzten Nacht**, nicht auf den letzten 24 Stunden — das ist
die Ansicht, um die es geht.

**Meldung** — aktueller CO₂-Wert und seine Bewertung. Meldet außerdem, wenn
länger als 25 Minuten nichts angekommen ist.

**Sechs Kacheln** — CO₂ jetzt, Anstieg der letzten Nacht, wie lange nachts über
1000 ppm, Temperatur, Feuchte, Taupunkt.

**Vier Diagramme** — CO₂ mit den Schwellen bei 1000 und 1400 ppm, Temperatur
mit Taupunkt, relative und absolute Feuchte getrennt. In den gröberen Ansichten
ist die Nacht hinterlegt. Überfahren mit Maus oder Finger liest Werte ab.

**Die Nächte im Vergleich** — je Nacht Anstieg, Spitze, Zeit über der Schwelle,
mittlere Temperatur und höchster Taupunkt. Das ist das Werkzeug, um
Lüftungsgewohnheiten zu beurteilen.

## Datenformat

`tage/JJJJ-MM-TT.csv`, Semikolon getrennt, Punkt als Dezimaltrennzeichen:

```
zeit;status;co2;t;rh
2026-10-17 06:30:00;ok;1842;19.40;55.98
```

| Spalte | Bedeutung |
|---|---|
| `zeit` | Ortszeit, `JJJJ-MM-TT HH:MM:SS` |
| `status` | `ok`, `sensor` (Lesefehler), `unplausibel`, `start` (Neustart) |
| `co2` | ppm |
| `t` | °C |
| `rh` | % relative Feuchte |

Bei `sensor` und `start` bleiben die Messspalten leer, die Spaltenzahl bleibt
gleich. Zeilen mit `unplausibel` **behalten ihre Werte**, gehen aber in keinen
Mittelwert ein — sie sind gekennzeichnet, nicht gelöscht.

Es gibt keine Zeitstufen-Spalte: Das Gerät hat dauerhaft WLAN und damit NTP.
Zeilen ohne gestellte Uhr werden gar nicht erst gepuffert, jede übertragene
Zeile hat also eine gültige Uhrzeit.

## Warum Pakete statt einzelner Messungen

Jeder Upload ist ein Commit. Eine Messung je Minute wären 1440 Commits am Tag —
die Versionsgeschichte wäre unbrauchbar und GitHub würde drosseln. Bei 15
Minuten sind es 96.

Der Commit, mit dem die Action ihre Ergebnisse zurückschreibt, trägt
`[skip ci]`. Sonst würde er sich selbst erneut auslösen: Er löscht Dateien
unter `roh/`, und genau darauf horcht der Auslöser.

## Datenmenge

Eine Zeile ist rund 40 Bytes, bei Minutentakt also **58 KB am Tag** oder 21 MB
im Jahr. Für ein Git-Repository unproblematisch, wächst aber stetig.

Das Dashboard lädt nicht die ganze Historie. `dashboard.json` enthält:

| Ansicht | Zeitraum | Raster |
|---|---|---|
| Letzte Nacht | 22:00 – 07:00 | 1 Minute |
| 24 Stunden | 1 Tag | 5 Minuten |
| Woche | 7 Tage | 15 Minuten |
| Monat | 30 Tage | 60 Minuten |

Dazu eine Zeile je Nacht. Die Datei bleibt damit bei rund 125 KB, gleichgültig
wie lange die Anlage schon läuft. Volle Minutenauflösung gibt es nur für die
letzte Nacht — die anderen Ansichten sähen damit gleich aus, kosteten aber bei
jedem Seitenaufruf rund 100 KB mehr.
