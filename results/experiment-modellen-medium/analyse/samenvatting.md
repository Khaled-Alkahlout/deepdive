# Modelvergelijking: resultaten van experiment 'modellen-medium'

Aanbieder: openrouter. Effort: medium voor alle modellen. Query's: top_products, top_customers, audit_log_page, revenue_orders. Condities: C1_query, C2_schema, C3_plan, C4_stats. Herhalingen per query en conditie: 3. Totaal 144 antwoorden, tokenkosten $2.17.

Lees dit als een kleine steekproef: per model en limiet zijn er hooguit 48 antwoorden en slechts een of enkele query's laten een ACCEPTED-antwoord toe. Tussen haakjes staat het exacte 95%-interval.

## 1. Prestatie en kosten per model en outputlimiet (beide condities samen)

| Model | Limiet | n | ACCEPTED | fout | gelijk, trager | ongewijzigd | afgekapt | api-fout | Kosten per antwoord | Kosten totaal | Kosten per ACCEPTED | Seconden per antwoord |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 | 16000 | 48 | 23% [12-37] | 0 | 10 | 23 | 0 | 0 | $0.0012 | $0.06 | $0.005 | 8.4 |
| Sonnet 5.5 | 16000 | 48 | 12% [5-25] | 0 | 15 | 27 | 0 | 0 | $0.0111 | $0.53 | $0.089 | 5.1 |
| Opus 5.5 | 16000 | 48 | 25% [14-40] | 0 | 12 | 22 | 0 | 0 | $0.0330 | $1.59 | $0.132 | 11.8 |

## 2. Context: alleen de query (C1) tegenover alles (C4), limiet 16000

| Model | Conditie | n | ACCEPTED | fout | gelijk, trager | ongewijzigd | Kosten per antwoord | Kosten per ACCEPTED | Mediaan speedup (ACCEPTED) |
|---|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 | C1_query | 12 | 17% [2-48] | 0 | 2 | 5 | $0.0008 | $0.005 | 152.4 |
| Haiku 5.5 | C2_schema | 12 | 25% [5-57] | 0 | 2 | 6 | $0.0010 | $0.004 | 124.8 |
| Haiku 5.5 | C3_plan | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0013 | $0.005 | 158.9 |
| Haiku 5.5 | C4_stats | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0015 | $0.006 | 159.9 |
| Sonnet 5.5 | C1_query | 12 | 0% [0-26] | 0 | 3 | 9 | $0.0075 | - | - |
| Sonnet 5.5 | C2_schema | 12 | 0% [0-26] | 0 | 6 | 6 | $0.0099 | - | - |
| Sonnet 5.5 | C3_plan | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0119 | $0.048 | 156.4 |
| Sonnet 5.5 | C4_stats | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0152 | $0.061 | 188.8 |
| Opus 5.5 | C1_query | 12 | 25% [5-57] | 0 | 3 | 5 | $0.0279 | $0.112 | 196.0 |
| Opus 5.5 | C2_schema | 12 | 25% [5-57] | 0 | 3 | 5 | $0.0309 | $0.123 | 210.3 |
| Opus 5.5 | C3_plan | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0329 | $0.131 | 163.2 |
| Opus 5.5 | C4_stats | 12 | 25% [5-57] | 0 | 3 | 6 | $0.0405 | $0.162 | 217.1 |

## 3. Herhalen: kans op minstens een ACCEPTED-antwoord bij 1, 2 of 3 pogingen (pass@k), limiet 16000

| Model | Conditie | Query's | pass@1 | pass@2 | pass@3 | Winst k=1 naar max k | Kosten van max k pogingen |
|---|---|---|---|---|---|---|---|
| Haiku 5.5 | C1_query | 4 | 17% | 25% | 25% | +8 pp | $0.0025 |
| Haiku 5.5 | C2_schema | 4 | 25% | 25% | 25% | +0 pp | $0.0029 |
| Haiku 5.5 | C3_plan | 4 | 25% | 25% | 25% | +0 pp | $0.0040 |
| Haiku 5.5 | C4_stats | 4 | 25% | 25% | 25% | +0 pp | $0.0044 |
| Sonnet 5.5 | C1_query | 4 | 0% | 0% | 0% | +0 pp | $0.0224 |
| Sonnet 5.5 | C2_schema | 4 | 0% | 0% | 0% | +0 pp | $0.0297 |
| Sonnet 5.5 | C3_plan | 4 | 25% | 25% | 25% | +0 pp | $0.0357 |
| Sonnet 5.5 | C4_stats | 4 | 25% | 25% | 25% | +0 pp | $0.0456 |
| Opus 5.5 | C1_query | 4 | 25% | 25% | 25% | +0 pp | $0.0837 |
| Opus 5.5 | C2_schema | 4 | 25% | 25% | 25% | +0 pp | $0.0926 |
| Opus 5.5 | C3_plan | 4 | 25% | 25% | 25% | +0 pp | $0.0986 |
| Opus 5.5 | C4_stats | 4 | 25% | 25% | 25% | +0 pp | $0.1214 |

pp = procentpunt. Het criterium voor 'dit model heeft geen herhalingen nodig' hoort vooraf te zijn vastgelegd, bijvoorbeeld een winst van minder dan 10 procentpunt. Met 4 query's en 3 antwoorden per query is een verschil klein ten opzichte van de onzekerheid.

## 4. Per query, limiet 16000 (beide condities samen): ACCEPTED van n, mediaan speedup bij ACCEPTED

| Model | audit_log_page | revenue_orders | top_customers | top_products |
|---|---|---|---|---|
| Haiku 5.5 | 0/12 | 0/12 | 11/12 (157x) | 0/12 |
| Sonnet 5.5 | 0/12 | 0/12 | 6/12 (174x) | 0/12 |
| Opus 5.5 | 0/12 | 0/12 | 12/12 (204x) | 0/12 |

## 5. Afkappen en tokenverbruik per model en limiet

| Model | Limiet | n | afgekapt | Uitvoertokens mediaan | p90 | max |
|---|---|---|---|---|---|---|
| Haiku 5.5 | 16000 | 48 | 0 (0%) | 1627 | 3436 | 5652 |
| Sonnet 5.5 | 16000 | 48 | 0 (0%) | 646 | 971 | 1045 |
| Opus 5.5 | 16000 | 48 | 0 (0%) | 1060 | 2063 | 2403 |

Uitvoertokens bevatten ook de denktokens. Een antwoord dat bij een lage limiet wordt afgekapt, is geen fout van het model maar een gevolg van de limiet; het telt hier als 'afgekapt' en niet als 'fout'.

## Methode en kanttekeningen

- Kosten zijn berekend uit de gemeten tokens en de prijstabel in `llm/prices.py` (dollar per miljoen tokens). Denktokens worden als uitvoer gerekend. Gerapporteerde kosten van de aanbieder staan, voor zover beschikbaar, in `per_poging.csv`.
- ACCEPTED hangt af van tijdmetingen op een laptop met een kleine database; dezelfde herschrijving kan elders anders uitvallen.
- Verschillen tussen modellen zijn pas aantoonbaar als de intervallen niet overlappen; bij kleine aantallen is dat zelden zo.
