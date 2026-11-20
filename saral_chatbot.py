"""
saral_chatbot.py  -  "Ask SARAL": plain-language AI assistant for the S.A.R.A.L Streamlit app.
v4.2 - designation matching fixed (AEE/OP/SUR, SSE/C&W/SUR, Sr.DEN/S ...), "last N inspections",
       true inspection date taken from the deficiency text, analytical findings.
"""

import difflib
import io
import json
import re
import time
import datetime as dt

import pandas as pd
import streamlit as st

CHATBOT_VERSION = "v4.2"
DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_ROWS_SHOWN = 500
MAX_ROWS_TO_AI = 40
MAX_ROWS_IN_WORD = 100
MAX_CATEGORY_VALUES = 150

# Many rows carry "DATE OF INSPECTION : yyyy-mm-dd | ..." inside "Deficiencies Noted".
# That is the REAL inspection date; the sheet's date column can be the entry/upload date.
# True  = use the embedded date for "Date of Inspection" (old value kept as "Date Entered").
# False = keep the sheet column exactly as it is.
USE_EMBEDDED_INSPECTION_DATE = True

INTERNAL_COLUMNS = ["_sheet_row", "_original_sheet_index", "_status_plain"]
STATUS_COLORS = {"Resolved": "#2e9e5b", "Pending": "#e0623b", "No Response": "#8a94a6"}
PALETTE = ["#2f6fb5", "#e0a030", "#7a5fb5", "#3aa5a5", "#c24d86", "#6b8e23"]
ROW_COLS_DOC = [
    "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
    "Deficiencies Noted", "Inspection By", "Action By", "Feedback", "Status"
]

_is_dt = pd.api.types.is_datetime64_any_dtype
_is_num = pd.api.types.is_numeric_dtype

# Officer cells can hold several officers: "Sr.DSO & Safety Team", "ADSO/SUR , SAFETY TEAM (SUR)".
# A "/" or an unspaced "&" is PART of a designation (AEE/OP/SUR, SSE/C&W/SUR, Sr.DEN/S) - never split on it.
_OFFICER_SPLIT = re.compile(r"\s*[,;+]\s*|\s+&\s+|\s+/\s+")

# ----------------------------------------------------------------------------
# S.A.R.A.L specific knowledge
# ----------------------------------------------------------------------------
SARAL_HINT = """
This is the S.A.R.A.L (Safety Abnormality Report & Action List) database of Solapur Division, Central Railway.
IMPORTANT DATA MODEL:
- Each row in the table is ONE DEFICIENCY noted during an inspection (one inspection often has 10-25 rows).
- A single INSPECTION is identified by Date of Inspection + Inspection By + Type of Inspection (across multiple locations).

Column meanings:
- "Date of Inspection": date the inspection was done (default date for any date range in a question).
  ("Date Entered", if present, is only when the record was uploaded - ignore it unless asked.)
- "Type of Inspection": FOOTPLATE INSPECTION, STATION INSPECTION, LC GATE INSPECTION, COACHING DEPOT, ON TRAIN,
  SURPRISE/AMBUSH INSPECTION, WORKSITE INSPECTION, OTHER (UNUSUAL).
- "Location": station code (SUR, KWV, WADI...), level crossing gate (LC-40) or footplate section (SUR-DD).
- "Head": the ACTION DEPARTMENT responsible for fixing the item. Valid values are ONLY:
  ELECT/TRD, ELECT/G, ELECT/TRO, SIGNAL & TELECOM, OPTG, MECHANICAL, ENGINEERING,
  COMMERCIAL, C&W, PERSONNEL, SECURITY, FINANCE, MEDICAL, STORE, GSU.
  NOTE: "SAFETY" or "Safety Team" is NEVER a value of "Head"!
- "Sub Head": category inside a department.
- "Deficiencies Noted": the text of the deficiency.
- "Inspection By": the officer/team who conducted the inspection. Designations often contain "/" and a station
  code, e.g. "AEE/OP/SUR", "SSE/C&W/SUR", "ADSO/SUR", "Sr.DSO", "Sr.DSO & Safety Team", "Sr.DOM", "DRM/SUR", "ADRM".
- "Action By": the officer RESPONSIBLE for fixing it (e.g. Sr.DOM, Sr.DEN/S, Sr.DSTE). Cells may contain multiple
  comma- or slash-separated officers (e.g. "Sr.DEN/S, Sr.DSTE").
- "Feedback": compliance reply given by the department. "User Feedback/Remark": extra remark.
- "Timestamp of Compliance": when the compliance feedback was given.
- "Status": Resolved, Pending or No Response (No Response = no feedback given yet).

Interpretation rules:
- A designation written with slashes such as "AEE/OP/SUR", "EE/OP/SUR", "SSE/C&W/SUR" is an OFFICER
  (column "Inspection By" or "Action By"). The "SUR" inside it is NOT a Location. Never turn it into a Location
  filter. Keep the whole designation as one value (e.g. "AEE/OP/SUR"), op "contains".
- "last inspection(s)" / "latest inspection(s)" means the most recent inspections, not a date range
  (the app applies this itself - do not invent a date range for it).
- Department words map to "Head": Engg/Engineering/Track -> ENGINEERING, S&T/Signal/Telecom -> SIGNAL & TELECOM,
  Operating/Optg -> OPTG, Mech -> MECHANICAL, Elect TRD -> ELECT/TRD, Elect G -> ELECT/G, Elect TRO -> ELECT/TRO.
- "Safety team" / "along with safety team" / "safety branch" refers to the inspecting team in "Inspection By",
  NEVER "Head". If the user says "Sr.DSO, safety team" or "Sr.DSO with safety team", filter "Inspection By" with
  op "contains" and value "Sr.DSO" (so it matches "Sr.DSO", "Sr.DSO & Safety Team", "Sr.DSO/Safety Team", etc.).
  Only if the user asks for "safety team" WITHOUT any officer designation, use Inspection By contains "Safety".
- Officer designations (Sr DOM, Sr DEN/S, DRM, Sr DSTE, Sr DSO, ADEN...) in a question about deficiencies, pending work,
  or compliance mean "Action By", unless the user says "inspected by" / "inspection by" / "inspections by" /
  "inspection report of" / "<officer> inspections" (then use "Inspection By").
  Use op "contains" for "Action By" and "Inspection By".
- "resolved / complied / closed / attended" -> Status = Resolved (op eq).
- IMPORTANT: in SARAL "pending / open / not done / outstanding" means NOT YET RESOLVED, i.e. Status in
  ["Pending", "No Response"] (use op "in" with BOTH values), because a deficiency with no feedback yet is still pending.
  Only if the user says "pending with feedback / feedback given but pending" use Status eq Pending.
- ONLY when the user says "no reply / not responded / no feedback / no response" use Status = No Response (op eq).
- Date ranges refer to "Date of Inspection" (do NOT add duplicate Month filters if Date of Inspection is filtered).
  Only if the user says "complied/resolved ON or DURING <dates>" use "Timestamp of Compliance" instead.
- "Deficiencies Noted" and "Feedback" are long text: for "related to <word>" questions use op "contains".
- For "all deficiencies" or "inspection report of <officer>" style questions leave group_by empty so full rows return.
- "Analysis" of a department: group_by ["Sub Head", "Status"] with count, after filtering Head and dates.
"""

EXAMPLES = [
    "Sr DOM all deficiencies resolved from August to October",
    "Give me analysis of Engg department of last 5 days",
    "Which department has the most pending deficiencies?",
    "Inspection report of Sr.DSO",
    "Last 3 inspections of AEE/OP/SUR",
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
  "chart": "auto",
  "title": "<short title for the result>",
  "clarification": null
}}

Rules:
- Users make heavy spelling mistakes, glued words ("frommthe"), punctuation mistakes (".", ",", "/", "-", "&"),
  uppercase/lowercase variations, and broken grammar (e.g. "inpection report od Sr,dso"). Understand their true intent.
- op is one of: eq, ne, in, contains, gt, gte, lt, lte, between, isnull, notnull.
- Dates are ISO strings YYYY-MM-DD. "between" takes [from, to] inclusive.
  Resolve "last 5 days", "this month", "August to October", "april to october 2025" into exact dates using today's date.
  If a year is attached to the end of a month range (e.g. "april to october 2025"), apply that year to both months.
  If no year is given for a month range, use the most recent such period that is not in the future.
- Do NOT add a separate Month column filter when Date of Inspection already covers the date range.
- Use values exactly as they appear in the sample values when possible (e.g. "Sr,dso" -> "Sr.DSO").
- Use op "contains" for "Action By" and "Inspection By".
- A designation with slashes (AEE/OP/SUR, SSE/C&W/SUR) is ONE officer value for "Inspection By"/"Action By";
  its station code is NOT a Location filter.
- Use op "eq" or "in" for exact codes like "Location" (e.g. "SUR", "LC-40") and "Head".
- For "analysis"/"summary"/"department wise" questions use group_by + aggregations.
- For "show/list/give me all/inspection report of" questions leave group_by and aggregations empty so full rows come back.
- Use ONLY the table and column names listed above. Never invent columns.
- Only inherit filters from earlier conversation if the current message is clearly a follow-up refinement
  (e.g. "now only for Solapur", "what about pending ones?", "same for last month"). If the user asks a new
  standalone question, DO NOT carry over old filters.
- When unsure between two meanings, pick the most likely one and answer; do not ask unless truly impossible.
"""

SUMMARY_SYSTEM = """You are the helpful assistant inside the S.A.R.A.L railway safety app.
Write a SHORT answer (3-6 lines) in very simple words for a person who is not good with computers.
Reply in the same language style as the question (English, Hindi or Hinglish).
State both the number of inspections (if provided) and total deficiency records first, then 2-4 key points
(biggest/smallest, pending vs resolved vs no response if visible).
If the question asks "which / who / most / least / highest", begin with the direct answer (name and number) in one line.
Mention the date range used if the result title shows it. Never mention spelling mistakes.
Use only the numbers given. Do not invent anything. No tables, no markdown headings."""


# ----------------------------------------------------------------------------
# Data preparation
# ----------------------------------------------------------------------------
_DEPT_MAP = {
    "ENGINEERING": "ENGINEERING", "ENGG": "ENGINEERING",
    "GSU": "GSU",
    "ELECT/G": "ELECT/G", "ELECTG": "ELECT/G", "ELEC/G": "ELECT/G",
    "ELECT/TRD": "ELECT/TRD", "ELECTTRD": "ELECT/TRD", "TRD": "ELECT/TRD",
    "ELECT/TRO": "ELECT/TRO", "ELECTTRO": "ELECT/TRO", "TRO": "ELECT/TRO",
    "OPTG": "OPTG", "OPERATING": "OPTG",
    "SIGNAL & TELECOM": "SIGNAL & TELECOM", "S&T": "SIGNAL & TELECOM", "SNT": "SIGNAL & TELECOM",
    "MECHANICAL": "MECHANICAL", "MECH": "MECHANICAL",
    "COMMERCIAL": "COMMERCIAL", "COMML": "COMMERCIAL",
    "C&W": "C&W", "CNW": "C&W",
    "SECURITY": "SECURITY", "RPF": "SECURITY",
    "PERSONNEL": "PERSONNEL",
    "MEDICAL": "MEDICAL",
    "FINANCE": "FINANCE",
    "STORE": "STORE", "STORES": "STORE",
}


def _officer_tokens(value):
    """Split a multi-officer cell into individual designations, keeping '/' and 'C&W' intact."""
    out = []
    for p in _OFFICER_SPLIT.split(str(value)):
        p = re.sub(r"\s*\([^)]*\)\s*$", "", p).strip()
        if p:
            out.append(p)
    return out


def _clean_for_chat(d):
    d = d.copy()
    if "Head" in d.columns:
        h = (
            d["Head"].fillna("").astype(str)
            .str.replace(r"[\*\-\_\'\"]", "", regex=True)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
            .str.upper()
        )
        d["Head"] = h.map(lambda x: _DEPT_MAP.get(x, x or "UNKNOWN"))
    for c in ("Action By", "Inspection By", "Sub Head", "Type of Inspection", "Location"):
        if c in d.columns:
            d[c] = d[c].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    if "Status" in d.columns:
        st_map = {
            "resolved": "Resolved", "complied": "Resolved", "closed": "Resolved",
            "pending": "Pending",
            "no response": "No Response", "no reply": "No Response", "": "No Response",
        }
        d["Status"] = d["Status"].fillna("").astype(str).str.strip().map(
            lambda x: st_map.get(x.lower(), x)
        )
    return d


def add_status(df, classify_fn, feedback_col="Feedback", remark_col="User Feedback/Remark"):
    return _clean_for_chat(_add_status_core(df, classify_fn, feedback_col, remark_col))


def _add_status_core(df, classify_fn, feedback_col="Feedback", remark_col="User Feedback/Remark"):
    d = df.copy()

    def _row(r):
        fb = str(r.get(feedback_col, "") or "").strip()
        if not fb or fb == "`":
            return "No Response"
        s = classify_fn(r.get(feedback_col, ""), r.get(remark_col, ""))
        return s if s in ("Resolved", "Pending") else "Pending"

    key = None
    try:
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


def _parse_dates_safely(series):
    if _is_dt(series):
        return series.dt.tz_localize(None) if getattr(series.dt, "tz", None) is not None else series
    s = series.astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "NaT": pd.NA})
    iso_mask = s.notna() & s.str.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}")
    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    if iso_mask.any():
        out[iso_mask] = pd.to_datetime(s[iso_mask], errors="coerce", dayfirst=False)
    other_mask = s.notna() & (~iso_mask)
    if other_mask.any():
        out[other_mask] = pd.to_datetime(s[other_mask], errors="coerce", dayfirst=True)
    return out


def _apply_embedded_inspection_date(d):
    """Use 'DATE OF INSPECTION : yyyy-mm-dd' from the deficiency text as the real inspection date."""
    if not USE_EMBEDDED_INSPECTION_DATE:
        return d
    if "Deficiencies Noted" not in d.columns or "Date of Inspection" not in d.columns:
        return d
    if not _is_dt(d["Date of Inspection"]):
        return d
    emb = pd.to_datetime(
        d["Deficiencies Noted"].astype(str)
        .str.extract(r"DATE\s+OF\s+INSPECTION\s*:\s*(\d{4}-\d{2}-\d{2})", flags=re.I)[0],
        errors="coerce",
    )
    if emb.notna().any():
        d["Date Entered"] = d["Date of Inspection"]
        d["Date of Inspection"] = emb.fillna(d["Date of Inspection"])
    return d


def _prepare(dfs, hidden_columns):
    drop = set(INTERNAL_COLUMNS) | set(hidden_columns or [])
    out = {}
    for name, df in dfs.items():
        d = df.copy()
        d.columns = [str(c).strip() for c in d.columns]
        d = d.drop(columns=[c for c in d.columns if c in drop])
        d = _clean_for_chat(d)
        for c in d.columns:
            if _is_dt(d[c]):
                if getattr(d[c].dt, "tz", None) is not None:
                    d[c] = d[c].dt.tz_localize(None)
            elif (not _is_num(d[c])) and re.search(r"date|time", c, re.I):
                non_empty = d[c].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA}).notna().sum()
                if non_empty > 0:
                    conv = _parse_dates_safely(d[c])
                    if conv.notna().sum() / non_empty > 0.5:
                        d[c] = conv
        d = _apply_embedded_inspection_date(d)
        out[name] = d
    return out


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
                vals = vals[vals != ""].unique()
                if c in ("Action By", "Inspection By"):
                    raw_unique = sorted(vals.tolist())
                    if len(raw_unique) <= MAX_CATEGORY_VALUES:
                        lines.append(f'  - "{c}" (text) values: {raw_unique}')
                    else:
                        tokens = sorted({tok for v in vals for tok in _officer_tokens(v)})
                        lines.append(f'  - "{c}" (text, individual designations): {tokens[:MAX_CATEGORY_VALUES]}')
                elif len(vals) <= MAX_CATEGORY_VALUES:
                    lines.append(f'  - "{c}" (text) values: {list(vals)}')
                else:
                    lines.append(f'  - "{c}" (text, {len(vals)} distinct) e.g. {list(vals[:15])}')
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# AI calls (Gemini by default, Groq / Claude fallback with auto-404 recovery)
# ----------------------------------------------------------------------------
def _secret(name):
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


def _is_model_not_found(msg):
    m = str(msg).lower()
    return "404" in m or "not_found" in m or "does not exist" in m or "not found" in m


def _discover_groq_model(key):
    import requests
    r = requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=15,
    )
    if r.status_code != 200:
        return None
    ids = [
        m["id"] for m in r.json().get("data", [])
        if not any(bad in m.get("id", "").lower() for bad in ("whisper", "guard", "tts", "embed"))
    ]
    preferred = [
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "qwen/qwen3-32b",
        "openai/gpt-oss-120b",
        "llama-3.1-8b-instant",
    ]
    for p in preferred:
        if p in ids:
            return p
    return ids[0] if ids else None


def _gem_generate(client, types, cfg, model, contents, config):
    if _STATE.get("gem_think", True):
        try:
            c2 = dict(cfg, thinking_config=types.ThinkingConfig(thinking_budget=0))
            return client.models.generate_content(
                model=model, contents=contents, config=types.GenerateContentConfig(**c2)
            )
        except Exception as e:
            m = str(e)
            if _is_limit_error(m) or _is_model_not_found(m) or any(x in m for x in ("401", "403", "PERMISSION", "API key")):
                raise
            _STATE["gem_think"] = False
    return client.models.generate_content(model=model, contents=contents, config=config)


def _llm_single(provider, system, messages, max_tokens, json_mode=False):
    if provider == "gemini":
        key = _secret("GEMINI_API_KEY") or _secret("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is missing in Secrets")
        from google import genai
        from google.genai import types
        try:
            client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000))
        except Exception:
            client = genai.Client(api_key=key)
        contents = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
            for m in messages
        ]
        cfg = dict(
            system_instruction=system,
            max_output_tokens=max(max_tokens * 2, 2048),
            temperature=0.0,
        )
        if json_mode:
            cfg["response_mime_type"] = "application/json"

        candidates = []
        for cand in (
            _STATE.get("gem_model"),
            _secret("GEMINI_MODEL"),
            DEFAULT_GEMINI_MODEL,
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
        ):
            if cand and cand not in candidates:
                candidates.append(cand)

        last_err = None
        for model in candidates:
            try:
                resp = _gem_generate(
                    client, types, cfg, model=model, contents=contents,
                    config=types.GenerateContentConfig(**cfg),
                )
                _STATE["gem_model"] = model
                return (resp.text or "").strip()
            except Exception as e:
                last_err = e
                if _is_model_not_found(e) or _is_limit_error(e):
                    continue
                raise
        raise last_err

    if provider == "groq":
        key = _secret("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is missing in Secrets")
        import requests

        def _call_groq(model_name):
            payload = {
                "model": model_name,
                "temperature": 0.0,
                "max_tokens": max(max_tokens, 1500),
                "messages": [{"role": "system", "content": system}] + messages,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            return requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
                timeout=30,
            )

        model = _STATE.get("groq_model") or _secret("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        r = _call_groq(model)
        if r.status_code == 404:
            alt = _discover_groq_model(key)
            if alt and alt != model:
                model = alt
                r = _call_groq(model)
        if r.status_code != 200:
            raise RuntimeError(f"Groq {r.status_code}: {r.text[:250]}")
        _STATE["groq_model"] = model
        return (r.json()["choices"][0]["message"]["content"] or "").strip()

    key = _secret("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing in Secrets")
    import anthropic
    resp = anthropic.Anthropic(api_key=key).messages.create(
        model=_secret("SARAL_CHAT_MODEL") or DEFAULT_MODEL,
        max_tokens=max_tokens, system=system, messages=messages
    )
    return "".join(b.text for b in resp.content if getattr(b, "text", None)).strip()


def _providers():
    avail = {
        "gemini": bool(_secret("GEMINI_API_KEY") or _secret("GOOGLE_API_KEY")),
        "groq": bool(_secret("GROQ_API_KEY")),
        "claude": bool(_secret("ANTHROPIC_API_KEY")),
    }
    order = [p for p in ("gemini", "groq", "claude") if avail[p]]
    forced = str(_secret("LLM_PROVIDER") or "").strip().lower()
    if forced in avail and avail[forced]:
        order = [forced] + [p for p in order if p != forced]
    return order


def _llm(system, messages, max_tokens, json_mode=False):
    order = _providers()
    if not order:
        raise RuntimeError("No API key found in Secrets (add GEMINI_API_KEY or GROQ_API_KEY)")
    errors, tried, limited = [], 0, 0
    for p in order:
        if time.time() < _STATE.get("off_" + p, 0):
            continue
        tried += 1
        try:
            out = _llm_single(p, system, messages, max_tokens, json_mode)
            _STATE["used"] = p
            return out
        except Exception as e:
            errors.append(f"{p}: {e}")
            if _is_limit_error(e):
                limited += 1
                _STATE["off_" + p] = time.time() + 900
    if tried == 0 or limited == tried:
        raise RuntimeError("429 RESOURCE_EXHAUSTED: all AI free limits are used up")
    raise RuntimeError(" | ".join(errors))


def _looks_like_followup(question):
    ql = " " + re.sub(r"\s+", " ", question.lower().strip()) + " "
    return bool(re.search(
        r"^\s*(only|now|also|same|and|what about|just|sirf|ab|aur|but|then|except|exclude|without)\b"
        r"|\b(of this|of these|of them|same for|same as|those|above|previous)\b",
        ql
    ))


def _ask_plan(question, tables, history, hint):
    system = PLAN_SYSTEM.format(
        today=dt.date.today().isoformat(),
        hint=hint or "",
        schema=_schema_text(tables),
    )
    msgs = []
    if history and _looks_like_followup(question):
        for h in history[-2:]:
            msgs.append({"role": "user", "content": h["q"]})
            msgs.append({"role": "assistant", "content": json.dumps(h["plan"], default=str)})
    cleaned_q = _normalize_query_text(question).strip()
    msgs.append({"role": "user", "content": f"{question}\n(Normalized: {cleaned_q})"})
    text = _llm(system, msgs, 1200, json_mode=True)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Could not understand the question. Please rephrase.")
    return json.loads(m.group(0))


def _ask_summary(question, title, total, insp_count, result):
    sample = result.head(MAX_ROWS_TO_AI).to_csv(index=False)
    if len(sample) > 12000:
        sample = sample[:12000]
    insp_line = f"Unique inspections in result: {insp_count}\n" if insp_count is not None else ""
    content = (
        f"Question: {question}\nResult title: {title}\n"
        f"{insp_line}Total deficiency rows in result: {total}\nFirst rows (CSV):\n{sample}"
    )
    return _llm(SUMMARY_SYSTEM, [{"role": "user", "content": content}], 400).strip()


# ----------------------------------------------------------------------------
# Safe plan executor & S.A.R.A.L. plan sanitizer
# ----------------------------------------------------------------------------
def _norm(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def _col(df, name):
    if name in df.columns:
        return name
    for c in df.columns:
        if c.lower().strip() == str(name).lower().strip():
            return c
    close = difflib.get_close_matches(str(name), list(df.columns), n=1, cutoff=0.75)
    if close:
        return close[0]
    raise KeyError(f'Column "{name}" not found')


def _strip_safety_team_phrase(val):
    """Turn 'Sr.DSO, safety team' or 'Sr.DSO & Safety' into 'Sr.DSO' while keeping pure 'Safety Team' as 'Safety'."""
    s = str(val).strip()
    cleaned = re.sub(
        r"(?:[,;&+/]|\b(?:and|with|along\s+with)\b)?\s*\b(?:safety|saftey)\s*(?:team|tem|teem|branch|dept|department)?\b",
        "", s, flags=re.I
    ).strip(" ,;&+/()")
    return cleaned if cleaned else "Safety"


def _sanitize_plan(plan, df):
    """Fix common S.A.R.A.L. domain misinterpretations before running filters."""
    plan = json.loads(json.dumps(plan))
    raw_filters = plan.get("filters") or []
    if isinstance(raw_filters, dict):
        raw_filters = [{"column": k, "op": "eq", "value": v} for k, v in raw_filters.items()]

    has_date_range = any(
        str(f.get("column", "")).strip().lower() == "date of inspection"
        and str(f.get("op", "")).lower() in ("between", "gte", "gt", "lte", "lt", "eq")
        for f in raw_filters if isinstance(f, dict)
    )
    has_insp_by = any(
        str(f.get("column", "")).strip().lower() == "inspection by"
        for f in raw_filters if isinstance(f, dict)
    )

    cleaned = []
    for f in raw_filters:
        if not isinstance(f, dict) or "column" not in f:
            continue
        col_raw = str(f["column"]).strip()
        val = f.get("value")

        # 1. "SAFETY" / "Safety Team" is NEVER a Head department in S.A.R.A.L.; it belongs to Inspection By
        if col_raw.lower() == "head" and isinstance(val, str) and _norm(val) in ("safety", "safetyteam", "safetytem", "safetybranch"):
            if not has_insp_by and "Inspection By" in df.columns:
                cleaned.append({"column": "Inspection By", "op": "contains", "value": "Safety"})
                has_insp_by = True
            continue

        # 2. Drop redundant Month filter when Date of Inspection already filters the date window
        if has_date_range and col_raw.lower() in ("month", "inspection month"):
            continue

        # 3. Clean "Sr.DSO, safety team" -> "Sr.DSO" on Inspection By / Action By
        if col_raw.lower() in ("inspection by", "action by") and isinstance(val, str):
            val = _strip_safety_team_phrase(val)
            f = dict(f, value=val)
            if str(f.get("op", "")).lower() in ("eq", "in"):
                f["op"] = "contains"

        cleaned.append(_fix_status_filter(f))

    plan["filters"] = cleaned
    return plan


# Designations starting with these letters may be written without the leading "A"
# (users type "EE/OP/SUR" for "AEE/OP/SUR").
_LEAD_A_OK = {"ee", "en", "ste"}


def _designation_regex(value):
    """Regex for one designation: punctuation-insensitive, whole-token, never inside another word."""
    chunks = re.findall(r"[a-z0-9]+", str(value).lower())
    if not chunks:
        return None
    lead = r"(?<![a-z0-9])" + ("a?" if chunks[0] in _LEAD_A_OK else "")
    body = r"[^a-z0-9]*".join(re.escape(c) for c in chunks)
    return re.compile(lead + body + r"(?![a-z0-9])")


def _token_boundary_mask(series, value):
    rx = _designation_regex(value)
    if rx is None:
        return pd.Series(False, index=series.index)
    return series.astype(str).str.lower().map(lambda s: bool(rx.search(s)))


def _text_mask(series, value, mode="exact"):
    ns = series.astype(str).map(_norm)
    nv = _norm(value)
    if not nv:
        return ns == ""
    if mode == "exact":
        return ns == nv
    if mode == "token":
        # Whole-designation matching on the raw cell, so "Sr.DSO" finds "Sr.DSO & Safety Team",
        # and "AEE/OP/SUR" is never broken into "AEE", "OP", "SUR".
        return _token_boundary_mask(series, value)
    return ns.str.contains(re.escape(nv), na=False)


def _apply_filter(df, f):
    if not isinstance(f, dict) or "column" not in f or "op" not in f:
        return df
    c = _col(df, f["column"])
    op, v, s = str(f["op"]).lower().strip(), f.get("value"), df[c]
    is_date = _is_dt(s)

    if op in ("isnull", "notnull"):
        blank = s.isna() | (s.astype(str).str.strip() == "")
        return df[blank] if op == "isnull" else df[~blank]
    if v is None:
        return df
    if op == "between":
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            return df
        lo, hi = v
        if is_date:
            d_lo, d_hi = pd.to_datetime(lo, errors="coerce"), pd.to_datetime(hi, errors="coerce")
            if pd.isna(d_lo) or pd.isna(d_hi):
                return df
            return df[(s >= d_lo) & (s < d_hi + pd.Timedelta(days=1))]
        return df[(s >= lo) & (s <= hi)]
    if op in ("gt", "gte", "lt", "lte"):
        v_cmp = pd.to_datetime(v, errors="coerce") if is_date else v
        if is_date and pd.isna(v_cmp):
            return df
        return df[{"gt": s > v_cmp, "gte": s >= v_cmp, "lt": s < v_cmp, "lte": s <= v_cmp}[op]]
    if op == "contains":
        mode = "token" if c in ("Action By", "Inspection By", "Location") else "contains"
        return df[_text_mask(s, v, mode=mode)]
    if op in ("eq", "ne", "in"):
        vals = v if isinstance(v, list) else [v]
        if is_date:
            mask = s.dt.normalize().isin(pd.to_datetime(vals, errors="coerce").normalize())
        elif _is_num(s):
            mask = s.isin([float(x) for x in vals])
        else:
            mode = "token" if c in ("Action By", "Inspection By") else "exact"
            mask = pd.Series(False, index=df.index)
            for x in vals:
                mask |= _text_mask(s, x, mode=mode)
        return df[~mask] if op == "ne" else df[mask]
    raise ValueError(f"Unsupported filter: {op}")


def _fix_status_filter(f):
    if f.get("column") == "Status" and f.get("op") in ("eq", "in"):
        vals = f["value"] if isinstance(f["value"], list) else [f["value"]]
        if [str(v).strip().lower() for v in vals] == ["pending"]:
            return dict(f, op="in", value=["Pending", "No Response"])
    return f


def _keep_last_n_inspections(df, n):
    """Keep only rows of the n most recent inspections (Date + Inspection By + Type)."""
    kc = [c for c in ("Date of Inspection", "Inspection By", "Type of Inspection") if c in df.columns]
    if df.empty or not kc:
        return df
    work = df.reset_index(drop=True)
    parts = []
    for c in kc:
        if _is_dt(work[c]):
            parts.append(work[c].dt.normalize().dt.strftime("%Y-%m-%d").fillna(""))
        else:
            parts.append(work[c].fillna("").astype(str).str.strip().str.upper())
    key = parts[0]
    for p in parts[1:]:
        key = key + "|" + p
    if "Date of Inspection" in kc and _is_dt(work["Date of Inspection"]):
        latest = work.assign(_k=key).groupby("_k")["Date of Inspection"].max().sort_values(ascending=False)
        keep = set(latest.head(n).index)
    else:
        keep = set(pd.unique(key)[:n])
    return df[key.isin(keep).values]


def _filter_df(plan, tables):
    name = plan.get("table")
    if name not in tables:
        name = next(iter(tables))
    df = tables[name]
    sanitized = _sanitize_plan(plan, df)
    for f in sanitized.get("filters") or []:
        df = _apply_filter(df, f)
    n_last = sanitized.get("last_n_inspections")
    if n_last:
        try:
            df = _keep_last_n_inspections(df, int(n_last))
        except Exception:
            pass
    return df, sanitized


def _aggregate_df(df, plan):
    group_by = []
    for g in plan.get("group_by") or []:
        try:
            col = _col(df, g)
            if col not in group_by:
                group_by.append(col)
        except KeyError:
            pass

    aggs = plan.get("aggregations") or []
    if group_by and aggs:
        spec = {}
        for a in aggs:
            func = a.get("func", "count")
            raw_col = a.get("column")
            if raw_col in (None, "*") or func == "count":
                col = group_by[0]
                func = "count" if raw_col in (None, "*") else func
            else:
                col = _col(df, raw_col)
            out_name = a.get("as") or f"{func}_{col}"
            if out_name in group_by:
                out_name = f"{out_name}_count"
            spec[out_name] = pd.NamedAgg(column=col, aggfunc=func)
        result = df.groupby(group_by, dropna=False).agg(**spec).reset_index()
    elif group_by:
        result = df.groupby(group_by, dropna=False).size().reset_index(name="Count")
    else:
        result = df
        cols = []
        for c in plan.get("columns") or []:
            try:
                cols.append(_col(df, c))
            except KeyError:
                pass
        if cols:
            result = df[cols]

    if plan.get("sort_by"):
        try:
            result = result.sort_values(
                _col(result, plan["sort_by"]),
                ascending=bool(plan.get("ascending", False))
            )
        except KeyError:
            pass
    elif group_by and len(result.columns) > len(group_by):
        val_col = result.columns[-1]
        if len(group_by) > 1:
            totals = result.groupby(group_by[0])[val_col].transform("sum")
            result = result.assign(_tot=totals).sort_values(
                ["_tot", group_by[0], val_col], ascending=[False, True, False]
            ).drop(columns=["_tot"])
        else:
            result = result.sort_values(val_col, ascending=False)
    elif not group_by:
        dcols = [c for c in result.columns if _is_dt(result[c])]
        if dcols:
            result = result.sort_values(dcols[0], ascending=False)

    if plan.get("limit"):
        try:
            result = result.head(int(plan["limit"]))
        except Exception:
            pass
    return result.reset_index(drop=True)


# ----------------------------------------------------------------------------
# Inspection-level summary (matches S.A.R.A.L. "View Records" inspection count)
# ----------------------------------------------------------------------------
def _inspection_summary(df):
    """Group deficiency rows into unique inspections (Date + Inspection By + Type of Inspection)."""
    if df.empty:
        return pd.DataFrame()
    key_cols = [c for c in ("Date of Inspection", "Inspection By", "Type of Inspection") if c in df.columns]
    if not key_cols:
        return pd.DataFrame()

    work = df.copy()
    norm_keys = []
    for c in key_cols:
        nk = f"_k_{c}"
        if _is_dt(work[c]):
            work[nk] = work[c].dt.normalize()
        else:
            work[nk] = work[c].fillna("").astype(str).str.strip().str.upper()
        norm_keys.append(nk)

    rows = []
    for _, grp in work.groupby(norm_keys, dropna=False, sort=False):
        first = grp.iloc[0]
        rec = {c: first[c] for c in key_cols}
        if "Location" in grp.columns:
            locs = sorted({str(x).strip() for x in grp["Location"].dropna() if str(x).strip()})
            rec["Locations"] = ", ".join(locs[:8]) + ("…" if len(locs) > 8 else "")
        rec["Deficiencies"] = len(grp)
        if "Status" in grp.columns:
            vc = grp["Status"].value_counts()
            rec["Resolved"] = int(vc.get("Resolved", 0))
            rec["Pending"] = int(vc.get("Pending", 0))
            rec["No Response"] = int(vc.get("No Response", 0))
        rows.append(rec)

    out = pd.DataFrame(rows)
    if "Date of Inspection" in out.columns and _is_dt(out["Date of Inspection"]):
        out = out.sort_values("Date of Inspection", ascending=False)
    return out.reset_index(drop=True)


# ----------------------------------------------------------------------------
# Basic mode (spelling-, glued-word- & punctuation-tolerant rules fallback)
# ----------------------------------------------------------------------------
_STATE = {}
_PLAN_CACHE = {}
_STATUS_CACHE = {}
_PREP_CACHE = {}

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12
}

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

_TYPO_MAP = {
    "inpection": "inspection", "inpections": "inspections",
    "isnpections": "inspections", "isnpection": "inspection",
    "inspecion": "inspection", "inspecions": "inspections",
    "inspecton": "inspection", "inspectons": "inspections",
    "inspectn": "inspection", "inspn": "inspection", "insp": "inspection",
    "defficiency": "deficiency", "defficiencies": "deficiencies",
    "deficency": "deficiency", "deficencies": "deficiencies",
    "deficincy": "deficiency", "defs": "deficiencies",
    "defficicies": "deficiencies", "defficiecies": "deficiencies", "defficiences": "deficiencies",
    "deficiences": "deficiencies", "deficienies": "deficiencies", "defficicy": "deficiency",
    "reprt": "report", "rport": "report",
    "anlysis": "analysis", "analisys": "analysis", "summry": "summary",
    "saftey": "safety", "safey": "safety",
    "tem": "team", "teem": "team",
    "od": "of", "fo": "of",
}

_BASIC_HELP = (
    "I can answer questions like:\n\n"
    "- Sr DOM all deficiencies resolved from August to October\n"
    "- Which department has most pending deficiencies this month\n"
    "- Engg analysis of last 7 days\n"
    "- Inspection report of Sr.DSO\n"
    "- Last 3 inspections of AEE/OP/SUR\n\n"
    "Please type your question with a department or officer, a status (pending / resolved) "
    "and a period (last 7 days, this month, August to October)."
)


def _normalize_query_text(question):
    q = re.sub(r"[^a-z0-9&/ ]+", " ", question.lower())
    # Split glued prepositions like "frommthe", "fromthe", "inthe", "ofthe"
    q = re.sub(r"\b(from+)(the)\b", r"from \2", q)
    q = re.sub(r"\b(in|of|to|on|at)(the)\b", r"\1 \2", q)
    words = [_TYPO_MAP.get(w, w) for w in q.split()]
    return " " + " ".join(words) + " "


def _prepare_cached(dfs, hidden):
    try:
        key = (CHATBOT_VERSION, USE_EMBEDDED_INSPECTION_DATE) + tuple(
            (n, d.shape, tuple(d.columns), int(pd.util.hash_pandas_object(d.astype(str), index=False).sum()))
            for n, d in dfs.items()
        ) + (tuple(hidden or []),)
    except Exception:
        return _prepare(dfs, hidden)
    if _PREP_CACHE.get("key") != key:
        _PREP_CACHE["key"], _PREP_CACHE["val"] = key, _prepare(dfs, hidden)
    return _PREP_CACHE["val"]


def _ai_available():
    order = _providers()
    return bool(order) and any(time.time() >= _STATE.get("off_" + p, 0) for p in order)


def _is_limit_error(msg):
    m = str(msg).lower()
    return "429" in m or "resource_exhausted" in m or "quota" in m


def _ask_plan_cached(question, tables, history, hint):
    last = json.dumps(history[-1]["plan"], sort_keys=True, default=str) if (history and _looks_like_followup(question)) else ""
    key = (
        CHATBOT_VERSION,
        re.sub(r"\s+", " ", question.strip().lower()),
        dt.date.today().isoformat(),
        last,
        tuple(len(d) for d in tables.values()),
    )
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


def _rule_dates(ql):
    today = dt.date.today()
    one = dt.timedelta(days=1)
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

    ql_date = re.sub(r"\bmay\s+(?:be|have|not|also)\b", " ", ql)
    month_rx = r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")(?:\s+(20\d{2}))?\b"
    found = re.findall(month_rx, ql_date)
    if found:
        m1, y1_str = _MONTHS[found[0][0]], found[0][1]
        m2, y2_str = _MONTHS[found[-1][0]], found[-1][1]

        if y1_str and y2_str:
            y1, y2 = int(y1_str), int(y2_str)
        elif y2_str:
            y2 = int(y2_str)
            y1 = y2 if m1 <= m2 else y2 - 1
        elif y1_str:
            y1 = int(y1_str)
            y2 = y1 if m2 >= m1 else y1 + 1
        else:
            y2 = today.year if m2 <= today.month else today.year - 1
            y1 = y2 if m1 <= m2 else y2 - 1

        start, end = dt.date(y1, m1, 1), min(_month_end(y2, m2), today)
        if start <= end:
            return start, end
    return None


def _last_n_from_question(question):
    """'last inspection' -> 1, 'last 3 inspections' -> 3, 'last inspections' -> 5, else None."""
    ql = _normalize_query_text(question)
    m = re.search(r"\b(?:last|latest|recent|newest)\s+(\d+)\s+inspections?\b", ql)
    if m:
        return max(1, int(m.group(1)))
    m = re.search(r"\b(?:last|latest|recent|newest)\s+(inspections?)\b", ql)
    if m:
        return 1 if m.group(1) == "inspection" else 5
    return None


def _detect_officer_col(ql, df):
    if "Inspection By" not in df.columns:
        return "Action By"
    if re.search(r"\b(?:insp(?:ected|ections?)(?:\s+done)?\s+by|noted\s+by|pointed\s+out\s+by|inspection\s+report)\b", ql):
        return "Inspection By"
    if re.search(r"\binspections?\b", ql) and not re.search(r"\b(?:action\s+by|deficienc|pending|resolved|compliance)\b", ql):
        return "Inspection By"
    # "<officer> last inspections ... deficiencies list": an inspection-centric question
    if re.search(r"\b(?:last|latest|recent)\s+(?:\d+\s+)?inspections?\b", ql):
        return "Inspection By"
    return "Action By"


def _find_officer(ql, df, col):
    toks = [_norm(t) for t in ql.split() if _norm(t)]
    cand = (
        set(toks)
        | {a + b for a, b in zip(toks, toks[1:])}
        | {a + b + c for a, b, c in zip(toks, toks[1:], toks[2:])}
        | {a + b + c + d for a, b, c, d in zip(toks, toks[1:], toks[2:], toks[3:])}
    )
    all_vals = {
        tok
        for v in df[col].dropna().astype(str).unique()
        for tok in _officer_tokens(v)
    }
    best_len, hits = 0, []
    variant_map = {}
    for v in all_vals:
        n = _norm(v)
        if len(n) < 3 or n in ("safety", "safetyteam", "team"):
            continue
        variants = {n: v}
        if n.startswith("sr") and len(n) > 4:
            variants[n[2:]] = v
        if n.startswith("a") and len(n) > 5:
            variants[n[1:]] = v
        for var, val in variants.items():
            variant_map[var] = val
            if var in cand:
                if len(var) > best_len:
                    best_len, hits = len(var), [val]
                elif len(var) == best_len and val not in hits:
                    hits.append(val)

    if not hits and variant_map:
        for c_tok in sorted(cand, key=len, reverse=True):
            if len(c_tok) >= 5:
                close = difflib.get_close_matches(c_tok, list(variant_map.keys()), n=1, cutoff=0.82)
                if close:
                    hits = [variant_map[close[0]]]
                    break
    return hits


def _enforce_officer(plan, question, df):
    """
    AI planners sometimes read the station code inside a designation as a Location
    ("EE/OP/SUR" -> Location SUR). Find the designation deterministically from the
    question and make sure it is filtered as an officer, dropping the wrong Location/Head filter.
    """
    try:
        ql = _normalize_query_text(question)
        main = _detect_officer_col(ql, df)
        other = "Inspection By" if main == "Action By" else "Action By"
        col, hits = main, []
        if main in df.columns:
            hits = _find_officer(ql, df, main)
        if not hits and other in df.columns:
            hits = _find_officer(ql, df, other)
            col = other
        if not hits:
            return plan
        hit = hits[0]
        nv = _norm(hit)
        plan = json.loads(json.dumps(plan))
        kept = []
        for f in plan.get("filters") or []:
            if not isinstance(f, dict):
                continue
            c = str(f.get("column", "")).strip().lower()
            fv = f.get("value")
            fvs = fv if isinstance(fv, list) else [fv]
            fns = [_norm(x) for x in fvs if isinstance(x, str) and _norm(x)]
            if c in ("location", "head") and any(x in nv and x != nv for x in fns):
                continue  # station code / word taken from inside the designation
            if c in ("inspection by", "action by") and any(x in nv or nv in x for x in fns):
                continue  # replaced by the exact designation below
            kept.append(f)
        kept.append({"column": col, "op": "contains", "value": hit})
        plan["filters"] = kept
        return plan
    except Exception:
        return plan


def _rule_plan(question, tables, prev=None):
    df = next(iter(tables.values()))
    tname = next(iter(tables))
    ql = _normalize_query_text(question)
    if re.fullmatch(r"\s*(hi|hii|hello|hey|hlo|help|namaste)\s*", ql) or "what can you do" in ql:
        return {"clarification": "Hello! " + _BASIC_HELP}

    filters, parts = [], []
    date_col = "Date of Inspection" if "Date of Inspection" in df.columns else next(
        (c for c in df.columns if _is_dt(df[c])), None
    )
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
        sts = ["Pending"]
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
        alias_to_target = {w: t for t, words in _DEPT_WORDS.items() for w in words}
        for target, words in _DEPT_WORDS.items():
            if any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", ql) for w in words):
                real = [h for h in heads if _norm(target) == _norm(h)]
                found.append(real[0] if real else target)
        if not found:
            for tok in ql.split():
                if len(tok) >= 5:
                    close = difflib.get_close_matches(tok, list(alias_to_target.keys()), n=1, cutoff=0.82)
                    if close:
                        target = alias_to_target[close[0]]
                        real = [h for h in heads if _norm(target) == _norm(h)]
                        found.append(real[0] if real else target)
                        break
        if found:
            dept_filtered = True
            filters.append({"column": "Head", "op": "in", "value": found})
            parts.append(" / ".join(found))

    ocol = _detect_officer_col(ql, df)
    if ocol in df.columns:
        offs = _find_officer(ql, df, ocol)
        if offs:
            filters.append(
                {"column": ocol, "op": "in", "value": offs}
                if len(offs) > 1
                else {"column": ocol, "op": "contains", "value": offs[0]}
            )
            parts.append(f"{'Inspected by ' if ocol == 'Inspection By' else ''}{' / '.join(offs)}")
        elif re.search(r"\bsafety\s*(?:team|branch)\b", ql) and "Inspection By" in df.columns:
            filters.append({"column": "Inspection By", "op": "contains", "value": "Safety"})
            parts.append("Inspected by Safety Team")

    if "Location" in df.columns:
        locs = {_norm(x): x for x in df["Location"].dropna().astype(str).unique() if _norm(x)}
        words = (
            re.findall(r"(?:at|in|station|stn|location|gate)\s+([a-z0-9\-]+)", ql)
            + re.findall(r"([a-z0-9\-]+)\s+(?:station|stn)\b", ql)
        )
        hit = next((w for w in words if _norm(w) in locs), None)
        if hit:
            filters.append({"column": "Location", "op": "eq", "value": locs[_norm(hit)]})
            parts.append(locs[_norm(hit)])

    toks_n = [_norm(t) for t in ql.split() if _norm(t)]
    cand_n = set(toks_n) | {a + b for a, b in zip(toks_n, toks_n[1:])}
    if "Sub Head" in df.columns:
        for v in df["Sub Head"].dropna().astype(str).unique():
            hit = [
                x for x in {_norm(v), _norm(re.sub(r"\(.*?\)", "", v))}
                if len(x) >= 3 and x in cand_n and x not in ("other", "others", "general", "nil", "none")
            ]
            if hit and not any(f["column"] == "Sub Head" for f in filters):
                filters.append({"column": "Sub Head", "op": "eq", "value": v})
                parts.append(v)

    if "Type of Inspection" in df.columns:
        for key, rx in (
            ("footplate", r"foot ?plate"),
            ("lc gate", r"\blc gate|level crossing"),
            ("coaching", r"\bcoaching\b"),
            ("on train", r"\bon train\b"),
            ("surprise", r"surprise|ambush"),
            ("worksite", r"work ?site"),
            ("station inspection", r"station inspection"),
        ):
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
    is_insp_report = bool(re.search(r"\binspection\s+report\b", ql)) and bool(filters)
    wise = None if is_insp_report else re.search(r"\bwise\b|\banalysis\b|\banalyse\b|\banalyze\b|\bsummary\b|\breport\b", ql)

    dims = [
        ("Sub Head", r"sub ?head|category|categories"),
        ("Type of Inspection", r"type of inspection|inspection type"),
        ("Location", r"\bstations?\b|\blocations?\b|\bgates?\b"),
        ("Action By", r"\bofficers?\b|\bofficials?\b"),
        ("Status", r"\bstatus\b"),
        ("Head", r"\bdept\b|\bdeptt\b|\bdpt\b|\bdepartments?\b|\bhead\b|\bbranch\b"),
    ]
    dim = next((c for c, rx in dims if c in df.columns and re.search(rx, ql)), None)

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

    if prev and _looks_like_followup(question) and (filters or group_by):
        base = json.loads(json.dumps(prev))
        newcols = {f["column"] for f in filters}
        gb = group_by or (
            [] if re.search(r"\b(list|show all|details|rows|records)\b", ql)
            else (base.get("group_by") or [])
        )
        old_filters = [f for f in (base.get("filters") or []) if f["column"] not in newcols]
        base.update(
            filters=old_filters + filters,
            group_by=gb,
            clarification=None,
            aggregations=[{"column": "*", "func": "count", "as": "Deficiencies"}] if gb else [],
            title="Deficiencies" + (" · " + " · ".join(parts) if parts else ""),
        )
        if gb and rank:
            base.update(sort_by="Deficiencies", ascending=asc)
        return base

    if not filters and not group_by:
        return {"clarification": "I could not understand that. " + _BASIC_HELP}

    plan = {
        "table": tname,
        "filters": filters,
        "group_by": group_by,
        "columns": [],
        "limit": None,
        "chart": "auto",
        "clarification": None,
        "sort_by": None,
        "ascending": False,
        "aggregations": [{"column": "*", "func": "count", "as": "Deficiencies"}] if group_by else [],
        "title": "Deficiencies" + (" · " + " · ".join(parts) if parts else ""),
    }
    if group_by and rank:
        plan["sort_by"], plan["ascending"] = "Deficiencies", asc
    return plan


def _explain_plan(plan):
    def d(x):
        try:
            return f"{dt.date.fromisoformat(str(x)[:10]):%d %b %Y}"
        except Exception:
            return str(x)

    out = []
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
    if plan.get("last_n_inspections"):
        n = int(plan["last_n_inspections"])
        out.append(f"only the latest {n} inspection{'s' if n > 1 else ''}")
    if plan.get("group_by"):
        out.append("counted by " + " and ".join(plan["group_by"]))
    return out


def _nm(x):
    return x.strftime("%d-%m-%Y") if isinstance(x, pd.Timestamp) else str(x)


def _local_summary(title, result, plan, raw_filtered, insp_count=None):
    num = [c for c in result.columns if _is_num(result[c])]
    k = _kpis(raw_filtered, plan, insp_count=insp_count)
    insp_prefix = (
        f"**{insp_count} inspections** ({len(raw_filtered)} deficiencies)"
        if insp_count is not None
        else f"**{len(raw_filtered)} records**"
    )

    if plan.get("group_by") and num:
        asc = bool(plan.get("ascending"))
        val = num[-1]
        g = [c for c in result.columns if c not in num]
        lines = [f"{insp_prefix} found: {title}."]
        if g:
            s = result.groupby(g[0])[val].sum().sort_values(ascending=asc)
            label = {"Head": "department", "Action By": "officer", "Location": "location"}.get(g[0], g[0])
            lines.append(f"{'Least' if asc else 'Most'} for {label}: **{_nm(s.index[0])}** ({int(s.iloc[0])}).")
            if len(s) > 1:
                lines.append("Next: " + ", ".join(f"{_nm(idx)} ({int(v)})" for idx, v in s.iloc[1:4].items()) + ".")
        if "Resolved" in k:
            comp_txt = f" Compliance **{k['Compliance %']}%**." if "Compliance %" in k else ""
            lines.append(
                f"Resolved **{k['Resolved']}**, not yet resolved **{k['Pending'] + k['No Response']}** "
                f"(pending {k['Pending']}, no response {k['No Response']}).{comp_txt}"
            )
        return "\n\n".join(lines)

    lines = [f"{insp_prefix} found: {title}."]
    if "Resolved" in k:
        comp_txt = f" Compliance **{k['Compliance %']}%**." if "Compliance %" in k else ""
        lines.append(
            f"Resolved **{k['Resolved']}**, not yet resolved **{k['Pending'] + k['No Response']}** "
            f"(feedback pending {k['Pending']}, no feedback {k['No Response']}).{comp_txt}"
        )
    return "\n\n".join(lines)


# ----------------------------------------------------------------------------
# Insights: KPIs, auto charts, quick findings, analysis
# ----------------------------------------------------------------------------
def _kpis(df, plan=None, insp_count=None):
    total = len(df)
    out = {}
    if insp_count is not None:
        out["Inspections"] = insp_count
    if "Status" not in df.columns:
        out["Deficiencies" if insp_count is not None else "Total records"] = total
        return out
    vc = df["Status"].value_counts()
    res = int(vc.get("Resolved", 0))
    pend = int(vc.get("Pending", 0))
    no_resp = int(vc.get("No Response", 0))
    out["Deficiencies" if insp_count is not None else "Total"] = total
    out["Resolved"] = res
    out["Pending"] = pend
    out["No Response"] = no_resp

    status_filtered_open = False
    for f in (plan or {}).get("filters") or []:
        if f.get("column") == "Status":
            vals = f.get("value") if isinstance(f.get("value"), list) else [f.get("value")]
            if "Resolved" not in [str(v) for v in vals]:
                status_filtered_open = True
    if not status_filtered_open:
        out["Compliance %"] = round(100 * res / total, 1) if total else 0
    return out


def _insights(df):
    out, cols = [], df.columns
    if df.empty:
        return out
    labels = {"Head": "department", "Action By": "officer", "Location": "location"}
    for col, label in labels.items():
        if col in cols and df[col].nunique() > 1:
            vc = df[col].astype(str).value_counts()
            out.append(f"Most records for {label}: **{vc.index[0]}** ({int(vc.iloc[0])} of {len(df)})")
    if "Status" in cols and "Date of Inspection" in cols and _is_dt(df["Date of Inspection"]):
        today = pd.Timestamp(dt.date.today())
        op = df[(df["Status"] != "Resolved") & df["Date of Inspection"].notna()]
        if not op.empty:
            r = op.sort_values("Date of Inspection").iloc[0]
            age = (today - r["Date of Inspection"]).days
            loc = f", {r['Location']}" if "Location" in op.columns and r["Location"] else ""
            out.append(f"Oldest open item is **{age} days** old ({r['Date of Inspection']:%d-%m-%Y}{loc})")
            over30 = int(((today - op["Date of Inspection"]).dt.days > 30).sum())
            if over30:
                out.append(f"**{over30}** open items are older than 30 days")
    return out


_TDC_RX = re.compile(r"T\.?\s*D\.?\s*C\.?\s*[:\-]?\s*(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})", re.I)


def _parse_tdc(text):
    """Target date of compliance from feedback like 'TDC 30.11.2026' / 'T.D.C - 30.11.2026'."""
    m = _TDC_RX.search(str(text))
    if not m:
        return pd.NaT
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return pd.Timestamp(y, mo, d)
    except Exception:
        return pd.NaT


def _analysis(df, insp_df=None):
    """Analytical findings (what is weak, what is overdue, what repeats) from the filtered records."""
    out = []
    if df.empty or "Status" not in df.columns:
        return out
    today = pd.Timestamp(dt.date.today())
    total = len(df)
    openm = df["Status"] != "Resolved"
    n_open = int(openm.sum())
    has_date = "Date of Inspection" in df.columns and _is_dt(df["Date of Inspection"])

    pct = 100 * (total - n_open) / total
    if n_open == 0:
        out.append(f"**Verdict:** all {total} deficiencies are resolved - full compliance.")
    else:
        level = "good" if pct >= 90 else "moderate" if pct >= 75 else "weak"
        out.append(f"**Verdict:** compliance is {level} - **{pct:.0f}%** resolved, **{n_open}** of {total} still open.")

    # Department strength / backlog
    if "Head" in df.columns and df["Head"].nunique() > 1:
        g = df.groupby("Head")["Status"].agg(total="size", res=lambda s: int((s == "Resolved").sum()))
        g["open"] = g["total"] - g["res"]
        g["pct"] = 100 * g["res"] / g["total"]
        big = g[g["total"] >= 3]
        if not big.empty:
            wn = big.sort_values(["pct", "total"], ascending=[True, False]).index[0]
            w = big.loc[wn]
            if w["pct"] < 100:
                out.append(
                    f"**Weakest department:** {wn} - only {int(w['res'])} of {int(w['total'])} resolved ({w['pct']:.0f}%)"
                )
        if n_open:
            top = g["open"].idxmax()
            if g.loc[top, "open"] > 0:
                share = 100 * g.loc[top, "open"] / n_open
                out.append(f"**Biggest backlog:** {top} holds {int(g.loc[top, 'open'])} open items ({share:.0f}% of all open)")

    # Officer load
    if "Action By" in df.columns and n_open:
        o = df.loc[openm, "Action By"].map(_officer_tokens).explode().dropna().astype(str)
        o = o[o.str.strip() != ""]
        vc = o.value_counts()
        if len(vc):
            out.append(f"**Officer with most open items:** {vc.index[0]} ({int(vc.iloc[0])})")

    # Ageing
    if has_date and n_open:
        ages = (today - df.loc[openm, "Date of Inspection"].dropna()).dt.days
        if len(ages):
            a = int((ages <= 7).sum())
            b = int(((ages > 7) & (ages <= 30)).sum())
            c = int((ages > 30).sum())
            out.append(f"**Ageing of open items:** {a} up to 7 days, {b} between 8-30 days, {c} older than 30 days")

    # Target date (TDC) overdue
    if "Feedback" in df.columns and n_open:
        tdc = pd.to_datetime(df.loc[openm, "Feedback"].map(_parse_tdc), errors="coerce")
        with_tdc = int(tdc.notna().sum())
        if with_tdc:
            overdue = int((tdc < today).sum())
            due7 = int(((tdc >= today) & (tdc <= today + pd.Timedelta(days=7))).sum())
            out.append(
                f"**Target dates (TDC):** {with_tdc} open items have one - **{overdue} already overdue**, "
                f"{due7} fall due within 7 days"
            )

    # Speed of compliance
    if has_date and "Timestamp of Compliance" in df.columns:
        r = df[df["Status"] == "Resolved"]
        ts = pd.to_datetime(r["Timestamp of Compliance"], errors="coerce")
        if getattr(ts.dt, "tz", None) is not None:
            ts = ts.dt.tz_localize(None)
        days = (ts.dt.normalize() - r["Date of Inspection"].dt.normalize()).dt.days.dropna()
        days = days[days >= 0]
        if len(days) >= 3:
            out.append(f"**Speed of compliance:** resolved items took {days.mean():.1f} days on average (median {days.median():.0f})")

    # Recurring issues
    if has_date and "Location" in df.columns and "Sub Head" in df.columns:
        g = df.groupby(["Location", "Sub Head"]).agg(n=("Status", "size"), insp=("Date of Inspection", "nunique"))
        rec = g[(g["insp"] >= 2) & (g["n"] >= 2)].sort_values(["insp", "n"], ascending=False)
        if len(rec):
            (loc, sub), r0 = rec.index[0], rec.iloc[0]
            out.append(f"**Recurring issue:** {sub} at {loc} was raised in {int(r0['insp'])} different inspections ({int(r0['n'])} records)")

    # Inspection depth
    if insp_df is not None and not insp_df.empty and len(insp_df) > 1 and "Deficiencies" in insp_df.columns:
        r0 = insp_df.sort_values("Deficiencies", ascending=False).iloc[0]
        when = _nm(r0["Date of Inspection"]) if "Date of Inspection" in insp_df.columns else ""
        who = f" by {r0['Inspection By']}" if "Inspection By" in insp_df.columns and r0["Inspection By"] else ""
        out.append(
            f"**Inspection depth:** {insp_df['Deficiencies'].mean():.1f} deficiencies per inspection on average; "
            f"heaviest was {when}{who} with {int(r0['Deficiencies'])}"
        )
    return out


def _charts_for(result, plan):
    hint = str(plan.get("chart") or "auto").lower()
    if hint == "none" or result.empty:
        return []
    cols = list(result.columns)
    num = [c for c in cols if _is_num(result[c])]
    specs = []

    if plan.get("group_by") and num:
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
            specs.append(dict(kind="stacked", df=d, cat=cat, val=val, color=col, title=f"{val} by {cat} and {col}"))
        return specs

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
                specs.append(dict(
                    kind="stacked", df=d[d[pick].isin(top)], cat=pick, val="Count",
                    color="Status", title=f"Records by {pick}"
                ))
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
        fig = px.bar(
            d, x=cat, y=val, color=color, barmode="stack",
            color_discrete_map=STATUS_COLORS, color_discrete_sequence=PALETTE
        )
    elif kind == "pie":
        fig = px.pie(
            d, names=cat, values=val, hole=0.45, color=cat,
            color_discrete_map=STATUS_COLORS, color_discrete_sequence=PALETTE
        )
        fig.update_traces(textinfo="label+value")
    else:
        fig = px.line(d, x=cat, y=val, markers=True, color_discrete_sequence=PALETTE)
    fig.update_layout(
        title=spec["title"], height=340, margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=-0.25, title_text="")
    )
    return fig


def _mpl_png(spec):
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
        ax.pie(
            d[val], labels=d[cat], colors=cs,
            autopct=lambda p: f"{p:.0f}%" if p >= 4 else "",
            wedgeprops=dict(width=0.45), textprops=dict(fontsize=8)
        )
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
def _to_excel(df, insp_df=None):
    buf = io.BytesIO()
    out = df.copy()
    for c in out.columns:
        if _is_dt(out[c]):
            out[c] = out[c].dt.strftime("%d-%m-%Y").fillna("")
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        out.to_excel(xw, index=False, sheet_name="Deficiencies")
        ws = xw.sheets["Deficiencies"]
        for i, c in enumerate(out.columns, 1):
            longest = max([len(str(c))] + [len(str(v)) for v in out[c].head(200)])
            ws.column_dimensions[ws.cell(1, i).column_letter].width = min(50, longest + 2)
        ws.freeze_panes = "A2"

        if insp_df is not None and not insp_df.empty and len(insp_df) < len(out):
            iout = insp_df.copy()
            for c in iout.columns:
                if _is_dt(iout[c]):
                    iout[c] = iout[c].dt.strftime("%d-%m-%Y").fillna("")
            iout.to_excel(xw, index=False, sheet_name="Inspections")
            ws2 = xw.sheets["Inspections"]
            for i, c in enumerate(iout.columns, 1):
                longest = max([len(str(c))] + [len(str(v)) for v in iout[c].head(200)])
                ws2.column_dimensions[ws2.cell(1, i).column_letter].width = min(40, longest + 2)
            ws2.freeze_panes = "A2"
    return buf.getvalue()


def _fmt_cell(v, limit=250):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    if isinstance(v, pd.Timestamp):
        return v.strftime("%d-%m-%Y")
    s = str(v)
    return s if len(s) <= limit else s[:limit - 1] + "…"


def _to_docx(turn):
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

    if turn.get("analysis"):
        doc.add_heading("Analysis", level=1)
        for s in turn["analysis"]:
            doc.add_paragraph(s.replace("**", ""), style="List Bullet")

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
        doc.add_paragraph(
            f"Showing first {MAX_ROWS_IN_WORD} of {len(tbl)} records. Download the Excel sheet for all records."
        )
    doc.add_paragraph("Auto-generated by Ask SARAL · Safety Department, Solapur Division")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Streamlit UI
# ----------------------------------------------------------------------------
def _answer(question, tables, history, hint):
    try:
        t0, ai_s = time.time(), None
        plan, mode, note = None, "ai", ""
        if _ai_available():
            try:
                ta = time.time()
                _STATE["used"] = None
                plan = _ask_plan_cached(question, tables, history, hint)
                ai_s = round(time.time() - ta, 1)
                used, order = _STATE.get("used"), _providers()
                if used and order and used != order[0]:
                    note = f"ℹ️ Primary AI limit reached; answered using {used.title()}."
            except Exception as e:
                msg = str(e)
                if _is_limit_error(msg):
                    note = "⚡ Free AI limit reached; using Basic mode (built-in rules)."
                elif isinstance(e, RuntimeError) and "API_KEY" in msg:
                    note = "⚡ AI key not configured; using Basic mode (built-in rules)."
                else:
                    note = f"⚡ AI fallback to Basic mode ({msg[:140]})."
                plan = None
        else:
            note = "⚡ AI unavailable or rate-limited; using Basic mode (built-in rules)."

        if plan is None:
            plan, mode = _rule_plan(question, tables, history[-1]["plan"] if history else None), "basic"
        if plan.get("clarification"):
            return {"q": question, "text": plan["clarification"], "note": note}

        src_df = tables.get(plan.get("table")) if plan.get("table") in tables else next(iter(tables.values()))
        if mode == "ai":
            # Deterministic safety net: designations like AEE/OP/SUR are officers, not Locations.
            plan = _enforce_officer(plan, question, src_df)
        n_last = _last_n_from_question(question)
        if n_last:
            plan["last_n_inspections"] = n_last

        raw_filtered, clean_plan = _filter_df(plan, tables)
        result = _aggregate_df(raw_filtered, clean_plan)
        title = clean_plan.get("title") or "Result"
        history.append({"q": question, "plan": clean_plan})

        if result.empty:
            date_note = ""
            src = tables.get(clean_plan.get("table")) if clean_plan.get("table") in tables else next(iter(tables.values()))
            dcols = [c for c in src.columns if _is_dt(src[c])]
            if dcols and src[dcols[0]].notna().any():
                date_note = f" The latest record in the data is dated {src[dcols[0]].max():%d-%m-%Y}."
            return {
                "q": question,
                "text": f"No records found for: {title}.{date_note} Try a longer date range or another name.",
                "explain": _explain_plan(clean_plan),
                "note": note,
            }

        insp_df = _inspection_summary(raw_filtered)
        insp_count = len(insp_df) if not insp_df.empty else None

        body = None
        if mode == "ai" and _ai_available() and str(_secret("SARAL_AI_SUMMARY") or "").strip().lower() in ("1", "true", "yes"):
            try:
                body = _ask_summary(question, title, len(raw_filtered), insp_count, result)
            except Exception:
                body = None
        if not body:
            body = _local_summary(title, result, clean_plan, raw_filtered, insp_count=insp_count)

        grouped = bool(clean_plan.get("group_by"))
        try:
            specs = _charts_for(result, clean_plan)
        except Exception:
            specs = []
        try:
            analysis = _analysis(raw_filtered, insp_df)
        except Exception:
            analysis = []

        return {
            "q": question,
            "text": body,
            "table": result,
            "insp_table": insp_df,
            "title": title,
            "grouped": grouped,
            "specs": specs,
            "note": note,
            "secs": round(time.time() - t0, 1),
            "ai_secs": ai_s,
            "explain": _explain_plan(clean_plan),
            "kpis": _kpis(raw_filtered, clean_plan, insp_count=insp_count),
            "insights": _insights(raw_filtered),
            "analysis": analysis,
            "xlsx": _to_excel(result, insp_df=insp_df if not grouped else None),
            "docx": None,
        }
    except Exception as e:
        msg = str(e)
        return {
            "q": question,
            "text": "Sorry, I could not answer that this time. Please try rephrasing in a few words.",
            "error": f"{type(e).__name__}: {msg}",
        }


def _show_turn(t, idx):
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
        if t.get("explain"):
            st.caption("🔍 Understood as: " + "  ·  ".join(t["explain"]))

        tbl = t.get("table")
        if tbl is not None:
            kp = t.get("kpis")
            if kp:
                for c, (k, v) in zip(st.columns(len(kp)), kp.items()):
                    c.metric(k, f"{v}%" if k == "Compliance %" else v)

            if t.get("analysis"):
                with st.expander("🧠 Analysis", expanded=True):
                    for s in t["analysis"]:
                        st.markdown(f"- {s}")

            specs = t.get("specs") or []
            if specs:
                try:
                    for i in range(0, len(specs), 2):
                        row = specs[i:i + 2]
                        for c, (j, sp) in zip(st.columns(len(row)), enumerate(row)):
                            with c:
                                st.plotly_chart(
                                    _plotly_fig(sp), use_container_width=True,
                                    key=f"saral_ch_{idx}_{i}_{j}"
                                )
                except ImportError:
                    st.caption("📊 Charts need the 'plotly' package (add it to requirements.txt).")
                except Exception as e:
                    st.caption(f"📊 Chart could not be drawn: {e}")

            if t.get("insights"):
                with st.expander("💡 Quick insights", expanded=False):
                    for s in t["insights"]:
                        st.markdown(f"- {s}")

            insp_tbl = t.get("insp_table")
            if insp_tbl is not None and not insp_tbl.empty and not t.get("grouped") and len(insp_tbl) < len(tbl):
                tab_insp, tab_def = st.tabs([
                    f"📋 Inspections ({len(insp_tbl)})",
                    f"📝 All Deficiencies ({len(tbl)})",
                ])
                with tab_insp:
                    st.dataframe(insp_tbl, use_container_width=True, hide_index=True)
                with tab_def:
                    st.dataframe(tbl.head(MAX_ROWS_SHOWN), use_container_width=True, hide_index=True)
                    if len(tbl) > MAX_ROWS_SHOWN:
                        st.caption(f"Showing first {MAX_ROWS_SHOWN} rows. Download the Excel sheet for all rows.")
            else:
                st.caption(f"{t.get('title', 'Result')}  •  {len(tbl)} records")
                st.dataframe(tbl.head(MAX_ROWS_SHOWN), use_container_width=True, hide_index=True)
                if len(tbl) > MAX_ROWS_SHOWN:
                    st.caption(f"Showing first {MAX_ROWS_SHOWN} rows. Download the sheet to get all rows.")

            d1, d2 = st.columns(2)
            stamp = f"SARAL_{dt.date.today():%Y%m%d}_{idx}"
            d1.download_button(
                "⬇️ Excel sheet", data=t["xlsx"], file_name=f"{stamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"saral_xl_{idx}", use_container_width=True
            )
            if t.get("docx"):
                d2.download_button(
                    "📄 Word report (with charts)", data=t["docx"], file_name=f"{stamp}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"saral_dx_{idx}", use_container_width=True
                )
            else:
                if t.get("docx_failed"):
                    d2.caption("📄 Word report needs 'python-docx' in requirements.txt")
                else:
                    d2.button(
                        "📄 Prepare Word report", key=f"saral_pw_{idx}", on_click=_prep_docx,
                        args=(idx,), use_container_width=True
                    )


def _prep_docx(idx):
    t = st.session_state["saral_turns"][idx]
    try:
        t["docx"] = _to_docx(t)
    except Exception:
        t["docx"] = None
    if not t["docx"]:
        t["docx_failed"] = True


def _show_turn_compact(t, idx):
    st.markdown(f"**🧑 {t['q']}**")
    with st.container(border=True):
        st.markdown(t["text"])
        if t.get("xlsx"):
            st.download_button(
                "⬇️ Excel sheet", data=t["xlsx"],
                file_name=f"SARAL_{dt.date.today():%Y%m%d}_{idx}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"saral_xl_{idx}"
            )


def _clear_chat():
    st.session_state["saral_turns"] = []
    st.session_state["saral_hist"] = []


def render_saral_chatbot(dataframes: dict, title: str = "Ask SARAL",
                         domain_hint: str = SARAL_HINT, hidden_columns=None):
    st.subheader(f"🤖 {title}")
    st.caption(
        "Type your question in simple words (English / हिंदी / Hinglish). "
        "You get the answer, analysis, charts, an Excel sheet and a Word report."
    )

    tables = _prepare_cached(dataframes, hidden_columns)
    ss = st.session_state
    ss.setdefault("saral_turns", [])
    ss.setdefault("saral_hist", [])

    question = None
    with st.form("saral_chat_form", clear_on_submit=True):
        typed = st.text_input(
            "Your question",
            placeholder="e.g. Sr DOM all deficiencies resolved from August to October"
        )
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

    n = len(ss["saral_turns"])
    for i in range(n - 1, -1, -1):
        if i >= n - 2:
            _show_turn(ss["saral_turns"][i], i)
        else:
            _show_turn_compact(ss["saral_turns"][i], i)

    if n:
        st.button("🗑️ Clear chat", key="saral_clear", on_click=_clear_chat)
