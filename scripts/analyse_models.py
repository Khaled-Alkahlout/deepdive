"""Analyseer het modelvergelijkingsexperiment (scripts/run_experiment.py): prestatie en kosten per model, outputlimiet,
context en aantal herhalingen.

Gebruik:
  python scripts/analyse_models.py                      # experiment 'modelvergelijking'
  python scripts/analyse_models.py --name mijnnaam

Het script leest alleen results/experiment-<naam>/ (geen database, geen sleutel nodig) en schrijft naar
results/experiment-<naam>/analyse/:
  samenvatting.md        leesbaar verslag met tabellen (Nederlands)
  per_groep.csv          per model, limiet en conditie: uitkomsten, kosten, tijd
  passk.csv              kans op minstens een ACCEPTED-antwoord bij 1, 2 of 3 pogingen, met de kosten van die pogingen
  per_query.csv          per model, limiet, conditie en query
  per_poging.csv         een regel per antwoord (zonder SQL), voor eigen grafieken

Definities
  ACCEPTED       resultaat gelijk op alle parametersets en minstens 1,2x sneller (zie validator/timing.py)
  fout           resultaat verschilt van het origineel of geen geldige SELECT
  gelijk, trager gelijk resultaat, maar minder dan 1/1,2 van de snelheid van het origineel
  ongewijzigd    het model gaf het origineel terug (na het weghalen van commentaar en witruimte)
  afgekapt       de tokenlimiet was bereikt voor er een volledig SQL-blok stond
  api-fout       de aanroep is na herhaalde pogingen mislukt; telt niet mee in n
  pass@k         schatting van de kans dat minstens een van k pogingen ACCEPTED is, uit de n opgenomen pogingen
                 per query en conditie: 1 - C(n-c, k) / C(n, k), met c het aantal ACCEPTED (Chen e.a., 2021),
                 gemiddeld over de query's. Het is een schatting uit weinig data, geen vaste eigenschap van het model.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from math import comb
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm.prices import LABELS, ORDER, cost_usd, family  # noqa: E402
from scripts.analyse import ORIGINALS, classify, norm_sql, pct  # noqa: E402

CATS = ["ACCEPTED", "fout", "gelijk, trager", "gelijk, geen winst", "ongewijzigd", "afgekapt", "api-fout"]


def categorize(row: dict) -> str:
    """
    Assign the outcome category of one attempt, including the categories of this experiment.

    Parameters
    ----------
    row : dict
        Attempt with the keys "verdict", "unchanged_norm" and "speedup".

    Returns
    -------
    str
        One of CATS.
    """
    if row["verdict"] == "API_ERROR":
        return "api-fout"
    if row["verdict"] == "TRUNCATED":
        return "afgekapt"
    return classify(row)


def load(exp_dir: Path) -> tuple[list[dict], list[str]]:
    """
    Read all finished runs of the experiment.

    Parameters
    ----------
    exp_dir : Path
        Folder ``results/experiment-<name>``.

    Returns
    -------
    tuple of (list of dict, list of str)
        One dict per attempt, and warnings about folders that were skipped.
    """
    rows, warn = [], []
    for d in sorted(p for p in exp_dir.iterdir() if p.is_dir() and p.name != "analyse"):
        if not (d / "meta.json").exists() or not (d / "llm-results.csv").exists():
            warn.append(f"overgeslagen (onvolledig): {d.name}")
            continue
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        for r in csv.DictReader(open(d / "llm-results.csv", encoding="utf-8")):
            tag = f"{r['case']}__{r['condition']}__r{r['rep']}"
            resp = json.loads((d / "responses" / f"{tag}.json").read_text(encoding="utf-8"))
            sql = resp.get("sql", "")
            tin, tout = int(float(r.get("input_tokens") or 0)), int(float(r.get("output_tokens") or 0))
            row = {
                "run": d.name, "model": meta["model"], "family": family(meta["model"]), "limit": int(meta["max_tokens"]),
                "effort": meta.get("effort") or "standaard", "case": r["case"], "condition": r["condition"],
                "rep": int(r["rep"]), "verdict": r["verdict"],
                "speedup": float(r["speedup"]) if r.get("speedup") else None,
                "input_tokens": tin, "output_tokens": tout, "llm_seconds": float(r.get("llm_seconds") or 0),
                "stop_reason": r.get("stop_reason", ""),
                "cost_reported": float(r["cost_reported"]) if r.get("cost_reported") else None,
                "unchanged_norm": bool(sql) and norm_sql(sql) == norm_sql(ORIGINALS[r["case"]]),
            }
            row["cost_usd"] = cost_usd(meta["model"], tin, tout)
            row["category"] = categorize(row)
            rows.append(row)
    return rows, warn


def passk(n: int, c: int, k: int) -> float:
    """
    Unbiased estimate of the chance that at least one of k attempts succeeds.

    Parameters
    ----------
    n : int
        Number of attempts that were made.
    c : int
        Number of successful attempts among them.
    k : int
        Number of attempts of the question (k <= n).

    Returns
    -------
    float
        ``1 - C(n - c, k) / C(n, k)``.
    """
    return 1.0 - comb(n - c, k) / comb(n, k)


def group(rows: list[dict], *keys: str) -> dict:
    """
    Group rows by the values of the given keys.

    Parameters
    ----------
    rows : list of dict
        Attempts.
    *keys : str
        Row keys to group by.

    Returns
    -------
    dict
        Mapping from a tuple of key values to the list of rows.
    """
    out = defaultdict(list)
    for r in rows:
        out[tuple(r[k] for k in keys)].append(r)
    return out


def order_key(k: tuple) -> tuple:
    """
    Sort key for group keys that start with the model family and then the limit (descending).

    Parameters
    ----------
    k : tuple
        Group key (family, limit, ...).

    Returns
    -------
    tuple
        Sort key: family order, limit descending, rest.
    """
    fam = ORDER.index(k[0]) if k[0] in ORDER else 99
    return (fam, -k[1] if isinstance(k[1], int) else 0, *k[2:])


def stats(rs: list[dict]) -> dict:
    """
    Summarise a group of attempts.

    Parameters
    ----------
    rs : list of dict
        Attempts of one group.

    Returns
    -------
    dict
        Counts per category, n (without API errors), cost, time and speedup statistics.
    """
    valid = [r for r in rs if r["category"] != "api-fout"]
    cnt = {c: sum(r["category"] == c for r in rs) for c in CATS}
    costs = [r["cost_usd"] for r in valid if r["cost_usd"] is not None]
    acc = [r["speedup"] for r in valid if r["category"] == "ACCEPTED" and r["speedup"]]
    return {"n": len(valid), **cnt, "cost_mean": mean(costs) if costs else None, "cost_total": sum(costs) if costs else None,
            "cost_per_accepted": (sum(costs) / cnt["ACCEPTED"]) if costs and cnt["ACCEPTED"] else None,
            "sec_mean": mean(r["llm_seconds"] for r in valid) if valid else None,
            "speedup_median_acc": median(acc) if acc else None,
            "out_tokens_median": median(r["output_tokens"] for r in valid) if valid else None,
            "out_tokens_p90": sorted(r["output_tokens"] for r in valid)[int(0.9 * (len(valid) - 1))] if valid else None,
            "out_tokens_max": max(r["output_tokens"] for r in valid) if valid else None}


def pass_table(rows: list[dict]) -> list[dict]:
    """
    Compute pass@k per model, limit and condition, averaged over the queries.

    Parameters
    ----------
    rows : list of dict
        Attempts.

    Returns
    -------
    list of dict
        One dict per group and k, with the cost of k attempts and the gain over one attempt.
    """
    out = []
    for key, rs in sorted(group(rows, "family", "limit", "condition").items(), key=lambda kv: order_key(kv[0])):
        cells = group([r for r in rs if r["category"] != "api-fout"], "case")
        kmax = min((len(v) for v in cells.values()), default=0)
        costs = [r["cost_usd"] for r in rs if r["cost_usd"] is not None and r["category"] != "api-fout"]
        for k in range(1, kmax + 1):
            vals = [passk(len(v), sum(x["category"] == "ACCEPTED" for x in v), k) for v in cells.values()]
            out.append({"family": key[0], "limit": key[1], "condition": key[2], "k": k, "n_queries": len(cells),
                        "pass_at_k": mean(vals), "cost_of_k_attempts": k * mean(costs) if costs else None})
    for r in out:
        base = next(x for x in out if (x["family"], x["limit"], x["condition"], x["k"]) == (r["family"], r["limit"], r["condition"], 1))
        r["gain_vs_k1_pp"] = 100 * (r["pass_at_k"] - base["pass_at_k"])
    return out


def fmt(x, nd=3, pre="") -> str:
    """
    Format a number for a table cell; None becomes a dash.

    Parameters
    ----------
    x : float or None
        Value.
    nd : int, default 3
        Decimals.
    pre : str, default ""
        Prefix such as "$".

    Returns
    -------
    str
        Text for the cell.
    """
    return "-" if x is None else f"{pre}{x:.{nd}f}"


def md(headers: list[str], rows: list[list]) -> str:
    """
    Render a markdown table.

    Parameters
    ----------
    headers : list of str
        Column headers.
    rows : list of list
        Rows of cells (converted with str).

    Returns
    -------
    str
        Markdown table.
    """
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict]) -> None:
    """
    Write dicts to a CSV file with the union of their keys as columns.

    Parameters
    ----------
    path : Path
        Output file.
    rows : list of dict
        Rows to write.

    Returns
    -------
    None
    """
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main():
    """
    Analyse the experiment and write the tables to ``results/experiment-<name>/analyse/``.

    Returns
    -------
    None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="modelvergelijking")
    args = ap.parse_args()
    exp_dir = ROOT / "results" / f"experiment-{args.name}"
    if not exp_dir.exists():
        sys.exit(f"Map niet gevonden: {exp_dir}")
    rows, warn = load(exp_dir)
    if not rows:
        sys.exit("Geen voltooide runs gevonden. Draai eerst scripts/run_experiment.py.")
    out = exp_dir / "analyse"
    out.mkdir(exist_ok=True)
    settings = json.loads((exp_dir / "experiment.json").read_text(encoding="utf-8")) if (exp_dir / "experiment.json").exists() else {}
    fams = sorted({r["family"] for r in rows}, key=lambda f: ORDER.index(f) if f in ORDER else 99)
    limits = sorted({r["limit"] for r in rows}, reverse=True)
    conds = sorted({r["condition"] for r in rows})
    top = limits[0]
    lab = lambda f: LABELS.get(f, f)

    # --- CSV's ---
    per_groep, per_query = [], []
    for key, rs in sorted(group(rows, "family", "limit", "condition").items(), key=lambda kv: order_key(kv[0])):
        per_groep.append({"family": key[0], "limit": key[1], "condition": key[2], **stats(rs)})
    for key, rs in sorted(group(rows, "family", "limit", "condition", "case").items(), key=lambda kv: order_key(kv[0])):
        per_query.append({"family": key[0], "limit": key[1], "condition": key[2], "case": key[3], **stats(rs)})
    pk = pass_table(rows)
    write_csv(out / "per_groep.csv", per_groep)
    write_csv(out / "per_query.csv", per_query)
    write_csv(out / "passk.csv", pk)
    write_csv(out / "per_poging.csv", [{k: v for k, v in r.items() if k != "unchanged_norm"} | {"unchanged": r["unchanged_norm"]} for r in rows])

    # --- verslag ---
    L = []
    L.append(f"# Modelvergelijking: resultaten van experiment '{args.name}'\n")
    L.append(f"Aanbieder: {settings.get('provider', '?')}. Effort: {settings.get('effort', rows[0]['effort'])} voor alle modellen. "
             f"Query's: {', '.join(settings.get('cases', sorted({r['case'] for r in rows})))}. "
             f"Condities: {', '.join(conds)}. Herhalingen per query en conditie: {settings.get('reps', '?')}. "
             f"Totaal {len(rows)} antwoorden, tokenkosten ${sum(r['cost_usd'] or 0 for r in rows):.2f}.\n")
    L.append("Lees dit als een kleine steekproef: per model en limiet zijn er hooguit "
             f"{max(len(v) for v in group(rows, 'family', 'limit').values())} antwoorden en slechts een of enkele query's "
             "laten een ACCEPTED-antwoord toe. Tussen haakjes staat het exacte 95%-interval.\n")
    if warn:
        L.append("Waarschuwingen: " + "; ".join(warn) + "\n")

    L.append("## 1. Prestatie en kosten per model en outputlimiet (beide condities samen)\n")
    rowsT = []
    for f in fams:
        for lim in limits:
            rs = [r for r in rows if r["family"] == f and r["limit"] == lim]
            if not rs:
                continue
            s = stats(rs)
            rowsT.append([lab(f), lim, s["n"], pct(s["ACCEPTED"], s["n"]) if s["n"] else "-", s["fout"], s["gelijk, trager"],
                          s["ongewijzigd"], s["afgekapt"], s["api-fout"], fmt(s["cost_mean"], 4, "$"), fmt(s["cost_total"], 2, "$"),
                          fmt(s["cost_per_accepted"], 3, "$"), fmt(s["sec_mean"], 1)])
    L.append(md(["Model", "Limiet", "n", "ACCEPTED", "fout", "gelijk, trager", "ongewijzigd", "afgekapt", "api-fout",
                 "Kosten per antwoord", "Kosten totaal", "Kosten per ACCEPTED", "Seconden per antwoord"], rowsT))

    L.append(f"\n## 2. Context: alleen de query (C1) tegenover alles (C4), limiet {top}\n")
    rowsT = []
    for f in fams:
        for c in conds:
            rs = [r for r in rows if r["family"] == f and r["limit"] == top and r["condition"] == c]
            if rs:
                s = stats(rs)
                rowsT.append([lab(f), c, s["n"], pct(s["ACCEPTED"], s["n"]), s["fout"], s["gelijk, trager"], s["ongewijzigd"],
                              fmt(s["cost_mean"], 4, "$"), fmt(s["cost_per_accepted"], 3, "$"), fmt(s["speedup_median_acc"], 1)])
    L.append(md(["Model", "Conditie", "n", "ACCEPTED", "fout", "gelijk, trager", "ongewijzigd", "Kosten per antwoord",
                 "Kosten per ACCEPTED", "Mediaan speedup (ACCEPTED)"], rowsT))

    L.append(f"\n## 3. Herhalen: kans op minstens een ACCEPTED-antwoord bij 1, 2 of 3 pogingen (pass@k), limiet {top}\n")
    rowsT = []
    for f in fams:
        for c in conds:
            g = [x for x in pk if x["family"] == f and x["limit"] == top and x["condition"] == c]
            if g:
                p = {x["k"]: x for x in g}
                cell = lambda k: f"{100 * p[k]['pass_at_k']:.0f}%" if k in p else "-"
                rowsT.append([lab(f), c, p[1]["n_queries"], cell(1), cell(2), cell(3),
                              f"{p[max(p)]['gain_vs_k1_pp']:+.0f} pp", fmt(p[max(p)]["cost_of_k_attempts"], 4, "$")])
    L.append(md(["Model", "Conditie", "Query's", "pass@1", "pass@2", "pass@3", "Winst k=1 naar max k", "Kosten van max k pogingen"], rowsT))
    L.append("\npp = procentpunt. Het criterium voor 'dit model heeft geen herhalingen nodig' hoort vooraf te zijn vastgelegd, "
             "bijvoorbeeld een winst van minder dan 10 procentpunt. Met 4 query's en 3 antwoorden per query is een verschil "
             "klein ten opzichte van de onzekerheid.\n")

    L.append(f"## 4. Per query, limiet {top} (beide condities samen): ACCEPTED van n, mediaan speedup bij ACCEPTED\n")
    cases = sorted({r["case"] for r in rows})
    rowsT = []
    for f in fams:
        cells = [lab(f)]
        for cs in cases:
            rs = [r for r in rows if r["family"] == f and r["limit"] == top and r["case"] == cs]
            s = stats(rs) if rs else None
            cells.append("-" if not s else f"{s['ACCEPTED']}/{s['n']}" + (f" ({s['speedup_median_acc']:.0f}x)" if s["speedup_median_acc"] else ""))
        rowsT.append(cells)
    L.append(md(["Model"] + cases, rowsT))

    L.append("\n## 5. Afkappen en tokenverbruik per model en limiet\n")
    rowsT = []
    for f in fams:
        for lim in limits:
            rs = [r for r in rows if r["family"] == f and r["limit"] == lim]
            if rs:
                s = stats(rs)
                rowsT.append([lab(f), lim, s["n"], f"{s['afgekapt']} ({100 * s['afgekapt'] / s['n']:.0f}%)" if s["n"] else "-",
                              fmt(s["out_tokens_median"], 0), fmt(s["out_tokens_p90"], 0), fmt(s["out_tokens_max"], 0)])
    L.append(md(["Model", "Limiet", "n", "afgekapt", "Uitvoertokens mediaan", "p90", "max"], rowsT))
    L.append("\nUitvoertokens bevatten ook de denktokens. Een antwoord dat bij een lage limiet wordt afgekapt, is geen "
             "fout van het model maar een gevolg van de limiet; het telt hier als 'afgekapt' en niet als 'fout'.\n")

    L.append("## Methode en kanttekeningen\n")
    L.append("- Kosten zijn berekend uit de gemeten tokens en de prijstabel in `llm/prices.py` (dollar per miljoen tokens). "
             "Denktokens worden als uitvoer gerekend. Gerapporteerde kosten van de aanbieder staan, voor zover beschikbaar, in `per_poging.csv`.")
    L.append("- ACCEPTED hangt af van tijdmetingen op een laptop met een kleine database; dezelfde herschrijving kan elders anders uitvallen.")
    L.append("- Verschillen tussen modellen zijn pas aantoonbaar als de intervallen niet overlappen; bij kleine aantallen is dat zelden zo.")
    (out / "samenvatting.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print("\nOpgeslagen in", out)


if __name__ == "__main__":
    main()
