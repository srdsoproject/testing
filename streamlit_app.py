#!/usr/bin/env python3
"""
Streamlit UI – Solapur Division Safety Deficiencies
===================================================
Select department(s), date range, and generate:
  • Detailed Analysis  (combinations logic)  → image + Sub-Head Excel
  • General Analysis   (master_code logic)   → image + Pending Excel

Run:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import io
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Import unified dashboard module (same folder or on PYTHONPATH)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Department catalogue
# key → (label, detailed_key, general_key)
# ---------------------------------------------------------------------------
DEPARTMENTS: Dict[str, Tuple[str, Optional[str], Optional[str]]] = {
    "elect_g": ("ELECT / G", "elect_g", "elect_g"),
    "elect_trd": ("ELECT / TRD", "elect_trd", "elect_trd"),
    "elect_tro": ("ELECT / TRO", "elect_tro", "elect_tro"),
    "engg": ("Engineering – Sr.DEN/C", "engg", "engg"),
    "engg_s": ("Engineering – Sr.DEN/S", "engg_s", "engg_s"),
    "engg_track": ("Engineering – DEN/TRACK", "engg_track", "engg_track"),
    "engg_full": ("Engineering – Full", "engg_full", "engg_full"),
    "operating": ("Operating (OPTG)", "operating", "operating"),
    "commercial": ("Commercial", "commercial", "commercial"),
    "mechanical": ("Mechanical", "mechanical", "mechanical"),
    "snt": ("S&T / Signal & Telecom", "snt", "snt"),
}

# Expected output filenames from detailed generators (may vary slightly)
DETAILED_OUT_HINTS = {
    "elect_g": "ELECT_G",
    "engg": "ENGINEERING",
    "engg_c": "ENGINEERING",
    "engg_s": "ENGINEERING",
    "engg_track": "ENGINEERING",
    "engg_full": "ENGINEERING",
    "elect_trd": "ELECT_TRD",
    "elect_tro": "ELECT_TRO",
    "tro": "ELECT_TRO",
    "snt": "SNT",
    "s_and_t": "SNT",
    "mechanical": "MECHANICAL",
    "operating": "OPERATING",
    "commercial": "COMMERCIAL",
}


# =============================================================================
# Helpers
# =============================================================================

def resolve_paths() -> Tuple[Path, Path, Path, Path]:
    """Prefer paths from unified module; fall back to script directory."""
    base = Path(rs.BASE_DIR)
    excel = Path(rs.EXCEL_FILE)
    logo = Path(rs.LOGO_FILE)
    out = Path(rs.OUTPUT_FOLDER)
    # If Windows path does not exist on this machine, use local project folder
    script_dir = Path(__file__).resolve().parent
    if not excel.exists():
        local_excel = script_dir / "DATA.xlsx"
        if local_excel.exists():
            excel = local_excel
            base = script_dir
            out = script_dir / "DEPARTMENT_DASHBOARDS"
            out.mkdir(parents=True, exist_ok=True)
            rs.EXCEL_FILE = excel
            rs.BASE_DIR = base
            rs.OUTPUT_FOLDER = out
            rs.OUTPUT_FOLDER_STR = str(out)
            # logo / train optional for PIL general; detailed needs them
            for name, attr in [
                ("indian_railways_logo.png", "LOGO_FILE"),
                ("train.png", "TRAIN_FILE"),
            ]:
                p = script_dir / name
                if p.exists():
                    setattr(rs, attr, str(p))
    return base, excel, logo, out


def load_raw_excel(excel: Path) -> pd.DataFrame:
    """Load first usable sheet (same idea as general load_data)."""
    xls = pd.ExcelFile(excel)
    preferred_cols = [
        "Date of Inspection", "Head", "Sub Head", "Status",
        "Location", "Deficiencies Noted", "Action By", "Action by",
    ]
    best = None
    best_score = -1
    for sheet in xls.sheet_names:
        try:
            tmp = pd.read_excel(excel, sheet_name=sheet)
            tmp.columns = (
                tmp.columns.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
            )
            score = sum(1 for c in preferred_cols if c in tmp.columns)
            if score > best_score:
                best_score = score
                best = tmp
        except Exception:
            continue
    if best is None:
        raise ValueError("Could not read any sheet from Excel.")
    return best


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    # Unify Action By
    if "Action by" in df.columns and "Action By" not in df.columns:
        df = df.rename(columns={"Action by": "Action By"})
    if "Date of Inspection" in df.columns:
        df["Date of Inspection"] = pd.to_datetime(
            df["Date of Inspection"], errors="coerce", dayfirst=True
        )
    return df


def filter_by_date(
    df: pd.DataFrame,
    start: Optional[date],
    end: Optional[date],
) -> pd.DataFrame:
    if "Date of Inspection" not in df.columns:
        return df
    out = df.copy()
    if start is not None:
        out = out[out["Date of Inspection"] >= pd.Timestamp(start)]
    if end is not None:
        out = out[out["Date of Inspection"] <= pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
    return out


def apply_report_period(start: date, end: date) -> None:
    """Update REPORT_MONTHS / YEAR / titles in unified module for this run."""
    months = sorted(set(
        pd.date_range(start=start, end=end, freq="D").month.tolist()
    ))
    if not months:
        months = [start.month]
    years = sorted(set(
        pd.date_range(start=start, end=end, freq="D").year.tolist()
    ))
    year = years[-1] if years else start.year

    rs.REPORT_MONTHS = months
    rs.REPORT_YEAR = year
    # Rebuild month labels for this year
    names = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December",
    }
    rs.MONTH_LABELS = {m: f"{names[m]}-{year}" for m in range(1, 13)}
    rs.PERIOD_TITLE = ""
    rs.SECTION_PERIOD = ""
    rs.DATA_AS_ON = end.strftime("%d %B %Y").upper()
    # General PIL period text
    rs.PERIOD_TEXT = (
        f"PERFORMANCE PERIOD: {start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')}"
    )


def write_temp_excel(df: pd.DataFrame) -> Path:
    """Write filtered frame to a temp xlsx used by generators."""
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    path = Path(tmp.name)
    df.to_excel(path, index=False)
    return path


def head_filter_for_dept(df: pd.DataFrame, dept_key: str) -> pd.DataFrame:
    """Rough head filter for Excel exports (not used to change generator logic)."""
    if "Head" not in df.columns:
        return df
    h = df["Head"].fillna("").astype(str).str.upper().str.replace(r"[\s.]", "", regex=True)
    mapping = {
        "elect_g": ["ELECT/G", "ELECTG", "ELECT-G"],
        "elect_trd": ["ELECT/TRD", "ELECTTRD", "ELECT-TRD"],
        "elect_tro": ["ELECT/TRO", "ELECTTRO", "ELECT-TRO", "TRACTIONOPERATION"],
        "engg": ["ENGINEERING"],
        "engg_s": ["ENGINEERING"],
        "engg_track": ["ENGINEERING"],
        "engg_full": ["ENGINEERING"],
        "operating": ["OPTG", "OPERATING"],
        "commercial": ["COMMERCIAL"],
        "mechanical": ["MECHANICAL"],
        "snt": ["SIGNAL", "S&T", "SNT", "TELECOM", "TELECOMMUNICATION"],
    }
    keys = mapping.get(dept_key, [])
    if not keys:
        return df
    mask = False
    for k in keys:
        k2 = k.upper().replace(" ", "").replace(".", "")
        mask = mask | h.str.contains(k2.replace("/", ""), regex=False, na=False) | (h == k2)
        # also allow slash forms
        mask = mask | h.str.contains(k.upper().replace(" ", ""), regex=False, na=False)
    # Engineering DEN filter for Action By when relevant
    sub = df[mask].copy() if hasattr(mask, "__len__") else df
    if dept_key in ("engg", "engg_s", "engg_track") and "Action By" in sub.columns:
        den = {
            "engg": "SR.DEN/C",
            "engg_s": "SR.DEN/S",
            "engg_track": "DEN/TRACK",
        }[dept_key]
        ab = sub["Action By"].fillna("").astype(str).str.upper().str.replace(" ", "", regex=False)
        sub = sub[ab.str.replace("\\", "/", regex=False) == den.replace("\\", "/")]
    return sub


def classify_status_series(s: pd.Series) -> pd.Series:
    return s.apply(rs.classify_status)


def _original_columns(df: pd.DataFrame) -> List[str]:
    """Prefer original source columns; drop helper columns we may have added."""
    drop = {"STATUS_GROUP", "Month", "Year", "Date", "Location_Clean",
            "Deficiency_Clean", "Status_Clean", "ACTION_BY_NORMALIZED",
            "Location_Norm", "ADSTE", "ELECT_G", "Classification_Method",
            "JURISDICTION", "Lobby/Running Room", "Lobby Keyword",
            "Running Room Keyword"}
    cols = [c for c in df.columns if c not in drop]
    return cols if cols else list(df.columns)


def _safe_sheet_name(name: str, used: set) -> str:
    """Excel sheet name max 31 chars, unique."""
    base = str(name).strip() or "Sheet"
    base = "".join(ch if ch not in r"[]:*?/\\" else "_" for ch in base)
    base = base[:28] if len(base) > 28 else base
    candidate = base
    i = 2
    while candidate in used or not candidate:
        suffix = f"_{i}"
        candidate = (base[: 31 - len(suffix)] + suffix)
        i += 1
    used.add(candidate)
    return candidate


def build_subhead_package(df: pd.DataFrame, dept_key: str) -> dict:
    """
    Returns dict:
      summary_xlsx  – SubHead_Summary + SubHead_By_Month only (no all-rows dump)
      per_subhead   – list of {name, bytes} one Excel per Sub Head (original cols)
      full_xlsx     – all department records, original column format
    """
    empty = {
        "summary_xlsx": None,
        "per_subhead": [],
        "full_xlsx": None,
    }
    work = head_filter_for_dept(df, dept_key)
    if work.empty or "Sub Head" not in work.columns:
        buf = io.BytesIO()
        pd.DataFrame({"Message": ["No records for this department / date range"]}).to_excel(
            buf, index=False
        )
        empty["summary_xlsx"] = buf.getvalue()
        empty["full_xlsx"] = buf.getvalue()
        return empty

    work = work.copy()
    work["Sub Head"] = work["Sub Head"].fillna("").astype(str).str.strip()
    work = work[work["Sub Head"] != ""].copy()
    if "Date of Inspection" in work.columns:
        work["Month"] = pd.to_datetime(work["Date of Inspection"], errors="coerce").dt.month
    if "Status" in work.columns:
        work["STATUS_GROUP"] = classify_status_series(work["Status"])
    else:
        work["STATUS_GROUP"] = "Pending"

    orig_cols = _original_columns(work)

    # --- Summary only (no All_Records sheet) ---
    summary = (
        work.groupby("Sub Head")
        .agg(
            Total=("Sub Head", "size"),
            Resolved=("STATUS_GROUP", lambda x: (x == "Resolved").sum()),
            Pending=("STATUS_GROUP", lambda x: (x == "Pending").sum()),
            No_Response=("STATUS_GROUP", lambda x: (x == "No Response").sum()),
        )
        .reset_index()
        .sort_values("Total", ascending=False)
    )
    if len(summary):
        summary["% Resolved"] = (summary["Resolved"] / summary["Total"] * 100).round(2)

    month_sheet = None
    if "Month" in work.columns:
        month_sheet = (
            work.groupby(["Sub Head", "Month"]).size().unstack(fill_value=0).reset_index()
        )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="SubHead_Summary", index=False)
        if month_sheet is not None:
            month_sheet.to_excel(writer, sheet_name="SubHead_By_Month", index=False)
    summary_bytes = buf.getvalue()

    # --- One Excel per Sub Head (original columns only) ---
    per_subhead = []
    for sh in summary["Sub Head"].tolist():
        part = work[work["Sub Head"] == sh][orig_cols].copy()
        b = io.BytesIO()
        part.to_excel(b, index=False, sheet_name="Records")
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(sh))[:40]
        per_subhead.append({"name": str(sh), "file": f"{safe}_Records.xlsx", "bytes": b.getvalue()})

    # --- Full department records (original columns) ---
    full_buf = io.BytesIO()
    work[orig_cols].to_excel(full_buf, index=False, sheet_name="Full_Records")
    full_bytes = full_buf.getvalue()

    # Also one workbook with each sub-head as its own sheet + Full at end
    multi = io.BytesIO()
    used = set()
    with pd.ExcelWriter(multi, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="SubHead_Summary", index=False)
        used.add("SubHead_Summary")
        if month_sheet is not None:
            month_sheet.to_excel(writer, sheet_name="SubHead_By_Month", index=False)
            used.add("SubHead_By_Month")
        for sh in summary["Sub Head"].tolist():
            part = work[work["Sub Head"] == sh][orig_cols]
            sname = _safe_sheet_name(str(sh), used)
            part.to_excel(writer, sheet_name=sname, index=False)
        work[orig_cols].to_excel(writer, sheet_name=_safe_sheet_name("FULL_RECORDS", used), index=False)
    multi_bytes = multi.getvalue()

    return {
        "summary_xlsx": summary_bytes,
        "per_subhead": per_subhead,
        "full_xlsx": full_bytes,
        "combined_xlsx": multi_bytes,  # summary + one sheet per sub-head + full
    }


def build_pending_excel(df: pd.DataFrame, dept_key: str) -> bytes:
    """Pending + No Response records in ORIGINAL Excel column format."""
    work = head_filter_for_dept(df, dept_key)
    if work.empty:
        buf = io.BytesIO()
        pd.DataFrame({"Message": ["No records for this department / date range"]}).to_excel(
            buf, index=False
        )
        return buf.getvalue()

    work = work.copy()
    if "Status" in work.columns:
        work["STATUS_GROUP"] = classify_status_series(work["Status"])
    else:
        work["STATUS_GROUP"] = "Pending"

    pending = work[work["STATUS_GROUP"].isin(["Pending", "No Response"])].copy()
    orig_cols = _original_columns(pending)
    out = pending[orig_cols] if len(pending) else pd.DataFrame(columns=orig_cols)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        out.to_excel(writer, sheet_name="Pending_Records", index=False)
        # light summary only on 2nd sheet
        if "STATUS_GROUP" in pending.columns and len(pending):
            summary = pending.groupby("STATUS_GROUP").size().reset_index(name="Count")
            summary.to_excel(writer, sheet_name="Summary", index=False)
    return buf.getvalue()


def find_latest_image(out_dir: Path, hint: str, after_ts: float) -> Optional[Path]:
    """Find newest PNG in output folder matching hint, created after after_ts."""
    if not out_dir.exists():
        return None
    candidates = []
    for p in out_dir.glob("*.png"):
        try:
            if p.stat().st_mtime >= after_ts - 2:
                if hint.upper() in p.name.upper() or True:
                    candidates.append(p)
        except OSError:
            continue
    if not candidates:
        # fallback: any matching hint
        candidates = [p for p in out_dir.glob("*.png") if hint.upper() in p.name.upper()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def general_output_name(dept_key: str) -> str:
    """Expected general PNG name from master_code naming."""
    head_map = {
        "elect_g": "ELECT_G_Analysis.png",
        "elect_trd": "ELECT_TRD_Analysis.png",
        "elect_tro": "ELECT_TRO_Analysis.png",
        "engg": "ENGG_Sr.DEN_C_Analysis.png",
        "engg_s": "ENGG_Sr.DEN_S_Analysis.png",
        "engg_track": "ENGG_DEN_TRACK_Analysis.png",
        "engg_full": "ENGG_General_Analysis.png",
        "operating": "OPTG_Analysis.png",
        "commercial": "COMMERCIAL_Analysis.png",
        "mechanical": "MECHANICAL_Analysis.png",
        "snt": "SIGNAL_AND_TELECOM_Analysis.png",
    }
    return head_map.get(dept_key, f"{dept_key}_Analysis.png")


# =============================================================================
# Streamlit page
# =============================================================================


st.markdown(
    """
    <style>
    .main-title { font-size: 1.8rem; font-weight: 700; color: #123A7A; }
    .sub-title { color: #555; margin-bottom: 1rem; }
    .section-box {
        border: 1px solid #D4DDE8; border-radius: 10px;
        padding: 1rem 1.2rem; margin-bottom: 1rem; background: #F8FAFC;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="main-title">🚆 Safety Deficiencies Dashboard</div>'
    '<div class="sub-title">Indian Railways · Solapur Division · Central Railway</div>',
    unsafe_allow_html=True,
)

base, excel_path, logo_path, out_dir = resolve_paths()

# ---- Sidebar / controls ----
with st.sidebar:
    st.header("⚙️ Settings")

    st.subheader("0. Data file")
    uploaded = st.file_uploader(
        "Upload Excel for analysis (optional)",
        type=["xlsx", "xls"],
        help="If you upload a file, it is used instead of DATA.xlsx on disk.",
    )
    if uploaded is not None:
        # Save upload to temp and use for this session
        up_path = Path(tempfile.gettempdir()) / f"streamlit_upload_{uploaded.name}"
        up_path.write_bytes(uploaded.getvalue())
        excel_path = up_path
        st.success(f"Using uploaded: **{uploaded.name}**")
        # bust cache when new file uploaded
        st.session_state["_upload_name"] = uploaded.name
        st.session_state["_upload_mtime"] = float(up_path.stat().st_mtime)
    else:
        st.caption(f"Default Excel: `{excel_path.name}`")
        if not excel_path.exists():
            st.error(f"Excel not found:\n{excel_path}\nUpload a file above or place DATA.xlsx in the project folder.")
            st.stop()

    st.subheader("1. Department")
    dept_options = {k: v[0] for k, v in DEPARTMENTS.items()}
    selected_keys = st.multiselect(
        "Select department(s)",
        options=list(dept_options.keys()),
        format_func=lambda k: dept_options[k],
        default=["operating"],
    )

    st.subheader("2. Date range")
    col_a, col_b = st.columns(2)
    with col_a:
        start_date = st.date_input("From", value=date(2026, 4, 1))
    with col_b:
        end_date = st.date_input("To", value=date(2026, 7, 31))
    if start_date > end_date:
        st.error("From date must be on or before To date.")
        st.stop()

    st.subheader("3. Analysis type")
    mode = st.radio(
        "Generate",
        options=["Both", "Detailed only", "General only"],
        index=0,
        help="Detailed = combinations.py style · General = master_code.py (PIL) style",
    )

    run_btn = st.button("▶ Generate dashboards", type="primary", use_container_width=True)

# ---- Load & preview data ----
@st.cache_data(show_spinner=False)
def cached_load(path_str: str, mtime: float) -> pd.DataFrame:
    return normalize_columns(load_raw_excel(Path(path_str)))


try:
    mtime = float(st.session_state.get("_upload_mtime", excel_path.stat().st_mtime))
    raw_df = cached_load(str(excel_path), mtime)
except Exception as e:
    st.error(f"Failed to read Excel: {e}")
    st.stop()

filtered_df = filter_by_date(raw_df, start_date, end_date)

with st.expander("📊 Data preview (after date filter)", expanded=False):
    st.write(
        f"Total rows in file: **{len(raw_df)}** · "
        f"After date filter ({start_date} → {end_date}): **{len(filtered_df)}**"
    )
    st.dataframe(filtered_df.head(30), use_container_width=True)

if not selected_keys:
    st.info("Select at least one department in the sidebar.")
    st.stop()

if not run_btn and "results" not in st.session_state:
    st.info("Choose options on the left, then click **Generate dashboards**.")
    st.stop()

# ---- Generate ----
if run_btn:
    results: List[dict] = []
    apply_report_period(start_date, end_date)
    temp_excel = write_temp_excel(filtered_df)
    # Point unified module at temp filtered data + local output
    rs.EXCEL_FILE = temp_excel
    rs.OUTPUT_FOLDER = out_dir
    rs.OUTPUT_FOLDER_STR = str(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear general cache so it reloads filtered file
    rs._cached_df = None

    progress = st.progress(0.0, text="Starting…")
    n = len(selected_keys)
    for i, key in enumerate(selected_keys):
        label, detailed_key, general_key = DEPARTMENTS[key]
        progress.progress((i) / max(n, 1), text=f"Processing {label}…")
        item = {
            "key": key,
            "label": label,
            "detailed_path": None,
            "general_path": None,
            "detailed_error": None,
            "general_error": None,
            "subhead_xlsx": None,
            "pending_xlsx": None,
        }
        t0 = datetime.now().timestamp()

        # Force both families to use the same filtered / uploaded Excel
        excel_arg = str(temp_excel)
        rs.EXCEL_FILE = temp_excel
        rs._cached_df = None

        # Detailed — call with excel= explicitly (defaults are bound at import time)
        if mode in ("Both", "Detailed only") and detailed_key:
            try:
                if detailed_key in ("engg", "engg_c"):
                    path = rs.generate_engineering(rs.ENGG_DEFAULT_DEN if detailed_key == "engg" else "Sr.DEN/C", excel=excel_arg)
                elif detailed_key == "engg_s":
                    path = rs.generate_engineering("Sr.DEN/S", excel=excel_arg)
                elif detailed_key == "engg_track":
                    path = rs.generate_engineering("DEN/TRACK", excel=excel_arg)
                elif detailed_key == "engg_full":
                    path = rs.generate_engineering(None, excel=excel_arg)
                elif detailed_key in ("elect_g",):
                    path = rs.generate_elect_g(excel=excel_arg)
                elif detailed_key in ("elect_trd",):
                    path = rs.generate_elect_trd(excel=excel_arg)
                elif detailed_key in ("elect_tro", "tro"):
                    path = rs.generate_elect_tro(excel=excel_arg)
                elif detailed_key in ("snt", "s_and_t"):
                    path = rs.generate_snt(excel=excel_arg)
                elif detailed_key == "mechanical":
                    path = rs.generate_mechanical(excel=excel_arg)
                elif detailed_key == "operating":
                    path = rs.generate_operating(excel=excel_arg)
                elif detailed_key == "commercial":
                    path = rs.generate_commercial(excel=excel_arg)
                elif detailed_key in rs.DASHBOARDS:
                    # fallback: try calling with excel kw if supported
                    fn = rs.DASHBOARDS[detailed_key]
                    try:
                        path = fn(excel=excel_arg)
                    except TypeError:
                        path = fn()
                else:
                    raise KeyError(f"Unknown detailed key: {detailed_key}")
                item["detailed_path"] = path
            except Exception as exc:
                item["detailed_error"] = str(exc)
                hint = DETAILED_OUT_HINTS.get(detailed_key, key.upper())
                found = find_latest_image(out_dir, hint, t0)
                if found:
                    item["detailed_path"] = str(found)

        # General (PIL) — already passed excel=
        if mode in ("Both", "General only") and general_key:
            try:
                path = rs.generate_general(general_key, excel=temp_excel)
                item["general_path"] = path
            except Exception as exc:
                item["general_error"] = str(exc)
                expected = out_dir / general_output_name(key)
                if expected.exists():
                    item["general_path"] = str(expected)

        # Excel downloads + on-page tables (from filtered data)
        item["subhead_pkg"] = None
        item["pending_xlsx"] = None
        item["pending_df"] = None
        item["summary_df"] = None
        item["full_df"] = None
        item["per_subhead_dfs"] = []
        try:
            item["subhead_pkg"] = build_subhead_package(filtered_df, key)
            # rebuild small display frames (same filter logic)
            work = head_filter_for_dept(filtered_df, key)
            if not work.empty and "Sub Head" in work.columns:
                work = work.copy()
                work["Sub Head"] = work["Sub Head"].fillna("").astype(str).str.strip()
                work = work[work["Sub Head"] != ""].copy()
                if "Status" in work.columns:
                    work["STATUS_GROUP"] = classify_status_series(work["Status"])
                else:
                    work["STATUS_GROUP"] = "Pending"
                orig_cols = _original_columns(work)
                summary = (
                    work.groupby("Sub Head")
                    .agg(
                        Total=("Sub Head", "size"),
                        Resolved=("STATUS_GROUP", lambda x: (x == "Resolved").sum()),
                        Pending=("STATUS_GROUP", lambda x: (x == "Pending").sum()),
                        No_Response=("STATUS_GROUP", lambda x: (x == "No Response").sum()),
                    )
                    .reset_index()
                    .sort_values("Total", ascending=False)
                )
                if len(summary):
                    summary["% Resolved"] = (
                        summary["Resolved"] / summary["Total"] * 100
                    ).round(2)
                item["summary_df"] = summary
                item["full_df"] = work[orig_cols]
                item["per_subhead_dfs"] = [
                    {"name": sh, "df": work[work["Sub Head"] == sh][orig_cols]}
                    for sh in summary["Sub Head"].tolist()
                ]
        except Exception as exc:
            item["detailed_error"] = (item["detailed_error"] or "") + f" | SubHead Excel: {exc}"
        try:
            item["pending_xlsx"] = build_pending_excel(filtered_df, key)
            work = head_filter_for_dept(filtered_df, key)
            if not work.empty and "Status" in work.columns:
                work = work.copy()
                work["STATUS_GROUP"] = classify_status_series(work["Status"])
                pending = work[work["STATUS_GROUP"].isin(["Pending", "No Response"])]
                item["pending_df"] = pending[_original_columns(pending)]
            elif not work.empty:
                item["pending_df"] = work.head(0)
        except Exception as exc:
            item["general_error"] = (item["general_error"] or "") + f" | Pending Excel: {exc}"

        results.append(item)

    progress.progress(1.0, text="Done")
    st.session_state["results"] = results
    st.session_state["period"] = (str(start_date), str(end_date))
    try:
        os.unlink(temp_excel)
    except OSError:
        pass

# ---- Display results ----
results = st.session_state.get("results", [])
period = st.session_state.get("period", ("", ""))

if not results:
    st.warning("No results yet.")
    st.stop()

st.success(
    f"Generated for period **{period[0]} → {period[1]}** · "
    f"{len(results)} department(s)"
)

for item in results:
    st.markdown("---")
    st.subheader(f"📁 {item['label']}")

    # ----- DETAILED -----
    if mode in ("Both", "Detailed only") or item.get("detailed_path") or item.get("subhead_pkg"):
        st.markdown("### 🔎 Detailed Analysis")
        st.caption("Jurisdiction / classification dashboards (combinations logic)")
        if item.get("detailed_error"):
            st.error(f"Detailed: {item['detailed_error']}")
        if item.get("detailed_path") and Path(item["detailed_path"]).exists():
            st.image(item["detailed_path"], use_container_width=True)
            with open(item["detailed_path"], "rb") as f:
                st.download_button(
                    "⬇ Download detailed image (PNG)",
                    data=f.read(),
                    file_name=Path(item["detailed_path"]).name,
                    mime="image/png",
                    key=f"dl_det_img_{item['key']}",
                )
        elif mode in ("Both", "Detailed only"):
            st.warning("Detailed image not available.")

        pkg = item.get("subhead_pkg") or {}
        # --- Show tables on page + download options ---
        if item.get("summary_df") is not None and len(item["summary_df"]):
            st.markdown("#### Sub-Head summary")
            st.dataframe(item["summary_df"], use_container_width=True, hide_index=True)
            if pkg.get("summary_xlsx"):
                st.download_button(
                    "⬇ Download Sub-Head summary Excel",
                    data=pkg["summary_xlsx"],
                    file_name=f"{item['key']}_SubHead_Summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_sum_{item['key']}",
                )

        per_dfs = item.get("per_subhead_dfs") or []
        per_bytes = (pkg.get("per_subhead") or []) if pkg else []
        if per_dfs:
            st.markdown("#### Records by Sub-Head")
            for i, part in enumerate(per_dfs):
                with st.expander(f"📂 {part['name']}  ({len(part['df'])} rows)", expanded=(i == 0)):
                    st.dataframe(part["df"], use_container_width=True, hide_index=True)
                    # matching download bytes if available
                    bdata = None
                    fname = f"{item['key']}_{part['name']}_Records.xlsx"
                    if i < len(per_bytes):
                        bdata = per_bytes[i]["bytes"]
                        fname = f"{item['key']}_{per_bytes[i]['file']}"
                    else:
                        bio = io.BytesIO()
                        part["df"].to_excel(bio, index=False)
                        bdata = bio.getvalue()
                    st.download_button(
                        f"⬇ Download Excel – {part['name'][:40]}",
                        data=bdata,
                        file_name=fname,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_sh_{item['key']}_{i}",
                    )

        if item.get("full_df") is not None and len(item["full_df"]):
            st.markdown("#### Full recorded data (this department)")
            st.dataframe(item["full_df"], use_container_width=True, hide_index=True)
            if pkg.get("full_xlsx"):
                st.download_button(
                    "⬇ Download full recorded Excel",
                    data=pkg["full_xlsx"],
                    file_name=f"{item['key']}_Full_Records.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_full_{item['key']}",
                )
            if pkg.get("combined_xlsx"):
                st.download_button(
                    "⬇ Download combined workbook (all Sub-Heads + Full)",
                    data=pkg["combined_xlsx"],
                    file_name=f"{item['key']}_SubHead_Combined.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_comb_{item['key']}",
                )

    # ----- GENERAL -----
    if mode in ("Both", "General only") or item.get("general_path") or item.get("pending_xlsx"):
        st.markdown("### 📋 General Analysis")
        st.caption("Summary resolution dashboards (master_code / PIL logic)")
        if item.get("general_error"):
            st.error(f"General: {item['general_error']}")
        if item.get("general_path") and Path(item["general_path"]).exists():
            st.image(item["general_path"], use_container_width=True)
            with open(item["general_path"], "rb") as f:
                st.download_button(
                    "⬇ Download general image (PNG)",
                    data=f.read(),
                    file_name=Path(item["general_path"]).name,
                    mime="image/png",
                    key=f"dl_gen_img_{item['key']}",
                )
        elif mode in ("Both", "General only"):
            st.warning("General image not available.")

        if item.get("pending_df") is not None:
            st.markdown("#### Pending / No Response records")
            if len(item["pending_df"]):
                st.dataframe(item["pending_df"], use_container_width=True, hide_index=True)
            else:
                st.info("No pending or no-response records for this selection.")
            if item.get("pending_xlsx"):
                st.download_button(
                    "⬇ Download Pending records Excel",
                    data=item["pending_xlsx"],
                    file_name=f"{item['key']}_Pending_Records.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_pend_{item['key']}",
                )
        elif item.get("pending_xlsx"):
            st.download_button(
                "⬇ Download Pending records Excel",
                data=item["pending_xlsx"],
                file_name=f"{item['key']}_Pending_Records.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_pend_{item['key']}",
            )

st.markdown("---")
st.caption("Source: SARAL · Solapur Division, Central Railway · Generated via Streamlit UI")
