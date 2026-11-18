"""
saral_chatbot.py  -  "Ask SARAL": plain-language chatbot for the S.A.R.A.L Streamlit app.

HOW IT WORKS (safe by design)
  1. The user types a normal question (English / Hindi / Hinglish).
  2. Claude sees ONLY column names + sample values (never the full data) and turns
     the question into a small JSON "plan" (filters, dates, group-by).
  3. This file runs that plan on your DataFrame with a fixed set of allowed
     operations. No AI-written code is ever executed.
  4. The user gets the table, a short summary in simple words, and an Excel download.

SETUP
    pip install anthropic openpyxl
    .streamlit/secrets.toml ->  ANTHROPIC_API_KEY = "sk-ant-..."
    (optional)                  SARAL_CHAT_MODEL  = "claude-sonnet-5-5"
"""

import difflib
import io
import json
import re
import datetime as dt

import pandas as pd
import streamlit as st

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_ROWS_SHOWN = 500
MAX_ROWS_TO_AI = 40
MAX_CATEGORY_VALUES = 60

# Columns that are internal plumbing and must never reach the AI or the user.
INTERNAL_COLUMNS = ["_sheet_row", "_original_sheet_index", "_status_plain"]

# ----------------------------------------------------------------------------
# S.A.R.A.L specific knowledge, taken from the app code
# ----------------------------------------------------------------------------
SARAL_HINT = """
This is the S.A.R.A.L (Safety Abnormality Report & Action List) database of Solapur Division, Central Railway.
Each row is ONE deficiency noted during an inspection.

Column meanings:
- "Date of Inspection": date the inspection was done (default date for any date range in a question).
- "Type of Inspection": FOOTPLATE INSPECTION, STATION INSPECTION, LC GATE INSPECTION, COACHING DEPOT, ON TRAIN,
  SURPRISE/AMBUSH INSPECTION, WORKSITE INSPECTION, OTHER (UNUSUAL).
- "Location": station code (SUR, KWV, WADI...), level crossing gate (LC-40) or footplate section (SUR-DD).
- "Head": the DEPARTMENT. Values: ELECT/TRD, ELECT/G, ELECT/TRO, SIGNAL & TELECOM, OPTG, MECHANICAL, ENGINEERING,
  COMMERCIAL, PERSONNEL, SECURITY, FINANCE, MEDICAL, STORE, GSU.
- "Sub Head": category inside a department.
- "Deficiencies Noted": the text of the deficiency.
- "Inspection By": the officer who inspected (e.g. Sr.DOM, DRM/SUR, ADRM).
- "Action By": the officer RESPONSIBLE for fixing it (e.g. Sr.DOM, Sr.DEN/S, Sr.DSTE).
- "Feedback": compliance reply given by the department. "User Feedback/Remark": extra remark.
- "Timestamp of Compliance": when the compliance feedback was given.
- "Status": Resolved, Pending or No Response (No Response = no feedback given yet).

Interpretation rules:
- Department words map to "Head": Engg/Engineering/Track -> ENGINEERING, S&T/Signal/Telecom -> SIGNAL & TELECOM,
  Operating/Optg -> OPTG, Mech -> MECHANICAL, Elect TRD -> ELECT/TRD, Elect G -> ELECT/G, Elect TRO -> ELECT/TRO.
- Officer designations (Sr DOM, Sr DEN/S, DRM, Sr DSTE, ADEN...) in a question about deficiencies, pending work,
  or compliance mean "Action By", unless the user says "inspected by" / "inspection done by" (then use "Inspection By").
- "resolved / complied / closed / attended" -> Status = Resolved. "pending / open / not done" -> Status = Pending.
  "no reply / not responded / no feedback" -> Status = No Response.
- Date ranges refer to "Date of Inspection". Only if the user says "complied/resolved ON or DURING <dates>"
  use "Timestamp of Compliance" instead.
- "Deficiencies Noted" and "Feedback" are long text: for "related to <word>" questions use op "contains".
- For "all deficiencies" style questions return the full rows with these columns:
  Date of Inspection, Type of Inspection, Location, Head, Sub Head, Deficiencies Noted, Inspection By, Action By,
  Feedback, Status.
- "Analysis" of a department: group_by ["Sub Head","Status"] with count, after filtering Head and dates.
"""

EXAMPLES = [
    "Sr DOM all deficiencies resolved from August to October",
    "Give me analysis of Engg department of last 5 days",
    "Which department has the most pending deficiencies?",
    "Sr DSTE pending deficiencies of this month",
]

PLAN_SYSTEM = """You convert a railway safety inspection question into a JSON query plan.
Today's date is {today}. Reply with ONE JSON object only, no other text.

{hint}

Available tables and columns (with sample values):
{schema}

JSON format:
{{
  "table": "<table name>",
  "filters": [{{"column": "<col>", "op": "<op>", "value": <value>}}],
  "group_by": ["<col>"],
  "aggregations": [{{"column": "<col or *>", "func": "count|sum|mean|min|max|nunique", "as": "<name>"}}],
  "columns": ["<cols to show>"],
  "sort_by": "<col or null>",
  "ascending": false,
  "limit": null,
  "title": "<short title for the result>",
  "clarification": null
}}

Rules:
- op is one of: eq, ne, in, contains, gt, gte, lt, lte, between, isnull, notnull.
- Dates are ISO strings YYYY-MM-DD. "between" takes [from, to] inclusive.
  Resolve "last 5 days", "this month", "August to October" into exact dates using today's date.
  If no year is given for a month range, use the most recent such period that is not in the future.
- Use values exactly as they appear in the sample values when possible
  (e.g. "Sr DOM" is stored as "Sr.DOM").
- For "analysis"/"summary"/"department wise" questions use group_by + aggregations.
- For "show/list/give me all" questions leave group_by and aggregations empty so full rows come back.
- Use ONLY the table and column names listed above. Never invent columns.
- If the question is too unclear, set "clarification" to ONE short question and leave other fields empty.
- Earlier conversation is given so follow-ups like "now only for Solapur" refine the previous plan.

Understanding careless typing (VERY IMPORTANT):
- Users are not computer-savvy. Expect spelling mistakes, missing spaces, short forms, mixed Hindi/English,
  no punctuation, ALL CAPS or all small letters. Work out what they MEAN and answer; never complain about spelling.
  Examples: "defficiencies", "defeciency", "deficencies", "defs" = deficiencies; "dept", "deptt", "dpt" = department
  (department = the "Head" column); "pndng", "pendng" = pending; "resolvd", "solved", "done", "closed" = Resolved;
  "wk", "wek" = week; "hw many", "kitne" = how many; "kon sa", "konsa", "which" = which.
- Department short forms: engg, engr, eng, enginering, track, den -> ENGINEERING; snt, s&t, s and t, signal, telecom,
  tele -> SIGNAL & TELECOM; optg, opt, ops, operating, operation -> OPTG; mech, mechnical -> MECHANICAL;
  comm, comml, commercial -> COMMERCIAL; trd -> ELECT/TRD; elect g, elec g, general elect -> ELECT/G; tro -> ELECT/TRO;
  pers, personal -> PERSONNEL; sec, rpf -> SECURITY; med -> MEDICAL.
- Officer short forms (go in "Action By" unless "inspection by" is clear): dom, sr dom, srdom -> Sr.DOM;
  sr den s, den s -> Sr.DEN/S; den c -> Sr.DEN/C; sr dste, dste -> Sr.DSTE; drm -> DRM/SUR; adrm -> ADRM; dso -> Sr.DSO.
  Always pick the closest value that really exists in the sample values.
- Time words: "today", "yesterday", "last N days", "last week"/"past week"/"this week" = the last 7 days ending today,
  "this month" = 1st of this month to today, "last month" = the previous full calendar month.
  Put the exact date range you used into the "title" (e.g. "Department-wise deficiencies, 11 Nov to 18 Nov 2026").
- Questions like "which department has most/least ..." mean: filter by the dates, group_by ["Head"], count rows
  (aggregation column "*" , func "count", as "Deficiencies"), sort descending (ascending true for "least"), limit null.
- If the user just says hi / help / what can you do, set "clarification" to a short friendly message listing 3 example
  questions they can ask.
- When unsure between two meanings, pick the most likely one and answer; do not ask unless truly impossible.
"""

SUMMARY_SYSTEM = """You are the helpful assistant inside the S.A.R.A.L railway safety app.
Write a SHORT answer (3-6 lines) in very simple words for a person who is not good with computers.
Reply in the same language style as the question (English, Hindi or Hinglish).
State the total number of records first, then 2-4 key points (biggest/smallest, pending vs resolved vs no response if visible).
If the question asks "which / who / most / least / highest", begin with the direct answer (name and number) in one line.
Mention the date range used if the result title shows it. Never mention spelling mistakes.
Use only the numbers given. Do not invent anything. No tables, no markdown headings."""


# ----------------------------------------------------------------------------
# Data preparation
# ----------------------------------------------------------------------------
def add_status(df, classify_fn, feedback_col="Feedback", remark_col="User Feedback/Remark"):
    """Add the same Resolved / Pending / No Response Status used in Smart Analysis.
    classify_fn = your app's classify_feedback(feedback, remark)."""
    d = df.copy()

    def _row(r):
        fb = str(r.get(feedback_col, "") or "").strip()
        if not fb:
            return "No Response"
        return classify_fn(r.get(feedback_col, ""), r.get(remark_col, ""))

    d["Status"] = d.apply(_row, axis=1)
    return d


def _prepare(dfs, hidden_columns):
    drop = set(INTERNAL_COLUMNS) | set(hidden_columns or [])
    out = {}
    for name, df in dfs.items():
        d = df.copy()
        d.columns = [str(c).strip() for c in d.columns]
        d = d.drop(columns=[c for c in d.columns if c in drop])
        for c in d.columns:
            if not pd.api.types.is_datetime64_any_dtype(d[c]) and d[c].dtype == object \
                    and re.search(r"date|time", c, re.I):
                conv = pd.to_datetime(d[c], errors="coerce", dayfirst=True)
                if conv.notna().mean() > 0.6:
                    d[c] = conv
        out[name] = d
    return out


def _schema_text(tables):
    lines = []
    for name, df in tables.items():
        lines.append(f'TABLE "{name}"  ({len(df)} rows)')
        for c in df.columns:
            s = df[c]
            if pd.api.types.is_datetime64_any_dtype(s):
                if s.notna().any():
                    lines.append(f'  - "{c}" (date) from {s.min():%Y-%m-%d} to {s.max():%Y-%m-%d}')
                else:
                    lines.append(f'  - "{c}" (date, empty)')
            elif pd.api.types.is_numeric_dtype(s):
                lines.append(f'  - "{c}" (number)')
            else:
                vals = s.dropna().astype(str).str.strip()
                vals = vals[vals != ""].unique()
                if len(vals) <= MAX_CATEGORY_VALUES:
                    lines.append(f'  - "{c}" (text) values: {list(vals)}')
                else:
                    lines.append(f'  - "{c}" (text, {len(vals)} distinct) e.g. {list(vals[:5])}')
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Claude calls
# ----------------------------------------------------------------------------
def _client():
    import anthropic
    key = st.secrets.get("ANTHROPIC_API_KEY", None)
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing in .streamlit/secrets.toml")
    return anthropic.Anthropic(api_key=key)


def _model():
    return st.secrets.get("SARAL_CHAT_MODEL", DEFAULT_MODEL)


def _ask_plan(question, tables, history, hint):
    system = PLAN_SYSTEM.format(today=dt.date.today().isoformat(),
                                hint=hint or "", schema=_schema_text(tables))
    msgs = []
    for h in history[-4:]:
        msgs.append({"role": "user", "content": h["q"]})
        msgs.append({"role": "assistant", "content": json.dumps(h["plan"])})
    msgs.append({"role": "user", "content": question})
    resp = _client().messages.create(model=_model(), max_tokens=1200, system=system, messages=msgs)
    text = "".join(b.text for b in resp.content if getattr(b, "text", None))
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Could not understand the question. Please rephrase.")
    return json.loads(m.group(0))


def _ask_summary(question, title, total, result):
    sample = result.head(MAX_ROWS_TO_AI).to_csv(index=False)
    if len(sample) > 12000:
        sample = sample[:12000]
    content = (f"Question: {question}\nResult title: {title}\n"
               f"Total rows in result: {total}\nFirst rows (CSV):\n{sample}")
    resp = _client().messages.create(model=_model(), max_tokens=500, system=SUMMARY_SYSTEM,
                                     messages=[{"role": "user", "content": content}])
    return "".join(b.text for b in resp.content if getattr(b, "text", None)).strip()


# ----------------------------------------------------------------------------
# Safe plan executor (no AI-generated code is ever run)
# ----------------------------------------------------------------------------
def _norm(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def _col(df, name):
    if name in df.columns:
        return name
    for c in df.columns:
        if c.lower().strip() == str(name).lower().strip():
            return c
    close = difflib.get_close_matches(str(name), list(df.columns), n=1, cutoff=0.7)
    if close:
        return close[0]
    raise KeyError(f'Column "{name}" not found')


def _text_mask(series, value, exact_first=True):
    """Exact match first, then 'contains', then spelling-tolerant (fuzzy) match."""
    ns = series.astype(str).map(_norm)
    nv = _norm(value)
    exact = ns == nv
    if exact_first and exact.any():
        return exact
    contains = ns.str.contains(re.escape(nv), na=False) if nv else exact
    if contains.any() or not exact_first or not nv:
        return contains
    close = difflib.get_close_matches(nv, ns.unique().tolist(), n=3, cutoff=0.75)
    return ns.isin(close) if close else contains


def _apply_filter(df, f):
    c = _col(df, f["column"])
    op, v, s = f["op"], f.get("value"), df[c]
    is_date = pd.api.types.is_datetime64_any_dtype(s)
    if op in ("isnull", "notnull"):
        blank = s.isna() | (s.astype(str).str.strip() == "")
        return df[blank] if op == "isnull" else df[~blank]
    if op == "between":
        lo, hi = v
        if is_date:
            return df[(s >= pd.to_datetime(lo)) & (s < pd.to_datetime(hi) + pd.Timedelta(days=1))]
        return df[(s >= lo) & (s <= hi)]
    if op in ("gt", "gte", "lt", "lte"):
        v = pd.to_datetime(v) if is_date else v
        return df[{"gt": s > v, "gte": s >= v, "lt": s < v, "lte": s <= v}[op]]
    if op == "contains":
        return df[_text_mask(s, v, exact_first=False)]
    if op in ("eq", "ne", "in"):
        vals = v if isinstance(v, list) else [v]
        if is_date:
            mask = s.isin(pd.to_datetime(vals))
        elif pd.api.types.is_numeric_dtype(s):
            mask = s.isin([float(x) for x in vals])
        else:
            mask = pd.Series(False, index=df.index)
            for x in vals:
                mask |= _text_mask(s, x)
        return df[~mask] if op == "ne" else df[mask]
    raise ValueError(f"Unsupported filter: {op}")


def _execute(plan, tables):
    name = plan.get("table")
    if name not in tables:
        name = next(iter(tables))
    df = tables[name]
    for f in plan.get("filters") or []:
        df = _apply_filter(df, f)

    group_by = [_col(df, g) for g in plan.get("group_by") or []]
    aggs = plan.get("aggregations") or []
    if group_by and aggs:
        spec = {}
        for a in aggs:
            func = a.get("func", "count")
            col = group_by[0] if a.get("column") in (None, "*") else _col(df, a["column"])
            spec[a.get("as") or f"{func}_{col}"] = pd.NamedAgg(column=col, aggfunc=func)
        result = df.groupby(group_by, dropna=False).agg(**spec).reset_index()
    elif group_by:
        result = df.groupby(group_by, dropna=False).size().reset_index(name="Count")
    else:
        result = df
        cols = [_col(df, c) for c in plan.get("columns") or []]
        if cols:
            result = df[cols]

    if plan.get("sort_by"):
        try:
            result = result.sort_values(_col(result, plan["sort_by"]),
                                        ascending=bool(plan.get("ascending", False)))
        except KeyError:
            pass
    elif group_by and len(result.columns) > len(group_by):
        result = result.sort_values(result.columns[-1], ascending=False)
    elif not group_by:
        dcols = [c for c in result.columns if pd.api.types.is_datetime64_any_dtype(result[c])]
        if dcols:
            result = result.sort_values(dcols[0])
    if plan.get("limit"):
        result = result.head(int(plan["limit"]))
    return result.reset_index(drop=True)


def _to_excel(df):
    buf = io.BytesIO()
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%d-%m-%Y").fillna("")
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        out.to_excel(xw, index=False, sheet_name="Result")
        ws = xw.sheets["Result"]
        for i, c in enumerate(out.columns, 1):
            longest = max([len(str(c))] + [len(str(v)) for v in out[c].head(200)])
            ws.column_dimensions[ws.cell(1, i).column_letter].width = min(50, longest + 2)
        ws.freeze_panes = "A2"
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Streamlit UI  (no st.rerun(), so the user stays on the same tab)
# ----------------------------------------------------------------------------
def _answer(question, tables, history, hint):
    try:
        plan = _ask_plan(question, tables, history, hint)
        if plan.get("clarification"):
            return {"q": question, "text": plan["clarification"]}
        result = _execute(plan, tables)
        title = plan.get("title") or "Result"
        history.append({"q": question, "plan": plan})
        if result.empty:
            note = ""
            src = tables.get(plan.get("table")) if plan.get("table") in tables else next(iter(tables.values()))
            dcols = [c for c in src.columns if pd.api.types.is_datetime64_any_dtype(src[c])]
            if dcols and src[dcols[0]].notna().any():
                note = f" The latest record in the data is dated {src[dcols[0]].max():%d-%m-%Y}."
            return {"q": question,
                    "text": f"No records found for: {title}.{note} Try a longer date range or another name."}
        return {"q": question, "text": _ask_summary(question, title, len(result), result),
                "table": result, "title": title}
    except Exception as e:
        msg = str(e)
        if "ANTHROPIC_API_KEY" in msg:
            return {"q": question,
                    "text": "🔧 The chatbot is not switched on yet. The app administrator must add the "
                            "ANTHROPIC_API_KEY in the app's Secrets settings. Please inform your administrator."}
        if isinstance(e, ModuleNotFoundError):
            return {"q": question,
                    "text": "🔧 The chatbot needs a software package that is not installed yet. "
                            "Please inform your administrator.", "error": msg}
        return {"q": question,
                "text": "Sorry, I could not answer that this time. Please try again in a few words, "
                        "for example: Engg pending deficiencies last 7 days.",
                "error": f"{type(e).__name__}: {msg}"}


def _show_turn(t, idx):
    st.markdown(f"**🧑 {t['q']}**")
    with st.container(border=True):
        st.markdown(t["text"])
        if t.get("error"):
            st.caption(f"Details: {t['error']}")
        tbl = t.get("table")
        if tbl is not None:
            st.caption(f"{t.get('title', 'Result')}  •  {len(tbl)} records")
            st.dataframe(tbl.head(MAX_ROWS_SHOWN), use_container_width=True, hide_index=True)
            if len(tbl) > MAX_ROWS_SHOWN:
                st.caption(f"Showing first {MAX_ROWS_SHOWN} rows. Download the sheet to get all rows.")
            st.download_button("⬇️ Download Excel sheet", data=_to_excel(tbl),
                               file_name=f"SARAL_{dt.date.today():%Y%m%d}_{idx}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key=f"saral_dl_{idx}", use_container_width=True)


def _clear_chat():
    st.session_state["saral_turns"] = []
    st.session_state["saral_hist"] = []


def render_saral_chatbot(dataframes: dict, title: str = "Ask SARAL",
                         domain_hint: str = SARAL_HINT, hidden_columns=None):
    """dataframes = {"Table name": DataFrame}.  Call inside your tab."""
    st.subheader(f"🤖 {title}")
    st.caption("Type your question in simple words (English / हिंदी / Hinglish). "
               "Every answer can be downloaded as an Excel sheet.")

    tables = _prepare(dataframes, hidden_columns)
    ss = st.session_state
    ss.setdefault("saral_turns", [])
    ss.setdefault("saral_hist", [])

    question = None
    with st.form("saral_chat_form", clear_on_submit=True):
        typed = st.text_input("Your question", placeholder="e.g. Sr DOM all deficiencies resolved from August to October")
        asked = st.form_submit_button("🔎 Ask", use_container_width=True)
    if asked and typed.strip():
        question = typed.strip()

    if not ss["saral_turns"] and not question:
        st.markdown("**Or tap an example:**")
        for i, ex in enumerate(EXAMPLES):
            if st.button(ex, key=f"saral_ex_{i}", use_container_width=True):
                question = ex

    if question:
        with st.spinner("Looking into SARAL data..."):
            ss["saral_turns"].append(_answer(question, tables, ss["saral_hist"], domain_hint))

    for i in range(len(ss["saral_turns"]) - 1, -1, -1):      # newest first
        _show_turn(ss["saral_turns"][i], i)

    if ss["saral_turns"]:
        st.button("🗑️ Clear chat", key="saral_clear", on_click=_clear_chat)
