# LernWerkstatt (Kurzfassung)

LernWerkstatt erzeugt mit einem Sprachmodell interaktive Lerneinheiten. Sie
beschreiben, was Lernende schon wissen und was sie lernen wollen, laden bei
Bedarf eigenes Material hoch und erhalten eine einzelne HTML-Datei: Lektionen
mit Fließtext, Diagrammen, Grafiken, Formeln, Simulatoren und
Selbstkontrollen, ein Glossar, einen Anwendungsteil je Kapitel und einen
Abschlusstest. Die Datei funktioniert offline und braucht keinen Server.

Gedacht ist das Werkzeug für Hochschulen und ähnliche Einrichtungen, die
themenspezifisches Lernmaterial auf eigener Infrastruktur und mit eigenen
Modellen erstellen wollen.

- **Umfang wird hergeleitet, nicht eingestellt:** Eine Gap-Analyse bildet ein
  Konzeptinventar mit Behandlungsklassen. Daraus ergeben sich Lernzeit und
  Format, vom kurzen Impuls bis zum Buch. Vor der Produktion prüfen und
  bearbeiten Sie das Inventar an einem Kontrollpunkt.
- **Oberfläche auf Deutsch und Englisch**, Lerneinheiten auf Deutsch,
  Englisch, Französisch, Spanisch oder Italienisch.
- **Produktion auf dem Server:** Das Fenster darf geschlossen werden; mit dem
  Abholcode lässt sich ein Auftrag fortsetzen oder löschen.
- **Prüfen und Reparieren:** Format, Struktur, Querverweise,
  Konzeptabdeckung, Simulatoren, Diagrammsyntax und Sprachmischung werden
  deterministisch geprüft. Mit eigenem Material kommt eine Faktenprüfung
  dazu.

## Schnellstart

Voraussetzungen: Docker und ein OpenAI-kompatibler LLM-Endpunkt.

```bash
git clone https://github.com/maltedreyer-5/lernwerkstatt.git
cd lernwerkstatt
cp .env.example .env      # LLM1_BASE_URL, LLM1_API_KEY, LLM1_MODEL eintragen
docker compose -f deploy/docker-compose.example.yml up -d --build
```

Dann <http://127.0.0.1:7860/lernwerkstatt/> öffnen. Für eine deutsche
Oberfläche unabhängig von der Browsersprache `APP_LANGUAGE=de` in `.env`
setzen.

Die Oberfläche hat keine Benutzerkonten. Bevor sie aus einem Netz erreichbar
ist, gehört ein Reverse Proxy mit Zugriffsschutz davor.

## Grenzen

Die Prüfungen belegen nicht, dass der Inhalt fachlich richtig ist. Lassen
Sie Lerneinheiten vor dem Einsatz in der Lehre fachlich prüfen; jede Einheit
weist selbst darauf hin, dass sie mit KI-Unterstützung erstellt wurde.

## Dokumentation

Die vollständige Dokumentation ist englisch: [README](README.md),
[Installation](docs/installation.md), [Konfiguration](docs/configuration.md),
[Betrieb](docs/operations.md), [Architektur](docs/architecture.md),
[Format](docs/unit-format.md), [Didaktik-Kriterien](docs/didactics-criteria.md),
[Entwicklung](docs/development.md).

Lizenz: MIT.
