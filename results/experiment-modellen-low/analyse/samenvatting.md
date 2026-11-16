# Modelvergelijking: resultaten van experiment 'modellen-low'

Aanbieder: openrouter. Effort: low voor alle modellen. Query's: top_products, top_customers, audit_log_page, revenue_orders. Condities: C1_query, C2_schema, C3_plan, C4_stats. Herhalingen per query en conditie: 3. Totaal 144 antwoorden, tokenkosten $1.84.

Lees dit als een kleine steekproef: per model en limiet zijn er hooguit 48 antwoorden en slechts een of enkele query's laten een ACCEPTED-antwoord toe. Tussen haakjes staat het exacte 95%-interval.

## 1. Prestatie en kosten per model en outputlimiet (beide condities samen)

| Model | Limiet | n | ACCEPTED | fout | gelijk, trager | ongewijzigd | afgekapt | api-fout | Kosten per antwoord | Kosten totaal | Kosten per ACCEPTED | Seconden per antwoord |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 | 16000 | 48 | 23% [12-37] | 0 | 8 | 24 | 0 | 0 | $0.0010 | $0.05 | $0.004 | 6.9 |
| Sonnet 5.5 | 16000 | 48 | 17% [7-30] | 1 | 9 | 29 | 0 | 0 | $0.0110 | $0.53 | $0.066 | 5.0 |
| Opus 5.5 | 16000 | 48 | 21% [10-35] | 0 | 13 | 24 | 0 | 0 | $0.0263 | $1.26 | $0.126 | 8.8 |

## 2. Context: alleen de query (C1) tegenover alles (C4), limiet 16000

| Model | Conditie | n | ACCEPTED | fout | gelijk, trager | ongewijzigd | Kosten per antwoord | Kosten per ACCEPTED | Mediaan speedup (ACCEPTED) |
|---|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 | C1_query | 12 | 25% [5-57] | 0 | 1 | 6 | $0.0007 | $0.003 | 125.7 |
| Haiku 5.5 | C2_schema | 12 | 17% [2-48] | 0 | 2 | 6 | $0.0009 | $0.005 | 190.1 |
| Haiku 5.5 | C3_plan | 12 | 25% [5-57] | 0 | 2 | 6 | $0.0011 | $0.004 | 162.3 |
| Haiku 5.5 | C4_stats | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0012 | $0.005 | 123.5 |
| Sonnet 5.5 | C1_query | 12 | 8% [0-38] | 1 | 2 | 8 | $0.0073 | $0.088 | 119.4 |
| Sonnet 5.5 | C2_schema | 12 | 8% [0-38] | 0 | 2 | 8 | $0.0100 | $0.120 | 117.5 |
| Sonnet 5.5 | C3_plan | 12 | 25% [5-57] | 0 | 2 | 7 | $0.0120 | $0.048 | 161.1 |
| Sonnet 5.5 | C4_stats | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0148 | $0.059 | 160.4 |
| Opus 5.5 | C1_query | 12 | 17% [2-48] | 0 | 4 | 5 | $0.0203 | $0.122 | 191.7 |
| Opus 5.5 | C2_schema | 12 | 17% [2-48] | 0 | 3 | 7 | $0.0233 | $0.140 | 209.2 |
| Opus 5.5 | C3_plan | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0272 | $0.109 | 186.1 |
| Opus 5.5 | C4_stats | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0342 | $0.137 | 184.7 |

## 3. Herhalen: kans op minstens een ACCEPTED-antwoord bij 1, 2 of 3 pogingen (pass@k), limiet 16000

| Model | Conditie | Query's | pass@1 | pass@2 | pass@3 | Winst k=1 naar max k | Kosten van max k pogingen |
|---|---|---|---|---|---|---|---|
| Haiku 5.5 | C1_query | 4 | 25% | 25% | 25% | +0 pp | $0.0022 |
| Haiku 5.5 | C2_schema | 4 | 17% | 25% | 25% | +8 pp | $0.0027 |
| Haiku 5.5 | C3_plan | 4 | 25% | 25% | 25% | +0 pp | $0.0032 |
| Haiku 5.5 | C4_stats | 4 | 25% | 25% | 25% | +0 pp | $0.0036 |
| Sonnet 5.5 | C1_query | 4 | 8% | 17% | 25% | +17 pp | $0.0220 |
| Sonnet 5.5 | C2_schema | 4 | 8% | 17% | 25% | +17 pp | $0.0301 |
| Sonnet 5.5 | C3_plan | 4 | 25% | 25% | 25% | +0 pp | $0.0360 |
| Sonnet 5.5 | C4_stats | 4 | 25% | 25% | 25% | +0 pp | $0.0444 |
| Opus 5.5 | C1_query | 4 | 17% | 25% | 25% | +8 pp | $0.0610 |
| Opus 5.5 | C2_schema | 4 | 17% | 25% | 25% | +8 pp | $0.0699 |
| Opus 5.5 | C3_plan | 4 | 25% | 25% | 25% | +0 pp | $0.0816 |
| Opus 5.5 | C4_stats | 4 | 25% | 25% | 25% | +0 pp | $0.1027 |

pp = procentpunt. Het criterium voor 'dit model heeft geen herhalingen nodig' hoort vooraf te zijn vastgelegd, bijvoorbeeld een winst van minder dan 10 procentpunt. Met 4 query's en 3 antwoorden per query is een verschil klein ten opzichte van de onzekerheid.

## 4. Per query, limiet 16000 (beide condities samen): ACCEPTED van n, mediaan speedup bij ACCEPTED

| Model | audit_log_page | revenue_orders | top_customers | top_products |
|---|---|---|---|---|
| Haiku 5.5 | 0/12 | 0/12 | 11/12 (161x) | 0/12 |
| Sonnet 5.5 | 0/12 | 0/12 | 8/12 (161x) | 0/12 |
| Opus 5.5 | 0/12 | 0/12 | 10/12 (192x) | 0/12 |

## 5. Afkappen en tokenverbruik per model en limiet

| Model | Limiet | n | afgekapt | Uitvoertokens mediaan | p90 | max |
|---|---|---|---|---|---|---|
| Haiku 5.5 | 16000 | 48 | 0 (0%) | 1471 | 2405 | 3329 |
| Sonnet 5.5 | 16000 | 48 | 0 (0%) | 604 | 873 | 1360 |
| Opus 5.5 | 16000 | 48 | 0 (0%) | 814 | 1208 | 1768 |

Uitvoertokens bevatten ook de denktokens. Een antwoord dat bij een lage limiet wordt afgekapt, is geen fout van het model maar een gevolg van de limiet; het telt hier als 'afgekapt' en niet als 'fout'.

## Methode en kanttekeningen

- Kosten zijn berekend uit de gemeten tokens en de prijstabel in `llm/prices.py` (dollar per miljoen tokens). Denktokens worden als uitvoer gerekend. Gerapporteerde kosten van de aanbieder staan, voor zover beschikbaar, in `per_poging.csv`.
- ACCEPTED hangt af van tijdmetingen op een laptop met een kleine database; dezelfde herschrijving kan elders anders uitvallen.
- Verschillen tussen modellen zijn pas aantoonbaar als de intervallen niet overlappen; bij kleine aantallen is dat zelden zo.
