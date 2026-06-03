# Reaktionsgeschwindigkeitstest

Eine einfache Python-App zur Messung der Reaktionszeit mit grafischer Oberfläche. Nach dem Start wartet das Programm eine zufällige Zeitspanne, färbt das Klickfeld grün und misst die Zeit bis zum Klick in Millisekunden.

## Funktionen

- Messung der Reaktionszeit in ms
- Speicherung aller Ergebnisse in einer CSV-Datei
- Anzeige von Mittelwert und Standardabweichung
- automatische Session-Auswertung bei Pausen über 1 Stunde
- gleitender Mittelwert über die letzten 5 Messungen
- grafische Darstellung der Einzelmessungen und Mittelwerte
- CSV-Export der Messdaten
- Zurücksetzen aller gespeicherten Ergebnisse

## Voraussetzungen

```bash
pip install matplotlib
````

Tkinter ist bei den meisten Python-Installationen bereits enthalten.

## Start

```bash
python reaktionstest.py
```

## Datenspeicherung

Die Messergebnisse werden automatisch in der Datei `reaction_results.csv` im gleichen Ordner gespeichert.


