"""
saral_chatbot.py  -  "Ask SARAL": plain-language AI assistant for the S.A.R.A.L Streamlit app.

WHAT THE USER GETS FOR EVERY QUESTION
  * A short answer in simple words
  * KPI cards (total / resolved / pending / no response / compliance %)
  * Charts (bar, stacked bar, donut, trend line) chosen automatically
  * Quick insights (oldest open item, worst department / officer / location ...)
  * The data table
  * Downloads: Excel sheet  AND  Word (.docx) report with charts
  * "Ask next" buttons with follow-up questions

NEW IN THIS VERSION
  * SMART ANALYSIS   "Smart analysis of Engg last 30 days"  -> Sub Head wise Resolved / Pending / No Response /
                     % Resolved (same numbers as the Smart Analysis tab) + detailed Excel (one sheet per Sub Head,
                     open items, full records).
  * INSPECTION REPORT "Inspection report of DRM/SUR yesterday" -> the same WhatsApp "Safety Inspection Report"
                     as the Inspections tab (copy / share on WhatsApp / .txt).  Needs report_builder=...
  * INSPECTIONS DATA  the Inspections tab data is also a table the AI can query ("who inspected most this month?").
  * FASTER           - the chat runs as a Streamlit fragment (a question no longer reruns the whole app)
                     - Groq (very fast) answers first, Gemini / Claude are the backups  (SARAL_AI_ORDER to change)
                     - smaller AI prompt (schema is cached), reused HTTP connection / AI client
                     - an AI that times out is skipped for 2 minutes instead of making every question wait
                     - Smart Analysis / Inspection report questions are understood by built-in rules (no AI wait)

HOW IT WORKS (safe by design)
  1. The AI sees ONLY column names + sample values (never the full data) and turns the question
     into a small JSON plan (filters, dates, group-by, action).
  2. This file runs that plan on your DataFrame with a fixed set of allowed operations.
     No AI-written code is ever executed.
  3. Charts, KPIs, insights, Excel and Word are all produced locally (free).

CALL IT FROM THE MAIN APP
    render_saral_chatbot({"Deficiencies": defi_df_with_Status, "Inspections": load_inspections_data()},
                         report_builder=build_whatsapp_message,
                         data_key=<any hashable that changes when the data changes>)   # optional, saves time

SETUP
    requirements.txt ->  google-genai, openpyxl, python-docx, plotly, matplotlib
    secrets (top of file, above every [section]):
        GEMINI_API_KEY = "AIza..."         optional: GEMINI_MODEL = "gemini-3.8-flash"
        GROQ_API_KEY   = "gsk_..."         optional: GROQ_MODEL   = "llama-3.3-70b-versatile"
        ANTHROPIC_API_KEY = "..."          (optional, needs the 'anthropic' package)
        SARAL_AI_ORDER = "groq,gemini,claude"   (default; first = tried first, the rest are backups)
        LLM_PROVIDER   = "gemini"          (optional: force one provider to go first)
    Groq needs no extra package (uses 'requests', which Streamlit already installs).

FREE-LIMIT FRIENDLY
    * Each question uses only ONE AI request (the answer text is written locally).
      Optional: SARAL_AI_SUMMARY = "true" in secrets adds an AI-written summary (a 2nd request).
    * Identical questions are remembered for the day and cost nothing.
    * If every AI is unavailable or over its free limit, "Basic mode" answers common questions
      with built-in rules (no AI, no limit).
"""

import difflib
import io
import json
import re
import time
import datetime as dt
from urllib.parse import quote

import pandas as pd
import streamlit as st

DEFAULT_MODEL = "claude-sonnet-5-5"           # used only if provider is Claude
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"     # override with GEMINI_MODEL in secrets
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"  # override with GROQ_MODEL in secrets
DEFAULT_ORDER = ("groq", "gemini", "claude")  # fastest first; change with SARAL_AI_ORDER
AI_TIMEOUT_S = 20                             # give up on a slow AI after this many seconds
MAX_ROWS_SHOWN = 500
MAX_ROWS_TO_AI = 40
MAX_ROWS_IN_WORD = 100
MAX_CATEGORY_VALUES = 45
MAX_REPORTS = 15                              # max WhatsApp reports built for one question
MAX_SUBHEAD_SHEETS = 30

INTERNAL_COLUMNS = ["_sheet_row", "_original_sheet_index", "_status_plain"]
STATUS_COLORS = {"Resolved": "#2e9e5b", "Pending": "#e0623b", "No Response": "#8a94a6"}
PALETTE = ["#2f6fb5", "#e0a030", "#7a5fb5", "#3aa5a5", "#c24d86", "#6b8e23"]
ROW_COLS_DOC = ["Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
                "Deficiencies Noted", "Inspection By", "Action By", "Feedback", "Status"]

_is_dt = pd.api.types.is_datetime64_any_dtype
_is_num = pd.api.types.is_numeric_dtype

# ----------------------------------------------------------------------------
# S.A.R.A.L specific knowledge, taken from the app code
# ----------------------------------------------------------------------------
SARAL_HINT = """
This is the S.A.R.A.L (Safety Abnormality Report & Action List) database of Solapur Division, Central Railway.
Each row of the main table is ONE deficiency noted during an inspection.

Column meanings:
- "Date of Inspection": date the inspection was done (default date for any date range in a question).
- "Type of Inspection": FOOTPLATE INSPECTION, STATION INSPECTION, LC GATE INSPECTION, COACHING DEPOT, ON TRAIN,
  SURPRISE/AMBUSH INSPECTION, WORKSITE INSPECTION, OTHER (UNUSUAL).
- "Location": station code (SUR, KWV, WADI...), level crossing gate (LC-40) or footplate section (SUR-DD).
- "Head": the DEPARTMENT. Values: ELECT/TRD, ELECT/G, ELECT/TRO, SIGNAL & TELECOM, OPTG, MECHANICAL, ENGINEERING,
  COMMERCIAL, C&W, PERSONNEL, SECURITY, FINANCE, MEDICAL, STORE, GSU.
- "Sub Head": category inside a department.
- "Deficiencies Noted": the text of the deficiency.
- "Inspection By": the officer who inspected (e.g. Sr.DOM, DRM/SUR, ADRM).
- "Action By": the officer RESPONSIBLE for fixing it (e.g. Sr.DOM, Sr.DEN/S, Sr.DSTE).
- "Feedback": compliance reply given by the department. "User Feedback/Remark": extra remark.
- "Timestamp of Compliance": when the compliance feedback was given.
- "Status": Resolved, Pending or No Response (No Response = no feedback given yet).

Second table "Inspections" = the Inspections tab (one row per deficiency of an inspection report):
"Date of Inspection", "Inspecting Official", "Designation & HQ", "Type of Inspection", "Location", "Head",
"Deficiency", "Action By", "Remarks". Use it for "how many inspections / which official inspected most" questions.

Interpretation rules:
- Department words map to "Head": Engg/Engineering/Track -> ENGINEERING, S&T/Signal/Telecom -> SIGNAL & TELECOM,
  Operating/Optg -> OPTG, Mech -> MECHANICAL, Elect TRD -> ELECT/TRD, Elect G -> ELECT/G, Elect TRO -> ELECT/TRO.
- Officer designations (Sr DOM, Sr DEN/S, DRM, Sr DSTE, ADEN...) in a question about deficiencies, pending work,
  or compliance mean "Action By", unless the user says "inspected by" / "inspection done by" (then use "Inspection By").
- "resolved / complied / closed / attended" -> Status = Resolved (op eq).
- IMPORTANT: in SARAL "pending / open / not done / outstanding" means NOT YET RESOLVED, i.e. Status in
  ["Pending","No Response"] (use op "in" with BOTH values), because a deficiency with no feedback yet is still pending.
  Only if the user says "pending with feedback / feedback given but pending" use Status eq Pending.
- ONLY when the user says "no reply / not responded / no feedback / no response" use Status = No Response (op eq).
- Date ranges refer to "Date of Inspection". Only if the user says "complied/resolved ON or DURING <dates>"
  use "Timestamp of Compliance" instead.
- "Deficiencies Noted" and "Feedback" are long text: for "related to <word>" questions use op "contains".
- For "all deficiencies" style questions return the full rows with these columns:
  Date of Inspection, Type of Inspection, Location, Head, Sub Head, Deficiencies Noted, Inspection By, Action By,
  Feedback, Status.
- "Analysis" / "Smart Analysis" of a department or officer: use action "smart_analysis" with the Head / Action By /
  date filters (it returns Sub Head wise Resolved / Pending / No Response and % resolved).
- "Inspection report" / "WhatsApp report" / "feedback of inspection": use action "inspection_report".
"""

EXAMPLES = [
    "Sr DOM all deficiencies resolved from August to October",
    "Smart analysis of Engg department last 30 days",
    "Inspection report of DRM/SUR yesterday",
    "Which department has the most pending deficiencies?",
    "Sr DSTE pending deficiencies of this month",
    "Which official did the most inspections this month?",
]

PLAN_SYSTEM = """You convert a railway safety inspection question into a JSON query plan.
Today's date is {today}. Reply with ONE JSON object only, no other text.

{hint}

Available tables and columns (with sample values):
{schema}

JSON format:
{{
  "action": "query",
  "table": "<table name>",
  "filters": [{{"column": "<col>", "op": "<op>", "value": <value>}}],
  "group_by": ["<col>"],
  "aggregations": [{{"column": "<col or *>", "func": "count|sum|mean|min|max|nunique", "as": "<name>"}}],
  "columns": ["<cols to show>"],
  "sort_by": "<col or null>",
  "ascending": false,
  "limit": null,
  "chart": "auto",
  "report": null,
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
- "action" is "query" for normal questions.
  "smart_analysis" when the user asks for Smart Analysis, or an analysis / summary of a department or officer:
  put the department / officer / date filters in "filters" (table = the deficiencies table); leave group_by empty
  for Sub Head wise, or use ["Head"] / ["Location"] / ["Action By"] to compare those instead.
  "inspection_report" when the user wants an inspection report / WhatsApp report / feedback of an inspection
  (table "Inspections"): set "report" to {{"who": "<inspecting official name or designation such as DRM/SUR, or empty>",
  "location": "<or empty>", "from": "YYYY-MM-DD or empty", "to": "YYYY-MM-DD or empty"}};
  leave from / to empty when no date is mentioned (the latest inspection date is used).
- For "analysis"/"summary"/"department wise" questions use group_by + aggregations.
- For "show/list/give me all" questions leave group_by and aggregations empty so full rows come back.
- "chart" is "auto" normally; "pie" if the user asks for a pie chart; "line" for trends; "none" only if the user
  says no chart.
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
Use only the numbers given. Do not invent anything. No tables, no markdown headings.
Then, on a NEW LAST LINE, write exactly:
FOLLOWUPS: <question 1> | <question 2> | <question 3>
These are three short, natural follow-up questions the user could ask next about the same data
(for example narrowing to pending only, another department, or a longer period), in the user's language style."""


# ----------------------------------------------------------------------------
# Data preparation
# ----------------------------------------------------------------------------
# Same department clean-up your Analytics tab uses (Head_std), so counts match the app.
_DEPT_MAP = {
    "ENGINEERING": "ENGINEERING", "GSU": "GSU", "ELECT/G": "ELECT/G", "ELECTG": "ELECT/G",
    "ELECT/TRD": "ELECT/TRD", "ELECT/TRO": "ELECT/TRO", "OPTG": "OPTG", "OPERATING": "OPTG",
    "SIGNAL & TELECOM": "SIGNAL & TELECOM", "MECHANICAL": "MECHANICAL", "COMMERCIAL": "COMMERCIAL",
    "C&W": "C&W", "SECURITY": "SECURITY", "PERSONNEL": "PERSONNEL", "MEDICAL": "MEDICAL",
    "FINANCE": "FINANCE", "STORE": "STORE",
}


def _clean_for_chat(d):
    d = d.copy()
    if "Head" in d.columns:
        h = (d["Head"].fillna("").astype(str).str.replace(r"[\*\-\_\'\"]", "", regex=True)
             .str.replace(r"\s+", " ", regex=True).str.strip().str.upper())
        d["Head"] = h.map(lambda x: _DEPT_MAP.get(x, x or "UNKNOWN"))
    for c in ("Action By", "Inspection By", "Sub Head", "Type of Inspection", "Location"):
        if c in d.columns:
            d[c] = d[c].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    return d


def add_status(df, classify_fn, feedback_col="Feedback", remark_col="User Feedback/Remark"):
    """Adds Status (Resolved / Pending / No Response) exactly like your Smart Analysis tab, and cleans the
    department names exactly like your Analytics tab. Call it with your app's classify_feedback."""
    return _clean_for_chat(_add_status_core(df, classify_fn, feedback_col, remark_col))


def _add_status_core(df, classify_fn, feedback_col="Feedback", remark_col="User Feedback/Remark"):
    """Add the same Resolved / Pending / No Response Status used in Smart Analysis.
    classify_fn = your app's classify_feedback(feedback, remark)."""
    d = df.copy()

    def _row(r):
        fb = str(r.get(feedback_col, "") or "").strip()
        if not fb or fb == "`":
            return "No Response"
        s = classify_fn(r.get(feedback_col, ""), r.get(remark_col, ""))
        return s if s in ("Resolved", "Pending") else "Pending"

    key = None
    try:                                    # same data as last time -> reuse the Status column (big time saver)
        cols = [c for c in (feedback_col, remark_col) if c in df.columns]
        key = (len(df), tuple(df.columns), int(pd.util.hash_pandas_object(df[cols].astype(str), index=False).sum()))
    except Exception:
        pass
    if key is not None and key in _STATUS_CACHE:
        d["Status"] = _STATUS_CACHE[key]
        return d
    d["Status"] = d.apply(_row, axis=1)
    if key is not None:
        _STATUS_CACHE.clear()
        _STATUS_CACHE[key] = d["Status"].tolist()
    return d


def _prepare(dfs, hidden_columns):
    drop = set(INTERNAL_COLUMNS) | set(hidden_columns or [])
    out = {}
    for name, df in dfs.items():
        d = df.copy()
        d.columns = [str(c).strip() for c in d.columns]
        d = d.drop(columns=[c for c in d.columns if c in drop])
        for c in d.columns:
            if not _is_dt(d[c]) and d[c].dtype == object and re.search(r"date|time", c, re.I):
                conv = pd.to_datetime(d[c], errors="coerce", dayfirst=True)
                if conv.notna().mean() > 0.6:
                    d[c] = conv
        out[name] = d
    return out


def _norm_insp_raw(raw):
    """Inspections-tab frame (from load_inspections_data) cleaned for report building."""
    if raw is None or len(raw) == 0:
        return None
    d = raw.copy()
    for c in ["Name", "Phone", "Type", "Location", "Deficiency", "InspectionBy", "ActionBy", "Remarks", "Head"]:
        if c not in d.columns:
            d[c] = ""
        d[c] = d[c].fillna("").astype(str).str.strip()
    if "Date_parsed" not in d.columns:
        d["Date_parsed"] = pd.to_datetime(d.get("Date"), errors="coerce", dayfirst=True)
    d["Date_parsed"] = pd.to_datetime(d["Date_parsed"], errors="coerce")
    d = d[d["Date_parsed"].notna()].reset_index(drop=True)
    return d if len(d) else None


def _insp_table(raw):
    """Readable version of the Inspections data that the AI can query."""
    return pd.DataFrame({
        "Date of Inspection": raw["Date_parsed"],
        "Inspecting Official": raw["Name"],
        "Designation & HQ": raw["InspectionBy"],
        "Type of Inspection": raw["Type"],
        "Location": raw["Location"].str.upper(),
        "Head": raw["Head"],
        "Deficiency": raw["Deficiency"],
        "Action By": raw["ActionBy"],
        "Remarks": raw["Remarks"],
    })


def _with_insp_table(dfs):
    """Returns (tables-dict with the Inspections table made readable, raw inspections frame or None)."""
    out = {k: v for k, v in dfs.items() if k != "Inspections"}
    raw = _norm_insp_raw(dfs.get("Inspections"))
    if raw is not None:
        out["Inspections"] = _insp_table(raw)
    return out, raw


def _schema_text(tables):
    lines = []
    for name, df in tables.items():
        lines.append(f'TABLE "{name}"  ({len(df)} rows)')
        for c in df.columns:
            s = df[c]
            if _is_dt(s):
                if s.notna().any():
                    lines.append(f'  - "{c}" (date) from {s.min():%Y-%m-%d} to {s.max():%Y-%m-%d}')
                else:
                    lines.append(f'  - "{c}" (date, empty)')
            elif _is_num(s):
                lines.append(f'  - "{c}" (number)')
            else:
                vals = s.dropna().astype(str).str.strip()
                vals = vals[vals != ""]
                uniq = vals.unique()
                if len(vals) and vals.head(300).str.len().mean() > 60:
                    lines.append(f'  - "{c}" (long text)')
                elif len(uniq) <= MAX_CATEGORY_VALUES:
                    lines.append(f'  - "{c}" (text) values: {[x[:40] for x in uniq]}')
                else:
                    lines.append(f'  - "{c}" (text, {len(uniq)} distinct) e.g. {[x[:30] for x in uniq[:4]]}')
    return "\n".join(lines)


def _schema_cached(tables):
    """The schema text only changes when the data changes - build it once, not for every question."""
    if _PREP_CACHE.get("val") is tables:
        if not _PREP_CACHE.get("schema"):
            _PREP_CACHE["schema"] = _schema_text(tables)
        return _PREP_CACHE["schema"]
    return _schema_text(tables)


# ----------------------------------------------------------------------------
# AI calls (Groq / Gemini / Claude, each backing up the others)
# ----------------------------------------------------------------------------
_SECRET_CACHE = {}


def _secret_lookup(name):
    """Read a secret. Also finds it if it was accidentally pasted inside a [section] of secrets.toml
    (a very common mistake: anything below a [section] header belongs to that section)."""
    try:
        v = st.secrets.get(name)
        if v:
            return v
        for k in st.secrets:
            sec = st.secrets[k]
            items = sec if isinstance(sec, (list, tuple)) else [sec]
            for it in items:
                if hasattr(it, "get") and not isinstance(it, str):
                    v = it.get(name)
                    if v:
                        return v
    except Exception:
        pass
    return None


def _secret(name):
    hit = _SECRET_CACHE.get(name)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    v = _secret_lookup(name)
    _SECRET_CACHE[name] = (time.time(), v)
    return v


def _http():
    """One shared HTTP session = no new TLS handshake for every AI call."""
    if "http" not in _STATE:
        import requests
        _STATE["http"] = requests.Session()
    return _STATE["http"]


def _gem_generate(client, types, cfg, model, contents, config):
    """Gemini call. Asks for LOW 'thinking' (much faster); falls back to a plain call if the model/SDK rejects it."""
    if _STATE.get("gem_think", True):
        try:
            c2 = dict(cfg, thinking_config=types.ThinkingConfig(thinking_level="low"))
            return client.models.generate_content(model=model, contents=contents,
                                                  config=types.GenerateContentConfig(**c2))
        except Exception as e:
            m = str(e)
            if _is_limit_error(m) or any(x in m for x in ("404", "NOT_FOUND", "401", "403", "PERMISSION", "API key")):
                raise
            _STATE["gem_think"] = False
    return client.models.generate_content(model=model, contents=contents, config=config)


def _llm_single(provider, system, messages, max_tokens, json_mode=False):
    """One text-in / text-out call. messages = [{"role": "user"|"assistant", "content": str}]"""
    if provider == "gemini":
        key = _secret("GEMINI_API_KEY") or _secret("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is missing in Secrets")
        from google import genai
        from google.genai import types
        client = _STATE.get("gem_client")
        if client is None or _STATE.get("gem_key") != key:
            try:
                client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=AI_TIMEOUT_S * 1000))
            except Exception:
                client = genai.Client(api_key=key)
            _STATE["gem_client"], _STATE["gem_key"] = client, key
        contents = [{"role": "user" if m["role"] == "user" else "model",
                     "parts": [{"text": m["content"]}]} for m in messages]
        cfg = dict(system_instruction=system,
                   max_output_tokens=max(max_tokens * 4, 4096),   # room for the model's own thinking
                   temperature=0.1)
        if json_mode:
            cfg["response_mime_type"] = "application/json"
        resp = _gem_generate(client, types, cfg,
            model=_secret("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(**cfg))
        return (resp.text or "").strip()

    if provider == "groq":
        key = _secret("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is missing in Secrets")
        payload = {"model": _secret("GROQ_MODEL") or DEFAULT_GROQ_MODEL, "temperature": 0.1,
                   "max_tokens": max(max_tokens, 1500),
                   "messages": [{"role": "system", "content": system}] + messages}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        url, headers = "https://api.groq.com/openai/v1/chat/completions", {"Authorization": f"Bearer {key}"}
        r = _http().post(url, headers=headers, json=payload, timeout=AI_TIMEOUT_S)
        if r.status_code == 400 and json_mode and "json" in r.text.lower():
            payload.pop("response_format", None)               # model refused JSON mode: retry plainly
            r = _http().post(url, headers=headers, json=payload, timeout=AI_TIMEOUT_S)
        if r.status_code != 200:
            raise RuntimeError(f"Groq {r.status_code}: {r.text[:300]}")
        return (r.json()["choices"][0]["message"]["content"] or "").strip()

    key = _secret("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing in Secrets")
    import anthropic
    resp = anthropic.Anthropic(api_key=key, timeout=AI_TIMEOUT_S).messages.create(
        model=_secret("SARAL_CHAT_MODEL") or DEFAULT_MODEL,
        max_tokens=max_tokens, system=system, messages=messages)
    return "".join(b.text for b in resp.content if getattr(b, "text", None)).strip()


def _providers():
    """AI providers that have a key, in the order they are tried (fastest first by default)."""
    avail = {"gemini": bool(_secret("GEMINI_API_KEY") or _secret("GOOGLE_API_KEY")),
             "groq": bool(_secret("GROQ_API_KEY")),
             "claude": bool(_secret("ANTHROPIC_API_KEY"))}
    cfg = str(_secret("SARAL_AI_ORDER") or "").lower()
    pref = [p.strip() for p in cfg.split(",") if p.strip() in avail] or list(DEFAULT_ORDER)
    order = [p for p in pref if avail[p]] + [p for p in DEFAULT_ORDER if avail[p] and p not in pref]
    forced = str(_secret("LLM_PROVIDER") or "").strip().lower()
    if forced in avail and avail[forced]:
        order = [forced] + [p for p in order if p != forced]
    return order


def _is_limit_error(msg):
    m = str(msg).lower()
    return "429" in m or "resource_exhausted" in m or "quota" in m or "rate limit" in m


def _is_timeout_error(msg):
    m = str(msg).lower()
    return "timed out" in m or "timeout" in m or "deadline" in m


def _llm(system, messages, max_tokens, json_mode=False):
    """Try each AI that has a key; if one hits its limit or is slow, the next one answers."""
    order = _providers()
    if not order:
        raise RuntimeError("GEMINI_API_KEY is missing in Secrets")
    last, tried, limited = None, 0, 0
    for p in order:
        if time.time() < _STATE.get("off_" + p, 0):
            continue
        tried += 1
        try:
            out = _llm_single(p, system, messages, max_tokens, json_mode)
            _STATE["used"] = p
            return out
        except Exception as e:
            last = e
            if _is_limit_error(e):
                limited += 1
                _STATE["off_" + p] = time.time() + 900     # rest this AI for 15 minutes
            elif _is_timeout_error(e):
                _STATE["off_" + p] = time.time() + 120     # slow right now: skip it for 2 minutes
    if tried == 0 or limited == tried:
        raise RuntimeError("429 RESOURCE_EXHAUSTED: all AI free limits are used up")
    raise last


def _ask_plan(question, tables, history, hint):
    system = PLAN_SYSTEM.format(today=dt.date.today().isoformat(),
                                hint=hint or "", schema=_schema_cached(tables))
    msgs = []
    for h in history[-4:]:
        msgs.append({"role": "user", "content": h["q"]})
        msgs.append({"role": "assistant", "content": json.dumps(h["plan"], default=str)})
    msgs.append({"role": "user", "content": question})
    text = _llm(system, msgs, 1200, json_mode=True)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Could not understand the question. Please rephrase.")
    plan = json.loads(m.group(0))
    plan.setdefault("action", "query")
    return plan


def _split_followups(text):
    m = re.search(r"FOLLOWUPS:\s*(.+)$", text, re.S | re.I)
    if not m:
        return text.strip(), []
    body = text[:m.start()].strip()
    fu = [x.strip(" -•*\n") for x in m.group(1).split("|") if x.strip(" -•*\n")]
    return body, fu[:3]


def _ask_summary(question, title, total, result):
    sample = result.head(MAX_ROWS_TO_AI).to_csv(index=False)
    if len(sample) > 12000:
        sample = sample[:12000]
    content = (f"Question: {question}\nResult title: {title}\n"
               f"Total rows in result: {total}\nFirst rows (CSV):\n{sample}")
    return _split_followups(_llm(SUMMARY_SYSTEM, [{"role": "user", "content": content}], 500))


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
    is_date = _is_dt(s)
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
        elif _is_num(s):
            mask = s.isin([float(x) for x in vals])
        else:
            mask = pd.Series(False, index=df.index)
            for x in vals:
                mask |= _text_mask(s, x)
        return df[~mask] if op == "ne" else df[mask]
    raise ValueError(f"Unsupported filter: {op}")


def _fix_status_filter(f):
    """In SARAL, 'Pending' = Pending + No Response (no feedback yet is still pending)."""
    if f.get("column") == "Status" and f.get("op") in ("eq", "in"):
        vals = f["value"] if isinstance(f["value"], list) else [f["value"]]
        if [str(v).strip().lower() for v in vals] == ["pending"]:
            return dict(f, op="in", value=["Pending", "No Response"])
    return f


def _filtered(plan, tables):
    name = plan.get("table")
    if name not in tables:
        name = next(iter(tables))
    df = tables[name]
    for f in plan.get("filters") or []:
        df = _apply_filter(df, _fix_status_filter(f))
    return df


def _execute(plan, tables):
    df = _filtered(plan, tables)

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
        dcols = [c for c in result.columns if _is_dt(result[c])]
        if dcols:
            result = result.sort_values(dcols[0])
    if plan.get("limit"):
        result = result.head(int(plan["limit"]))
    return result.reset_index(drop=True)


# ----------------------------------------------------------------------------
# SMART ANALYSIS  (same buckets as the Smart Analysis tab: Resolved / Pending / No Response)
# ----------------------------------------------------------------------------
def _smart_analysis(plan, tables):
    """Returns (summary table, working rows, group column, rows left out because the group value was blank)."""
    name = plan.get("table")
    if name not in tables or "Status" not in tables[name].columns:
        name = next((n for n, d in tables.items() if "Status" in d.columns), next(iter(tables)))
    df = tables[name]
    for f in plan.get("filters") or []:
        df = _apply_filter(df, _fix_status_filter(f))
    gb = [g for g in (plan.get("group_by") or []) if str(g).lower() != "status"]
    key = _col(df, gb[0]) if gb else "Sub Head"
    if key not in df.columns:
        key = "Head"
    work = df.copy()
    work[key] = work[key].fillna("").astype(str).str.strip()
    excluded = int((work[key] == "").sum())
    work = work[work[key] != ""].copy()
    if work.empty:
        return pd.DataFrame(), work, key, excluded
    work["Status"] = work["Status"].fillna("Pending")
    pv = pd.crosstab(work[key], work["Status"])
    for c in ("Resolved", "Pending", "No Response"):
        if c not in pv.columns:
            pv[c] = 0
    pv["Total"] = pv[["Resolved", "Pending", "No Response"]].sum(axis=1)
    pv["% Resolved"] = (pv["Resolved"] / pv["Total"] * 100).round(1)
    pv = pv.rename_axis(columns=None).reset_index().sort_values("Total", ascending=False)
    pv = pv[[key, "Total", "Resolved", "Pending", "No Response", "% Resolved"]].reset_index(drop=True)
    return pv, work, key, excluded


def _smart_summary(title, pv, work, key, excluded):
    tot = len(work)
    cnt = work["Status"].value_counts()
    res, pend, nr = int(cnt.get("Resolved", 0)), int(cnt.get("Pending", 0)), int(cnt.get("No Response", 0))
    lines = [f"**{tot} deficiencies** analysed: {title}.",
             f"Resolved **{res}** ({round(100 * res / tot, 1)}%) · Pending **{pend}** · No Response **{nr}** "
             f"→ **{pend + nr} not yet resolved**."]
    d = pv.assign(Open=pv["Pending"] + pv["No Response"])
    top = d[d["Open"] > 0].sort_values("Open", ascending=False).head(3)
    if not top.empty:
        lines.append(f"Most open items ({key}): " + ", ".join(f"{r[key]} ({int(r['Open'])})" for _, r in top.iterrows()) + ".")
    if excluded:
        lines.append(f"({excluded} records with a blank {key} are not included, same as the Smart Analysis tab.)")
    return "\n\n".join(lines)


def _smart_insights(pv, work, key):
    out = []
    big = pv[pv["Total"] >= 3].sort_values(["% Resolved", "Total"], ascending=[True, False])
    if len(big) > 1:
        r = big.iloc[0]
        out.append(f"Lowest compliance: **{r[key]}** — {r['% Resolved']}% resolved ({int(r['Resolved'])} of {int(r['Total'])})")
        r = big.sort_values(["% Resolved", "Total"], ascending=[False, False]).iloc[0]
        out.append(f"Best compliance: **{r[key]}** — {r['% Resolved']}% resolved ({int(r['Resolved'])} of {int(r['Total'])})")
    try:
        out += [s for s in _insights(work) if "Oldest open" in s or "older than" in s]
    except Exception:
        pass
    return out


def _smart_specs(pv, key):
    d = pv.head(15).melt(id_vars=[key], value_vars=["Resolved", "Pending", "No Response"],
                         var_name="Status", value_name="Count")
    return [dict(kind="stacked", df=d, cat=key, val="Count", color="Status", title=f"Status by {key}")]


def _safe_sheet_name(name, used):
    base = "".join("_" if ch in "[]:*?/\\" else ch for ch in str(name).strip()) or "Sheet"
    base = base[:28]
    cand, i = base, 2
    while cand in used:
        suffix = f"_{i}"
        cand = base[:31 - len(suffix)] + suffix
        i += 1
    used.add(cand)
    return cand


def _smart_workbook(pv, work, key):
    """Summary + OPEN_ITEMS + one sheet per Sub Head + FULL_RECORDS (like the Smart Analysis downloads)."""
    out = work.copy()
    for c in out.columns:
        if _is_dt(out[c]):
            out[c] = out[c].dt.strftime("%d-%m-%Y").fillna("")
    used = set()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pv.to_excel(xw, sheet_name=_safe_sheet_name("Summary", used), index=False)
        out[out["Status"].isin(["Pending", "No Response"])].to_excel(
            xw, sheet_name=_safe_sheet_name("OPEN_ITEMS", used), index=False)
        for v in pv[key].tolist()[:MAX_SUBHEAD_SHEETS]:
            out[out[key] == v].to_excel(xw, sheet_name=_safe_sheet_name(v, used), index=False)
        out.to_excel(xw, sheet_name=_safe_sheet_name("FULL_RECORDS", used), index=False)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# INSPECTION REPORTS  (the same WhatsApp report as the Inspections tab)
# ----------------------------------------------------------------------------
def _report_rows(insp, who, location, d_from, d_to):
    d = insp
    whos = [w for w in (who if isinstance(who, (list, tuple)) else [who]) if str(w or "").strip()]
    if whos:
        nn, nd = d["Name"].map(_norm), d["InspectionBy"].map(_norm)
        mask = pd.Series(False, index=d.index)
        for w in whos:
            q = _norm(w)
            if q:
                mask |= nn.str.contains(q, regex=False) | nd.str.contains(q, regex=False)
        if not mask.any():                                   # spelling-tolerant fallback
            pool = list(set(nn) | set(nd))
            close = [c for w in whos for c in difflib.get_close_matches(_norm(w), pool, n=3, cutoff=0.75)]
            mask = nn.isin(close) | nd.isin(close)
        d = d[mask]
    if str(location or "").strip():
        d = d[_text_mask(d["Location"], str(location))]
    date_note = ""
    if str(d_from or "").strip() or str(d_to or "").strip():
        dp = d["Date_parsed"]
        if str(d_from or "").strip():
            d = d[dp >= pd.Timestamp(d_from)]
            dp = d["Date_parsed"]
        if str(d_to or "").strip():
            d = d[dp < pd.Timestamp(d_to) + pd.Timedelta(days=1)]
    elif len(d):
        latest = d["Date_parsed"].max()
        d = d[d["Date_parsed"].dt.normalize() == latest.normalize()]
        date_note = f"latest inspection date ({latest:%d %b %Y})"
    return d, date_note


def _build_reports(insp, builder, who, location, d_from, d_to):
    """Returns (list of (title, message), info)."""
    d, date_note = _report_rows(insp, who, location, d_from, d_to)
    info = {"groups": 0, "date_note": date_note}
    if d.empty:
        return [], info
    d = d.assign(Date_str=d["Date_parsed"].dt.strftime("%Y-%m-%d"))
    groups = list(d.groupby(["Name", "Phone", "Date_str"], sort=True))
    info["groups"] = len(groups)
    reports = []
    for (name, phone, dstr), sub in groups[:MAX_REPORTS]:
        ds = sub["InspectionBy"][sub["InspectionBy"].str.strip() != ""]
        desig = ds.iloc[0] if not ds.empty else ""
        sections = []
        for (typ, loc), rows in sub.groupby(["Type", "Location"], sort=False):
            defs = [(r["Deficiency"].strip(), r["ActionBy"].strip(), r["Remarks"].strip())
                    for _, r in rows.iterrows() if r["Deficiency"].strip()]
            if defs:
                sections.append((typ, loc, defs))
        if sections:
            n_def = sum(len(x[2]) for x in sections)
            reports.append((f"{name or 'Unknown'} • {dstr} • {len(sections)} inspection(s), {n_def} deficiencies",
                            builder(name, phone, desig, dstr, sections)))
    return reports, info


def _answer_report(question, plan, ctx, history, t0, note):
    insp, builder = ctx.get("insp"), ctx.get("builder")
    if insp is None or builder is None:
        return {"q": question, "note": note,
                "text": "Inspection reports are not available right now (the Inspections data or report "
                        "builder was not passed to the chatbot). Please inform your administrator."}
    r = plan.get("report") or {}
    reports, info = _build_reports(insp, builder, r.get("who"), r.get("location"), r.get("from"), r.get("to"))
    history.append({"q": question, "plan": plan})
    title = plan.get("title") or "Inspection report"
    if not reports:
        latest = insp["Date_parsed"].max()
        return {"q": question, "note": note, "explain": _explain_plan(plan),
                "text": f"No inspections found for: {title}. The latest inspection in the Inspections tab is dated "
                        f"{latest:%d-%m-%Y}. Try another date, name or location."}
    where = f" for the {info['date_note']}" if info["date_note"] else ""
    text = f"**{len(reports)} inspection report(s)** ready{where}: {title}. Copy the message or share it on WhatsApp."
    if info["groups"] > len(reports):
        text += f"\n\nShowing the first {len(reports)} of {info['groups']} reports. Add a name, location or date to narrow it down."
    return {"q": question, "text": text, "reports": reports, "title": title, "note": note,
            "secs": round(time.time() - t0, 1), "explain": _explain_plan(plan),
            "followups": _local_followups(plan, "basic")}


def _answer_smart(question, plan, tables, history, t0, note, ai_s):
    pv, work, key, excluded = _smart_analysis(plan, tables)
    history.append({"q": question, "plan": plan})
    title = plan.get("title") or "Smart Analysis"
    if pv.empty:
        return {"q": question, "note": note,
                "text": f"No records found for: {title}. Try a longer date range or another name."}
    turn = {"q": question, "text": _smart_summary(title, pv, work, key, excluded), "table": pv, "title": title,
            "followups": _local_followups(plan, "basic"), "grouped": True, "specs": _smart_specs(pv, key),
            "note": note, "secs": round(time.time() - t0, 1), "ai_secs": ai_s, "explain": _explain_plan(plan),
            "kpis": _kpis(work), "insights": _smart_insights(pv, work, key),
            "detail": (pv, work, key)}
    turn["xlsx"] = _to_excel(pv)
    return turn


# ----------------------------------------------------------------------------
# Basic mode: answers common questions with NO AI (used automatically when the AI is
# unavailable or its free daily limit is used up). Also: plan cache, local summary.
# ----------------------------------------------------------------------------
_STATE = {}            # shared by all users: when an AI limit was hit, shared clients
_PLAN_CACHE = {}       # same question on the same day = no new AI request
_STATUS_CACHE = {}
_PREP_CACHE = {}

_MONTHS = {"january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
           "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8,
           "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11, "nov": 11,
           "december": 12, "dec": 12}
_MON_RX = "|".join(sorted(_MONTHS, key=len, reverse=True))

_DEPT_WORDS = {
    "ENGINEERING": ["engg", "engr", "eng", "enginering", "engineering", "track", "pway"],
    "SIGNAL & TELECOM": ["snt", "s&t", "s and t", "signal", "telecom", "tele"],
    "OPTG": ["optg", "opt", "ops", "operating", "operation", "operations"],
    "MECHANICAL": ["mech", "mechanical", "mechnical"],
    "COMMERCIAL": ["comm", "comml", "commercial"],
    "ELECT/TRD": ["trd"],
    "ELECT/G": ["elect g", "elec g"],
    "ELECT/TRO": ["tro"],
    "PERSONNEL": ["pers", "personnel", "personal"],
    "SECURITY": ["sec", "rpf", "security"],
    "MEDICAL": ["med", "medical"],
    "STORE": ["store", "stores"],
    "FINANCE": ["finance", "accounts"],
    "C&W": ["c&w", "cnw", "c and w", "carriage", "wagon"],
}

_BASIC_HELP = ("I can answer questions like:\n\n"
               "- Sr DOM all deficiencies resolved from August to October\n"
               "- Smart analysis of Engg department last 30 days\n"
               "- Inspection report of DRM/SUR yesterday\n"
               "- Which department has most pending deficiencies this month\n\n"
               "Please type your question with a department or officer, a status (pending / resolved) "
               "and a period (last 7 days, this month, August to October).")

_REPORT_RX = re.compile(r"insp\w*\s+(?:report|reports|rpt|feedback)|whats ?app\s+(?:report|message|msg)"
                        r"|feedback\s+of\s+(?:\w+\s+){0,3}insp")
_SMART_RX = re.compile(r"smart ?analy")
_FAST_RX = re.compile(_REPORT_RX.pattern + "|" + _SMART_RX.pattern)


def _prepare_cached(dfs, hidden, data_key=None):
    """Returns (tables, raw inspections frame). _prepare() copies the data and parses dates; do it only when the
    data really changed. If data_key is given it is used instead of hashing every cell (much faster)."""
    try:
        if data_key is not None:
            key = ("dk", data_key, tuple(hidden or []))
        else:
            key = tuple((n, d.shape, tuple(d.columns), int(pd.util.hash_pandas_object(d, index=False).sum()))
                        for n, d in dfs.items()) + (tuple(hidden or []),)
    except Exception:
        key = None
    if key is not None and _PREP_CACHE.get("key") == key:
        return _PREP_CACHE["val"], _PREP_CACHE.get("insp")
    conv, raw = _with_insp_table(dfs)
    tables = _prepare(conv, hidden)
    _PREP_CACHE.update(key=key, val=tables, insp=raw, schema=None)
    return tables, raw


def _ai_available():
    order = _providers()
    return not order or any(time.time() >= _STATE.get("off_" + p, 0) for p in order)


def _ask_plan_cached(question, tables, history, hint):
    last = json.dumps(history[-1]["plan"], sort_keys=True, default=str) if history else ""
    key = (re.sub(r"\s+", " ", question.strip().lower()), dt.date.today().isoformat(), last,
           tuple(len(d) for d in tables.values()))
    if key in _PLAN_CACHE:
        return json.loads(json.dumps(_PLAN_CACHE[key]))
    plan = _ask_plan(question, tables, history, hint)
    if len(_PLAN_CACHE) > 500:
        _PLAN_CACHE.clear()
    _PLAN_CACHE[key] = json.loads(json.dumps(plan))
    return plan


def _month_end(y, m):
    first_next = dt.date(y + (m == 12), (m % 12) + 1, 1)
    return first_next - dt.timedelta(days=1)


def _explicit_dates(ql):
    """'15/11/2026', '15 11 2026', '15 nov', '3rd march 2026'  -> (first, last) or None."""
    today = dt.date.today()
    found = []
    for d_, m_, y_ in re.findall(r"\b(\d{1,2})[/ ](\d{1,2})[/ ](20\d{2})\b", ql):
        try:
            found.append(dt.date(int(y_), int(m_), int(d_)))
        except ValueError:
            pass
    pat = r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MON_RX + r")[a-z]*(?:\s+(20\d{2}))?\b"
    for d_, mon, y_ in re.findall(pat, ql):
        y = int(y_) if y_ else today.year
        try:
            d = dt.date(y, _MONTHS[mon], int(d_))
            if not y_ and d > today:
                d = d.replace(year=y - 1)
        except ValueError:
            continue
        found.append(d)
    return (min(found), max(found)) if found else None


def _rule_dates(ql):
    """Return (from_date, to_date) or None."""
    today = dt.date.today()
    one = dt.timedelta(days=1)
    ex = _explicit_dates(ql)
    if ex:
        return ex
    m = re.search(r"\b(?:last|past|previous|pichle)\s+(\d+)\s*(day|days|dys|din|week|weeks|wk|wks|month|months)\b", ql)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = n * (7 if unit.startswith("w") else 30 if unit.startswith("m") else 1)
        return today - dt.timedelta(days=days - 1), today
    if re.search(r"\byesterday\b", ql):
        return today - one, today - one
    if re.search(r"\btoday\b", ql):
        return today, today
    if re.search(r"\b(last|previous)\s+month\b", ql):
        end = today.replace(day=1) - one
        return end.replace(day=1), end
    if re.search(r"\b(this|current)\s+month\b", ql):
        return today.replace(day=1), today
    if re.search(r"\bweek\b|\bwk\b|\bwek\b", ql):
        return today - dt.timedelta(days=6), today
    found = re.findall(r"\b(" + _MON_RX + r")\b", ql)
    if found:
        m1, m2 = _MONTHS[found[0]], _MONTHS[found[-1]]
        y1 = today.year if m1 <= today.month else today.year - 1
        y2 = y1 if m2 >= m1 else y1 + 1
        start, end = dt.date(y1, m1, 1), min(_month_end(y2, m2), today)
        if start <= end:
            return start, end
    return None


def _find_officer(ql, df, col, split_slash=False):
    toks = [_norm(t) for t in ql.split() if _norm(t)]
    cand = set(toks) | {a + b for a, b in zip(toks, toks[1:])} | {a + b + c for a, b, c in zip(toks, toks[1:], toks[2:])}
    best_len, hits = 0, []
    for v in df[col].dropna().astype(str).unique():
        n = _norm(v)
        variants = {n: v}
        if n.startswith("sr") and len(n) > 4:
            variants[n[2:]] = n[2:]
        if split_slash and "/" in str(v):
            first = _norm(str(v).split("/")[0])
            if len(first) >= 3:
                variants.setdefault(first, v)
        for var, val in variants.items():
            if len(var) >= 3 and var in cand:
                if len(var) > best_len:
                    best_len, hits = len(var), [val]
                elif len(var) == best_len and val not in hits:
                    hits.append(val)
    return hits


def _find_names(ql, df):
    """Inspecting officials whose first / last name appears in the question."""
    toks = {_norm(t) for t in ql.split() if len(_norm(t)) >= 4}
    hits = []
    for v in df["Name"].dropna().astype(str).unique():
        parts = [_norm(p) for p in re.split(r"[\s,&.]+", v) if len(_norm(p)) >= 4]
        if any(p in toks for p in parts):
            hits.append(v)
    return hits[:5]


def _rule_report_plan(ql, ctx):
    insp = ctx["insp"]
    rng = _rule_dates(ql)
    who = list(dict.fromkeys(_find_officer(ql, insp, "InspectionBy", split_slash=True) + _find_names(ql, insp)))
    locs = _find_officer(ql, insp, "Location")
    parts = []
    if who:
        parts.append(" / ".join(who))
    if locs:
        parts.append(locs[0])
    if rng:
        parts.append(f"{rng[0]:%d %b %Y}" if rng[0] == rng[1] else f"{rng[0]:%d %b %Y} to {rng[1]:%d %b %Y}")
    return {"action": "inspection_report", "table": "Inspections", "filters": [], "group_by": [],
            "aggregations": [], "columns": [], "limit": None, "chart": "none", "clarification": None,
            "sort_by": None, "ascending": False,
            "report": {"who": who, "location": locs[0] if locs else "",
                       "from": rng[0].isoformat() if rng else "", "to": rng[1].isoformat() if rng else ""},
            "title": "Inspection report" + (" · " + " · ".join(parts) if parts else "")}


def _rule_plan(question, tables, prev=None, ctx=None):
    """Understand common questions with plain rules (no AI)."""
    df = next(iter(tables.values()))
    tname = next(iter(tables))
    ql = " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9&/ ]+", " ", question.lower())) + " "
    if re.fullmatch(r"\s*(hi|hii|hello|hey|hlo|help|namaste)\s*", ql) or "what can you do" in ql:
        return {"clarification": "Hello! " + _BASIC_HELP}

    if _REPORT_RX.search(ql):
        if ctx and ctx.get("insp") is not None:
            return _rule_report_plan(ql, ctx)
        return {"clarification": "Inspection reports are not available right now."}

    filters, parts = [], []
    date_col = "Date of Inspection" if "Date of Inspection" in df.columns else \
        next((c for c in df.columns if _is_dt(df[c])), None)
    rng = _rule_dates(ql) if date_col else None
    if rng:
        filters.append({"column": date_col, "op": "between", "value": [rng[0].isoformat(), rng[1].isoformat()]})
        parts.append(f"{rng[0]:%d %b %Y} to {rng[1]:%d %b %Y}")

    sts = []
    ql_s = ql.replace("not resolved", " ").replace("unresolved", " ").replace("not done", " ")
    if re.search(r"no response|no reply|not responded|no feedback|without reply|bina reply", ql):
        sts.append("No Response")
    if re.search(r"pending|pendng|pndng|pendin|unresolved|not resolved|not done|\bopen\b", ql):
        sts.append("Pending")
    if re.search(r"resolved|resolvd|resolve|solved|\bdone\b|closed|complied|attended|cleared", ql_s):
        sts.append("Resolved")
    if sts == ["Pending"] or set(sts) == {"Pending", "No Response"}:
        sts = ["Pending"]                       # SARAL: pending = Pending + No Response
        if "Status" in df.columns:
            filters.append({"column": "Status", "op": "in", "value": ["Pending", "No Response"]})
            parts.append("Pending")
    elif len(sts) == 1 and "Status" in df.columns:
        filters.append({"column": "Status", "op": "eq", "value": sts[0]})
        parts.append(sts[0])

    dept_filtered = False
    if "Head" in df.columns:
        heads = df["Head"].dropna().astype(str).unique()
        found = []
        for target, words in _DEPT_WORDS.items():
            if any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", ql) for w in words):
                real = [h for h in heads if _norm(target) in _norm(h)]
                found.append(real[0] if real else target)
        if found:
            dept_filtered = True
            filters.append({"column": "Head", "op": "in", "value": found})
            parts.append(" / ".join(found))

    offs = []
    ocol = "Inspection By" if re.search(r"insp(?:ected|ection)\s+by", ql) and "Inspection By" in df.columns else "Action By"
    if ocol in df.columns:
        offs = _find_officer(ql, df, ocol)
        if offs:
            filters.append({"column": ocol, "op": "in", "value": offs} if len(offs) > 1
                           else {"column": ocol, "op": "contains", "value": offs[0]})
            parts.append(" / ".join(offs))

    if "Location" in df.columns:
        locs = {_norm(x): x for x in df["Location"].dropna().astype(str).unique()}
        words = re.findall(r"(?:at|in|station|stn|location|gate)\s+([a-z0-9\-]+)", ql) + \
            re.findall(r"([a-z0-9\-]+)\s+(?:station|stn)\b", ql)
        hit = next((w for w in words if _norm(w) in locs), None)
        if hit:
            filters.append({"column": "Location", "op": "eq", "value": locs[_norm(hit)]})
            parts.append(locs[_norm(hit)])

    # Learn names straight from the data: Sub Head values and inspection types
    toks_n = [_norm(t) for t in ql.split() if _norm(t)]
    cand_n = set(toks_n) | {a + b for a, b in zip(toks_n, toks_n[1:])}
    if "Sub Head" in df.columns:
        for v in df["Sub Head"].dropna().astype(str).unique():
            hit = [x for x in {_norm(v), _norm(re.sub(r"\(.*?\)", "", v))}
                   if len(x) >= 3 and x in cand_n and x not in ("other", "others", "general", "nil", "none")]
            if hit and not any(f["column"] == "Sub Head" for f in filters):
                filters.append({"column": "Sub Head", "op": "eq", "value": v})
                parts.append(v)
    if "Type of Inspection" in df.columns:
        for key, rx in (("footplate", r"foot ?plate"), ("lc gate", r"\blc gate|level crossing"),
                        ("coaching", r"\bcoaching\b"), ("on train", r"\bon train\b"),
                        ("surprise", r"surprise|ambush"), ("worksite", r"work ?site"),
                        ("station inspection", r"station inspection")):
            if re.search(rx, ql):
                filters.append({"column": "Type of Inspection", "op": "contains", "value": key})
                parts.append(key.upper())
                break

    mt = re.search(r"(?:related to|relating to|regarding|about|concerning)\s+([a-z0-9&/\-]+)", ql)
    if mt and "Deficiencies Noted" in df.columns:
        filters.append({"column": "Deficiencies Noted", "op": "contains", "value": mt.group(1)})
        parts.append(f"'{mt.group(1)}'")

    rank = re.search(r"\b(which|most|more|max|maximum|least|less|minimum|lowest|highest|top|konsa|kaun)\b", ql)
    asc = bool(re.search(r"\b(least|less|minimum|lowest|fewest)\b", ql))
    wise = re.search(r"\bwise\b|\banalysis\b|\banalyse\b|\banalyze\b|\bsummary\b|\breport\b", ql)
    dims = [("Sub Head", r"sub ?head|category|categories"),
            ("Type of Inspection", r"type of inspection|inspection type"),
            ("Location", r"\bstations?\b|\blocations?\b|\bgates?\b"),
            ("Action By", r"\bofficers?\b|\bofficials?\b"),
            ("Status", r"\bstatus\b"),
            ("Head", r"\bdept\b|\bdeptt\b|\bdpt\b|\bdepartments?\b|\bhead\b|\bbranch\b")]
    dim = next((c for c, rx in dims if c in df.columns and re.search(rx, ql)), None)

    # SMART ANALYSIS: "smart analysis of engg ...", or "analysis of <department / officer> ..."
    is_followup = bool(prev and re.search(
        r"^\s*(only|now|also|same|and|what about|just|sirf|ab|aur|but|then)\b|\b(of this|of these|of them|same for|same as)\b", ql))
    smart_kw = _SMART_RX.search(ql)
    if smart_kw and prev and prev.get("action") != "inspection_report" and \
            re.search(r"\b(of|for|on) (this|these|them|same)\b", ql):
        newcols = {f["column"] for f in filters}          # carry the earlier filters over
        filters = [f for f in (prev.get("filters") or []) if f["column"] not in newcols] + filters
        parts = (prev.get("title") or "").split(" · ")[1:] + parts
        dept_filtered = dept_filtered or any(f["column"] == "Head" for f in filters)
        offs = offs or [f for f in filters if f["column"] in ("Action By", "Inspection By")]
    if "Status" in df.columns and (smart_kw or (
            re.search(r"\banaly[sz]\w*\b|\bsummary\b", ql) and (dept_filtered or offs)
            and not rank and not dim and not is_followup)):
        gb = [dim] if dim and dim != "Status" else ([] if (dept_filtered or offs) else ["Head"])
        return {"action": "smart_analysis", "table": tname, "filters": filters, "group_by": gb,
                "aggregations": [], "columns": [], "limit": None, "chart": "auto", "clarification": None,
                "sort_by": None, "ascending": False, "report": None,
                "title": "Smart Analysis" + (" · " + " · ".join(parts) if parts else "")}

    group_by = []
    if rank or wise:
        if dim and not (dim == "Head" and dept_filtered and wise and not rank):
            group_by = [dim]
            if wise and not rank and dim != "Status" and "Status" in df.columns and len(sts) != 1:
                group_by.append("Status")
        elif dept_filtered and wise and "Sub Head" in df.columns:
            group_by = ["Sub Head"] + (["Status"] if "Status" in df.columns and len(sts) != 1 else [])
        elif rank and "Head" in df.columns:
            group_by = ["Head"]
        elif wise and "Head" in df.columns:
            group_by = ["Head"] + (["Status"] if "Status" in df.columns and len(sts) != 1 else [])

    # Follow-up ("only pending ones", "same for last month", "department wise of this"): refine previous plan
    followup = is_followup and prev.get("action") != "inspection_report"
    if followup and (filters or group_by):
        base = json.loads(json.dumps(prev, default=str))
        newcols = {f["column"] for f in filters}
        smart_prev = base.get("action") == "smart_analysis"
        gb = group_by or ([] if re.search(r"\b(list|show all|details|rows|records)\b", ql)
                          else (base.get("group_by") or []))
        segs = (base.get("title") or "Deficiencies").split(" · ")
        for f in base.get("filters") or []:
            if f["column"] in newcols:                      # this condition is being replaced: drop its old words
                vals = f["value"] if isinstance(f["value"], list) else [f["value"]]
                drop = {" / ".join(map(str, vals))} | {str(v) for v in vals} | {str(v).upper() for v in vals} \
                    | {f"'{v}'" for v in vals}
                segs = [s for s in segs if s not in drop and not (
                    f["column"] == date_col and re.fullmatch(r"\d{2} \w{3} \d{4} to \d{2} \w{3} \d{4}", s))]
        old_title = " · ".join(segs)
        extra = [p for p in parts if p not in old_title]
        base.update(filters=[f for f in (base.get("filters") or []) if f["column"] not in newcols] + filters,
                    group_by=gb, clarification=None,
                    aggregations=[] if smart_prev else ([{"column": "*", "func": "count", "as": "Deficiencies"}] if gb else []),
                    title=old_title + (" · " + " · ".join(extra) if extra else ""))
        if gb and rank and not smart_prev:
            base.update(sort_by="Deficiencies", ascending=asc)
        return base

    if not filters and not group_by:
        return {"clarification": "I could not understand that. " + _BASIC_HELP}

    plan = {"action": "query", "table": tname, "filters": filters, "group_by": group_by, "columns": [],
            "limit": None, "chart": "auto", "clarification": None, "sort_by": None, "ascending": False,
            "aggregations": [{"column": "*", "func": "count", "as": "Deficiencies"}] if group_by else [],
            "title": "Deficiencies" + (" · " + " · ".join(parts) if parts else "")}
    if group_by and rank:
        plan["sort_by"], plan["ascending"] = "Deficiencies", asc
    return plan


def _explain_plan(plan):
    """Plain words showing exactly how the question was understood, so a wrong reading is easy to spot."""
    def d(x):
        try:
            return f"{dt.date.fromisoformat(str(x)[:10]):%d %b %Y}"
        except Exception:
            return str(x)
    out = []
    act = plan.get("action")
    if act == "inspection_report":
        r = plan.get("report") or {}
        who = r.get("who")
        who = " / ".join(who) if isinstance(who, list) else (who or "")
        out.append("Inspection report from the Inspections tab")
        if who:
            out.append(f"Official / designation: {who}")
        if r.get("location"):
            out.append(f"Location: {r['location']}")
        if r.get("from") or r.get("to"):
            a, b = d(r.get("from") or r.get("to")), d(r.get("to") or r.get("from"))
            out.append(f"Date: {a}" if a == b else f"Date: {a} to {b}")
        else:
            out.append("Date: latest inspection date")
        return out
    if act == "smart_analysis":
        gb = [g for g in (plan.get("group_by") or []) if g != "Status"]
        out.append(f"Smart Analysis ({gb[0] if gb else 'Sub Head'} wise)")
    for f in plan.get("filters") or []:
        f = _fix_status_filter(f)
        col, op, v = f.get("column"), f.get("op"), f.get("value")
        vals = v if isinstance(v, list) else [v]
        if op == "between" and len(vals) == 2:
            out.append(f"{col}: {d(vals[0])} to {d(vals[1])}")
        elif op in ("gt", "gte"):
            out.append(f"{col} from {d(v)}")
        elif op in ("lt", "lte"):
            out.append(f"{col} up to {d(v)}")
        elif op == "contains":
            out.append(f"{col} contains '{v}'")
        elif op == "ne":
            out.append(f"{col} is not {' or '.join(map(str, vals))}")
        elif op in ("eq", "in"):
            out.append(f"{col} is {' or '.join(map(str, vals))}")
        elif op in ("isnull", "notnull"):
            out.append(f"{col} is {'blank' if op == 'isnull' else 'filled'}")
    if act != "smart_analysis" and plan.get("group_by"):
        out.append("counted by " + " and ".join(plan["group_by"]))
    return out


def _nm(x):
    return x.strftime("%d-%m-%Y") if isinstance(x, pd.Timestamp) else str(x)


def _local_summary(title, result, plan):
    """Plain-language answer written locally (no AI request)."""
    num = [c for c in result.columns if _is_num(result[c])]
    if plan.get("group_by") and num:
        asc = bool(plan.get("ascending"))
        val = num[-1]
        g = [c for c in result.columns if c not in num]
        lines = [f"**{int(result[val].sum())} records** found: {title}."]
        if g:
            s = result.groupby(g[0])[val].sum().sort_values(ascending=asc)
            label = {"Head": "department", "Action By": "officer", "Location": "location"}.get(g[0], g[0])
            lines.append(f"{'Least' if asc else 'Most'} for {label}: **{_nm(s.index[0])}** ({int(s.iloc[0])}).")
            if len(s) > 1:
                lines.append("Next: " + ", ".join(f"{_nm(k)} ({int(v)})" for k, v in s.iloc[1:4].items()) + ".")
            if "Status" in g and g[0] != "Status":
                stt = result.groupby("Status")[val].sum()
                lines.append("Status: " + ", ".join(f"{k} {int(v)}" for k, v in stt.items()) + ".")
        return "\n\n".join(lines)
    k = _kpis(result)
    lines = [f"**{len(result)} records** found: {title}."]
    if "Resolved" in k:
        lines.append(f"Resolved {k['Resolved']}, **not yet resolved {k['Pending'] + k['No Response']}** "
                     f"(feedback pending {k['Pending']}, no feedback {k['No Response']}). "
                     f"Compliance {k['Compliance %']}%.")
    return "\n\n".join(lines)


def _local_followups(plan, mode):
    act = plan.get("action")
    if act == "inspection_report":
        return ["Inspection report of yesterday", "Inspection report of last 7 days",
                "Which official did the most inspections this month?"]
    if act == "smart_analysis":
        return ["Only pending ones", "Same for last 30 days", "Department wise analysis of this"]
    has_status = any(f.get("column") == "Status" for f in plan.get("filters") or [])
    return ["Only resolved ones" if has_status else "Only pending ones",
            "Smart analysis of this", "Same for last 30 days"]


# ----------------------------------------------------------------------------
# Insights: KPIs, auto charts, quick findings  (all local, free)
# ----------------------------------------------------------------------------
def _kpis(result):
    total = len(result)
    if "Status" not in result.columns:
        return {"Total records": total}
    vc = result["Status"].value_counts()
    res = int(vc.get("Resolved", 0))
    return {"Total": total, "Resolved": res, "Pending": int(vc.get("Pending", 0)),
            "No Response": int(vc.get("No Response", 0)),
            "Compliance %": round(100 * res / total, 1) if total else 0}


def _insights(result):
    out, cols = [], result.columns
    if result.empty:
        return out
    labels = {"Head": "department", "Action By": "officer", "Location": "location",
              "Inspecting Official": "inspecting official"}
    for col, label in labels.items():
        if col in cols and result[col].nunique() > 1:
            vc = result[col].astype(str).value_counts()
            out.append(f"Most records for {label}: **{vc.index[0]}** ({int(vc.iloc[0])} of {len(result)})")
    if "Status" in cols and "Date of Inspection" in cols and _is_dt(result["Date of Inspection"]):
        today = pd.Timestamp(dt.date.today())
        op = result[(result["Status"] != "Resolved") & result["Date of Inspection"].notna()]
        if not op.empty:
            r = op.sort_values("Date of Inspection").iloc[0]
            age = (today - r["Date of Inspection"]).days
            loc = f", {r['Location']}" if "Location" in op.columns else ""
            out.append(f"Oldest open item is **{age} days** old ({r['Date of Inspection']:%d-%m-%Y}{loc})")
            over30 = int(((today - op["Date of Inspection"]).dt.days > 30).sum())
            if over30:
                out.append(f"**{over30}** open items are older than 30 days")
    return out


def _charts_for(result, plan):
    """Decide which charts suit this result. Returns a list of chart specs."""
    hint = str(plan.get("chart") or "auto").lower()
    if hint == "none" or result.empty:
        return []
    cols = list(result.columns)
    num = [c for c in cols if _is_num(result[c])]
    specs = []

    if plan.get("group_by") and num:                       # aggregated result
        val = num[-1]
        g = [c for c in cols if c not in num]
        if not g:
            return []
        if len(g) == 1:
            d = result[[g[0], val]].copy()
            if _is_dt(d[g[0]]) or hint == "line":
                kind, d = "line", d.sort_values(g[0])
            elif g[0] == "Status" or (hint == "pie" and len(d) <= 8):
                kind = "pie"
            else:
                kind, d = "bar", d.sort_values(val, ascending=False).head(20)
            specs.append(dict(kind=kind, df=d, cat=g[0], val=val, color=None, title=f"{val} by {g[0]}"))
        else:
            cat, col = g[0], g[1]
            d = result[[cat, col, val]].copy()
            d[cat], d[col] = d[cat].astype(str), d[col].astype(str)
            top = d.groupby(cat)[val].sum().nlargest(15).index
            d = d[d[cat].isin(top)]
            specs.append(dict(kind="stacked", df=d, cat=cat, val=val, color=col,
                              title=f"{val} by {cat} and {col}"))
        return specs

    # row-level result: build overview charts from the rows
    if "Status" in cols:
        c = result["Status"].value_counts().reset_index()
        c.columns = ["Status", "Count"]
        specs.append(dict(kind="pie", df=c, cat="Status", val="Count", color=None, title="Status split"))
    for pick in ["Head", "Sub Head", "Action By", "Location", "Type of Inspection"]:
        if pick in cols and result[pick].astype(str).nunique() > 1:
            r = result.assign(**{pick: result[pick].astype(str)})
            if "Status" in cols:
                d = r.groupby([pick, "Status"]).size().reset_index(name="Count")
                top = d.groupby(pick)["Count"].sum().nlargest(12).index
                specs.append(dict(kind="stacked", df=d[d[pick].isin(top)], cat=pick, val="Count",
                                  color="Status", title=f"Records by {pick}"))
            else:
                d = r.groupby(pick).size().reset_index(name="Count").sort_values("Count", ascending=False).head(12)
                specs.append(dict(kind="bar", df=d, cat=pick, val="Count", color=None, title=f"Records by {pick}"))
            break
    dc = "Date of Inspection" if "Date of Inspection" in cols else next((c for c in cols if _is_dt(result[c])), None)
    if dc and _is_dt(result[dc]) and result[dc].dt.date.nunique() > 1:
        d = result.groupby(result[dc].dt.normalize()).size().reset_index(name="Count")
        d.columns = [dc, "Count"]
        specs.append(dict(kind="line", df=d, cat=dc, val="Count", color=None, title=f"Records per day ({dc})"))
    return specs[:3]


def _plotly_fig(spec):
    import plotly.express as px
    d, cat, val, color, kind = spec["df"].copy(), spec["cat"], spec["val"], spec.get("color"), spec["kind"]
    if not (kind == "line" and _is_dt(d[cat])):
        d[cat] = d[cat].astype(str)
    if kind == "bar":
        fig = px.bar(d, x=val, y=cat, orientation="h", text=val, color_discrete_sequence=PALETTE)
        fig.update_yaxes(autorange="reversed")
    elif kind == "stacked":
        d[color] = d[color].astype(str)
        fig = px.bar(d, x=cat, y=val, color=color, barmode="stack",
                     color_discrete_map=STATUS_COLORS, color_discrete_sequence=PALETTE)
    elif kind == "pie":
        fig = px.pie(d, names=cat, values=val, hole=0.45, color=cat,
                     color_discrete_map=STATUS_COLORS, color_discrete_sequence=PALETTE)
        fig.update_traces(textinfo="label+value")
    else:
        fig = px.line(d, x=cat, y=val, markers=True, color_discrete_sequence=PALETTE)
    fig.update_layout(title=spec["title"], height=340, margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", y=-0.25, title_text=""))
    return fig


def _mpl_png(spec):
    """Static chart image for the Word report (matplotlib; no extra install)."""
    from matplotlib.figure import Figure
    d, cat, val, color, kind = spec["df"].copy(), spec["cat"], spec["val"], spec.get("color"), spec["kind"]
    if not (kind == "line" and _is_dt(d[cat])):
        d[cat] = d[cat].astype(str)
    fig = Figure(figsize=(6.6, 3.4))
    ax = fig.subplots()
    if kind == "bar":
        d = d.iloc[::-1]
        ax.barh(d[cat], d[val], color=PALETTE[0])
        for i, v in enumerate(d[val]):
            ax.text(v, i, f" {v:g}", va="center", fontsize=8)
    elif kind == "stacked":
        p = d.pivot_table(index=cat, columns=color, values=val, aggfunc="sum", fill_value=0)
        p = p.loc[p.sum(axis=1).sort_values(ascending=False).index]
        colors = [STATUS_COLORS.get(str(c), PALETTE[i % len(PALETTE)]) for i, c in enumerate(p.columns)]
        p.plot(kind="bar", stacked=True, ax=ax, color=colors, rot=30, width=0.75)
        ax.set_xlabel("")
        ax.legend(fontsize=8, title="")
    elif kind == "pie":
        cs = [STATUS_COLORS.get(str(x)) for x in d[cat]]
        cs = None if any(c is None for c in cs) else cs
        ax.pie(d[val], labels=d[cat], colors=cs, autopct=lambda p: f"{p:.0f}%" if p >= 4 else "",
               wedgeprops=dict(width=0.45), textprops=dict(fontsize=8))
        ax.axis("equal")
    else:
        ax.plot(d[cat], d[val], marker="o", color=PALETTE[0])
        fig.autofmt_xdate()
    ax.set_title(spec["title"], fontsize=10)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Downloads: Excel and Word
# ----------------------------------------------------------------------------
def _to_excel(df):
    buf = io.BytesIO()
    out = df.copy()
    for c in out.columns:
        if _is_dt(out[c]):
            out[c] = out[c].dt.strftime("%d-%m-%Y").fillna("")
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        out.to_excel(xw, index=False, sheet_name="Result")
        ws = xw.sheets["Result"]
        for i, c in enumerate(out.columns, 1):
            longest = max([len(str(c))] + [len(str(v)) for v in out[c].head(200)])
            ws.column_dimensions[ws.cell(1, i).column_letter].width = min(50, longest + 2)
        ws.freeze_panes = "A2"
    return buf.getvalue()


def _fmt_cell(v, limit=250):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    if isinstance(v, pd.Timestamp):
        return v.strftime("%d-%m-%Y")
    s = str(v)
    return s if len(s) <= limit else s[:limit - 1] + "…"


def _to_docx(turn):
    """Word report with summary, KPIs, charts and data. Returns bytes, or None if python-docx is missing."""
    try:
        from docx import Document
        from docx.enum.section import WD_ORIENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt
    except ImportError:
        return None

    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(0.7))

    doc.add_heading("S.A.R.A.L Report", level=0)
    p = doc.add_paragraph("Safety Abnormality Report & Action List · Solapur Division · Central Railway")
    p.runs[0].italic = True
    doc.add_paragraph(f"Question: {turn['q']}")
    doc.add_paragraph(f"Report: {turn.get('title', 'Result')}   |   Generated on {dt.datetime.now():%d-%m-%Y %H:%M}")

    doc.add_heading("Summary", level=1)
    doc.add_paragraph(turn["text"].replace("**", ""))

    kp = turn.get("kpis")
    if kp:
        t = doc.add_table(rows=2, cols=len(kp))
        t.style = "Light Grid Accent 1"
        for i, (a, b) in enumerate(kp.items()):
            t.cell(0, i).text, t.cell(1, i).text = str(a), str(b)

    if turn.get("insights"):
        doc.add_heading("Key points", level=1)
        for s in turn["insights"]:
            doc.add_paragraph(s.replace("**", ""), style="List Bullet")

    charts_done = False
    for spec in turn.get("specs") or []:
        try:
            png = _mpl_png(spec)
        except Exception:
            continue
        if not charts_done:
            doc.add_heading("Charts", level=1)
            charts_done = True
        doc.add_picture(io.BytesIO(png), width=Inches(5.8))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    tbl = turn["table"]
    cols = list(tbl.columns)
    if not turn.get("grouped"):
        cols = [c for c in ROW_COLS_DOC if c in tbl.columns] or cols
    shown = tbl[cols].head(MAX_ROWS_IN_WORD)
    doc.add_heading("Data", level=1)
    t = doc.add_table(rows=1, cols=len(cols))
    t.style = "Light Grid Accent 1"
    for i, c in enumerate(cols):
        t.rows[0].cells[i].text = str(c)
    for _, r in shown.iterrows():
        cells = t.add_row().cells
        for i, c in enumerate(cols):
            cells[i].text = _fmt_cell(r[c])
    for row in t.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(8)
    if len(tbl) > MAX_ROWS_IN_WORD:
        doc.add_paragraph(f"Showing first {MAX_ROWS_IN_WORD} of {len(tbl)} records. "
                          f"Download the Excel sheet for all records.")
    doc.add_paragraph("Auto-generated by Ask SARAL · Safety Department, Solapur Division")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Streamlit UI  (no st.rerun(), so the user stays on the same tab)
# ----------------------------------------------------------------------------
def _answer(question, tables, history, hint, ctx):
    try:
        t0, ai_s = time.time(), None
        plan, mode, note = None, "ai", ""
        prev = history[-1]["plan"] if history else None
        ql = " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9&/ ]+", " ", question.lower())) + " "

        # Smart Analysis / Inspection report questions are understood by built-in rules: instant, no AI wait
        if _FAST_RX.search(ql):
            p = _rule_plan(question, tables, prev, ctx)
            if p.get("action") in ("inspection_report", "smart_analysis"):
                plan, mode = p, "basic"

        if plan is None and _ai_available():
            try:
                ta = time.time()
                _STATE["used"] = None
                plan = _ask_plan_cached(question, tables, history, hint)
                ai_s = round(time.time() - ta, 1)
                used, order = _STATE.get("used"), _providers()
                if used and order and used != order[0]:
                    note = f"ℹ️ The main AI was busy or unavailable, so this answer used {used.title()}."
            except Exception as e:
                msg = str(e)
                if _is_limit_error(msg):
                    note = ("⚡ The free AI limit is used up for now, so this answer comes from Basic mode "
                            "(built-in rules). The AI will work again later.")
                elif isinstance(e, RuntimeError) and "API_KEY" in msg:
                    note = "⚡ The AI key is not set, so this answer comes from Basic mode (built-in rules)."
                else:
                    note = f"⚡ The AI was not available, so this answer comes from Basic mode. ({type(e).__name__})"
                plan = None
        elif plan is None:
            note = ("⚡ The free AI limit is used up for now, so this answer comes from Basic mode "
                    "(built-in rules). The AI will work again later.")
        if plan is None:
            plan, mode = _rule_plan(question, tables, prev, ctx), "basic"
        if plan.get("clarification"):
            return {"q": question, "text": plan["clarification"], "note": note}

        action = plan.get("action") or "query"
        if action == "inspection_report":
            return _answer_report(question, plan, ctx, history, t0, note)
        if action == "smart_analysis":
            return _answer_smart(question, plan, tables, history, t0, note, ai_s)

        result = _execute(plan, tables)
        title = plan.get("title") or "Result"
        history.append({"q": question, "plan": plan})
        if result.empty:
            note = ""
            src = tables.get(plan.get("table")) if plan.get("table") in tables else next(iter(tables.values()))
            dcols = [c for c in src.columns if _is_dt(src[c])]
            if dcols and src[dcols[0]].notna().any():
                note = f" The latest record in the data is dated {src[dcols[0]].max():%d-%m-%Y}."
            return {"q": question,
                    "text": f"No records found for: {title}.{note} Try a longer date range or another name."}

        body, followups = None, []
        if mode == "ai" and _ai_available() and \
                str(_secret("SARAL_AI_SUMMARY") or "").strip().lower() in ("1", "true", "yes"):
            try:
                body, followups = _ask_summary(question, title, len(result), result)
            except Exception:
                body, followups = None, []
        if not body:
            body = _local_summary(title, result, plan)
        if not followups:
            followups = _local_followups(plan, mode)
        grouped = bool(plan.get("group_by"))
        try:
            specs = _charts_for(result, plan)
        except Exception:
            specs = []
        turn = {"q": question, "text": body, "table": result, "title": title, "followups": followups,
                "grouped": grouped, "specs": specs, "note": note,
                "secs": round(time.time() - t0, 1), "ai_secs": ai_s, "explain": _explain_plan(plan),
                "kpis": None if grouped else _kpis(result),
                "insights": [] if grouped else _insights(result)}
        turn["xlsx"] = _to_excel(result)
        turn["docx"] = None                    # built only when the user asks for it (saves time)
        return turn
    except Exception as e:
        msg = str(e)
        if "API_KEY" in msg and isinstance(e, RuntimeError):
            return {"q": question,
                    "text": "🔧 The chatbot is not switched on yet. The app administrator must add the "
                            "AI key (GROQ_API_KEY or GEMINI_API_KEY) in the app's Secrets settings. "
                            "Please inform your administrator.",
                    "error": msg}
        if isinstance(e, ModuleNotFoundError):
            return {"q": question,
                    "text": "🔧 The chatbot needs a software package that is not installed yet. "
                            "Please inform your administrator.", "error": msg}
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return {"q": question,
                    "text": "⏳ The free AI limit is used up for now. Please try again after some time.",
                    "error": msg}
        return {"q": question,
                "text": "Sorry, I could not answer that this time. Please try again in a few words, "
                        "for example: Engg pending deficiencies last 7 days.",
                "error": f"{type(e).__name__}: {msg}"}


def _queue_question(q):
    st.session_state["saral_queued"] = q


def _show_reports(t, idx, expanded):
    reps = t.get("reports") or []
    for j, (ttl, msg) in enumerate(reps):
        with st.expander(f"📋 {ttl}", expanded=(expanded and len(reps) == 1)):
            try:
                st.code(msg, language=None, wrap_lines=True)     # has a copy button
            except TypeError:
                st.code(msg, language=None)
            c1, c2 = st.columns(2)
            c1.markdown(
                f'<a href="https://wa.me/?text={quote(msg)}" target="_blank" rel="noopener noreferrer">'
                f'<button style="width:100%;min-height:44px;background-color:#25D366;color:white;border:none;'
                f'border-radius:10px;font-weight:600;cursor:pointer;">📤 Share via WhatsApp</button></a>',
                unsafe_allow_html=True)
            safe = re.sub(r"[^A-Za-z0-9_-]+", "_", ttl.split(" • ")[0]) or "report"
            c2.download_button("📥 Download as .txt", data=msg.encode("utf-8"),
                               file_name=f"inspection_report_{safe}_{j + 1}.txt", mime="text/plain",
                               key=f"saral_rd_{idx}_{j}", use_container_width=True)
    if len(reps) > 1:
        st.download_button("📥 Download all reports (.txt)",
                           data=("\n\n" + "=" * 40 + "\n\n").join(m for _, m in reps).encode("utf-8"),
                           file_name=f"inspection_reports_{dt.date.today():%Y%m%d}.txt", mime="text/plain",
                           key=f"saral_rall_{idx}")


def _show_turn(t, idx, newest):
    st.markdown(f"**🧑 {t['q']}**")
    with st.container(border=True):
        st.markdown(t["text"])
        if t.get("note"):
            st.caption(t["note"])
        if t.get("secs") is not None:
            ai_txt = f" (AI part {t['ai_secs']} s)" if t.get("ai_secs") is not None else ""
            st.caption(f"⏱ answered in {t['secs']} s{ai_txt}")
        if t.get("error"):
            st.caption(f"Details: {t['error']}")
        tbl = t.get("table")
        if tbl is None and t.get("explain"):
            st.caption("🔍 Understood as: " + "  ·  ".join(t["explain"]))
        _show_reports(t, idx, True)
        if tbl is not None:
            kp = t.get("kpis")
            if kp:
                for c, (k, v) in zip(st.columns(len(kp)), kp.items()):
                    c.metric(k, f"{v}%" if k == "Compliance %" else v)

            specs = t.get("specs") or []
            if specs:
                try:
                    for i in range(0, len(specs), 2):
                        row = specs[i:i + 2]
                        for c, (j, sp) in zip(st.columns(len(row)), enumerate(row)):
                            with c:
                                st.plotly_chart(_plotly_fig(sp), use_container_width=True,
                                                key=f"saral_ch_{idx}_{i}_{j}")
                except ImportError:
                    st.caption("📊 Charts need the 'plotly' package (add it to requirements.txt).")
                except Exception as e:
                    st.caption(f"📊 Chart could not be drawn: {e}")

            if t.get("insights"):
                with st.expander("💡 Quick insights", expanded=True):
                    for s in t["insights"]:
                        st.markdown(f"- {s}")

            if t.get("explain"):
                st.caption("🔍 Understood as: " + "  ·  ".join(t["explain"]))
            st.caption(f"{t.get('title', 'Result')}  •  {len(tbl)} records")
            st.dataframe(tbl.head(MAX_ROWS_SHOWN), use_container_width=True, hide_index=True)
            if len(tbl) > MAX_ROWS_SHOWN:
                st.caption(f"Showing first {MAX_ROWS_SHOWN} rows. Download the sheet to get all rows.")

            d1, d2 = st.columns(2)
            stamp = f"SARAL_{dt.date.today():%Y%m%d}_{idx}"
            d1.download_button("⬇️ Excel sheet", data=t["xlsx"], file_name=f"{stamp}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key=f"saral_xl_{idx}", use_container_width=True)
            if t.get("docx"):
                d2.download_button("📄 Word report (with charts)", data=t["docx"], file_name=f"{stamp}.docx",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   key=f"saral_dx_{idx}", use_container_width=True)
            else:
                if t.get("docx_failed"):
                    d2.caption("📄 Word report needs 'python-docx' in requirements.txt")
                else:
                    d2.button("📄 Prepare Word report", key=f"saral_pw_{idx}", on_click=_prep_docx,
                              args=(idx,), use_container_width=True)

            if t.get("detail"):                            # Smart Analysis: detailed workbook
                if t.get("detail_xlsx"):
                    st.download_button("⬇️ Detailed Excel (Summary + Open items + every Sub Head + Full records)",
                                       data=t["detail_xlsx"], file_name=f"{stamp}_detailed.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       key=f"saral_dd_{idx}", use_container_width=True)
                else:
                    st.button("📦 Prepare detailed Excel (all Sub Heads + open items)", key=f"saral_pd_{idx}",
                              on_click=_prep_detail, args=(idx,), use_container_width=True)

        if newest and t.get("followups"):
            st.markdown("**Ask next:**")
            for j, f in enumerate(t["followups"]):
                st.button(f, key=f"saral_fu_{idx}_{j}", on_click=_queue_question, args=(f,),
                          use_container_width=True)


def _prep_docx(idx):
    t = st.session_state["saral_turns"][idx]
    try:
        t["docx"] = _to_docx(t)
    except Exception:
        t["docx"] = None
    if not t["docx"]:
        t["docx_failed"] = True


def _prep_detail(idx):
    t = st.session_state["saral_turns"][idx]
    try:
        t["detail_xlsx"] = _smart_workbook(*t["detail"])
    except Exception:
        t["detail_xlsx"] = _to_excel(t["table"])


def _show_turn_compact(t, idx):
    """Older answers: just the question and the answer text (keeps the page fast)."""
    st.markdown(f"**🧑 {t['q']}**")
    with st.container(border=True):
        st.markdown(t["text"])
        _show_reports(t, idx, False)
        if t.get("xlsx"):
            st.download_button("⬇️ Excel sheet", data=t["xlsx"],
                               file_name=f"SARAL_{dt.date.today():%Y%m%d}_{idx}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key=f"saral_xl_{idx}")


def _clear_chat():
    st.session_state["saral_turns"] = []
    st.session_state["saral_hist"] = []


def _render(dataframes, title, domain_hint, hidden_columns, report_builder, data_key):
    st.subheader(f"🤖 {title}")
    st.caption("Type your question in simple words (English / हिंदी / Hinglish). "
               "You get the answer, charts, an Excel sheet and a Word report. "
               "Ask for a **Smart analysis** or an **Inspection report** too.")

    tables, insp_raw = _prepare_cached(dataframes, hidden_columns, data_key)
    ctx = {"insp": insp_raw, "builder": report_builder}
    ss = st.session_state
    ss.setdefault("saral_turns", [])
    ss.setdefault("saral_hist", [])

    question = ss.pop("saral_queued", None)           # a tapped "Ask next" suggestion
    with st.form("saral_chat_form", clear_on_submit=True):
        typed = st.text_input("Your question", placeholder="e.g. Smart analysis of Engg last 30 days")
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
            ss["saral_turns"].append(_answer(question, tables, ss["saral_hist"], domain_hint, ctx))

    n = len(ss["saral_turns"])
    for i in range(n - 1, -1, -1):                     # newest first
        if i >= n - 2:
            _show_turn(ss["saral_turns"][i], i, newest=(i == n - 1))
        else:
            _show_turn_compact(ss["saral_turns"][i], i)

    if n:
        st.button("🗑️ Clear chat", key="saral_clear", on_click=_clear_chat)


# The chat runs as a Streamlit "fragment": asking a question reruns ONLY this block, not the whole app
# (grids, charts and the other tabs stay untouched). Needs Streamlit 1.37+ (1.33+ with the experimental name).
_fragment = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)
_render_fragment = _fragment(_render) if _fragment else None


def render_saral_chatbot(dataframes: dict, title: str = "Ask SARAL",
                         domain_hint: str = SARAL_HINT, hidden_columns=None,
                         report_builder=None, data_key=None, use_fragment: bool = True):
    """dataframes = {"Deficiencies": df_with_Status, "Inspections": load_inspections_data()}  (Inspections optional).
    report_builder = build_whatsapp_message from the main app (needed for inspection reports).
    data_key = anything hashable that changes when the data changes (skips hashing every cell on each rerun)."""
    fn = _render_fragment if (use_fragment and _render_fragment) else _render
    fn(dataframes, title, domain_hint, hidden_columns, report_builder, data_key)
