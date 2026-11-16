"""Streamlit-demo van de SQL Rewrite Validator: het hele proces van een herschrijving, stap voor stap.

Starten, vanuit de hoofdmap van deepdive_kit (de database moet draaien, zie README):
    streamlit run ui/app.py

De sleutel voor de modellen wordt alleen uit de omgevingsvariabele gelezen (OPENROUTER_API_KEY of
ANTHROPIC_API_KEY) en nooit getoond of opgeslagen.
"""
from __future__ import annotations

import difflib
import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm.client import HEADERS  # noqa: E402
from llm.prices import LABELS, cost_usd, family  # noqa: E402
from scripts.run_validation import evaluate  # noqa: E402
from ui import pipeline as P  # noqa: E402

st.set_page_config(page_title="SQL Rewrite Validator", page_icon="🔎", layout="wide")


# Noodoplossing: een Application Control-beleid kan pyarrow blokkeren (DLL load failed).
# Streamlit gebruikt pyarrow voor tabellen en grafieken; zonder pyarrow tonen we ze als HTML-tabel.
try:
    import pyarrow  # noqa: F401
except Exception:  # pragma: no cover
    def _toon_tabel(data, *args, **kwargs):
        """Toon een DataFrame als HTML-tabel, zonder pyarrow."""
        if not hasattr(data, "to_html"):
            data = pd.DataFrame(data)
        verberg_index = kwargs.get("hide_index", False)
        html = data.to_html(index=not verberg_index, border=0, float_format=lambda x: f"{x:.2f}")
        st.markdown(f'<div style="overflow-x:auto;font-size:0.85rem">{html}</div>', unsafe_allow_html=True)

    st.dataframe = _toon_tabel
    st.bar_chart = _toon_tabel

SOURCES = {
    "llm": "LLM (live, via de aanbieder)",
    "stored": "Opgeslagen LLM-antwoord (de controle draait wel live)",
    "candidate": "Handmatige kandidaat uit de mutatietest",
    "own": "Eigen SQL plakken",
    "mock": "Nepmodel (geeft het origineel terug)",
}
EFFORTS = ["standaard van het model", "low", "medium", "high", "xhigh", "max"]
STATUS_ICON = {"EQUIVALENT": "✅", "TIE_AMBIGUOUS": "⚠️"}
STEP_TITLES = ["1 · De originele query", "2 · Context voor het model", "3 · Antwoord van het model",
               "4 · Statische controle", "5 · Gelijkwaardigheid op alle parametersets", "6 · Tijdmeting", "7 · Eindoordeel"]


# ---------------------------------------------------------------- database

@st.cache_resource(show_spinner=False)
def _open(uri: str):
    """
    Open (and cache) a database connection per URI.

    Parameters
    ----------
    uri : str
        Database URI.

    Returns
    -------
    psycopg.Connection
        Open connection in autocommit mode.
    """
    return P.connect(uri)


def get_conn(uri: str):
    """
    Get a working connection for the URI; reconnect when the cached one has gone stale.

    Parameters
    ----------
    uri : str
        Database URI.

    Returns
    -------
    psycopg.Connection
        Open connection.
    """
    conn = _open(uri)
    try:
        conn.execute("SELECT 1")
    except Exception:  # verbroken: opnieuw verbinden
        _open.clear()
        conn = _open(uri)
    return conn


@st.cache_resource(show_spinner=False)
def get_ctx(uri: str):
    """
    Build (and cache) the parameter context of the database.

    Parameters
    ----------
    uri : str
        Database URI.

    Returns
    -------
    dict
        Context as returned by ``make_ctx``.
    """
    return P.make_ctx(get_conn(uri))


def start_embedded_db(datadir: str) -> None:
    """
    Start the embedded PostgreSQL (pgserver) and put its URI in the sidebar field. Used as button callback.

    Parameters
    ----------
    datadir : str
        Folder with the data directory of the database.

    Returns
    -------
    None
    """
    try:
        import pgserver

        os.makedirs(os.path.dirname(os.path.abspath(datadir)), exist_ok=True)
        srv = pgserver.get_server(os.path.abspath(datadir), cleanup_mode=None)
        st.session_state["uri"] = srv.get_uri()
        st.session_state["db_msg"] = ("ok", "Ingebedde database gestart.")
    except Exception as e:  # noqa: BLE001 - de melding is voor de gebruiker
        st.session_state["db_msg"] = ("err", f"Starten mislukt: {type(e).__name__}: {str(e)[:200]}")


# ---------------------------------------------------------------- hulpfuncties voor weergave

def sql_diff(old: str, new: str) -> str:
    """
    Make a unified diff of two queries.

    Parameters
    ----------
    old : str
        The original query.
    new : str
        The candidate query.

    Returns
    -------
    str
        The diff, or an empty string when both are the same.
    """
    return "\n".join(difflib.unified_diff(old.strip().splitlines(), new.strip().splitlines(), "origineel", "kandidaat", lineterm=""))


def banner(kind: str, text: str) -> None:
    """
    Show a coloured message.

    Parameters
    ----------
    kind : str
        "success", "warning", "error" or "info".
    text : str
        The message.

    Returns
    -------
    None
    """
    {"success": st.success, "warning": st.warning, "error": st.error}.get(kind, st.info)(text)


def expected_matches(expected: str, verdict: str) -> bool:
    """
    Check whether the verdict agrees with the expected verdict of a handmade candidate.

    Parameters
    ----------
    expected : str
        "equivalent" or "not_equivalent".
    verdict : str
        The verdict of the validator.

    Returns
    -------
    bool
        True when a not-equivalent candidate was rejected, or an equivalent one was not rejected.
    """
    rejected = verdict in ("REJECTED_STATIC", "REJECTED_NOT_EQUIVALENT")
    return rejected if expected == "not_equivalent" else not rejected


# ---------------------------------------------------------------- weergave per stap

def show_query(run: dict) -> None:
    """
    Show step 1: the original query and its parameter sets.

    Parameters
    ----------
    run : dict
        The run, as built by ``execute``.

    Returns
    -------
    None
    """
    st.code(run["original"], language="sql")
    st.caption("De controle draait op elk van deze parametersets (een grote en een kleine tenant, vier tijdvensters).")
    st.dataframe(pd.DataFrame(run["params"]), hide_index=True, width="stretch")


def show_context(run: dict) -> None:
    """
    Show step 2: what the model gets to see.

    Parameters
    ----------
    run : dict
        The run, as built by ``execute``.

    Returns
    -------
    None
    """
    if run.get("blocks") is None:
        st.info("Overgeslagen: bij deze bron is geen model betrokken.")
        return
    st.markdown(f"**Conditie:** {P.CONDITION_LABELS.get(run['condition'], run['condition'])}")
    chars = len(run["prompt"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Blokken in de prompt", len(run["blocks"]))
    c2.metric("Tekens", f"{chars:,}".replace(",", "."))
    c3.metric("Ongeveer tokens", f"{chars // 4:,}".replace(",", "."), help="Grove schatting: vier tekens per token.")
    for key, text in run["blocks"].items():
        with st.expander(HEADERS.get(key, "Opgeslagen prompt van deze run")):
            st.code(text, language="sql" if key == "query" else None)
    with st.expander("Volledige prompt die naar het model gaat"):
        st.code(run["prompt"], language=None)
    with st.expander("Systeemprompt (instructies aan het model)"):
        st.code(P.SYSTEM, language=None)


def show_model(run: dict) -> None:
    """
    Show step 3: the answer of the model and what it changed.

    Parameters
    ----------
    run : dict
        The run, as built by ``execute``.

    Returns
    -------
    None
    """
    resp = run.get("response")
    if resp is None:
        st.info("Overgeslagen: de SQL komt niet van een model." if run["source"] in ("candidate", "own")
                else "Geen antwoord ontvangen.")
        if run["source"] in ("candidate", "own"):
            st.code(run["sql"], language="sql")
        return
    c = st.columns(5)
    c[0].markdown(f"**Model**  \n`{resp.get('model', run.get('model', ''))}`")
    c[1].metric("Tokens in / uit", f"{resp.get('input_tokens', 0)} / {resp.get('output_tokens', 0)}")
    c[2].metric("Duur", f"{resp.get('seconds', 0)} s")
    cost = resp.get("cost_usd")
    c[3].metric("Kosten", f"$ {cost:.4f}" if cost is not None else "onbekend")
    c[4].metric("Stopreden", resp.get("stop_reason") or "onbekend")
    if resp.get("truncated"):
        st.error("Het antwoord is afgekapt door de tokenlimiet voordat er een volledig SQL-blok stond.")
    with st.expander("Ruw antwoord van het model"):
        st.code(resp["text"], language=None)
    st.markdown("**Voorgestelde herschrijving**")
    st.code(run["sql"], language="sql")
    diff = sql_diff(run["original"], run["sql"])
    if not diff:
        st.warning("Het model gaf de originele query ongewijzigd terug.")
    else:
        with st.expander("Wat is er veranderd? (verschil met het origineel)", expanded=True):
            st.code(diff, language="diff")


def show_static(run: dict) -> None:
    """
    Show step 4: the static check.

    Parameters
    ----------
    run : dict
        The run, as built by ``execute``.

    Returns
    -------
    None
    """
    ok, msg = run["static"]
    st.caption("Wordt de SQL met sqlglot geparsed: precies één SELECT, geen DDL of schrijfacties, ook niet in een CTE.")
    (st.success if ok else st.error)(f"{'Geslaagd' if ok else 'Afgekeurd'}: {msg}")


def show_equivalence(run: dict) -> None:
    """
    Show step 5: the result per parameter set.

    Parameters
    ----------
    run : dict
        The run, as built by ``execute``.

    Returns
    -------
    None
    """
    rows = run.get("equivalence")
    if rows is None:
        st.info("Overgeslagen: de statische controle is niet geslaagd, dus er is niets uitgevoerd.")
        return
    good = sum(r["status"] in ("EQUIVALENT", "TIE_AMBIGUOUS") for r in rows)
    st.caption("Origineel en kandidaat draaien in een read-only transactie. Vergeleken worden kolommen, aantal rijen, "
               "waarden (als multiset) en de volgorde volgens de ORDER BY.")
    (st.success if good == len(rows) else st.error)(f"{good} van {len(rows)} parametersets geven hetzelfde resultaat.")
    df = pd.DataFrame(rows)
    df.insert(1, "", df["status"].map(lambda s: STATUS_ICON.get(s, "❌")))
    st.dataframe(df.rename(columns={"set": "parameterset", "orig_rows": "rijen origineel", "cand_rows": "rijen kandidaat",
                                    "orig_ms": "ms origineel", "cand_ms": "ms kandidaat"}),
                 hide_index=True, width="stretch")
    bad = [r for r in rows if r["status"] not in ("EQUIVALENT", "TIE_AMBIGUOUS")]
    if bad:
        with st.expander("Waar zit het verschil?", expanded=True):
            for r in bad:
                st.markdown(f"**{r['set']}** · {r['status']}")
                st.code(r["detail"] or "(geen detail)", language=None)


def show_timing(run: dict) -> None:
    """
    Show step 6: the timing comparison.

    Parameters
    ----------
    run : dict
        The run, as built by ``execute``.

    Returns
    -------
    None
    """
    t = run.get("timing")
    if t is None:
        st.info("Overgeslagen: alleen een gelijkwaardige kandidaat wordt getimed.")
        return
    st.caption(f"Om en om (ABAB) gemeten, zodat caching en drift beide kanten even raken. Een voorstel telt als sneller "
               f"vanaf {P.SPEEDUP_THRESHOLD}× op de mediaan.")
    c = st.columns(4)
    c[0].metric("Mediaan origineel", f"{t['orig_median_ms']} ms")
    c[1].metric("Mediaan kandidaat", f"{t['cand_median_ms']} ms")
    c[2].metric("Speedup", f"{t['speedup']}×", delta=f"{round(t['speedup'] - P.SPEEDUP_THRESHOLD, 2)} t.o.v. de drempel")
    c[3].metric("Herhalingen", t["reps"])
    st.bar_chart(pd.DataFrame({"ms (mediaan)": [t["orig_median_ms"], t["cand_median_ms"]]}, index=["1 · Origineel", "2 · Kandidaat"]),
                 horizontal=True, height=180)


def show_verdict(run: dict) -> None:
    """
    Show step 7: the verdict, and for a handmade candidate whether it matches the expectation.

    Parameters
    ----------
    run : dict
        The run, as built by ``execute``.

    Returns
    -------
    None
    """
    kind, text = P.VERDICTS[run["verdict"]]
    banner(kind, f"**{run['verdict']}** — {text}")
    exp = run.get("expected")
    if exp:
        ok = expected_matches(exp, run["verdict"])
        (st.success if ok else st.error)(
            f"Verwacht door de maker: **{exp}** → de validator {'bevestigt dat' if ok else 'wijkt hiervan af'}.")
    st.caption("`ACCEPTED` betekent: gelijk resultaat op de geteste parametersets en aantoonbaar sneller. Het is geen bewijs "
               "van gelijkwaardigheid voor alle mogelijke data.")
    st.download_button("Resultaat van deze run (JSON)", json.dumps(
        {k: v for k, v in run.items() if k not in ("blocks", "prompt", "response")}, indent=2, default=str),
        file_name=f"run_{run['case']}.json", mime="application/json")


RENDERERS = [show_query, show_context, show_model, show_static, show_equivalence, show_timing, show_verdict]


def render_run(run: dict) -> None:
    """
    Show all steps of a finished run.

    Parameters
    ----------
    run : dict
        The run, as built by ``execute``.

    Returns
    -------
    None
    """
    for title, fn in zip(STEP_TITLES, RENDERERS):
        st.subheader(title)
        fn(run)


# ---------------------------------------------------------------- uitvoeren, stap voor stap met live weergave

def execute(conn, ctx, cfg: dict) -> dict | None:
    """
    Run the whole process for the chosen settings, showing every step as soon as it is ready.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection.
    ctx : dict
        Context as returned by ``make_ctx``.
    cfg : dict
        The settings from the form: case, source, condition, model, provider, effort, max_tokens, reps, and the
        chosen candidate, stored answer or own SQL.

    Returns
    -------
    dict or None
        The finished run; None when the model call failed.
    """
    case = P.case_by_name(cfg["case"])
    run = {"case": case.name, "source": cfg["source"], "original": case.original.strip(), "params": P.param_table(case, ctx),
           "condition": cfg.get("condition"), "blocks": None, "prompt": None, "response": None, "expected": None}
    slots = []
    for title in STEP_TITLES:
        st.subheader(title)
        slots.append(st.empty())

    def step(i: int, fn) -> None:
        with slots[i].container():
            fn(run)

    step(0, show_query)
    src = cfg["source"]

    # stap 2 en 3: context en antwoord van het model
    if src in ("llm", "mock"):
        slots[1].info("Context opbouwen (schema, plan en statistieken uit de database)…")
        run["blocks"], run["prompt"] = P.build_prompt_for(conn, case, ctx, cfg["condition"])
        step(1, show_context)
        slots[2].info("Model aanroepen… dit duurt meestal 10 tot 60 seconden.")
        model = "mock" if src == "mock" else cfg["model"]
        try:
            run["response"] = P.ask_model(run["prompt"], model, cfg["provider"], cfg["effort"], cfg["max_tokens"], case.original)
        except (Exception, SystemExit) as e:  # noqa: BLE001 - ontbrekende sleutel of netwerkfout tonen
            slots[2].error(f"De aanroep van het model is mislukt: {type(e).__name__}: {str(e)[:300]}")
            return None
        run["model"] = model
        run["sql"] = run["response"]["sql"]
    elif src == "stored":
        resp = P.load_answer(cfg["stored"]["path"])
        run["response"], run["model"], run["sql"] = resp, resp.get("model", ""), resp["sql"]
        prompt_file = cfg["stored"]["path"].parents[1] / "prompts" / f"{case.name}__{cfg['stored']['condition']}.txt"
        if prompt_file.exists():
            run["prompt"] = prompt_file.read_text(encoding="utf-8")
            run["blocks"] = {"prompt": run["prompt"]}
            run["condition"] = cfg["stored"]["condition"]
        step(1, show_context)
    else:
        run["sql"] = cfg["sql"]
        run["expected"] = cfg.get("expected")
        step(1, show_context)
    step(2, show_model)

    # stap 4: statische controle
    run["static"] = P.static_check(run["sql"])
    step(3, show_static)
    run["equivalence"], run["timing"] = None, None

    # stap 5: gelijkwaardigheid
    if run["static"][0]:
        slots[4].info("Origineel en kandidaat uitvoeren op alle parametersets…")
        run["equivalence"] = P.check_equivalence(conn, case, run["sql"], ctx)
    step(4, show_equivalence)

    # stap 6: tijdmeting (alleen als het resultaat gelijk is)
    if run["equivalence"] is not None and P.equivalent(run["equivalence"]):
        slots[5].info(f"Tijdmeting (ABAB, {cfg['reps']} herhalingen); bij een trage query kan dit enkele minuten duren…")
        run["timing"] = P.check_timing(conn, case, run["sql"], ctx, cfg["reps"])
    step(5, show_timing)

    run["verdict"] = P.decide(run["static"][0], run["equivalence"], run["timing"])
    step(6, show_verdict)
    return run


# ---------------------------------------------------------------- zijbalk

st.sidebar.title("🔎 SQL Rewrite Validator")
st.sidebar.caption("Laat een model een SQL-query herschrijven en toont elke stap van de controle.")
st.sidebar.subheader("Database")
st.session_state.setdefault("uri", os.environ.get("SUE_DEMO_DB_URI", ""))
uri = st.sidebar.text_input("Database-URI", key="uri", help="De URI die `python scripts/start_db.py <map>` print.")
with st.sidebar.expander("Ingebedde database starten"):
    datadir = st.text_input("Datamap", value=str(ROOT.parent / "pgdata" / "bazaar"))
    st.button("Start de database", on_click=start_embedded_db, args=(datadir,))
if "db_msg" in st.session_state:
    kind, msg = st.session_state["db_msg"]
    (st.sidebar.success if kind == "ok" else st.sidebar.error)(msg)

conn = ctx = None
if uri:
    try:
        conn, ctx = get_conn(uri), get_ctx(uri)
        st.sidebar.success("Verbonden met de database.")
    except Exception as e:  # noqa: BLE001
        st.sidebar.error(f"Geen verbinding: {type(e).__name__}: {str(e)[:150]}")
else:
    st.sidebar.info("Vul een database-URI in of start de ingebedde database.")

st.sidebar.subheader("Sleutel voor de modellen")
for var in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
    st.sidebar.write(("✅ " if os.environ.get(var) else "⬜ ") + var + (" gevonden" if os.environ.get(var) else " niet gezet"))
st.sidebar.caption("Zet de sleutel alleen in de terminal waarin je Streamlit start, nooit in een bestand.")

# ---------------------------------------------------------------- hoofdscherm

tab_run, tab_res, tab_mut, tab_info = st.tabs(["Proces", "Resultaten en modelvergelijking", "Mutatietest", "Uitleg"])

with tab_run:
    st.header("Het proces voor één query")
    if conn is None:
        st.warning("Verbind eerst met de database (zijbalk).")
    else:
        top = st.columns([1.2, 2])
        case_name = top[0].selectbox("Query", [c.name for c in P.CASES])
        case = P.case_by_name(case_name)
        source = top[1].radio("Bron van de herschrijving", list(SOURCES), format_func=SOURCES.get)
        cfg = {"case": case_name, "source": source, "reps": 7}

        if source in ("llm", "mock"):
            cols = st.columns(5)
            cfg["condition"] = cols[0].selectbox("Context voor het model", P.CONDITIONS, format_func=P.CONDITION_LABELS.get)
            cfg["provider"] = cols[1].selectbox("Aanbieder", ["openrouter", "anthropic"], help="OpenRouter is de standaard (sleutel van SUE).",
                                                disabled=source == "mock")
            label = cols[2].selectbox("Model", list(P.MODELS), index=1, disabled=source == "mock")
            cfg["model"] = P.MODELS[label][0 if cfg["provider"] == "openrouter" else 1]
            eff = cols[3].selectbox("Denkinspanning", EFFORTS, disabled=source == "mock")
            cfg["effort"] = None if eff == EFFORTS[0] else eff
            cfg["max_tokens"] = cols[4].select_slider("Max. uitvoertokens", [1000, 2000, 4000, 8000], value=4000, disabled=source == "mock")
        elif source == "stored":
            options = [a for a in P.stored_answers() if a["case"] == case_name]
            if not options:
                st.info("Geen opgeslagen antwoorden voor deze query in `results/`.")
            else:
                cfg["stored"] = st.selectbox(
                    "Opgeslagen antwoord", options,
                    format_func=lambda a: f"{a['run']} · {a['condition']} · herhaling {a['rep']} · {a['model']} · toen: {a['old_verdict']}")
        elif source == "candidate":
            cand = st.selectbox("Kandidaat", case.candidates, format_func=lambda c: f"{c.name}   (verwacht: {c.expected}, fout: {c.fault or '-'})")
            cfg["sql"], cfg["expected"] = cand.sql, cand.expected
            with st.expander("SQL van deze kandidaat"):
                st.code(cand.sql, language="sql")
        else:
            cfg["sql"] = st.text_area("SQL van de kandidaat", value=case.original.strip(), height=240,
                                      help="Gebruik %(naam)s voor de parameters, precies zoals in het origineel.")

        cfg["reps"] = st.slider("Tijdmeting: herhalingen per query", 3, 9, 7,
                                help="Meer herhalingen geven een betrouwbaardere mediaan maar duren langer.")
        missing = source == "llm" and not os.environ.get("OPENROUTER_API_KEY" if cfg["provider"] == "openrouter" else "ANTHROPIC_API_KEY")
        if missing:
            st.warning("Voor een live aanroep ontbreekt de sleutel in deze terminal. Kies een opgeslagen antwoord, een kandidaat of het nepmodel.")
        needs_stored = source == "stored" and "stored" not in cfg
        if st.button("▶ Start het proces", type="primary", disabled=missing or needs_stored):
            st.session_state["run"] = execute(conn, ctx, cfg)
        elif st.session_state.get("run"):
            st.caption("Laatste run:")
            render_run(st.session_state["run"])

with tab_res:
    st.header("Resultaten van eerdere LLM-runs")
    st.caption("Alle runs in de map `results/`, ook die van de modelvergelijking.")

    @st.cache_data(show_spinner=False)
    def load_results(stamp: float) -> pd.DataFrame:
        """
        Read all LLM result files in ``results/`` into one table.

        Parameters
        ----------
        stamp : float
            Newest modification time of the result files; only used as cache key.

        Returns
        -------
        pandas.DataFrame
            One row per judged answer, with the run, model, settings, verdict, speedup, tokens and cost.
        """
        rows = []
        for f in P.RESULTS.glob("**/llm-results.json"):
            run_dir = f.parent
            meta = {}
            if (run_dir / "meta.json").exists():
                meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
            for r in json.loads(f.read_text(encoding="utf-8")):
                model = r.get("model", meta.get("model", ""))
                cost = r.get("cost_reported")
                if cost in (None, ""):
                    cost = cost_usd(model, r.get("input_tokens", 0) or 0, r.get("output_tokens", 0) or 0)
                rows.append({"run": str(run_dir.relative_to(P.RESULTS)), "model": LABELS.get(family(model), model),
                             "max_tokens": r.get("max_tokens", meta.get("max_tokens", "")), "effort": r.get("effort", meta.get("effort") or ""),
                             "case": r["case"], "condition": r["condition"], "verdict": r["verdict"], "speedup": r.get("speedup"),
                             "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"), "cost_usd": cost})
        return pd.DataFrame(rows)

    files = list(P.RESULTS.glob("**/llm-results.json"))
    df = load_results(max((f.stat().st_mtime for f in files), default=0.0)) if files else pd.DataFrame()
    if df.empty:
        st.info("Nog geen resultaten in `results/`.")
    else:
        runs = st.multiselect("Runs", sorted(df["run"].unique()), default=sorted(df["run"].unique()))
        d = df[df["run"].isin(runs)]
        m = st.columns(4)
        m[0].metric("Beoordeelde antwoorden", len(d))
        m[1].metric("ACCEPTED", int((d["verdict"] == "ACCEPTED").sum()))
        m[2].metric("Afgekeurd (niet gelijk)", int(d["verdict"].isin(["REJECTED_NOT_EQUIVALENT", "REJECTED_STATIC"]).sum()))
        m[3].metric("Kosten (geschat)", f"$ {d['cost_usd'].fillna(0).sum():.2f}")
        st.subheader("Oordelen per conditie")
        st.bar_chart(pd.crosstab(d["condition"], d["verdict"]))
        st.subheader("Oordelen per query")
        st.bar_chart(pd.crosstab(d["case"], d["verdict"]))
        st.subheader("Per model")
        g = d.groupby("model").agg(antwoorden=("verdict", "size"), accepted=("verdict", lambda s: int((s == "ACCEPTED").sum())),
                                   mediaan_speedup_accepted=("speedup", lambda s: s[d.loc[s.index, "verdict"] == "ACCEPTED"].median()),
                                   kosten_usd=("cost_usd", "sum")).reset_index()
        g["accepted %"] = (100 * g["accepted"] / g["antwoorden"]).round(1)
        st.dataframe(g, hide_index=True, width="stretch")
        with st.expander("Alle rijen"):
            st.dataframe(d, hide_index=True, width="stretch")

with tab_mut:
    st.header("Mutatietest: vangt de validator opzettelijke fouten?")
    st.caption("Per query liggen er handgemaakte herschrijvingen: sommige gelijkwaardig, sommige met een bewust ingebouwde fout. "
               "Dit toont of de validator ze goed beoordeelt. Er is geen model of sleutel voor nodig.")
    if conn is None:
        st.warning("Verbind eerst met de database (zijbalk).")
    else:
        reps_m = st.slider("Herhalingen per tijdmeting", 3, 9, 5, key="reps_m")
        if st.button("▶ Draai de mutatietest (ongeveer 2 minuten)"):
            allc = [(c, k) for c in P.CASES for k in c.candidates]
            bar, out = st.progress(0.0), []
            for i, (c, k) in enumerate(allc):
                bar.progress(i / len(allc), text=f"{c.name} · {k.name}")
                r = evaluate(conn, c, k, ctx, reps_m)
                out.append({"query": c.name, "kandidaat": k.name, "verwacht": k.expected, "oordeel": r["verdict"],
                            "klopt": expected_matches(k.expected, r["verdict"]), "speedup": r.get("speedup")})
            bar.progress(1.0, text="Klaar")
            st.session_state["mut"] = pd.DataFrame(out)
        if "mut" in st.session_state:
            mdf = st.session_state["mut"]
            neq, eq = mdf[mdf["verwacht"] == "not_equivalent"], mdf[mdf["verwacht"] == "equivalent"]
            c = st.columns(3)
            c[0].metric("Fouten gedetecteerd", f"{int(neq['klopt'].sum())} / {len(neq)}")
            c[1].metric("Onterecht afgekeurd", f"{int((~eq['klopt']).sum())} / {len(eq)}")
            c[2].metric("Gemist", ", ".join(neq.loc[~neq["klopt"], "kandidaat"]) or "geen")
            st.dataframe(mdf, hide_index=True, width="stretch")

with tab_info:
    st.header("Hoe werkt het?")
    st.markdown("""
Een model kan een trage SQL-query herschrijven naar iets dat er sneller uitziet, maar dat is geen garantie dat het ook
klopt of sneller is. Deze tool controleert dat in zeven stappen:

1. **De originele query** met de parametersets waarop getest wordt.
2. **Context voor het model:** alleen de query (C1), of ook schema (C2), uitvoeringsplan (C3) en statistieken (C4).
3. **Het antwoord van het model**, met tokens, duur en kosten.
4. **Statische controle:** precies één toegestane SELECT.
5. **Gelijkwaardigheid:** origineel en kandidaat draaien op elke parameterset in een read-only transactie en de resultaten worden vergeleken.
6. **Tijdmeting:** om en om (ABAB) herhaald; sneller telt pas vanaf 1,2× op de mediaan.
7. **Eindoordeel:** `ACCEPTED`, `EQUIVALENT_NOT_FASTER`, `REJECTED_NOT_EQUIVALENT` of `REJECTED_STATIC`.

**Beperkingen.** `ACCEPTED` bewijst niet dat de herschrijving voor alle mogelijke data gelijk is, alleen voor de geteste
parametersets op een kleine, verzonnen dataset. De tijden komen van één machine met standaardinstellingen. Zie de README voor meer.
""")
