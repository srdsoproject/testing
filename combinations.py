#!/usr/bin/env python3
"""
Indian Railways – Solapur Division
Unified Safety Deficiencies Dashboard Generator
(Fixed: Logo/Train from GitHub URL + Excel support)
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle
from PIL import Image
import requests

# ============================================================
# ★★★  EASY SETTINGS  ★★★
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE_NAME = "DATA.xlsx"
OUTPUT_FOLDER_NAME = "DEPARTMENT_DASHBOARDS"

# GitHub raw links
LOGO_URL = "https://raw.githubusercontent.com/srdsoproject/testing/main/indian_railways_logo.png"
TRAIN_URL = "https://raw.githubusercontent.com/srdsoproject/testing/main/train.png"

REPORT_MONTHS = [4, 5, 6, 7]
START_DATE = None
END_DATE = None
REPORT_YEAR = 2026

MONTH_LABELS = {
    1: f"January-{REPORT_YEAR}", 2: f"February-{REPORT_YEAR}", 3: f"March-{REPORT_YEAR}",
    4: f"April-{REPORT_YEAR}", 5: f"May-{REPORT_YEAR}", 6: f"June-{REPORT_YEAR}",
    7: f"July-{REPORT_YEAR}", 8: f"August-{REPORT_YEAR}", 9: f"September-{REPORT_YEAR}",
    10: f"October-{REPORT_YEAR}", 11: f"November-{REPORT_YEAR}", 12: f"December-{REPORT_YEAR}",
}
MONTH_SHORT = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}

PERIOD_TITLE = ""
SECTION_PERIOD = ""
DATA_AS_ON = "31 JULY 2026"

GENERATE = {
    "elect_g": True, "engg": True, "engg_s": False, "engg_track": False,
    "engg_full": False, "elect_trd": True, "elect_tro": True, "snt": True,
    "mechanical": True, "operating": True, "commercial": True,
}
ENGG_DEFAULT_DEN = "Sr.DEN/C"

# ============================================================
EXCEL_FILE = os.path.join(BASE_DIR, EXCEL_FILE_NAME)
OUTPUT_FOLDER = os.path.join(BASE_DIR, OUTPUT_FOLDER_NAME)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ---------- Logo / Train download (cached) ----------
_LOGO_PATH = None
_TRAIN_PATH = None

def _download_image(url: str, suffix: str = ".png") -> str:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(r.content)
    tmp.close()
    return tmp.name

def get_logo_path() -> str:
    global _LOGO_PATH
    if _LOGO_PATH is None:
        _LOGO_PATH = _download_image(LOGO_URL)
    return _LOGO_PATH

def get_train_path() -> str:
    global _TRAIN_PATH
    if _TRAIN_PATH is None:
        _TRAIN_PATH = _download_image(TRAIN_URL)
    return _TRAIN_PATH

# ============================================================
def _period_title() -> str:
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
    return [MONTH_LABELS.get(m, str(m)) for m in REPORT_MONTHS]

def _month_short_list() -> List[str]:
    return [MONTH_SHORT.get(m, str(m)) for m in REPORT_MONTHS]

# ============================================================
# COLOURS & DRAWING
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
    for path, desc in [*[(p, p) for p in extra]]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"{desc} not found:\n{path}")

def draw_box(ax, x, y, w, h, facecolor="white", edgecolor=GRID, radius=0.05):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.012,rounding_size={radius}",
        facecolor=facecolor, edgecolor=edgecolor, linewidth=0.8,
    ))

def draw_rect(ax, x, y, w, h, color, edgecolor=None):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=color,
                           edgecolor=edgecolor or color, linewidth=0.5))

def add_text(ax, x, y, text, size=8, weight="normal", color=TEXT, ha="left", va="center"):
    ax.text(x, y, str(text), fontsize=size, fontweight=weight,
            color=color, ha=ha, va=va, family="DejaVu Sans")

def new_canvas():
    fig = plt.figure(figsize=(WIDTH, HEIGHT), dpi=170)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(0, HEIGHT)
    ax.axis("off")
    return fig, ax

def draw_header(ax, title_lines: Sequence[str], subtitle: str = "Source: SARAL"):
    try:
        logo = Image.open(get_logo_path()).convert("RGBA")
        ax.imshow(logo, extent=[0.08, 0.88, 7.18, 7.94], aspect="auto", zorder=10)
    except Exception as e:
        print(f"Logo load failed: {e}")

    add_text(ax, 1.02, 7.72, "INDIAN RAILWAYS", 13, "bold", NAVY)
    add_text(ax, 1.02, 7.46, "SOLAPUR DIVISION", 10.5, "bold", NAVY)
    add_text(ax, 1.02, 7.24, "CENTRAL RAILWAY", 10.5, "bold", NAVY)

    y = 7.62
    for i, line in enumerate(title_lines):
        add_text(ax, 7, y - i * 0.23, line, 16 if i < 2 else 13, "bold", NAVY, "center")
    add_text(ax, 7, 6.98, subtitle, 8.5, "bold", NAVY, "center")

    try:
        train = Image.open(get_train_path()).convert("RGBA")
        ax.imshow(train, extent=[12.25, 13.88, 7.20, 7.83], aspect="auto", zorder=10)
    except Exception as e:
        print(f"Train load failed: {e}")

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

# ---------- baaki helper functions (subhead_columns, month_pairs, status_counts,
# filter_months, subhead_table, save_fig) ORIGINAL se same copy karo ----------
