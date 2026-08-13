#inspectionviewer
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from io import BytesIO
from matplotlib import pyplot as plt
import altair as alt
import re
import random
import string
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from openpyxl.styles import Alignment, Font, Border, Side, NamedStyle
from pandas.api.types import is_numeric_dtype, is_datetime64_any_dtype
import pandas.api.types as ptypes
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode
import pytz
from datetime import datetime, date, timedelta

# =========================================================================
# CONFIG
# =========================================================================
st.set_page_config(
    page_title="S.A.R.A.L Inspection App",
    layout="wide",
    initial_sidebar_state="auto",  # collapsed on mobile by default in many clients
    menu_items={
        "Get Help": "https://wa.me/919022507772",
        "About": "S.A.R.A.L – Safety Abnormality Report & Action List (Solapur Division)",
    },
)

TIMESTAMP_COL_NAME = "Timestamp of Compliance"

# Characters used for the CAPTCHA text. Visually-confusable characters
# (0/O, 1/I/l) are excluded so a genuine human isn't penalised for a
# reasonable misread.
CAPTCHA_CHARS = "".join(c for c in (string.ascii_uppercase + string.digits) if c not in "0O1IL")
CAPTCHA_LENGTH = 5
CAPTCHA_MAX_ATTEMPTS = 5  # lock out after this many wrong CAPTCHA attempts in a session

# =========================================================================
# GLOBAL RESPONSIVE CSS (mobile-first + adaptive)
# =========================================================================
st.markdown(
    """
<style>
/* ---------- Base / Reset ---------- */
html, body, [class*="css"] {
    font-family: 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif !important;
    -webkit-text-size-adjust: 100%;
    text-size-adjust: 100%;
}

/* Make main content breathe on all devices */
.main .block-container {
    padding-top: 1rem !important;
    padding-bottom: 2rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 100% !important;
}

/* Touch-friendly buttons & inputs */
.stButton > button,
.stDownloadButton > button,
div[data-testid="stForm"] button {
    min-height: 44px !important;          /* Apple HIG / Material touch target */
    border-radius: 10px !important;
    font-weight: 600 !important;
    white-space: normal !important;
    word-break: break-word !important;
}

.stTextInput input,
.stTextArea textarea,
.stSelectbox > div,
.stMultiSelect > div {
    min-height: 42px !important;
    font-size: 16px !important;           /* prevents iOS zoom on focus */
}

/* Metrics – stack nicely */
div[data-testid="stMetric"] {
    background: rgba(128,128,128,0.06);
    border-radius: 12px;
    padding: 12px 8px !important;
    text-align: center;
}

/* Expanders more readable */
.streamlit-expanderHeader {
    font-size: 1.05rem !important;
    font-weight: 600 !important;
}

/* Dataframes & tables */
.stDataFrame, .stTable {
    width: 100% !important;
    overflow-x: auto !important;
}

/* AgGrid container – allow horizontal scroll on small screens */
.ag-theme-streamlit, .ag-root-wrapper {
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
}

/* Images */
img {
    max-width: 100% !important;
    height: auto !important;
}

/* Captcha image specifically */
.stImage > img {
    max-width: min(100%, 420px) !important;
    max-height: 320px !important;
    width: auto !important;
    height: auto !important;
    object-fit: contain !important;
    margin: 0 auto;
    display: block;
}
/* Keep markdown header logo small even if CSS class is missed */
img.saral-logo,
.saral-header img {
    height: 48px !important;
    max-height: 48px !important;
    max-width: 120px !important;
    width: auto !important;
    object-fit: contain !important;
}

/* ---------- Header – compact, space-aware ---------- */
.saral-header {
    display: flex;
    align-items: center;
    padding: 8px 0 12px;
    margin-bottom: 12px;
    flex-wrap: wrap;
    gap: 10px;
}
.saral-logo {
    /* Strict size so the logo never dominates the screen */
    height: 48px !important;
    width: auto !important;
    max-height: 48px !important;
    max-width: 120px !important;
    border-radius: 8px;
    margin-right: 14px;
    object-fit: contain;
    flex-shrink: 0;
}
.saral-header-text { flex: 1; min-width: 160px; }
.saral-initiative { margin: 0; font-size: 1.0em; font-weight: 500; color: #4fc3f7; }
.saral-safety { color: #4fc3f7; font-weight: 700; }
.saral-title { margin: 2px 0 0; font-size: 1.75em; font-weight: bold; line-height: 1.15; }
.saral-subtitle { margin: 2px 0 0; font-size: 0.95em; color: #666; }

/* ---------- Footer credit ---------- */
.adaptive-credit {
    display: inline-block;
    padding: 12px 24px;
    background: var(--bg-glass, rgba(255,255,255,0.75));
    border: 2px solid #40c4ff;
    border-radius: 16px;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    box-shadow: 0 6px 20px rgba(64,196,255,0.2);
    font-size: 14px;
    line-height: 1.45;
    max-width: 95vw;
}

/* ---------- Mobile / small tablet (<= 768px) ---------- */
@media (max-width: 768px) {
    .main .block-container {
        padding-left: 0.6rem !important;
        padding-right: 0.6rem !important;
        padding-top: 0.6rem !important;
    }

    /* Force columns to stack */
    div[data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }

    /* Header stacks */
    .saral-header {
        flex-direction: column;
        text-align: center;
        padding: 10px 0 16px;
    }
    .saral-logo {
        margin-right: 0;
        margin-bottom: 6px;
        height: 40px !important;
        max-height: 40px !important;
        max-width: 100px !important;
    }
    .saral-title { font-size: 1.45em; }
    .saral-subtitle { font-size: 0.85em; }
    .saral-initiative { font-size: 0.9em; }
    .saral-header {
        padding: 6px 0 10px;
        margin-bottom: 8px;
    }

    /* Metrics in a tighter grid */
    div[data-testid="stMetric"] {
        margin-bottom: 8px;
    }

    /* Buttons full-width on mobile for easier tapping */
    .stButton > button,
    .stDownloadButton > button {
        width: 100% !important;
    }

    /* Forms */
    div[data-testid="stForm"] {
        padding: 0.5rem !important;
    }

    /* Tabs – larger touch targets */
    button[data-baseweb="tab"] {
        font-size: 0.95rem !important;
        padding: 10px 12px !important;
    }

    /* Sidebar content a bit tighter */
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1rem !important;
    }

    /* Reduce AgGrid height on mobile so user can still scroll the page */
    .ag-theme-streamlit {
        height: 420px !important;
    }

    /* WhatsApp / contact button */
    a button {
        font-size: 16px !important;
        padding: 12px 20px !important;
        width: 100% !important;
        max-width: 320px;
    }

    /* Captcha form columns */
    .stForm [data-testid="column"] {
        width: 100% !important;
    }
}

/* ---------- Very small phones (<= 400px) ---------- */
@media (max-width: 400px) {
    .saral-title { font-size: 1.65em; }
    .main .block-container {
        padding-left: 0.4rem !important;
        padding-right: 0.4rem !important;
    }
    .adaptive-credit {
        padding: 10px 14px;
        font-size: 13px;
    }
}

/* ---------- Tablet (769–1024px) – soft adjustments ---------- */
@media (min-width: 769px) and (max-width: 1024px) {
    .main .block-container {
        padding-left: 1.2rem !important;
        padding-right: 1.2rem !important;
    }
    .saral-title { font-size: 2.2em; }
}

/* ---------- Dark / light adaptive credit (kept from original) ---------- */
@media (prefers-color-scheme: light) {
  :root {
    --text-color: #1a1a1a; --text-highlight: #0d47a1; --text-sub: #1565c0;
    --bg-glass: rgba(255, 255, 255, 0.75); --border-color: #40c4ff;
    --shadow-base: rgba(64, 196, 255, 0.2); --shadow-hover: rgba(64, 196, 255, 0.35);
    --glow-color: rgba(179, 229, 252, 0.9);
  }
}
@media (prefers-color-scheme: dark) {
  :root {
    --text-color: #ffffff; --text-highlight: #e3f2fd; --text-sub: #bbdefb;
    --bg-glass: rgba(15, 25, 45, 0.65); --border-color: #40c4ff;
    --shadow-base: rgba(64, 196, 255, 0.15); --shadow-hover: rgba(64, 196, 255, 0.4);
    --glow-color: rgba(179, 229, 252, 0.95);
  }
}
.adaptive-credit p { margin: 0; color: var(--text-color); font-weight: 500; letter-spacing: 0.5px; }
.adaptive-credit p span.highlight { color: var(--text-highlight); font-weight: 700; }
.adaptive-credit p em { font-style: normal; color: var(--text-sub); }
.adaptive-credit:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 28px var(--shadow-hover), 0 0 30px var(--glow-color);
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================================
# SESSION STATE INITIALIZATION (single pass — no duplicates)
# =========================================================================
DEFAULT_SESSION_STATE = {
    "captcha_text": lambda: None,       # the correct answer for the current image
    "captcha_fail_count": lambda: 0,    # wrong CAPTCHA attempts this session
    "logged_in": lambda: False,
    "user": lambda: None,
    "df": lambda: None,
    "feedback_submitting": lambda: False,
}
for _key, _default_factory in DEFAULT_SESSION_STATE.items():
    if _key not in st.session_state:
        st.session_state[_key] = _default_factory()


# =========================================================================
# IMAGE CAPTCHA
# =========================================================================
def _load_captcha_font(size):
    """Best-effort load of a bundled TrueType font; falls back to PIL's
    built-in bitmap font if none of the common system paths exist."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def generate_captcha_text(length=CAPTCHA_LENGTH):
    return "".join(random.choices(CAPTCHA_CHARS, k=length))


def generate_captcha_image(text, width=240, height=90):
    """Render `text` as a distorted image: randomised per-character
    position/rotation/colour, background noise lines and dots, plus a
    slight blur — enough to defeat simple OCR without being unreadable."""
    bg = (245, 247, 250)
    image = Image.new("RGB", (width, height), color=bg)
    draw = ImageDraw.Draw(image)

    # Background noise lines (drawn first, so text sits on top)
    for _ in range(8):
        xy = [
            (random.randint(0, width), random.randint(0, height)),
            (random.randint(0, width), random.randint(0, height)),
        ]
        draw.line(xy, fill=tuple(random.randint(190, 220) for _ in range(3)), width=2)

    font = _load_captcha_font(46)
    char_width = width // len(text)
    for i, ch in enumerate(text):
        char_img = Image.new("RGBA", (char_width, height), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        color = tuple(random.randint(20, 90) for _ in range(3))
        char_draw.text((char_width * 0.15, height * 0.2), ch, font=font, fill=color)
        angle = random.randint(-28, 28)
        rotated = char_img.rotate(angle, expand=0, resample=Image.BICUBIC)
        x_offset = i * char_width + random.randint(-4, 4)
        y_offset = random.randint(-6, 6)
        image.paste(rotated, (x_offset, y_offset), rotated)

    # Foreground noise dots
    for _ in range(120):
        x, y = random.randint(0, width - 1), random.randint(0, height - 1)
        draw.point((x, y), fill=tuple(random.randint(120, 180) for _ in range(3)))

    image = image.filter(ImageFilter.SMOOTH)
    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf


def new_captcha():
    st.session_state.captcha_text = generate_captcha_text()


if st.session_state.captcha_text is None:
    new_captcha()


# =========================================================================
# LOGIN
# =========================================================================
def login(email, password):
    for user in st.secrets["users"]:
        if user["email"] == email and user["password"] == password:
            return user
    return None


if not st.session_state.logged_in:
    st.title("🔐 Login to S.A.R.A.L")
    st.caption("Safety Abnormality Report & Action List")

    if st.session_state.captcha_fail_count >= CAPTCHA_MAX_ATTEMPTS:
        st.error(
            "🚫 Too many incorrect attempts. Please refresh the page and try again."
        )
        st.stop()

    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("📧 Email", placeholder="your.email@example.com")
        password = st.text_input("🔒 Password", type="password")

        st.markdown("**🤖 Human check:**")
        st.image(
            generate_captcha_image(st.session_state.captcha_text),
            caption="Type the characters shown above (not case-sensitive)",
        )
        captcha_answer = st.text_input(
            "Enter the characters shown in the image",
            key="captcha_input",
            placeholder="e.g. AB3K9",
        )

        # On mobile these stack automatically thanks to CSS; on desktop they stay side-by-side
        btn_col1, btn_col2 = st.columns([2, 1])
        with btn_col1:
            submitted = st.form_submit_button("Login", use_container_width=True)
        with btn_col2:
            refresh_clicked = st.form_submit_button("🔄 New Image", use_container_width=True)

        if refresh_clicked:
            new_captcha()
            st.rerun()

        if submitted:
            given = (captcha_answer or "").strip().upper()
            expected = (st.session_state.captcha_text or "").upper()

            if not given or given != expected:
                st.session_state.captcha_fail_count += 1
                st.error("❌ Incorrect CAPTCHA. Please look at the new image and try again.")
                new_captcha()
                st.rerun()
            else:
                user = login(email, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.session_state.captcha_fail_count = 0
                    new_captcha()  # burn this CAPTCHA so it can't be replayed
                    st.success(f"✅ Welcome, {user['name']}!")
                    st.rerun()
                else:
                    st.session_state.captcha_fail_count += 1
                    st.error("❌ Invalid email or password.")
                    new_captcha()
                    st.rerun()
    st.stop()

# ---------- ACKNOWLEDGMENT ----------
user_id = st.session_state.user["email"]  # use email as unique ID

try:
    ack_df = pd.read_excel("responses.xlsx")
    if "UserID" not in ack_df.columns or "Name" not in ack_df.columns:
        ack_df = pd.DataFrame(columns=["UserID", "Name"])
except FileNotFoundError:
    ack_df = pd.DataFrame(columns=["UserID", "Name"])

user_ack_done = user_id in ack_df["UserID"].values

if not user_ack_done:
    st.title("📢 Pending Deficiencies Compliance")
    with st.expander("⚠️ Pending Deficiencies Notice", expanded=True):
        st.info(
            """
            The compliance of deficiencies of previous dates are pending & needs to be completed immediately.
            I hereby declare that I have read this notice and will ensure compliance.
            """
        )
        with st.form("ack_form"):
            responder_name = st.text_input("✍️ Your Name")
            ack_submitted = st.form_submit_button("Submit Acknowledgment", use_container_width=True)
            if ack_submitted:
                if responder_name.strip():
                    new_entry = {"UserID": user_id, "Name": responder_name.strip()}
                    ack_df = pd.concat([ack_df, pd.DataFrame([new_entry])], ignore_index=True)
                    ack_df.to_excel("responses.xlsx", index=False)
                    st.success(f"✅ Thank you, {responder_name}, for acknowledging.")
                    st.rerun()
                else:
                    st.error("❌ Please enter your name before submitting.")
    st.stop()

# ---------- DISPLAY ALL RESPONSES ----------
st.markdown("### 📝 Responses Received")

try:
    ack_df = pd.read_excel("responses.xlsx")
    if not ack_df.empty:
        st.dataframe(ack_df, use_container_width=True, hide_index=True)
    else:
        st.info("No responses submitted yet.")
except FileNotFoundError:
    st.info("No responses submitted yet.")

if st.button("🗑️ Clear All Responses", key="clear_responses_btn", use_container_width=True):
    pd.DataFrame(columns=["UserID", "Name"]).to_excel("responses.xlsx", index=False)
    st.success("✅ All responses have been cleared.")

# =========================================================================
# GOOGLE SHEETS CONNECTION
# =========================================================================
@st.cache_resource
def connect_to_gsheet():
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    service_account_info = dict(st.secrets["gcp_service_account"])
    if "private_key" in service_account_info:
        service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    SHEET_ID = st.secrets["google_sheets"]["sheet_id"]
    SHEET_NAME = st.secrets["google_sheets"]["sheet_name"]
    return gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)


try:
    sheet = connect_to_gsheet()
    st.sidebar.success("✅ Connected to Google Sheets!")
except Exception as e:
    st.error(f"❌ Could not connect to Google Sheets: {e}")
    st.stop()

# ---------- SIDEBAR ----------
st.sidebar.markdown(f"👤 Logged in as: **{st.session_state.user['name']}**")
st.sidebar.markdown(f"📧 {st.session_state.user['email']}")

if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()

# =========================================================================
# CONSTANT LISTS
# =========================================================================
STATION_LIST = list(dict.fromkeys([
    'BRB', 'MLM', 'BGVN', 'JNTR', 'KEU', 'WSB', 'PPJ', 'JEUR', 'KEM', 'BLNI', 'DHS', 'KWV', 'WDS', 'MA', 'AAG',
    'MKPT', 'MO', 'MVE', 'PK', 'BALE', "SUR", 'TKWD', 'HG', 'TLT', 'AKOR', 'NGS', 'BOT', 'DUD', 'KUI', 'GDGN', 'GUR',
    'HHD', 'SVG', 'BBD', 'TJSP', 'KLBG', 'HQR', 'MR', 'SDB', 'WADI', 'ARAG', 'BLNK', 'SGRE', 'KVK', 'LNP', 'DLGN',
    'JTRD', 'MSDG', 'JVA', 'WSD', 'SGLA', 'PVR', 'MLB', 'SEI', 'BTW', 'PJR', 'DRSV', 'YSI', 'KMRD', 'DKY', 'MRX',
    'OSA', 'HGL', 'LUR', 'NTPC', 'MRJ', 'BHLI'
]))

GATE_LIST = list(dict.fromkeys([
    'LC-19', 'LC-22A', 'LC-25', 'LC-26', 'LC-27C', 'LC-28', 'LC-30', 'LC-31', 'LC-35', 'LC-37', 'LC-40', 'LC-41',
    'LC-43', 'LC-44', 'LC-45', 'LC-46C', 'LC-54', 'LC-61', 'LC-66', 'LC-74', 'LC-76', 'LC-78', 'LC-82', 'LC-1',
    'LC-60A', 'LC-1', 'LC-1 ACC', 'LC-2 ACC', 'LC-91', 'LC-22', 'LC-24', 'LC-32', 'LC-49', 'LC-70',
    'LC-10', 'LC-34', 'LC-36', 'LC-47', 'LC-55', 'LC-59', 'LC-2', 'LC-4', 'LC-42', 'LC-02', 'LC-128', 'LC-63',
    'LC-04', 'LC-67', 'LC-77', 'LC-75', 'LC-64', 'LC-65', 'LC-5', 'LC-6', 'LC-57', 'LC-62', 'LC-39', 'LC-2/C',
    'LC-6/C', 'LC-11', 'LC-03', 'LC-15/C', 'LC-21', 'LC-26-A', 'LC-60'
]))

FOOTPLATE_ROUTE_HIERARCHY = {
    "SUR-DD": ["SUR-KWV", "KWV-DD", "BRB-DD", 'PPJ-WSB', 'SUR-BGVN', 'SUR-MA', 'SUR-PUNE', 'SUR', 'BALE', 'PK', 'MVE', 'MO', 'MKPT', 'WKA', 'ANG', 'MA', 'WDS', 'KWV', 'KEM', 'DHS', 'BLNI', 'JEUR', 'PPJ', 'WSB', 'KEU', 'JNTR', 'BGVN', 'MLM', 'BRB', 'DD', 'LC-40', 'LC-42', 'LC-21', 'LC-19'],
    "SUR-WADI": ["SUR-KLBG", "SDB-WADI", "KLBG-WADI", "BOT-DUD", "DUD-WADI", "SUR-TKWD", 'BBD-KLBG', 'SUR-DUD', 'SUR-SDB', 'SUR', 'TKWD', 'HG', 'TLT', 'AKOR', 'NGS', 'BOT', 'GUR', 'GDGN', 'KUI', 'DUD', 'HDD', 'SVG', 'BBD', 'TJSP', 'KLBG', 'HQR', 'MR', 'SDB', 'WADI', 'LC-1', 'LC-60', 'LC-61', 'LC-66', 'LC-74', 'LC-82', 'LC-91'],
    "LUR-KWV": ["BTW-KWV", "DRSV-KWV", 'SEI-KWV', 'SEI', 'BTW', 'PJR', 'DRSV', 'YSI', 'KMRD', 'DKY', 'MRX', 'OSA', 'HGL', 'LUR'],
    "KWV-MRJ": ["KWV-PVR", 'DLGN-KVK', 'DLGN-PVR', 'PVR-MRJ', 'ARAG', 'BLNK', 'SGRE', 'KVK', 'LNP', 'DLGN', 'JTRD', 'MSDG', 'JVA', 'WSD', 'SGLA', 'PVR', 'MLB'],
    "DD-SUR": ["JEUR-KWV", "BGVN-JNTR", 'BGVN-JNTR', 'DD-KWV', 'KWV-SUR', 'SUR', 'BALE', 'PK', 'MVE', 'MO', 'MKPT', 'WKA', 'ANG', 'MA', 'WDS', 'KWV', 'KEM', 'DHS', 'BLNI', 'JEUR', 'PPJ', 'WSB', 'KEU', 'JNTR', 'BGVN', 'MLM', 'BRB', 'DD'],
    "WADI-SUR": ["WADI-KLBG", "KLBG-SUR", "DUD-HG", 'BOT-NGS', 'WADI-SDB', 'SUR', 'TKWD', 'HG', 'TLT', 'AKOR', 'NGS', 'BOT', 'GUR', 'GDGN', 'KUI', 'DUD', 'HDD', 'SVG', 'BBD', 'KLBG', 'HQR', 'MR', 'SDB', 'WADI'],
    "KWV-LUR": ["KWV-BTW", 'DRSV-LUR', 'SEI', 'BTW', 'PJR', 'DRSV', 'YSI', 'KMRD', 'DKY', 'MRX', 'OSA', 'HGL', 'LUR'],
    "MRJ-KWV": ["PVR-KWV", "SGLA-PVR", 'SGRE-KVK', 'ARAG', 'BLNK', 'SGRE', 'KVK', 'LNP', 'DLGN', 'JTRD', 'MSDG', 'JVA', 'WSD', 'SGLA', 'PVR', 'MLB'],
}

FOOTPLATE_ROUTES = list(FOOTPLATE_ROUTE_HIERARCHY.keys())
ALL_FOOTPLATE_LOCATIONS = FOOTPLATE_ROUTES + [sub for subs in FOOTPLATE_ROUTE_HIERARCHY.values() for sub in subs]
ALL_LOCATIONS = STATION_LIST + GATE_LIST + ALL_FOOTPLATE_LOCATIONS

HEAD_LIST = ["", "ELECT/TRD", "ELECT/G", "ELECT/TRO", "SIGNAL & TELECOM", "OPTG", "MECHANICAL",
             "ENGINEERING", "COMMERCIAL", 'PERSONNEL', 'SECURITY', "FINANCE", "MEDICAL", "STORE"]

SUBHEAD_LIST = {
    "ELECT/TRD": ["T/W WAGON", "TSS/SP/SSP", "OHE SECTION", "OHE STATION", "MISC"],
    "ELECT/G": ["TL/AC COACH", "POWER/PANTRY CAR", "WIRING/EQUIPMENT", "UPS", "AC", "DG", "SOLAR LIGHT", "MISC"],
    "ELECT/TRO": ["LOCO DEFECTS", "RUNNING ROOM DEFICIENCIES", "LOBBY DEFICIENCIES", "LRD RELATED", "PERSONAL STORE", "PR RELATED", "CMS", "FSD", "MISC"],
    "MECHANICAL": ['C&W RELATED', "DEMU RELATED", "VANDE BHARAT RELATED", "MISC", 'MECHANICAL RELATED', 'HABD'],
    "SIGNAL & TELECOM": ["S&T ASSETS", 'WALKIE-TALKIE/PHONE', 'VDU/BPAC/BLOCK INST./PANEL', 'PASSENGER AMENITIES', 'SIGNAL RELATED', 'P&C', 'TRACK CIRCUIT', 'RELAY ROOM', 'MISC'],
    "OPTG": ["SWR/CSR/CSL/TWRD", "STATION RECORDS", "STATION DEFICIENCIES", "TRAIN O/P RELATED", "LC GATE DEFICIENCIES", "CIRCULAR/KNOWLEDGE/STAFF", "SIGNAL EXCHANGE", 'WALKIE-TALKIE/PHONE', "SM OFFICE DEFICIENCIES/ASSETS", "MISC"],
    "ENGINEERING": ["IOW WORKS (Other)", "IOW WORKS (Safety Related)", "PWI (Track Related)", 'LC GATE DEFICIENCIES', 'P&C', 'WORKSITE'],
    "COMMERCIAL": ["REQUIREMENT/ASSETS", "CLEANLINESS/COAL BAGS", "PASSENGER AMENITIES", "STAFF (RAILWAY/CONTRACT)", "MISC"],
    "FINANCE": ["MISC"], "MEDICAL": ["MISC"], "STORE": ["MISC"],
}

INSPECTION_BY_LIST = [""] + ["HQ OFFICER CCE/CR", 'DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                              'Sr.DEE/TRD', 'Sr.DEE/G', 'Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC',
                              'DME', 'DEE/TRD', 'DFM', 'DSTE/HQ', 'DSTE/KLBG', 'ADEN/T/SUR', 'ADEN/W/SUR', 'ADEN/KWV',
                              'ADEN/PVR', 'ADEN/LUR', 'ADEN/KLBG', 'ADSTE/SUR', 'ADSTE/I/KWV', 'ADSTE/II/KWV',
                              'ADME/SUR', 'AOM/GD', 'AOM/GEN', 'ACM/Cog', 'ACM/TC', 'ACM/GD', 'APO/GEN', 'APO/WEL',
                              'ADFM/I', 'ADFMII', 'ASC', 'ADSO/SUR', "ADME/WADI", 'DEN/TRACK']

ACTION_BY_LIST = [""] + ['DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                          'Sr.DEE/TRD', 'Sr.DEE/G', 'Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC', 'CMS', 'ADEN/TM/SUR', 'DEN/TRACK', 'GSU']

VALID_INSPECTIONS = [
    "FOOTPLATE INSPECTION", "STATION INSPECTION", "LC GATE INSPECTION",
    "COACHING DEPOT", "ON TRAIN", "SURPRISE/AMBUSH INSPECTION", "WORKSITE INSPECTION", "OTHER (UNUSUAL)",
]

# =========================================================================
# HELPERS — data / classification
# =========================================================================
def normalize_str(text):
    if not isinstance(text, str):
        return ""
    return re.sub(r'\s+', ' ', text.lower()).strip()


def classify_feedback(feedback, user_remark=""):
    if isinstance(feedback, str) and feedback.strip() == "`":
        return ""

    def _classify(text_normalized):
        if not text_normalized:
            return None
        date_found = bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text_normalized))
        resolved_kw = [
            "attended", "solved", "done", "completed", "confirmed by", "message given",
            "tdc work completed", "replaced", "msg given", "msg sent", "counseled", "info shared",
            "communicated", "sent successfully", "counselled", "gate will be closed soon",
            "attending at the time", "handled", "resolved", "action taken", "spoken to", "warned",
            "counselling", "hubli", "working normal", "met", "discussion held", "report sent",
            "notified", "explained", "nil", "na", "tlc", "work completed", "acknowledged", "visited",
            "briefed", "guided", "handover", "working properly", "checked found working", "supply restored",
            "this is not a deficiency.", "this is not a deficiency", "not a deficiency", "this is observation",
            "it is observation", "updated by", "adv to", "counselled the staff", "complied", "checked and found",
            "maintained", "for needful action", "provided at", "in working condition", "is working",
            "found working", "equipment is working", "item is working", "as per plan", "putright", "put right",
            'attend dt', 'attend dt.', "operational feasibility", "will be provided",
            "will be supplied shortly", "advised to ubl", "updated"
        ]
        pending_kw = [
            "work is going on", "tdc given", "target date", "expected by", "likely by", "planned by",
            "will be", "needful", "to be", "pending", "not done", "awaiting", "waiting", "yet to", "next time",
            "follow up", "tdc.", "tdc", "t d c", "will attend", "will be attended", "scheduled", "reminder",
            "to inform", "to counsel", "to submit", "to do", "to replace", "prior", "remains", "still",
            "under process", "not yet", "to be done", "will ensure", "during next", "action will be taken",
            'noted please tdc', "will be supplied shortly", "not available", "not updated", "progress",
            "under progress", "to arrange", "awaited", "material awaited", "approval awaited", "to procure",
            "yet pending", "incomplete", "tentative", "ongoing", "in progress", "being done", "arranging",
            "waiting for", "subject to", "awaiting approval", "awaiting material", "awaiting confirmation",
            "next schedule", "planned for", "will arrange", "proposed date", "to complete", "to be completed",
            "likely completion", "expected completion", "not received", "awaiting response"
        ]
        if "tdc" in text_normalized and any(k in text_normalized for k in resolved_kw):
            return "Resolved"
        if any(k in text_normalized for k in pending_kw):
            return "Pending"
        if date_found:
            return "Pending" if "tdc" in text_normalized else "Resolved"
        if any(k in text_normalized for k in resolved_kw):
            return "Resolved"
        return None

    fb = normalize_str(feedback)
    rm = normalize_str(user_remark)
    m = re.findall(r"[!#]", f"{fb} {rm}".strip())
    if m:
        return "Resolved" if m[-1] == "#" else "Pending"
    a = _classify(fb)
    b = _classify(rm)
    if a == "Resolved" or b == "Resolved":
        return "Resolved"
    if a == "Pending" or b == "Pending":
        return "Pending"
    return "Pending"


def get_status(feedback, remark):
    return classify_feedback(feedback, remark)


def color_text_status(status):
    return "🔴 Pending" if status == "Pending" else ("🟢 Resolved" if status == "Resolved" else status)


def strip_status_emoji(status_text):
    """Undo color_text_status() so exports can match on plain 'Pending'/'Resolved'."""
    return re.sub(r"^[^\w]*", "", str(status_text)).strip()


def expand_locations(selected_locations):
    """Expand any selected footplate routes into their constituent sub-locations."""
    expanded = set(selected_locations)
    for loc in selected_locations:
        if loc in FOOTPLATE_ROUTE_HIERARCHY:
            expanded.update(FOOTPLATE_ROUTE_HIERARCHY[loc])
    return expanded


# =========================================================================
# HELPERS — Google Sheet update
# =========================================================================
def update_feedback_column(edited_df):
    header = sheet.row_values(1)

    def col_idx(name):
        try:
            return header.index(name) + 1
        except ValueError:
            st.warning(f"Column '{name}' not found in sheet header.")
            return None

    feedback_col = col_idx("Feedback")
    remark_col = col_idx("User Feedback/Remark")
    head_col = col_idx("Head")
    action_col = col_idx("Action By")
    subhead_col = col_idx("Sub Head")
    timestamp_col = col_idx(TIMESTAMP_COL_NAME)

    required = (feedback_col, remark_col, head_col, action_col, subhead_col, timestamp_col)
    if None in required:
        st.error("Cannot update: one or more required columns missing in Google Sheet.")
        return

    updates = []
    ist = pytz.timezone('Asia/Kolkata')

    for _, row in edited_df.iterrows():
        r = int(row["_sheet_row"])
        def a1(c):
            return gspread.utils.rowcol_to_a1(r, c)

        fv = row.get("Feedback", "") or ""
        rv = row.get("User Feedback/Remark", "") or ""
        hv = row.get("Head", "") or ""
        av = row.get("Action By", "") or ""
        sv = row.get("Sub Head", "") or ""

        timestamp_value = ""
        if fv.strip():
            now_ist = datetime.now(ist)
            timestamp_value = now_ist.strftime("%d-%m-%Y %H:%M:%S IST")

        updates.extend([
            {"range": a1(feedback_col), "values": [[fv]]},
            {"range": a1(remark_col), "values": [[rv]]},
            {"range": a1(head_col), "values": [[hv]]},
            {"range": a1(action_col), "values": [[av]]},
            {"range": a1(subhead_col), "values": [[sv]]},
            {"range": a1(timestamp_col), "values": [[timestamp_value]]},
        ])

        s = st.session_state.df
        mask = s["_sheet_row"] == r
        s.loc[mask, "Feedback"] = fv
        s.loc[mask, "User Feedback/Remark"] = rv
        s.loc[mask, "Head"] = hv
        s.loc[mask, "Action By"] = av
        s.loc[mask, "Sub Head"] = sv
        s.loc[mask, TIMESTAMP_COL_NAME] = timestamp_value

    if updates:
        try:
            sheet.spreadsheet.values_batch_update({
                "valueInputOption": "USER_ENTERED",
                "data": updates
            })
            st.success(f"Updated {len(updates) // 6} record(s) including timestamps.")
        except Exception as e:
            st.error(f"Google Sheets update failed: {str(e)}")


# =========================================================================
# HELPERS — filters
# =========================================================================
def apply_common_filters(df, prefix=""):
    default_to_date = date.today()
    default_from_date = default_to_date - timedelta(days=2)

    with st.expander("🔍 Apply Additional Filters", expanded=True):
        c1, c2 = st.columns(2)
        c1.multiselect(
            "Inspection By", INSPECTION_BY_LIST[1:],
            default=st.session_state.get(prefix + "insp", []),
            key=prefix + "insp"
        )
        c2.multiselect(
            "Action By", ACTION_BY_LIST[1:],
            default=st.session_state.get(prefix + "action", []),
            key=prefix + "action"
        )

        d1, d2 = st.columns(2)
        d1.date_input(
            "📅 From Date",
            value=st.session_state.get(prefix + "from_date", default_from_date),
            key=prefix + "from_date"
        )
        d2.date_input(
            "📅 To Date",
            value=st.session_state.get(prefix + "to_date", default_to_date),
            key=prefix + "to_date"
        )

    out = df.copy()

    if st.session_state.get(prefix + "insp"):
        sel = st.session_state[prefix + "insp"]
        out = out[out["Inspection By"].apply(
            lambda x: any(s.strip() in str(x).split(",") for s in sel)
        )]

    if st.session_state.get(prefix + "action"):
        sel = st.session_state[prefix + "action"]
        out = out[out["Action By"].apply(
            lambda x: any(s.strip() in str(x).split(",") for s in sel)
        )]

    if st.session_state.get(prefix + "from_date") and st.session_state.get(prefix + "to_date"):
        from_date = st.session_state[prefix + "from_date"]
        to_date = st.session_state[prefix + "to_date"]

        if from_date > to_date:
            st.warning("From Date cannot be after To Date. Adjusting filter.")
            from_date, to_date = to_date, from_date

        out = out[
            (out["Date of Inspection"] >= pd.to_datetime(from_date)) &
            (out["Date of Inspection"] <= pd.to_datetime(to_date))
        ]

    return out


# =========================================================================
# HELPERS — Excel export (shared by both download buttons)
# =========================================================================
def build_excel_export(export_df, sheet_name):
    """Build a styled Excel workbook (bytes buffer) from an export-ready DataFrame.
    Expects a 'Date of Inspection' column (date) and a plain-text 'Status' column
    ('Pending' / 'Resolved') with no emoji prefix.
    """
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]

        date_style = NamedStyle(name=f"date_style_{sheet_name}", number_format="DD-MM-YYYY")
        thin_border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin')
        )

        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                cell.border = thin_border

        if "Date of Inspection" in export_df.columns:
            date_col_idx = export_df.columns.get_loc("Date of Inspection") + 1
            for row in ws.iter_rows(min_row=2, min_col=date_col_idx, max_col=date_col_idx,
                                     max_row=len(export_df) + 1):
                for cell in row:
                    cell.style = date_style

        for col in ws.columns:
            max_length = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except Exception:
                    pass
            ws.column_dimensions[col_letter].width = (max_length + 2) if max_length < 50 else 50

        if "Status" in export_df.columns:
            status_col_idx = export_df.columns.get_loc("Status") + 1
            for row in ws.iter_rows(min_row=2, min_col=status_col_idx, max_col=status_col_idx,
                                     max_row=len(export_df) + 1):
                for cell in row:
                    val = strip_status_emoji(cell.value).lower()
                    if val == "pending":
                        cell.font = Font(color="FF0000")  # Red
                    elif val == "resolved":
                        cell.font = Font(color="008000")  # Green

    buf.seek(0)
    return buf


# =========================================================================
# HELPERS — pie-chart breakdown (shared by Head / Sub Head distributions)
# =========================================================================
def render_pie_breakdown(df, group_col, chart_title, caption_parts, threshold=0.02):
    """Render a labelled pie chart (small slices grouped into 'Others') plus a
    download button. caption_parts is a list of strings joined for the footer.
    """
    summary = (
        df.groupby(group_col)[group_col]
        .count()
        .reset_index(name="Count")
        .sort_values(by="Count", ascending=False)
    )
    if summary.empty:
        return

    total = summary["Count"].sum()
    display_data = summary.copy()
    display_data["Percent"] = display_data["Count"] / total
    major = display_data[display_data["Percent"] >= threshold][[group_col, "Count"]]
    minor = display_data[display_data["Percent"] < threshold]
    if not minor.empty:
        major = pd.concat(
            [major, pd.DataFrame([{group_col: "Others", "Count": minor["Count"].sum()}])],
            ignore_index=True
        )

    # Slightly smaller figure on narrow screens for better fit
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    wedges, texts, autotexts = ax.pie(
        major["Count"], startangle=90, autopct='%1.1f%%',
        textprops=dict(color='black', fontsize=9)
    )
    for i, (wedge, (_, row)) in enumerate(zip(wedges, major.iterrows())):
        ang = (wedge.theta2 + wedge.theta1) / 2.0
        x = np.cos(np.deg2rad(ang))
        y = np.sin(np.deg2rad(ang))
        place_right = (i % 2 == 0)
        lx = 1.45 if place_right else -1.45
        ly = 1.15 * y
        ax.text(lx, ly, f"{row[group_col]} ({row['Count']})",
                ha="left" if place_right else "right",
                va="center", fontsize=9,
                bbox=dict(facecolor="white", edgecolor="gray", alpha=0.7, pad=1))
        ax.annotate("", xy=(0.9 * x, 0.9 * y), xytext=(lx, ly),
                    arrowprops=dict(arrowstyle="-", lw=0.8, color="black"))

    fig.suptitle(chart_title, fontsize=13, fontweight="bold")
    fig.text(0.5, 0.02, " | ".join(caption_parts), ha='center', fontsize=8, color='gray')
    plt.tight_layout(rect=[0, 0.06, 1, 0.94])

    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)

    st.image(buf)
    st.download_button(
        f"📥 Download {chart_title} (PNG)", data=buf,
        file_name=f"{group_col.lower().replace(' ', '_')}_distribution.png",
        mime="image/png",
        key=f"dl_{group_col}_{chart_title}",
        use_container_width=True,
    )


# =========================================================================
# HEADER
# =========================================================================
st.markdown(
    """
    <div class="saral-header">
        <img src="https://raw.githubusercontent.com/srdsoproject/testing/main/Central%20Railway%20Logo.png"
             class="saral-logo" alt="Central Railway Logo">
        <div class="saral-header-text">
            <h2 class="saral-initiative">An Initiative by <span class="saral-safety">Safety Department</span>, Solapur Division</h2>
            <h1 class="saral-title">📋 S.A.R.A.L</h1>
            <h3 class="saral-subtitle">(Safety Abnormality Report & Action List – Version 1.3)</h3>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# =========================================================================
# LOAD DATA
# =========================================================================
@st.cache_data(ttl=5)
def load_data():
    REQUIRED_COLS = [
        "Date of Inspection", "Type of Inspection", "Location",
        "Head", "Sub Head", "Deficiencies Noted",
        "Inspection By", "Action By", "Feedback",
        "User Feedback/Remark", TIMESTAMP_COL_NAME
    ]
    try:
        data = sheet.get_all_values()
        if not data or len(data) < 2:
            st.warning("No data found in Google Sheet. Returning empty DataFrame.")
            return pd.DataFrame(columns=REQUIRED_COLS)
        headers = [c.strip() for c in data[0]]
        df = pd.DataFrame(data[1:], columns=headers)
        for col in REQUIRED_COLS:
            if col not in df.columns:
                df[col] = ""
        df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
        df["Location"] = df["Location"].astype(str).str.strip().str.upper()
        df["_sheet_row"] = df.index + 2
        return df
    except Exception as e:
        st.error(f"❌ Error loading Google Sheet: {str(e)}")
        st.warning("Returning empty DataFrame to prevent crashes.")
        return pd.DataFrame(columns=REQUIRED_COLS)


if st.session_state.df is None:
    st.session_state.df = load_data()

# =========================================================================
# MAIN TABS
# =========================================================================
tabs = st.tabs(["📝 View Records", "📊 Analytics"])

with tabs[0]:
    df = st.session_state.df
    if df is None or df.empty:
        st.warning("No data available. Please check Google Sheets connection or refresh.")
        st.stop()

    for col in ["Type of Inspection", "Location", "Head", "Sub Head", "Deficiencies Noted",
                "Inspection By", "Action By", "Feedback", "User Feedback/Remark"]:
        if col not in df.columns:
            df[col] = ""

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    df["_original_sheet_index"] = df.index
    df["Status"] = df.apply(lambda r: classify_feedback(r["Feedback"], r.get("User Feedback/Remark", "")), axis=1)

    start_date = df["Date of Inspection"].min() if not df["Date of Inspection"].isna().all() else pd.Timestamp.today()
    end_date = df["Date of Inspection"].max() if not df["Date of Inspection"].isna().all() else pd.Timestamp.today()

    # Primary filters – these will stack on mobile via CSS
    c1, c2 = st.columns(2)
    c1.multiselect("Type of Inspection", VALID_INSPECTIONS, key="view_type_filter")
    c2.multiselect("Location", ALL_LOCATIONS, key="view_location_filter")

    c3, c4 = st.columns(2)
    c3.multiselect("Head", HEAD_LIST[1:], key="view_head_filter")
    sub_opts = sorted({s for h in st.session_state.view_head_filter for s in SUBHEAD_LIST.get(h, [])})
    c4.multiselect("Sub Head", sub_opts, key="view_sub_filter")

    selected_status = st.selectbox("🔘 Status", ["All", "Pending", "Resolved"], key="view_status_filter")

    filtered = df[(df["Date of Inspection"] >= start_date) & (df["Date of Inspection"] <= end_date)]

    if st.session_state.view_type_filter:
        filtered = filtered[filtered["Type of Inspection"].isin(st.session_state.view_type_filter)]

    if st.session_state.view_location_filter:
        filtered = filtered[filtered["Location"].isin(expand_locations(st.session_state.view_location_filter))]

    if st.session_state.view_head_filter:
        filtered = filtered[filtered["Head"].isin(st.session_state.view_head_filter)]

    if st.session_state.view_sub_filter:
        filtered = filtered[filtered["Sub Head"].isin(st.session_state.view_sub_filter)]

    if selected_status != "All":
        filtered = filtered[filtered["Status"] == selected_status]

    filtered = apply_common_filters(filtered, prefix="view_")
    filtered = filtered.apply(lambda x: x.str.replace("\n", " ") if x.dtype == "object" else x)
    filtered = filtered.sort_values("Date of Inspection")

    # Metrics – 2×2 on mobile, 4 across on desktop
    col_a, col_b, col_c, col_d = st.columns(4)
    pending_count = (filtered["Status"] == "Pending").sum()
    no_response_count = filtered["Feedback"].isna().sum() + (filtered["Feedback"].astype(str).str.strip() == "").sum()
    resolved_count = (filtered["Status"] == "Resolved").sum()
    col_a.metric("🟨 Pending", pending_count)
    col_b.metric("⚠️ No Response", no_response_count)
    col_c.metric("🟩 Resolved", resolved_count)
    col_d.metric("📊 Total Records", len(filtered))

    # ---- Department-wise (Head) breakdown when Location is selected ----
    if st.session_state.view_location_filter and not filtered.empty:
        st.markdown("### 📊 Department-wise Distribution")
        dr = f"{start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}"
        locations = ", ".join(st.session_state.view_location_filter)
        type_display = ", ".join(st.session_state.view_type_filter) if st.session_state.view_type_filter else "All Types"
        render_pie_breakdown(
            filtered, "Head", "Department-wise Breakdown",
            [f"Date Range: {dr}", f"Locations: {locations}", f"Type: {type_display}"]
        )

    # ---- Sub Head breakdown when Head is selected ----
    if st.session_state.view_head_filter and not filtered.empty:
        st.markdown("### Sub Head Distribution")
        dr = f"{start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}"
        heads = ", ".join(st.session_state.view_head_filter)
        type_display = ", ".join(st.session_state.view_type_filter) if st.session_state.view_type_filter else "All Types"
        location_display = ", ".join(st.session_state.view_location_filter) if st.session_state.view_location_filter else "All Locations"
        caption = [f"Date Range: {dr}", f"Department: {heads}", f"Type: {type_display}", f"Location: {location_display}"]
        if st.session_state.view_sub_filter:
            caption.append(f"Sub Head Filter: {', '.join(st.session_state.view_sub_filter)}")
        render_pie_breakdown(filtered, "Sub Head", "Sub Head Breakdown", caption)

    # ---- Export filtered (read-only) records ----
    export_df = filtered[[
        "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
        "Deficiencies Noted", "Inspection By", "Action By", "Feedback", "User Feedback/Remark",
        "Status", TIMESTAMP_COL_NAME
    ]].copy()
    export_df["Date of Inspection"] = pd.to_datetime(export_df["Date of Inspection"]).dt.date
    st.download_button(
        "📥 Export Filtered Records to Excel",
        data=build_excel_export(export_df, "Filtered Records"),
        file_name="filtered_records.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    # ---------- EDITOR ----------
    if not filtered.empty:
        display_cols = [
            "Date of Inspection", "Type of Inspection", "Head", "Sub Head", "Location",
            "Deficiencies Noted", "Inspection By", "Action By", "Feedback",
            "User Feedback/Remark", TIMESTAMP_COL_NAME
        ]
        valid_cols = [col for col in display_cols if col in filtered.columns]
        if not valid_cols:
            st.error("⚠️ No valid columns found in the DataFrame.")
            st.stop()
        if "Deficiencies Noted" not in valid_cols:
            st.error("⚠️ 'Deficiencies Noted' column is required for search functionality.")
            st.stop()

        editable_filtered = filtered.copy()
        if "_original_sheet_index" not in editable_filtered.columns:
            editable_filtered["_original_sheet_index"] = editable_filtered.index
        if "_sheet_row" not in editable_filtered.columns:
            editable_filtered["_sheet_row"] = editable_filtered.index + 2

        editable_df = editable_filtered[valid_cols + ["_original_sheet_index", "_sheet_row"]].copy()

        if "Date of Inspection" in editable_df.columns:
            editable_df["Date of Inspection"] = pd.to_datetime(
                editable_df["Date of Inspection"], errors="coerce"
            ).dt.date

        if "Feedback" in editable_df.columns and "User Feedback/Remark" in editable_df.columns:
            editable_df.insert(
                editable_df.columns.get_loc("User Feedback/Remark") + 1,
                "Status",
                [get_status(r["Feedback"], r["User Feedback/Remark"]) for _, r in editable_df.iterrows()]
            )
            # Keep a plain-text copy for exports (emoji version is display-only in the grid)
            editable_df["_status_plain"] = editable_df["Status"]
            editable_df["Status"] = editable_df["Status"].apply(color_text_status)

        # ---- Global Search ----
        st.markdown("#### 🔍 Search and Filter")
        search_text = st.text_input("Search All Columns (case-insensitive)", "").strip().lower()
        if search_text:
            mask = editable_df[valid_cols].astype(str).apply(
                lambda col: col.str.contains(search_text, case=False, na=False)
            ).any(axis=1)
            editable_df = editable_df[mask].copy()
            st.info(f"Found {len(editable_df)} matching rows after search.")

        # ---- Column filtering ----
        max_cols = st.slider(
            "Max columns to filter on",
            1, len(valid_cols), min(10, len(valid_cols)),
            key="max_cols_filter"
        )
        candidate_columns = valid_cols[:max_cols]
        selected_columns = st.multiselect(
            "Select columns to filter",
            options=candidate_columns,
            key="column_select_filter"
        )

        if selected_columns:
            df_filtered = editable_df.copy()
            for column in selected_columns:
                col_dtype = editable_df[column].dtype
                if isinstance(col_dtype, pd.CategoricalDtype) or col_dtype == "object":
                    unique_vals = sorted(editable_df[column].dropna().unique())
                    selected_vals = st.multiselect(f"Filter {column}", unique_vals, key=f"filter_{column}")
                    if selected_vals:
                        df_filtered = df_filtered[df_filtered[column].isin(selected_vals)]
                elif is_numeric_dtype(editable_df[column]):
                    _min = float(editable_df[column].min())
                    _max = float(editable_df[column].max())
                    step = (_max - _min) / 100 if _max != _min else 1
                    selected_range = st.slider(f"Filter {column}", _min, _max, (_min, _max), step=step, key=f"range_{column}")
                    df_filtered = df_filtered[df_filtered[column].between(selected_range[0], selected_range[1])]
                elif is_datetime64_any_dtype(editable_df[column]):
                    _min = editable_df[column].min()
                    _max = editable_df[column].max()
                    selected_dates = st.date_input(f"Filter {column}", [_min, _max], min_value=_min, max_value=_max, key=f"date_{column}")
                    if len(selected_dates) == 2:
                        df_filtered = df_filtered[df_filtered[column].between(
                            pd.to_datetime(selected_dates[0]), pd.to_datetime(selected_dates[1])
                        )]
                else:
                    case = st.selectbox(f"Case sensitive for {column}?", ["both", "upper", "lower"], key=f"case_{column}")
                    search_term = st.text_input(f"Filter {column}", key=f"search_{column}")
                    if search_term:
                        if case == "upper":
                            df_filtered = df_filtered[df_filtered[column].str.upper().str.contains(search_term.upper(), na=False)]
                        elif case == "lower":
                            df_filtered = df_filtered[df_filtered[column].str.lower().str.contains(search_term.lower(), na=False)]
                        else:
                            df_filtered = df_filtered[df_filtered[column].str.contains(search_term, case=False, na=False)]
            editable_df = df_filtered
            st.info(f"Applied column filters → {len(editable_df)} rows remaining.")

        # ---- AgGrid configuration ----
        grid_display_df = editable_df.drop(columns=["_status_plain"], errors="ignore")
        gb = GridOptionsBuilder.from_dataframe(grid_display_df)
        gb.configure_default_column(
            editable=False,
            wrapText=True,
            autoHeight=True,
            resizable=True,
            suppressMovable=True,  # helps on touch devices
        )
        if "User Feedback/Remark" in grid_display_df.columns:
            gb.configure_column(
                "User Feedback/Remark",
                editable=True, wrapText=True, autoHeight=True,
                cellEditor="agTextCellEditor", cellEditorPopup=False,
                cellEditorParams={"maxLength": 4000}
            )
        gb.configure_column("_original_sheet_index", hide=True)
        gb.configure_column("_sheet_row", hide=True)
        gb.configure_grid_options(
            singleClickEdit=True,
            suppressHorizontalScroll=False,
            enableCellTextSelection=True,
            ensureDomOrder=True,
        )

        auto_size_js = JsCode("""
        function(params) {
            let allColumnIds = [];
            params.columnApi.getAllColumns().forEach(function(column) {
                allColumnIds.push(column.getColId());
            });
            params.columnApi.autoSizeColumns(allColumnIds);
        }
        """)
        gb.configure_grid_options(onFirstDataRendered=auto_size_js)
        grid_options = gb.build()

        st.markdown("#### 🚈 Inspection Details")
        st.caption("Type your compliance in 'User Feedback/Remark' column. Use column headers to sort. On mobile you can scroll the grid horizontally.")
        grid_response = AgGrid(
            grid_display_df,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            height=500,                 # CSS will reduce this further on small screens
            allow_unsafe_jscode=True,
            fit_columns_on_grid_load=False,
            theme="streamlit",
        )
        edited_df = pd.DataFrame(grid_response["data"])

        # ---- Export edited grid (plain-text Status so colouring matches) ----
        export_cols = [c for c in valid_cols if c not in ["_original_sheet_index", "_sheet_row"]]
        export_edited_df = edited_df[export_cols].copy()
        export_edited_df["Status"] = edited_df["Status"].apply(strip_status_emoji)
        export_edited_df["Date of Inspection"] = pd.to_datetime(export_edited_df["Date of Inspection"]).dt.date

        st.download_button(
            label="📥 Export Edited Records to Excel",
            data=build_excel_export(export_edited_df, "Edited Records"),
            file_name=f"edited_records_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        # ---- Buttons ----
        b1, b2 = st.columns(2)
        submitted = b1.button("✅ Submit Feedback", use_container_width=True)
        refresh_clicked = b2.button("🔄 Refresh Data", use_container_width=True)

        if refresh_clicked:
            with st.spinner("🔄 Refreshing data from Google Sheets..."):
                st.session_state.df = load_data()
            st.success("✅ Data refreshed successfully!")
            st.rerun()

        if submitted:
            if st.session_state.get("feedback_submitting", False):
                st.warning("⏳ Submission already in progress. Please wait...")
            else:
                st.session_state.feedback_submitting = True
                try:
                    with st.spinner("💾 Saving feedback to Google Sheet... Please do not refresh or close the page."):
                        need_cols = {"_original_sheet_index", "User Feedback/Remark"}
                        if not need_cols.issubset(edited_df.columns) or "Feedback" not in editable_filtered.columns:
                            st.error("⚠️ Required columns are missing from the data.")
                        else:
                            orig = editable_filtered.set_index("_original_sheet_index")
                            new_df = edited_df.set_index("_original_sheet_index")

                            old_remarks = orig["User Feedback/Remark"].fillna("").astype(str)
                            new_remarks = new_df["User Feedback/Remark"].fillna("").astype(str)

                            common_ids = new_remarks.index.intersection(old_remarks.index)
                            diff_mask = new_remarks.loc[common_ids] != old_remarks.loc[common_ids]
                            changed_ids = diff_mask[diff_mask].index.tolist()

                            if changed_ids:
                                diffs = new_df.loc[changed_ids].copy()
                                diffs["_sheet_row"] = orig.loc[changed_ids, "_sheet_row"].values

                                for oid in changed_ids:
                                    user_remark = new_df.loc[oid, "User Feedback/Remark"].strip()
                                    if not user_remark:
                                        continue
                                    # Copy the remark into Feedback and clear the remark field
                                    diffs.at[oid, "Feedback"] = user_remark
                                    diffs.at[oid, "User Feedback/Remark"] = ""
                                    st.session_state.df.at[oid, "Feedback"] = user_remark
                                    st.session_state.df.at[oid, "User Feedback/Remark"] = ""

                                update_feedback_column(diffs.reset_index())
                                st.success(f"✅ Successfully updated {len(changed_ids)} record(s)!")
                            else:
                                st.info("ℹ️ No changes detected in the feedback.")
                except Exception as e:
                    st.error(f"❌ Error during submission: {str(e)}")
                finally:
                    st.session_state.feedback_submitting = False
    else:
        st.info("No deficiencies available to update at the moment.")

# =========================================================================
# FOOTER
# =========================================================================
st.markdown("""
<div style="text-align: center; margin: 28px 0;">
  <div class="adaptive-credit">
    <p>
      <strong>Designed & Developed by</strong>
      <span class="highlight">Safety Department</span>,
      <em>Solapur Division</em>
    </p>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("### 📞 Need Help or Correction in Data?")
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    whatsapp_url = "https://wa.me/919022507772?text=Hello%20Safety%20Department%2C%20I%20need%20assistance%20regarding%20S.A.R.A.L%20data."
    st.markdown(
        f"""
        <div style="text-align: center;">
            <a href="{whatsapp_url}" target="_blank" rel="noopener noreferrer">
                <button style="
                    background-color: #25D366; color: white; font-size: 17px; font-weight: bold;
                    padding: 14px 28px; border: none; border-radius: 50px; cursor: pointer;
                    box-shadow: 0 4px 15px rgba(37, 211, 102, 0.4); transition: all 0.3s ease;
                    max-width: 100%;">
                    📱 Contact Us on WhatsApp<br>
                    <small>+91 90225 07772</small>
                </button>
            </a>
            <p style="margin-top: 14px; color: gray; font-size: 13px; line-height: 1.5;">
                For data corrections:<br>
                ✉️ <a href="mailto:sursafetyposition@gmail.com">sursafetyposition@gmail.com</a><br>
                Rly: 55620
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

# =========================================================================
# ANALYTICS TAB
# =========================================================================
with tabs[1]:
    st.markdown("### Total Deficiencies Trend (Bar + Trend Line)")
    df = st.session_state.df.copy()

    if "Status" not in df.columns:
        df["Status"] = df.apply(
            lambda r: classify_feedback(r["Feedback"], r.get("User Feedback/Remark", "")), axis=1
        )
    df["Status"] = df["Status"].fillna("Pending").replace({"": "Pending", "NA": "Pending"})
    df["Status"] = df["Status"].str.strip().str.upper().map({
        "PENDING": "Pending", "RESOLVED": "Resolved", "CLOSED": "Resolved"
    }).fillna("Pending")

    if df.empty:
        st.info("No data available for analytics.")
    else:
        df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
        df = df.dropna(subset=["Date of Inspection"])

        min_date = df["Date of Inspection"].min().date()
        max_date = df["Date of Inspection"].max().date()
        start_date, end_date = st.date_input(
            "Select Inspection Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
        df = df[
            (df["Date of Inspection"] >= pd.to_datetime(start_date)) &
            (df["Date of Inspection"] <= pd.to_datetime(end_date))
        ].copy()

        def clean_name(text):
            if pd.isna(text):
                return "UNKNOWN"
            s = str(text).strip()
            s = re.sub(r"[\*\-\_\'\"]", "", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s.upper()

        df["Head_clean"] = df["Head"].apply(clean_name)
        dept_map = {
            "ENGINEERING": "ENGINEERING", "GSU": "GSU",
            "ELECT/G": "ELECT/G", "ELECTG": "ELECT/G",
            "ELECT/TRD": "ELECT/TRD", "ELECT/TRO": "ELECT/TRO",
            "OPTG": "OPTG", "OPERATING": "OPTG",
            "SIGNAL & TELECOM": "SIGNAL & TELECOM",
            "MECHANICAL": "MECHANICAL", "COMMERCIAL": "COMMERCIAL",
            "C&W": "C&W", "SECURITY": "SECURITY", "PERSONNEL": "PERSONNEL",
            "MEDICAL": "MEDICAL", "FINANCE": "FINANCE", "STORE": "STORE",
        }
        df["Head_std"] = df["Head_clean"].map(dept_map).fillna("UNKNOWN")

        if "Location" not in df.columns:
            df["Location"] = ""
        df["Location_clean"] = df["Location"].astype(str).apply(clean_name)
        STATIONS_NORM = {clean_name(x) for x in STATION_LIST}
        df["Is_Station"] = df["Location_clean"].isin(STATIONS_NORM)

        all_locations = set(df["Location_clean"].dropna().unique())
        for main_route, subsections in FOOTPLATE_ROUTE_HIERARCHY.items():
            if main_route in all_locations:
                all_locations.update(subsections)
        df = df[df["Location_clean"].isin(all_locations)]

        # ---- Trend chart ----
        trend = df.groupby(pd.Grouper(key="Date of Inspection", freq="MS")).size().reset_index(name="TotalCount")
        trend = trend.dropna(subset=["Date of Inspection"])

        if not trend.empty:
            trend = trend.sort_values("Date of Inspection")
            base = alt.Chart(trend).encode(
                x=alt.X("Date of Inspection:T", title="Month", axis=alt.Axis(format="%b-%Y")),
                y=alt.Y("TotalCount:Q", title="Total Deficiencies")
            )
            bars = base.mark_bar(color="#1f77b4", cornerRadius=3)
            line = base.transform_regression("Date of Inspection", "TotalCount").mark_line(
                color="red", strokeDash=[6, 4], strokeWidth=2.5
            )
            st.altair_chart(bars + line, use_container_width=True)
        else:
            st.info("No data in selected range.")

        # ---- Department summary (overall) ----
        st.markdown("### Department-wise **Total** Deficiencies Logged")
        dept_counts = df.groupby("Head_std").size().reset_index(name="TotalCount") \
            .sort_values("TotalCount", ascending=False)
        total_deficiencies = dept_counts["TotalCount"].sum()
        dept_counts["color"] = "#ff7f0e"
        dept_counts.loc[:2, "color"] = "red"
        for _, row in dept_counts.iterrows():
            st.markdown(f"- **{row['Head_std']}** : **{row['TotalCount']:,}**")
        st.markdown(f"**Grand Total: {total_deficiencies:,}**")

        dept_chart = alt.Chart(dept_counts).mark_bar().encode(
            x=alt.X("TotalCount:Q", title="Total Deficiencies"),
            y=alt.Y("Head_std:N", sort="-x", title="Department"),
            color=alt.Color("color:N", scale=None),
            tooltip=["Head_std", alt.Tooltip("TotalCount", format=",")]
        ).properties(height=max(280, len(dept_counts) * 36))
        st.altair_chart(dept_chart, use_container_width=True)

        top3 = dept_counts.head(3)
        critical_text = ", ".join([f"**{r['Head_std']}** ({r['TotalCount']:,})" for _, r in top3.iterrows()])
        st.markdown(f"**Critical Departments:** {critical_text}")

        # ---- Top 3 stations ----
        st.markdown("### Top 3 Stations having most logged deficiencies")
        station_df = df[df["Is_Station"]].copy()
        if not station_df.empty:
            top3_stations = (
                station_df.groupby("Location_clean")
                .size()
                .reset_index(name="TotalCount")
                .sort_values("TotalCount", ascending=False)
                .head(3)
                .copy()
            )
            top3_stations["Label"] = top3_stations["Location_clean"]
            top3_stations["color"] = "red"
            chart = alt.Chart(top3_stations).mark_bar().encode(
                x=alt.X("TotalCount:Q", title="Total Deficiencies"),
                y=alt.Y("Label:N", sort="-x", title="Station"),
                color=alt.Color("color:N", scale=None),
                tooltip=["Label", alt.Tooltip("TotalCount", format=",")]
            ).properties(height=220)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No station data found in the selected period.")

        # ---- Location filter → department breakdown ----
        st.markdown("### Department wise deficiencies logged")
        all_locations = sorted(all_locations)
        selected_locations = st.multiselect(
            "Select Locations (Stations / Gates / Routes)",
            options=all_locations,
            default=all_locations
        )
        if selected_locations:
            expanded_locations = expand_locations(selected_locations)
            filtered = df[df["Location_clean"].isin(expanded_locations)].copy()

            dept_breakdown = (
                filtered.groupby("Head_std")
                .size()
                .reset_index(name="TotalCount")
                .sort_values("TotalCount", ascending=False)
            )
            status_breakdown = (
                filtered.groupby(["Head_std", "Status"])
                .size()
                .unstack(fill_value=0)
            )
            status_breakdown.columns = [f"{col}Count" for col in status_breakdown.columns]
            status_breakdown = status_breakdown.reset_index()

            summary_df = dept_breakdown.merge(status_breakdown, on="Head_std", how="left")
            summary_df["PendingCount"] = summary_df.get("PendingCount", 0)
            summary_df["ResolvedCount"] = summary_df.get("ResolvedCount", 0)

            bar_chart = alt.Chart(summary_df).mark_bar(color="#1f77b4").encode(
                x=alt.X("TotalCount:Q", title="Total Deficiencies Logged"),
                y=alt.Y("Head_std:N", title="Department", sort="-x"),
                tooltip=[
                    "Head_std",
                    alt.Tooltip("TotalCount", title="Total", format=","),
                    alt.Tooltip("PendingCount", title="Pending", format=","),
                    alt.Tooltip("ResolvedCount", title="Resolved", format=",")
                ]
            ).properties(height=max(280, len(summary_df) * 38))

            text = bar_chart.mark_text(
                align="left", baseline="middle", dx=3, fontWeight="bold", color="black"
            ).encode(text=alt.Text("TotalCount:Q", format=","))

            final_chart = (bar_chart + text).configure_axis(
                labelFontSize=12, titleFontSize=14
            ).configure_title(fontSize=16)
            st.altair_chart(final_chart, use_container_width=True)

            total = summary_df["TotalCount"].sum()
            pending = summary_df["PendingCount"].sum()
            resolved = summary_df["ResolvedCount"].sum()
            st.markdown(
                f"**Total Deficiencies Logged:** {total:,} | "
                f"**Pending:** {pending:,} | "
                f"**Resolved:** {resolved:,}"
            )

            st.markdown("**Department-wise Breakdown:**")
            for _, row in summary_df.iterrows():
                st.markdown(
                    f"- **{row['Head_std']}**: **Total Deficiencies:** {row['TotalCount']:,} | "
                    f"**Pending:** {row['PendingCount']:,} | "
                    f"**Resolved:** {row['ResolvedCount']:,}"
                )
        else:
            st.info("Please select at least one location to view the breakdown.")
