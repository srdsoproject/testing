import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from io import BytesIO
from matplotlib import pyplot as plt
import altair as alt
import re
import numpy as np
from openpyxl.styles import Alignment, Font, Border, Side, NamedStyle
from pandas.api.types import is_categorical_dtype, is_numeric_dtype, is_datetime64_any_dtype
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode

# ---------- CONFIG ----------
st.set_page_config(page_title="Inspection App", layout="wide")

# Inject custom CSS for mobile responsiveness
st.markdown("""
<style>
/* General styles */
body {
    font-family: 'Roboto', sans-serif;
}
.stButton > button {
    width: 100%;
    padding: 10px;
    font-size: 1rem;
    border-radius: 8px;
}
.stTextInput > div > input, .stSelectbox > div > select {
    font-size: 1rem;
    padding: 8px;
}
.stExpander summary {
    font-size: 1rem;
    padding: 10px;
}
.stTabs > div > button {
    font-size: 1rem;
    padding: 8px 16px;
}
.stDataFrame, .stTable {
    width: 100% !important;
    overflow-x: auto;
}
/* Mobile-specific styles */
@media (max-width: 600px) {
    .stApp {
        padding: 10px;
    }
    h1 {
        font-size: 1.5rem;
        margin-bottom: 10px;
    }
    h3 {
        font-size: 1.2rem;
    }
    .stButton > button {
        font-size: 0.9rem;
        padding: 8px;
    }
    .stTextInput > div > input, .stSelectbox > div > select {
        font-size: 0.9rem;
    }
    .stExpander summary {
        font-size: 0.9rem;
    }
    .stTabs > div > button {
        font-size: 0.9rem;
        padding: 6px 12px;
    }
    .stMetric {
        font-size: 0.8rem;
    }
    .stDataFrame, .stTable {
        font-size: 0.9rem;
    }
    .adaptive-credit {
        padding: 10px 20px;
        font-size: 0.9rem;
    }
    marquee {
        display: none;
    }
    .vega-embed, canvas {
        width: 100% !important;
        max-width: 100%;
    }
    .stHorizontal > div {
        flex-direction: column;
    }
    .stColumn {
        width: 100% !important;
        margin-bottom: 10px;
    }
    /* Card layout for mobile */
    .card {
        border: 1px solid #ccc;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 10px;
        background-color: #f9f9f9;
    }
    .card-header {
        font-weight: bold;
        font-size: 0.95rem;
        margin-bottom: 8px;
    }
    .card-field {
        margin-bottom: 8px;
    }
    .card-field label {
        font-size: 0.9rem;
        color: #555;
    }
    .card-field p {
        font-size: 0.9rem;
        margin: 4px 0;
    }
}
/* AgGrid adjustments */
.ag-root-wrapper {
    font-size: 0.9rem;
    overflow-x: auto;
}
.ag-cell {
    padding: 8px !important;
    line-height: 1.4 !important;
    white-space: normal !important;
}
.ag-header-cell-text {
    font-size: 0.9rem;
    white-space: normal !important;
}
@media (max-width: 600px) {
    .ag-root-wrapper {
        font-size: 0.9rem;
        max-width: 100%;
        overflow-x: auto;
    }
    .ag-cell {
        padding: 8px !important;
        min-height: 40px;
    }
    .ag-header-cell-text {
        font-size: 0.9rem;
    }
    .ag-header-cell {
        padding: 6px !important;
    }
}
.vega-embed text {
    font-size: 10px;
}
@media (max-width: 600px) {
    .vega-embed text {
        font-size: 9px;
    }
}
</style>
""", unsafe_allow_html=True)

# Inject JavaScript to detect screen width
st.markdown("""
<script>
    if (window.innerWidth <= 600) {
        window.sessionStorage.setItem('is_mobile', 'true');
    } else {
        window.sessionStorage.setItem('is_mobile', 'false');
    }
</script>
""", unsafe_allow_html=True)

# ---------- SESSION STATE INITIALIZATION ----------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = {}
if "ack_done" not in st.session_state:
    st.session_state.ack_done = False
if "alerts_log" not in st.session_state:
    st.session_state.alerts_log = []
if "df" not in st.session_state:
    st.session_state.df = None
if "is_mobile" not in st.session_state:
    st.session_state.is_mobile = False  # Default until JS updates it

# ---------- LOGIN ----------
def login(email, password):
    for user in st.secrets["users"]:
        if user["email"] == email and user["password"] == password:
            return user
    return None

if not st.session_state.logged_in:
    st.title("🔐 Login to S.A.R.A.L")
    with st.form("login_form", clear_on_submit=True):
        email = st.text_input("📧 Email")
        password = st.text_input("🔒 Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            user = login(email, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.success(f"✅ Welcome, {user['name']}!")
                st.rerun()
            else:
                st.error("❌ Invalid email or password.")
    st.stop()

# ---------- ACKNOWLEDGMENT ----------
user_id = st.session_state.user["email"]
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
        st.info("""
        The compliance of deficiencies of previous dates are pending & needs to be completed immediately.
        I hereby declare that I have read this notice and will ensure compliance.
        """)
        with st.form("ack_form"):
            responder_name = st.text_input("✍️ Your Name")
            ack_submitted = st.form_submit_button("Submit Acknowledgment")
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
    df = pd.read_excel("responses.xlsx")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.write("No responses submitted yet.")
except FileNotFoundError:
    st.write("No responses submitted yet.")
if st.button("🗑️ Clear All Responses", key="clear_responses_btn"):
    df = pd.DataFrame(columns=["UserID", "Name"])
    df.to_excel("responses.xlsx", index=False)
    st.success("✅ All responses have been cleared.")

# ---------- GOOGLE SHEETS CONNECTION ----------
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
    SHEET_ID = "1_WQyJCtdXuAIQn3IpFTI4KfkrveOHosNsvsZn42jAvw"
    SHEET_NAME = "Sheet1"
    return gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

sheet = connect_to_gsheet()
st.sidebar.success("✅ Connected to Google Sheets!")

# ---------- SIDEBAR ----------
st.sidebar.markdown(f"👤 Logged in as: **{st.session_state.user['name']}**")
st.sidebar.markdown(f"📧 {st.session_state.user['email']}")
if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.session_state.user = {}
    st.rerun()

# ---------- CONSTANT LISTS ----------
STATION_LIST = list(dict.fromkeys([
    'BRB', 'MLM', 'BGVN', 'JNTR', 'PRWD', 'WSB', 'PPJ', 'JEUR', 'KEM', 'BLNI', 'DHS', 'KWV', 'WDS', 'MA', 'AAG',
    'MKPT', 'MO', 'MVE', 'PK', 'BALE', "SUR", 'TKWD', 'HG', 'TLT', 'AKOR', 'NGS', 'BOT', 'DUD', 'KUI', 'GDGN', 'GUR',
    'HHD', 'SVG', 'BBD', 'TJSP', 'KLBG', 'HQR', 'MR', 'SDB', 'WADI', 'ARAG', 'BLNK', 'SGRE', 'KVK', 'LNP', 'DLGN',
    'JTRD', 'MSDG', 'JVA', 'WSD', 'SGLA', 'PVR', 'MLB', 'SEI', 'BTW', 'PJR', 'DRSV', 'YSI', 'KMRD', 'DKY', 'MRX',
    'OSA', 'HGL', 'LUR', 'NTPC', 'MRJ', 'BHLI'
]))
GATE_LIST = list(dict.fromkeys([
    'LC-19', 'LC-22A', 'LC-25', 'LC-26', 'LC-27C', 'LC-28', 'LC-30', 'LC-31', 'LC-35', 'LC-37', 'LC-40', 'LC-41',
    'LC-43', 'LC-44', 'LC-45', 'LC-46C', 'LC-54', 'LC-61', 'LC-66', 'LC-74', 'LC-76', 'LC-78', 'LC-82', 'LC-1',
    'LC-60A', 'LC-1 TLT ZCL', 'LC-1 ACC', 'LC-2 ACC', 'LC-91', 'LC-22', 'LC-24', 'LC-32', 'LC-49', 'LC-70',
    'LC-10', 'LC-34', 'LC-36', 'LC-47', 'LC-55', 'LC-59', 'LC-2', 'LC-4', 'LC-42', 'LC-02', 'LC-128', 'LC-63',
    'LC-04', 'LC-67', 'LC-77', 'LC-75', 'LC-64', 'LC-65', 'LC-5', 'LC-6', 'LC-57', 'LC-62', 'LC-39', 'LC-2/C',
    'LC-6/C', 'LC-11', 'LC-03', 'LC-15/C', 'LC-21', 'LC-26-A', 'LC-60'
]))
FOOTPLATE_ROUTES = ["SUR-DD", "SUR-WADI", "LUR-KWV", 'KWV-MRJ', 'DD-SUR', 'WADI-SUR', 'KWV-LUR', 'MRJ-KWV']
HEAD_LIST = ["", "ELECT/TRD", "ELECT/G", "ELECT/TRO", "SIGNAL & TELECOM", "OPTG", "MECHANICAL",
             "ENGINEERING", "COMMERCIAL", "C&W", 'PERSONNEL', 'SECURITY', "FINANCE", "MEDICAL", "STORE"]
SUBHEAD_LIST = {
    "ELECT/TRD": ["T/W WAGON", "TSS/SP/SSP", "OHE SECTION", "OHE STATION", "MISC"],
    "ELECT/G": ["TL/AC COACH", "POWER/PANTRY CAR", "WIRING/EQUIPMENT", "UPS", "AC", "DG", "SOLAR LIGHT", "MISC"],
    "ELECT/TRO": ["LOCO DEFECTS", "RUNNING ROOM DEFICIENCIES", "LOBBY DEFICIENCIES", "LRD RELATED", "PERSONAL STORE", "PR RELATED",
                  "CMS", "MISC"],
    "MECHANICAL": ["MISC"],
    "SIGNAL & TELECOM": ["SIGNAL PUTBACK/BLANK", "OTHER SIGNAL FAILURE", "BPAC", "GATE", "RELAY ROOM",
                         "STATION(VDU/BLOCK INSTRUMENT)", "MISC", "CCTV", "DISPLAY BOARDS"],
    "OPTG": ["SWR/CSR/CSL/TWRD", "COMPETENCY RELATED", "STATION RECORDS", "STATION DEFICIENCIES",
             "SM OFFICE DEFICIENCIES", "MISC"],
    "ENGINEERING": ["IOW WORKS", "GSU", "ROUGH RIDING", "TRACK NEEDS ATTENTION", "MISC"],
    "COMMERCIAL": ["TICKETING RELATED/MACHINE", "IRCTC", "MISC"],
    "C&W": ["BRAKE BINDING", 'WHEEL DEFECT', 'TRAIN PARTING', 'PASSENGER AMENITIES', 'AIR PRESSURE LEAKAGE',
            'DAMAGED UNDER GEAR PARTS', 'MISC'],
    "FINANCE": ["MISC"], "MEDICAL": ["MISC"], "STORE": ["MISC"],
}
INSPECTION_BY_LIST = [""] + ["HQ OFFICER CCE/CR", 'DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                             'Sr.DEE/TRD', 'Sr.DEE/G', 'Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC',
                             'DME,DEE/TRD', 'DFM', 'DSTE/HQ', 'DSTE/KLBG', 'ADEN/T/SUR', 'ADEN/W/SUR', 'ADEN/KWV',
                             'ADEN/PVR', 'ADEN/LUR', 'ADEN/KLBG', 'ADSTE/SUR', 'ADSTE/I/KWV', 'ADSTE/II/KWV',
                             'ADME/SUR', 'AOM/GD', 'AOM/GEN', 'ACM/Cog', 'ACM/TC', 'ACM/GD', 'APO/GEN', 'APO/WEL',
                             'ADFM/I', 'ADFMII', 'ASC', 'ADSO/SUR']
ACTION_BY_LIST = [""] + ['DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                         'Sr.DEE/TRD', 'Sr.DEE/G', 'Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC', 'CMS']
VALID_INSPECTIONS = [
    "FOOTPLATE INSPECTION", "STATION INSPECTION", "LC GATE INSPECTION",
    "MISC", "COACHING DEPOT", "ON TRAIN", "SURPRISE/AMBUSH INSPECTION", "WORKSITE INSPECTION", "OTHER (UNUSUAL)",
]
FOOTPLATE_LIST = STATION_LIST + GATE_LIST + FOOTPLATE_ROUTES

# ---------- HELPERS ----------
def clean_name(text):
    if pd.isna(text) or text is None:
        return ""
    try:
        return re.sub(r'\s+', ' ', str(text).upper()).strip()
    except Exception as e:
        st.warning(f"Error cleaning text: {text} ({type(text)}). Error: {e}")
        return ""

def normalize_str(text):
    if pd.isna(text) or text is None:
        return ""
    try:
        return re.sub(r'\s+', ' ', str(text).lower()).strip()
    except Exception as e:
        st.warning(f"Error normalizing text: {text} ({type(text)}). Error: {e}")
        return ""

def classify_feedback(feedback, user_remark=""):
    try:
        if isinstance(feedback, str) and feedback.strip() == "`":
            return ""
        
        def _classify(text_normalized):
            if not isinstance(text_normalized, str) or not text_normalized:
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
                "updated by", "adv to", "counselled the staff", "complied", "checked and found",
                "maintained", "for needful action", "provided at", "in working condition", "is working",
                "found working", "equipment is working", "item is working", "as per plan", "putright", "put right",
                "operational feasibility", "will be provided", "will be supplied shortly", "advised to ubl", "updated"
            ]
            pending_kw = [
                "work is going on", "tdc given", "target date", "expected by", "likely by", "planned by",
                "will be", "needful", "to be", "pending", "not done", "awaiting", "waiting", "yet to", "next time",
                "follow up", "tdc.", "tdc", "t d c", "will attend", "will be attended", "scheduled", "reminder",
                "to inform", "to counsel", "to submit", "to do", "to replace", "prior", "remains", "still",
                "under process", "not yet", "to be done", "will ensure", "during next", "action will be taken", "noted please tdc",
                "will be supplied shortly", "not available", "not updated", "progress", "under progress",
                "to arrange", "awaited", "material awaited", "approval awaited", "to procure", "yet pending",
                "incomplete", "tentative", "ongoing", "in progress", "being done", "arranging", "waiting for",
                "subject to", "awaiting approval", "awaiting material", "awaiting confirmation", "next schedule",
                "planned for", "will arrange", "proposed date", "to complete", "to be completed",
                "likely completion", "expected completion", "not received", "awaiting response"
            ]
            resolved_kw = [str(kw) for kw in resolved_kw]
            pending_kw = [str(kw) for kw in pending_kw]
            
            if "tdc" in text_normalized and any(kw in text_normalized for kw in resolved_kw):
                return "Resolved"
            if any(kw in text_normalized for kw in pending_kw):
                return "Pending"
            if date_found:
                return "Pending" if "tdc" in text_normalized else "Resolved"
            if any(kw in text_normalized for kw in resolved_kw):
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
    except Exception as e:
        st.error(f"Error in classify_feedback: {e}. Feedback: {feedback}, Remark: {user_remark}")
        return "Pending"

def get_status(feedback, remark):
    return classify_feedback(feedback, remark)

def color_text_status(status):
    return "🔴 Pending" if status == "Pending" else ("🟢 Resolved" if status == "Resolved" else status)

def filter_dataframe(df: pd.DataFrame, include_index: bool = False) -> pd.DataFrame:
    df_filtered = df.copy()
    for column in column_selection:
        if is_categorical_dtype(df[column]) or df[column].dtype == "object":
            unique_vals = sorted(df[column].dropna().unique())
            selected_vals = st.multiselect(f"Filter {column}", unique_vals, key=f"filter_{column}")
            if selected_vals:
                df_filtered = df_filtered[df_filtered[column].isin(selected_vals)]
        elif is_numeric_dtype(df[column]):
            _min = float(df[column].min())
            _max = float(df[column].max())
            step = (_max - _min) / 100 if _max != _min else 1
            selected_range = st.slider(f"Filter {column}", _min, _max, (_min, _max), step=step, key=f"range_{column}")
            df_filtered = df_filtered[df_filtered[column].between(selected_range[0], selected_range[1])]
        elif is_datetime64_any_dtype(df[column]):
            _min = df[column].min()
            _max = df[column].max()
            selected_dates = st.date_input(f"Filter {column}", [_min, _max], min_value=_min, max_value=_max, key=f"date_{column}")
            if len(selected_dates) == 2:
                df_filtered = df_filtered[df_filtered[column].between(pd.to_datetime(selected_dates[0]), pd.to_datetime(selected_dates[1]))]
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
    return df_filtered

# ---------- GOOGLE SHEET UPDATE ----------
def update_feedback_column(edited_df):
    header = sheet.row_values(1)
    def col_idx(name):
        try:
            return header.index(name) + 1
        except ValueError:
            st.error(f"⚠️ '{name}' column not found")
            return None
    feedback_col = col_idx("Feedback")
    remark_col = col_idx("User Feedback/Remark")
    head_col = col_idx("Head")
    action_col = col_idx("Action By")
    subhead_col = col_idx("Sub Head")
    if None in (feedback_col, remark_col, head_col, action_col, subhead_col):
        return
    updates = []
    for _, row in edited_df.iterrows():
        r = int(row["_sheet_row"])
        def a1(c): return gspread.utils.rowcol_to_a1(r, c)
        fv = row.get("Feedback", "") or ""
        rv = row.get("User Feedback/Remark", "") or ""
        hv = row.get("Head", "") or ""
        av = row.get("Action By", "") or ""
        sv = row.get("Sub Head", "") or ""
        updates += [
            {"range": a1(feedback_col), "values": [[fv]]},
            {"range": a1(remark_col), "values": [[rv]]},
            {"range": a1(head_col), "values": [[hv]]},
            {"range": a1(action_col), "values": [[av]]},
            {"range": a1(subhead_col), "values": [[sv]]},
        ]
        s = st.session_state.df
        s.loc[s["_sheet_row"] == r, ["Feedback", "User Feedback/Remark", "Head", "Action By", "Sub Head"]] = [fv, rv, hv, av, sv]
    if updates:
        sheet.spreadsheet.values_batch_update({"valueInputOption": "USER_ENTERED", "data": updates})

# ---------- FILTER WIDGETS ----------
def apply_common_filters(df, prefix=""):
    with st.expander("🔍 Apply Additional Filters", expanded=False):
        c1, c2 = st.columns([1, 1])
        c1.multiselect("Inspection By", INSPECTION_BY_LIST[1:],
                       default=st.session_state.get(prefix + "insp", []), key=prefix + "insp")
        c2.multiselect("Action By", ACTION_BY_LIST[1:],
                       default=st.session_state.get(prefix + "action", []), key=prefix + "action")
        d1, d2 = st.columns([1, 1])
        d1.date_input("📅 From Date", key=prefix + "from_date")
        d2.date_input("📅 To Date", key=prefix + "to_date")
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
        out = out[
            (out["Date of Inspection"] >= pd.to_datetime(from_date)) &
            (out["Date of Inspection"] <= pd.to_datetime(to_date))
        ]
    return out

# ---------- HEADER ----------
st.markdown(
    """
    <div style="display:flex;align-items:center;margin-top:10px;margin-bottom:20px;">
        <img src="https://raw.githubusercontent.com/srdsoproject/testing/main/Central%20Railway%20Logo.png"
             style="height:40px;margin-right:10px;object-fit:contain;">
        <div>
            <h3 style="margin:0;font-weight:bold;color:var(--text-color);font-size:1rem;">
                An initiative by <b>Safety Department</b>, Solapur Division
            </h3>
        </div>
    </div>
    <h1 style="margin-top:0;color:var(--text-color);font-size:1.8rem;">📋 S.A.R.A.L</h1>
    <h3 style="margin-top:-10px;font-weight:normal;color:var(--text-color);font-size:1rem;">
        (Safety Abnormality Report & Action List – Version 1.1.8)
    </h3>
    """,
    unsafe_allow_html=True
)

# ---------- LOAD DATA ----------
@st.cache_data(ttl=300)
def load_data():
    REQUIRED_COLS = [
        "Date of Inspection", "Type of Inspection", "Location",
        "Head", "Sub Head", "Deficiencies Noted",
        "Inspection By", "Action By", "Feedback",
        "User Feedback/Remark"
    ]
    try:
        data = sheet.get_all_values()
        if not data or len(data) < 2:
            st.warning("No data found in Google Sheet.")
            return pd.DataFrame(columns=REQUIRED_COLS)
        headers = [c.strip() for c in data[0]]
        df = pd.DataFrame(data[1:], columns=headers)
        for col in REQUIRED_COLS:
            if col not in df.columns:
                df[col] = ""
        df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
        df["Location"] = df["Location"].astype(str).str.strip().str.upper()
        df["_sheet_row"] = df.index + 2
        for col in ["Location", "Head", "Sub Head", "Deficiencies Noted", "Inspection By", "Action By", "Feedback", "User Feedback/Remark"]:
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"❌ Error loading Google Sheet: {str(e)}")
        return pd.DataFrame(columns=REQUIRED_COLS)

if st.session_state.df is None:
    st.session_state.df = load_data()

# ---------- TABS ----------
tabs = st.tabs(["📊 View Records", "📈 Analytics"])

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
    
    # Responsive filter layout
    with st.container():
        c1, c2 = st.columns([1, 1])
        c1.multiselect("Type of Inspection", VALID_INSPECTIONS, key="view_type_filter")
        c2.multiselect("Location", FOOTPLATE_LIST, key="view_location_filter")
        c3, c4 = st.columns([1, 1])
        c3.multiselect("Head", HEAD_LIST[1:], key="view_head_filter")
        sub_opts = sorted({s for h in st.session_state.view_head_filter for s in SUBHEAD_LIST.get(h, [])})
        c4.multiselect("Sub Head", sub_opts, key="view_sub_filter")
    
    selected_status = st.selectbox("🔘 Status", ["All", "Pending", "Resolved"], key="view_status_filter")
    filtered = df[(df["Date of Inspection"] >= start_date) & (df["Date of Inspection"] <= end_date)]
    if st.session_state.view_type_filter:
        filtered = filtered[filtered["Type of Inspection"].isin(st.session_state.view_type_filter)]
    if st.session_state.view_location_filter:
        filtered = filtered[filtered["Location"].isin(st.session_state.view_location_filter)]
    if st.session_state.view_head_filter:
        filtered = filtered[filtered["Head"].isin(st.session_state.view_head_filter)]
    if st.session_state.view_sub_filter:
        filtered = filtered[filtered["Sub Head"].isin(st.session_state.view_sub_filter)]
    if selected_status != "All":
        filtered = filtered[filtered["Status"] == selected_status]
    filtered = apply_common_filters(filtered, prefix="view_")
    filtered = filtered.apply(lambda x: x.str.replace("\n", " ") if x.dtype == "object" else x)
    filtered = filtered.sort_values("Date of Inspection")
    
    st.write(f"🔹 Showing {len(filtered)} record(s) from **{start_date.strftime('%d.%m.%Y')}** "
             f"to **{end_date.strftime('%d.%m.%Y')}**")
    
    # Responsive metrics
    col_a, col_b = st.columns([1, 1])
    col_c, col_d = st.columns([1, 1])
    pending_count = (filtered["Status"] == "Pending").sum()
    no_response_count = filtered["Feedback"].isna().sum() + (filtered["Feedback"].astype(str).str.strip() == "").sum()
    resolved_count = (filtered["Status"] == "Resolved").sum()
    col_a.metric("🟨 Pending", pending_count)
    col_b.metric("⚠️ No Response", no_response_count)
    col_c.metric("🟩 Resolved", resolved_count)
    col_d.metric("📊 Total Records", len(filtered))
    
    # Sub Head Distribution (Simplified for mobile)
    if st.session_state.view_head_filter and not filtered.empty:
        st.markdown("### 📊 Sub Head Distribution")
        subhead_summary = (
            filtered.groupby("Sub Head")["Sub Head"]
            .count()
            .reset_index(name="Count")
            .sort_values(by="Count", ascending=False)
        )
        if not subhead_summary.empty:
            total_subs = subhead_summary["Count"].sum()
            display_data = subhead_summary.copy()
            thresh = 0.02
            display_data["Percent"] = display_data["Count"] / total_subs
            major = display_data[display_data["Percent"] >= thresh][["Sub Head", "Count"]]
            minor = display_data[display_data["Percent"] < thresh]
            if not minor.empty:
                major = pd.concat([major, pd.DataFrame([{"Sub Head": "Others", "Count": minor["Count"].sum()}])],
                                  ignore_index=True)
            
            fig, ax = plt.subplots(figsize=(8, 4))
            wedges, texts, autotexts = ax.pie(
                major["Count"], startangle=90, autopct='%1.1f%%',
                textprops=dict(color='black', fontsize=8)
            )
            ax.set_title("Sub Head Breakdown", fontsize=12)
            plt.tight_layout()
            buf = BytesIO()
            plt.savefig(buf, format="png", dpi=150)
            buf.seek(0)
            plt.close()
            st.image(buf, use_column_width=True)
            st.download_button("📥 Download Sub Head Distribution (PNG)", data=buf,
                               file_name="subhead_distribution.png", mime="image/png")
    
    # Export to Excel
    export_df = filtered[[
        "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
        "Deficiencies Noted", "Inspection By", "Action By", "Feedback", "User Feedback/Remark",
        "Status"
    ]].copy()
    export_df["Date of Inspection"] = pd.to_datetime(export_df["Date of Inspection"]).dt.date
    towb = BytesIO()
    with pd.ExcelWriter(towb, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Filtered Records")
        ws = writer.sheets["Filtered Records"]
        date_style = NamedStyle(name="date_style", number_format="DD-MM-YYYY")
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        date_col_idx = export_df.columns.get_loc("Date of Inspection") + 1
        for row in ws.iter_rows(min_row=2, min_col=date_col_idx, max_col=date_col_idx, max_row=len(export_df) + 1):
            for cell in row:
                cell.style = date_style
        for col in ws.columns:
            max_length = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except:
                    pass
            adjusted_width = (max_length + 2) if max_length < 30 else 30
            ws.column_dimensions[col_letter].width = adjusted_width
        thin_border = Border(left=Side(style='thin'),
                             right=Side(style='thin'),
                             top=Side(style='thin'),
                             bottom=Side(style='thin'))
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.border = thin_border
        status_col_idx = export_df.columns.get_loc("Status") + 1
        for row in ws.iter_rows(min_row=2, min_col=status_col_idx, max_col=status_col_idx, max_row=len(export_df) + 1):
            for cell in row:
                if str(cell.value).strip().lower() == "pending":
                    cell.font = Font(color="FF0000")
                elif str(cell.value).strip().lower() == "resolved":
                    cell.font = Font(color="008000")
    towb.seek(0)
    st.download_button(
        "📥 Export Filtered Records to Excel",
        data=towb,
        file_name="filtered_records.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    # ---------- EDITOR ----------
    st.markdown("### ✍️ Edit User Feedback/Remarks")
    if not filtered.empty:
        # Use JavaScript-detected mobile status
        is_mobile = st.session_state.get('is_mobile', 'false') == 'true'
        
        display_cols = [
            "Date of Inspection", "Location", "Head", "Deficiencies Noted",
            "User Feedback/Remark", "Status"
        ] if is_mobile else [
            "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
            "Deficiencies Noted", "Inspection By", "Action By", "Feedback", "User Feedback/Remark"
        ]
        valid_cols = [col for col in display_cols if col in filtered.columns]
        if not valid_cols:
            st.error("⚠️ No valid columns found.")
            st.stop()
        if "Deficiencies Noted" not in valid_cols:
            st.error("⚠️ 'Deficiencies Noted' column is required.")
            st.stop()
        editable_filtered = filtered.copy()
        editable_filtered["_original_sheet_index"] = editable_filtered.index
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
            editable_df["Status"] = editable_df["Status"].apply(color_text_status)
        
        # Global Search
        st.markdown("#### 🔍 Search and Filter")
        search_text = st.text_input("Search All Columns", "").strip().lower()
        if search_text:
            mask = editable_df[valid_cols].astype(str).apply(
                lambda col: col.str.contains(search_text, case=False, na=False)
            ).any(axis=1)
            editable_df = editable_df[mask].copy()
            st.info(f"Found {len(editable_df)} matching rows.")
        
        # Column Filtering
        max_cols = st.slider("Max columns to filter on", 1, len(valid_cols), min(3, len(valid_cols)), key="max_cols_filter")
        global column_selection
        column_selection = st.multiselect("Select columns to filter", valid_cols[:max_cols], key="column_select_filter")
        if column_selection:
            editable_df = filter_dataframe(editable_df)
            st.info(f"Applied filters to {len(editable_df)} rows.")
        
        if is_mobile:
            # Card-based layout for mobile
            st.markdown("#### 📋 Edit Records")
            st.caption("Tap to expand and edit each record.")
            for idx, row in editable_df.iterrows():
                with st.expander(f"Record {idx + 1}: {row['Location']} - {row['Status']}"):
                    st.markdown(f"<div class='card'>", unsafe_allow_html=True)
                    for col in valid_cols:
                        if col != "User Feedback/Remark":
                            st.markdown(f"<div class='card-field'><label>{col}:</label><p>{row[col]}</p></div>", unsafe_allow_html=True)
                    # Editable field
                    new_remark = st.text_area(
                        "User Feedback/Remark",
                        value=row["User Feedback/Remark"],
                        key=f"remark_{idx}",
                        height=100
                    )
                    editable_df.at[idx, "User Feedback/Remark"] = new_remark
                    st.markdown("</div>", unsafe_allow_html=True)
        else:
            # AgGrid Configuration for desktop
            gb = GridOptionsBuilder.from_dataframe(editable_df)
            gb.configure_default_column(editable=False, wrapText=True, autoHeight=True, resizable=True)
            if "User Feedback/Remark" in editable_df.columns:
                gb.configure_column(
                    "User Feedback/Remark",
                    editable=True,
                    wrapText=True,
                    autoHeight=True,
                    cellEditor="agTextCellEditor",
                    cellEditorPopup=False,
                    cellEditorParams={"maxLength": 4000}
                )
                gb.configure_column("User Feedback/Remark", pinned="left")
                gb.configure_column("Status", pinned="left")
            gb.configure_column("_original_sheet_index", hide=True)
            gb.configure_column("_sheet_row", hide=True)
            gb.configure_grid_options(singleClickEdit=False, enterMovesDown=True)
            auto_size_js = JsCode("""
            function(params) {
                let allColumnIds = [];
                params.columnApi.getAllColumns().forEach(function(column) {
                    if (!column.getColDef().pinned) {
                        allColumnIds.push(column.getColId());
                    }
                });
                params.columnApi.autoSizeColumns(allColumnIds);
                params.columnApi.setColumnWidths([
                    {key: 'User Feedback/Remark', newWidth: 200},
                    {key: 'Status', newWidth: 100}
                ]);
            }
            """)
            gb.configure_grid_options(onFirstDataRendered=auto_size_js)
            grid_options = gb.build()
            
            st.markdown("#### 📋 Editable Table")
            st.caption("Double-click 'User Feedback/Remark' to edit. Click headers to sort.")
            grid_response = AgGrid(
                editable_df,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.VALUE_CHANGED,
                height=400,
                allow_unsafe_jscode=True,
                fit_columns_on_grid_load=True
            )
            edited_df = pd.DataFrame(grid_response["data"])
        
        # Export Edited Records
        export_cols = [col for col in valid_cols if col not in ["_original_sheet_index", "_sheet_row"]] + ["Status"]
        export_edited_df = edited_df[export_cols].copy()
        export_edited_df["Date of Inspection"] = pd.to_datetime(export_edited_df["Date of Inspection"]).dt.date
        towb_edited = BytesIO()
        with pd.ExcelWriter(towb_edited, engine="openpyxl") as writer:
            export_edited_df.to_excel(writer, index=False, sheet_name="Edited Records")
            ws = writer.sheets["Edited Records"]
            date_style = NamedStyle(name="date_style", number_format="DD-MM-YYYY")
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
            date_col_idx = export_edited_df.columns.get_loc("Date of Inspection") + 1
            for row in ws.iter_rows(min_row=2, min_col=date_col_idx, max_col=date_col_idx, max_row=len(export_edited_df) + 1):
                for cell in row:
                    cell.style = date_style
            for col in ws.columns:
                max_length = 0
                col_letter = col[0].column_letter
                for cell in col:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                adjusted_width = (max_length + 2) if max_length < 30 else 30
                ws.column_dimensions[col_letter].width = adjusted_width
            thin_border = Border(left=Side(style='thin'),
                                 right=Side(style='thin'),
                                 top=Side(style='thin'),
                                 bottom=Side(style='thin'))
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
                for cell in row:
                    cell.border = thin_border
            status_col_idx = export_edited_df.columns.get_loc("Status") + 1
            for row in ws.iter_rows(min_row=2, min_col=status_col_idx, max_col=status_col_idx, max_row=len(export_edited_df) + 1):
                for cell in row:
                    if str(cell.value).strip().lower() == "pending":
                        cell.font = Font(color="FF0000")
                    elif str(cell.value).strip().lower() == "resolved":
                        cell.font = Font(color="008000")
        towb_edited.seek(0)
        st.download_button(
            label="📥 Export Edited Records to Excel",
            data=towb_edited,
            file_name=f"edited_records_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Buttons
        c1, c2 = st.columns([1, 1])
        submitted = c1.button("✅ Submit Feedback")
        if c2.button("🔄 Refresh Data"):
            st.session_state.df = load_data()
            st.success("✅ Data refreshed successfully!")
            st.rerun()
        
        # Submit logic
        if submitted:
            need_cols = {"_original_sheet_index", "User Feedback/Remark"}
            if not need_cols.issubset(edited_df.columns) or "Feedback" not in editable_filtered.columns:
                st.error("⚠️ Required columns are missing.")
            else:
                orig = editable_filtered.set_index("_original_sheet_index")
                new = edited_df.set_index("_original_sheet_index")
                old_remarks = orig["User Feedback/Remark"].fillna("").astype(str)
                new_remarks = new["User Feedback/Remark"].fillna("").astype(str)
                common_ids = new_remarks.index.intersection(old_remarks.index)
                diff_mask = new_remarks.loc[common_ids] != old_remarks.loc[common_ids]
                changed_ids = diff_mask[diff_mask].index.tolist()
                if changed_ids:
                    diffs = new.loc[changed_ids].copy()
                    diffs["_sheet_row"] = orig.loc[changed_ids, "_sheet_row"].values
                    routing = {
                        "OPTG": ("OPTG", "Sr.DOM"),
                        "S&T": ("SIGNAL & TELECOM", "Sr.DSTE"),
                        "COMMERCIAL": ("COMMERCIAL", "Sr.DCM"),
                        "ELECT/G": ("ELECT/G", "Sr.DEE/G"),
                        "MECHANICAL": ("MECHANICAL", "Sr.DME"),
                        "ELECT/TRD": ("ELECT/TRD", "Sr.DEE/TRD"),
                        "ELECT/TRO": ("ELECT/TRO", "Sr.DEE/TRO"),
                        "Sr.DEN/S": ("ENGINEERING", "Sr.DEN/S"),
                        "Sr.DEN/C": ("ENGINEERING", "Sr.DEN/C"),
                        "FINAINCE": ("FINANCE", "Sr.DFM"),
                        "STORE": ("STORE", "Sr.DMM"),
                        "MEDICAL": ("MEDICAL", "CMS"),
                        "SECURITY": ("SECURITY", "DSC")
                    }
                    for oid in changed_ids:
                        user_remark = new.loc[oid, "User Feedback/Remark"].strip()
                        if not user_remark:
                            continue
                        for key, (head, action_by) in routing.items():
                            if key in user_remark:
                                st.session_state.df.at[oid, "Head"] = head
                                st.session_state.df.at[oid, "Action By"] = action_by
                                st.session_state.df.at[oid, "Sub Head"] = ""
                                diffs.at[oid, "Head"] = head
                                diffs.at[oid, "Action By"] = action_by
                                diffs.at[oid, "Sub Head"] = ""
                                date_str = orig.loc[oid, "Date of Inspection"]
                                deficiency = orig.loc[oid, "Deficiencies Noted"]
                                forwarded_by = orig.loc[oid, "Head"]
                                alert_msg = (
                                    f"📌 **{head} Department Alert**\n"
                                    f"- Date: {date_str}\n"
                                    f"- Deficiency: {deficiency}\n"
                                    f"- Forwarded By: {forwarded_by}\n"
                                    f"- Forwarded Remark: {user_remark}"
                                )
                                st.session_state.alerts_log.insert(0, alert_msg)
                        diffs.at[oid, "Feedback"] = user_remark
                        diffs.at[oid, "User Feedback/Remark"] = ""
                        st.session_state.df.at[oid, "Feedback"] = user_remark
                        st.session_state.df.at[oid, "User Feedback/Remark"] = ""
                    update_feedback_column(
                        diffs.reset_index().rename(columns={"index": "_original_sheet_index"})
                    )
                    st.success(f"✅ Updated {len(changed_ids)} Feedback row(s).")
                else:
                    st.info("ℹ️ No changes detected.")
    else:
        st.info("Deficiencies will be updated soon!")

# ---------------- ALERT LOG SECTION ----------------
st.markdown("## 📋 Alerts Log")
if st.session_state.alerts_log:
    for i, log in enumerate(st.session_state.alerts_log):
        with st.expander(f"🔔 Alert {i+1}", expanded=False):
            st.markdown(log, unsafe_allow_html=True)
            if st.button("Mark as Read", key=f"mark_{i}"):
                st.session_state.alerts_log.pop(i)
                st.session_state.last_alert_clicked = i
                st.rerun()

if "last_alert_clicked" in st.session_state:
    st.markdown(
        """
        <script>
            var el = window.document.querySelector('details');
            if (el) {
                el.scrollIntoView({behavior: "smooth", block: "start"});
            }
        </script>
        """,
        unsafe_allow_html=True
    )
    del st.session_state.last_alert_clicked
else:
    st.info("✅ No pending alerts.")

# -------------------- FOOTER --------------------
st.markdown(
    """
    <div style="text-align: center; margin: 20px 0;">
        <p style="color:red;font-weight:bold;font-size:0.9rem;">
            For any correction in data, contact Safety Department on sursafetyposition@gmail.com, Contact: Rly phone no. 55620, Cell: +91 9022507772
        </p>
    </div>
    """,
    unsafe_allow_html=True
)
st.markdown("""
**Use the following syntax to forward attention to other department:**
- For Operating: Pertains to **OPTG**
- For Signal & Telecom: Pertains to **S&T**
- For Commercial: Pertains to **COMMERCIAL**
- For ELECT/G: Pertains to **ELECT/G**
- For MECHANICAL: Pertains to **MECHANICAL**
- For ELECT/TRD: Pertains to **ELECT/TRD**
- For ELECT/TRO: Pertains to **ELECT/TRO**
- For Engineering South: Pertains to **Sr.DEN/S**
- For Engineering North: Pertains to **Sr.DEN/C**
- For Finance Department: Pertains to **FINAINCE**
- For Store Department: Pertains to **STORE**
- For Medical Department: Pertains to **MEDICAL**
- For Security Department: Pertains to **SECURITY**
""")
st.markdown("""
<div style="text-align: center; margin: 20px 0;">
  <div class="adaptive-credit">
    <p>
      <strong>Designed & Developed by</strong>
      <span class="highlight">Safety Department</span>,
      <em>Solapur Division</em>
    </p>
  </div>
</div>
""", unsafe_allow_html=True)

# Analytics Tab
with tabs[1]:
    st.markdown("### Total Deficiencies Trend")
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
        df["Head_clean"] = df["Head"].apply(clean_name)
        dept_map = {
            "ELECT/TRD": "ELECT/TRD",
            "ELECT/G": "ELECT/G",
            "ELECT/TRO": "ELECT/TRO",
            "SIGNAL & TELECOM": "SIGNAL & TELECOM",
            "OPTG": "OPERATING",
            "MECHANICAL": "MECHANICAL",
            "ENGINEERING": "ENGINEERING",
            "COMMERCIAL": "COMMERCIAL",
            "C&W": "CARRIAGE & WAGON",
            "PERSONNEL": "PERSONNEL",
            "SECURITY": "SECURITY",
            "FINANCE": "FINANCE",
            "MEDICAL": "MEDICAL",
            "STORE": "STORE",
            "": "UNKNOWN"
        }
        df["Head_std"] = df["Head_clean"].map(dept_map).fillna("UNKNOWN")
        df["Location_clean"] = df["Location"].astype(str).apply(clean_name)
        STATIONS_NORM = {clean_name(x) for x in STATION_LIST}
        df["Is_Station"] = df["Location_clean"].isin(STATIONS_NORM)
        
        # Trend chart
        trend = df.groupby(pd.Grouper(key="Date of Inspection", freq="M")).size().reset_index(name="TotalCount")
        if not trend.empty:
            trend = trend.sort_values("Date of Inspection")
            trend["Month"] = trend["Date of Inspection"].dt.strftime("%b-%Y")
            bars = alt.Chart(trend).mark_bar(color="#1f77b4", cornerRadius=2).encode(
                x=alt.X("Month:O", title="Month", sort=trend["Month"].tolist(), axis=alt.Axis(labelAngle=45, labelFontSize=10)),
                y=alt.Y("TotalCount:Q", title="Total Deficiencies"),
                tooltip=["Month", "TotalCount"]
            ).properties(width="container")
            line = alt.Chart(trend).transform_regression("Date of Inspection", "TotalCount").mark_line(
                color="red", strokeDash=[4, 2], strokeWidth=2
            ).encode(x="Month:O", y="TotalCount:Q")
            st.altair_chart(bars + line, use_container_width=True)
        else:
            st.info("No data in selected range.")
        
        # Department summary
        st.markdown("### Department-wise Total Deficiencies")
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
        ).properties(height=300)
        st.altair_chart(dept_chart, use_container_width=True)
        
        # Top 3 stations
        st.markdown("### Top 3 Stations")
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
            ).properties(height=200, width="container")
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No station data found.")
        
        # Location filter
        st.markdown("### Department-wise Breakdown")
        all_locations = sorted(df["Location_clean"].dropna().unique())
        selected_locations = st.multiselect(
            "Select Locations",
            options=all_locations,
            default=all_locations[:5] if len(all_locations) > 5 else all_locations
        )
        if selected_locations:
            filtered = df[df["Location_clean"].isin(selected_locations)].copy()
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
            x=alt.X("TotalCount:Q", title="Total Deficiencies"),
            y=alt.Y("Head_std:N", title="Department", sort="-x"),
            tooltip=[
            "Head_std",
            alt.Tooltip("TotalCount", title="Total", format=","),
            alt.Tooltip("Point", title="Pending", format=","),  # Error here
            alt.Tooltip("ResolvedCount", title="Resolved", format=",")
                    ]
            ).properties(
                            height=max(200, len(summary_df) * 30)
                        )
            text = bar_chart.mark_text(
                align="left",
                baseline="middle",
                dx=3,
                fontWeight="bold",
                color="black"
            ).encode(
                text=alt.Text("TotalCount:Q", format=",")
            )
            st.altair_chart((bar_chart + text), use_container_width=True)
            total = summary_df["TotalCount"].sum()
            pending = summary_df["PendingCount"].sum()
            resolved = summary_df["ResolvedCount"].sum()
            st.markdown(
                f"**Total Deficiencies:** {total:,} | "
                f"**Pending:** {pending:,} | "
                f"**Resolved:** {resolved:,}"
            )
            st.markdown("**Department-wise Breakdown:**")
            for _, row in summary_df.iterrows():
                st.markdown(
                    f"- **{row['Head_std']}**: **Total:** {row['TotalCount']:,} | "
                    f"**Pending:** {row['PendingCount']:,} | "
                    f"**Resolved:** {row['ResolvedCount']:,}"
                )
        else:
            st.info("Please select at least one location.")

