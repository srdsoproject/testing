
#!/usr/bin/env python3
"""
Safety Deficiencies Dashboard - website with day/month/year + record tables
Run:
    streamlit run app.py
"""

from __future__ import annotations

import io
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------- Project folder ----------
BASE_DIR = Path(r"C:\Users\USER1.DSONC\PycharmProjects\PythonProject1")
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

EXCEL_FILE = BASE_DIR / "DATA.xlsx"
OUTPUT_FOLDER = BASE_DIR / "DEPARTMENT_DASHBOARDS"
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

DEPARTMENT_OPTIONS = {
    "ELECT / G": "elect_g",
    "Engineering (Sr.DEN/C)": "engg",
    "Engineering (Sr.DEN/S)": "engg_s",
    "Engineering (DEN/TRACK)": "engg_track",
    "Engineering (Full)": "engg_full",
    "ELECT / TRD": "elect_trd",
    "ELECT / TRO": "elect_tro",
    "S&T (ADSTE)": "snt",
    "Mechanical": "mechanical",
    "Operating": "operating",
    "Commercial": "commercial",
}

# Map website key -> Excel Head value(s)
HEAD_FOR_KEY = {
    "elect_g": ["ELECT/G", "ELECT / G", "ELECTG"],
    "engg": ["ENGINEERING"],
    "engg_c": ["ENGINEERING"],
    "engg_s": ["ENGINEERING"],
    "engg_track": ["ENGINEERING"],
    "engg_full": ["ENGINEERING"],
    "elect_trd": ["ELECT/TRD", "ELECT / TRD", "ELECTTRD"],
    "elect_tro": ["ELECT/TRO", "ELECT / TRO", "ELECTTRO", "ELECT/TRO"],
    "snt": ["SIGNAL & TELECOM", "S&T", "SNT", "SIGNAL AND TELECOM"],
    "mechanical": ["MECHANICAL"],
    "operating": ["OPTG", "OPERATING", "OPERATING DEPARTMENT"],
    "commercial": ["COMMERCIAL"],
}

ENGG_DEN_FOR_KEY = {
    "engg": "Sr.DEN/C",
    "engg_c": "Sr.DEN/C",
    "engg_s": "Sr.DEN/S",
    "engg_track": "DEN/TRACK",
    "engg_full": None,
}

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

st.set_page_config(
    page_title="Safety Deficiencies Dashboard",
    page_icon="rail",
    layout="wide",
)

st.title("Safety Deficiencies Dashboard Generator")
st.caption("Solapur Division · Central Railway · SARAL data")

st.markdown("---")

col1, col2 = st.columns([2, 1])
with col1:
    dept_label = st.selectbox(
        "Select department",
        list(DEPARTMENT_OPTIONS.keys()),
        index=list(DEPARTMENT_OPTIONS.keys()).index("Operating")
        if "Operating" in DEPARTMENT_OPTIONS
        else 0,
    )
    dept_key = DEPARTMENT_OPTIONS[dept_label]
with col2:
    mode = st.radio(
        "What to generate",
        ["Both (Detailed + General)", "Detailed only", "General only"],
        index=0,
    )

st.subheader("Report period (Day / Month / Year)")

c1, c2 = st.columns(2)
with c1:
    start_date = st.date_input(
        "From date",
        value=date(2026, 4, 1),
        min_value=date(2020, 1, 1),
        max_value=date(2035, 12, 31),
        format="DD/MM/YYYY",
    )
with c2:
    end_date = st.date_input(
        "To date",
        value=date(2026, 7, 31),
        min_value=date(2020, 1, 1),
        max_value=date(2035, 12, 31),
        format="DD/MM/YYYY",
    )

if end_date < start_date:
    st.error("To date cannot be before From date. Please correct the dates.")
    st.stop()

report_months = []
y, m = start_date.year, start_date.month
while (y, m) <= (end_date.year, end_date.month):
    report_months.append(m)
    if m == 12:
        y += 1
        m = 1
    else:
        m += 1
report_months = list(dict.fromkeys(report_months))

year = end_date.year
from_label = start_date.strftime("%d %B %Y")
to_label = end_date.strftime("%d %B %Y")
period_title = (
    f"FOR THE PERIOD {start_date.strftime('%d %b %Y').upper()} "
    f"TO {end_date.strftime('%d %b %Y').upper()}"
)
section_period = (
    f"{start_date.strftime('%d %b').upper()} TO "
    f"{end_date.strftime('%d %b %Y').upper()}"
)
data_as_on = end_date.strftime("%d %B %Y").upper()
period_text_general = f"PERFORMANCE PERIOD: {from_label} to {to_label}"

st.info(
    f"**From:** {from_label}  \n"
    f"**To:** {to_label}  \n"
    f"**Months in tables:** {', '.join(MONTH_NAMES[m] for m in report_months)}  \n"
    f"**Title:** {period_title}"
)

st.markdown("---")
generate = st.button("Generate dashboards", type="primary", use_container_width=True)


def apply_period_to_detailed(mod) -> None:
    mod.REPORT_MONTHS = list(report_months)
    mod.REPORT_YEAR = int(year)
    mod.MONTH_LABELS = {m: f"{MONTH_NAMES[m]}-{year}" for m in range(1, 13)}
    mod.START_DATE = start_date.isoformat()
    mod.END_DATE = end_date.isoformat()
    mod.PERIOD_TITLE = period_title
    mod.SECTION_PERIOD = section_period
    mod.DATA_AS_ON = data_as_on


def apply_period_to_general(mod) -> None:
    mod.PERIOD_TEXT = period_text_general


def _normalize_head(s: str) -> str:
    return (
        str(s).upper().strip()
        .replace(" ", "")
        .replace("/", "")
        .replace("&", "AND")
        .replace("-", "")
        .replace("_", "")
    )


def _normalize_action(s: str) -> str:
    return str(s).strip().upper().replace(" ", "").replace("\\", "/")


def load_filtered_records(dept_key: str, start, end) -> pd.DataFrame:
    """Load Excel and filter by department + date range (same period as dashboards)."""
    if not EXCEL_FILE.exists():
        raise FileNotFoundError(f"DATA.xlsx not found at {EXCEL_FILE}")

    xls = pd.ExcelFile(EXCEL_FILE)
    df = None
    for sheet in xls.sheet_names:
        try:
            tmp = pd.read_excel(EXCEL_FILE, sheet_name=sheet)
            tmp.columns = (
                tmp.columns.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
            )
            if "Date of Inspection" in tmp.columns and "Head" in tmp.columns:
                df = tmp
                break
        except Exception:
            continue
    if df is None:
        raise ValueError("Could not find a sheet with Date of Inspection and Head")

    df = df.copy()
    df.columns = df.columns.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    df["Date of Inspection"] = pd.to_datetime(
        df["Date of Inspection"], errors="coerce", dayfirst=True
    )
    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    mask = df["Date of Inspection"].notna()
    mask &= df["Date of Inspection"] >= pd.Timestamp(start)
    mask &= df["Date of Inspection"] <= end_ts
    df = df[mask].copy()

    heads = HEAD_FOR_KEY.get(dept_key, [])
    head_norm = df["Head"].fillna("").astype(str).map(_normalize_head)
    want = {_normalize_head(h) for h in heads}
    # also partial match for SIGNAL / OPTG
    def head_ok(h):
        if h in want:
            return True
        for w in want:
            if w and (w in h or h in w):
                return True
        return False

    df = df[head_norm.map(head_ok)].copy()

    # Engineering DEN filter
    if dept_key in ENGG_DEN_FOR_KEY and "Action By" in df.columns:
        den = ENGG_DEN_FOR_KEY[dept_key]
        if den is not None:
            ab = df["Action By"].fillna("").map(_normalize_action)
            target = _normalize_action(den)
            df = df[ab == target].copy()

    return df.reset_index(drop=True)


def _safe_sheet_name(name: str, used: set) -> str:
    # Excel sheet name: max 31 chars; no / \ ? * : [ ]
    s = str(name)
    for ch in ['/', '\\', '?', '*', ':', '[', ']']:
        s = s.replace(ch, '_')
    s = s.strip() or 'Sheet'
    s = s[:31]
    base = s
    n = 1
    while s in used:
        suffix = '_' + str(n)
        s = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(s)
    return s


def to_excel_bytes(frames: dict) -> bytes:
    # frames: sheet_name to DataFrame
    buf = io.BytesIO()
    used = set()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, frame in frames.items():
            safe = _safe_sheet_name(name, used)
            if frame is None or len(frame) == 0:
                pd.DataFrame({"Info": ["No records"]}).to_excel(
                    writer, sheet_name=safe, index=False
                )
            else:
                frame.to_excel(writer, sheet_name=safe, index=False)
    return buf.getvalue()


def is_pending(status) -> bool:
    s = str(status).upper()
    # drop non-ascii symbols (emoji etc.)
    s = "".join(c for c in s if ord(c) < 128)
    s = s.strip()
    if "RESOLVED" in s:
        return False
    if "PENDING" in s:
        return True
    if s in ("", "NAN", "NONE", "NO RESPONSE", "NO_RESPONSE", "NO RESPONSE RECEIVED"):
        return False
    return "PENDING" in s



if generate:
    results = []
    errors = []
    need_detailed = mode in ("Both (Detailed + General)", "Detailed only")
    need_general = mode in ("Both (Detailed + General)", "General only")
    records_df = None

    progress = st.progress(0, text="Starting...")

    # Load records once for tables/downloads
    try:
        progress.progress(10, text="Loading Excel records for tables...")
        records_df = load_filtered_records(dept_key, start_date, end_date)
    except Exception as exc:
        errors.append(f"Records load error: {exc}")

    if need_detailed:
        progress.progress(25, text="Running detailed analysis (combinations.py)...")
        try:
            import combinations as detailed_mod

            apply_period_to_detailed(detailed_mod)
            if dept_key not in detailed_mod.DASHBOARDS:
                errors.append(f"Detailed: unknown department key '{dept_key}'")
            else:
                path = detailed_mod.DASHBOARDS[dept_key]()
                results.append(("Detailed", path))
        except Exception as exc:
            errors.append(f"Detailed error: {exc}")

    progress.progress(55, text="Running general analysis (master_code.py)...")

    if need_general:
        try:
            import master_code as general_mod

            apply_period_to_general(general_mod)
            if not hasattr(general_mod, "generate_general"):
                errors.append(
                    "General error: master_code.py has no generate_general. "
                    "Use the updated master_code.py file."
                )
            else:
                try:
                    path = general_mod.generate_general(
                        dept_key, period_text=period_text_general
                    )
                except TypeError:
                    path = general_mod.generate_general(dept_key)
                results.append(("General", path))
        except Exception as exc:
            errors.append(f"General error: {exc}")

    progress.progress(100, text="Done")

    if errors:
        st.error("Some steps failed:")
        for e in errors:
            st.write(f"- {e}")

    # ---- Show dashboard images ----
    if results:
        st.success(
            f"Generated {len(results)} dashboard(s) for **{dept_label}** "
            f"({from_label} to {to_label})"
        )
        for kind, path in results:
            path = Path(path)
            st.subheader(f"{kind} dashboard")
            st.write(f"Saved as: `{path.name}`")
            if path.exists():
                st.image(str(path), use_container_width=True)
                with open(path, "rb") as f:
                    st.download_button(
                        label=f"Download {path.name}",
                        data=f.read(),
                        file_name=path.name,
                        mime="image/png",
                        key=f"dl_{kind}_{path.name}",
                    )
            else:
                st.warning(f"File not found: {path}")

    # ---- DETAILED: Sub-Head wise records (same Excel columns) ----
    if need_detailed and records_df is not None:
        st.markdown("---")
        st.header("Detailed – Records Sub-Head wise")
        st.caption(
            "Same data as Excel, filtered by department and date, grouped by Sub Head "
            "so officers can see which items fall under each Sub Head."
        )

        if records_df.empty:
            st.warning("No records found for this department and date range.")
        else:
            st.write(f"Total records: **{len(records_df)}**")

            # Full download – all records in period
            all_bytes = to_excel_bytes({"All_Records": records_df})
            st.download_button(
                label="Download all records (Excel)",
                data=all_bytes,
                file_name=f"{dept_key}_all_records_{start_date}_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_all_records",
            )

            # One sheet per Sub Head for officers
            sub_col = "Sub Head" if "Sub Head" in records_df.columns else None
            if sub_col:
                sheets = {"All_Records": records_df}
                for sh, grp in records_df.groupby(records_df[sub_col].fillna("(Blank)")):
                    key = str(sh)
                    for ch in ['/', '\\', '?', '*', ':', '[', ']']:
                        key = key.replace(ch, '_')
                    sheets[key[:31] or 'Sheet'] = grp
                by_sub_bytes = to_excel_bytes(sheets)
                st.download_button(
                    label="Download Sub-Head wise Excel (one sheet per Sub Head)",
                    data=by_sub_bytes,
                    file_name=f"{dept_key}_subhead_wise_{start_date}_{end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_subhead_excel",
                )

                subheads = sorted(
                    records_df[sub_col].fillna("(Blank)").astype(str).unique(),
                    key=lambda x: (-len(records_df[records_df[sub_col].fillna("(Blank)").astype(str) == x]), x),
                )
                for sh in subheads:
                    grp = records_df[
                        records_df[sub_col].fillna("(Blank)").astype(str) == sh
                    ]
                    with st.expander(f"{sh}  ({len(grp)} records)", expanded=False):
                        st.dataframe(grp, use_container_width=True)
                        st.download_button(
                            label=f"Download Excel – {sh[:40]}",
                            data=to_excel_bytes({str(sh)[:31]: grp}),
                            file_name=f"{dept_key}_{str(sh)[:40].replace('/', '_')}_{start_date}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_sh_{hash(sh) % 10_000_000}",
                        )
            else:
                st.dataframe(records_df, use_container_width=True)

    # ---- GENERAL: Pending records (Excel format) ----
    if need_general and records_df is not None:
        st.markdown("---")
        st.header("General – Pending records")
        st.caption(
            "Pending items only, same columns as the Excel sheet, "
            "for the selected department and date range."
        )

        status_col = "Status" if "Status" in records_df.columns else None
        if status_col is None:
            st.warning("No Status column found in Excel.")
        else:
            pending_df = records_df[records_df[status_col].map(is_pending)].copy()
            st.write(f"Pending records: **{len(pending_df)}**")

            if pending_df.empty:
                st.success("No pending records in this period.")
            else:
                st.dataframe(pending_df, use_container_width=True)
                st.download_button(
                    label="Download Pending records (Excel)",
                    data=to_excel_bytes({"Pending": pending_df}),
                    file_name=f"{dept_key}_pending_{start_date}_{end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_pending_excel",
                )
                # Also CSV
                csv_buf = pending_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="Download Pending records (CSV)",
                    data=csv_buf,
                    file_name=f"{dept_key}_pending_{start_date}_{end_date}.csv",
                    mime="text/csv",
                    key="dl_pending_csv",
                )

st.markdown("---")
st.caption(
    "Data: DATA.xlsx · Output: DEPARTMENT_DASHBOARDS · "
    "Detailed = combinations.py + Sub-Head wise records · "
    "General = master_code.py + Pending records · Downloads are Excel/CSV."
)