# Modelvergelijking: resultaten van experiment 'modellen-high'

Aanbieder: openrouter. Effort: high voor alle modellen. Query's: top_products, top_customers, audit_log_page, revenue_orders. Condities: C1_query, C2_schema, C3_plan, C4_stats. Herhalingen per query en conditie: 3. Totaal 144 antwoorden, tokenkosten $2.62.

Lees dit als een kleine steekproef: per model en limiet zijn er hooguit 48 antwoorden en slechts een of enkele query's laten een ACCEPTED-antwoord toe. Tussen haakjes staat het exacte 95%-interval.

## 1. Prestatie en kosten per model en outputlimiet (beide condities samen)

| Model | Limiet | n | ACCEPTED | fout | gelijk, trager | ongewijzigd | afgekapt | api-fout | Kosten per antwoord | Kosten totaal | Kosten per ACCEPTED | Seconden per antwoord |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 | 16000 | 48 | 25% [14-40] | 0 | 9 | 21 | 0 | 0 | $0.0017 | $0.08 | $0.007 | 13.1 |
| Sonnet 5.5 | 16000 | 48 | 25% [14-40] | 0 | 9 | 27 | 0 | 0 | $0.0152 | $0.73 | $0.061 | 8.1 |
| Opus 5.5 | 16000 | 48 | 25% [14-40] | 0 | 12 | 22 | 0 | 0 | $0.0377 | $1.81 | $0.151 | 13.8 |

## 2. Context: alleen de query (C1) tegenover alles (C4), limiet 16000

| Model | Conditie | n | ACCEPTED | fout | gelijk, trager | ongewijzigd | Kosten per antwoord | Kosten per ACCEPTED | Mediaan speedup (ACCEPTED) |
|---|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 | C1_query | 12 | 25% [5-57] | 0 | 1 | 5 | $0.0013 | $0.005 | 190.2 |
| Haiku 5.5 | C2_schema | 12 | 25% [5-57] | 0 | 2 | 4 | $0.0014 | $0.006 | 183.7 |
| Haiku 5.5 | C3_plan | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0018 | $0.007 | 154.5 |
| Haiku 5.5 | C4_stats | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0022 | $0.009 | 158.3 |
| Sonnet 5.5 | C1_query | 12 | 25% [5-57] | 0 | 0 | 9 | $0.0121 | $0.049 | 198.2 |
| Sonnet 5.5 | C2_schema | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0140 | $0.056 | 214.2 |
| Sonnet 5.5 | C3_plan | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0156 | $0.062 | 212.3 |
| Sonnet 5.5 | C4_stats | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0191 | $0.076 | 212.6 |
| Opus 5.5 | C1_query | 12 | 25% [5-57] | 0 | 3 | 4 | $0.0344 | $0.137 | 180.2 |
| Opus 5.5 | C2_schema | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0326 | $0.130 | 206.0 |
| Opus 5.5 | C3_plan | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0387 | $0.155 | 194.1 |
| Opus 5.5 | C4_stats | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0450 | $0.180 | 192.8 |

## 3. Herhalen: kans op minstens een ACCEPTED-antwoord bij 1, 2 of 3 pogingen (pass@k), limiet 16000

| Model | Conditie | Query's | pass@1 | pass@2 | pass@3 | Winst k=1 naar max k | Kosten van max k pogingen |
|---|---|---|---|---|---|---|---|
| Haiku 5.5 | C1_query | 4 | 25% | 25% | 25% | +0 pp | $0.0039 |
| Haiku 5.5 | C2_schema | 4 | 25% | 25% | 25% | +0 pp | $0.0042 |
| Haiku 5.5 | C3_plan | 4 | 25% | 25% | 25% | +0 pp | $0.0053 |
| Haiku 5.5 | C4_stats | 4 | 25% | 25% | 25% | +0 pp | $0.0066 |
| Sonnet 5.5 | C1_query | 4 | 25% | 25% | 25% | +0 pp | $0.0364 |
| Sonnet 5.5 | C2_schema | 4 | 25% | 25% | 25% | +0 pp | $0.0419 |
| Sonnet 5.5 | C3_plan | 4 | 25% | 25% | 25% | +0 pp | $0.0468 |
| Sonnet 5.5 | C4_stats | 4 | 25% | 25% | 25% | +0 pp | $0.0574 |
| Opus 5.5 | C1_query | 4 | 25% | 25% | 25% | +0 pp | $0.1031 |
| Opus 5.5 | C2_schema | 4 | 25% | 25% | 25% | +0 pp | $0.0978 |
| Opus 5.5 | C3_plan | 4 | 25% | 25% | 25% | +0 pp | $0.1161 |
| Opus 5.5 | C4_stats | 4 | 25% | 25% | 25% | +0 pp | $0.1349 |

pp = procentpunt. Het criterium voor 'dit model heeft geen herhalingen nodig' hoort vooraf te zijn vastgelegd, bijvoorbeeld een winst van minder dan 10 procentpunt. Met 4 query's en 3 antwoorden per query is een verschil klein ten opzichte van de onzekerheid.

## 4. Per query, limiet 16000 (beide condities samen): ACCEPTED van n, mediaan speedup bij ACCEPTED

| Model | audit_log_page | revenue_orders | top_customers | top_products |
|---|---|---|---|---|
| Haiku 5.5 | 0/12 | 0/12 | 12/12 (182x) | 0/12 |
| Sonnet 5.5 | 0/12 | 0/12 | 12/12 (211x) | 0/12 |
| Opus 5.5 | 0/12 | 0/12 | 12/12 (193x) | 0/12 |

## 5. Afkappen en tokenverbruik per model en limiet

| Model | Limiet | n | afgekapt | Uitvoertokens mediaan | p90 | max |
|---|---|---|---|---|---|---|
| Haiku 5.5 | 16000 | 48 | 0 (0%) | 2498 | 4974 | 8490 |
| Sonnet 5.5 | 16000 | 48 | 0 (0%) | 1074 | 1807 | 2113 |
| Opus 5.5 | 16000 | 48 | 0 (0%) | 1197 | 2698 | 3678 |

Uitvoertokens bevatten ook de denktokens. Een antwoord dat bij een lage limiet wordt afgekapt, is geen fout van het model maar een gevolg van de limiet; het telt hier als 'afgekapt' en niet als 'fout'.

## Methode en kanttekeningen

- Kosten zijn berekend uit de gemeten tokens en de prijstabel in `llm/prices.py` (dollar per miljoen tokens). Denktokens worden als uitvoer gerekend. Gerapporteerde kosten van de aanbieder staan, voor zover beschikbaar, in `per_poging.csv`.
- ACCEPTED hangt af van tijdmetingen op een laptop met een kleine database; dezelfde herschrijving kan elders anders uitvallen.
- Verschillen tussen modellen zijn pas aantoonbaar als de intervallen niet overlappen; bij kleine aantallen is dat zelden zo.
