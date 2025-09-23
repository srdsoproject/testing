import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode
import os
import requests
import re
import io
from io import BytesIO
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from openpyxl.styles import Alignment
import streamlit as st

# -------------------- CONSTANTS (DEDUPED) --------------------
# Use dict.fromkeys(...) to preserve order while removing duplicates
STATION_LIST = list(dict.fromkeys([
    'BRB','MLM','BGVN','JNTR','PRWD','WSB','PPJ','JEUR','KEM','BLNI','DHS','KWV','WDS','MA','AAG',
    'MKPT','MO','MVE','PK','BALE',"SUR",'TKWD','HG','TLT','AKOR','NGS','BOT','DUD','KUI','GDGN','GUR',
    'HHD','SVG','BBD','TJSP','KLBG','HQR','MR','SDB','WADI','ARAG','BLNK','SGRE','KVK','LNP','DLGN',
    'JTRD','MSDG','JVA','WSD','SGLA','PVR','MLB','SEI','BTW','PJR','DRSV','YSI','KMRD','DKY','MRX',
    'OSA','HGL','LUR','NTPC','MRJ','BHLI'
]))

GATE_LIST = list(dict.fromkeys([
    'LC-19','LC-22A','LC-25','LC-26','LC-27C','LC-28','LC-30','LC-31','LC-35','LC-37','LC-40','LC-41',
    'LC-43','LC-44','LC-45','LC-46C','LC-54','LC-61','LC-66','LC-74','LC-76','LC-78','LC-82','LC-1',
    'LC-60A','LC-1 TLT ZCL','LC-1 ACC','LC-2 ACC','LC-91','LC-22','LC-24','LC-32','LC-49','LC-70',
    'LC-10','LC-34','LC-36','LC-47','LC-55','LC-59','LC-2','LC-4','LC-42','LC-02','LC-128','LC-63',
    'LC-04','LC-67','LC-77','LC-75','LC-64','LC-65','LC-5','LC-6','LC-57','LC-62','LC-39','LC-2/C',
    'LC-6/C','LC-11','LC-03','LC-15/C','LC-21','LC-26-A','LC-60'
]))

FOOTPLATE_ROUTES = ["SUR-DD","SUR-WADI","LUR-KWV",'KWV-MRJ','DD-SUR','WADI-SUR','KWV-LUR','MRJ-KWV']

HEAD_LIST = ["", "ELECT/TRD", "ELECT/G", "ELECT/TRO", "SIGNAL & TELECOM", "OPTG","MECHANICAL",
             "ENGINEERING", "COMMERCIAL", "C&W", 'PERSONNEL', 'SECURITY', "FINANCE", "MEDICAL", "STORE"]

SUBHEAD_LIST = {
    "ELECT/TRD": ["T/W WAGON", "TSS/SP/SSP", "OHE SECTION", "OHE STATION", "MISC"],
    "ELECT/G": ["TL/AC COACH", "POWER/PANTRY CAR", "WIRING/EQUIPMENT", "UPS", "AC", "DG", "SOLAR LIGHT", "MISC"],
    "ELECT/TRO": ["LOCO DEFECTS", "RUNNING ROOM DEFICIENCIES", "LOBBY DEFICIENCIES", "LRD RELATED", "PERSONAL STORE", "PR RELATED",
                  "CMS", "MISC"],
    "MECHANICAL":["MISC"],
    "SIGNAL & TELECOM": [ "SIGNAL PUTBACK/BLANK", "OTHER SIGNAL FAILURE", "BPAC", "GATE", "RELAY ROOM",
                         "STATION(VDU/BLOCK INSTRUMENT)", "MISC", "CCTV", "DISPLAY BOARDS"],
    "OPTG": [ "SWR/CSR/CSL/TWRD", "COMPETENCY RELATED", "STATION RECORDS", "STATION DEFICIENCIES",
             "SM OFFICE DEFICIENCIES", "MISC"],
    "ENGINEERING": [ "IOW WORKS","GSU","ROUGH RIDING", "TRACK NEEDS ATTENTION", "MISC"],
    "COMMERCIAL": [ "TICKETING RELATED/MACHINE", "IRCTC", "MISC"],
    "C&W": [ "BRAKE BINDING", 'WHEEL DEFECT', 'TRAIN PARTING', 'PASSENGER AMENITIES', 'AIR PRESSURE LEAKAGE',
            'DAMAGED UNDER GEAR PARTS', 'MISC'],
    "FINANCE":["MISC"], "MEDICAL":["MISC"], "STORE": ["MISC"],
}

INSPECTION_BY_LIST = [""] + ["HQ OFFICER CCE/CR",'DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                             'Sr.DEE/TRD', 'Sr.DEE/G','Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC',
                             'DME,DEE/TRD', 'DFM', 'DSTE/HQ', 'DSTE/KLBG', 'ADEN/T/SUR', 'ADEN/W/SUR', 'ADEN/KWV',
                             'ADEN/PVR', 'ADEN/LUR', 'ADEN/KLBG', 'ADSTE/SUR', 'ADSTE/I/KWV', 'ADSTE/II/KWV',
                             'ADME/SUR', 'AOM/GD', 'AOM/GEN', 'ACM/Cog', 'ACM/TC', 'ACM/GD', 'APO/GEN', 'APO/WEL',
                             'ADFM/I', 'ADFMII', 'ASC', 'ADSO/SUR']

ACTION_BY_LIST = [""] + ['DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                         'Sr.DEE/TRD', 'Sr.DEE/G','Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC', 'CMS']

VALID_INSPECTIONS = [
    "FOOTPLATE INSPECTION", "STATION INSPECTION", "LC GATE INSPECTION",
    "MISC", "COACHING DEPOT", "ON TRAIN", "SURPRISE/AMBUSH INSPECTION", "WORKSITE INSPECTION", "OTHER (UNUSUAL)",
]

FOOTPLATE_LIST = STATION_LIST + GATE_LIST + FOOTPLATE_ROUTES

# -------------------- HELPERS --------------------
def normalize_str(text):
    if not isinstance(text, str):
        return ""
    return re.sub(r'\s+', ' ', text.lower()).strip()

def classify_feedback(feedback, user_remark=""):
    # Empty backtick = clear
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
             "updated by", "adv to", "counselled the staff", "complied", "checked and found",
            "maintained", "for needful action", "provided at", "in working condition", "is working", "this is not a deficiency", "not deficiency", "it is observation", 
            "found working", "equipment is working", "item is working", "as per plan", "putright", "put right",
            "operational feasibility", "will be provided", "will be supplied shortly", "advised to ubl", "updated", "letter has been sent", "letter has been given"
        ]

        pending_kw = [
            "work is going on", "tdc given", "target date", "expected by", "likely by", "planned by",
            "will be", "needful", "to be", "pending", "not done", "awaiting", "waiting", "yet to", "next time",
            "follow up", "tdc.", "tdc", "t d c", "will attend", "will be attended", "scheduled", "reminder",
            "to inform", "to counsel", "to submit", "to do", "to replace", "prior", "remains", "still",
            "under process", "not yet", "to be done", "will ensure", "during next", "action will be taken",
            "will be supplied shortly", "not available", "not updated", "progress", "under progress", 'noted please', 'noted please. tdc',
            "to arrange", "awaited", "material awaited", "approval awaited", "to procure", "yet pending", "Noted Please.",
            "incomplete", "tentative", "ongoing", "in progress", "being done", "arranging", "waiting for",
            "subject to", "awaiting approval", "awaiting material", "awaiting confirmation", "next schedule",
            "planned for", "will arrange", "proposed date", "to complete", "to be completed",
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

    # marker override
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
# ---------- CONFIG ----------
st.set_page_config(page_title="Inspection App", layout="wide")

LOCAL_FILE = "responses_local.xlsx"
GITHUB_RAW_URL = "https://github.com/srdsoproject/testing/raw/main/responses.xlsx"

# ---------- SESSION STATE ----------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = {}
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()
if "alerts_log" not in st.session_state:
    st.session_state.alerts_log = []

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

# ---------- HELPER FUNCTIONS ----------
def load_data():
    """Load data from local file or GitHub if missing"""
    if os.path.exists(LOCAL_FILE):
        df = pd.read_excel(LOCAL_FILE)
    else:
        resp = requests.get(GITHUB_RAW_URL)
        resp.raise_for_status()
        df = pd.read_excel(BytesIO(resp.content))

    # Ensure required columns
    REQUIRED_COLS = [
        "Date of Inspection", "Type of Inspection", "Location",
        "Head", "Sub Head", "Deficiencies Noted",
        "Inspection By", "Action By", "Feedback",
        "User Feedback/Remark"
    ]
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = ""

    # Convert "Date of Inspection" to datetime, keep only date
    # After loading your dataframe
    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce").dt.strftime("%Y-%m-%d")


    # Helper columns for AG-Grid
    if "_sheet_row" not in df.columns:
        df["_sheet_row"] = df.index + 2
    if "_original_sheet_index" not in df.columns:
        df["_original_sheet_index"] = df.index

    # Ensure string type for feedback fields
    df["Feedback"] = df["Feedback"].fillna("").astype(str)
    df["User Feedback/Remark"] = df["User Feedback/Remark"].fillna("").astype(str)

    return df


def save_to_local_excel(df):
    df.to_excel(LOCAL_FILE, index=False)

def classify_feedback(feedback):
    val = "" if pd.isna(feedback) else str(feedback)
    return "Pending" if val.strip() == "" else "Resolved"

def get_status(feedback, remark):
    return classify_feedback(feedback)

def color_text_status(status):
    return "🔴 Pending" if status == "Pending" else ("🟢 Resolved" if status == "Resolved" else status)
def apply_common_filters(df, prefix=""):
    with st.expander("🔍 Apply Additional Filters", expanded=True):
        c1, c2 = st.columns(2)
        c1.multiselect("Inspection By", INSPECTION_BY_LIST[1:], 
                       default=st.session_state.get(prefix+"insp", []), key=prefix+"insp")
        c2.multiselect("Action By", ACTION_BY_LIST[1:], 
                       default=st.session_state.get(prefix+"action", []), key=prefix+"action")

        d1, d2 = st.columns(2)
        d1.date_input("📅 From Date", key=prefix+"from_date")
        d2.date_input("📅 To Date", key=prefix+"to_date")

    out = df.copy()

    # --- Filter by "Inspection By"
    if st.session_state.get(prefix+"insp"):
        sel = st.session_state[prefix+"insp"]
        out = out[out["Inspection By"].apply(
            lambda x: any(s.strip() in str(x).split(",") for s in sel)
        )]

    # --- Filter by "Action By"
    if st.session_state.get(prefix+"action"):
        sel = st.session_state[prefix+"action"]
        out = out[out["Action By"].apply(
            lambda x: any(s.strip() in str(x).split(",") for s in sel)
        )]

    # --- Filter by Date Range (using "Date of Inspection")
    if st.session_state.get(prefix+"from_date") and st.session_state.get(prefix+"to_date"):
        from_date = st.session_state[prefix+"from_date"]
        to_date   = st.session_state[prefix+"to_date"]
        out = out[
            (out["Date of Inspection"] >= pd.to_datetime(from_date)) &
            (out["Date of Inspection"] <= pd.to_datetime(to_date))
        ]

    return out


# -------------------- HEADER --------------------
st.markdown(
    """
    <div style="display:flex;align-items:center;margin-top:10px;margin-bottom:20px;">
        <img src="https://raw.githubusercontent.com/srdsoproject/testing/main/Central%20Railway%20Logo.png"
             height="55" style="margin-right:15px;object-fit:contain;">
        <div>
            <h3 style="margin:0;font-weight:bold;color:var(--text-color);">
                An initiative by <b>Safety Department</b>, Solapur Division
            </h3>
        </div>
    </div>
    <h1 style="margin-top:0;color:var(--text-color);">📋 S.A.R.A.L</h1>
    <h3 style="margin-top:-10px;font-weight:normal;color:var(--text-color);">
        (Safety Abnormality Report & Action List – Version 1.1.8)
    </h3>
    """,
    unsafe_allow_html=True
)
tabs = st.tabs(["📊 View Records"])
with tabs[0]:
    if df.empty:
        st.warning("Deficiencies will be updated soon !")
        st.stop()

    # Ensure required cols
    for col in ["Type of Inspection","Location","Head","Sub Head","Deficiencies Noted",
                "Inspection By","Action By","Feedback","User Feedback/Remark"]:
        if col not in df.columns:
            df[col] = ""

    # Format date to yyyy-mm-dd
    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce").dt.date
    df["_original_sheet_index"] = df.index
    df["Status"] = df.apply(lambda r: get_status(r["Feedback"], r.get("User Feedback/Remark","")), axis=1)

    # ---------------- FILTERS ----------------
    start_date = df["Date of Inspection"].min()
    end_date   = df["Date of Inspection"].max()

    c1, c2 = st.columns(2)
    c1.multiselect("Type of Inspection", VALID_INSPECTIONS, key="view_type_filter")
    c2.multiselect("Location", FOOTPLATE_LIST, key="view_location_filter")

    c3, c4 = st.columns(2)
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

    # Replace newlines
    filtered = filtered.applymap(lambda x: x.replace("\n"," ") if isinstance(x,str) else x)
    filtered = filtered.sort_values("Date of Inspection")

    st.write(f"🔹 Showing {len(filtered)} record(s) from **{start_date}** to **{end_date}**")

    # ---------------- METRICS ----------------
    col_a, col_b, col_c, col_d = st.columns(4)
    pending_count = (filtered["Status"]=="Pending").sum()
    no_response_count = filtered["Feedback"].isna().sum() + (filtered["Feedback"].astype(str).str.strip()=="").sum()
    resolved_count = (filtered["Status"]=="Resolved").sum()
    col_a.metric("🟨 Pending", pending_count)
    col_b.metric("⚠️ No Response", no_response_count)
    col_c.metric("🟩 Resolved", resolved_count)
    col_d.metric("📊 Total Records", len(filtered))
# ---------- LOAD DATA ----------
if st.session_state.df.empty:
    st.session_state.df = load_data()
df_main = st.session_state.df.copy()

st.markdown("### ✍️ Edit User Feedback / Remarks")

# ---------- PREPARE EDITABLE DF ----------
editable_df = df_main.copy()
editable_df["User Feedback/Remark"] = editable_df.get("User Feedback/Remark", "").fillna("").astype(str)
editable_df["Feedback"] = editable_df.get("Feedback", "").fillna("").astype(str)
editable_df["Status"] = editable_df.apply(
    lambda r: color_text_status(get_status(r["Feedback"], r["User Feedback/Remark"])),
    axis=1
)

# ---------- AG-GRID CONFIG ----------
gb = GridOptionsBuilder.from_dataframe(editable_df)
gb.configure_default_column(editable=False, wrapText=True, autoHeight=True, resizable=True)
gb.configure_column(
    "User Feedback/Remark",
    editable=True,
    wrapText=True,
    autoHeight=True,
    cellEditor="agTextCellEditor",
    cellEditorPopup=False,
    cellEditorParams={"maxLength": 4000},
)
gb.configure_column("_original_sheet_index", hide=True)
gb.configure_column("_sheet_row", hide=True)

# Auto-size columns
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

grid_response = AgGrid(
    editable_df,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.VALUE_CHANGED,
    height=600,
    allow_unsafe_jscode=True
)
edited_df = pd.DataFrame(grid_response["data"])

# ---------- BUTTONS ----------
c1, c2, _ = st.columns([1,1,1])

# Submit Feedback
if c1.button("✅ Submit Feedback"):
    if "_original_sheet_index" not in edited_df.columns:
        st.error("⚠️ Cannot find original row index. Please refresh.")
    else:
        changes = 0
        df_main = st.session_state.df.copy()

        # Only update rows with non-empty User Feedback/Remark
        edited_rows = edited_df[edited_df["User Feedback/Remark"].astype(str).str.strip() != ""]
        for _, row in edited_rows.iterrows():
            idx = int(row["_original_sheet_index"])
            new_remark = str(row["User Feedback/Remark"]).strip()
            if new_remark:
                df_main.at[idx, "Feedback"] = new_remark  # Update Feedback
                df_main.at[idx, "User Feedback/Remark"] = ""  # Clear edit field
                changes += 1

        if changes > 0:
            save_to_local_excel(df_main)
            st.session_state.df = df_main
            st.success(f"✅ Updated {changes} feedback row(s).")
            st.rerun()
        else:
            st.info("ℹ️ No new feedback to submit.")

# Refresh Data
if c2.button("🔄 Refresh Data"):
    st.session_state.df = load_data()
    st.success("✅ Data refreshed successfully!")
    st.rerun()




# ---------- ALERT LOG ----------
st.markdown("## 📋 Alerts Log")
if st.session_state.alerts_log:
    for i, log in enumerate(st.session_state.alerts_log):
        with st.expander(f"🔔 Alert {i+1}", expanded=True):
            st.markdown(log, unsafe_allow_html=True)
            if st.button("Mark as Read", key=f"mark_{i}"):
                st.session_state.alerts_log.pop(i)
                st.rerun()
else:
    st.info("✅ No pending alerts.")

# ---------- FOOTER ----------
st.markdown("""
<marquee behavior="scroll" direction="left" style="color:red;font-weight:bold;font-size:16px;">
    For any correction in data, contact Safety Department on sursafetyposition@gmail.com, Contact: Rly phone no. 55620, Cell: +91 9022507772
</marquee>
""", unsafe_allow_html=True)



























