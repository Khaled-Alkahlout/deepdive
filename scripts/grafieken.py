"""Maak presentatiegrafieken van de experimentresultaten (matplotlib).

Leest ``results/experiment-modellen-*/resultaten.csv`` en schrijft naar
``results/grafieken/``:

* vijf grafieken als PNG (2400x1350, voor PowerPoint) en SVG (schaalbaar);
* ``overzicht.html`` met alle grafieken, een tabel per grafiek en de kanttekeningen.

Examples
--------
>>> # vanuit de projectmap
>>> # python scripts/grafieken.py
>>> # python scripts/grafieken.py --invoer "results/experiment-*/resultaten.csv"
"""

from __future__ import annotations

import argparse
import base64
import csv
import glob
import io
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # geen scherm nodig
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402
from matplotlib.cm import ScalarMappable  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, NullFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- opmaak
SURFACE = "#ffffff"
INK = "#14161a"
INK2 = "#4b5058"
MUTED = "#7b808a"
GRID = "#e6e8ec"

# Vaste kleur per model (nooit per rang)
MODEL_KLEUR = {"haiku": "#2a78d6", "sonnet": "#eb6834", "opus": "#1baf7a", "fable": "#eda100"}
MODEL_NAAM = {"haiku": "Haiku 5.5", "sonnet": "Sonnet 5.5", "opus": "Opus 5.5", "fable": "Fable 5.1"}
MODEL_VOLGORDE = ["haiku", "sonnet", "opus", "fable"]
EFFORT_VOLGORDE = ["low", "medium", "high", "xhigh", "max"]

# Sequentieel (één tint, licht -> donker) voor 'aandeel goed'
CMAP = LinearSegmentedColormap.from_list("aandeel", ["#eef4fc", "#9bbbe6", "#154ea0"])

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "Inter", "Helvetica Neue", "Arial", "DejaVu Sans"],
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK2,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "svg.fonttype": "none",
        "text.parse_math": False,  # '$' in bedragen is geen wiskunde
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
    }
)


# ---------------------------------------------------------------- data
@dataclass
class Antwoord:
    """Eén antwoord van een model op één query."""

    query: str
    context: str  # "C1".."C4"
    context_naam: str
    model: str  # familie: haiku/sonnet/opus/fable
    effort: str
    goed: bool
    uit: int
    inn: int
    kosten: float


def _getal(tekst: str) -> float:
    """Zet een getal met decimale komma om naar float (leeg -> 0)."""
    tekst = (tekst or "").strip().replace(",", ".")
    return float(tekst) if tekst else 0.0


def laad(patronen: list[str]) -> list[Antwoord]:
    """Lees alle resultaat-CSV's die bij de patronen passen.

    Parameters
    ----------
    patronen : list of str
        Glob-patronen (absoluut of relatief aan de projectmap).

    Returns
    -------
    list of Antwoord
        Alle antwoorden uit alle gevonden bestanden.
    """
    bestanden: list[str] = []
    for patroon in patronen:
        p = patroon if Path(patroon).is_absolute() else str(ROOT / patroon)
        bestanden += sorted(glob.glob(p))
    if not bestanden:
        sys.exit(f"Geen resultaatbestanden gevonden voor: {patronen}")
    antwoorden: list[Antwoord] = []
    for pad in bestanden:
        with open(pad, encoding="utf-8-sig", newline="") as f:
            for rij in csv.DictReader(f, delimiter=";"):
                fam = re.search(r"(haiku|sonnet|opus|fable)", rij["model"].lower())
                if not fam:
                    continue
                antwoorden.append(
                    Antwoord(
                        query=rij["query"],
                        context=rij["context"].split()[0],
                        context_naam=rij["context"],
                        model=fam.group(1),
                        effort=rij["effort"],
                        goed=rij["oordeel"].upper().startswith("GOED"),
                        uit=int(_getal(rij["uitvoertokens"])),
                        inn=int(_getal(rij["invoertokens"])),
                        kosten=_getal(rij["kosten_usd"]),
                    )
                )
    print(f"{len(antwoorden)} antwoorden uit {len(bestanden)} bestand(en) gelezen.")
    return antwoorden


# ---------------------------------------------------------------- hulpfuncties
def usd(v: float) -> str:
    """Dollarbedrag met Nederlandse komma en passend aantal decimalen."""
    if v == 0:
        return "$0"
    s = f"{v:.2f}" if v >= 0.1 else f"{v:.3f}" if v >= 0.01 else f"{v:.4f}"
    return "$" + s.replace(".", ",")


def getal(n: float) -> str:
    """Geheel getal met punt als duizendtalscheiding."""
    return f"{round(n):,}".replace(",", ".")


def percentiel(waarden: list[float], p: float) -> float:
    """Lineair geïnterpoleerd percentiel (p tussen 0 en 100)."""
    s = sorted(waarden)
    if not s:
        return 0.0
    k = (len(s) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def nette_ticks(vmax: float, n: int = 5) -> list[float]:
    """Mooie assen-ticks van 0 tot net boven vmax."""
    ruw = vmax / n
    mag = 10 ** math.floor(math.log10(ruw))
    stap = next(m * mag for m in (1, 2, 2.5, 5, 10) if ruw <= m * mag)
    aantal = math.ceil(vmax / stap - 1e-9)
    return [round(i * stap, 10) for i in range(aantal + 1)]


def som(rijen: list[Antwoord]) -> tuple[int, int]:
    """Aantal goede antwoorden en totaal aantal."""
    return sum(a.goed for a in rijen), len(rijen)


def nieuwe_figuur(titel: str, ondertitel: list[str], noten: list[str]):
    """Maak een 16:9-figuur met titel, ondertitel en voetnoten."""
    fig = plt.figure(figsize=(16, 9))
    fig.text(0.03, 0.955, titel, fontsize=27, fontweight="bold", color=INK, va="top")
    for i, regel in enumerate(ondertitel):
        fig.text(0.03, 0.895 - 0.033 * i, regel, fontsize=15, color=INK2, va="top")
    for i, regel in enumerate(noten):
        fig.text(0.03, 0.022 + 0.03 * (len(noten) - 1 - i), regel, fontsize=11.5, color=MUTED, va="bottom")
    return fig


def cel(ax, x, y, g, n, fontsize=22, vet=True):
    """Teken één heatmapcel met 'g/n' erin."""
    f = g / n if n else 0
    ax.add_patch(Rectangle((x, y), 1, 1, facecolor=CMAP(f), edgecolor=SURFACE, linewidth=5))
    ax.text(
        x + 0.5, y + 0.5, f"{g}/{n}", ha="center", va="center", fontsize=fontsize,
        fontweight="bold" if vet else "normal", color="white" if f > 0.55 else INK,
    )


def kleurschaal(fig, rect):
    """Kleine horizontale kleurschaal 0-100% goed."""
    cax = fig.add_axes(rect)
    cb = fig.colorbar(ScalarMappable(Normalize(0, 1), CMAP), cax=cax, orientation="horizontal")
    cb.set_ticks([0, 1])
    cb.set_ticklabels(["0% goed", "100% goed"])
    cb.outline.set_visible(False)
    cax.tick_params(length=0, labelsize=11, colors=INK2)


def als_png(fig) -> bytes:
    """Render een figuur naar PNG-bytes."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=SURFACE)
    return buf.getvalue()


# ---------------------------------------------------------------- grafiek 1: query x context
def grafiek_query_context(data: list[Antwoord]):
    """Heatmap: welke query wordt met welke context opgelost."""
    contexten = sorted({a.context for a in data})
    naam = {a.context: a.context_naam for a in data}
    queries = sorted({a.query for a in data})
    per = defaultdict(list)
    for a in data:
        per[(a.query, a.context)].append(a)
    totaal_q = {q: som([a for a in data if a.query == q]) for q in queries}
    queries.sort(key=lambda q: (-totaal_q[q][0], q))
    inv = {c: sum(a.inn for a in data if a.context == c) / max(1, sum(a.context == c for a in data)) for c in contexten}

    gt, nt = som(data)
    opgelost = [q for q in queries if totaal_q[q][0] > 0]
    nper = len(per[(queries[0], contexten[0])])
    titel = (
        f"Alleen {opgelost[0]} wordt opgelost: {gt} van {nt} antwoorden goed"
        if len(opgelost) == 1
        else f"{len(opgelost)} van {len(queries)} queries worden opgelost: {gt} van {nt} antwoorden goed"
    )
    fig = nieuwe_figuur(
        titel,
        [
            f"Aantal goede antwoorden per query en contextniveau, alle modellen en efforts samen ({nper} antwoorden per cel).",
            "Goed = zelfde resultaat én minstens 1,2x sneller dan de originele query.",
        ],
        [
            "De contexten zijn cumulatief: C2 = C1 + schema, C3 = C2 + uitvoeringsplan, C4 = C3 + statistieken.",
            "Bron: results/experiment-modellen-*/resultaten.csv. Eén experiment, vier queries: de andere drie queries zijn dus niet onderscheidend.",
        ],
    )
    ax = fig.add_axes([0.2, 0.17, 0.62, 0.5])
    ax.set_xlim(0, len(contexten))
    ax.set_ylim(len(queries), 0)
    ax.axis("off")
    tabel = []
    for j, c in enumerate(contexten):
        ax.text(j + 0.5, -0.38, naam[c], ha="center", va="bottom", fontsize=17, fontweight="bold", color=INK)
        ax.text(j + 0.5, -0.12, f"gem. {getal(inv[c])} invoertokens", ha="center", va="bottom", fontsize=11.5, color=MUTED)
    ax.text(len(contexten) + 0.5, -0.12, "Totaal", ha="center", va="bottom", fontsize=17, fontweight="bold", color=INK)
    for i, q in enumerate(queries):
        ax.text(-0.06, i + 0.5, q, ha="right", va="center", fontsize=17, fontweight="bold", color=INK)
        rij = [q]
        for j, c in enumerate(contexten):
            g, n = som(per[(q, c)])
            cel(ax, j, i, g, n, 26)
            rij.append(f"{g}/{n}")
        g, n = totaal_q[q]
        ax.text(len(contexten) + 0.5, i + 0.5, f"{g}/{n}", ha="center", va="center", fontsize=20, fontweight="bold", color=INK)
        rij.append(f"{g}/{n}")
        tabel.append(rij)
    kleurschaal(fig, [0.2, 0.135, 0.2, 0.014])
    return "1-queries-per-context", fig, ["query"] + [naam[c] for c in contexten] + ["totaal"], tabel


# ---------------------------------------------------------------- grafiek 2: model x effort x context
def grafiek_model_effort(data: list[Antwoord]):
    """Heatmap: per model, effort en context hoeveel van de herhalingen goed zijn."""
    contexten = sorted({a.context for a in data})
    naam = {a.context: a.context_naam for a in data}
    goed_per_q = defaultdict(int)
    for a in data:
        goed_per_q[a.query] += a.goed
    focus = max(goed_per_q, key=lambda q: (goed_per_q[q], q))
    d = [a for a in data if a.query == focus]
    modellen = [m for m in MODEL_VOLGORDE if any(a.model == m for a in d)]
    efforts = [e for e in EFFORT_VOLGORDE if any(a.effort == e for a in d)]
    cellen = defaultdict(list)
    for a in d:
        cellen[(a.model, a.effort, a.context)].append(a)
    per_cel = max(len(v) for v in cellen.values())
    top, rest = efforts[-1], efforts[:-1]
    rest_rijen = {c: [a for a in d if a.context == c and a.effort in rest] for c in contexten}
    top_rijen = {c: [a for a in d if a.context == c and a.effort == top] for c in contexten}

    base, rijk = contexten[0], contexten[2:]
    a1, n1 = som(rest_rijen[base])
    a2 = sum(som(rest_rijen[c])[0] for c in rijk)
    n2 = sum(som(rest_rijen[c])[1] for c in rijk)
    e1 = sum(som(top_rijen[c])[0] for c in contexten)
    f1 = sum(som(top_rijen[c])[1] for c in contexten)
    fig = nieuwe_figuur(
        f"Bij {'/'.join(rest)} effort: {base} {a1}/{n1} goed, {'+'.join(rijk)} {a2}/{n2} goed",
        [
            f"Query {focus}: aantal goede antwoorden per model, effort en context ({per_cel} herhalingen per cel).",
            f"Bij {top} effort is {e1} van {f1} antwoorden goed, in elke context.",
        ],
        [
            f"Eerlijk: n = {per_cel} per cel is klein; de samengevoegde rijen onderaan zijn het betrouwbaarst. Alleen query {focus} is onderscheidend.",
            "Een verschil van één antwoord (1/3) is ruis: dezelfde cel kan bij een herhaalde run anders uitvallen.",
        ],
    )
    # rijen met y-posities (groepen en samenvatting krijgen extra ruimte)
    rijen, y = [], 0.0
    for m in modellen:
        for e in efforts:
            rijen.append((y, f"{e}", MODEL_KLEUR[m], m, {c: cellen[(m, e, c)] for c in contexten}, False))
            y += 1
        y += 0.3
    y += 0.3
    rijen.append((y, f"{' + '.join(rest)}", None, None, rest_rijen, True))
    rijen.append((y + 1, f"{top}", None, None, top_rijen, True))
    ymax = y + 2

    ax = fig.add_axes([0.25, 0.115, 0.6, 0.625])
    ax.set_xlim(0, len(contexten))
    ax.set_ylim(ymax, 0)
    ax.axis("off")
    for j, c in enumerate(contexten):
        ax.text(j + 0.5, -0.55, naam[c], ha="center", va="bottom", fontsize=15, fontweight="bold", color=INK)
        inv = [a.inn for a in d if a.context == c]
        ax.text(j + 0.5, -0.12, f"gem. {getal(sum(inv) / len(inv))} invoertokens", ha="center", va="bottom", fontsize=10.5, color=MUTED)
    tabel = []
    for y, e, kleur, m, per_ctx, samen in rijen:
        label = f"{MODEL_NAAM[m]} · {e}" if m else f"Alle modellen · {e}"
        if m:
            ax.add_patch(Rectangle((-0.96, y + 0.3), 0.06, 0.4, facecolor=kleur, edgecolor="none", clip_on=False))
        ax.text(-0.06 if not m else -0.06, y + 0.5, label, ha="right", va="center", fontsize=13.5,
                fontweight="bold" if samen else "normal", color=INK)
        out = [label]
        for j, c in enumerate(contexten):
            g, n = som(per_ctx[c])
            cel(ax, j, y, g, n, 16, vet=samen)
            out.append(f"{g}/{n}")
        tabel.append(out)
    return "2-model-effort-context", fig, ["model · effort"] + [naam[c] for c in contexten], tabel


# ---------------------------------------------------------------- grafiek 3: tokens vs kosten
def _legenda_modellen(ax, modellen, extra=None):
    """Legenda boven de grafiek: modellen (gekleurd) plus optionele extra items."""
    h = [Line2D([], [], marker="o", linestyle="", markersize=10, color=MODEL_KLEUR[m], label=MODEL_NAAM[m]) for m in modellen]
    ax.legend(
        handles=h + (extra or []), loc="lower left", bbox_to_anchor=(0, 1.02), ncol=8, frameon=False,
        fontsize=13, labelcolor=INK, handletextpad=0.3, columnspacing=1.6,
    )


def grafiek_tokens_kosten(data: list[Antwoord]):
    """Scatter: output tokens tegen kosten per antwoord, gevuld = opgelost."""
    modellen = [m for m in MODEL_VOLGORDE if any(a.model == m for a in data)]
    gt, nt = som(data)
    goede_q = sorted({a.query for a in data if a.goed})
    med = {m: percentiel([a.kosten for a in data if a.model == m and a.goed], 50) for m in modellen if any(a.model == m and a.goed for a in data)}
    delen = " · ".join(f"{MODEL_NAAM[m].split()[0]} {usd(v)}" for m, v in med.items())
    fig = nieuwe_figuur(
        f"Een goed antwoord kost (mediaan): {delen}",
        [f"Elk punt is één antwoord (n = {nt}); {gt} antwoorden zijn goed (gevuld), de rest is niet opgelost (open)."],
        [
            f"Alle goede antwoorden zijn van query {', '.join(goede_q)}; open punten bij andere queries zijn kosten zonder resultaat.",
            "Kosten zijn berekend uit tokens × prijs per miljoen tokens (llm/prices.py), niet uit de factuur. Tokens bevatten ook denkwerk.",
        ],
    )
    ax = fig.add_axes([0.085, 0.17, 0.89, 0.61])
    ax.set_xscale("log")
    ax.set_yscale("log")
    for goed in (False, True):
        for m in modellen:
            punten = [a for a in data if a.model == m and a.goed == goed]
            if not punten:
                continue
            xs, ys = [max(a.uit, 1) for a in punten], [max(a.kosten, 1e-6) for a in punten]
            if goed:
                ax.scatter(xs, ys, s=70, color=MODEL_KLEUR[m], edgecolor="white", linewidth=1.2, zorder=4)
            else:
                ax.scatter(xs, ys, s=55, facecolor="none", edgecolor=MODEL_KLEUR[m], linewidth=1.4, alpha=0.75, zorder=3)
    tabel = []
    for m in modellen:
        goed = [a for a in data if a.model == m and a.goed]
        allen = [a for a in data if a.model == m]
        if goed:
            mu, mk = percentiel([a.uit for a in goed], 50), percentiel([a.kosten for a in goed], 50)
            ax.scatter([mu], [mk], marker="D", s=150, color=MODEL_KLEUR[m], edgecolor=INK, linewidth=2, zorder=6)
            ax.annotate(
                f"{MODEL_NAAM[m]}\nmediaan goed: {usd(mk)}", (mu, mk), xytext=(0, -44 if m == "sonnet" else 26), textcoords="offset points",
                ha="center", fontsize=12, fontweight="bold", color=INK, zorder=7,
                path_effects=[pe.withStroke(linewidth=4, foreground="white")],
            )
            tabel.append([MODEL_NAAM[m], f"{len(goed)}/{len(allen)}", getal(mu), usd(mk)])
        else:
            tabel.append([MODEL_NAAM[m], f"0/{len(allen)}", "-", "-"])
    xt = [200, 300, 500, 1000, 2000, 3000, 5000, 10000]
    yt = [0.0002, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2]
    ax.set_xticks(xt)
    ax.set_yticks(yt)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: getal(v)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: usd(v)))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.minorticks_off()
    ax.set_xlim(240, 11000)
    ax.set_ylim(0.00025, 0.15)
    ax.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=12, length=0)
    ax.set_xlabel("Output tokens per antwoord (log-schaal, inclusief denktokens)", fontsize=14, labelpad=10)
    ax.set_ylabel("Kosten per antwoord (USD, log-schaal)", fontsize=14, labelpad=10)
    extra = [
        Line2D([], [], marker="o", linestyle="", markersize=9, color=INK2, label="goed"),
        Line2D([], [], marker="o", linestyle="", markersize=9, markerfacecolor="none", markeredgecolor=INK2, label="niet opgelost"),
        Line2D([], [], marker="D", linestyle="", markersize=9, markerfacecolor=INK2, markeredgecolor=INK, label="mediaan van de goede"),
    ]
    _legenda_modellen(ax, modellen, extra)
    return "3-tokens-en-kosten", fig, ["model", "goed", "mediaan output tokens (goed)", "mediaan kosten (goed)"], tabel


# ---------------------------------------------------------------- gegroepeerde staafgrafiek
def staven(fig, efforts, modellen, waarde, fmt_as, fmt_label, sublabel=None, whisker=None, y_titel=""):
    """Teken gegroepeerde staven (groep = effort, serie = model).

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        Doelfiguur.
    efforts, modellen : list of str
        Volgorde van groepen en series.
    waarde : dict
        ``(model, effort) -> float of None`` (None = geen waarde).
    fmt_as, fmt_label : callable
        Opmaak voor aslabels en staaflabels.
    sublabel : dict, optional
        ``(model, effort) -> str`` kleine tekst boven het waardelabel.
    whisker : dict, optional
        ``(model, effort) -> (laag, hoog)``.
    y_titel : str
        Titel van de y-as.
    """
    ax = fig.add_axes([0.085, 0.145, 0.89, 0.635])
    hoogste = max([v for v in waarde.values() if v] + [h for _, h in (whisker or {}).values()] + [1e-9])
    ticks = nette_ticks(hoogste * 1.15)
    ymax = ticks[-1]
    bw, stap = 0.24, 0.27
    for i, e in enumerate(efforts):
        for k, m in enumerate(modellen):
            x = i + (k - (len(modellen) - 1) / 2) * stap
            v = waarde.get((m, e))
            if not v:
                ax.text(x, ymax * 0.01, "geen goed", ha="center", va="bottom", fontsize=11, color=MUTED)
                continue
            ax.bar(x, v, width=bw, color=MODEL_KLEUR[m], zorder=3)
            top = v
            if whisker and (m, e) in whisker:
                lo, hi = whisker[(m, e)]
                ax.errorbar([x], [v], yerr=[[v - lo], [hi - v]], fmt="none", ecolor=INK, elinewidth=1.5, capsize=5, zorder=4)
                top = hi
            ax.text(x, top + ymax * 0.012, fmt_label(v), ha="center", va="bottom", fontsize=14, fontweight="bold", color=INK, zorder=5)
            if sublabel:
                ax.text(x, top + ymax * 0.058, sublabel[(m, e)], ha="center", va="bottom", fontsize=11, color=INK2, zorder=5)
    ax.set_xticks(range(len(efforts)))
    ax.set_xticklabels([f"effort: {e}" for e in efforts], fontsize=15, fontweight="bold", color=INK)
    ax.set_yticks(ticks)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_as(v)))
    ax.set_ylim(0, ymax)
    ax.set_xlim(-0.55, len(efforts) - 0.45)
    ax.grid(True, axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", labelsize=12, length=0)
    ax.tick_params(axis="x", length=0, pad=8)
    ax.set_ylabel(y_titel, fontsize=14, labelpad=10)
    _legenda_modellen(ax, modellen)


def _effort_model(data):
    modellen = [m for m in MODEL_VOLGORDE if any(a.model == m for a in data)]
    efforts = [e for e in EFFORT_VOLGORDE if any(a.effort == e for a in data)]
    return modellen, efforts


# ---------------------------------------------------------------- grafiek 4: kosten per goed antwoord
def grafiek_kosten_per_goed(data: list[Antwoord]):
    """Staven: totale kosten gedeeld door het aantal goede antwoorden."""
    modellen, efforts = _effort_model(data)
    waarde, sub, tabel = {}, {}, []
    for m in modellen:
        for e in efforts:
            rijen = [a for a in data if a.model == m and a.effort == e]
            g, n = som(rijen)
            kosten = sum(a.kosten for a in rijen)
            waarde[(m, e)] = kosten / g if g else None
            sub[(m, e)] = f"{g}/{n} goed"
            tabel.append([MODEL_NAAM[m], e, f"{g}/{n}", usd(kosten), usd(kosten / g) if g else "-"])
    tot = {}
    for m in modellen:
        rijen = [a for a in data if a.model == m]
        g = sum(a.goed for a in rijen)
        tot[m] = sum(a.kosten for a in rijen) / g if g else None
    if all(tot.get(m) for m in ("haiku", "sonnet", "opus")):
        titel = f"Per goed antwoord kost Opus ≈{tot['opus'] / tot['haiku']:.0f}x en Sonnet ≈{tot['sonnet'] / tot['haiku']:.0f}x zoveel als Haiku"
    else:
        titel = "Kosten per goed antwoord per model en effort"
    ctxn = len({a.context for a in data})
    qgoed = {a.query for a in data if a.goed}
    herh = max(1, len([a for a in data if a.model == modellen[0] and a.effort == efforts[0] and a.query in qgoed]) // max(1, ctxn * len(qgoed)))
    perm = {m: [sum(a.goed for a in data if a.model == m and a.effort == e) for e in efforts] for m in modellen}
    maximum = (
        f"Maximum is {ctxn * herh * len(qgoed)} goed per groep (alleen {', '.join(sorted(qgoed))} wordt opgelost). "
        + " · ".join(f"{MODEL_NAAM[m].split()[0]} haalt {min(v)}-{max(v)}" for m, v in perm.items())
        + "."
    )
    fig = nieuwe_figuur(
        titel,
        ["Totale kosten van alle antwoorden in de groep, ook de mislukte, gedeeld door het aantal goede antwoorden."],
        [maximum, "Kosten berekend uit tokens × prijs per miljoen tokens (Haiku $0,10/$0,50 · Sonnet $2/$10 · Opus $4/$20, in/uit), niet uit de factuur."],
    )
    staven(fig, efforts, modellen, waarde, usd, usd, sub, None, "Kosten per goed antwoord (USD)")
    return "4-kosten-per-goed-antwoord", fig, ["model", "effort", "goed", "totale kosten", "kosten per goed"], tabel


# ---------------------------------------------------------------- grafiek 5: output tokens
def grafiek_output_tokens(data: list[Antwoord]):
    """Staven: mediaan output tokens per antwoord met 10e-90e percentiel."""
    modellen, efforts = _effort_model(data)
    waarde, wh, tabel = {}, {}, []
    for m in modellen:
        for e in efforts:
            u = [a.uit for a in data if a.model == m and a.effort == e]
            p10, med, p90 = percentiel(u, 10), percentiel(u, 50), percentiel(u, 90)
            waarde[(m, e)], wh[(m, e)] = med, (p10, p90)
            tabel.append([MODEL_NAAM[m], e, str(len(u)), getal(p10), getal(med), getal(p90)])
    top = efforts[-1]
    delen = ", ".join(f"{MODEL_NAAM[m].split()[0]} {getal(waarde[(m, top)])}" for m in modellen)
    n = len([a for a in data if a.model == modellen[0] and a.effort == efforts[0]])
    fig = nieuwe_figuur(
        f"Mediaan output tokens bij {top}: {delen}",
        [f"Staaf = mediaan, streepje = 10e tot 90e percentiel (n = {n} antwoorden per staaf, alle queries en contexten)."],
        [
            "Output tokens bevatten ook de denktokens (reasoning) vóór het antwoord en bepalen de kosten (output is 5x duurder dan input).",
            "Meer output tokens betekent niet automatisch een beter antwoord: zie grafiek 2 en 3 voor wat er per model werd opgelost.",
        ],
    )
    staven(fig, efforts, modellen, waarde, getal, getal, None, wh, "Output tokens per antwoord")
    return "5-output-tokens", fig, ["model", "effort", "n", "p10", "mediaan", "p90"], tabel


# ---------------------------------------------------------------- HTML-overzicht
def maak_html(grafieken, pngs: dict, data: list[Antwoord]) -> str:
    """Bouw één HTML-pagina met alle grafieken (ingebed) en een tabel per grafiek."""
    gt, nt = som(data)
    queries = sorted({a.query for a in data})
    goede_q = sorted({a.query for a in data if a.goed})
    delen = [
        "<!DOCTYPE html><html lang='nl'><head><meta charset='utf-8'><title>Resultaten experiment</title>",
        f"<style>body{{font-family:'Segoe UI',Arial,sans-serif;color:{INK};max-width:1320px;margin:0 auto;padding:24px}}"
        "figure{margin:32px 0}img{width:100%;height:auto;border:1px solid #e6e8ec;border-radius:8px}"
        "table{border-collapse:collapse;font-size:14px;margin-top:8px}td,th{border-bottom:1px solid #e6e8ec;padding:4px 14px;text-align:left}"
        "details{margin-top:6px}summary{cursor:pointer;color:#4b5058}</style></head><body>",
        "<h1>Resultaten: welke context helpt een LLM bij het herschrijven van SQL?</h1>",
        f"<p>{nt} antwoorden, {len(queries)} queries, {gt} goed. Goed = zelfde resultaat én minstens 1,2x sneller.</p>",
        "<h3>Kanttekeningen (lees dit voor je de grafieken laat zien)</h3><ul>",
        f"<li>Alleen query {escape(', '.join(goede_q))} wordt ooit opgelost; de overige {len(queries) - len(goede_q)} queries geen enkele keer. Conclusies gelden dus voor één type query.</li>",
        "<li>Per cel (model × effort × context) zijn het slechts 3 herhalingen: verschillen van één antwoord zijn ruis.</li>",
        "<li>Output tokens bevatten denktokens. Kosten zijn berekend uit tokens × prijs, niet uit de factuur.</li>",
        "<li>De uitkomsten zijn gemeten op één database (schaal 0,02, seed 42).</li></ul>",
    ]
    for slug, _fig, kop, rijen in grafieken:
        b64 = base64.b64encode(pngs[slug]).decode()
        delen.append(f"<figure id='{slug}'><img src='data:image/png;base64,{b64}' alt='{slug}'>")
        delen.append("<details><summary>Tabel bij deze grafiek</summary><table><tr>")
        delen += [f"<th>{escape(k)}</th>" for k in kop]
        delen.append("</tr>")
        for r in rijen:
            delen.append("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in r) + "</tr>")
        delen.append("</table></details></figure>")
    delen.append("</body></html>")
    return "\n".join(delen)


def main() -> None:
    """Lees de resultaten en schrijf de grafieken."""
    p = argparse.ArgumentParser(description="Maak presentatiegrafieken van de experimentresultaten.")
    p.add_argument(
        "--invoer", nargs="+", default=["results/experiment-modellen-*/resultaten.csv"],
        help="glob(s) naar resultaten.csv (standaard: de drie modellenvergelijkingen)",
    )
    p.add_argument("--uit", default="results/grafieken", help="uitvoermap")
    args = p.parse_args()

    data = laad(args.invoer)
    uit = Path(args.uit) if Path(args.uit).is_absolute() else ROOT / args.uit
    uit.mkdir(parents=True, exist_ok=True)
    grafieken = [
        grafiek_query_context(data),
        grafiek_model_effort(data),
        grafiek_tokens_kosten(data),
        grafiek_kosten_per_goed(data),
        grafiek_output_tokens(data),
    ]
    pngs = {}
    for slug, fig, _, _ in grafieken:
        pngs[slug] = als_png(fig)
        (uit / f"{slug}.png").write_bytes(pngs[slug])
        fig.savefig(uit / f"{slug}.svg", facecolor=SURFACE)
        plt.close(fig)
        print("geschreven:", uit / f"{slug}.png")
    (uit / "overzicht.html").write_text(maak_html(grafieken, pngs, data), encoding="utf-8")
    print("geschreven:", uit / "overzicht.html")


if __name__ == "__main__":
    main()
