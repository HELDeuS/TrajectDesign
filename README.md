# TrajectDesign

Webapplicatie voor het ontwerpen, weergeven en aanpassen van leertrajecten voor een mbo-ict-opleiding.

## Rollen

- **Ontwerper**: leertrajecten aanmaken en aanpassen, modules en onderwijsproducten definiëren, leerdoelen/-uitkomsten vastleggen en koppelen, afhankelijkheden tussen modules instellen.
- **Docent**: resultaten van studenten beoordelen (cijfers per onderwijsproduct, voldoende/onvoldoende per leerdoel/-uitkomst van een onderwijsproduct en van een module).
- **Student**: eigen voortgang bekijken in een boomweergave met statussen (niet gestart / bezig / behaald / geblokkeerd).

## Kernregels

- Een module heeft een **maximale SBU**; als de som van de SBU van de onderwijsproducten die overschrijdt, toont de applicatie een waarschuwing.
- Modules hebben **afhankelijkheden**: per module is configureerbaar of **alle** vereiste modules behaald moeten zijn, of **ten minste één**.
- De **behaalregel** van een module is per module te kiezen:
  - *percentage*: de module is behaald als minstens het drempelpercentage van de onderwijsproducten met een voldoende cijfer is beoordeeld;
  - *doelen*: de module is behaald als alle leerdoelen en -uitkomsten van de module voldoende zijn; de resultaten van onderwijsproducten tellen dan niet mee.
- Leerdoelen en -uitkomsten van onderwijsproducten zijn **koppelbaar** aan de leerdoelen en -uitkomsten van de module (en omgekeerd zichtbaar).

## Lokaal draaien

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

De applicatie luistert standaard op **alle netwerkinterfaces** (`0.0.0.0`) op poort 5000, zodat hij vanaf andere machines in het netwerk bereikbaar is (bijv. op een Ubuntu-server via `http://<server-ip>:5000`). Configuratie via omgevingsvariabelen:

- `HOST` – bind-adres (standaard `0.0.0.0`)
- `PORT` – poort (standaard `5000`)
- `DEBUG` – debug-modus aan/uit (standaard uit)
- `TRAJECT_DB` – pad naar de SQLite-database (standaard `traject.db` naast `app.py`)

De SQLite-database wordt bij de eerste start aangemaakt en gevuld met demogegevens (gebruikers, een voorbeeldleertraject met modules, onderwijsproducten en leerdoelen).

### Productie-installatie op Ubuntu (optioneel)

De ingebouwde Flask-server is geschikt voor ontwikkeling en klein gebruik. Voor productie kun je beter een WSGI-server gebruiken, bijvoorbeeld met `gunicorn`:

```bash
pip install gunicorn
gunicorn --bind 0.0.0.0:5000 app:app
```

Zorg dat de poort openstaat in de firewall (`sudo ufw allow 5000/tcp`) en dat verkeer van buiten alleen via een beveiligde route (bijv. een reverse proxy met HTTPS) loopt.

## Tests

De kernregels zijn gedekt door automatische tests (behaalregels, afhankelijkheden, SBU-waarschuwing, koppelingen, persistentie):

```bash
python test_regels.py
```

De tests gebruiken een tijdelijke database en raken de eigen `traject.db` niet aan.

## Opbouw

- `app.py` – Flask-applicatie: routes, sessie/rollen en bedrijfslogica (modulestatus, behaalregels, SBU-controle).
- `test_regels.py` – automatische tests voor de bedrijfsregels.
- `schema.sql` – datamodel (SQLite).
- `templates/` – Jinja2-templates (Nederlandstalige UI).
- `static/style.css` – styling.

## Datamodel (kern)

- `traject` → `module` (max SBU, behaalregel, drempelpercentage, voldoende-cijfer, afhankelijkheidmodus)
- `module_afhankelijkheid`: vereiste voorgangers van een module
- `module_doel` / `product_doel`: leerdoelen en -uitkomsten op module- en productniveau, gekoppeld via `product_doel.module_doel_id`
- `beoordeling`: cijfer per student per onderwijsproduct
- `product_doel_beoordeling` / `module_doel_beoordeling`: voldoende/onvoldoende per doel per student
- `traject_deelnemer`: koppeling student ↔ leertraject
