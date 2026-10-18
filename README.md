# Raumluft — Datenablage und Dashboard

Dieses Repository nimmt die Messdaten auf und zeigt sie als Dashboard.
Befüllt wird es vom ESP32, der alle 15 Minuten ein Paket ablegt.

```
ESP32 ──WLAN──▶ roh/ ──GitHub Action──▶ tage/ + tage.json ──▶ Dashboard
```

## Inhalt

| Datei / Ordner | Zweck |
|---|---|
| `roh/` | Rohpakete, wie das Gerät sie ablegt. Werden nach dem Einarbeiten gelöscht. |
| `tage/` | Eine CSV je Tag. **Das ist die Langzeitablage** — nur gemessene Werte. |
| `tage.json` | Auswertung je Tag. Wird fortgeschrieben, nicht neu gerechnet. |
| `dashboard.json` | Was die Seite lädt. Entsteht bei jedem Lauf neu, **nicht eingecheckt**. |
| `index.html` | Das Dashboard. Ohne Fremdbibliothek, Tacho und Diagramme sind handgezeichnetes SVG. |
| `werkzeuge/luft.py` | Absolute Feuchte und Taupunkt (Magnus-Formel). |
| `werkzeuge/test_luft.py` | Selbsttests dazu. |
| `werkzeuge/test_zeitumstellung.py` | Regressionstest für die Nacht der Zeitumstellung. |
| `werkzeuge/aufbereiten.py` | Rohpakete einarbeiten, Tage auswerten, `dashboard.json` bauen. |
| `werkzeuge/beispiel.py` | Testdaten aus einer Mischungsbilanz, um alles ohne Hardware zu prüfen. |
| `.github/workflows/aufbereiten.yml` | Führt das aus und veröffentlicht die Seite. |

## Die Bewertung

CO₂ wird nach der dreistufigen hygienischen Einstufung des **Umweltbundesamts**
bewertet (Ad-hoc-Arbeitsgruppe Innenraumrichtwerte 2008, fortgeführt in
[Hygienische Leitwerte für die Innenraumluft](https://www.umweltbundesamt.de/system/files/medien/4031/bilder/dateien/hygienische_leitwerte_0.pdf)):

| CO₂ | Bewertung | Empfehlung |
|---|---|---|
| unter 1000 ppm | hygienisch unbedenklich | keine Maßnahme nötig |
| 1000–2000 ppm | hygienisch auffällig | mehr Außenluft zuführen, lüften |
| über 2000 ppm | hygienisch inakzeptabel | lüften; reicht das nicht, ist der Raum nicht ausreichend belüftbar |

Frischluft im Freien liegt derzeit bei rund 420 ppm.

Für **Temperatur** (20–24 °C) und **relative Feuchte** (40–60 %) sind die
Bereiche im Dashboard Komfort- und Bauschutzwerte, keine Gesundheitsgrenzen.
Dauerhaft über 60 % relative Feuchte begünstigt Schimmelwachstum.

## Gerechnet wird hier, nicht auf dem Gerät

Das Archiv unter `tage/` enthält **nur, was der Sensor gemessen hat**: CO₂,
Temperatur, relative Feuchte. Die absolute Feuchte entsteht erst beim
Aufbereiten.

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

### 3. Zugriffstoken erzeugen

**Settings → Developer settings → Personal access tokens → Fine-grained tokens.**

- *Repository access*: nur dieses eine Repository
- *Permissions → Repository permissions → Contents*: **Read and write**
- sonst nichts

Das Token kommt in `raumluft/config.h` auf das Gerät — **niemals in dieses
Repository.** Die `.gitignore` fängt ein versehentliches `config.h` ab.

> **Workflow-Dateien kann dieses Token nicht schreiben**, und das ist Absicht.
> Ein PUT auf `.github/workflows/` antwortet mit 403. Diese eine Datei wird von
> Hand über die Weboberfläche angelegt. Das Token liegt im Klartext auf einem
> ESP32 und soll nur Messdaten ablegen dürfen — nicht den Automatisierungscode
> des Repositorys ändern.

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
Zwei Menschen geben CO₂ und Wasserdampf in einen Raum von 35 m³ ab, solange sie
da sind, der Luftwechsel trägt beides wieder hinaus. Die Feuchte läuft durch
dieselbe Bilanz und wird erst zum Schluss in relative Feuchte zurückgerechnet —
die Testdaten sind dadurch in sich physikalisch stimmig. Jeder Tag bekommt
einen eigenen Luftwechsel, sonst sähen alle gleich aus.

> Es sind **erfundene** Daten. Vor dem ersten echten Betrieb `tage/*.csv`,
> `tage.json` und `dashboard.json` löschen.

Läuft hier eine Meldung auf, dass `Europe/Vienna` nicht ladbar sei: Windows
bringt keine Zeitzonendatenbank mit. Es gilt dann die Zeitzone dieses Rechners,
was in Mitteleuropa dasselbe Ergebnis liefert. Abstellen mit
`python -m pip install tzdata`.

## Was das Dashboard zeigt

**Der Tacho** — CO₂ als Zeigerinstrument mit grünem, orangem und rotem Bereich,
dazu die Einstufung im Klartext und was zu tun ist. Meldet außerdem, wenn
länger als 25 Minuten nichts angekommen ist.

**Fünf Kacheln** — CO₂, Temperatur, relative und absolute Feuchte, dazu die
Zeit über den Schwellen am laufenden Tag. Der farbige Rand links zeigt die
Bewertung.

**Vier Diagramme** — CO₂ mit beiden Schwellen, Temperatur, relative und
absolute Feuchte. Überfahren mit Maus oder Finger liest Werte ab.

**Die Tage im Vergleich** — je Tag Mittelwert, Spitze und die Zeit über den
Schwellen als Balken.

## Datenformat

`tage/JJJJ-MM-TT.csv`, Semikolon getrennt, Punkt als Dezimaltrennzeichen:

```
zeit;status;co2;t;rh
2026-10-18 17:52:01+0200;ok;1298;24.52;51.62
```

| Spalte | Bedeutung |
|---|---|
| `zeit` | Ortszeit mit Zeitzonenversatz |
| `status` | `ok`, `einlauf`, `sensor`, `unplausibel`, `start` |
| `co2` | ppm |
| `t` | °C |
| `rh` | % relative Feuchte |

**Zum Status:**

- `einlauf` — der Sensor war noch am Einschwingen. Nach dem Start meldet er
  mehrere Minuten lang eine zu hohe Temperatur (gemessen: 27,6 °C statt 22,5).
  Diese Zeilen stehen im Archiv, gehen aber in keinen Mittelwert ein.
- `sensor` — Lesefehler, die Messspalten bleiben leer.
- `unplausibel` — Werte außerhalb des Erwartbaren. Sie **behalten ihre Werte**,
  gehen aber in keinen Mittelwert ein.
- `start` — Neustart des Geräts.

Die Spaltenzahl bleibt immer gleich.

### Der Zeitzonenversatz ist kein Zierrat

Am letzten Oktobersonntag springt die Uhr von 03:00 auf 02:00 zurück. Die
Ortszeiten 02:00:00 bis 02:59:59 kommen dann **zweimal** vor, mit
verschiedenen Messwerten. Ohne den Versatz wären das dieselben Zeitstempel —
und da hier nach Zeitstempel abgelegt wird, würde die zweite Stunde die erste
überschreiben: 60 Minuten still falscher Werte, einmal im Jahr.

Genau das ist einmal passiert und durch `test_zeitumstellung.py` abgesichert.
Der Test arbeitet in einem Temporärordner und kann das echte Archiv nicht
anfassen.

## Warum Pakete statt einzelner Messungen

Jeder Upload ist ein Commit. Eine Messung je Minute wären 1440 Commits am Tag —
die Versionsgeschichte wäre unbrauchbar und GitHub würde drosseln. Bei 15
Minuten sind es 96.

Der Commit, mit dem die Action ihre Ergebnisse zurückschreibt, trägt
`[skip ci]`. Sonst würde er sich selbst erneut auslösen: Er löscht Dateien
unter `roh/`, und genau darauf horcht der Auslöser.

## Datenmenge

Eine Zeile ist rund 45 Bytes, bei Minutentakt also **65 KB am Tag** oder 24 MB
im Jahr. Für ein Git-Repository unproblematisch, wächst aber stetig.

Das Dashboard lädt nicht die ganze Historie. `dashboard.json` enthält:

| Ansicht | Zeitraum | Raster |
|---|---|---|
| 24 Stunden | 1 Tag | 1 Minute |
| Woche | 7 Tage | 15 Minuten |
| Monat | 30 Tage | 60 Minuten |

Dazu eine Zeile je Tag. Die Datei bleibt damit bei rund 165 KB, gleichgültig
wie lange die Anlage schon läuft.
