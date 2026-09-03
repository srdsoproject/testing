#!/usr/bin/env python3
"""
Indian Railways – Solapur Division
Unified Safety Deficiencies Dashboard Generator
================================================
Single entry-point module that generates all department dashboards
while preserving original logic, classification rules and layout.

Usage
-----
    python railway_safety_dashboards.py                  # generate ALL
    python railway_safety_dashboards.py elect_g engg    # selected only
    from railway_safety_dashboards import generate_all
    generate_all()
"""

from __future__ import annotations

import os
import re
import sys
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle
from PIL import Image

# ============================================================
# ★★★  EASY SETTINGS – OFFICE USE ONLY (edit this block)  ★★★
# ============================================================
# Non-technical users: change ONLY the values in this section.
#
# IMPORTANT:
#   Sub-Head tables and Jurisdiction tables AUTOMATICALLY create
#   one column / one row for EVERY month in REPORT_MONTHS.
#   Titles also follow these settings.
#
# After editing → Save → Run:
#     python railway_safety_dashboards.py
# ============================================================

# ---------- 1. FILES / FOLDERS ----------
BASE_DIR = r"C:\Users\USER1.DSONC\PycharmProjects\PythonProject1"
EXCEL_FILE_NAME = "DATA.xlsx"
LOGO_FILE_NAME = "indian_railways_logo.png"
TRAIN_FILE_NAME = "train.png"
OUTPUT_FOLDER_NAME = "DEPARTMENT_DASHBOARDS"

# ---------- 2. MONTHS (controls ALL table columns & rows) ----------
# Add or remove month numbers – tables rebuild automatically.
# 1=Jan  2=Feb  3=Mar  4=Apr  5=May  6=Jun
# 7=Jul  8=Aug  9=Sep  10=Oct 11=Nov 12=Dec
#
# Examples:
#   [4, 5, 6]     → April, May, June
#   [4, 5, 6, 7]  → April, May, June, July   ← current
#   [7, 8, 9]     → July, August, September
REPORT_MONTHS = [4, 5, 6, 7]

# Optional exact date range (set by website). None = use full months only.
START_DATE = None  # e.g. "2026-04-01"
END_DATE = None    # e.g. "2026-07-31"

# Year used in labels and titles
REPORT_YEAR = 2026

# Full labels for Sub-Head table column headers
MONTH_LABELS = {
    1: f"January-{REPORT_YEAR}",
    2: f"February-{REPORT_YEAR}",
    3: f"March-{REPORT_YEAR}",
    4: f"April-{REPORT_YEAR}",
    5: f"May-{REPORT_YEAR}",
    6: f"June-{REPORT_YEAR}",
    7: f"July-{REPORT_YEAR}",
    8: f"August-{REPORT_YEAR}",
    9: f"September-{REPORT_YEAR}",
    10: f"October-{REPORT_YEAR}",
    11: f"November-{REPORT_YEAR}",
    12: f"December-{REPORT_YEAR}",
}

# Short labels for Jurisdiction tables (one row per month)
MONTH_SHORT = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}

# ---------- 3. TITLES (blank "" = auto from REPORT_MONTHS) ----------
# Main title under department name:
#   FOR THE MONTH OF APRIL, MAY, JUNE & JULY 2026
PERIOD_TITLE = ""

# Text inside section boxes, e.g.:
#   II - CLASSIFICATION SUB HEAD DISTRIBUTION (APRIL TO JULY-2026)
SECTION_PERIOD = ""

# Footer date
DATA_AS_ON = "31 JULY 2026"

# ---------- 4. WHICH DASHBOARDS TO RUN ----------
GENERATE = {
    "elect_g": True,
    "engg": True,          # uses ENGG_DEFAULT_DEN
    "engg_s": False,
    "engg_track": False,
    "engg_full": False,
    "elect_trd": True,
    "elect_tro": True,
    "snt": True,
    "mechanical": True,
    "operating": True,
    "commercial": True,
}

# Engineering DEN when key "engg" is used
# "Sr.DEN/C" | "Sr.DEN/S" | "DEN/TRACK" | None
ENGG_DEFAULT_DEN = "Sr.DEN/C"

# ============================================================
# (Do not edit below this line unless you are a developer)
# ============================================================

EXCEL_FILE = os.path.join(BASE_DIR, EXCEL_FILE_NAME)
LOGO_FILE = os.path.join(BASE_DIR, LOGO_FILE_NAME)
TRAIN_FILE = os.path.join(BASE_DIR, TRAIN_FILE_NAME)
OUTPUT_FOLDER = os.path.join(BASE_DIR, OUTPUT_FOLDER_NAME)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def _period_title() -> str:
    """Main title: FOR THE MONTH OF APRIL, MAY, JUNE & JULY 2026"""
    if PERIOD_TITLE and str(PERIOD_TITLE).strip():
        return str(PERIOD_TITLE).strip()
    names = []
    for m in REPORT_MONTHS:
        label = MONTH_LABELS.get(m, str(m))
        word = label.split("-")[0].upper() if "-" in str(label) else str(label).upper()
        names.append(word)
    if not names:
        return f"FOR THE SELECTED PERIOD {REPORT_YEAR}"
    if len(names) == 1:
        body = names[0]
    elif len(names) == 2:
        body = f"{names[0]} & {names[1]}"
    else:
        body = ", ".join(names[:-1]) + f" & {names[-1]}"
    return f"FOR THE MONTH OF {body} {REPORT_YEAR}"


def _section_period() -> str:
    """Short period for section headers: APRIL TO JULY-2026"""
    if SECTION_PERIOD and str(SECTION_PERIOD).strip():
        return str(SECTION_PERIOD).strip()
    if not REPORT_MONTHS:
        return str(REPORT_YEAR)
    first = MONTH_LABELS.get(REPORT_MONTHS[0], str(REPORT_MONTHS[0]))
    last = MONTH_LABELS.get(REPORT_MONTHS[-1], str(REPORT_MONTHS[-1]))
    first_word = str(first).split("-")[0].upper()
    last_label = str(last).upper() if "-" in str(last) else f"{str(last).upper()}-{REPORT_YEAR}"
    if len(REPORT_MONTHS) == 1:
        return last_label
    return f"{first_word} TO {last_label}"


def _month_header_list() -> List[str]:
    """Table column headers for months in REPORT_MONTHS order."""
    return [MONTH_LABELS.get(m, str(m)) for m in REPORT_MONTHS]


def _month_short_list() -> List[str]:
    return [MONTH_SHORT.get(m, str(m)) for m in REPORT_MONTHS]

# ============================================================
# 2. SHARED COLOURS & DRAWING HELPERS
# ============================================================

NAVY = "#123A7A"
DARK_NAVY = "#0C2F67"
GRID = "#D4DDE8"
LIGHT_BLUE = "#EEF4FA"
PALE_YELLOW = "#FFF3D4"
GREEN = "#11833B"
RED = "#C81E2A"
ORANGE = "#D97706"
PURPLE = "#56319A"
TEXT = "#222222"
GRAY = "#6B7280"

WIDTH, HEIGHT = 14, 8


def _check_assets(*extra: str) -> None:
    for path, desc in [
        (LOGO_FILE, "Indian Railways logo"),
        (TRAIN_FILE, "Train PNG"),
        *[(p, p) for p in extra],
    ]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"{desc} not found:\n{path}")


def draw_box(ax, x, y, w, h, facecolor="white", edgecolor=GRID, radius=0.05):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0.012,rounding_size={radius}",
            facecolor=facecolor, edgecolor=edgecolor, linewidth=0.8,
        )
    )


def draw_rect(ax, x, y, w, h, color, edgecolor=None):
    ax.add_patch(
        Rectangle(
            (x, y), w, h,
            facecolor=color,
            edgecolor=edgecolor or color,
            linewidth=0.5,
        )
    )


def add_text(ax, x, y, text, size=8, weight="normal", color=TEXT, ha="left", va="center"):
    ax.text(
        x, y, str(text),
        fontsize=size, fontweight=weight, color=color,
        ha=ha, va=va, family="DejaVu Sans",
    )


def new_canvas():
    fig = plt.figure(figsize=(WIDTH, HEIGHT), dpi=170)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(0, HEIGHT)
    ax.axis("off")
    return fig, ax


def draw_header(ax, title_lines: Sequence[str], subtitle: str = "Source: SARAL"):
    logo = Image.open(LOGO_FILE).convert("RGBA")
    ax.imshow(logo, extent=[0.08, 0.88, 7.18, 7.94], aspect="auto", zorder=10)
    add_text(ax, 1.02, 7.72, "INDIAN RAILWAYS", 13, "bold", NAVY)
    add_text(ax, 1.02, 7.46, "SOLAPUR DIVISION", 10.5, "bold", NAVY)
    add_text(ax, 1.02, 7.24, "CENTRAL RAILWAY", 10.5, "bold", NAVY)
    y = 7.62
    for i, line in enumerate(title_lines):
        add_text(ax, 7, y - i * 0.23, line, 16 if i < 2 else 13, "bold", NAVY, "center")
    add_text(ax, 7, 6.98, subtitle, 8.5, "bold", NAVY, "center")
    train = Image.open(TRAIN_FILE).convert("RGBA")
    ax.imshow(train, extent=[12.25, 13.88, 7.20, 7.83], aspect="auto", zorder=10)


def draw_kpi_cards(ax, total, resolved, pending, no_response, y=6.20):
    resolution_rate = (resolved / total * 100) if total else 0.0
    cards = [
        ("TOTAL RECORDS", total, "100% of Total", NAVY, "■"),
        ("RESOLVED", resolved, f"{resolution_rate:.2f}%", GREEN, "✓"),
        ("NO RESPONSE", no_response,
         f"{no_response / total * 100:.2f}%" if total else "0.00%", RED, "..."),
        ("PENDING", pending,
         f"{pending / total * 100:.2f}%" if total else "0.00%", ORANGE, "P"),
        ("OVERALL RESOLUTION RATE", f"{resolution_rate:.2f}%",
         "(Resolved / Total)", PURPLE, "↗"),
    ]
    for i, (title, value, sub_t, color, icon) in enumerate(cards):
        x = 0.20 + i * 2.76
        draw_box(ax, x, y, 2.60, 0.65)
        ax.add_patch(Circle((x + 0.35, y + 0.32), 0.19, facecolor=color,
                            edgecolor="white", linewidth=1))
        add_text(ax, x + 0.35, y + 0.32, icon, 15, "bold", "white", "center")
        add_text(ax, x + 0.66, y + 0.44, title, 7.5, "bold", color)
        add_text(ax, x + 0.66, y + 0.23, str(value), 18, "bold", color)
        add_text(ax, x + 0.66, y + 0.06, sub_t, 7.2, "bold", TEXT)
    return resolution_rate


def draw_footer(ax, dept_text: str, data_as_on: Optional[str] = None):
    data_as_on = data_as_on if data_as_on is not None else DATA_AS_ON
    draw_rect(ax, 0, 0, WIDTH, 0.34, DARK_NAVY)
    add_text(ax, 0.22, 0.17, "Source: SARAL System", 8, color="white")
    add_text(ax, 3.25, 0.17, dept_text, 7.5, color="white")
    add_text(ax, 8.55, 0.17, "Analysis Type: Deficiency Analysis", 8, color="white")
    add_text(ax, 11.35, 0.17, f"Data as on: {data_as_on}", 8, color="white")


def subhead_columns(sub_head_width: float = 2.25, month_width: float = 0.72,
                    total_width: float = 0.65, share_width: float = 0.82,
                    with_share: bool = True):
    """Build table column list from REPORT_MONTHS (office-friendly CONFIG)."""
    cols = [("Sub Head", sub_head_width)]
    for m in REPORT_MONTHS:
        cols.append((MONTH_LABELS.get(m, str(m)), month_width))
    cols.append(("Total", total_width))
    if with_share:
        cols.append(("% Share", share_width))
    return cols


def month_pairs():
    """List of (display_name, month_number) from CONFIG."""
    return [(MONTH_LABELS.get(m, str(m)), m) for m in REPORT_MONTHS]


def total_row_values(df: pd.DataFrame, with_share: bool = True):
    """Total-row cells: label + per-month counts + grand total [+ 100%]."""
    vals = ["Total"] + [int((df["Month"] == m).sum()) for m in REPORT_MONTHS] + [len(df)]
    if with_share:
        vals.append("100.00%")
    return vals


def sub_row_values(sub_head, row, with_share: bool = True):
    vals = [sub_head] + [int(row.get(m, 0)) for m in REPORT_MONTHS] + [int(row["Total"])]
    if with_share:
        vals.append(f"{row['Share']:.2f}%")
    return vals


def status_counts(df: pd.DataFrame) -> Tuple[int, int, int, int]:
    total = len(df)
    resolved = df["Status"].str.contains("Resolved", case=False, na=False).sum()
    pending = df["Status"].str.contains("Pending", case=False, na=False).sum()
    no_response = df["Status"].str.contains("No Response", case=False, na=False).sum()
    return total, int(resolved), int(pending), int(no_response)


def filter_months(df: pd.DataFrame, months: Optional[Sequence[int]] = None) -> pd.DataFrame:
    """Keep only rows in the reporting period.
    - If START_DATE / END_DATE are set: filter by exact day range.
    - Else: filter by REPORT_MONTHS (whole months).
    """
    months = list(months if months is not None else REPORT_MONTHS)
    df = df.copy()
    if "Date of Inspection" in df.columns:
        df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
        df["Month"] = df["Date of Inspection"].dt.month
    elif "Month" not in df.columns:
        return df

    before = len(df)
    start = globals().get("START_DATE")
    end = globals().get("END_DATE")
    if start or end:
        d = df["Date of Inspection"]
        mask = d.notna()
        if start:
            mask &= d >= pd.to_datetime(start)
        if end:
            # include the full end day
            end_ts = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            mask &= d <= end_ts
        out = df[mask].copy()
        dropped = before - len(out)
        if dropped:
            print(f"  [filter] Excluded {dropped} row(s) outside {start} .. {end}")
    else:
        out = df[df["Month"].isin(months)].copy()
        dropped = before - len(out)
        if dropped:
            print(f"  [filter] Excluded {dropped} row(s) outside months {months} / invalid dates")
    return out


def subhead_table(df: pd.DataFrame, months: Optional[Sequence[int]] = None) -> pd.DataFrame:
    months = list(months if months is not None else REPORT_MONTHS)
    sub = df.groupby(["Sub Head", "Month"]).size().unstack(fill_value=0)
    for m in months:
        if m not in sub.columns:
            sub[m] = 0
    sub["Total"] = sub[months].sum(axis=1)
    total = len(df)
    sub["Share"] = (sub["Total"] / total * 100) if total else 0.0
    return sub.sort_values("Total", ascending=False)


def save_fig(fig, path: str) -> None:
    plt.savefig(path, dpi=180, bbox_inches="tight", pad_inches=0.03, facecolor="white")
    plt.close(fig)
    print(f"Saved → {path}")


# ============================================================
# 3. ELECT / G
# ============================================================

def generate_elect_g(excel: str = EXCEL_FILE) -> str:
    _check_assets(excel)
    df = pd.read_excel(excel)
    required = ["Date of Inspection", "Head", "Sub Head", "Location",
                "Deficiencies Noted", "Status"]
    for c in required:
        if c not in df.columns:
            raise KeyError(f"Required column '{c}' missing. Available: {df.columns.tolist()}")

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    for c in ["Head", "Sub Head", "Location", "Deficiencies Noted", "Status"]:
        df[c] = df[c].fillna("").astype(str).str.strip()

    head_clean = df["Head"].str.upper().str.replace(" ", "", regex=False)
    df = df[head_clean.isin(["ELECT/G", "ELECT/G.", "ELECT-G", "ELECTG"])].copy()
    if len(df) == 0:
        raise ValueError("No records found for Head = ELECT/G")

    df["Month"] = df["Date of Inspection"].dt.month
    df = filter_months(df)
    if len(df) == 0:
        raise ValueError("No ELECT/G records in April–June")

    SSE_ELECT_KWV = {
        "KWV", "DHS", "KEM", "BLNI", "BTW", "SEI", "PPJ", "WSB", "KEU", "JNTR",
        "BGVN", "MLM", "BRB", "DD", "MLB", "PVR", "SGLA", "DLGN", "JTRD", "SGRE",
        "ARAG", "KVK", "MRJ", "MKPT", "AAG", "WKA", "MA", "WDS", "WSD",
    }
    SSE_ELECT_SUR = {
        "MKPT", "MA", "AAG", "WKA", "WDS", "DUD", "NGS", "BOT", "AKOR", "SUR",
        "JEUR", "PK", "BALE", "MVE", "MO", "TKWD", "HG", "TLT",
    }
    SSE_ELECT_KLBG = {
        "DUD", "KUI", "GDGN", "GUR", "SVG", "BBD", "KLBG", "TJSP", "HQR", "MR",
        "SDB", "SBD", "WADI", "ME",
    }
    SSE_ELECT_WADI = {"SBD", "SDB", "WADI"}
    SSE_ELECT_LUR = {
        "PJR", "LTRR", "YSI", "DKY", "OSA", "HGL", "LUR", "DRSV", "KMRD",
    }
    ELECT_G_ORDER = [
        "SSE/ELECT/KWV", "SSE/ELECT/SUR", "SSE/ELECT/KLBG",
        "SSE/ELECT/WADI", "SSE/ELECT/LUR",
    ]

    station_map: Dict[str, str] = {}
    for loc in SSE_ELECT_KWV:
        station_map[loc] = "SSE/ELECT/KWV"
    for loc in SSE_ELECT_SUR:
        station_map.setdefault(loc, "SSE/ELECT/SUR")
    for loc in SSE_ELECT_KLBG:
        station_map.setdefault(loc, "SSE/ELECT/KLBG")
    for loc in SSE_ELECT_WADI:
        station_map.setdefault(loc, "SSE/ELECT/WADI")
    for loc in SSE_ELECT_LUR:
        station_map.setdefault(loc, "SSE/ELECT/LUR")

    SECTION_MAP = {
        "KWV-DD": "SSE/ELECT/KWV", "KWV-MLB": "SSE/ELECT/KWV", "KWV-MRJ": "SSE/ELECT/KWV",
        "KWV-DLGN": "SSE/ELECT/KWV", "KWV-SGRE": "SSE/ELECT/KWV", "KWV-SEI": "SSE/ELECT/KWV",
        "KWV-PVR": "SSE/ELECT/KWV", "KWV-DUD": "SSE/ELECT/KWV",
        "KWV-OSA": "SSE/ELECT/LUR", "KWV-LTRR": "SSE/ELECT/LUR",
        "SUR-KWV": "SSE/ELECT/SUR", "KWV-SUR": "SSE/ELECT/SUR", "SUR-DD": "SSE/ELECT/SUR",
        "DD-SUR": "SSE/ELECT/SUR", "SUR-JEUR": "SSE/ELECT/SUR", "JEUR-SUR": "SSE/ELECT/SUR",
        "SUR-NGS": "SSE/ELECT/SUR", "SUR-BOT": "SSE/ELECT/SUR", "BOT-DUD": "SSE/ELECT/SUR",
        "NGS-BOT": "SSE/ELECT/SUR", "DUD-SUR": "SSE/ELECT/SUR", "SUR-PVR": "SSE/ELECT/SUR",
        "SUR-MRJ": "SSE/ELECT/SUR", "SUR-MO": "SSE/ELECT/SUR", "SUR-SDB": "SSE/ELECT/SUR",
        "SUR-KEM": "SSE/ELECT/SUR", "SUR-HG": "SSE/ELECT/SUR",
        "SUR-WADI": "SSE/ELECT/WADI", "WADI-SUR": "SSE/ELECT/WADI",
        "WADI-KLBG": "SSE/ELECT/WADI", "KLBG-WADI": "SSE/ELECT/KLBG",
        "WADI-SDB": "SSE/ELECT/WADI", "WADI-TLT": "SSE/ELECT/WADI", "WADI-KWV": "SSE/ELECT/WADI",
        "KLBG-SUR": "SSE/ELECT/KLBG", "DUD-KLBG": "SSE/ELECT/KLBG", "KLBG-DUD": "SSE/ELECT/KLBG",
        "LUR-KWV": "SSE/ELECT/LUR", "LTRR-KWV": "SSE/ELECT/LUR", "HGL-KWV": "SSE/ELECT/LUR",
    }

    LC_ELECT_G_MAPPING = {
        "LC-19A": "SSE/ELECT/SUR", "LC-40": "SSE/ELECT/SUR", "LC-21": "SSE/ELECT/KWV",
        "LC-42": "SSE/ELECT/SUR",
        "LC-2": "SSE/ELECT/LUR", "LC-4": "SSE/ELECT/LUR", "LC-5": "SSE/ELECT/LUR",
        "LC-6": "SSE/ELECT/LUR", "LC-55": "SSE/ELECT/LUR", "LC-59": "SSE/ELECT/LUR",
        "LC-47": "SSE/ELECT/LUR", "LC-39": "SSE/ELECT/LUR", "LC-34": "SSE/ELECT/LUR",
        "LC-10": "SSE/ELECT/LUR", "LC-36": "SSE/ELECT/LUR",
        "LC-22": "SSE/ELECT/KWV", "LC-24": "SSE/ELECT/KWV", "LC-70": "SSE/ELECT/KWV",
        "LC-31": "SSE/ELECT/KWV", "LC-49": "SSE/ELECT/KWV",
        "LC-74": "SSE/ELECT/SUR", "LC-82": "SSE/ELECT/KLBG", "LC-91": "SSE/ELECT/WADI",
        "LC-1": "SSE/ELECT/WADI", "LC-3": "SSE/ELECT/WADI", "LC-61": "SSE/ELECT/SUR",
        "LC-66": "SSE/ELECT/SUR", "LC-60A": "SSE/ELECT/SUR", "LC-60": "SSE/ELECT/SUR",
    }

    def normalize_location(value):
        value = str(value).upper().strip()
        return value.replace(" ", "").replace("_", "-").replace("–", "-").replace("—", "-")

    def normalize_text(value):
        return str(value).upper().replace("–", "-").replace("—", "-")

    ALL_STATIONS = set()
    for s in (SSE_ELECT_KWV, SSE_ELECT_SUR, SSE_ELECT_KLBG, SSE_ELECT_WADI, SSE_ELECT_LUR):
        ALL_STATIONS.update(s)
    ALL_STATIONS_SORTED = sorted(ALL_STATIONS, key=len, reverse=True)

    def stations_found_in_text(text):
        text = normalize_text(text)
        found = []
        for station in ALL_STATIONS_SORTED:
            pattern = r"(?<![A-Z0-9])" + re.escape(station) + r"(?![A-Z0-9])"
            if re.search(pattern, text):
                found.append(station)
        return found

    def classify_from_deficiency(deficiency_text):
        text = normalize_text(deficiency_text)
        for section, jurisdiction in SECTION_MAP.items():
            section_pattern = re.escape(section).replace(r"\-", r"\s*[-/]\s*")
            if re.search(section_pattern, text):
                return jurisdiction, "DEFICIENCY-SECTION"
        found_stations = stations_found_in_text(text)
        if not found_stations:
            return None, "NOT FOUND"
        jurisdictions_found = []
        for station in found_stations:
            j = station_map.get(station)
            if j and j not in jurisdictions_found:
                jurisdictions_found.append(j)
        if len(jurisdictions_found) == 1:
            return jurisdictions_found[0], "DEFICIENCY-STATION"
        for i in range(len(found_stations)):
            for j in range(i + 1, len(found_stations)):
                a, b = found_stations[i], found_stations[j]
                if a + "-" + b in SECTION_MAP:
                    return SECTION_MAP[a + "-" + b], "DEFICIENCY-PAIR"
                if b + "-" + a in SECTION_MAP:
                    return SECTION_MAP[b + "-" + a], "DEFICIENCY-PAIR"
        return None, "AMBIGUOUS"

    def classify_record(location, deficiency):
        location = normalize_location(location)
        if location == "":
            j, m = classify_from_deficiency(deficiency)
            return (j, "DEFICIENCY-" + m) if j else (None, "UNCLASSIFIED")
        if location in SECTION_MAP:
            return SECTION_MAP[location], "LOCATION-SECTION"
        if location in station_map:
            return station_map[location], "LOCATION-STATION"
        if re.match(r"^LC[- ]?\d+[A-Z]*$", location):
            if location in LC_ELECT_G_MAPPING:
                return LC_ELECT_G_MAPPING[location], "LC-MAP"
            j, m = classify_from_deficiency(deficiency)
            return (j, "LC-" + m) if j else (None, "LC-NOT-FOUND")
        location_clean = location.replace("/", "-")
        if location_clean in SECTION_MAP:
            return SECTION_MAP[location_clean], "LOCATION-SECTION"
        j, m = classify_from_deficiency(deficiency)
        return (j, "DEFICIENCY-" + m) if j else (None, "UNCLASSIFIED")

    results = df.apply(lambda row: classify_record(row["Location"], row["Deficiencies Noted"]), axis=1)
    df["ELECT_G"] = results.apply(lambda x: x[0])
    df["Classification_Method"] = results.apply(lambda x: x[1])
    df["ELECT_G"] = df["ELECT_G"].fillna("Unclassified")
    if (df["ELECT_G"] == "Unclassified").any() and "Unclassified" not in ELECT_G_ORDER:
        ELECT_G_ORDER = list(ELECT_G_ORDER) + ["Unclassified"]

    total, resolved, pending, no_response = status_counts(df)
    sub = subhead_table(df)

    elect_g = (
        df.groupby(["ELECT_G", "Month"]).size().unstack(fill_value=0)
        .reindex(ELECT_G_ORDER, fill_value=0)
    )
    for m in REPORT_MONTHS:
        if m not in elect_g.columns:
            elect_g[m] = 0
    elect_g["Total"] = elect_g[list(REPORT_MONTHS)].sum(axis=1)
    elect_g["Share"] = (elect_g["Total"] / total * 100) if total else 0

    # ---- draw ----
    fig, ax = new_canvas()
    draw_header(ax, [
        "SAFETY DEFICIENCIES ANALYSIS OF ELECTRICAL /",
        "GENERAL DEPARTMENT",
        _period_title(),
    ])
    draw_kpi_cards(ax, total, resolved, pending, no_response)

    # Sub-head table
    x, y, w, h = 0.15, 3.45, 6.55, 2.48
    draw_box(ax, x, y, w, h)
    draw_rect(ax, x, y + h - 0.28, w, 0.28, NAVY)
    add_text(ax, x + w / 2, y + h - 0.14,
             f"II - CLASSIFICATION SUB HEAD DISTRIBUTION ({_section_period()})",
             9.8, "bold", "white", "center")
    columns = subhead_columns(2.25, 0.72, 0.65, 0.82, with_share=True)
    start_x = x + 0.07
    header_y = y + h - 0.56
    row_height = 0.155
    cx = start_x
    for name, cw in columns:
        draw_rect(ax, cx, header_y - row_height / 2, cw, row_height, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, name, 6.9, "bold", NAVY, "center")
        cx += cw
    sub_display = sub.head(11)
    for r, (sub_head, row) in enumerate(sub_display.iterrows()):
        row_y = header_y - (r + 1) * row_height
        cx = start_x
        values = sub_row_values(sub_head, row, with_share=True)
        for c, (_, cw) in enumerate(columns):
            draw_rect(ax, cx, row_y - row_height / 2, cw, row_height,
                      PALE_YELLOW if r == len(sub_display) - 1 else "white", GRID)
            add_text(ax, cx + (0.035 if c == 0 else cw / 2), row_y, str(values[c]),
                     6.5, "bold" if c == 0 else "normal", TEXT,
                     "left" if c == 0 else "center")
            cx += cw
    row_y = header_y - (len(sub_display) + 1) * row_height
    cx = start_x
    total_values = total_row_values(df, with_share=True)
    for c, (_, cw) in enumerate(columns):
        draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, PALE_YELLOW, GRID)
        add_text(ax, cx + (0.035 if c == 0 else cw / 2), row_y, str(total_values[c]),
                 6.5, "bold", TEXT, "left" if c == 0 else "center")
        cx += cw

    # Bar chart
    x2, y2, w2, h2 = 6.88, 3.45, 6.97, 2.48
    draw_box(ax, x2, y2, w2, h2)
    draw_rect(ax, x2, y2 + h2 - 0.28, w2, 0.28, NAVY)
    add_text(ax, x2 + w2 / 2, y2 + h2 - 0.14,
             f"SUB HEAD WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    plot = sub.head(10)
    left, right = x2 + 2.20, x2 + 5.85
    top, bottom = y2 + h2 - 0.57, y2 + 0.40
    step = (top - bottom) / max(len(plot) - 1, 1)
    maximum = max(plot["Total"].max(), 1) if len(plot) else 1
    for i, (sub_head, row) in enumerate(plot.iterrows()):
        yy = top - i * step
        label = str(sub_head) if len(str(sub_head)) <= 27 else str(sub_head)[:27] + "..."
        add_text(ax, left - 0.08, yy, label, 6.5, "bold", TEXT, "right")
        bar_width = row["Total"] / maximum * (right - left)
        draw_rect(ax, left, yy - 0.055, bar_width, 0.11, NAVY)
        add_text(ax, right + 0.12, yy, str(int(row["Total"])), 7, "bold", TEXT)

    # Jurisdiction table
    x3, y3, w3, h3 = 0.15, 0.50, 6.55, 2.62
    draw_box(ax, x3, y3, w3, h3)
    draw_rect(ax, x3, y3 + h3 - 0.28, w3, 0.28, NAVY)
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.14, "III - CLASSIFICATION SSE/ELECT WISE",
             9.8, "bold", "white", "center")
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.43, "ELECT/G JURISDICTION WISE SUMMARY",
             7.8, "bold", NAVY, "center")
    headers = ["Month"] + ELECT_G_ORDER + ["TOTAL"]
    widths = [0.72, 1.05, 1.05, 1.05, 1.08, 1.05, 0.55]
    start_x = x3 + 0.06
    header_y = y3 + h3 - 0.73
    row_height = 0.34
    cx = start_x
    for header, cw in zip(headers, widths):
        draw_rect(ax, cx, header_y - row_height / 2, cw, row_height, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, header, 5.2, "bold", NAVY, "center")
        cx += cw
    for r, (month_name, month_num) in enumerate(month_pairs()):
        row_y = header_y - (r + 1) * row_height
        cx = start_x
        values = [month_name] + [int(elect_g.loc[j, month_num]) for j in ELECT_G_ORDER] + [int(elect_g[month_num].sum())]
        for c, cw in enumerate(widths):
            draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, "white", GRID)
            add_text(ax, cx + cw / 2, row_y, str(values[c]), 6.2, "normal", TEXT, "center")
            cx += cw
    row_y = header_y - (len(REPORT_MONTHS) + 1) * row_height
    cx = start_x
    values = ["TOTAL"] + [int(elect_g.loc[j, "Total"]) for j in ELECT_G_ORDER] + [int(elect_g["Total"].sum())]
    for c, cw in enumerate(widths):
        draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, PALE_YELLOW, GRID)
        add_text(ax, cx + cw / 2, row_y, str(values[c]), 6.3, "bold", TEXT, "center")
        cx += cw

    # Donut
    x4, y4, w4, h4 = 6.88, 0.50, 6.97, 2.62
    draw_box(ax, x4, y4, w4, h4)
    draw_rect(ax, x4, y4 + h4 - 0.28, w4, 0.28, NAVY)
    add_text(ax, x4 + w4 / 2, y4 + h4 - 0.14,
             f"SSE/ELECT WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    donut_ax = fig.add_axes([0.515, 0.095, 0.205, 0.245])
    donut_ax.set_aspect("equal")
    donut_values = elect_g["Total"].values
    donut_colors = ["#1D4FA3", "#159447", "#D91F2D", "#E58A00", "#56319A", GRAY]
    while len(donut_colors) < len(donut_values):
        donut_colors.append(GRAY)
    if donut_values.sum() > 0:
        donut_ax.pie(donut_values, startangle=90,
                     wedgeprops={"width": 0.35, "edgecolor": "white", "linewidth": 1.2},
                     colors=donut_colors, normalize=True)
    donut_ax.text(0, 0.07, "TOTAL", ha="center", va="center", fontsize=9, fontweight="bold", color=NAVY)
    donut_ax.text(0, -0.11, str(int(donut_values.sum())), ha="center", va="center",
                  fontsize=14, fontweight="bold", color=NAVY)
    donut_ax.axis("off")
    for i, j in enumerate(ELECT_G_ORDER):
        yy = y4 + h4 - 0.56 - i * 0.40
        value = int(elect_g.loc[j, "Total"])
        percentage = (value / total * 100) if total else 0
        draw_rect(ax, x4 + 3.25, yy - 0.065, 0.13, 0.13, donut_colors[i])
        add_text(ax, x4 + 3.48, yy, j, 6.7, "bold", TEXT)
        add_text(ax, x4 + 6.25, yy, f"{value} ({percentage:.2f}%)", 6.7, "bold", TEXT, "right")

    draw_footer(ax, "Reporting Department: Electrical / General , SUR DIVN, CR")
    out = os.path.join(OUTPUT_FOLDER, "ELECT_G_Dashboard_April_May_June_2026.png")
    save_fig(fig, out)
    print(f"ELECT/G → Total:{total} Resolved:{resolved} Pending:{pending} NoResp:{no_response}")
    return out


# ============================================================
# 4. ENGINEERING (supports TARGET_DEN filter)
# ============================================================

def generate_engineering(target_den: Optional[str] = "Sr.DEN/C",
                         excel: str = EXCEL_FILE) -> str:
    """target_den: 'Sr.DEN/C' | 'Sr.DEN/S' | 'DEN/TRACK' | None (full)"""
    _check_assets(excel)

    df = pd.read_excel(excel)
    required = ["Date of Inspection", "Head", "Sub Head", "Location", "Status", "Action by"]
    for column in required:
        if column not in df.columns:
            possible = [c for c in df.columns if "action" in c.lower() and "by" in c.lower()]
            if possible and column == "Action by":
                df = df.rename(columns={possible[0]: "Action by"})
            else:
                raise KeyError(f"Required column '{column}' missing.\nAvailable: {df.columns.tolist()}")

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    for column in ["Head", "Sub Head", "Location", "Status", "Action by"]:
        df[column] = df[column].fillna("").astype(str).str.strip()

    df = df[df["Head"].str.upper().eq("ENGINEERING")].copy()
    if len(df) == 0:
        raise ValueError("No ENGINEERING records found")

    def normalize_location(value):
        if pd.isna(value):
            return ""
        value = str(value).strip().upper()
        return value.replace("–", "-").replace("—", "-").replace("_", "-").replace(" ", "")

    df["Location_Clean"] = df["Location"].apply(normalize_location)
    df["Month"] = df["Date of Inspection"].dt.month
    df = filter_months(df)  # Engineering includes July
    if len(df) == 0:
        raise ValueError("No ENGINEERING records in April–July")

    # ---- jurisdiction sets (kept verbatim) ----
    ADEN_KLBG = {
        "GDGN", "GUR", "HQR", "KLBG", "KUI", "MR", "SBD", "SDB", "SVG", "TJSP", "WADI", "WD", "BBD",
        "WD-SDB-MR", "MR-HQR-KLBG-BBD-SVG", "WADI-SDB", "WADI-KLBG", "KLBG-WADI", "KLBG-SUR", "SUR-KLBG",
        "DUD-KLBG", "KLBG-DUD", "SUR-WADI", "WADI-SUR", "SUR-SBD", "SBD-SUR", "SUR-GUR", "KLBG-TJSP",
        "GDGN-GUR", "GDGN-HQR", "GDGN-KLBG", "GDGN-KUI", "GDGN-MR", "GDGN-SDB", "GDGN-SVG", "GDGN-TJSP",
        "GDGN-WADI", "GUR-GDGN", "GUR-HQR", "GUR-KLBG", "GUR-KUI", "GUR-MR", "GUR-SDB", "GUR-SVG",
        "GUR-TJSP", "GUR-WADI", "HQR-GDGN", "HQR-GUR", "HQR-KLBG", "HQR-KUI", "HQR-MR", "HQR-SDB",
        "HQR-SVG", "HQR-TJSP", "HQR-WADI", "KLBG-GDGN", "KLBG-GUR", "KLBG-HQR", "KLBG-KUI", "KLBG-MR",
        "KLBG-SDB", "KLBG-SVG", "KLBG-TJSP", "KLBG-WADI", "KUI-GDGN", "KUI-GUR", "KUI-HQR", "KUI-KLBG",
        "KUI-MR", "KUI-SDB", "KUI-SVG", "KUI-TJSP", "KUI-WADI", "MR-GDGN", "MR-GUR", "MR-HQR",
        "MR-KLBG", "MR-KUI", "MR-SDB", "MR-SVG", "MR-TJSP", "MR-WADI", "SDB-GDGN", "SDB-GUR",
        "SDB-HQR", "SDB-KLBG", "SDB-KUI", "SDB-MR", "SDB-SVG", "SDB-TJSP", "SDB-WADI", "SVG-GDGN",
        "SVG-GUR", "SVG-HQR", "SVG-KLBG", "SVG-KUI", "SVG-MR", "SVG-SDB", "SVG-TJSP", "SVG-WADI",
        "TJSP-GDGN", "TJSP-GUR", "TJSP-HQR", "TJSP-KLBG", "TJSP-KUI", "TJSP-MR", "TJSP-SDB", "TJSP-SVG",
        "TJSP-WADI", "WADI-GDGN", "WADI-GUR", "WADI-HQR", "WADI-KLBG", "WADI-KUI", "WADI-MR", "WADI-SDB",
        "WADI-SVG", "WADI-TJSP",
    }
    ADEN_S_SUR = {
        "AKOR", "BOT", "DUD", "HG", "NGS", "TKWD", "TLT", "DUD-SUR", "SUR-HG", "BOT-DUD", "NGS-BOT",
        "WADI-TLT", "KWV-DUD", "SUR-BOT", "SUR-NGS",
        "AKOR-BOT", "AKOR-DUD", "AKOR-HG", "AKOR-NGS", "AKOR-TKWD", "AKOR-TLT",
        "BOT-AKOR", "BOT-HG", "BOT-NGS", "BOT-TKWD", "BOT-TLT",
        "DUD-AKOR", "DUD-BOT", "DUD-HG", "DUD-NGS", "DUD-TKWD", "DUD-TLT",
        "HG-AKOR", "HG-BOT", "HG-DUD", "HG-NGS", "HG-TKWD", "HG-TLT",
        "NGS-AKOR", "NGS-BOT", "NGS-DUD", "NGS-HG", "NGS-TKWD", "NGS-TLT",
        "TKWD-AKOR", "TKWD-BOT", "TKWD-DUD", "TKWD-HG", "TKWD-NGS", "TKWD-TLT",
        "TLT-AKOR", "TLT-BOT", "TLT-DUD", "TLT-HG", "TLT-NGS", "TLT-TKWD",
    }
    SR_ADEN_N_SUR = {
        "AAG", "BALE", "MA", "MKPT", "MO", "MVE", "PK", "SUR", "WDS", "WKA",
        "BALE-SUR", "SUR-MO", "SUR-LTRR", "SUR-KEM", "JEUR-SUR", "SUR-DD", "DD-SUR",
        "SUR-MRJ", "SUR-KWV", "KWV-SUR", "SUR-PVR", "SUR-KLBG", "SUR-WADI",
        "AAG-MKPT", "BGVN-SUR", "SUR-BGVN",
    }
    SR_ADEN_KWV_BG = {
        "BGVN", "BLNI", "BRB", "DHS", "JEUR", "JNTR", "KEM", "KWV", "MLM", "PPJ", "PRWD", "WSB", "KEU",
        "JNTR-KEU", "SUR-JEUR", "JEUR-DD", "MLM-BRB", "KWV-DD", "DD-KWV", "KWV-MRJ", "KWV-PVR",
        "KWV-OSA", "KWV-SEI", "KWV-LTRR", "LTRR-KWV", "BGVN-JNTR", "KWV-DHS",
        "BGVN-BLNI", "BGVN-BRB", "BGVN-DHS", "BGVN-JEUR", "BGVN-KEM", "BGVN-KWV", "BGVN-MLM",
        "BGVN-PPJ", "BGVN-WSB", "BLNI-BGVN", "BLNI-BRB", "BLNI-DHS", "BLNI-JEUR", "BLNI-JNTR",
        "BLNI-KEM", "BLNI-KWV", "BLNI-MLM", "BLNI-PPJ", "BLNI-WSB", "BRB-BGVN", "BRB-BLNI",
        "BRB-DHS", "BRB-JEUR", "BRB-JNTR", "BRB-KEM", "BRB-KWV", "BRB-MLM", "BRB-PPJ", "BRB-WSB",
        "DHS-BGVN", "DHS-BLNI", "DHS-BRB", "DHS-JEUR", "DHS-JNTR", "DHS-KEM", "DHS-KWV", "DHS-MLM",
        "DHS-PPJ", "DHS-WSB", "JEUR-BGVN", "JEUR-BLNI", "JEUR-BRB", "JEUR-DHS", "JEUR-JNTR",
        "JEUR-KEM", "JEUR-KWV", "JEUR-MLM", "JEUR-PPJ", "JEUR-WSB", "JNTR-BGVN", "JNTR-BLNI",
        "JNTR-BRB", "JNTR-DHS", "JNTR-JEUR", "JNTR-KEM", "JNTR-KWV", "JNTR-MLM", "JNTR-PPJ",
        "JNTR-WSB", "KEM-BGVN", "KEM-BLNI", "KEM-BRB", "KEM-DHS", "KEM-JEUR", "KEM-JNTR",
        "KEM-KWV", "KEM-MLM", "KEM-PPJ", "KEM-WSB", "KWV-BGVN", "KWV-BLNI", "KWV-BRB", "KWV-DHS",
        "KWV-JEUR", "KWV-JNTR", "KWV-KEM", "KWV-MLM", "KWV-PPJ", "KWV-WSB", "MLM-BGVN", "MLM-BLNI",
        "MLM-BRB", "MLM-DHS", "MLM-JEUR", "MLM-JNTR", "MLM-KEM", "MLM-KWV", "MLM-PPJ", "MLM-WSB",
        "PPJ-BGVN", "PPJ-BLNI", "PPJ-BRB", "PPJ-DHS", "PPJ-JEUR", "PPJ-JNTR", "PPJ-KEM", "PPJ-KWV",
        "PPJ-MLM", "PPJ-WSB", "WSB-BGVN", "WSB-BLNI", "WSB-BRB", "WSB-DHS", "WSB-JEUR", "WSB-JNTR",
        "WSB-KEM", "WSB-KWV", "WSB-MLM", "WSB-PPJ",
    }
    ADEN_PVR = {
        "ARAG", "DLGN", "JTRD", "KVK", "MLB", "PVR", "SGLA", "SGRE",
        "SUR-PVR", "KWV-PVR", "MRJ-PVR", "KWV-DLGN", "KWV-MLB", "KWV-SGRE", "SGRE-KWV",
        "MLB-PVR", "SGRE-KVK",
        "ARAG-DLGN", "ARAG-JTRD", "ARAG-KVK", "ARAG-MLB", "ARAG-PVR", "ARAG-SGLA", "ARAG-SGRE",
        "DLGN-ARAG", "DLGN-JTRD", "DLGN-KVK", "DLGN-MLB", "DLGN-PVR", "DLGN-SGLA", "DLGN-SGRE",
        "JTRD-ARAG", "JTRD-DLGN", "JTRD-KVK", "JTRD-MLB", "JTRD-PVR", "JTRD-SGLA", "JTRD-SGRE",
        "KVK-ARAG", "KVK-DLGN", "KVK-JTRD", "KVK-MLB", "KVK-PVR", "KVK-SGLA", "KVK-SGRE",
        "MLB-ARAG", "MLB-DLGN", "MLB-JTRD", "MLB-KVK", "MLB-PVR", "MLB-SGLA", "MLB-SGRE",
        "PVR-ARAG", "PVR-DLGN", "PVR-JTRD", "PVR-KVK", "PVR-MLB", "PVR-SGLA", "PVR-SGRE",
        "SGLA-ARAG", "SGLA-DLGN", "SGLA-JTRD", "SGLA-KVK", "SGLA-MLB", "SGLA-PVR", "SGLA-SGRE",
        "SGRE-ARAG", "SGRE-DLGN", "SGRE-JTRD", "SGRE-KVK", "SGRE-MLB", "SGRE-PVR", "SGRE-SGLA",
    }
    ADEN_LUR = {
        "BTW", "DKY", "HGL", "LUR", "OSA", "PJR", "SEI", "UMD", "YSI", "KMRD", "MRX", "DRSV",
        "KWV-LUR", "LUR-KWV", "KWV-OSA", "KWV-SEI", "KWV-LTRR", "LTRR-KWV", "SUR-LTRR",
        "HGL-KWV", "KWV-HGL",
        "BTW-DKY", "BTW-HGL", "BTW-LUR", "BTW-OSA", "BTW-PJR", "BTW-SEI", "BTW-YSI",
        "DKY-BTW", "DKY-HGL", "DKY-LUR", "DKY-OSA", "DKY-PJR", "DKY-SEI", "DKY-YSI",
        "HGL-BTW", "HGL-DKY", "HGL-LUR", "HGL-OSA", "HGL-PJR", "HGL-SEI", "HGL-YSI",
        "LUR-BTW", "LUR-DKY", "LUR-HGL", "LUR-OSA", "LUR-PJR", "LUR-SEI", "LUR-YSI",
        "OSA-BTW", "OSA-DKY", "OSA-HGL", "OSA-LUR", "OSA-PJR", "OSA-SEI", "OSA-YSI",
        "PJR-BTW", "PJR-DKY", "PJR-HGL", "PJR-LUR", "PJR-OSA", "PJR-SEI", "PJR-YSI",
        "SEI-BTW", "SEI-DKY", "SEI-HGL", "SEI-LUR", "SEI-OSA", "SEI-PJR", "SEI-YSI",
        "YSI-BTW", "YSI-DKY", "YSI-HGL", "YSI-LUR", "YSI-OSA", "YSI-PJR", "YSI-SEI",
    }

    aden_map: Dict[str, str] = {}
    for loc in ADEN_KLBG:
        aden_map[loc] = "ADEN KLBG"
    for loc in ADEN_S_SUR:
        aden_map[loc] = "ADEN S SUR"
    for loc in SR_ADEN_N_SUR:
        aden_map[loc] = "Sr.ADEN N SUR"
    for loc in SR_ADEN_KWV_BG:
        aden_map[loc] = "Sr.ADEN KWV BG"
    for loc in ADEN_PVR:
        aden_map[loc] = "ADEN/PVR"
    for loc in ADEN_LUR:
        aden_map[loc] = "ADEN/LUR"

    SECTION_PRIORITY = {
        "KWV-LTRR": "ADEN/LUR", "LTRR-KWV": "ADEN/LUR", "KWV-LUR": "ADEN/LUR", "LUR-KWV": "ADEN/LUR",
        "KWV-OSA": "ADEN/LUR", "KWV-SEI": "ADEN/LUR", "KWV-HGL": "ADEN/LUR", "HGL-KWV": "ADEN/LUR",
        "SUR-LTRR": "ADEN/LUR",
        "KWV-PVR": "ADEN/PVR", "MRJ-PVR": "ADEN/PVR", "SUR-PVR": "ADEN/PVR", "MLB-PVR": "ADEN/PVR",
        "SGRE-KVK": "ADEN/PVR", "KWV-DLGN": "ADEN/PVR", "KWV-MLB": "ADEN/PVR", "KWV-SGRE": "ADEN/PVR",
        "SGRE-KWV": "ADEN/PVR",
        "SUR-WADI": "ADEN KLBG", "WADI-SUR": "ADEN KLBG", "SUR-KLBG": "ADEN KLBG", "KLBG-SUR": "ADEN KLBG",
        "SUR-SBD": "ADEN KLBG", "SBD-SUR": "ADEN KLBG", "SUR-GUR": "ADEN KLBG", "KLBG-TJSP": "ADEN KLBG",
        "SUR-BGVN": "Sr.ADEN N SUR", "BGVN-SUR": "Sr.ADEN N SUR", "AAG-MKPT": "Sr.ADEN N SUR",
        "KWV-DHS": "Sr.ADEN KWV BG", "BGVN-JNTR": "Sr.ADEN KWV BG",
    }

    def classify_location_smart(location_clean: str):
        loc = str(location_clean).upper().strip()
        if not loc:
            return None
        if loc in SECTION_PRIORITY:
            return SECTION_PRIORITY[loc]
        tokens = set(loc.replace("-", " ").replace("/", " ").split())
        if "SUR" in tokens or loc == "SUR":
            south_partners = {"TKWD", "HG", "TLT", "AKOR", "NGS", "BOT", "DUD"}
            north_partners = {"BALE", "PK", "PAKNI", "MVE", "MO", "MKPT", "AAG", "WKA", "WDS", "MA"}
            if tokens & south_partners:
                return "ADEN S SUR"
            if tokens & north_partners:
                return "Sr.ADEN N SUR"
            return "Sr.ADEN N SUR"
        if "DUD" in tokens or loc == "DUD":
            klbg_partners = {"KLBG", "KUI", "GDGN", "GUR", "SVG", "WADI", "MR", "HQR", "BBD"}
            ssur_partners = {"BOT", "NGS", "AKOR", "HG", "TKWD", "TLT", "SUR"}
            if tokens & klbg_partners:
                return "ADEN KLBG"
            if tokens & ssur_partners:
                return "ADEN S SUR"
            return "ADEN S SUR"
        if "AKOR" in tokens or loc == "AKOR":
            return "ADEN S SUR"
        if "MKPT" in tokens or "AAG" in tokens:
            kwv_partners = {"KWV", "WKA", "MA", "WDS", "DHS", "KEM", "BLNI"}
            nsur_partners = {"SUR", "BALE", "PK", "MVE", "MO"}
            if tokens & kwv_partners:
                return "Sr.ADEN KWV BG"
            if tokens & nsur_partners:
                return "Sr.ADEN N SUR"
            return "Sr.ADEN N SUR"
        if "KWV" in tokens or loc == "KWV":
            lur_partners = {"LUR", "LTRR", "OSA", "SEI", "HGL", "BTW", "PJR", "DKY", "YSI"}
            pvr_partners = {"PVR", "MLB", "SGLA", "JTRD", "DLGN", "KVK", "SGRE", "ARAG", "MRJ"}
            kwvbg_partners = {"DHS", "KEM", "BLNI", "JH", "PPJ", "WSB", "KEU", "JNTR", "BGVN", "MLM", "BRB", "DD", "WKA", "MA", "WDS"}
            if tokens & lur_partners:
                return "ADEN/LUR"
            if tokens & pvr_partners:
                return "ADEN/PVR"
            if tokens & kwvbg_partners:
                return "Sr.ADEN KWV BG"
            return "Sr.ADEN KWV BG"
        if "WADI" in tokens or loc == "WADI":
            return "ADEN KLBG"
        return aden_map.get(loc)

    df["ADEN"] = df["Location_Clean"].apply(classify_location_smart)
    for location, aden_name in SECTION_PRIORITY.items():
        df.loc[df["Location_Clean"].eq(location), "ADEN"] = aden_name
    df.loc[df["Location_Clean"].eq("MR"), "ADEN"] = "ADEN KLBG"
    df.loc[df["Location_Clean"].eq("SVG"), "ADEN"] = "ADEN KLBG"

    LC_ROUTE_MAPPING = {
        "LC-2": "ADEN/LUR", "LC-4": "ADEN/LUR", "LC-5": "ADEN/LUR", "LC-6": "ADEN/LUR",
        "LC-10": "ADEN/LUR", "LC-34": "ADEN/LUR", "LC-36": "ADEN/LUR", "LC-39": "ADEN/LUR",
        "LC-47": "ADEN/LUR", "LC-55": "ADEN/LUR", "LC-59": "ADEN/LUR",
        "LC-22": "ADEN/PVR", "LC-24": "ADEN/PVR", "LC-31": "ADEN/PVR", "LC-49": "ADEN/PVR", "LC-70": "ADEN/PVR",
        "LC-19": "Sr.ADEN KWV BG", "LC-21": "Sr.ADEN KWV BG", "LC-40": "Sr.ADEN KWV BG", "LC-42": "Sr.ADEN KWV BG",
        "LC-1": "ADEN S SUR", "LC-3": "ADEN KLBG", "LC-60": "ADEN S SUR", "LC-61": "ADEN S SUR",
        "LC-66": "ADEN S SUR", "LC-74": "ADEN S SUR", "LC-82": "ADEN KLBG", "LC-91": "ADEN KLBG",
    }

    def classify_lc_row(row):
        location = str(row.get("Location_Clean", "")).upper()
        sub_head = str(row.get("Sub Head", "")).upper()
        type_inspection = str(row.get("Type of Inspection", "")).upper() if "Type of Inspection" in row.index else ""
        combined = location + " " + sub_head + " " + type_inspection
        if location == "LC-2":
            if "SUR-WADI" in combined or "WADI-SUR" in combined:
                return "ADEN KLBG"
            return "ADEN/LUR"
        if location == "LC-1":
            return "ADEN KLBG"
        return LC_ROUTE_MAPPING.get(location)

    for index, row in df.iterrows():
        if str(row["Location_Clean"]).startswith("LC-"):
            lc_aden = classify_lc_row(row)
            if lc_aden:
                df.at[index, "ADEN"] = lc_aden
    df.loc[df["Location_Clean"].isin(["SUR-SDB", "SBD-SUR", "SUR-SBD", "SBD-SUR"]), "ADEN"] = "ADEN KLBG"

    ALL_ADEN_ORDER = [
        "ADEN KLBG", "ADEN S SUR", "Sr.ADEN N SUR",
        "Sr.ADEN KWV BG", "ADEN/PVR", "ADEN/LUR", "Unclassified",
    ]
    DEN_TO_ADENS = {
        "Sr.DEN/C": ["Sr.ADEN KWV BG", "Sr.ADEN N SUR"],
        "Sr.DEN/S": ["ADEN S SUR", "ADEN KLBG"],
        "DEN/TRACK": ["ADEN/PVR", "ADEN/LUR"],
    }

    if target_den:
        target_clean = target_den.upper().replace(" ", "").replace("/", "")
        df = df[
            df["Action by"].str.upper().str.replace(" ", "", regex=False)
            .str.replace("/", "", regex=False).eq(target_clean)
        ].copy()
        ADEN_ORDER = DEN_TO_ADENS.get(target_den, ALL_ADEN_ORDER[:-1])
    else:
        ADEN_ORDER = ALL_ADEN_ORDER[:-1]

    df["ADEN"] = df["ADEN"].fillna("Unclassified")
    present = df["ADEN"].unique().tolist()
    ADEN_ORDER = [a for a in ADEN_ORDER if a in present]
    if "Unclassified" in present and "Unclassified" not in ADEN_ORDER:
        ADEN_ORDER.append("Unclassified")

    total, resolved, pending, no_response = status_counts(df)
    MONTHS = month_pairs()
    month_numbers = list(REPORT_MONTHS)

    sub = df.groupby(["Sub Head", "Month"]).size().unstack(fill_value=0)
    for _, m in MONTHS:
        if m not in sub.columns:
            sub[m] = 0
    sub["Total"] = sub[month_numbers].sum(axis=1)
    sub["Share"] = (sub["Total"] / total * 100) if total else 0
    sub = sub.sort_values("Total", ascending=False)

    adste = (
        df.groupby(["ADEN", "Month"]).size().unstack(fill_value=0)
        .reindex(ADEN_ORDER, fill_value=0)
    )
    for _, m in MONTHS:
        if m not in adste.columns:
            adste[m] = 0
    adste["Total"] = adste[month_numbers].sum(axis=1)
    adste["Share"] = (adste["Total"] / total * 100) if total else 0

    # ---- draw ----
    fig, ax = new_canvas()
    title = (f"SAFETY DEFICIENCIES ANALYSIS OF ENGINEERING DEPARTMENT - {target_den}"
             if target_den else "SAFETY DEFICIENCIES ANALYSIS OF ENGINEERING DEPARTMENT")
    logo = Image.open(LOGO_FILE).convert("RGBA")
    ax.imshow(logo, extent=[0.08, 0.88, 7.18, 7.94], aspect="auto", zorder=10)
    add_text(ax, 1.02, 7.72, "INDIAN RAILWAYS", 13, "bold", NAVY)
    add_text(ax, 1.02, 7.46, "SOLAPUR DIVISION", 10.5, "bold", NAVY)
    add_text(ax, 1.02, 7.24, "CENTRAL RAILWAY", 10.5, "bold", NAVY)
    add_text(ax, 7, 7.62, title, 11, "bold", NAVY, "center")
    add_text(ax, 7, 7.35, _period_title(), 12.5, "bold", NAVY, "center")
    add_text(ax, 7, 7.13, "Source: SARAL", 8.5, "bold", NAVY, "center")
    train = Image.open(TRAIN_FILE).convert("RGBA")
    ax.imshow(train, extent=[12.25, 13.88, 7.20, 7.83], aspect="auto", zorder=10)

    draw_kpi_cards(ax, total, resolved, pending, no_response, y=6.35)

    # Sub-head table (with July)
    x, y, w, h = 0.15, 3.45, 6.55, 2.68
    draw_box(ax, x, y, w, h)
    draw_rect(ax, x, y + h - 0.28, w, 0.28, NAVY)
    add_text(ax, x + w / 2, y + h - 0.14,
             f"I - CLASSIFICATION SUB HEAD DISTRIBUTION ({_section_period()})",
             9.8, "bold", "white", "center")
    columns = subhead_columns(1.85, 0.72, 0.65, 0.82, with_share=False)
    start_x = x + 0.07
    header_y = y + h - 0.56
    row_height = 0.135
    cx = start_x
    for name, cw in columns:
        draw_rect(ax, cx, header_y - row_height / 2, cw, row_height, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, name, 6.3, "bold", NAVY, "center")
        cx += cw
    sub_display = sub.head(11)
    for r, (sub_head, row) in enumerate(sub_display.iterrows()):
        row_y = header_y - (r + 1) * row_height
        cx = start_x
        values = sub_row_values(sub_head, row, with_share=False)
        for c, (_, cw) in enumerate(columns):
            draw_rect(ax, cx, row_y - row_height / 2, cw, row_height,
                      PALE_YELLOW if r == len(sub_display) - 1 else "white", GRID)
            add_text(ax, cx + (0.025 if c == 0 else cw / 2), row_y, str(values[c]),
                     6.0, "bold" if c == 0 else "normal", TEXT, "left" if c == 0 else "center")
            cx += cw
    row_y = header_y - (len(sub_display) + 1) * row_height
    cx = start_x
    total_values = total_row_values(df, with_share=False)
    for c, (_, cw) in enumerate(columns):
        draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, PALE_YELLOW, GRID)
        add_text(ax, cx + (0.025 if c == 0 else cw / 2), row_y, str(total_values[c]),
                 6.0, "bold", TEXT, "left" if c == 0 else "center")
        cx += cw

    # Bar
    x2, y2, w2, h2 = 6.88, 3.45, 6.97, 2.68
    draw_box(ax, x2, y2, w2, h2)
    draw_rect(ax, x2, y2 + h2 - 0.28, w2, 0.28, NAVY)
    add_text(ax, x2 + w2 / 2, y2 + h2 - 0.14,
             f"SUB HEAD WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    plot = sub.head(10)
    left, right = x2 + 2.20, x2 + 5.85
    top, bottom = y2 + h2 - 0.57, y2 + 0.45
    step = (top - bottom) / max(len(plot) - 1, 1)
    maximum = max(plot["Total"].max(), 1) if len(plot) else 1
    for i, (sub_head, row) in enumerate(plot.iterrows()):
        yy = top - i * step
        label = str(sub_head) if len(str(sub_head)) <= 27 else str(sub_head)[:27] + "..."
        add_text(ax, left - 0.08, yy, label, 6.5, "bold", TEXT, "right")
        bar_width = row["Total"] / maximum * (right - left)
        draw_rect(ax, left, yy - 0.055, bar_width, 0.11, NAVY)
        add_text(ax, right + 0.12, yy, str(int(row["Total"])), 7, "bold", TEXT)

    # ADEN table
    x3, y3, w3, h3 = 0.15, 0.50, 6.55, 2.62
    draw_box(ax, x3, y3, w3, h3)
    draw_rect(ax, x3, y3 + h3 - 0.28, w3, 0.28, NAVY)
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.14, "II - CLASSIFICATION ADEN WISE",
             9.8, "bold", "white", "center")
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.43, "ADEN WISE SUMMARY", 7.8, "bold", NAVY, "center")
    headers = ["Month"] + ADEN_ORDER + ["TOTAL"]
    available_width = 6.40
    month_w, total_w = 0.70, 0.60
    aden_w = (available_width - month_w - total_w) / max(len(ADEN_ORDER), 1)
    widths = [month_w] + [aden_w] * len(ADEN_ORDER) + [total_w]
    start_x = x3 + 0.07
    header_y = y3 + h3 - 0.73
    row_height = 0.30
    cx = start_x
    for header, cw in zip(headers, widths):
        draw_rect(ax, cx, header_y - row_height / 2, cw, row_height, LIGHT_BLUE, GRID)
        font_size = 5.0 if len(ADEN_ORDER) <= 3 else 4.5
        add_text(ax, cx + cw / 2, header_y, header, font_size, "bold", NAVY, "center")
        cx += cw
    for r, (month_name, month_num) in enumerate(MONTHS):
        row_y = header_y - (r + 1) * row_height
        cx = start_x
        values = [month_name]
        for a in ADEN_ORDER:
            values.append(int(adste.loc[a, month_num]) if a in adste.index else 0)
        values.append(int(adste[month_num].sum()) if month_num in adste.columns else 0)
        for c, cw in enumerate(widths):
            draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, "white", GRID)
            add_text(ax, cx + cw / 2, row_y, str(values[c]), 5.5, "normal", TEXT, "center")
            cx += cw
    row_y = header_y - (len(REPORT_MONTHS) + 1) * row_height
    cx = start_x
    values = ["TOTAL"]
    for a in ADEN_ORDER:
        values.append(int(adste.loc[a, "Total"]) if a in adste.index else 0)
    values.append(total)
    for c, cw in enumerate(widths):
        draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, PALE_YELLOW, GRID)
        add_text(ax, cx + cw / 2, row_y, str(values[c]), 5.8, "bold", TEXT, "center")
        cx += cw

    # Donut
    x4, y4, w4, h4 = 6.88, 0.50, 6.97, 2.62
    draw_box(ax, x4, y4, w4, h4)
    draw_rect(ax, x4, y4 + h4 - 0.28, w4, 0.28, NAVY)
    add_text(ax, x4 + w4 / 2, y4 + h4 - 0.14,
             f"ADEN WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    donut_ax = fig.add_axes([0.515, 0.095, 0.205, 0.245])
    donut_ax.set_aspect("equal")
    donut_values = [int(adste.loc[a, "Total"]) if a in adste.index else 0 for a in ADEN_ORDER]
    all_colors = ["#1D4FA3", "#159447", "#D91F2D", "#E58A00", "#56319A", "#008C95", GRAY]
    color_map = dict(zip(ALL_ADEN_ORDER, all_colors))
    donut_colors = [color_map.get(a, GRAY) for a in ADEN_ORDER]
    if sum(donut_values) > 0:
        donut_ax.pie(donut_values, startangle=90,
                     wedgeprops={"width": 0.35, "edgecolor": "white", "linewidth": 1.2},
                     colors=donut_colors, normalize=True)
    donut_ax.text(0, 0.07, "TOTAL", ha="center", va="center", fontsize=9, fontweight="bold", color=NAVY)
    donut_ax.text(0, -0.11, str(total), ha="center", va="center", fontsize=14, fontweight="bold", color=NAVY)
    donut_ax.axis("off")
    for i, aden_name in enumerate(ADEN_ORDER):
        yy = y4 + h4 - 0.56 - i * 0.32
        value = int(adste.loc[aden_name, "Total"]) if aden_name in adste.index else 0
        percentage = (value / total * 100) if total else 0
        draw_rect(ax, x4 + 3.25, yy - 0.065, 0.13, 0.13, donut_colors[i])
        add_text(ax, x4 + 3.48, yy, aden_name, 6.7, "bold", TEXT)
        add_text(ax, x4 + 6.25, yy, f"{value} ({percentage:.2f}%)", 6.7, "bold", TEXT, "right")

    dept_text = (f"Reporting Department: Engineering Dept - {target_den}, SUR DIVN, CR"
                 if target_den else "Reporting Department: Engineering Department, SUR DIVN, CR")
    draw_footer(ax, dept_text, data_as_on="31 JULY 2026")

    if target_den:
        safe_name = target_den.replace("/", "_").replace(" ", "_")
        out = os.path.join(OUTPUT_FOLDER, f"ENGG_Dashboard_{safe_name}.png")
    else:
        out = os.path.join(OUTPUT_FOLDER, "ENGG_Dashboard.png")
    save_fig(fig, out)
    print(f"Engineering ({target_den or 'FULL'}) → Total:{total}")
    return out


# ============================================================
# 5. ELECT / TRD
# ============================================================

def generate_elect_trd(excel: str = EXCEL_FILE) -> str:
    _check_assets(excel)
    df = pd.read_excel(excel)
    required = ["Date of Inspection", "Head", "Sub Head", "Location",
                "Deficiencies Noted", "Status"]
    for c in required:
        if c not in df.columns:
            raise KeyError(f"Required column '{c}' missing.")

    df["Head"] = df["Head"].fillna("").astype(str).str.strip()
    df = df[df["Head"].str.upper().str.replace(" ", "", regex=False)
            .isin(["ELECT/TRD", "ELECT/TRD."])].copy()
    print(f"ELECT/TRD records: {len(df)}")

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    df["Month"] = df["Date of Inspection"].dt.month
    for c in ["Sub Head", "Location", "Deficiencies Noted", "Status"]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df = filter_months(df)
    if len(df) == 0:
        raise ValueError("No ELECT/TRD records in April–June")

    SUR_WADI_TRD = {
        "SUR": "SSE/TRD/SUR", "TKWD": "SSE/TRD/SUR", "HG": "SSE/TRD/SUR", "TLT": "SSE/TRD/SUR",
        "AKOR": "SSE/TRD/SUR", "NGS": "SSE/TRD/DUD", "BOT": "SSE/TRD/DUD", "DUD": "SSE/TRD/DUD",
        "KUI": "SSE/TRD/DUD", "GDGN": "SSE/TRD/DUD", "GUR": "SSE/TRD/DUD", "SVG": "SSE/TRD/DUD",
        "BBD": "JE/TRD/KLBG", "KLBG": "JE/TRD/KLBG", "TJSP": "JE/TRD/KLBG", "HQR": "JE/TRD/KLBG",
        "MR": "JE/TRD/KLBG", "SDB": "JE/TRD/KLBG", "WADI": "JE/TRD/WADI",
    }
    SUR_DD_TRD = {
        "SUR": "SSE/TRD/SUR", "BALE": "SSE/TRD/SUR", "PAKNI": "SSE/TRD/SUR", "PK": "SSE/TRD/SUR",
        "MVE": "SSE/TRD/SUR", "MOHOL": "SSE/TRD/SUR", "MO": "SSE/TRD/SUR",
        "MKPT": "SSE/TRD/KWV", "AAG": "SSE/TRD/KWV", "WKA": "SSE/TRD/KWV", "MADHA": "SSE/TRD/KWV",
        "WDS": "SSE/TRD/KWV", "KWV": "SSE/TRD/KWV", "DHS": "SSE/TRD/KWV", "KEM": "SSE/TRD/KWV",
        "BLNI": "SSE/TRD/KWV", "JEUR": "SSE/TRD/KEU", "PPJ": "SSE/TRD/KEU", "WSB": "SSE/TRD/KEU",
        "KEU": "SSE/TRD/KEU", "JNTR": "SSE/TRD/KEU", "BGVN": "SSE/TRD/KEU", "MLM": "SSE/TRD/KEU",
        "BRB": "SSE/TRD/KEU",
    }
    KWV_LUR_TRD = {
        "SEI": "SSE/TRD/BTW", "BTW": "SSE/TRD/BTW", "PJR": "SSE/TRD/BTW",
        "DRSV": "SSE/TRD/DRSV", "YSI": "SSE/TRD/DRSV", "DKY": "SSE/TRD/DRSV",
        "OSA": "SSE/TRD/LUR", "HGL": "SSE/TRD/LUR", "LUR": "SSE/TRD/LUR",
    }
    KWV_MRJ_TRD = {
        "MLB": "SSE/TRD/PVR", "PVR": "SSE/TRD/PVR", "SGLA": "SSE/TRD/SGLA",
        "JTRD": "SSE/TRD/SGLA", "DLGN": "SSE/TRD/SGLA", "KVK": "SSE/TRD/SGRE",
        "SGRE": "SSE/TRD/SGRE", "ARAG": "SSE/TRD/SGRE",
    }
    elect_trd_map: Dict[str, str] = {}
    for d in (SUR_WADI_TRD, SUR_DD_TRD, KWV_LUR_TRD, KWV_MRJ_TRD):
        for k, v in d.items():
            elect_trd_map.setdefault(k, v)

    section_trd_map = {
        "SUR-WADI": "SSE/TRD/SUR", "WADI-SUR": "SSE/TRD/SUR", "SUR-DD": "SSE/TRD/SUR",
        "DD-SUR": "SSE/TRD/SUR", "KLBG-DUD": "SSE/TRD/DUD", "DUD-KLBG": "SSE/TRD/DUD",
        "KLBG-WADI": "JE/TRD/WADI", "WADI-KLBG": "JE/TRD/WADI", "KWV-LUR": "SSE/TRD/BTW",
        "LUR-KWV": "SSE/TRD/BTW", "SUR-KWV": "SSE/TRD/SUR", "KWV-SUR": "SSE/TRD/KWV",
        "SUR-SDB": "SSE/TRD/SUR", "SDB-SUR": "SSE/TRD/SUR", "SUR-PVR": "SSE/TRD/SUR",
        "PVR-SUR": "SSE/TRD/PVR", "KWV-PVR": "SSE/TRD/PVR", "PVR-KWV": "SSE/TRD/PVR",
        "KWV-MRJ": "SSE/TRD/KWV", "MRJ-KWV": "SSE/TRD/KWV", "KWV-DLGN": "SSE/TRD/SGLA",
        "DLGN-KWV": "SSE/TRD/SGLA", "KWV-SGRE": "SSE/TRD/SGRE", "SGRE-KWV": "SSE/TRD/SGRE",
        "KWV-OSA": "SSE/TRD/LUR", "OSA-KWV": "SSE/TRD/LUR", "KWV-LTRR": "SSE/TRD/LUR",
        "LTRR-KWV": "SSE/TRD/LUR", "SUR-LTRR": "SSE/TRD/SUR", "LTRR-SUR": "SSE/TRD/LUR",
        "HGL-KWV": "SSE/TRD/LUR", "SUR-MO": "SSE/TRD/SUR", "MO-SUR": "SSE/TRD/SUR",
    }
    LC_TRD_MAPPING = {
        "LC-19A": "SSE/TRD/KEU", "LC-40": "SSE/TRD/SUR", "LC-21": "SSE/TRD/KEU", "LC-42": "SSE/TRD/SUR",
        "LC-2": "SSE/TRD/LUR", "LC-4": "SSE/TRD/LUR", "LC-5": "SSE/TRD/LUR", "LC-6": "SSE/TRD/LUR",
        "LC-55": "SSE/TRD/LUR", "LC-59": "SSE/TRD/LUR", "LC-47": "SSE/TRD/LUR", "LC-39": "SSE/TRD/DRSV",
        "LC-34": "SSE/TRD/DRSV", "LC-10": "SSE/TRD/BTW", "LC-36": "SSE/TRD/DRSV",
        "LC-22": "SSE/TRD/PVR", "LC-24": "SSE/TRD/PVR", "LC-70": "SSE/TRD/PVR", "LC-31": "SSE/TRD/SGLA",
        "LC-49": "SSE/TRD/SGRE",
        "LC-74": "SSE/TRD/DUD", "LC-82": "JE/TRD/KLBG", "LC-91": "JE/TRD/WADI", "LC-1": "JE/TRD/WADI",
        "LC-3": "JE/TRD/WADI", "LC-61": "SSE/TRD/SUR", "LC-66": "SSE/TRD/SUR", "LC-60A": "SSE/TRD/SUR",
        "LC-60": "SSE/TRD/SUR",
    }

    def classify_trd(location):
        location = str(location).strip().upper().replace(" ", "").replace("_", "-")
        if not location:
            return np.nan
        if location in elect_trd_map:
            return elect_trd_map[location]
        if location in section_trd_map:
            return section_trd_map[location]
        if location.startswith("LC-"):
            return LC_TRD_MAPPING.get(location, np.nan)
        return np.nan

    df["ELECT_TRD"] = df["Location"].apply(classify_trd)
    df["ELECT_TRD"] = df["ELECT_TRD"].fillna("Unclassified")

    total, resolved, pending, no_response = status_counts(df)
    sub = subhead_table(df)

    TRD_ORDER = [
        "SSE/TRD/SUR", "SSE/TRD/DUD", "JE/TRD/KLBG", "JE/TRD/WADI",
        "SSE/TRD/KWV", "SSE/TRD/KEU", "SSE/TRD/BTW", "SSE/TRD/DRSV",
        "SSE/TRD/LUR", "SSE/TRD/PVR", "SSE/TRD/SGLA", "SSE/TRD/SGRE",
    ]
    if (df["ELECT_TRD"] == "Unclassified").any():
        TRD_ORDER = list(TRD_ORDER) + ["Unclassified"]
    elect_trd = (
        df.groupby(["ELECT_TRD", "Month"]).size().unstack(fill_value=0)
        .reindex(TRD_ORDER, fill_value=0)
    )
    for m in REPORT_MONTHS:
        if m not in elect_trd.columns:
            elect_trd[m] = 0
    elect_trd["Total"] = elect_trd[list(REPORT_MONTHS)].sum(axis=1)
    elect_trd["Share"] = (elect_trd["Total"] / total * 100) if total else 0

    fig, ax = new_canvas()
    draw_header(ax, [
        "SAFETY DEFICIENCIES ANALYSIS OF ELECTRICAL /",
        "TRACTION DISTRIBUTION DEPARTMENT",
        _period_title(),
    ])
    draw_kpi_cards(ax, total, resolved, pending, no_response)

    # Sub-head + bar (same layout as ELECT/G)
    x, y, w, h = 0.15, 3.45, 6.55, 2.48
    draw_box(ax, x, y, w, h)
    draw_rect(ax, x, y + h - 0.28, w, 0.28, NAVY)
    add_text(ax, x + w / 2, y + h - 0.14,
             f"II - CLASSIFICATION SUB HEAD DISTRIBUTION ({_section_period()})",
             9.8, "bold", "white", "center")
    columns = subhead_columns(2.25, 0.72, 0.65, 0.82, with_share=True)
    start_x, header_y, row_height = x + 0.07, y + h - 0.56, 0.165
    cx = start_x
    for name, cw in columns:
        draw_rect(ax, cx, header_y - row_height / 2, cw, row_height, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, name, 7.4, "bold", NAVY, "center")
        cx += cw
    sub_display = sub.head(11)
    for r, (sub_head, row) in enumerate(sub_display.iterrows()):
        row_y = header_y - (r + 1) * row_height
        cx = start_x
        values = sub_row_values(sub_head, row, with_share=True)
        for c, (_, cw) in enumerate(columns):
            draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, "white", GRID)
            add_text(ax, cx + (0.035 if c == 0 else cw / 2), row_y, str(values[c]),
                     7.0, "bold" if c == 0 else "normal", TEXT, "left" if c == 0 else "center")
            cx += cw
    row_y = header_y - (len(sub_display) + 1) * row_height
    cx = start_x
    total_values = total_row_values(df, with_share=True)
    for c, (_, cw) in enumerate(columns):
        draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, PALE_YELLOW, GRID)
        add_text(ax, cx + (0.035 if c == 0 else cw / 2), row_y, str(total_values[c]),
                 7.0, "bold", TEXT, "left" if c == 0 else "center")
        cx += cw

    x2, y2, w2, h2 = 6.88, 3.45, 6.97, 2.48
    draw_box(ax, x2, y2, w2, h2)
    draw_rect(ax, x2, y2 + h2 - 0.28, w2, 0.28, NAVY)
    add_text(ax, x2 + w2 / 2, y2 + h2 - 0.14,
             f"SUB HEAD WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    plot = sub.head(10)
    left, right = x2 + 2.20, x2 + 5.85
    top, bottom = y2 + h2 - 0.57, y2 + 0.40
    step = (top - bottom) / max(len(plot) - 1, 1)
    maximum = max(plot["Total"].max(), 1) if len(plot) else 1
    for i, (sub_head, row) in enumerate(plot.iterrows()):
        yy = top - i * step
        label = sub_head if len(str(sub_head)) <= 27 else str(sub_head)[:27] + "..."
        add_text(ax, left - 0.08, yy, label, 6.5, "bold", TEXT, "right")
        draw_rect(ax, left, yy - 0.055, row["Total"] / maximum * (right - left), 0.11, NAVY)
        add_text(ax, right + 0.12, yy, str(int(row["Total"])), 7, "bold", TEXT)

    # TRD table (compact)
    x3, y3, w3, h3 = 0.15, 0.50, 6.55, 2.62
    draw_box(ax, x3, y3, w3, h3)
    draw_rect(ax, x3, y3 + h3 - 0.28, w3, 0.28, NAVY)
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.14, "III - CLASSIFICATION SSE/TRD WISE",
             9.8, "bold", "white", "center")
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.43, "ELECT/TRD JURISDICTION WISE SUMMARY",
             7.8, "bold", NAVY, "center")
    TRD_SHORT = {j: ("Uncl." if j == "Unclassified" else j.split("/")[-1]) for j in TRD_ORDER}
    headers = ["Month"] + [TRD_SHORT[j] for j in TRD_ORDER] + ["TOTAL"]
    widths = [0.58] + [0.42] * len(TRD_ORDER) + [0.50]
    scale = (w3 - 0.12) / sum(widths)
    widths = [v * scale for v in widths]
    start_x, header_y, row_height = x3 + 0.06, y3 + h3 - 0.73, 0.32
    cx = start_x
    for header, cw in zip(headers, widths):
        draw_rect(ax, cx, header_y - row_height / 2, cw, row_height, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, header, 6.0, "bold", NAVY, "center")
        cx += cw
    for r, (mn, mnum) in enumerate([(MONTH_SHORT.get(m, str(m)), m) for m in REPORT_MONTHS]):
        row_y = header_y - (r + 1) * row_height
        cx = start_x
        values = [mn] + [int(elect_trd.loc[j, mnum]) for j in TRD_ORDER] + [int(elect_trd[mnum].sum())]
        for c, cw in enumerate(widths):
            draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, "white", GRID)
            add_text(ax, cx + cw / 2, row_y, str(values[c]), 6.5,
                     "bold" if c == 0 else "normal", TEXT, "center")
            cx += cw
    row_y = header_y - (len(REPORT_MONTHS) + 1) * row_height
    cx = start_x
    values = ["TOTAL"] + [int(elect_trd.loc[j, "Total"]) for j in TRD_ORDER] + [int(elect_trd["Total"].sum())]
    for c, cw in enumerate(widths):
        draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, PALE_YELLOW, GRID)
        add_text(ax, cx + cw / 2, row_y, str(values[c]), 6.5, "bold", TEXT, "center")
        cx += cw

    # Donut + legend
    x4, y4, w4, h4 = 6.88, 0.50, 6.97, 2.62
    draw_box(ax, x4, y4, w4, h4)
    draw_rect(ax, x4, y4 + h4 - 0.28, w4, 0.28, NAVY)
    add_text(ax, x4 + w4 / 2, y4 + h4 - 0.14,
             f"SSE/TRD WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    donut_values = elect_trd["Total"].values
    donut_colors = [
        "#1D4FA3", "#159447", "#D91F2D", "#E58A00", "#56319A", "#008C95",
        "#B84A9B", "#5E6B73", "#2F7D32", "#A64B00", "#7B3F98", "#336699", GRAY,
    ]
    while len(donut_colors) < len(donut_values):
        donut_colors.append(GRAY)
    donut_ax = fig.add_axes([0.505, 0.105, 0.225, 0.215])
    donut_ax.set_aspect("equal")
    if donut_values.sum() > 0:
        donut_ax.pie(donut_values, startangle=90,
                     wedgeprops={"width": 0.32, "edgecolor": "white", "linewidth": 1.0},
                     colors=donut_colors, normalize=True)
    donut_ax.text(0, 0.13, "TOTAL", ha="center", va="center", fontsize=7.5, fontweight="bold", color=NAVY)
    donut_ax.text(0, -0.12, str(int(donut_values.sum())), ha="center", va="center",
                  fontsize=13.5, fontweight="bold", color=NAVY)
    donut_ax.axis("off")
    legend_x, legend_top = x4 + 3.18, y4 + h4 - 0.55
    for i, jurisdiction in enumerate(TRD_ORDER):
        value = int(elect_trd.loc[jurisdiction, "Total"])
        percentage = (value / total * 100) if total else 0
        col, row = i // 6, i % 6
        lx = legend_x + col * 1.67
        yy = legend_top - row * 0.31
        draw_rect(ax, lx, yy - 0.055, 0.11, 0.11, donut_colors[i])
        add_text(ax, lx + 0.17, yy, jurisdiction, 5.9, "bold", TEXT)
        add_text(ax, lx + 1.18, yy, f"{value}", 6.0, "bold", TEXT, "right")
        add_text(ax, lx + 1.25, yy, f"({percentage:.1f}%)", 5.8, "bold", TEXT)

    draw_footer(ax, "Reporting Department: Electrical / Traction Distribution, SUR DIVN, CR")
    out = os.path.join(OUTPUT_FOLDER, "ELECT_TRD_Safety_Dashboard.png")
    save_fig(fig, out)
    print(f"ELECT/TRD → Total:{total}")
    return out


# ============================================================
# 6. MECHANICAL
# ============================================================

def generate_mechanical(excel: str = EXCEL_FILE) -> str:
    _check_assets(excel)
    df = pd.read_excel(excel)
    required = ["Date of Inspection", "Head", "Sub Head", "Location",
                "Deficiencies Noted", "Status"]
    for c in required:
        if c not in df.columns:
            raise KeyError(f"Missing: {c}")

    df["Head"] = df["Head"].fillna("").astype(str).str.strip()
    head_clean = df["Head"].str.upper().str.replace(r"[\s.]", "", regex=True)
    df = df[head_clean == "MECHANICAL"].copy()
    print(f"Mechanical records: {len(df)}")

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    df["Month"] = df["Date of Inspection"].dt.month
    for c in ["Sub Head", "Location", "Deficiencies Noted", "Status"]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df = filter_months(df)
    if len(df) == 0:
        raise ValueError("No MECHANICAL records in April–June")
    df["MECHANICAL_JURISDICTION"] = "Sr.DME"

    total, resolved, pending, no_response = status_counts(df)
    resolution_rate = (resolved / total * 100) if total else 0.0
    month_totals = {m: int((df["Month"] == m).sum()) for m in REPORT_MONTHS}
    sub = subhead_table(df)

    fig, ax = new_canvas()
    draw_header(ax, [
        "SAFETY DEFICIENCIES ANALYSIS OF",
        "MECHANICAL DEPARTMENT",
        _period_title(),
    ])
    draw_kpi_cards(ax, total, resolved, pending, no_response)

    # Sub-head table
    x, y, w, h = 0.15, 3.45, 6.55, 2.48
    draw_box(ax, x, y, w, h)
    draw_rect(ax, x, y + h - 0.28, w, 0.28, NAVY)
    add_text(ax, x + w / 2, y + h - 0.14,
             f"II - CLASSIFICATION SUB HEAD DISTRIBUTION ({_section_period()})",
             10.2, "bold", "white", "center")
    cols = subhead_columns(2.25, 0.72, 0.65, 0.82, with_share=True)
    start_x, header_y, row_h = x + 0.07, y + h - 0.56, 0.155
    cx = start_x
    for name, cw in cols:
        draw_rect(ax, cx, header_y - row_h / 2, cw, row_h, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, name, 7.2, "bold", NAVY, "center")
        cx += cw
    sub_display = sub.head(11)
    for i, (sub_head, row) in enumerate(sub_display.iterrows()):
        ry = header_y - (i + 1) * row_h
        values = sub_row_values(sub_head, row, with_share=True)
        cx = start_x
        for j, (_, cw) in enumerate(cols):
            draw_rect(ax, cx, ry - row_h / 2, cw, row_h, "white", GRID)
            add_text(ax, cx + (0.035 if j == 0 else cw / 2), ry, str(values[j]),
                     7.0, "bold" if j == 0 else "normal", TEXT, "left" if j == 0 else "center")
            cx += cw
    ry = header_y - (len(sub_display) + 1) * row_h
    totals = total_row_values(df, with_share=True)
    cx = start_x
    for j, (_, cw) in enumerate(cols):
        draw_rect(ax, cx, ry - row_h / 2, cw, row_h, PALE_YELLOW, GRID)
        add_text(ax, cx + (0.035 if j == 0 else cw / 2), ry, str(totals[j]),
                 7.0, "bold", TEXT, "left" if j == 0 else "center")
        cx += cw

    # Bar
    x2, y2, w2, h2 = 6.88, 3.45, 6.97, 2.48
    draw_box(ax, x2, y2, w2, h2)
    draw_rect(ax, x2, y2 + h2 - 0.28, w2, 0.28, NAVY)
    add_text(ax, x2 + w2 / 2, y2 + h2 - 0.14,
             f"SUB HEAD WISE DISTRIBUTION ({_section_period()})", 10.2, "bold", "white", "center")
    plot = sub.head(10)
    left, right = x2 + 2.20, x2 + 5.85
    top, bottom = y2 + h2 - 0.57, y2 + 0.40
    step = (top - bottom) / max(len(plot) - 1, 1)
    maximum = max(plot["Total"].max(), 1)
    for i, (sub_head, row) in enumerate(plot.iterrows()):
        yy = top - i * step
        label = sub_head if len(sub_head) <= 27 else sub_head[:27] + "..."
        add_text(ax, left - 0.08, yy, label, 7.0, "bold", TEXT, "right")
        draw_rect(ax, left, yy - 0.055, row["Total"] / maximum * (right - left), 0.11, NAVY)
        add_text(ax, right + 0.12, yy, str(int(row["Total"])), 7.5, "bold", TEXT)

    # Jurisdiction (single Sr.DME)
    x3, y3, w3, h3 = 0.15, 0.50, 6.55, 2.62
    draw_box(ax, x3, y3, w3, h3)
    draw_rect(ax, x3, y3 + h3 - 0.28, w3, 0.28, NAVY)
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.14, "III - MECHANICAL JURISDICTION WISE",
             10.2, "bold", "white", "center")
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.43, "SR.DME - SOLAPUR DIVISION",
             8.0, "bold", NAVY, "center")
    headers, widths = ["Month", "Sr.DME", "TOTAL"], [1.15, 2.55, 1.15]
    scale = (w3 - 0.12) / sum(widths)
    widths = [v * scale for v in widths]
    start_x, header_y, row_h = x3 + 0.06, y3 + h3 - 0.78, 0.38
    cx = start_x
    for hname, cw in zip(headers, widths):
        draw_rect(ax, cx, header_y - row_h / 2, cw, row_h, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, hname, 8.5, "bold", NAVY, "center")
        cx += cw
    for r, (mn, mnum) in enumerate([(MONTH_SHORT.get(m, str(m)), m) for m in REPORT_MONTHS]):
        ry = header_y - (r + 1) * row_h
        val = int((df["Month"] == mnum).sum())
        values = [mn, val, val]
        cx = start_x
        for j, cw in enumerate(widths):
            draw_rect(ax, cx, ry - row_h / 2, cw, row_h, "white", GRID)
            add_text(ax, cx + cw / 2, ry, str(values[j]), 8.5, "bold", TEXT, "center")
            cx += cw
    ry = header_y - (len(REPORT_MONTHS) + 1) * row_h
    values = ["TOTAL", total, total]
    cx = start_x
    for j, cw in enumerate(widths):
        draw_rect(ax, cx, ry - row_h / 2, cw, row_h, PALE_YELLOW, GRID)
        add_text(ax, cx + cw / 2, ry, str(values[j]), 8.5, "bold", TEXT, "center")
        cx += cw

    # Donut
    x4, y4, w4, h4 = 6.88, 0.50, 6.97, 2.62
    draw_box(ax, x4, y4, w4, h4)
    draw_rect(ax, x4, y4 + h4 - 0.28, w4, 0.28, NAVY)
    add_text(ax, x4 + w4 / 2, y4 + h4 - 0.14,
             f"SR.DME DISTRIBUTION ({_section_period()})", 10.2, "bold", "white", "center")
    donut_ax = fig.add_axes([0.515, 0.105, 0.205, 0.215])
    donut_ax.set_aspect("equal")
    if total > 0:
        donut_ax.pie([total], startangle=90,
                     wedgeprops={"width": 0.32, "edgecolor": "white", "linewidth": 1.0},
                     colors=["#1D4FA3"], normalize=True)
    donut_ax.text(0, 0.13, "TOTAL", ha="center", va="center", fontsize=8.5, fontweight="bold", color=NAVY)
    donut_ax.text(0, -0.15, str(total), ha="center", va="center", fontsize=14, fontweight="bold", color=NAVY)
    donut_ax.axis("off")
    legend_x, legend_top = x4 + 3.35, y4 + h4 - 0.72
    draw_rect(ax, legend_x, legend_top - 0.06, 0.13, 0.13, "#1D4FA3")
    add_text(ax, legend_x + 0.20, legend_top, "Sr.DME ", 8.2, "bold", TEXT)
    add_text(ax, legend_x + 2.25, legend_top, str(total), 8.5, "bold", TEXT, "right")
    add_text(ax, legend_x + 2.35, legend_top, "(100.0%)", 8.0, "bold", TEXT)
    month_info_y = y4 + 1.17
    add_text(ax, legend_x, month_info_y, "MONTH-WISE RECORDS", 8.0, "bold", NAVY)
    for i, (mname, mnum) in enumerate(month_pairs()):
        val = month_totals.get(mnum, 0)
        yy = month_info_y - 0.30 - i * 0.32
        pct = (val / total * 100) if total else 0
        add_text(ax, legend_x, yy, mname, 7.5, "bold", TEXT)
        add_text(ax, legend_x + 1.15, yy, str(val), 7.5, "bold", TEXT, "right")
        add_text(ax, legend_x + 1.28, yy, f"({pct:.1f}%)", 7.2, "bold", TEXT)

    draw_footer(ax, "Reporting Department: Mechanical, SUR DIVN, CR")
    out = os.path.join(OUTPUT_FOLDER, "MECHANICAL_Safety_Dashboard.png")
    save_fig(fig, out)
    print(f"Mechanical → Total:{total}")
    return out


# ============================================================
# 7. OPERATING
# ============================================================

def generate_operating(excel: str = EXCEL_FILE) -> str:
    _check_assets(excel)
    df = pd.read_excel(excel)
    required = ["Date of Inspection", "Head", "Sub Head", "Location",
                "Deficiencies Noted", "Status"]
    for c in required:
        if c not in df.columns:
            raise KeyError(f"Required '{c}' missing.")

    df["Head"] = df["Head"].fillna("").astype(str).str.strip()

    def normalize_head(value):
        value = str(value).upper().strip()
        return re.sub(r"[\s./_-]+", "", value)

    df["_HEAD_NORMALIZED"] = df["Head"].apply(normalize_head)
    OPERATING_HEADS = {"OPERATING", "OPTG", "OPERATINGDEPARTMENT"}
    df = df[df["_HEAD_NORMALIZED"].isin(OPERATING_HEADS)].copy()
    print(f"Operating records: {len(df)}")

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    df["Month"] = df["Date of Inspection"].dt.month
    for c in ["Sub Head", "Location", "Deficiencies Noted", "Status"]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df = filter_months(df)
    if len(df) == 0:
        raise ValueError("No OPERATING records in April–June")

    SUR_WADI_TI = {
        "SUR": "TI/SUR/N", "TKWD": "TI/SUR/S", "HG": "TI/SUR/S", "TLT": "TI/SUR/S",
        "AKOR": "TI/SUR/S", "NGS": "TI/SUR/S", "BOT": "TI/SUR/S",
        "DUD": "TI/KLBG", "KUI": "TI/KLBG", "GDGN": "TI/KLBG", "GUR": "TI/KLBG",
        "SVG": "TI/KLBG", "BBD": "TI/KLBG", "KLBG": "TI/KLBG", "TJSP": "TI/KLBG",
        "HQR": "TI/WD", "MR": "TI/WD", "SDB": "TI/WD", "WADI": "TI/WD",
    }
    SUR_DD_TI = {
        "SUR": "TI/SUR/N", "BALE": "TI/SUR/N", "PAKNI": "TI/SUR/N", "PK": "TI/SUR/N",
        "MVE": "TI/SUR/N", "MOHOL": "TI/SUR/N", "MO": "TI/SUR/N",
        "MKPT": "TI/SUR/N", "AAG": "TI/SUR/N", "WKA": "TI/SUR/N",
        "MADHA": "TI/KWV", "WDS": "TI/KWV", "KWV": "TI/KWV", "DHS": "TI/KWV",
        "KEM": "TI/KWV", "BLNI": "TI/KWV", "JEUR": "TI/KWV",
        "PPJ": "TI/BGVN", "WSB": "TI/BGVN", "KEU": "TI/BGVN", "JNTR": "TI/BGVN",
        "BGVN": "TI/BGVN", "MLM": "TI/BGVN", "BRB": "TI/BGVN",
    }
    KWV_LUR_TI = {
        "SEI": "TI/LUR", "BTW": "TI/LUR", "PJR": "TI/LUR", "DRSV": "TI/LUR",
        "YSI": "TI/LUR", "DKY": "TI/LUR", "OSA": "TI/LUR", "HGL": "TI/LUR", "LUR": "TI/LUR",
    }
    KWV_MRJ_TI = {
        "MLB": "TI/PVR", "PVR": "TI/PVR", "SGLA": "TI/PVR", "JTRD": "TI/PVR",
        "DLGN": "TI/PVR", "KVK": "TI/PVR", "SGRE": "TI/PVR", "ARAG": "TI/PVR",
    }
    operating_ti_map: Dict[str, str] = {}
    for d in (SUR_WADI_TI, SUR_DD_TI, KWV_LUR_TI, KWV_MRJ_TI):
        operating_ti_map.update(d)

    section_ti_map = {
        "SUR-WADI": "TI/SUR/N", "WADI-SUR": "TI/WD", "KLBG-DUD": "TI/KLBG", "DUD-KLBG": "TI/KLBG",
        "KLBG-WADI": "TI/KLBG", "WADI-KLBG": "TI/WD", "SUR-SDB": "TI/WD", "SDB-SUR": "TI/WD",
        "SUR-KWV": "TI/SUR/N", "KWV-SUR": "TI/KWV", "SUR-DD": "TI/SUR/N", "DD-SUR": "TI/SUR/N",
        "KWV-LUR": "TI/LUR", "LUR-KWV": "TI/LUR", "KWV-MRJ": "TI/KWV", "MRJ-KWV": "TI/KWV",
        "KWV-PVR": "TI/PVR", "PVR-KWV": "TI/PVR", "KWV-DLGN": "TI/PVR", "DLGN-KWV": "TI/PVR",
        "KWV-SGRE": "TI/PVR", "SGRE-KWV": "TI/PVR", "KWV-OSA": "TI/LUR", "OSA-KWV": "TI/LUR",
        "HGL-KWV": "TI/LUR", "KWV-HGL": "TI/LUR",
    }
    LC_OPERATING_MAPPING = {
        "LC-31": "TI/PVR", "LC-22": "TI/PVR", "LC-24": "TI/PVR", "LC-70": "TI/PVR", "LC-49": "TI/PVR",
        "LC-60": "TI/WD", "LC-60A": "TI/WD", "LC-61": "TI/SUR/S", "LC-66": "TI/SUR/S",
        "LC-1": "TI/WD", "LC-2": "TI/WD", "LC-3": "TI/WD", "LC-91": "TI/WD",
        "LC-74": "TI/KLBG", "LC-82": "TI/KLBG",
        "LC-10": "TI/LUR", "LC-34": "TI/LUR", "LC-36": "TI/LUR", "LC-39": "TI/LUR",
        "LC-4": "TI/LUR", "LC-5": "TI/LUR", "LC-6": "TI/LUR", "LC-55": "TI/LUR",
        "LC-59": "TI/LUR", "LC-47": "TI/LUR",
        "LC-19A": "TI/BGVN", "LC-21": "TI/BGVN", "LC-40": "TI/SUR/N", "LC-42": "TI/SUR/N",
    }

    def normalize_location(value):
        value = str(value).upper().strip()
        value = re.sub(r"\s+", " ", value).replace("_", "-")
        return value

    def classify_from_text(text):
        text = normalize_location(text)
        if not text:
            return np.nan
        section_pattern = re.search(r"\b([A-Z0-9]+)\s+TO\s+([A-Z0-9]+)\b", text)
        if section_pattern:
            section = f"{section_pattern.group(1)}-{section_pattern.group(2)}"
            if section in section_ti_map:
                return section_ti_map[section]
        section_match = re.search(r"SECTION\s*:\s*([A-Z0-9]+)\s*(?:TO|-)\s*([A-Z0-9]+)", text)
        if section_match:
            section = f"{section_match.group(1)}-{section_match.group(2)}"
            if section in section_ti_map:
                return section_ti_map[section]
        stations = sorted(operating_ti_map.keys(), key=len, reverse=True)
        for station in stations:
            pattern = r"(?<![A-Z0-9])" + re.escape(station) + r"(?![A-Z0-9])"
            if re.search(pattern, text):
                return operating_ti_map[station]
        sections = sorted(section_ti_map.keys(), key=len, reverse=True)
        for section in sections:
            a, b = section.split("-")
            if (re.search(r"(?<![A-Z0-9])" + re.escape(a) + r"(?![A-Z0-9])", text) and
                    re.search(r"(?<![A-Z0-9])" + re.escape(b) + r"(?![A-Z0-9])", text)):
                return section_ti_map[section]
        return np.nan

    def classify_operating(row):
        location = normalize_location(row["Location"])
        deficiency = normalize_location(row["Deficiencies Noted"])
        if location in operating_ti_map:
            return operating_ti_map[location]
        if location in section_ti_map:
            return section_ti_map[location]
        if location.startswith("LC-") or location in LC_OPERATING_MAPPING:
            if location in LC_OPERATING_MAPPING:
                return LC_OPERATING_MAPPING[location]
        location_result = classify_from_text(location)
        if pd.notna(location_result):
            return location_result
        deficiency_result = classify_from_text(deficiency)
        if pd.notna(deficiency_result):
            return deficiency_result
        return np.nan

    df["OPERATING_TI"] = df.apply(classify_operating, axis=1)
    df["OPERATING_TI"] = df["OPERATING_TI"].fillna("Unclassified")
    total, resolved, pending, no_response = status_counts(df)
    sub = subhead_table(df)

    TI_ORDER = ["TI/SUR/N", "TI/SUR/S", "TI/KLBG", "TI/WD", "TI/KWV", "TI/BGVN", "TI/LUR", "TI/PVR"]
    if (df["OPERATING_TI"] == "Unclassified").any():
        TI_ORDER = list(TI_ORDER) + ["Unclassified"]
    operating_ti = (
        df.groupby(["OPERATING_TI", "Month"]).size().unstack(fill_value=0)
        .reindex(TI_ORDER, fill_value=0)
    )
    for m in REPORT_MONTHS:
        if m not in operating_ti.columns:
            operating_ti[m] = 0
    operating_ti["Total"] = operating_ti[list(REPORT_MONTHS)].sum(axis=1)
    operating_ti["Share"] = (operating_ti["Total"] / total * 100) if total else 0

    fig, ax = new_canvas()
    draw_header(ax, [
        "SAFETY DEFICIENCIES ANALYSIS OF",
        "OPERATING DEPARTMENT",
        _period_title(),
    ])
    draw_kpi_cards(ax, total, resolved, pending, no_response)

    # Sub-head + bar (standard)
    x, y, w, h = 0.15, 3.45, 6.55, 2.48
    draw_box(ax, x, y, w, h)
    draw_rect(ax, x, y + h - 0.28, w, 0.28, NAVY)
    add_text(ax, x + w / 2, y + h - 0.14,
             f"II - CLASSIFICATION SUB HEAD DISTRIBUTION ({_section_period()})",
             9.8, "bold", "white", "center")
    columns = subhead_columns(2.25, 0.72, 0.65, 0.82, with_share=True)
    start_x, header_y, row_height = x + 0.07, y + h - 0.56, 0.155
    cx = start_x
    for name, cw in columns:
        draw_rect(ax, cx, header_y - row_height / 2, cw, row_height, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, name, 7.2, "bold", NAVY, "center")
        cx += cw
    sub_display = sub.head(11)
    for r, (sub_head, row) in enumerate(sub_display.iterrows()):
        row_y = header_y - (r + 1) * row_height
        cx = start_x
        values = sub_row_values(sub_head, row, with_share=True)
        for c, (_, cw) in enumerate(columns):
            draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, "white", GRID)
            add_text(ax, cx + (0.035 if c == 0 else cw / 2), row_y, str(values[c]),
                     7.0, "bold" if c == 0 else "normal", TEXT, "left" if c == 0 else "center")
            cx += cw
    row_y = header_y - (len(sub_display) + 1) * row_height
    cx = start_x
    total_values = total_row_values(df, with_share=True)
    for c, (_, cw) in enumerate(columns):
        draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, PALE_YELLOW, GRID)
        add_text(ax, cx + (0.035 if c == 0 else cw / 2), row_y, str(total_values[c]),
                 7.0, "bold", TEXT, "left" if c == 0 else "center")
        cx += cw

    x2, y2, w2, h2 = 6.88, 3.45, 6.97, 2.48
    draw_box(ax, x2, y2, w2, h2)
    draw_rect(ax, x2, y2 + h2 - 0.28, w2, 0.28, NAVY)
    add_text(ax, x2 + w2 / 2, y2 + h2 - 0.14,
             f"SUB HEAD WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    plot = sub.head(10)
    left, right = x2 + 2.20, x2 + 5.85
    top, bottom = y2 + h2 - 0.57, y2 + 0.40
    step = (top - bottom) / max(len(plot) - 1, 1)
    maximum = max(plot["Total"].max(), 1) if len(plot) else 1
    for i, (sub_head, row) in enumerate(plot.iterrows()):
        yy = top - i * step
        label = sub_head if len(str(sub_head)) <= 27 else str(sub_head)[:27] + "..."
        add_text(ax, left - 0.08, yy, label, 7.0, "bold", TEXT, "right")
        draw_rect(ax, left, yy - 0.055, row["Total"] / maximum * (right - left), 0.11, NAVY)
        add_text(ax, right + 0.12, yy, str(int(row["Total"])), 7.5, "bold", TEXT)

    # TI table
    x3, y3, w3, h3 = 0.15, 0.50, 6.55, 2.62
    draw_box(ax, x3, y3, w3, h3)
    draw_rect(ax, x3, y3 + h3 - 0.28, w3, 0.28, NAVY)
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.14, "III - CLASSIFICATION TI WISE",
             9.8, "bold", "white", "center")
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.43, "OPERATING / TI JURISDICTION WISE SUMMARY",
             7.8, "bold", NAVY, "center")
    TI_SHORT = {
        "TI/SUR/N": "SUR/N", "TI/SUR/S": "SUR/S", "TI/KLBG": "KLBG", "TI/WD": "WD",
        "TI/KWV": "KWV", "TI/BGVN": "BGVN", "TI/LUR": "LUR", "TI/PVR": "PVR",
        "Unclassified": "Uncl.",
    }
    headers = ["Month"] + [TI_SHORT.get(j, j) for j in TI_ORDER] + ["TOTAL"]
    widths = [0.62] + [0.65] * len(TI_ORDER) + [0.65]
    scale = (w3 - 0.12) / sum(widths)
    widths = [v * scale for v in widths]
    start_x, header_y, row_height = x3 + 0.06, y3 + h3 - 0.73, 0.30
    cx = start_x
    for header, cw in zip(headers, widths):
        draw_rect(ax, cx, header_y - row_height / 2, cw, row_height, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, header, 6.3, "bold", NAVY, "center")
        cx += cw
    for r, (mn, mnum) in enumerate([(MONTH_SHORT.get(m, str(m)), m) for m in REPORT_MONTHS]):
        row_y = header_y - (r + 1) * row_height
        cx = start_x
        values = [mn] + [int(operating_ti.loc[j, mnum]) for j in TI_ORDER] + [int(operating_ti[mnum].sum())]
        for c, cw in enumerate(widths):
            draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, "white", GRID)
            add_text(ax, cx + cw / 2, row_y, str(values[c]), 7.0,
                     "bold" if c == 0 else "normal", TEXT, "center")
            cx += cw
    row_y = header_y - (len(REPORT_MONTHS) + 1) * row_height
    cx = start_x
    values = ["TOTAL"] + [int(operating_ti.loc[j, "Total"]) for j in TI_ORDER] + [int(operating_ti["Total"].sum())]
    for c, cw in enumerate(widths):
        draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, PALE_YELLOW, GRID)
        add_text(ax, cx + cw / 2, row_y, str(values[c]), 7.0, "bold", TEXT, "center")
        cx += cw

    # Donut
    x4, y4, w4, h4 = 6.88, 0.50, 6.97, 2.62
    draw_box(ax, x4, y4, w4, h4)
    draw_rect(ax, x4, y4 + h4 - 0.28, w4, 0.28, NAVY)
    add_text(ax, x4 + w4 / 2, y4 + h4 - 0.14,
             f"TI WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    donut_values = operating_ti["Total"].values
    donut_colors = ["#1D4FA3", "#159447", "#D91F2D", "#E58A00", "#56319A", "#008C95", "#B84A9B", "#5E6B73", GRAY]
    while len(donut_colors) < len(donut_values):
        donut_colors.append(GRAY)
    donut_ax = fig.add_axes([0.515, 0.105, 0.205, 0.215])
    donut_ax.set_aspect("equal")
    if donut_values.sum() > 0:
        donut_ax.pie(donut_values, startangle=90,
                     wedgeprops={"width": 0.32, "edgecolor": "white", "linewidth": 1.0},
                     colors=donut_colors, normalize=True)
    donut_ax.text(0, 0.075, "TOTAL", ha="center", va="center", fontsize=7.5, fontweight="bold", color=NAVY)
    donut_ax.text(0, -0.095, str(int(donut_values.sum())), ha="center", va="center",
                  fontsize=12, fontweight="bold", color=NAVY)
    donut_ax.axis("off")
    legend_x, legend_top = x4 + 3.18, y4 + h4 - 0.55
    for i, jurisdiction in enumerate(TI_ORDER):
        value = int(operating_ti.loc[jurisdiction, "Total"])
        percentage = (value / total * 100) if total else 0
        col, row = i // 4, i % 4
        lx = legend_x + col * 1.70
        yy = legend_top - row * 0.43
        draw_rect(ax, lx, yy - 0.055, 0.11, 0.11, donut_colors[i])
        add_text(ax, lx + 0.17, yy + 0.045, jurisdiction, 6.4, "bold", TEXT)
        add_text(ax, lx + 0.17, yy - 0.075, str(value), 6.8, "bold", NAVY)
        add_text(ax, lx + 0.52, yy - 0.075, f"({percentage:.1f}%)", 6.3, "bold", TEXT)

    draw_footer(ax, "Reporting Department: Operating, SUR DIVN, CR")
    out = os.path.join(OUTPUT_FOLDER, "OPERATING_Safety_Dashboard.png")
    save_fig(fig, out)
    print(f"Operating → Total:{total}")
    return out


# ============================================================
# 8. COMMERCIAL
# ============================================================

def generate_commercial(excel: str = EXCEL_FILE) -> str:
    _check_assets(excel)
    df = pd.read_excel(excel)
    required = ["Date of Inspection", "Head", "Sub Head", "Location",
                "Deficiencies Noted", "Status"]
    for c in required:
        if c not in df.columns:
            raise KeyError(f"Missing: {c}")

    df["Head"] = df["Head"].fillna("").astype(str).str.strip()
    head_norm = df["Head"].str.upper().str.replace(r"[\s.]", "", regex=True)
    df = df[head_norm == "COMMERCIAL"].copy()
    print(f"COMMERCIAL records: {len(df)}")
    if len(df) == 0:
        raise ValueError("No COMMERCIAL records found")

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    df["Month"] = df["Date of Inspection"].dt.month
    for c in ["Sub Head", "Location", "Deficiencies Noted", "Status"]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df = filter_months(df)
    if len(df) == 0:
        raise ValueError("No COMMERCIAL records in April–June")
    df["JURISDICTION"] = "Sr.DCM"

    total, resolved, pending, no_response = status_counts(df)
    sub = subhead_table(df)
    jur = df.groupby(["JURISDICTION", "Month"]).size().unstack(fill_value=0).reindex(["Sr.DCM"], fill_value=0)
    for m in REPORT_MONTHS:
        if m not in jur.columns:
            jur[m] = 0
    jur["Total"] = jur[list(REPORT_MONTHS)].sum(axis=1)
    grand_total = int(jur.loc["Sr.DCM", "Total"])

    fig, ax = new_canvas()
    draw_header(ax, [
        "SAFETY DEFICIENCIES ANALYSIS OF",
        "COMMERCIAL DEPARTMENT",
        _period_title(),
    ])
    draw_kpi_cards(ax, total, resolved, pending, no_response)

    # Sub-head
    x, y, w, h = 0.15, 3.45, 6.55, 2.48
    draw_box(ax, x, y, w, h)
    draw_rect(ax, x, y + h - 0.28, w, 0.28, NAVY)
    add_text(ax, x + w / 2, y + h - 0.14,
             f"II - CLASSIFICATION SUB HEAD DISTRIBUTION ({_section_period()})",
             9.8, "bold", "white", "center")
    cols = subhead_columns(2.25, 0.72, 0.65, 0.82, with_share=True)
    sx, hy, rh = x + 0.07, y + h - 0.56, 0.155
    cx = sx
    for name, cw in cols:
        draw_rect(ax, cx, hy - rh / 2, cw, rh, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, hy, name, 7.5, "bold", NAVY, "center")
        cx += cw
    for r, (sh, row) in enumerate(sub.head(11).iterrows()):
        ry = hy - (r + 1) * rh
        vals = sub_row_values(sh, row, with_share=True)
        cx = sx
        for c, (_, cw) in enumerate(cols):
            draw_rect(ax, cx, ry - rh / 2, cw, rh, "white", GRID)
            add_text(ax, cx + (0.035 if c == 0 else cw / 2), ry, str(vals[c]),
                     7.2, "bold" if c == 0 else "normal", TEXT, "left" if c == 0 else "center")
            cx += cw
    ry = hy - (len(sub.head(11)) + 1) * rh
    tvals = total_row_values(df, with_share=True)
    cx = sx
    for c, (_, cw) in enumerate(cols):
        draw_rect(ax, cx, ry - rh / 2, cw, rh, PALE_YELLOW, GRID)
        add_text(ax, cx + (0.035 if c == 0 else cw / 2), ry, str(tvals[c]),
                 7.2, "bold", TEXT, "left" if c == 0 else "center")
        cx += cw

    # Bar
    x2, y2, w2, h2 = 6.88, 3.45, 6.97, 2.48
    draw_box(ax, x2, y2, w2, h2)
    draw_rect(ax, x2, y2 + h2 - 0.28, w2, 0.28, NAVY)
    add_text(ax, x2 + w2 / 2, y2 + h2 - 0.14,
             f"SUB HEAD WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    plot = sub.head(10)
    left, right, top, bottom = x2 + 2.20, x2 + 5.85, y2 + h2 - 0.57, y2 + 0.40
    step = (top - bottom) / max(len(plot) - 1, 1)
    mx = max(plot["Total"].max(), 1) if len(plot) else 1
    for i, (sh, row) in enumerate(plot.iterrows()):
        yy = top - i * step
        label = str(sh) if len(str(sh)) <= 27 else str(sh)[:27] + "..."
        add_text(ax, left - 0.08, yy, label, 7.0, "bold", TEXT, "right")
        draw_rect(ax, left, yy - 0.055, row["Total"] / mx * (right - left), 0.11, NAVY)
        add_text(ax, right + 0.12, yy, str(int(row["Total"])), 7.5, "bold", TEXT)

    # Sr.DCM table
    x3, y3, w3, h3 = 0.15, 0.50, 6.55, 2.62
    draw_box(ax, x3, y3, w3, h3)
    draw_rect(ax, x3, y3 + h3 - 0.28, w3, 0.28, NAVY)
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.14, "III - CLASSIFICATION Sr.DCM WISE",
             9.8, "bold", "white", "center")
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.43, "COMMERCIAL DIVISION-WISE SUMMARY",
             8.2, "bold", NAVY, "center")
    headers, widths = ["Month", "Sr.DCM", "TOTAL"], [1.25, 3.85, 1.25]
    sx, hy, rh = x3 + 0.10, y3 + h3 - 0.75, 0.42
    cx = sx
    for hname, cw in zip(headers, widths):
        draw_rect(ax, cx, hy - rh / 2, cw, rh, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, hy, hname, 8.2, "bold", NAVY, "center")
        cx += cw
    for r, (mn, mnum) in enumerate([(MONTH_SHORT.get(m, str(m)), m) for m in REPORT_MONTHS]):
        ry = hy - (r + 1) * rh
        val = int(jur.loc["Sr.DCM", mnum])
        vals = [mn, val, val]
        cx = sx
        for c, cw in enumerate(widths):
            draw_rect(ax, cx, ry - rh / 2, cw, rh, "white", GRID)
            add_text(ax, cx + cw / 2, ry, str(vals[c]), 8.5, "bold", TEXT, "center")
            cx += cw
    ry = hy - (len(REPORT_MONTHS) + 1) * rh
    vals = ["TOTAL", grand_total, grand_total]
    cx = sx
    for c, cw in enumerate(widths):
        draw_rect(ax, cx, ry - rh / 2, cw, rh, PALE_YELLOW, GRID)
        add_text(ax, cx + cw / 2, ry, str(vals[c]), 8.8, "bold", TEXT, "center")
        cx += cw

    # Donut
    x4, y4, w4, h4 = 6.88, 0.50, 6.97, 2.62
    draw_box(ax, x4, y4, w4, h4)
    draw_rect(ax, x4, y4 + h4 - 0.28, w4, 0.28, NAVY)
    add_text(ax, x4 + w4 / 2, y4 + h4 - 0.14,
             f"Sr.DCM WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    donut_ax = fig.add_axes([0.515, 0.105, 0.205, 0.215])
    donut_ax.set_aspect("equal")
    if grand_total > 0:
        donut_ax.pie([grand_total], startangle=90,
                     wedgeprops={"width": 0.32, "edgecolor": "white", "linewidth": 1.0},
                     colors=["#1D4FA3"], normalize=True)
    donut_ax.text(0, 0.10, "TOTAL", ha="center", va="center", fontsize=8, fontweight="bold", color=NAVY)
    donut_ax.text(0, -0.14, str(grand_total), ha="center", va="center",
                  fontsize=13, fontweight="bold", color=NAVY)
    donut_ax.axis("off")
    draw_rect(ax, x4 + 3.25, y4 + 1.55 - 0.06, 0.13, 0.13, "#1D4FA3")
    add_text(ax, x4 + 3.47, y4 + 1.55, "Sr.DCM", 8.5, "bold", TEXT)
    add_text(ax, x4 + 4.45, y4 + 1.55, str(grand_total), 8.5, "bold", TEXT, "right")
    add_text(ax, x4 + 4.60, y4 + 1.55, "(100.0%)", 8.0, "bold", TEXT)

    draw_footer(ax, "Reporting Department: Commercial, SUR DIVN, CR")
    out = os.path.join(OUTPUT_FOLDER, "COMMERCIAL_Safety_Dashboard.png")
    save_fig(fig, out)
    print(f"Commercial → Total:{total}")
    return out


# ============================================================
# 9. ELECT / TRO  (Lobby & Running Room analysis)
# ============================================================

def generate_elect_tro(excel: str = EXCEL_FILE) -> str:
    _check_assets(excel)
    # Prefer default sheet; fall back if "Edited Records" exists
    try:
        df = pd.read_excel(excel, sheet_name="Edited Records")
    except Exception:
        df = pd.read_excel(excel)

    required = ["Date of Inspection", "Head", "Sub Head", "Location",
                "Deficiencies Noted", "Status"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Missing columns:\n" + "\n".join(missing))

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    for col in ["Head", "Sub Head", "Location", "Deficiencies Noted", "Status"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["Head"] = df["Head"].str.upper().str.strip()

    df["Location_Clean"] = (
        df["Location"].str.upper()
        .str.replace(r"[^A-Z0-9/\- ]", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True).str.strip()
    )
    df["Deficiency_Clean"] = (
        df["Deficiencies Noted"].str.upper()
        .str.replace(r"\s+", " ", regex=True).str.strip()
    )
    df["Status_Clean"] = (
        df["Status"].str.upper()
        .str.replace(r"\s+", " ", regex=True).str.strip()
    )

    TRO_HEAD_NAMES = {
        "ELECT/TRO", "ELECT / TRO", "ELECT/TRO.", "ELECTRICAL/TRO",
        "ELECTRICAL / TRO", "TRACTION OPERATION", "TRACTION OPERATING",
    }
    tro_df = df[df["Head"].isin(TRO_HEAD_NAMES)].copy()
    if len(tro_df) == 0:
        tro_df = df[df["Head"].str.contains("TRO", case=False, na=False)].copy()
    print(f"Elect/TrO records found: {len(tro_df)}")
    if len(tro_df) == 0:
        raise ValueError("No Elect/TrO records found in Excel.")
    tro_df["Month"] = tro_df["Date of Inspection"].dt.month
    tro_df = filter_months(tro_df)
    if len(tro_df) == 0:
        raise ValueError("No Elect/TrO records in April–June")

    LOBBY_KEYWORDS = {
        "FSD": ["FSD"],
        "KOISK": ["KOISK", "KIOSK"],
        "BA MACHINE": ["BA MACHINE", "BA MACH", "BREATH ANALYSER", "BREATH ANALYZER"],
        "WALKIE-TALKIE": ["WALKIE-TALKIE", "WALKIE TALKIE", "WALKIE", "TALKIE"],
        "CREW": ["CREW"],
        "RECORDS": ["RECORD", "RECORDS", "REGISTER", "REGISTERS"],
    }
    RUNNING_ROOM_KEYWORDS = {
        "CLEANING": ["CLEANING", "CLEAN", "HYGIENE", "SANITATION"],
        "STAFF": ["STAFF", "MANPOWER", "PERSONNEL"],
        "LINEN": ["LINEN", "BED SHEET", "BED SHEETS", "BLANKET", "PILLOW"],
        "STORAGE": ["STORAGE", "STORE", "CUPBOARD", "RACK"],
        "HARDWARE REQUIRED / MISSING": [
            "HARDWARE", "REQUIRED", "MISSING", "NOT AVAILABLE",
            "NOT PROVIDED", "PROVISION", "EQUIPMENT REQUIRED", "EQUIPMENT MISSING",
        ],
        "FOOD QUALITY": ["FOOD QUALITY", "FOOD", "QUALITY OF FOOD", "MEAL", "MEALS", "MESS"],
    }
    LOCATION_ORDER = ["SUR", "WADI", "LUR", "KWV", "KLBG"]
    LOCATION_COLORS = {
        "SUR": "#123A7A", "WADI": "#11833B", "LUR": "#D97706",
        "KWV": "#56319A", "KLBG": "#C81E2A",
    }

    def classify_location(text):
        text = str(text).upper().strip()
        for loc in ["WADI", "KLBG", "KWV", "LUR", "SUR"]:
            if re.search(rf"\b{loc}\b", text):
                return loc
        return None

    def find_keyword(text, keyword_dict):
        text = str(text).upper()
        for category, keywords in keyword_dict.items():
            if any(kw.upper() in text for kw in keywords):
                return category
        return None

    def create_keyword_table(data, keyword_col, order_dict):
        working = data[data[keyword_col].notna()].copy()
        if working.empty:
            return pd.DataFrame(columns=LOCATION_ORDER + ["Total"])
        table = pd.crosstab(working[keyword_col], working["Lobby/Running Room"])
        for loc in LOCATION_ORDER:
            if loc not in table.columns:
                table[loc] = 0
        table = table[LOCATION_ORDER]
        table["Total"] = table[LOCATION_ORDER].sum(axis=1)
        order = [k for k in order_dict if k in table.index]
        return table.reindex(order)

    tro_df["Lobby/Running Room"] = tro_df["Location_Clean"].apply(classify_location)
    tro_df["Lobby Keyword"] = tro_df["Deficiency_Clean"].apply(lambda x: find_keyword(x, LOBBY_KEYWORDS))
    tro_df["Running Room Keyword"] = tro_df["Deficiency_Clean"].apply(
        lambda x: find_keyword(x, RUNNING_ROOM_KEYWORDS)
    )
    lobby_table = create_keyword_table(tro_df, "Lobby Keyword", LOBBY_KEYWORDS)
    running_room_table = create_keyword_table(tro_df, "Running Room Keyword", RUNNING_ROOM_KEYWORDS)

    total = len(tro_df)
    status = tro_df["Status_Clean"].fillna("").astype(str)
    resolved = int(status.str.contains(r"\bRESOLVED\b", regex=True, na=False).sum())
    no_response = int(status.str.contains("NO RESPONSE", regex=True, na=False).sum())
    pending = int(status.str.contains(r"\bPENDING\b", regex=True, na=False).sum())
    resolution_rate = (resolved / total * 100) if total else 0.0

    # ---- draw (taller canvas for two sections) ----
    TRO_H = 9.0
    fig = plt.figure(figsize=(WIDTH, TRO_H), dpi=170)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(0, TRO_H)
    ax.axis("off")

    logo = Image.open(LOGO_FILE).convert("RGBA")
    ax.imshow(logo, extent=[0.08, 0.88, 8.20, 8.90], aspect="auto", zorder=10)
    add_text(ax, 1.02, 8.72, "INDIAN RAILWAYS", 13, "bold", NAVY)
    add_text(ax, 1.02, 8.48, "SOLAPUR DIVISION", 10.5, "bold", NAVY)
    add_text(ax, 1.02, 8.28, "CENTRAL RAILWAY", 10.5, "bold", NAVY)
    add_text(ax, 7, 8.68, "SAFETY DEFICIENCIES ANALYSIS OF ELECTRICAL /", 16, "bold", NAVY, "center")
    add_text(ax, 7, 8.40, "TRACTION OPERATION DEPARTMENT", 16, "bold", NAVY, "center")
    add_text(ax, 7, 8.12, _period_title(), 13, "bold", NAVY, "center")
    add_text(ax, 7, 7.90, "Source: SARAL", 8.5, "bold", NAVY, "center")
    train = Image.open(TRAIN_FILE).convert("RGBA")
    ax.imshow(train, extent=[12.25, 13.88, 8.22, 8.85], aspect="auto", zorder=10)

    # KPI cards
    cards = [
        ("TOTAL RECORDS", str(total), "100% of Total", NAVY, "■"),
        ("RESOLVED", str(resolved), f"{resolution_rate:.2f}%", GREEN, "✓"),
        ("NO RESPONSE", str(no_response),
         f"{no_response / total * 100:.2f}%" if total else "0.00%", RED, "..."),
        ("PENDING", str(pending),
         f"{pending / total * 100:.2f}%" if total else "0.00%", ORANGE, "P"),
        ("OVERALL RESOLUTION RATE", f"{resolution_rate:.2f}%",
         "(Resolved / Total)", PURPLE, "↗"),
    ]
    for i, (title, value, pct, color, icon) in enumerate(cards):
        x = 0.15 + i * 2.78
        draw_box(ax, x, 7.12, 2.65, 0.72)
        ax.add_patch(Circle((x + 0.39, 7.48), 0.22, facecolor=color, edgecolor="white", linewidth=1.2))
        add_text(ax, x + 0.39, 7.48, icon, 14, "bold", "white", "center")
        add_text(ax, x + 0.72, 7.62, title, 7.0, "bold", color)
        add_text(ax, x + 0.72, 7.38, value, 17, "bold", color)
        add_text(ax, x + 0.72, 7.18, pct, 6.3, "normal", TEXT)

    def _draw_keyword_table(table, x, y, width, height, title):
        draw_box(ax, x, y, width, height)
        title_h = 0.34
        draw_rect(ax, x, y + height - title_h, width, title_h, NAVY)
        add_text(ax, x + width / 2, y + height - title_h / 2, title, 10.2, "bold", "white", "center")
        columns = [
            ("Sub Head / Keyword", 2.65), ("SUR", 0.62), ("WADI", 0.62),
            ("LUR", 0.62), ("KWV", 0.62), ("KLBG", 0.62), ("Total", 0.72),
        ]
        start_x = x + 0.08
        header_y = y + height - title_h - 0.17
        row_h = 0.32
        cx = start_x
        for name, cw in columns:
            draw_rect(ax, cx, header_y - row_h / 2, cw, row_h, LIGHT_BLUE, GRID)
            add_text(ax, cx + cw / 2, header_y, name, 8.0, "bold", NAVY, "center")
            cx += cw
        display = table.head(6) if not table.empty else table
        for i, (keyword, row) in enumerate(display.iterrows()):
            ry = header_y - (i + 1) * row_h
            values = [
                keyword,
                int(row.get("SUR", 0)), int(row.get("WADI", 0)),
                int(row.get("LUR", 0)), int(row.get("KWV", 0)),
                int(row.get("KLBG", 0)), int(row.get("Total", 0)),
            ]
            cx = start_x
            for j, (_, cw) in enumerate(columns):
                draw_rect(ax, cx, ry - row_h / 2, cw, row_h, "white", GRID)
                val = str(values[j])
                if j == 0:
                    if len(val) > 35:
                        val = val[:35] + "..."
                    add_text(ax, cx + 0.04, ry, val, 7.8, "bold", TEXT, "left")
                else:
                    add_text(ax, cx + cw / 2, ry, val, 8.0, "bold", TEXT, "center")
                cx += cw
        total_y = header_y - (len(display) + 1) * row_h
        totals = ["TOTAL"]
        for loc in LOCATION_ORDER:
            totals.append(int(display[loc].sum()) if not display.empty and loc in display.columns else 0)
        totals.append(int(display["Total"].sum()) if not display.empty and "Total" in display.columns else 0)
        cx = start_x
        for j, (_, cw) in enumerate(columns):
            draw_rect(ax, cx, total_y - row_h / 2, cw, row_h, PALE_YELLOW, GRID)
            add_text(ax, cx + (0.04 if j == 0 else cw / 2), total_y, str(totals[j]),
                     8.0, "bold", TEXT, "left" if j == 0 else "center")
            cx += cw

    def _draw_keyword_bar(table, x, y, width, height, title, y_axis_title):
        draw_box(ax, x, y, width, height)
        title_h = 0.34
        draw_rect(ax, x, y + height - title_h, width, title_h, NAVY)
        add_text(ax, x + width / 2, y + height - title_h / 2, title, 10.2, "bold", "white", "center")
        if table.empty:
            add_text(ax, x + width / 2, y + height / 2, "NO KEYWORD DATA FOUND", 10, "bold", RED, "center")
            return
        categories = list(table.index)
        graph_left = x + 0.82
        graph_right = x + width - 0.22
        graph_bottom = y + 0.68
        graph_top = y + height - 0.88
        graph_w = graph_right - graph_left
        graph_h = graph_top - graph_bottom
        max_val = int(table[LOCATION_ORDER].to_numpy().max()) or 1
        if max_val <= 5:
            y_max = 5
        elif max_val <= 10:
            y_max = 10
        elif max_val <= 20:
            y_max = 20
        elif max_val <= 50:
            y_max = int(np.ceil(max_val / 5)) * 5
        else:
            y_max = int(np.ceil(max_val / 10)) * 10
        for tick in np.linspace(0, y_max, 6):
            yy = graph_bottom + (tick / y_max) * graph_h
            ax.plot([graph_left, graph_right], [yy, yy], color=GRID, linewidth=0.55, zorder=1)
            add_text(ax, graph_left - 0.12, yy, int(tick), 7.2, "normal", TEXT, "right")
        ax.plot([graph_left, graph_left], [graph_bottom, graph_top], color=NAVY, linewidth=1)
        ax.plot([graph_left, graph_right], [graph_bottom, graph_bottom], color=NAVY, linewidth=1)
        # Y-axis title (rotated, outside plot area – avoid overlap with bars)
        ax.text(x + 0.12, graph_bottom + graph_h / 2, y_axis_title,
                fontsize=7.5, fontweight="bold", color=NAVY, ha="center", va="center",
                rotation=90, family="DejaVu Sans", clip_on=False)
        n_cat = len(categories)
        n_loc = len(LOCATION_ORDER)
        cat_space = graph_w / max(n_cat, 1)
        bar_w = min(0.18, cat_space * 0.68 / n_loc)
        for ci, cat in enumerate(categories):
            center_x = graph_left + (ci + 0.5) * cat_space
            group_start = center_x - (n_loc * bar_w) / 2
            for li, loc in enumerate(LOCATION_ORDER):
                val = int(table.loc[cat, loc])
                bx = group_start + li * bar_w
                bh = val / y_max * graph_h
                if val > 0:
                    draw_rect(ax, bx, graph_bottom, bar_w * 0.88, bh,
                              LOCATION_COLORS[loc], LOCATION_COLORS[loc])
            label = cat if len(str(cat)) <= 12 else str(cat)[:11] + "…"
            add_text(ax, center_x, graph_bottom - 0.22, label, 6.5, "bold", TEXT, "center")
        # legend
        lx = x + 0.90
        ly = y + 0.28
        for li, loc in enumerate(LOCATION_ORDER):
            draw_rect(ax, lx + li * 1.05, ly - 0.05, 0.12, 0.12, LOCATION_COLORS[loc])
            add_text(ax, lx + li * 1.05 + 0.16, ly, loc, 7.0, "bold", TEXT)

    LOBBY_Y, SECTION_H = 4.25, 2.55
    _draw_keyword_table(lobby_table, 0.15, LOBBY_Y, 6.55, SECTION_H,
                        "I - LOBBY-WISE DEFICIENCY CLASSIFICATION")
    _draw_keyword_bar(lobby_table, 6.98, LOBBY_Y, 6.72, SECTION_H,
                      "LOBBY-WISE DEFICIENCY DISTRIBUTION", "NO. OF LOBBY DEFICIENCIES")

    RUNNING_Y, RUNNING_H = 1.25, 2.55
    _draw_keyword_table(running_room_table, 0.15, RUNNING_Y, 6.55, RUNNING_H,
                        "II - RUNNING ROOM-WISE DEFICIENCY CLASSIFICATION")
    _draw_keyword_bar(running_room_table, 6.98, RUNNING_Y, 6.72, RUNNING_H,
                      "RUNNING ROOM-WISE DEFICIENCY DISTRIBUTION", "NO. OF RUNNING ROOM DEFICIENCIES")

    draw_rect(ax, 0, 0, WIDTH, 0.38, DARK_NAVY)
    add_text(ax, 0.22, 0.19, "Source: SARAL System", 7.7, "normal", "white")
    add_text(ax, 3.25, 0.19, "Reporting Department: Safety Department, SUR DIVN, CR", 7.7, "normal", "white")
    add_text(ax, 8.40, 0.19, "Analysis Type: Elect/TrO Lobby & Running Room", 7.7, "normal", "white")
    add_text(ax, 11.40, 0.19, "Data as on: 30 JUNE 2026", 7.3, "normal", "white")

    out = os.path.join(OUTPUT_FOLDER, "ELECT_TRO_DEDICATED_ANALYSIS.png")
    save_fig(fig, out)
    print(f"ELECT/TRO → Total:{total} Resolved:{resolved} Pending:{pending} NoResp:{no_response}")
    return out


# ============================================================
# 10. S&T (ADSTE) DEPARTMENT
# ============================================================

def generate_snt(excel: str = EXCEL_FILE) -> str:
    _check_assets(excel)
    df = pd.read_excel(excel)

    # Filter S&T / Signal heads if present; otherwise use full file (original S&T script did not filter Head)
    if "Head" in df.columns:
        head_norm = df["Head"].fillna("").astype(str).str.upper().str.replace(r"[\s./_-]+", "", regex=True)
        snt_mask = head_norm.str.contains("S&T|SNT|SIGNAL|TELECOM|TELECOMMUNICATION", regex=True, na=False)
        if snt_mask.any():
            df = df[snt_mask].copy()
            print(f"S&T records after Head filter: {len(df)}")

    if "Date of Inspection" not in df.columns:
        raise KeyError("Missing column: Date of Inspection")
    for col in ["Sub Head", "Location", "Status"]:
        if col not in df.columns:
            raise KeyError(f"Missing column: {col}")

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    df["Month"] = df["Date of Inspection"].dt.month
    for column in ["Sub Head", "Location", "Status"]:
        df[column] = df[column].fillna("").astype(str).str.strip()
    df = filter_months(df)
    if len(df) == 0:
        raise ValueError("No S&T records in April–June")

    KLBG = {
        "WADI", "SDB", "MR", "HQR", "KLBG", "BBD", "SVG", "HHD", "GUR", "KUI",
        "DUD", "BOT", "AKOR", "TLT", "HG", "TJSP",
        "WADI-SUR", "SUR-WADI", "WADI-KLBG", "SUR-SDB", "SUR-HG", "SUR-NGS",
    }
    SUR = {
        "TKWD", "SUR", "BALE", "PK", "MVE", "MO", "MKPT", "AAG", "WKA", "MLB",
        "PVR", "SGLA", "MSDG", "JTRD", "DLGN", "KVK", "SGRE", "ARAG", "MRJ",
        "SUR-KWV", "KWV-MLB", "MLB-MRJ", "TKWD-MKPT",
    }
    KWV_I = {
        "KWV", "DHS", "KEM", "BLNI", "JEUR", "PPJ", "WSB", "KEU", "JNTR", "BGVN",
        "MLM", "BRB", "WDS", "MLM-BRB", "DD-KWV", "BGVN-JNTR", "SUR-KEM",
        "JEUR-SUR", "SUR-JEUR", "WSD", "KWV-BRB",
    }
    KWV_II = {
        "SEI", "BTW", "PJR", "UMD", "YSI", "MRX", "OSA", "HGL", "LUR", "KMRD",
        "LC-10", "LC-34", "LC-6", "LC-22", "LC-31", "LC-42", "LC-61", "LC-70", "LC-91",
        "KWV-LUR", "KWV-SEI", "LC-3", "DRSV", "DKY", "LC-34(DKY)-LUR",
    }

    adste_map: Dict[str, str] = {}
    for location in KLBG:
        adste_map[location] = "ADSTE/KLBG (WADI-HG)"
    for location in SUR:
        adste_map[location] = "ADSTE/SUR (TKWD-MKPT & MLB-MRJ)"
    for location in KWV_I:
        adste_map[location] = "ADSTE/KWV-I (KWV-BRB)"
    for location in KWV_II:
        adste_map[location] = "ADSTE/KWV-II (LC-34(DKY)-LUR)"

    def normalize_loc(v):
        return str(v).upper().strip().replace(" ", "").replace("_", "-")

    df["Location_Norm"] = df["Location"].apply(normalize_loc)
    df["ADSTE"] = df["Location_Norm"].map(adste_map)
    # also try raw Location
    mask = df["ADSTE"].isna()
    df.loc[mask, "ADSTE"] = df.loc[mask, "Location"].map(adste_map)
    df["ADSTE"] = df["ADSTE"].fillna("Unclassified")

    total, resolved, pending, no_response = status_counts(df)
    sub = subhead_table(df)

    ADSTE_ORDER = [
        "ADSTE/KLBG (WADI-HG)",
        "ADSTE/SUR (TKWD-MKPT & MLB-MRJ)",
        "ADSTE/KWV-I (KWV-BRB)",
        "ADSTE/KWV-II (LC-34(DKY)-LUR)",
    ]
    if (df["ADSTE"] == "Unclassified").any():
        ADSTE_ORDER = list(ADSTE_ORDER) + ["Unclassified"]
    adste = (
        df.groupby(["ADSTE", "Month"]).size().unstack(fill_value=0)
        .reindex(ADSTE_ORDER, fill_value=0)
    )
    for m in REPORT_MONTHS:
        if m not in adste.columns:
            adste[m] = 0
    adste["Total"] = adste[list(REPORT_MONTHS)].sum(axis=1)
    adste["Share"] = (adste["Total"] / total * 100) if total else 0

    fig, ax = new_canvas()
    logo = Image.open(LOGO_FILE).convert("RGBA")
    ax.imshow(logo, extent=[0.08, 0.88, 7.18, 7.94], aspect="auto", zorder=10)
    add_text(ax, 1.02, 7.72, "INDIAN RAILWAYS", 13, "bold", NAVY)
    add_text(ax, 1.02, 7.46, "SOLAPUR DIVISION", 10.5, "bold", NAVY)
    add_text(ax, 1.02, 7.24, "CENTRAL RAILWAY", 10.5, "bold", NAVY)
    add_text(ax, 7, 7.62, "SAFETY DEFICIENCIES ANALYSIS OF S&T DEPARTMENT", 17, "bold", NAVY, "center")
    add_text(ax, 7, 7.35, _period_title(), 13, "bold", NAVY, "center")
    add_text(ax, 7, 7.13, "Source: SARAL", 8.5, "bold", NAVY, "center")
    train = Image.open(TRAIN_FILE).convert("RGBA")
    ax.imshow(train, extent=[12.25, 13.88, 7.20, 7.83], aspect="auto", zorder=10)

    draw_kpi_cards(ax, total, resolved, pending, no_response, y=6.35)

    # Sub-head table
    x, y, w, h = 0.15, 3.45, 6.55, 2.68
    draw_box(ax, x, y, w, h)
    draw_rect(ax, x, y + h - 0.28, w, 0.28, NAVY)
    add_text(ax, x + w / 2, y + h - 0.14,
             f"II - CLASSIFICATION SUB HEAD DISTRIBUTION ({_section_period()})",
             9.8, "bold", "white", "center")
    columns = subhead_columns(2.25, 0.72, 0.65, 0.82, with_share=True)
    start_x, header_y, row_height = x + 0.07, y + h - 0.56, 0.155
    cx = start_x
    for name, cw in columns:
        draw_rect(ax, cx, header_y - row_height / 2, cw, row_height, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, name, 6.7, "bold", NAVY, "center")
        cx += cw
    sub_display = sub.head(11)
    for r, (sub_head, row) in enumerate(sub_display.iterrows()):
        row_y = header_y - (r + 1) * row_height
        cx = start_x
        values = sub_row_values(sub_head, row, with_share=True)
        for c, (_, cw) in enumerate(columns):
            draw_rect(ax, cx, row_y - row_height / 2, cw, row_height,
                      PALE_YELLOW if r == len(sub_display) - 1 else "white", GRID)
            add_text(ax, cx + (0.035 if c == 0 else cw / 2), row_y, str(values[c]),
                     6.0 if c == 0 else 6.2, "bold" if c == 0 else "normal", TEXT,
                     "left" if c == 0 else "center")
            cx += cw
    row_y = header_y - (len(sub_display) + 1) * row_height
    cx = start_x
    total_values = total_row_values(df, with_share=True)
    for c, (_, cw) in enumerate(columns):
        draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, PALE_YELLOW, GRID)
        add_text(ax, cx + (0.035 if c == 0 else cw / 2), row_y, str(total_values[c]),
                 6.2, "bold", TEXT, "left" if c == 0 else "center")
        cx += cw

    # Bar
    x2, y2, w2, h2 = 6.88, 3.45, 6.97, 2.68
    draw_box(ax, x2, y2, w2, h2)
    draw_rect(ax, x2, y2 + h2 - 0.28, w2, 0.28, NAVY)
    add_text(ax, x2 + w2 / 2, y2 + h2 - 0.14,
             f"SUB HEAD WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    plot = sub.head(10)
    left, right = x2 + 2.20, x2 + 5.85
    top, bottom = y2 + h2 - 0.57, y2 + 0.45
    step = (top - bottom) / max(len(plot) - 1, 1)
    maximum = max(plot["Total"].max(), 1) if len(plot) else 1
    for i, (sub_head, row) in enumerate(plot.iterrows()):
        yy = top - i * step
        label = sub_head if len(str(sub_head)) <= 27 else str(sub_head)[:27] + "..."
        add_text(ax, left - 0.08, yy, label, 6.3, "bold", TEXT, "right")
        draw_rect(ax, left, yy - 0.055, row["Total"] / maximum * (right - left), 0.11, NAVY)
        add_text(ax, right + 0.12, yy, str(int(row["Total"])), 6.8, "bold", TEXT)

    # ADSTE table
    x3, y3, w3, h3 = 0.15, 0.50, 6.55, 2.62
    draw_box(ax, x3, y3, w3, h3)
    draw_rect(ax, x3, y3 + h3 - 0.28, w3, 0.28, NAVY)
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.14, "III - CLASSIFICATION ADSTE WISE",
             9.8, "bold", "white", "center")
    add_text(ax, x3 + w3 / 2, y3 + h3 - 0.43, "ADSTE WISE SUMMARY", 7.5, "bold", NAVY, "center")
    headers = [
        "Month",
        "ADSTE/KLBG\n(WADI-HG)",
        "ADSTE/SUR\n(TKWD-MKPT &\nMLB-MRJ)",
        "ADSTE/KWV-I\n(KWV-BRB)",
        "ADSTE/KWV-II\n(LC-34(DKY)-LUR)",
        "TOTAL",
    ]
    widths = [0.75, 1.05, 1.50, 1.02, 1.52, 0.52]
    start_x, header_y, row_height = x3 + 0.07, y3 + h3 - 0.73, 0.34
    cx = start_x
    for header, cw in zip(headers, widths):
        draw_rect(ax, cx, header_y - row_height / 2, cw, row_height, LIGHT_BLUE, GRID)
        add_text(ax, cx + cw / 2, header_y, header, 5.7, "bold", NAVY, "center")
        cx += cw
    for r, (month_name, month_num) in enumerate(month_pairs()):
        row_y = header_y - (r + 1) * row_height
        cx = start_x
        values = [
            month_name,
            int(adste.loc[ADSTE_ORDER[0], month_num]),
            int(adste.loc[ADSTE_ORDER[1], month_num]),
            int(adste.loc[ADSTE_ORDER[2], month_num]),
            int(adste.loc[ADSTE_ORDER[3], month_num]),
            int(adste[month_num].sum()),
        ]
        for c, cw in enumerate(widths):
            draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, "white", GRID)
            add_text(ax, cx + cw / 2, row_y, str(values[c]), 6.0, "normal", TEXT, "center")
            cx += cw
    row_y = header_y - (len(REPORT_MONTHS) + 1) * row_height
    cx = start_x
    values = [
        "TOTAL",
        int(adste.loc[ADSTE_ORDER[0], "Total"]),
        int(adste.loc[ADSTE_ORDER[1], "Total"]),
        int(adste.loc[ADSTE_ORDER[2], "Total"]),
        int(adste.loc[ADSTE_ORDER[3], "Total"]),
        int(adste["Total"].sum()),
    ]
    for c, cw in enumerate(widths):
        draw_rect(ax, cx, row_y - row_height / 2, cw, row_height, PALE_YELLOW, GRID)
        add_text(ax, cx + cw / 2, row_y, str(values[c]), 6.1, "bold", TEXT, "center")
        cx += cw

    # Donut
    x4, y4, w4, h4 = 6.88, 0.50, 6.97, 2.62
    draw_box(ax, x4, y4, w4, h4)
    draw_rect(ax, x4, y4 + h4 - 0.28, w4, 0.28, NAVY)
    add_text(ax, x4 + w4 / 2, y4 + h4 - 0.14,
             f"ADSTE WISE DISTRIBUTION ({_section_period()})", 9.8, "bold", "white", "center")
    donut_ax = fig.add_axes([0.535, 0.095, 0.185, 0.245])
    donut_ax.set_aspect("equal")
    donut_values = adste["Total"].values
    donut_colors = ["#1D4FA3", "#159447", "#D91F2D", "#E58A00", GRAY]
    while len(donut_colors) < len(donut_values):
        donut_colors.append(GRAY)
    if donut_values.sum() > 0:
        donut_ax.pie(donut_values, startangle=90,
                     wedgeprops={"width": 0.35, "edgecolor": "white", "linewidth": 1.2},
                     colors=donut_colors, labels=None, autopct=None)
    donut_ax.text(0, 0.07, "TOTAL", ha="center", va="center", fontsize=9.5, fontweight="bold", color=NAVY)
    donut_ax.text(0, -0.11, str(int(total)), ha="center", va="center", fontsize=15, fontweight="bold", color=NAVY)
    donut_ax.axis("off")

    for i, adste_name in enumerate(ADSTE_ORDER):
        yy = y4 + h4 - 0.65 - i * 0.42
        value = int(adste.loc[adste_name, "Total"])
        percentage = (value / total * 100) if total else 0
        draw_rect(ax, x4 + 3.35, yy - 0.065, 0.13, 0.13, donut_colors[i])
        if i == 1:
            add_text(ax, x4 + 3.55, yy + 0.04, "ADSTE/SUR (TKWD-MKPT &", 6.8, "bold", TEXT)
            add_text(ax, x4 + 3.55, yy - 0.10, "MLB-MRJ)", 6.8, "bold", TEXT)
        elif i == 3:
            add_text(ax, x4 + 3.55, yy + 0.04, "ADSTE/KWV-II", 6.8, "bold", TEXT)
            add_text(ax, x4 + 3.55, yy - 0.10, "(LC-34(DKY)-LUR)", 6.8, "bold", TEXT)
        else:
            add_text(ax, x4 + 3.55, yy, adste_name, 6.8, "bold", TEXT)
        add_text(ax, x4 + 6.22, yy, f"{value} ({percentage:.2f}%)", 6.8, "bold", TEXT, "right")

    draw_footer(ax, "Reporting Department: Safety Department, SUR DIVN, CR")
    out = os.path.join(OUTPUT_FOLDER, "SNT_ADSTE_Safety_Dashboard.png")
    save_fig(fig, out)
    print(f"S&T/ADSTE → Total:{total} ADSTE classified:{int(adste['Total'].sum())}")
    return out


# ============================================================
# 11. DISPATCHER – call any / all dashboards
# ============================================================

DASHBOARDS: Dict[str, Callable[..., str]] = {
    "elect_g": generate_elect_g,
    "engg": lambda: generate_engineering(ENGG_DEFAULT_DEN),
    "engg_c": lambda: generate_engineering("Sr.DEN/C"),
    "engg_s": lambda: generate_engineering("Sr.DEN/S"),
    "engg_track": lambda: generate_engineering("DEN/TRACK"),
    "engg_full": lambda: generate_engineering(None),
    "elect_trd": generate_elect_trd,
    "elect_tro": generate_elect_tro,
    "tro": generate_elect_tro,
    "snt": generate_snt,
    "s_and_t": generate_snt,
    "mechanical": generate_mechanical,
    "operating": generate_operating,
    "commercial": generate_commercial,
}


def generate_all(names: Optional[Sequence[str]] = None) -> List[str]:
    """Generate selected (or CONFIG-enabled) dashboards. Returns list of output paths."""
    if names:
        targets = list(names)
    else:
        # Use GENERATE flags from the Easy Settings block at the top
        targets = [k for k, on in GENERATE.items() if on]
        if not targets:
            targets = list(DASHBOARDS.keys())
    seen = set()
    ordered = []
    for n in targets:
        key = n.lower().strip()
        if key not in seen and key in DASHBOARDS:
            seen.add(key)
            ordered.append(key)
    print("Report months:", REPORT_MONTHS, "→", _month_header_list())
    print("Period title :", _period_title())
    print("Generating   :", ", ".join(ordered) if ordered else "(none)")
    results = []
    for name in ordered:
        print("\n" + "=" * 54)
        print(f"  Generating: {name}")
        print("=" * 54)
        try:
            path = DASHBOARDS[name]()
            results.append(path)
        except Exception as exc:
            print(f"[ERROR] {name}: {exc}")
    return results


def main(argv: Optional[Sequence[str]] = None) -> None:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("all", "--all"):
        generate_all()
    else:
        generate_all(argv)


if __name__ == "__main__":
    main()