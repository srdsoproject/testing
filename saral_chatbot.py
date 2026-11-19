"""
saral_chatbot.py  -  "Ask SARAL": plain-language AI assistant for the S.A.R.A.L Streamlit app.
"""

import difflib
import io
import json
import re
import time
import datetime as dt

import pandas as pd
import streamlit as st

DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_ROWS_SHOWN = 500
MAX_ROWS_TO_AI = 40
MAX_ROWS_IN_WORD = 100
MAX_CATEGORY_VALUES = 150

INTERNAL_COLUMNS = ["_sheet_row", "_original_sheet_index", "_status_plain"]
STATUS_COLORS = {"Resolved": "#2e9e5b", "Pending": "#e0623b", "No Response": "#8a94a6"}
PALETTE = ["#2f6fb5", "#e0a030", "#7a5fb5", "#3aa5a5", "#c24d86", "#6b8e23"]
ROW_COLS_DOC = [
    "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
    "Deficiencies Noted", "Inspection By", "Action By", "Feedback", "Status"
]

_is_dt = pd.api.types.is_datetime64_any_dtype
_is_num = pd.api.types.is_numeric_dtype

# ----------------------------------------------------------------------------
# S.A.R.A.L specific knowledge
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
  COMMERCIAL, C&W, PERSONNEL, SECURITY, FINANCE, MEDICAL, STORE, GSU.
- "Sub Head": category inside a department.
- "Deficiencies Noted": the text of the deficiency.
- "Inspection By": the officer who inspected (e.g. Sr.DOM, DRM/SUR, ADRM).
- "Action By": the officer RESPONSIBLE for fixing it (e.g. Sr.DOM, Sr.DEN/S, Sr.DSTE). Cells may contain multiple
  comma- or slash-separated officers (e.g. "Sr.DEN/S, Sr.DSTE").
- "Feedback": compliance reply given by the department. "User Feedback/Remark": extra remark.
- "Timestamp of Compliance": when the compliance feedback was given.
- "Status": Resolved, Pending or No Response (No Response = no feedback given yet).

Interpretation rules:
- Department words map to "Head": Engg/Engineering/Track -> ENGINEERING, S&T/Signal/Telecom -> SIGNAL & TELECOM,
  Operating/Optg -> OPTG, Mech -> MECHANICAL, Elect TRD -> ELECT/TRD, Elect G -> ELECT/G, Elect TRO -> ELECT/TRO.
- Officer designations (Sr DOM, Sr DEN/S, DRM, Sr DSTE, ADEN...) in a question about deficiencies, pending work,
  or compliance mean "Action By", unless the user says "inspected by" / "inspection done by" (then use "Inspection By").
  Use op "contains" for "Action By" and "Inspection By" because cells can list multiple officers.
- "resolved / complied / closed / attended" -> Status = Resolved (op eq).
- IMPORTANT: in SARAL "pending / open / not done / outstanding" means NOT YET RESOLVED, i.e. Status in
  ["Pending", "No Response"] (use op "in" with BOTH values), because a deficiency with no feedback yet is still pending.
  Only if the user says "pending with feedback / feedback given but pending" use Status eq Pending.
- ONLY when the user says "no reply / not responded / no feedback / no response" use Status = No Response (op eq).
- Date ranges refer to "Date of Inspection". Only if the user says "complied/resolved ON or DURING <dates>"
  use "Timestamp of Compliance" instead.
- "Deficiencies Noted" and "Feedback" are long text: for "related to <word>" questions use op "contains".
- For "all deficiencies" style questions return the full rows with these columns:
  Date of Inspection, Type of Inspection, Location, Head, Sub Head, Deficiencies Noted, Inspection By, Action By,
  Feedback, Status.
- "Analysis" of a department: group_by ["Sub Head", "Status"] with count, after filtering Head and dates.
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
  "chart": "auto",
  "title": "<short title for the result>",
  "clarification": null
}}

Rules:
- op is one of: eq, ne, in, contains, gt, gte, lt, lte, between, isnull, notnull.
- Dates are ISO strings YYYY-MM-DD. "between" takes [from, to] inclusive.
  Resolve "last 5 days", "this month", "August to October" into exact dates using today's date.
  If no year is given for a month range, use the most recent such period that is not in the future.
- Use values exactly as they appear in the sample values when possible (e.g. "Sr DOM" -> "Sr.DOM").
- Use op "contains" for "Action By" and "Inspection By" so multi-officer entries match accurately.
- Use op "eq" or "in" for exact codes like "Location" (e.g. "SUR", "LC-40") and "Head".
- For "analysis"/"summary"/"department wise" questions use group_by + aggregations.
- For "show/list/give me all" questions leave group_by and aggregations empty so full rows come back.
- Use ONLY the table and column names listed above. Never invent columns.
- Only inherit filters from earlier conversation if the current message is clearly a follow-up refinement
  (e.g. "now only for Solapur", "what about pending ones?", "same for last month"). If the user asks a new
  standalone question, DO NOT carry over old filters.
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
FOLLOWUPS: <question 1> | <question 2> | <question 3>"""


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
    """Parse ISO YYYY-MM-DD and DD-MM-YYYY dates without dropping valid ISO rows as NaT."""
    s = series.astype(str).str.strip()
    iso_mask = s.str.match(r"^\d{4}-\d{1,2}-\d{1,2}")
    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    if iso_mask.any():
        out[iso_mask] = pd.to_datetime(s[iso_mask], errors="coerce", format="mixed")
    if (~iso_mask).any():
        out[~iso_mask] = pd.to_datetime(s[~iso_mask], errors="coerce", dayfirst=True, format="mixed")
    return out


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
            elif d[c].dtype == object and re.search(r"date|time", c, re.I):
                conv = _parse_dates_safely(d[c])
                if conv.notna().mean() > 0.5:
                    d[c] = conv
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
                    tokens = sorted({
                        tok.strip() for v in vals
                        for tok in re.split(r"[,;&]+", v) if tok.strip()
                    })
                    lines.append(f'  - "{c}" (text, individual values): {tokens[:MAX_CATEGORY_VALUES]}')
                elif len(vals) <= MAX_CATEGORY_VALUES:
                    lines.append(f'  - "{c}" (text) values: {list(vals)}')
                else:
                    lines.append(f'  - "{c}" (text, {len(vals)} distinct) e.g. {list(vals[:15])}')
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# AI calls (Gemini by default, Groq / Claude fallback)
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


def _gem_generate(client, types, cfg, model, contents, config):
    if _STATE.get("gem_think", True):
        try:
            c2 = dict(cfg, thinking_config=types.ThinkingConfig(thinking_budget=0))
            return client.models.generate_content(
                model=model, contents=contents, config=types.GenerateContentConfig(**c2)
            )
        except Exception as e:
            m = str(e)
            if _is_limit_error(m) or any(x in m for x in ("404", "NOT_FOUND", "401", "403", "PERMISSION", "API key")):
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
        resp = _gem_generate(
            client, types, cfg,
            model=_secret("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(**cfg),
        )
        return (resp.text or "").strip()

    if provider == "groq":
        key = _secret("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is missing in Secrets")
        import requests
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": _secret("GROQ_MODEL") or DEFAULT_GROQ_MODEL,
                "temperature": 0.0,
                "max_tokens": max(max_tokens, 1500),
                "messages": [{"role": "system", "content": system}] + messages,
            },
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Groq {r.status_code}: {r.text[:300]}")
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
                _STATE["off_" + p] = time.time() + 900
    if tried == 0 or limited == tried:
        raise RuntimeError("429 RESOURCE_EXHAUSTED: all AI free limits are used up")
    raise last


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
    msgs.append({"role": "user", "content": question})
    text = _llm(system, msgs, 1200, json_mode=True)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Could not understand the question. Please rephrase.")
    return json.loads(m.group(0))


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
    content = (
        f"Question: {question}\nResult title: {title}\n"
        f"Total rows in result: {total}\nFirst rows (CSV):\n{sample}"
    )
    return _split_followups(_llm(SUMMARY_SYSTEM, [{"role": "user", "content": content}], 500))


# ----------------------------------------------------------------------------
# Safe plan executor
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


def _token_boundary_mask(series, value):
    """Match an officer/code token cleanly inside cells like 'Sr.DEN/S, Sr.DSTE' without matching 'LC-4' to 'LC-40'."""
    nv = _norm(value)
    if not nv:
        return pd.Series(False, index=series.index)

    def _matches(cell):
        parts = [_norm(p) for p in re.split(r"[,;&]+", str(cell)) if _norm(p)]
        if nv in parts:
            return True
        # Allow prefix/suffix boundary match on non-digit boundaries (e.g. 'dens' inside 'srdens', 'sur' inside 'surdd')
        for p in parts:
            idx = p.find(nv)
            if idx != -1:
                before = p[idx - 1] if idx > 0 else ""
                after = p[idx + len(nv)] if idx + len(nv) < len(p) else ""
                # Prevent LC-4 matching LC-40 or DOM matching ADOM
                if nv[-1].isdigit() and after.isdigit():
                    continue
                if nv == "dom" and before == "a":
                    continue
                return True
        return False

    return series.map(_matches)


def _text_mask(series, value, mode="exact"):
    """
    mode='exact': strict normalized equality (never falls back to wrong stations/codes when 0 rows match).
    mode='token': boundary-aware token match (ideal for Action By / Inspection By).
    mode='contains': substring match (for free-text columns like Deficiencies Noted / Feedback).
    """
    ns = series.astype(str).map(_norm)
    nv = _norm(value)
    if not nv:
        return ns == ""
    if mode == "exact":
        return ns == nv
    if mode == "token":
        exact = ns == nv
        return exact if exact.any() else _token_boundary_mask(series, value)
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


def _filter_df(plan, tables):
    name = plan.get("table")
    if name not in tables:
        name = next(iter(tables))
    df = tables[name]
    filters = plan.get("filters") or []
    if isinstance(filters, dict):
        filters = [{"column": k, "op": "eq", "value": v} for k, v in filters.items()]
    for f in filters:
        df = _apply_filter(df, _fix_status_filter(f))
    return df


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
# Basic mode (built-in rules fallback)
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

_BASIC_HELP = (
    "I can answer questions like:\n\n"
    "- Sr DOM all deficiencies resolved from August to October\n"
    "- Which department has most pending deficiencies this month\n"
    "- Engg analysis of last 7 days\n\n"
    "Please type your question with a department or officer, a status (pending / resolved) "
    "and a period (last 7 days, this month, August to October)."
)


def _prepare_cached(dfs, hidden):
    try:
        key = tuple(
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

    # Avoid treating English modal "may" ("that may be pending") as month May
    ql_date = re.sub(r"\bmay\s+(?:be|have|not|also)\b", " ", ql)
    month_rx = r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")(?:\s+(20\d{2}))?\b"
    found = re.findall(month_rx, ql_date)
    if found:
        m1, y1_str = _MONTHS[found[0][0]], found[0][1]
        m2, y2_str = _MONTHS[found[-1][0]], found[-1][1]
        y1 = int(y1_str) if y1_str else (today.year if m1 <= today.month else today.year - 1)
        y2 = int(y2_str) if y2_str else (y1 if m2 >= m1 else y1 + 1)
        start, end = dt.date(y1, m1, 1), min(_month_end(y2, m2), today)
        if start <= end:
            return start, end
    return None


def _find_officer(ql, df, col):
    toks = [_norm(t) for t in ql.split() if _norm(t)]
    cand = (
        set(toks)
        | {a + b for a, b in zip(toks, toks[1:])}
        | {a + b + c for a, b, c in zip(toks, toks[1:], toks[2:])}
        | {a + b + c + d for a, b, c, d in zip(toks, toks[1:], toks[2:], toks[3:])}
    )
    all_vals = {
        tok.strip()
        for v in df[col].dropna().astype(str).unique()
        for tok in re.split(r"[,;&]+", v) if tok.strip()
    }
    best_len, hits = 0, []
    for v in all_vals:
        n = _norm(v)
        variants = {n: v}
        if n.startswith("sr") and len(n) > 4:
            variants[n[2:]] = v
        for var, val in variants.items():
            if len(var) >= 3 and var in cand:
                if len(var) > best_len:
                    best_len, hits = len(var), [val]
                elif len(var) == best_len and val not in hits:
                    hits.append(val)
    return hits


def _rule_plan(question, tables, prev=None):
    df = next(iter(tables.values()))
    tname = next(iter(tables))
    ql = " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9&/ ]+", " ", question.lower())) + " "
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
        for target, words in _DEPT_WORDS.items():
            if any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", ql) for w in words):
                real = [h for h in heads if _norm(target) == _norm(h)]
                found.append(real[0] if real else target)
        if found:
            dept_filtered = True
            filters.append({"column": "Head", "op": "in", "value": found})
            parts.append(" / ".join(found))

    ocol = "Inspection By" if re.search(r"insp(?:ected|ection)\s+by", ql) and "Inspection By" in df.columns else "Action By"
    if ocol in df.columns:
        offs = _find_officer(ql, df, ocol)
        if offs:
            filters.append(
                {"column": ocol, "op": "in", "value": offs}
                if len(offs) > 1
                else {"column": ocol, "op": "contains", "value": offs[0]}
            )
            parts.append(" / ".join(offs))

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
    wise = re.search(r"\bwise\b|\banalysis\b|\banalyse\b|\banalyze\b|\bsummary\b|\breport\b", ql)
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
    if plan.get("group_by"):
        out.append("counted by " + " and ".join(plan["group_by"]))
    return out


def _nm(x):
    return x.strftime("%d-%m-%Y") if isinstance(x, pd.Timestamp) else str(x)


def _local_summary(title, result, plan, raw_filtered):
    num = [c for c in result.columns if _is_num(result[c])]
    k = _kpis(raw_filtered, plan)
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
                lines.append("Next: " + ", ".join(f"{_nm(idx)} ({int(v)})" for idx, v in s.iloc[1:4].items()) + ".")
        if "Resolved" in k:
            comp_txt = f" Compliance **{k['Compliance %']}%**." if "Compliance %" in k else ""
            lines.append(
                f"Resolved **{k['Resolved']}**, not yet resolved **{k['Pending'] + k['No Response']}** "
                f"(pending {k['Pending']}, no response {k['No Response']}).{comp_txt}"
            )
        return "\n\n".join(lines)

    lines = [f"**{len(result)} records** found: {title}."]
    if "Resolved" in k:
        comp_txt = f" Compliance **{k['Compliance %']}%**." if "Compliance %" in k else ""
        lines.append(
            f"Resolved **{k['Resolved']}**, not yet resolved **{k['Pending'] + k['No Response']}** "
            f"(feedback pending {k['Pending']}, no feedback {k['No Response']}).{comp_txt}"
        )
    return "\n\n".join(lines)


def _local_followups(plan):
    has_status = any(f.get("column") == "Status" for f in plan.get("filters") or [])
    return [
        "Only resolved ones" if has_status else "Only pending ones",
        "Department wise analysis of this",
        "Same for last 30 days",
    ]


# ----------------------------------------------------------------------------
# Insights: KPIs, auto charts, quick findings
# ----------------------------------------------------------------------------
def _kpis(df, plan=None):
    total = len(df)
    if "Status" not in df.columns:
        return {"Total records": total}
    vc = df["Status"].value_counts()
    res = int(vc.get("Resolved", 0))
    pend = int(vc.get("Pending", 0))
    no_resp = int(vc.get("No Response", 0))
    out = {"Total": total, "Resolved": res, "Pending": pend, "No Response": no_resp}

    # Only show Compliance % when Status wasn't restricted exclusively to non-resolved items
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
    doc.add_paragraph(turn["text"])

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
                    note = f"⚡ AI fallback to Basic mode ({type(e).__name__}: {msg[:80]})."
                plan = None
        else:
            note = "⚡ AI unavailable or rate-limited; using Basic mode (built-in rules)."

        if plan is None:
            plan, mode = _rule_plan(question, tables, history[-1]["plan"] if history else None), "basic"
        if plan.get("clarification"):
            return {"q": question, "text": plan["clarification"], "note": note}

        raw_filtered = _filter_df(plan, tables)
        result = _aggregate_df(raw_filtered, plan)
        title = plan.get("title") or "Result"
        history.append({"q": question, "plan": plan})

        if result.empty:
            date_note = ""
            src = tables.get(plan.get("table")) if plan.get("table") in tables else next(iter(tables.values()))
            dcols = [c for c in src.columns if _is_dt(src[c])]
            if dcols and src[dcols[0]].notna().any():
                date_note = f" The latest record in the data is dated {src[dcols[0]].max():%d-%m-%Y}."
            return {
                "q": question,
                "text": f"No records found for: {title}.{date_note} Try a longer date range or another name.",
                "explain": _explain_plan(plan),
                "note": note,
            }

        body, followups = None, []
        if mode == "ai" and _ai_available() and str(_secret("SARAL_AI_SUMMARY") or "").strip().lower() in ("1", "true", "yes"):
            try:
                body, followups = _ask_summary(question, title, len(result), result)
            except Exception:
                body, followups = None, []
        if not body:
            body = _local_summary(title, result, plan, raw_filtered)
        if not followups:
            followups = _local_followups(plan)

        grouped = bool(plan.get("group_by"))
        try:
            specs = _charts_for(result, plan)
        except Exception:
            specs = []

        return {
            "q": question,
            "text": body,
            "table": result,
            "title": title,
            "followups": followups,
            "grouped": grouped,
            "specs": specs,
            "note": note,
            "secs": round(time.time() - t0, 1),
            "ai_secs": ai_s,
            "explain": _explain_plan(plan),
            "kpis": _kpis(raw_filtered, plan),
            "insights": _insights(raw_filtered),
            "xlsx": _to_excel(result),
            "docx": None,
        }
    except Exception as e:
        msg = str(e)
        return {
            "q": question,
            "text": "Sorry, I could not answer that this time. Please try rephrasing in a few words.",
            "error": f"{type(e).__name__}: {msg}",
        }


def _queue_question(q):
    st.session_state["saral_queued"] = q


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
        if t.get("explain"):
            st.caption("🔍 Understood as: " + "  ·  ".join(t["explain"]))

        tbl = t.get("table")
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
                                st.plotly_chart(
                                    _plotly_fig(sp), use_container_width=True,
                                    key=f"saral_ch_{idx}_{i}_{j}"
                                )
                except ImportError:
                    st.caption("📊 Charts need the 'plotly' package (add it to requirements.txt).")
                except Exception as e:
                    st.caption(f"📊 Chart could not be drawn: {e}")

            if t.get("insights"):
                with st.expander("💡 Quick insights", expanded=True):
                    for s in t["insights"]:
                        st.markdown(f"- {s}")

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

        if newest and t.get("followups"):
            st.markdown("**Ask next:**")
            for j, f in enumerate(t["followups"]):
                st.button(
                    f, key=f"saral_fu_{idx}_{j}", on_click=_queue_question, args=(f,),
                    use_container_width=True
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
        "You get the answer, charts, an Excel sheet and a Word report."
    )

    tables = _prepare_cached(dataframes, hidden_columns)
    ss = st.session_state
    ss.setdefault("saral_turns", [])
    ss.setdefault("saral_hist", [])

    question = ss.pop("saral_queued", None)
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
            _show_turn(ss["saral_turns"][i], i, newest=(i == n - 1))
        else:
            _show_turn_compact(ss["saral_turns"][i], i)

    if n:
        st.button("🗑️ Clear chat", key="saral_clear", on_click=_clear_chat)
