# SQL Rewrite Validator

Een validatieframework dat controleert of een herschreven SQL-query (bijvoorbeeld door een LLM) **geldig, resultaat-gelijk en aantoonbaar sneller** is dan het origineel, plus een testbank om herschrijvingen op grote schaal te laten maken en beoordelen.

---

## Inleiding

### Het probleem

Een LLM kan een trage SQL-query herschrijven naar iets dat er sneller uitziet. Maar een herschrijving die er goed uitziet, is daarmee nog niet goed. Er zijn drie manieren waarop het misgaat:

- De herschrijving is **geen geldige of toegestane query** (bijvoorbeeld een `DELETE` in een CTE).
- De herschrijving geeft een **ander resultaat**. Een enkele verandering is genoeg, zoals een vervangen statuswaarde, een weggevallen filter of een andere sortering. Zo'n fout leest een mens snel over.
- De herschrijving geeft hetzelfde resultaat, maar is **niet sneller**, of zelfs trager.

### Wat deze repository doet

Deze repository beoordeelt elke herschrijving automatisch in drie stappen:

1. **Statische controle.** Is het precies één `SELECT`, zonder schrijfacties?
2. **Resultaatvergelijking.** Geeft de herschrijving op meerdere parametersets exact dezelfde rijen als het origineel?
3. **Tijdmeting.** Is de herschrijving op een eerlijke, herhaalde meting minstens 1,2× sneller?

Het eindoordeel is een van vier uitkomsten: `REJECTED_STATIC`, `REJECTED_NOT_EQUIVALENT`, `EQUIVALENT_NOT_FASTER` of `ACCEPTED`.

### Wat erin zit

| Onderdeel | Wat het is |
|---|---|
| **Validator** (`validator/`) | De drie controles hierboven, als losse, herbruikbare functies |
| **Testbank** (`cases/`) | Vier trage query's met parametersets en handgemaakte herschrijvingen met een bekend oordeel |
| **Mutatietest** (`scripts/run_validation.py`) | Laat de validator los op herschrijvingen waarvan het oordeel bekend is, om te meten of de validator zelf klopt |
| **LLM-koppeling** (`llm/`, `scripts/run_llm.py`) | Bouwt een prompt met een instelbare hoeveelheid context, roept een model aan en laat elk antwoord door de validator beoordelen |
| **A/A-controle** (`run_llm.py --model mock`) | Vergelijkt het origineel met zichzelf, om de meetruis en onterechte `ACCEPTED`-oordelen te meten |
| **Experimenten** (`scripts/run_experiment.py`, `scripts/analyse_models.py`, `scripts/grafieken.py`) | Laat een of meer modellen dezelfde query's herschrijven bij verschillende outputlimieten, efforts, condities en aantallen herhalingen, via OpenRouter of Anthropic, en rekent prestatie en kosten uit. Hiermee onderzoek je ook welke context (C1 t/m C4) het verschil maakt (zie [hoofdstuk 8](#8-modelvergelijking-meerdere-modellen-en-instellingen)) |
| **Leesbare resultaten** (`llm/uitvoer.py`) | Zet elke run om in een `resultaten.csv` met Nederlandse kolommen, voor Excel (zie stap B5) |
| **Demo-UI** (`ui/`) | Streamlit-app die voor één query het hele proces op het scherm toont (zie [hoofdstuk 6](#6-de-demo-ui-streamlit)) |
| **Analyse** (`scripts/analyse.py`) | Zet de ruwe resultaten om in tabellen, betrouwbaarheidsintervallen, voorbeelden en figuren |
| **Database-hulp** (`scripts/start_db.py`, `stop_db.py`) | Start en stopt een ingebedde PostgreSQL 16, zodat er niets apart hoeft te worden geïnstalleerd |

### Waarvoor je het kunt gebruiken

- Een **herschrijving van een query controleren** voordat je hem toepast.
- Meten **hoe betrouwbaar een validator is**, voordat je erop vertrouwt.
- **Prompts of modellen vergelijken** door ze op dezelfde query's los te laten.
- Onderzoeken **welke contextinformatie** (query, schema, uitvoeringsplan, statistieken) het verschil maakt voor een herschrijving.
- Het hele proces **laten zien in de demo-UI**, voor een presentatie of om te begrijpen wat er gebeurt.
- Een **eigen query toevoegen** (zie [hoofdstuk 7](#7-een-eigen-query-toevoegen)).

### Scope

Alleen het herschrijven van `SELECT`-query's. Geen indexen, geen schemawijzigingen, geen applicatiecode. De validator werkt op PostgreSQL (sqlglot-dialect `postgres`).

De testdatabase is de webshop "Bazaar" van SUE (FastAPI, PostgreSQL 16, bewust traag). Die code zit niet in deze repository; [hoofdstuk 5](#5-installeren-en-draaien-stap-voor-stap) legt uit hoe je hem ophaalt.

### Snel aan de slag

- **Eerste keer op een computer:** hoofdstuk 5, deel A (stap A1 t/m A8).
- **Elke keer dat je werkt:** hoofdstuk 5, deel B (stap B1 t/m B7), met in het kort de commando's om te starten en te stoppen.
- **De demo-UI:** [hoofdstuk 6](#6-de-demo-ui-streamlit).

---

## Inhoud

1. [Hoe het werkt](#1-hoe-het-werkt)
2. [De vier condities voor het model](#2-de-vier-condities-voor-het-model)
3. [Mapstructuur en bestanden](#3-mapstructuur-en-bestanden)
4. [Wat je nodig hebt](#4-wat-je-nodig-hebt)
5. [Installeren en draaien, stap voor stap](#5-installeren-en-draaien-stap-voor-stap): deel A (eenmalig) en deel B (elke keer)
6. [De demo-UI (Streamlit)](#6-de-demo-ui-streamlit)
7. [Een eigen query toevoegen](#7-een-eigen-query-toevoegen)
8. [Modelvergelijking en experimenten](#8-modelvergelijking-meerdere-modellen-en-instellingen)
9. [Problemen oplossen](#9-problemen-oplossen)
10. [Technische beperkingen](#10-technische-beperkingen)
11. [Bronnen](#11-bronnen)

---

## 1. Hoe het werkt

```
 originele query ──► (LLM of handgemaakte kandidaat) ──► herschreven SQL ──► VALIDATIE ──► oordeel
                                                                              │
          1. statische controle (sqlglot)  ── niet geldig ──────────────► REJECTED_STATIC
          2. zelfde resultaat op alle parametersets ── verschil ───────► REJECTED_NOT_EQUIVALENT
          3. tijd: ABAB, mediaan ── speedup < 1,2 ─────────────────────► EQUIVALENT_NOT_FASTER
                                  ── speedup ≥ 1,2 ────────────────────► ACCEPTED
```

**Statische controle** (`validator/checker.py`, `static_check`). De SQL wordt geparsed met sqlglot (PostgreSQL-dialect). Het moet precies één `SELECT` zijn. DDL en DML worden afgekeurd, ook binnen een CTE.

**Resultaatvergelijking** (`checker.py`, `run_query` en `compare`). Elke query draait in een read-only transactie met een `statement_timeout`, die altijd wordt teruggedraaid. De rijen worden vergeleken als multiset van genormaliseerde waarden (`validator/normalize.py`: int, `Decimal` en float zijn gelijk bij dezelfde waarde). Heeft het origineel een `ORDER BY`, dan wordt ook de volgorde van de sorteersleutel vergeleken. Een verschil dat alleen rijen met dezelfde sorteersleutel aan de `LIMIT`-grens betreft, geeft `TIE_AMBIGUOUS` en telt niet als fout, omdat beide uitkomsten dan geldig zijn.

**Parametersets** (`cases/cases.py`, `make_ctx`). De parameters komen uit de database zelf: een grote en een kleine tenant (de tenants met de meeste en de minste orders), elk met vier tijdvensters:

| Venster | Doel |
|---|---|
| `full` | alle data |
| `recent` | de laatste 90 dagen |
| `empty` | een venster zonder data (vangt fouten bij lege uitkomsten) |
| `boundary` | bovengrens precies op de laatste order (laat `<` en `<=` verschillen) |

Een gelijk resultaat op één parameterset bewijst weinig; daarom worden alle combinaties gecontroleerd. Voor trage query's kan een deelverzameling worden gebruikt (zie `tc_params` in `cases.py`).

**Tijdmeting** (`validator/timing.py`, `measure`). Origineel en herschrijving worden om en om gemeten (ABAB), zodat een tijdelijk trage periode van de computer beide even hard raakt. Standaard zijn dat 2 warm-ups en 7 meetherhalingen; de **mediaan** telt, omdat één uitschieter de mediaan niet verandert. De speedup is de mediaan van het origineel gedeeld door die van de herschrijving, en pas vanaf `SPEEDUP_THRESHOLD = 1.2` is het oordeel `ACCEPTED`. Duurt het origineel langer dan 5 seconden, dan worden hooguit 3 herhalingen zonder warm-up gedaan.

**Mutatietest.** `cases/cases.py` bevat per query handgemaakte herschrijvingen met een verwacht oordeel (`expected`): foute (mutanten, gemaakt door kleine wijzigingen aan de SQL) en gelijkwaardige. De validator moet alle foute afkeuren en geen gelijkwaardige. Het verwachte oordeel is de redenering van degene die de herschrijving maakte en is niet onafhankelijk bewezen.

**A/A-controle.** `run_llm.py --model mock` geeft het origineel terug als "antwoord". De echte speedup is dan 1,0, dus elke `ACCEPTED` is meetruis.

---

## 2. De vier condities voor het model

`run_llm.py` kan het model vier hoeveelheden context geven. Elke conditie bevat de vorige:

| Conditie | Wat het model krijgt |
|---|---|
| `C1_query` | alleen de originele query |
| `C2_schema` | + kolommen, constraints en indexen van de gebruikte tabellen |
| `C3_plan` | + `EXPLAIN (ANALYZE, BUFFERS)` van het origineel |
| `C4_stats` | + geschatte rijen per tabel en `pg_stats` van de gebruikte kolommen |

De context wordt gebouwd in `llm/context.py` (`build_context`). De tabellen en kolommen worden met sqlglot uit de originele query gehaald, dus er is geen handmatige lijst nodig. Kies met `--conditions` welke condities draaien.

---

## 3. Mapstructuur en bestanden

```
.
├── README.md
├── requirements.txt
├── scripts/                      # de uitvoerbare programma's
│   ├── start_db.py               # start de ingebedde PostgreSQL, print de URI
│   ├── stop_db.py                # stopt de database
│   ├── run_validation.py         # mutatietest; bevat ook evaluate(), dat run_llm.py hergebruikt
│   ├── run_llm.py                # LLM laten herschrijven en elk antwoord beoordelen (Anthropic of OpenRouter)
│   ├── run_experiment.py         # modelvergelijking: draait run_llm.py voor elk model en elke outputlimiet
│   ├── analyse.py                # leest results/llm-*, maakt tabellen en figuren voor een enkele modelrun
│   ├── analyse_models.py         # leest results/experiment-*, vergelijkt modellen, limieten, condities en herhalingen
│   └── grafieken.py              # maakt presentatiegrafieken (SVG + overzicht.html) in results/grafieken/
├── ui/                           # Streamlit-demo van het hele proces
│   ├── app.py                    # de UI (streamlit run ui/app.py)
│   └── pipeline.py               # de stappen als losse functies; roept validator/ en llm/ aan
├── cases/                        # wat er wordt getest
│   ├── cases.py                  # de 4 Case-objecten, parametersets en alle handgemaakte herschrijvingen
│   ├── classes/
│   │   ├── candidate.py          # dataclass Candidate: naam, sql, verwacht oordeel, fouttype
│   │   └── case.py               # dataclass Case: origineel, ORDER BY-kolommen, parametersets, kandidaten
│   └── original/                 # de 4 originele SUE-query's (.sql)
├── validator/                    # het framework
│   ├── checker.py                # static_check, run_query, compare
│   ├── normalize.py              # norm_value, norm_row
│   ├── timing.py                 # measure; SPEEDUP_THRESHOLD = 1.2
│   └── classes/
│       ├── comparison.py         # dataclass Comparison (status + detail)
│       └── result.py             # dataclass Result (kolommen, rijen, ms)
├── llm/                          # de LLM-koppeling
│   ├── context.py                # bouwt de context per conditie (schema, plan, statistieken)
│   ├── client.py                 # systeemprompt, prompt bouwen, API-aanroep (anthropic en openrouter), SQL uitpakken
│   ├── prices.py                 # prijzen per model (dollar per miljoen tokens), kosten uit tokens
│   └── uitvoer.py                # maakt het leesbare resultaten.csv uit de technische bestanden van een run
└── results/                      # uitvoer van de runs (zie hieronder)
```

Er zijn bewust geen `__init__.py`-bestanden (Python-namespacepakketten). De scripts voegen de repo-map toe aan het zoekpad en alle imports beginnen bij die map, bijvoorbeeld `from validator.checker import compare`. **Draai de scripts daarom altijd vanuit de hoofdmap van de repository** (`python scripts/...`) en markeer geen submappen als *Sources Root* in een IDE.

### De belangrijkste functies

| Functie | Bestand | Wat het doet |
|---|---|---|
| `static_check(sql)` | `validator/checker.py` | Parsed de SQL en keurt alles af wat geen enkele `SELECT` is |
| `run_query(conn, sql, params, timeout_ms)` | `validator/checker.py` | Voert uit in een read-only transactie en rolt altijd terug |
| `compare(orig, cand, order_cols)` | `validator/checker.py` | Vergelijkt twee resultaten; geeft een `Comparison` |
| `measure(conn, orig_sql, cand_sql, params, reps=7, warmup=2)` | `validator/timing.py` | ABAB-meting; geeft mediaan en speedup |
| `evaluate(conn, case, cand, ctx, reps)` | `scripts/run_validation.py` | Volledige keten voor één kandidaat; geeft het eindoordeel |
| `make_ctx(conn)` | `cases/cases.py` | Zoekt grote en kleine tenant en bouwt de tijdvensters |
| `build_context(conn, case, ctx, condition)` | `llm/context.py` | Bouwt de contextblokken voor een conditie |
| `build_prompt(blocks)` | `llm/client.py` | Zet de blokken om in de prompt |
| `call_llm(prompt, model, max_tokens=4000, original_sql="", provider="anthropic", effort=None)` | `llm/client.py` | Roept de API aan (OpenRouter of Anthropic, of het nepmodel) |
| `extract_sql(text)` | `llm/client.py` | Haalt de SQL uit het antwoord van het model |
| `schrijf_resultaten_csv(run_map)` | `llm/uitvoer.py` | Maakt het leesbare `resultaten.csv` van een run |
| `voeg_samen(experiment_map)` | `llm/uitvoer.py` | Voegt de `resultaten.csv` van alle runs van een experiment samen |

### Volgorde van aanroepen in `run_llm.py`

Per query, conditie en herhaling:

1. `make_ctx(conn)`: grote en kleine tenant en tijdvensters.
2. `build_context(...)`, dan `build_prompt(...)`.
3. `call_llm(...)`, dan `extract_sql(...)`.
4. `evaluate(...)`, dat `static_check`, `run_query`, `compare` en `measure` aanroept.
5. Het resultaat wordt opgeslagen in `results/llm-<tijdstempel>/`.
6. `schrijf_resultaten_csv(...)` maakt het leesbare `resultaten.csv`.

### Wat in `results/` komt

Alle scripts schrijven hun uitvoer naar `results/`, in een nieuwe map met tijdstempel. **Bestaande mappen worden nooit overschreven.**

| Map of bestand | Gemaakt door | Inhoud |
|---|---|---|
| `validation-<tijdstempel>.csv/.json` | `run_validation.py` | Oordeel per handgemaakte kandidaat |
| `llm-<tijdstempel>/prompts/` | `run_llm.py` | Precies wat het model kreeg, per query en conditie (`_system.txt` bevat de regels) |
| `llm-<tijdstempel>/responses/` | `run_llm.py` | Ruw antwoord, uitgepakte SQL en tokengebruik |
| `llm-<tijdstempel>/llm-results.csv/.json` | `run_llm.py` | Oordeel per antwoord |
| `llm-<tijdstempel>/resultaten.csv` | `run_llm.py` | **Het bestand om te lezen**: een regel per antwoord met Nederlandse kolommen (zie stap B5) |
| `llm-<tijdstempel>/meta.json` | `run_llm.py` | De instellingen van de run: model, aanbieder, effort, outputlimiet, herhalingen |
| `analyse/` | `analyse.py` | Tabellen (`analyse.txt`, `per_*.csv`), `voorbeelden.md` en figuren |
| `experiment-<naam>/<model>_<limiet>/` | `run_experiment.py` | Een run van `run_llm.py` per model en outputlimiet, met dezelfde mapindeling als `llm-<tijdstempel>/` |
| `experiment-<naam>/resultaten.csv` | `run_experiment.py` | De `resultaten.csv` van alle runs van het experiment onder elkaar, met een extra kolom `run` |
| `experiment-<naam>/analyse/` | `analyse_models.py` | `samenvatting.md`, `per_groep.csv`, `passk.csv`, `per_query.csv`, `per_poging.csv` |

---

## 4. Wat je nodig hebt

- Python **3.12** (via conda). Andere versies kunnen mislukken: `pgserver` levert op Windows alleen wielen voor Python 3.9 t/m 3.12.
- Git.
- Internet voor `pip install` en het klonen van de SUE-repo.
- Een **API-sleutel**, alleen voor de echte LLM-runs: standaard een OpenRouter-sleutel (`sk-or-v1-...`), eventueel een directe Anthropic-sleutel (`sk-ant-...`), zie stap B2 en hoofdstuk 8.
- Enkele GB vrije schijfruimte voor de database en de runs.
- Voor de demo-UI een webbrowser (Streamlit opent hem zelf).

Voor de mutatietest, het bekijken van prompts, de A/A-controle, de demo-UI met opgeslagen antwoorden en de analyse is na de installatie **geen API-sleutel** nodig. De analyse heeft zelfs geen database nodig.

---

## 5. Installeren en draaien, stap voor stap

De stappen zijn geschreven voor **Windows met PowerShell** (bijvoorbeeld de terminal in PyCharm) en conda. Waar Linux of macOS verschilt, staat het erbij. Ze zijn in twee delen verdeeld:

| Deel | Wanneer | Stappen |
|---|---|---|
| **A. Eenmalig** | alleen de eerste keer op een computer | A1 t/m A8: installeren, database en data aanmaken, controleren dat alles werkt |
| **B. Elke keer** | elke keer dat je werkt | B1 t/m B7: omgeving en database starten, sleutel zetten, draaien, resultaten lezen, alles stoppen |

Heb je deel A al gedaan, dan begin je elke werksessie bij **B1**. De data blijft bewaard in de datamap; je hoeft de database niet opnieuw te maken.

**Deel B in het kort** (de uitleg staat bij de stappen):

```powershell
conda activate sqlvalidator
cd initial_poc_sue
python scripts/start_db.py C:\pgdata\bazaar            # print de URI; de poort is elke keer anders
$URI = "postgresql://..."                              # plak de geprinte URI
$s = Read-Host "OpenRouter-sleutel" -AsSecureString    # alleen voor echte modelaanroepen
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new("", $s).Password
streamlit run ui/app.py                                # de demo-UI, of: python scripts/run_experiment.py $URI ...
python scripts/stop_db.py C:\pgdata\bazaar             # aan het eind, altijd
```

### Deel A. Eenmalig: de eerste keer instellen

#### Stap A1. Deze repository klonen


```powershell
git clone https://github.com/Khaled-Alkahlout/initial_poc_sue.git
cd initial_poc_sue
```

Pas de URL aan als de repository een andere naam of eigenaar heeft. Deze map heet hieronder de **repo-map**.

#### Stap A2. Conda-omgeving maken


```powershell
conda create -n sqlvalidator python=3.12 -y
conda activate sqlvalidator
python --version      # moet Python 3.12.x tonen
```

#### Stap A3. Pakketten installeren


```powershell
pip install -r requirements.txt
pip install matplotlib        # optioneel: alleen nodig voor de figuren van analyse.py
```

`requirements.txt` bevat `pgserver`, `psycopg[binary]`, `sqlglot`, `anthropic`, en voor de analyse en de demo-UI `streamlit`, `pandas` en `matplotlib`.

#### Stap A4. De SUE-repo ophalen en een werkkopie maken


Het schema en de testdata komen uit de repo van SUE. Gebruik een **kopie**, want er wordt één regel aangepast. Zet de SUE-map naast de repo-map:

```powershell
cd ..
git clone https://github.com/robinverstraelen/sql-performance-challenge.git
cd sql-performance-challenge
git checkout 6951dfc          # de versie waarmee deze testbank is gebouwd
cd ..
Copy-Item -Recurse sql-performance-challenge sql-performance-challenge-lab
```

Open in de kopie `sql-performance-challenge-lab\migrations\versions\0001_tenancy.py` en verwijder of becommentarieer de regel:

```python
op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
```

`pgserver` bevat de extensie `pgcrypto` niet. De functie `gen_random_uuid()` zit in PostgreSQL zelf, dus de rest werkt.

Installeer de pakketten die de SUE-code nodig heeft (in dezelfde omgeving):

```powershell
pip install "sqlalchemy>=2.0.30" "alembic>=1.13" "pydantic>=2.7" "pydantic-settings>=2.3" "structlog>=24.1" "faker>=25.0" "rich>=13.7" "typer>=0.12" "fastapi>=0.115"
```

#### Stap A5. De database aanmaken en voor het eerst starten


Vanuit de **repo-map**:

```powershell
python scripts/start_db.py C:\pgdata\bazaar
```

Het script maakt de map aan en start een ingebedde PostgreSQL 16.2. Het **print één regel: de URI** van de database. Kopieer die volledig. De poort verandert bij elke start. De server blijft draaien nadat het script klaar is.

Zet de URI in een variabele, zodat je hem niet steeds hoeft te plakken (dit doe je bij elke start opnieuw, zie stap B1):

```powershell
$URI = "postgresql://...      # plak hier de geprinte URI"
```

Linux of macOS: `URI="postgresql://..."` en gebruik bijvoorbeeld `/tmp/pgdata/bazaar` als datamap.

#### Stap A6. Het schema aanmaken (migraties)


Ga naar de **SUE-werkkopie** en zet dezelfde URI met het voorvoegsel `postgresql+psycopg://` in plaats van `postgresql://`:

```powershell
cd ..\sql-performance-challenge-lab
$env:BAZAAR_DATABASE_URL = $URI -replace '^postgresql://', 'postgresql+psycopg://'
python -m alembic upgrade head
```

Verwacht: **25 regels "Running upgrade"** en geen foutmelding.

#### Stap A7. De data genereren


Nog steeds in de SUE-werkkopie:

```powershell
python -m seed.generate --scale 0.02 --seed 42 --database-url $URI --manifest manifest.json
```

- `--scale 0.02` betekent 2% van het aantal rijen van de volledige dataset (ongeveer 60.000 orders en 10.000 klanten). De generator verzint alle data.
- `--seed 42` bepaalt de willekeurige keuzes.
- Verwacht: een voortgangsbalk en aan het eind een regel `done in ...s (scale 0.02, seed 42, anchor ...)`.

> **Let op voor exact herhalen.** Dezelfde seed en schaal geven alleen identieke data als ook de **anchor** gelijk is: het "nu" waaraan alle tijdstempels hangen. Standaard is dat het huidige uur. Wie de data in een ander uur genereert, krijgt dezelfde vorm met andere tijdstempels. Geef bij een exacte herhaling `--anchor <ISO-tijdstip>` mee, bijvoorbeeld `--anchor 2026-10-26T12:00:00`.

**Controle** (terug in de repo-map, de database moet nog draaien):

```powershell
cd ..\initial_poc_sue
python -c "import psycopg,sys; c=psycopg.connect(sys.argv[1]); print(c.execute('select count(*) from orders').fetchone())" $URI
```

Verwacht: een aantal rond 60.000.

#### Stap A8. Controleren dat alles werkt

Drie controles, in deze volgorde. Geen van de drie vraagt om een API-sleutel; ze kosten niets.

**a. De mutatietest.**


Vanuit de repo-map:

```powershell
python scripts/run_validation.py $URI --reps 5
```

Dit duurt enkele minuten. Onderaan staat de samenvatting, met drie regels waar je op let:

```
Fout (niet-gelijkwaardig) gedetecteerd: 16/17
Foute afkeuringen van gelijkwaardige kandidaten: 0/5
Gemist: ['M3_geen_id_tiebreak']
```

Dit is ook een **installatiecontrole**: komen jouw getallen hiermee overeen, dan werken database, data en validator zoals bedoeld. Een iets ander getal is geen fout van jou, maar controleer dan eerst stap A7 (data en anchor). De uitvoer staat in `results/validation-<tijdstempel>.csv` en `.json`.

**b. De prompts bekijken zonder LLM (gratis).**


```powershell
python scripts/run_llm.py $URI --dry-run
```

Er wordt geen API aangeroepen. Het script bouwt de context uit de database, print per query en conditie de lengte van de prompt en schrijft de prompts naar `results/llm-<tijdstempel>/prompts/`.

**c. De A/A-controle draaien.**


```powershell
python scripts/run_llm.py $URI --model mock --reps 3
```

Het nepmodel geeft de originele query terug, de rest van de keten is echt. Dit geeft 4 × 4 × 3 = 48 metingen. Elke `ACCEPTED` hier is meetruis. Verwacht: geen of nauwelijks `ACCEPTED`, en een speedup rond 1,0.

#### Klaar met deel A

Stop de database (stap B7). Vanaf nu begin je elke keer bij deel B.

---

### Deel B. Elke keer: starten, draaien en stoppen

#### Stap B1. De terminal klaarzetten en de database starten

Open een nieuw PowerShell-venster, ga naar de **repo-map** en start de database:

```powershell
conda activate sqlvalidator
cd initial_poc_sue
Get-Process postgres -ErrorAction SilentlyContinue | Measure-Object     # Count hoort 0 te zijn: er draait nog geen database
python scripts/start_db.py C:\pgdata\bazaar
```

Het script **print één regel: de URI** van de database. Kopieer die volledig: de poort verandert bij elke start. De server blijft draaien nadat het script klaar is. Zet de URI in een variabele, zodat je hem niet steeds hoeft te plakken:

```powershell
$URI = "postgresql://...      # plak hier de geprinte URI"
```

Linux of macOS: `URI="postgresql://..."` en bijvoorbeeld `/tmp/pgdata/bazaar` als datamap.

Controleer dat de database antwoordt en de data er nog is:

```powershell
python -c "import psycopg,sys; c=psycopg.connect(sys.argv[1], connect_timeout=5); print(c.execute('select count(*) from orders').fetchone())" $URI
```

Verwacht `(60000,)` bij schaal 0,02. Geeft dit een time-out, dan draait de server nog niet of herstelt hij nog na een onjuiste afsluiting; zie [hoofdstuk 9](#9-problemen-oplossen). De start duurt na een schone afsluiting enkele seconden en na een onjuiste afsluiting ruim een halve minuut.

#### Stap B2. De API-sleutel instellen (alleen voor echte modelaanroepen)

De standaard is **OpenRouter**: de Claude-modellen worden aangeroepen via de OpenRouter-sleutel (begint met `sk-or-v1-`). Zet hem **alleen in de terminal**, nooit in een bestand dat in git komt (dus ook niet in een `.env`) en nooit in een chat. Deze variant toont de sleutel niet op het scherm en laat hem niet achter in je opdrachtgeschiedenis:

```powershell
$s = Read-Host "OpenRouter-sleutel" -AsSecureString
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new("", $s).Password
```

Linux: `export OPENROUTER_API_KEY="sk-or-v1-..."`. De sleutel geldt alleen voor het huidige terminalvenster. **Start de UI en de experimenten vanuit dit venster.** Zonder sleutel stopt `run_llm.py` met de melding dat `OPENROUTER_API_KEY` ontbreekt.

**Tegoed en limiet bekijken** (gratis, er wordt geen model aangeroepen; de uitvoer bevat de sleutel zelf niet):

```powershell
(curl.exe -s https://openrouter.ai/api/v1/key -H "Authorization: Bearer $env:OPENROUTER_API_KEY" | ConvertFrom-Json).data | Select-Object limit, limit_remaining, usage, usage_daily, is_free_tier
```

`limit_remaining` is het resterende tegoed van **deze sleutel**. Is het leeg (`null`), dan heeft de sleutel geen eigen limiet en zie je het saldo alleen op het platform van de eigenaar. Wordt de sleutel door een groep gedeeld, dan tellen `usage` en `usage_daily` het gebruik van iedereen; je eigen kosten staan in de kolom `kosten_usd` van `resultaten.csv`. Stem grote runs af met de andere gebruikers.

**Sleutel en model testen** (een paar duizendsten van een cent per model):

```powershell
python scripts/run_experiment.py --check --models sonnet
```

Je wilt `OK` zien. Zonder `--models` test het script alle vier de modellen.

Heb je in plaats daarvan een directe Anthropic-sleutel (`sk-ant-...`, via console.anthropic.com)? Zet die dan in `ANTHROPIC_API_KEY` en gebruik `--provider anthropic` met een directe modelnaam zoals `claude-sonnet-5-5`. Een Anthropic-sleutel hoort **niet** in `OPENROUTER_API_KEY` (hij zou dan naar OpenRouter worden gestuurd), en andersom werkt een OpenRouter-sleutel niet als `ANTHROPIC_API_KEY`. Bij een Anthropic-sleutel is er geen `/key`-opvraag; het saldo staat in de Anthropic Console van de eigenaar.

#### Stap B3. De demo-UI starten (optioneel)

Wil je het hele proces voor één query op het scherm laten zien, start dan de Streamlit-app:

```powershell
$env:SUE_DEMO_DB_URI = $URI
streamlit run ui/app.py
```

De app opent op `http://localhost:8501`. Wat de UI wel en niet doet, staat in [hoofdstuk 6](#6-de-demo-ui-streamlit). Stoppen doe je met `Ctrl+C`.

#### Stap B4. Een run of een experiment draaien

Er zijn twee manieren, en allebei schrijven ze hun uitvoer naar `results/` en maken ze aan het eind een leesbaar `resultaten.csv`:

- **`run_llm.py`** draait **één model met één limiet** (hieronder).
- **`run_experiment.py`** draait een **raster van modellen en limieten** en voegt een plan met kostenschatting, hervatten, een veiligheidsstop bij te veel API-fouten en een gecombineerd `resultaten.csv` toe (hoofdstuk 8). Voor het onderzoek naar de contextcondities staat daar een kant-en-klaar voorbeeld.

De UI (hoofdstuk 6) draait geen experimenten en slaat niets op.


Eerst een kleine proef om te zien dat alles werkt en wat het kost:

```powershell
python scripts/run_llm.py $URI --cases revenue_orders --conditions C1_query C3_plan --reps 1
```

Daarna een volledige run, bijvoorbeeld per query:

```powershell
python scripts/run_llm.py $URI --cases revenue_orders --reps 3
python scripts/run_llm.py $URI --cases top_products   --reps 3
python scripts/run_llm.py $URI --cases audit_log_page --reps 3
python scripts/run_llm.py $URI --cases top_customers  --reps 3
```

Alles in één keer kan ook: laat `--cases` weg. Een LLM is niet deterministisch, dus een tweede run met dezelfde instellingen geeft niet exact dezelfde antwoorden.

**Opties van `run_llm.py`:**

| Optie | Standaard | Betekenis |
|---|---|---|
| `uri` | verplicht | de database-URI |
| `--model` | `anthropic/claude-sonnet-5.5` | modelnaam van de aanbieder (bij `--provider anthropic` bijvoorbeeld `claude-sonnet-5-5`), of `mock` |
| `--provider` | `openrouter` | `openrouter` (sleutel in `OPENROUTER_API_KEY`) of `anthropic` (direct, sleutel in `ANTHROPIC_API_KEY`) |
| `--effort` | niet gezet | `low`, `medium`, `high`, `xhigh` of `max`; zonder waarde geldt de standaard van het model, en die verschilt per model |
| `--max-tokens` | 4000 | harde limiet op uitvoertokens, inclusief denktokens. Bij `--effort max` is 16000 of meer nodig; zie hoofdstuk 9 |
| `--reps` | 3 | LLM-aanroepen per query per conditie |
| `--val-reps` | 7 | tijdmetingen per gelijkwaardige herschrijving |
| `--cases` | alle vier | lijst van query's |
| `--conditions` | alle vier | lijst van condities |
| `--out` | `results/llm-<tijdstempel>` | uitvoermap; mag nog niet bestaan |
| `--label` | leeg | vrije tekst, bewaard in `meta.json` |
| `--dry-run` | uit | alleen prompts opslaan |

Naast de oordelen van de validator kent `run_llm.py` twee eigen uitkomsten: `TRUNCATED` (de tokenlimiet was bereikt voor er een volledig SQL-blok stond; niet gevalideerd) en `API_ERROR` (de aanroep mislukte na herhaalde pogingen; niet gevalideerd). Een run stopt niet bij een API-fout, maar noteert hem en gaat door.

De kosten zijn te schatten uit de proefrun: het tokengebruik staat per antwoord in `responses/`.

#### Stap B5. De resultaten lezen


Aan het eind van elke run schrijft `run_llm.py` (en na een experiment ook `run_experiment.py`) een bestand `resultaten.csv`. Het opent direct in Excel: scheidingsteken `;`, decimale komma, UTF-8. Met pandas lees je het met `pd.read_csv(pad, sep=";", decimal=",", encoding="utf-8-sig")`. De JSON-bestanden in dezelfde map zijn technisch (de analysescripts en de Streamlit-demo lezen ze); je hoeft ze niet te openen.

| Kolom | Betekenis |
|---|---|
| `query`, `context`, `herhaling` | welke query, welke contextvorm (C1 query, C2 schema, C3 plan, C4 statistieken) en de hoeveelste poging |
| `model`, `aanbieder`, `effort`, `max_uitvoertokens` | welk model en met welke instellingen; `standaard` bij effort betekent: niets meegegeven, dus de standaard van het model |
| `duur_origineel_ms`, `duur_kandidaat_ms`, `versnelling_x` | mediaan van de metingen (afwisselend origineel en kandidaat, `aantal_metingen` stuks) en origineel gedeeld door kandidaat. Leeg als de kandidaat niet is gemeten |
| `oordeel` | GOED (zelfde resultaat en minstens 1,2x sneller), ZELFDE RESULTAAT NIET SNELLER, AFGEKEURD: ANDER RESULTAAT, AFGEKEURD: GEEN GELDIGE SELECT, AFGEKAPT DOOR DE TOKENLIMIET of API-FOUT |
| `aantal_parametersets`, `parametersets_met_verschil`, `reden_afkeuring` | op hoeveel verschillende invoerwaarden de query is uitgevoerd, op hoeveel daarvan het resultaat afweek van het origineel (0 = overal gelijk) en welke set hoe afweek |
| `invoertokens`, `uitvoertokens`, `stopreden`, `modeltijd_s`, `kosten_usd` | wat het model verbruikte; `modeltijd_s` is de tijd van het model, niet van de query; `kosten_usd` komt van de aanbieder of anders uit de prijstabel |
| `query_ongewijzigd` | het model gaf het origineel terug |
| `spreiding_origineel_ms`, `spreiding_kandidaat_ms` | interkwartielafstand van de metingen; alleen om te beoordelen of een versnelling meer is dan ruis |
| `sql_kandidaat` | de herschreven query |

#### Stap B6. De analyse draaien


```powershell
python scripts/analyse.py
```

Dit heeft **geen database en geen API-sleutel** nodig, het leest alleen `results/`. Het kiest automatisch de volledige runs (echt model, alle vier de condities) en gebruikt de mock-mappen voor de ruisband (de nepmodelrun van stap A8c; zonder zo'n map krijg je geen ruisband). Met `--map <mappen>` kies je zelf mappen. De uitvoer staat in `results/analyse/`:

- `analyse.txt`: het volledige verslag met tabellen
- `per_poging.csv`, `per_conditie.csv`, `per_casus_conditie.csv`: de data in tabelvorm
- `voorbeelden.md`: goede en foute voorbeelden met SQL
- `uitkomsten.png`, `speedup.png`: figuren (alleen met matplotlib)

`analyse.py` beantwoordt de vraag *welke contextconditie wat oplevert* voor een run van één model. Een experiment met meerdere modellen, limieten of efforts analyseer je met `python scripts/analyse_models.py --name <naam>` (hoofdstuk 8). Het eerste leest `results/llm-*`; ligt een run in een experimentmap, geef dan het pad mee met `--map`.

#### Stap B7. Alles stoppen

1. Stop de UI of een lopend experiment met `Ctrl+C`. Een afgebroken experiment hervat je door hetzelfde commando opnieuw te starten (zie hoofdstuk 8).
2. Stop de database, **altijd** voordat je de computer uitzet. Gebruik dezelfde datamap als bij de start:

   ```powershell
   python scripts/stop_db.py C:\pgdata\bazaar
   ```

3. Controleer dat alles schoon is afgesloten:

   ```powershell
   Get-Process postgres -ErrorAction SilentlyContinue | Measure-Object     # Count : 0
   Test-Path C:\pgdata\bazaar\postmaster.pid                               # False
   ```

4. Haal de sleutel uit de sessie (hij verdwijnt ook als je het venster sluit):

   ```powershell
   Remove-Item Env:OPENROUTER_API_KEY
   ```

Zet je de computer uit zonder te stoppen, dan blijft er een verouderd `postmaster.pid` achter en moet de database bij de volgende start herstellen. Op Windows kan Windows het procesnummer in dat bestand dan aan een ander programma geven; zie [hoofdstuk 9](#9-problemen-oplossen) voordat je dan `stop_db.py` uitvoert.

De data blijft bewaard in de datamap. De volgende keer begin je weer bij stap B1.

---

## 6. De demo-UI (Streamlit)

`ui/app.py` is een Streamlit-app die voor **één query** het hele proces op het scherm toont. Je ziet in zeven stappen wat er gebeurt:

1. de originele query en de parametersets waarop hij wordt gecontroleerd;
2. de context die het model krijgt (per conditie) en de volledige prompt;
3. het antwoord van het model: tokens, duur, kosten, stopreden en het verschil met het origineel;
4. de statische controle;
5. de gelijkwaardigheidscontrole per parameterset (aantal rijen van origineel en kandidaat);
6. de tijdmeting (medianen, versnelling, staafdiagram);
7. het eindoordeel, met een downloadknop (JSON) voor het resultaat van deze ene run.

### Wat de UI wel en niet doet

- De UI **roept `run_llm.py` en `run_experiment.py` niet aan**. Ze importeert dezelfde onderdelen (`llm/` voor de context en de modelaanroep, `validator/` voor de controle en de tijdmeting, en de oordeelregels van `evaluate()`) en laat die stappen één voor één zien. Ze heeft geen eigen beoordelingslogica, dus ze geeft dezelfde oordelen als de scripts.
- De UI **slaat niets op in `results/`**, behalve via de downloadknop. Dat is bewust: de demo moet snel en overzichtelijk blijven en een live-aanroep kost geld per klik.
- **Experimenten draai je in de terminal** (stap B4 en hoofdstuk 8). De UI toont de uitkomst daarna in het tabblad "Resultaten en modelvergelijking".

### Starten

Doe eerst stap B1 (database) en, voor live modelaanroepen, stap B2 (sleutel), allebei in hetzelfde venster. Dan:

```powershell
$env:SUE_DEMO_DB_URI = $URI          # vult de URI in de zijbalk alvast in
streamlit run ui/app.py
```

De app opent op `http://localhost:8501`. Vraagt Streamlit bij de allereerste start om een e-mailadres, druk dan op Enter. Stoppen doe je met `Ctrl+C`. Gebruik je de database niet apart, dan kun je ook de knop "Ingebedde database starten" in de zijbalk gebruiken.

In de zijbalk staat of de sleutel aanwezig is (alleen de aanwezigheid, nooit de sleutel zelf). Ontbreekt hij, dan is de knop voor een live-aanroep uitgeschakeld.

### Bron van de herschrijving

| Bron | Gebruik |
|---|---|
| LLM (live) | echte aanroep via OpenRouter (of direct Anthropic); kies conditie, model, denkinspanning (effort) en tokenlimiet. Kost geld |
| Opgeslagen LLM-antwoord | een antwoord uit `results/`; de controle en tijdmeting draaien wel opnieuw. Veilig voor een demo zonder netwerk of sleutel |
| Handmatige kandidaat | een herschrijving uit de mutatietest, met de verwachting van de maker erbij |
| Eigen SQL plakken | vrije SQL, bijvoorbeeld een fout die je live wilt laten afvangen |
| Nepmodel | geeft het origineel terug (A/A-controle) |

### Tabbladen

| Tabblad | Wat het doet |
|---|---|
| **Proces** | de zeven stappen hierboven voor één query |
| **Resultaten en modelvergelijking** | leest alle runs in `results/` (`llm-results.json` en `meta.json`) en toont per conditie, query en model de uitkomsten en kosten. Experimentmappen zoals `results/experiment-contexten/` doen mee |
| **Mutatietest** | draait alle handgemaakte kandidaten door de validator en laat zien hoeveel fouten hij vangt. Geen model en geen sleutel nodig |
| **Uitleg** | een korte toelichting in de app zelf |

### Tips voor een demo

- Een live aanroep duurt 10 tot 60 seconden bij Sonnet met medium effort, en veel langer bij hoge effort. De tijdmeting bij `top_customers` duurt enkele minuten. Plan daarop.
- Begin met een opgeslagen antwoord of een handgemaakte kandidaat: dat kost niets en laat de hele controle zien. Doe daarna hooguit één live-aanroep.
- Start de database ruim van tevoren (na een onjuiste afsluiting duurt dat langer) en controleer de telling van `orders` (stap B1).

---

## 7. Een eigen query toevoegen

Alle scripts lezen de lijst `CASES` onderaan `cases/cases.py`. Een nieuwe query toevoegen gaat in vier stappen:

1. **Zet de query in `cases/original/<naam>.sql`.** Gebruik `%(naam)s`-plaatsvervangers voor parameters (zoals `%(tenant_id)s`, `%(from)s`, `%(to)s`, `%(limit)s` in de bestaande query's).
2. **Lever parametersets.** Hergebruik `std_params(limit)` als je query dezelfde parameters heeft als de bestaande, of schrijf een functie `f(ctx)` die een lijst `(label, dict)` teruggeeft. Voor de tijdmeting is `std_timing(limit)` of een eigen functie `f(ctx)` die één dict teruggeeft.
3. **Maak (optioneel) handgemaakte kandidaten** voor de mutatietest:

   ```python
   Candidate(name="M1_filter_weg", sql="...", expected="not_equivalent", fault="filter_weggelaten")
   Candidate(name="E1_cte_herschrijving", sql="...", expected="equivalent", fault="-")
   ```

4. **Voeg een `Case` toe aan `CASES`:**

   ```python
   Case("mijn_query", original("mijn_query"), ["kolom_a", "kolom_b"], std_params(1000), std_timing(1000), MIJN_CANDS)
   ```

   Het derde argument is de lijst met kolommen die de `ORDER BY` bepalen, of `None` als het origineel geen `ORDER BY` heeft.

Daarna werkt `--cases mijn_query` in `run_llm.py`, doet `run_validation.py` de kandidaten mee en neemt `analyse.py` de query op.

Een query die niet op de SUE-database draait, vraagt een eigen database en een eigen `make_ctx` (die nu `orders` en `tenant_id` aanneemt).

---

## 8. Modelvergelijking: meerdere modellen en instellingen

`scripts/run_experiment.py` laat meerdere modellen **dezelfde query's** op **dezelfde database** herschrijven en beoordeelt elk antwoord met dezelfde validatie. Je vergelijkt zo prestatie en kosten per model, en het effect van drie instellingen.

### Het raster

| Dimensie | Standaard | Waarom |
|---|---|---|
| Model | `haiku`, `sonnet`, `opus`, `fable` (Haiku 5.5, Sonnet 5.5, Opus 5.5, Fable 5.1) | de modellen die je vergelijkt; ook letterlijke modelnamen zijn toegestaan |
| Outputlimiet (`--limits`) | 4000, 2000, 1000 | een harde limiet op uitvoertokens; het denken telt mee, dus een te lage limiet kapt het antwoord af |
| Context (`--conditions`) | `C1_query` en `C4_stats` | de twee uitersten: alleen de query tegenover alle context |
| Query's (`--cases`) | alle vier | dezelfde trage query's voor elk model |
| Herhalingen (`--reps`) | 3 | meerdere antwoorden per query en conditie; de analyse berekent daaruit wat 1, 2 of 3 pogingen opleveren |
| Effort (`--effort`) | `medium` voor alle modellen | de standaard verschilt per model (Haiku 5.5 en Opus 5.5: `medium`; Sonnet 5.5 en Fable 5.1: `high`); zonder vaste waarde meet je model en denkdiepte door elkaar |

Een run is één model bij één limiet: 4 query's × 2 condities × 3 herhalingen = 24 antwoorden. Het volledige raster is 4 modellen × 3 limieten = 12 runs en 288 antwoorden. Houd de database en alle andere instellingen gelijk tijdens het hele experiment; genereer de data dus niet opnieuw.

**Herhalingen worden niet apart gedraaid.** Je draait per query en conditie 3 antwoorden. `analyse_models.py` rekent daaruit uit wat de kans op minstens één geslaagde poging is bij 1, 2 of 3 pogingen (pass@k). Dat is zuiverder dan drie aparte runs, omdat elk antwoord een toevallige trekking is.

### Voorbeeld: welke context maakt het verschil?

Het raster hierboven vergelijkt modellen. Wil je alleen weten **welke contextinformatie het verschil maakt**, dan draai je één model met alle vier de condities, zodat alleen de context varieert. Eerst het plan (kost niets), dan de echte run:

```powershell
python scripts/run_experiment.py $URI --name contexten --models sonnet --limits 16000 --conditions C1_query C2_schema C3_plan C4_stats --reps 3 --plan
python scripts/run_experiment.py $URI --name contexten --models sonnet --limits 16000 --conditions C1_query C2_schema C3_plan C4_stats --reps 3
```

Dat zijn 4 query's x 4 condities x 3 herhalingen = 48 antwoorden. De uitvoer staat in `results/experiment-contexten/` (met `resultaten.csv` van alle runs onder elkaar). Een ander model of een andere effort draai je in een **eigen experiment met een andere `--name`**, bijvoorbeeld `--name contexten-high --effort high`, omdat `experiment.json` geen gemengde instellingen toelaat. Doe bij een dure combinatie eerst een kleine proef, bijvoorbeeld `--cases top_customers --reps 1`, en kijk in `resultaten.csv` naar `uitvoertokens`, `kosten_usd` en `modeltijd_s` voordat je het hele raster draait.

**Gemeten kosten en duur** (november 2026, via OpenRouter; meetpunten en geen garantie, en alleen geldig bij deze instellingen en prijzen):

| Run | Antwoorden | Kosten | Duur | Uitvoertokens per antwoord |
|---|---|---|---|---|
| Sonnet 5.5, effort `medium`, limiet 16000, C1 t/m C4, alle query's | 48 | circa $0,53 | 19 minuten | circa 570 tot 700 gemiddeld per conditie, hoogstens 1.394 |
| Fable 5.1, effort `max`, limiet 16000, `top_customers`, C1 t/m C4 | 4 | circa $2,5 | 13 minuten | 7.900 tot 16.000; het antwoord bij C1 bereikte de limiet en werd afgekapt |

De kosten worden bepaald door de uitvoer (het denken) en veel minder door de hoeveelheid context: bij Fable was het invoergedeelte 4 tot 11% van de kosten per antwoord. De kostenschatting van `--plan` gaat uit van het tokengebruik van Sonnet met effort medium en is bij hoge effort of een duurder model te laag.

### Stappen

**1. De sleutel zetten** (alleen in de terminal, nooit in een bestand; zie stap B2):

```powershell
$s = Read-Host "OpenRouter-sleutel" -AsSecureString
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new("", $s).Password
```

**2. Sleutel, modelnamen en effort testen.** Dit stuurt één klein verzoek per model, heeft geen database nodig en kost een fractie van een cent per model:

```powershell
python scripts/run_experiment.py --check
```

Elke regel begint met `OK` of `FOUT`. Bij `FOUT` staat de melding van de aanbieder erbij. De naam `anthropic/claude-fable-5.1` bij OpenRouter werkte in november 2026 (een run met effort `max` ging goed); werkt een standaardnaam later niet meer, geef dan de naam uit de catalogus van OpenRouter mee: `--models haiku sonnet opus <naam-van-fable>`. Test je maar één model, gebruik dan `--models sonnet` (en eventueel `--effort high`). Met `--provider anthropic` en een Anthropic-sleutel gebruikt het script de namen van Anthropic zelf.

**3. Het plan bekijken** met een kostenschatting, zonder iets te draaien:

```powershell
python scripts/run_experiment.py $URI --plan
```

De schatting gaat uit van het tokenverbruik van een eerdere Sonnet-run en de prijzen in `llm/prices.py`. Modellen die meer denken, kosten meer.

**4. Het experiment draaien:**

```powershell
python scripts/run_experiment.py $URI
```

De database moet draaien (stap B1) en je laptop moet rustig blijven: de tijdmetingen die bepalen of een herschrijving sneller is, lopen op dezelfde machine. Reken op ongeveer 35 seconden per antwoord, dus enkele uren voor het volledige raster. De goedkoopste modellen komen eerst.

- **Hervatten:** is een run klaar (`llm-results.csv` bestaat), dan wordt hij overgeslagen. Na een onderbreking start je dus gewoon hetzelfde commando opnieuw. Een onderbroken run wordt opzij gezet als `<naam>.onvolledig-<tijdstempel>` en nooit verwijderd.
- **Beveiliging:** zijn meer dan 25% van de aanroepen in een run mislukt, dan stopt het experiment en wordt die run opzij gezet als `<naam>.api-fouten`. Controleer dan sleutel, tegoed en modelnaam met `--check` en start opnieuw.
- **Instellingen vastleggen:** `experiment.json` in de experimentmap bewaart de instellingen. Wijzig je effort, condities, query's of herhalingen, gebruik dan een andere `--name`, zodat runs met verschillende instellingen niet worden gemengd.
- **Een deel draaien:** bijvoorbeeld `--models haiku sonnet --limits 2000`.

**5. Analyseren** (geen database en geen sleutel nodig):

```powershell
python scripts/analyse_models.py
```

De uitvoer staat in `results/experiment-<naam>/analyse/`:

| Bestand | Inhoud |
|---|---|
| `samenvatting.md` | Leesbaar verslag met vijf tabellen: per model en limiet, context, herhalingen (pass@k), per query, afkappen en tokenverbruik |
| `per_groep.csv` | Per model, limiet en conditie: aantallen per uitkomst, kosten, kosten per `ACCEPTED`, tijd, tokens |
| `passk.csv` | pass@1, pass@2 en pass@3 met de kosten van die pogingen |
| `per_query.csv` | Hetzelfde per query |
| `per_poging.csv` | Een regel per antwoord (zonder SQL), voor eigen grafieken |

### Uitkomsten en begrippen

| Uitkomst | Betekenis |
|---|---|
| `ACCEPTED` | resultaat gelijk op alle parametersets en minstens 1,2× sneller |
| `fout` | resultaat verschilt van het origineel, of geen geldige SELECT |
| `gelijk, trager` | gelijk resultaat, maar minder dan 1/1,2 van de snelheid van het origineel |
| `ongewijzigd` | het model gaf het origineel terug (commentaar, witruimte en afsluitende `;` genegeerd) |
| `afgekapt` | de tokenlimiet was bereikt voor er een volledig SQL-blok stond; dit is een gevolg van de limiet en geen fout van het model, maar het kost wel tokens |
| `api-fout` | de aanroep mislukte na herhaalde pogingen; telt niet mee in n |

**pass@k** is de geschatte kans dat minstens één van k pogingen `ACCEPTED` is: `1 - C(n-c, k) / C(n, k)`, met n het aantal gedane pogingen en c het aantal `ACCEPTED` daarvan, gemiddeld over de query's (Chen e.a., 2021). Het is een schatting uit weinig data. **Kosten per `ACCEPTED`** zijn de totale kosten gedeeld door het aantal `ACCEPTED`-antwoorden: de prijs van één bruikbare herschrijving, inclusief alle mislukte pogingen.

### Hoe de aanroep naar OpenRouter werkt

`llm/client.py` roept `POST https://openrouter.ai/api/v1/chat/completions` aan met de sleutel als bearer-token. De systeemprompt gaat mee als `system`-bericht, de effort als `reasoning.effort`, de limiet als `max_tokens`. Tijdelijke fouten (429 en 5xx) worden tot vier keer geprobeerd met oplopende wachttijd. Voor een test met een nepserver kun je het basisadres overschrijven met `OPENROUTER_BASE_URL`. De sleutel wordt nooit geprint of opgeslagen.

---

## 9. Problemen oplossen

| Melding of gedrag | Oorzaak en oplossing |
|---|---|
| `ModuleNotFoundError: No module named 'classes'` of `'cases'` | Je draait niet vanuit de repo-map, of de IDE heeft `cases/` of `validator/` als *Sources Root* gemarkeerd. Draai `python scripts/...` vanuit de repo-map en markeer geen submappen als Sources Root. |
| PyCharm toont "Import resolves to its containing file" bij `cases.py` | Alleen een waarschuwing van de statische analyse: het bestand `cases.py` heeft dezelfde naam als de map `cases`. Het script draait gewoon. Negeren. |
| `TypeError: Could not resolve authentication method` of "Zet eerst de omgevingsvariabele OPENROUTER_API_KEY" (of `ANTHROPIC_API_KEY`) | De sleutel is niet gezet in **dit** terminalvenster. Zie stap B2. |
| `start_db.py` geeft een time-out van ongeveer 10 seconden (`TimeoutExpired`), vaak na een herstart of uitzetten zonder stoppen | De database moet herstellen na een onjuiste afsluiting en Windows houdt het logbestand nog vast ("sharing violation" in het log, ongeveer 30 seconden), terwijl pgserver maar 10 seconden wacht. De server start op de achtergrond gewoon door. Wacht een minuut, kijk of `postmaster.pid` in de datamap als laatste regel `ready` toont en voer `start_db.py` opnieuw uit: het ziet dat de server draait en print de URI. Controleer daarna het aantal orders (stap B1). Stop de database voortaan met `stop_db.py`. |
| `start_db.py` print wel een URI, maar elke verbinding geeft `ConnectionTimeout`; `stop_db.py` meldt `Failed to stop server, killing it instead` en `AccessDenied` | Verouderd `postmaster.pid` na een onjuiste afsluiting: het procesnummer erin is intussen aan een ander programma gegeven (bijvoorbeeld `NisSrv.exe`, de netwerkinspectie van Windows Defender). pgserver kijkt alleen of dat nummer bestaat, denkt dat de database al draait en start hem niet; `stop_db.py` probeert dat vreemde proces te beëindigen. **Voer `stop_db.py` dan niet uit en draai PowerShell niet als administrator.** Controleer dat `Get-Process postgres` niets toont, hernoem `postmaster.pid` in de datamap (bijvoorbeeld naar `postmaster.pid.oud`; verwijder niets) en start met `start_db.py` opnieuw. |
| De URI geeft `ConnectionTimeout` of `$URI` is leeg | De database draait niet in dit venster of `$URI` is niet gezet. Start de database en zet `$URI` opnieuw (stap B1). |
| In de UI is de knop voor een live-aanroep uitgeschakeld | De sleutel is niet gezet in het venster waarin je `streamlit run` startte (stap B2). Stop Streamlit, zet de sleutel en start opnieuw. |
| De URI werkt niet meer | De poort verandert bij elke start. Gebruik de URI die `start_db.py` nu print. |
| `alembic` mislukt op `pgcrypto` | De regel in `0001_tenancy.py` is nog niet verwijderd (stap A4). |
| `analyse.py`: "geen figuren: matplotlib niet geinstalleerd" | `pip install matplotlib`. De tabellen worden wel gemaakt. |
| `run_experiment.py --check`: `FOUT ... HTTP 401` | De OpenRouter-sleutel is niet gezet in **dit** terminalvenster, of is onjuist (let op: een sleutel die met `sk-ant-` begint is geen OpenRouter-sleutel). Zie stap B2. |
| `run_experiment.py --check`: `FOUT ... HTTP 400` met "No endpoints found" of "not a valid model" | De modelnaam klopt niet voor deze aanbieder. Zoek de naam op in de catalogus van OpenRouter en geef hem mee met `--models`. |
| `run_experiment.py --check`: `FOUT ... HTTP 402` of een melding over tegoed | Er staat te weinig tegoed op de sleutel, of de sleutel heeft een limiet. Vraag de eigenaar van de sleutel. |
| `run_experiment.py` stopt met "Meer dan 25% API-fouten" | Zie de melding die `run_llm.py` per mislukte aanroep print. Los het op met `--check` en start opnieuw; de gestopte run staat opzij als `.api-fouten`. |
| `run_experiment.py` weigert met "bevat andere instellingen" | De map `experiment-<naam>` is met andere instellingen gemaakt. Gebruik een andere `--name`. |
| veel `afgekapt` in de analyse of in `resultaten.csv` | De outputlimiet is te laag voor het model, omdat het denken meetelt. Verhoog `--limits` of verlaag `--effort`. Bij effort `max` was 16000 in een meting voor 1 van 4 antwoorden te weinig (Fable 5.1). |
| `analyse.py` toont geen ruisband | Er is geen nepmodelrun (A/A) in `results/`. Draai stap A8c opnieuw; het kost niets. |
| `analyse.py`: "Geen volledige runs gevonden" | `results/` bevat geen map met `llm-results.csv` van een echt model met alle vier de condities. Draai stap B4 of geef `--map` mee. |

---

## 10. Technische beperkingen

- **Geen bewijs van gelijkwaardigheid.** `ACCEPTED` betekent: gelijk resultaat op de geteste parametersets en minstens 1,2× sneller. De validator bewijst niet dat een herschrijving voor alle mogelijke data gelijk is. Een fout die de testdata niet zichtbaar maakt, wordt gemist (voorbeeld: `M3_geen_id_tiebreak`, omdat in `audit_log` de combinatie tenant en tijd uniek is).
- **Verzonnen, kleine data.** Standaard schaal 0,02 met 3 tenants. Op een grotere of echte database kunnen queryplannen en tijden anders zijn. Op schaal 0,05 duurde `top_customers` al 34 tot 56 seconden per uitvoering.
- **Tijdmetingen op één machine.** Gedaan met de standaardinstellingen van een ingebedde PostgreSQL 16.2 en niet vergelijkbaar met de bewust slechte `postgresql.conf` van SUE. `pg_stat_statements` en `auto_explain` zitten niet in `pgserver` en worden niet gebruikt.
- **De drempel 1,2× is een ontwerpkeuze.** Meet de ruis van je eigen machine met de A/A-controle (stap A8c) voordat je de drempel vertrouwt. Met 3 herhalingen per meting gaf de A/A-controle wel onterechte `ACCEPTED`-oordelen; daarom zijn 7 herhalingen de standaard. Een uitkomst van 0 onterechte `ACCEPTED` bij 48 metingen betekent niet dat de kans nul is: het exacte 95%-interval loopt dan tot ongeveer 7%.
- **Eigen labels.** Het verwachte oordeel (`expected`) van de handgemaakte kandidaten is de redenering van de maker en niet onafhankelijk bewezen.
- **Categorie "ongewijzigd" in de analyse.** `analyse.py` berekent dit opnieuw uit genormaliseerde SQL (commentaar, witruimte en afsluitende `;` genegeerd), omdat de vlag `unchanged` in de ruwe resultaten onjuist is wanneer het model de commentaarkop weglaat.
- **LLM-uitkomsten wisselen.** Een model geeft bij een herhaalde run niet dezelfde antwoorden. Daarom is bij de modelvergelijking elk resultaat een schatting uit weinig trekkingen; kijk naar de intervallen.
- **Effort en sampling.** Bij de nieuwste Claude-modellen zijn `temperature`, `top_p` en `top_k` niet instelbaar, en de standaard-effort verschilt per model. De modelvergelijking zet effort daarom voor alle modellen gelijk; zonder `--effort` meet je model en denkdiepte door elkaar.
- **Kosten volgens een prijstabel.** `llm/prices.py` bevat de prijzen op de datum in dat bestand. Controleer ze voordat je ze in een verslag zet. Een aanbieder als OpenRouter kan extra kosten rekenen die niet in de tokenprijs zitten.
- **Via een tussenpartij.** Bij `--provider openrouter` gaan de prompts (queries, schema, plannen) langs OpenRouter en daarna naar de modelaanbieder. Controleer of dat past bij de afspraken over dataverwerking.
- **Kleine testbank.** Er zijn vier query's. In de gemeten runs werd maar één daarvan aantoonbaar sneller (`top_customers`), dus verschillen tussen condities, modellen en efforts komen vooral uit die ene query. Met 3 herhalingen per cel zijn zulke verschillen suggestief en geen bewijs.
- **Gedeelde sleutel.** Wordt een OpenRouter-sleutel door een groep gebruikt, dan tellen tegoed en gebruik voor iedereen samen. Een run met een duur model of een hoge effort kan veel kosten; zie de gemeten kosten in hoofdstuk 8.
- **Afgekapte antwoorden bij hoge effort.** Denktokens tellen mee in de limiet; bij effort `max` kan 16000 te weinig zijn. Een afgekapt antwoord is een gevolg van de limiet en geen oordeel over de herschrijving.
- **Platform.** De scripts zijn getest op Windows met conda en Python 3.12 en eerder ook op Linux. De Streamlit-demo is ontwikkeld en getest op Linux; controleer hem op Windows voordat je er een demo mee doet.

---

## 11. Bronnen

- Webshop, schema en datagenerator: SUE, repository `robinverstraelen/sql-performance-challenge`, commit `6951dfc`. Dit is code van SUE en geen onderdeel van deze repository.
- Ingebedde PostgreSQL: [`pgserver`](https://pypi.org/project/pgserver/). SQL-parser: [`sqlglot`](https://pypi.org/project/sqlglot/). Database-driver: `psycopg` 3.
- Modellen: `claude-sonnet-5-5` en de andere modellen van de modelvergelijking via de Anthropic API of OpenRouter. Prijzen en modelgegevens: [Claude Platform Docs, Pricing](https://platform.claude.com/docs/en/about-claude/pricing) en de pagina's per model. Effort: [Claude Platform Docs, Effort](https://platform.claude.com/docs/en/build-with-claude/effort). OpenRouter: [openrouter.ai/docs](https://openrouter.ai/docs).
- pass@k: Chen e.a. (2021), *Evaluating Large Language Models Trained on Code*.
