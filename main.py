import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from io import BytesIO
from matplotlib import pyplot as plt

# ---------- CONFIG ----------
st.set_page_config(page_title="Inspection App", layout="wide")

# ---------- LOGIN ----------
def login(email, password):
    try:
        users = st.secrets["users"]
        for user in users:
            if user["email"] == email and user["password"] == password:
                return user
        return None
    except KeyError:
        st.error("⚠️ No users found in secrets.toml — please check your [[users]] block.")
        st.stop()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = {}

if not st.session_state.logged_in:
    st.title("🔐 Login to S.A.R.A.L (Safety Abnormality Report & Action List)")
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

# ---------- GOOGLE SHEETS CONNECTION ----------
import streamlit as st
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials

# ---------- STEP 1: CONNECT TO GOOGLE SHEETS ----------
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
station_list = ['BRB', 'MLM', 'BGVN', 'JNTR', 'PRWD', 'WSB', 'PPJ', 'JEUR', 'KEM', 'BLNI', 'DHS', 'KWV', 'WDS',
                'MA', 'AAG', 'MKPT', 'MO', 'MVE', 'PK', 'BALE', "SUR", 'TKWD', 'HG', 'TLT', 'AKOR', 'NGS', 'BOT', 'DUD',
                'KUI', 'GDGN', 'GUR', 'HHD', 'SVG', 'BBD', 'TJSP', 'KLBG', 'HQR', 'MR', 'SDB', 'WADI', 'ARAG',
                'BLNK', 'SGRE', 'KVK', 'LNP', 'DLGN', 'JTRD', 'MSDG', 'JVA', 'WSD', 'SGLA', 'PVR', 'MLB', 'SEI', 'BTW',
                'PJR', 'DRSV', 'YSI', 'KMRD', 'DKY', 'MRX', 'OSA', 'HGL', 'LUR', 'NTPC', 'MRJ', 'BHLI', 'NTPC' ]
footplate_list = ["SUR-DD", "SUR-WADI", "LUR-KWV", 'KWV-MRJ', 'DD-SUR', 'WADI-SUR', 'KWV-LUR', 'MRJ-KWV']
gate_list = ['LC-19', 'LC-22A', 'LC-25', 'LC-26', 'LC-27C', 'LC-28', 'LC-30', 'LC-31', 'LC-35', 'LC-37', 'LC-40',
             'LC-41', 'LC-43', 'LC-44', 'LC-45', 'LC-46C', 'LC-54', 'LC-61', 'LC-66', 'LC-74', 'LC-76', 'LC-78',
             'LC-82', 'LC-1', 'LC-60A', 'LC-1 TLT ZCL', 'LC-1 ACC', 'LC-2 ACC', 'LC-91', 'LC-22', 'LC-24', 'LC-31',
             'LC-32', 'LC-49', 'LC-70', 'LC-10', 'LC-34', 'LC-36', 'LC-44', 'LC-47', 'LC-55', 'LC-59', 'LC-2', 
             'LC-4', 'LC-42', 'LC-02', 'LC-31', 'LC-128', 'LC-63', 'LC-04', 'LC-67', 'LC-77','LC-75', 'LC-64','LC-65',
             'LC-5', 'LC-6', 'LC-57', 'LC-62', 'LC-66', 'LC-70', 'LC-39', 'LC-2/C', 'LC-6/C', 'LC-10', 'LC-11', 'LC-03',
             'LC-15/C', 'LC-21', 'LC-26-A', 'LC-34', 'LC-36', 'LC-44', 'LC-47', 'LC-55', 'LC-57', 'LC-59', 'LC-60',
             'LC-61']
HEAD_LIST = ["", "ELECT/TRD", "ELECT/G", "ELECT/TRO", "SIGNAL & TELECOM", "OPTG","MECHANICAL",
             "ENGINEERING", "COMMERCIAL", "C&W", 'PERSONNEL', 'SECURITY']
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
}
INSPECTION_BY_LIST = [""] + ["HQ OFFICER CCE/CR",'DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                             'Sr.DEE/TRD', 'Sr.DEE/G','Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC',
                             'DME,DEE/TRD', 'DFM', 'DSTE/HQ', 'DSTE/KLBG', 'ADEN/T/SUR', 'ADEN/W/SUR', 'ADEN/KWV',
                             'ADEN/PVR', 'ADEN/LUR', 'ADEN/KLBG', 'ADSTE/SUR', 'ADSTE/I/KWV', 'ADSTE/II/KWV',
                             'ADME/SUR', 'AOM/GD', 'AOM/GEN', 'ACM/Cog', 'ACM/TC', 'ACM/GD', 'APO/GEN', 'APO/WEL',
                             'ADFM/I', 'ADFMII', 'ASC', 'ADSO']
ACTION_BY_LIST = [""] + ['DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                         'Sr.DEE/TRD', 'Sr.DEE/G','Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC']

# ---------- HELPER FUNCTIONS ----------
def normalize(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

import re

def classify_feedback(feedback, user_remark=""):
    def normalize(text):
        return text.lower().strip()

    def classify_single(text):
        if not isinstance(text, str) or text.strip() == "":
            return ""
        return normalize(text)

    # NEW: Clear feedback trigger
    if isinstance(feedback, str) and feedback.strip() == "`":
        return ""  # This will leave the cell blank

    feedback_normalized = classify_single(feedback)
    remark_normalized = classify_single(user_remark)

    # Combine to preserve order
    combined_text = f"{feedback_normalized} {remark_normalized}".strip()

    # Step 1: Latest symbol override
    last_marker_match = re.findall(r"[!#]", combined_text)
    if last_marker_match:
        last_marker = last_marker_match[-1]
        if last_marker == "#":
            return "Resolved"
        elif last_marker == "!":
            return "Pending"

    def run_classification(text_normalized):
        date_found = bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text_normalized))

        resolved_keywords = [
            "attended", "solved", "done", "completed",  "confirmed by", "message given",
            "tdc work completed", "replaced", "msg given", "msg sent", "counseled", "info shared", "communicated", "sent successfully",
            "counselled", "gate will be closed soon", "attending at the time", "handled", "resolved", "action taken",
            "spoken to", "warned", "counselling", "hubli", "working normal", "met", "discussion held", "report sent",
            "notified", "explained", "nil", "na", "tlc", "work completed", "acknowledged", "visited", "briefed",
            "guided", "handover", "working properly", "checked found working", "supply restored", "noted please",
            "updated by", "adv to", "counselled the staff", "complied", "checked and found", "maintained",
            "for needful action", "provided at", "in working condition", "is working", "found working",
            "equipment is working", "item is working", "as per plan", "putright", "put right", "operational feasibility",
            "will be provided", "will be supplied shortly", "advised to ubl", "updated"
        ]

        pending_keywords = [
            "work is going on", "tdc given", "target date", "expected by", "likely by", "planned by",
            "will be", "needful", "to be", "pending", "not done", "awaiting", "waiting", "yet to", "next time",
            "follow up", "tdc.", "tdc", "t d c", "will attend", "will be attended", "scheduled", "reminder", "to inform",
            "to counsel", "to submit", "to do", "to replace", "prior", "remains", "still", "under process", "not yet",
            "to be done", "will ensure", "during next", "action will be taken", "will be supplied shortly", "not available",
            "not updated", "progress", "under progress", "to arrange", "awaited", "material awaited", "approval awaited",
            "to procure", "yet pending", "incomplete", "tentative", "ongoing", "in progress", "being done",
            "arranging", "waiting for", "subject to", "awaiting approval", "awaiting material", "awaiting confirmation",
            "next schedule", "planned for", "will arrange", "proposed date", "to complete", "to be completed",
            "likely completion", "expected completion", "not received", "awaiting response"
        ]

        # If TDC present and resolved keyword also present → Resolved
        if "tdc" in text_normalized and any(kw in text_normalized for kw in resolved_keywords):
            return "Resolved"

        if any(kw in text_normalized for kw in pending_keywords):
            return "Pending"

        if date_found:
            if "tdc" in text_normalized:
                return "Pending"
            return "Resolved"

        if any(kw in text_normalized for kw in resolved_keywords):
            return "Resolved"

        return None

    # Step 2: Fallback to normal classification if no !/# found
    feedback_result = run_classification(feedback_normalized)
    remark_result = run_classification(remark_normalized)

    if feedback_result == "Resolved" or remark_result == "Resolved":
        return "Resolved"
    if feedback_result == "Pending" or remark_result == "Pending":
        return "Pending"

    return "Pending"



# ---------- LOAD DATA ----------
@st.cache_data(ttl=0)
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
        st.error(f"❌ Error loading Google Sheet: {e}")
        return pd.DataFrame(columns=REQUIRED_COLS)

# ---------- SESSION STATE ----------
if "df" not in st.session_state:
    st.session_state.df = load_data()

df = st.session_state.df

# ---------- ADD STATUS COLUMN ----------

# ---------- UPDATE FEEDBACK ----------
def update_feedback_column(edited_df):
    header = sheet.row_values(1)

    # Get column indices (+1 because gspread is 1-based)
    try:
        feedback_col = header.index("Feedback") + 1
    except ValueError:
        st.error("⚠️ 'Feedback' column not found")
        return

    try:
        remark_col = header.index("User Feedback/Remark") + 1
    except ValueError:
        st.error("⚠️ 'User Feedback/Remark' column not found")
        return

    try:
        head_col = header.index("Head") + 1
    except ValueError:
        st.error("⚠️ 'Head' column not found")
        return

    try:
        action_by_col = header.index("Action By") + 1
    except ValueError:
        st.error("⚠️ 'Action By' column not found")
        return

    try:
        sub_head_col = header.index("Sub Head") + 1
    except ValueError:
        st.error("⚠️ 'Sub Head' column not found")
        return

    updates = []
    for _, row in edited_df.iterrows():
        row_number = int(row["_sheet_row"])

        feedback_value = row["Feedback"] if pd.notna(row["Feedback"]) else ""
        remark_value = row["User Feedback/Remark"] if pd.notna(row["User Feedback/Remark"]) else ""
        head_value = row["Head"] if pd.notna(row["Head"]) else ""
        action_by_value = row["Action By"] if pd.notna(row["Action By"]) else ""
        sub_head_value = row["Sub Head"] if pd.notna(row["Sub Head"]) else ""

        # Get A1 notation for each cell to update
        feedback_cell = gspread.utils.rowcol_to_a1(row_number, feedback_col)
        remark_cell = gspread.utils.rowcol_to_a1(row_number, remark_col)
        head_cell = gspread.utils.rowcol_to_a1(row_number, head_col)
        action_by_cell = gspread.utils.rowcol_to_a1(row_number, action_by_col)
        sub_head_cell = gspread.utils.rowcol_to_a1(row_number, sub_head_col)

        # Append all updates to batch list
        updates.append({"range": feedback_cell, "values": [[feedback_value]]})
        updates.append({"range": remark_cell, "values": [[remark_value]]})
        updates.append({"range": head_cell, "values": [[head_value]]})
        updates.append({"range": action_by_cell, "values": [[action_by_value]]})
        updates.append({"range": sub_head_cell, "values": [[sub_head_value]]})

        # Update session state just to keep data consistent
        st.session_state.df.loc[st.session_state.df["_sheet_row"] == row_number, "Feedback"] = feedback_value
        st.session_state.df.loc[st.session_state.df["_sheet_row"] == row_number, "User Feedback/Remark"] = remark_value
        st.session_state.df.loc[st.session_state.df["_sheet_row"] == row_number, "Head"] = head_value
        st.session_state.df.loc[st.session_state.df["_sheet_row"] == row_number, "Action By"] = action_by_value
        st.session_state.df.loc[st.session_state.df["_sheet_row"] == row_number, "Sub Head"] = sub_head_value

    if updates:
        body = {"valueInputOption": "USER_ENTERED", "data": updates}
        sheet.spreadsheet.values_batch_update(body)



def apply_common_filters(df, prefix=""):
    """Applies common filters (Inspection By, Action By, Date Range) to a DataFrame.
    Filters are read from st.session_state using the given prefix."""
    with st.expander("🔍 Apply Additional Filters", expanded=True):
        col4, col5 = st.columns(2)
        # Widget creation. The 'key' automatically handles updating session_state.
        col4.multiselect(
            "Inspection By",
            INSPECTION_BY_LIST[1:],
            default=st.session_state.get(prefix + "insp", []),
            key=prefix + "insp"
        )
        col5.multiselect(
            "Action By",
            ACTION_BY_LIST[1:],
            default=st.session_state.get(prefix + "action", []),
            key=prefix + "action"
        )

        col6, col7 = st.columns(2)
        col6.date_input(
            "From Date",
            value=st.session_state.get(prefix + "from", None),
            key=prefix + "from"
        )
        col7.date_input(
            "To Date",
            value=st.session_state.get(prefix + "to", None),
            key=prefix + "to"
        )

    df_filtered = df.copy()
    # Apply filters based on session state values
   # Apply filters based on session state values
    if st.session_state.get(prefix + "insp"):
        selected = st.session_state[prefix + "insp"]
        df_filtered = df_filtered[df_filtered["Inspection By"].isin(selected if isinstance(selected, list) else [selected])]

    
    if st.session_state.get(prefix + "action"):
        selected = st.session_state[prefix + "action"]
        df_filtered = df_filtered[df_filtered["Action By"].isin(selected if isinstance(selected, list) else [selected])]



    # Convert 'Date of Inspection' to datetime for comparison if it exists
    if "Date of Inspection" in df_filtered.columns:
        df_filtered["Date_dt"] = pd.to_datetime(df_filtered["Date of Inspection"], errors="coerce", format="%d.%m.%y")

        if st.session_state.get(prefix + "from"):
            df_filtered = df_filtered[df_filtered["Date_dt"] >= pd.to_datetime(st.session_state[prefix + "from"])]
        if st.session_state.get(prefix + "to"):
            df_filtered = df_filtered[df_filtered["Date_dt"] <= pd.to_datetime(st.session_state[prefix + "to"])]

        # Drop the temporary datetime column
        df_filtered = df_filtered.drop(columns=["Date_dt"], errors='ignore')

    return df_filtered
# -------------------- HELPER FUNCTIONS --------------------
# All functions are defined here before they are called in the UI logic.
# ---------- MAIN APP ----------
st.title("📋 Welcome to S.A.R.A.L (Safety Abnormality Report & Action List) -version 1.1")
tabs = st.tabs(["📊 View Records"])
with tabs[0]:
    # ---------- GLOBAL CONSTANTS ----------
    VALID_INSPECTIONS = [
        "FOOTPLATE INSPECTION", "STATION INSPECTION", "LC GATE INSPECTION",
        "MISC", "COACHING DEPOT", "ON TRAIN", "SURPRISE/AMBUSH INSPECTION", "WORKSITE INSPECTION"
    ]
    
    station_list = [
        'BRB','MLM','BGVN','JNTR','PRWD','WSB','PPJ','JEUR','KEM','BLNI','DHS','KWV','WDS','MA','AAG',
        'MKPT','MO','MVE','PK','BALE',"SUR",'TKWD','HG','TLT','AKOR','NGS','BOT','DUD','KUI','GDGN','GUR',
        'HHD','SVG','BBD','TJSP','KLBG','HQR','MR','SDB','WADI','ARAG','BLNK','SGRE','KVK','LNP','DLGN',
        'JTRD','MSDG','JVA','WSD','SGLA','PVR','MLB','SEI','BTW','PJR','DRSV','YSI','KMRD','DKY','MRX',
        'OSA','HGL','LUR','NTPC','MRJ','BHLI','NTPC'
    ]
    
    gate_list = [
        'LC-19','LC-22A','LC-25','LC-26','LC-27C','LC-28','LC-30','LC-31','LC-35','LC-37','LC-40','LC-41',
        'LC-43','LC-44','LC-45','LC-46C','LC-54','LC-61','LC-66','LC-74','LC-76','LC-78','LC-82','LC-1',
        'LC-60A','LC-1 TLT ZCL','LC-1 ACC','LC-2 ACC','LC-91','LC-22','LC-24','LC-32','LC-49','LC-70',
        'LC-10','LC-34','LC-36','LC-47','LC-55','LC-59','LC-2','LC-4','LC-42','LC-02','LC-128','LC-63',
        'LC-04','LC-67','LC-77','LC-75','LC-64','LC-65','LC-5','LC-6','LC-57','LC-62','LC-39','LC-2/C',
        'LC-6/C','LC-11','LC-03','LC-15/C','LC-21','LC-26-A','LC-60','LC-61'
    ]
    
    footplate_list = station_list + gate_list + [
        "SUR-DD","SUR-WADI","LUR-KWV","KWV-MRJ","DD-SUR","WADI-SUR","KWV-LUR","MRJ-KWV"
    ]
    
    # ---------- DATA LOAD ----------
    @st.cache_data(show_spinner="Loading data...", persist="disk")
    def get_data():
        return load_data()
    
    if "df" not in st.session_state:
        st.session_state.df = get_data()
    
    df = st.session_state.df.copy()
    
    if df.empty:
        st.warning("No records found")
    else:
        df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], format="%d.%m.%y", errors="coerce")
        df["_original_sheet_index"] = df.index
    
    for col in ["Type of Inspection", "Location", "Head", "Sub Head", "Deficiencies Noted", 
                "Inspection By", "Action By", "Feedback", "User Feedback/Remark"]:
        if col not in df.columns:
            df[col] = ""
    
    df["Status"] = df["Feedback"].apply(classify_feedback)
    
    # ---------- FILTERS ----------
    # Use full available date range automatically (no date picker)
    start_date = df["Date of Inspection"].min()
    end_date = df["Date of Inspection"].max()
    
    col1, col2 = st.columns(2)
    col1.multiselect("Type of Inspection", VALID_INSPECTIONS, key="view_type_filter")
    col2.selectbox("Location", [""] + footplate_list, key="view_location_filter")
    
    col3, col4 = st.columns(2)
    col3.multiselect("Head", HEAD_LIST[1:], key="view_head_filter")
    sub_opts = sorted({s for h in st.session_state.view_head_filter for s in SUBHEAD_LIST.get(h, [])})
    col4.selectbox("Sub Head", [""] + sub_opts, key="view_sub_filter")
    
    selected_status = st.selectbox("🔘 Status", ["All", "Pending", "Resolved"], key="view_status_filter")
    
    # ---------- APPLY FILTERS ----------
    filtered = df[
        (df["Date of Inspection"] >= start_date) &
        (df["Date of Inspection"] <= end_date)
    ]
    
    if st.session_state.view_type_filter:
        filtered = filtered[filtered["Type of Inspection"].isin(st.session_state.view_type_filter)]
    if st.session_state.view_location_filter:
        filtered = filtered[filtered["Location"] == st.session_state.view_location_filter]
    if st.session_state.view_head_filter:
        filtered = filtered[filtered["Head"].isin(st.session_state.view_head_filter)]
    if st.session_state.view_sub_filter:
        filtered = filtered[filtered["Sub Head"] == st.session_state.view_sub_filter]
    if selected_status != "All":
        filtered = filtered[filtered["Status"] == selected_status]
    
    filtered = apply_common_filters(filtered, prefix="view_")
    filtered = filtered.applymap(lambda x: x.replace("\n", " ") if isinstance(x, str) else x)
    filtered = filtered.sort_values("Date of Inspection")

    st.write(f"🔹 Showing {len(filtered)} record(s) from **{start_date.strftime('%d.%m.%Y')}** "
             f"to **{end_date.strftime('%d.%m.%Y')}**")
    
    # Summary Counts Display
    pending_count = (filtered["Status"] == "Pending").sum()
    resolved_count = (filtered["Status"] == "Resolved").sum()
    total_count = len(filtered)
    
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("🟨 Pending", pending_count)
    col_b.metric("🟩 Resolved", resolved_count)
    col_c.metric("📊 Total Records", total_count)



        # ---------- NEW SUB HEAD DISTRIBUTION CHART ----------

    import matplotlib.pyplot as plt
    import numpy as np
    from io import BytesIO
    
    if st.session_state.view_head_filter:
        st.markdown("### 📊 Sub Head Distribution")
    
        # --- Prepare data ---
        subhead_summary = (
            filtered.groupby("Sub Head")["Sub Head"]
            .count()
            .reset_index(name="Count")
            .sort_values(by="Count", ascending=False)
        )
        total_subs = subhead_summary["Count"].sum()
        subhead_summary.loc[len(subhead_summary)] = ["Total", total_subs]
    
        # --- Create figure ---
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
        # --- Pie chart ---
            
        # Filter data
        import pandas as pd
        import matplotlib.pyplot as plt
        import numpy as np
        
       
        # --- Pie chart data preparation ---
        pie_data = subhead_summary[subhead_summary["Sub Head"] != "Total"].copy()
        pie_data = pie_data.sort_values("Count", ascending=False)
        
        # Group small segments into "Others"
        threshold = 0.02
        total = pie_data["Count"].sum()
        pie_data["Percent"] = pie_data["Count"] / total
        
        major = pie_data[pie_data["Percent"] >= threshold]
        minor = pie_data[pie_data["Percent"] < threshold]
        
        if not minor.empty:
            others_sum = minor["Count"].sum()
            others_row = pd.DataFrame([{"Sub Head": "Others", "Count": others_sum}])
            major = pd.concat([major, others_row], ignore_index=True)
        
        # --- Create figure with space for pie + table ---
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))  # Wider layout
        
        # --- Pie chart ---
        wedges, texts, autotexts = axes[0].pie(
            major["Count"],
            startangle=90,
            autopct='%1.1f%%',
            colors=plt.cm.Paired.colors,
            textprops=dict(color='black', fontsize=8)
        )
        
        # Alternating labels (left/right)
        for i, (wedge, (_, row)) in enumerate(zip(wedges, major.iterrows())):
            ang = (wedge.theta2 + wedge.theta1) / 2.0
            x = np.cos(np.deg2rad(ang))
            y = np.sin(np.deg2rad(ang))
        
            place_on_right = (i % 2 == 0)
            label_x = 1.5 if place_on_right else -1.5
            label_y = 1.2 * y
            align = "left" if place_on_right else "right"
        
            label = f"{row['Sub Head']} ({row['Count']})"
        
            axes[0].text(
                label_x, label_y, label,
                ha=align,
                va="center",
                fontsize=8,
                bbox=dict(facecolor="white", edgecolor="gray", alpha=0.7, pad=1)
            )
        
            axes[0].annotate(
                "", xy=(0.9 * x, 0.9 * y), xytext=(label_x, label_y),
                arrowprops=dict(arrowstyle="-", lw=0.8, color="black")
            )
        
        #axes[0].set_title("Sub Head Breakdown", fontsize=14, fontweight="bold")
        
        # --- Table ---
        table_data = [["Sub Head", "Count"]] + subhead_summary.values.tolist()
        axes[1].axis('off')
        
        table_row_count = len(table_data)
        row_scale = 1 + (table_row_count * 0.05)
               
        # --- Final layout adjustments ---
        plt.tight_layout(rect=[0, 0.06, 1, 0.94])
        plt.show()       
    
        # --- Table ---
        table_data = [["Sub Head", "Count"]] + subhead_summary.values.tolist()
        axes[1].axis('off')
        tbl = axes[1].table(cellText=table_data, loc='center')
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(10)
        tbl.scale(1, 1.5)
    
        # --- Annotations ---
        dr = f"{start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}"
        heads = ", ".join(st.session_state.view_head_filter)
        type_display = ", ".join(st.session_state.view_type_filter) if st.session_state.view_type_filter else "All Types"
        location_display = st.session_state.view_location_filter or "All Locations"
    
        # Title
        fig.suptitle("📊 Sub Head Breakdown", fontsize=14, fontweight="bold")
        
        # Dynamic bottom text
        y_base = 0.02  # Push it slightly higher to avoid clipping
        line_spacing = 0.015
        
        fig.text(
            0.5, y_base + line_spacing,
            f"Date Range: {dr}   |   Department: {heads}   |   Type: {type_display}   |   Location: {location_display}",
            ha='center', fontsize=9, color='gray'
        )
        
        if st.session_state.view_sub_filter:
            fig.text(
                0.5, y_base,
                f"Sub Head Filter: {st.session_state.view_sub_filter}",
                ha='center', fontsize=9, color='black', fontweight='bold'
            )


    
        # --- Output ---
        plt.tight_layout(rect=[0, 0.06, 1, 0.94])
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=200, bbox_inches="tight")
        buf.seek(0)
        plt.close()
    
        st.image(buf, use_column_width=True)
        st.download_button(
            "📥 Download Sub Head Distribution (PNG)",
            data=buf,
            file_name="subhead_distribution.png",
            mime="image/png"
        )




        export_df = filtered[[
            "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
            "Deficiencies Noted", "Inspection By", "Action By", "Feedback", "User Feedback/Remark"
        ]].copy()
        from io import BytesIO
        from openpyxl.styles import Alignment    
        towb = BytesIO()
        with pd.ExcelWriter(towb, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False, sheet_name="Filtered Records")
        
            # Access workbook & worksheet
            worksheet = writer.sheets["Filtered Records"]
            
            # Find "Deficiencies Noted" column index
            col_idx = export_df.columns.get_loc("Deficiencies Noted") + 1  # +1 because Excel is 1-indexed
        
            # Apply text wrap to all cells in that column
            for row in worksheet.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx, max_row=len(export_df)+1):
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
        
        towb.seek(0)
        st.download_button(
            "📥 Export Filtered Records to Excel",
            data=towb,
            file_name="filtered_records.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.markdown("### 📄 Preview of Filtered Records")

        
            
# Load once and keep in session
# ---- Status calculation ----
# ---- Status calculation ----
def get_status(feedback, remark):
    status = classify_feedback(feedback, remark)  # tumhara existing function
    return status

def color_text_status(status):
    if status == "Pending":
        return "🔴 Pending"
    elif status == "Resolved":
        return "🟢 Resolved"
    else:
        return status
import io


st.markdown("### ✍️ Edit User Feedback/Remarks in Table")

# 🎨 Custom CSS for scrollbar
st.markdown(
    """
    <style>
    /* For WebKit browsers (Chrome, Edge, Safari) */
    ::-webkit-scrollbar {
        width: 16px;   /* vertical scrollbar width */
        height: 16px;  /* horizontal scrollbar height */
    }
    ::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 8px;
    }
    ::-webkit-scrollbar-thumb {
        background: #888;
        border-radius: 8px;
        border: 3px solid #f1f1f1;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #555;
    }

    /* For Firefox */
    * {
        scrollbar-width: auto;
        scrollbar-color: #888 #f1f1f1;
    }

    /* 👇 Increase row height & enable wrapping ONLY for Deficiencies Noted & Feedback */
    div[data-testid="stDataFrame"] div[role="cell"]:has(div:contains("Deficiencies Noted")),
    div[data-testid="stDataFrame"] div[role="cell"]:has(div:contains("Feedback")) {
        min-height: 70px !important;
        height: auto !important;
        white-space: normal !important;
        word-wrap: break-word !important;
        line-height: 1.6 !important;
        vertical-align: top !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

editable_filtered = filtered.copy()

if not editable_filtered.empty:
    if "_sheet_row" not in editable_filtered.columns:
        editable_filtered["_sheet_row"] = editable_filtered.index + 2  

    display_cols = [
        "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
        "Deficiencies Noted", "Inspection By", "Action By", "Feedback",
        "User Feedback/Remark"
    ]
    editable_df = editable_filtered[display_cols].copy()

    # ✅ Fix: format "Date of Inspection" to only show date
    if "Date of Inspection" in editable_df.columns:
        editable_df["Date of Inspection"] = pd.to_datetime(
            editable_df["Date of Inspection"], errors="coerce"
        ).dt.date

    # Insert Status column next to User Feedback/Remark
    editable_df.insert(
        editable_df.columns.get_loc("User Feedback/Remark") + 1,
        "Status",
        [
            get_status(row["Feedback"], row["User Feedback/Remark"])
            for _, row in editable_df.iterrows()
        ]
    )

    # Add colored emoji prefix to Status for visual distinction
    editable_df["Status"] = editable_df["Status"].apply(color_text_status)

    if (
        "feedback_buffer" not in st.session_state
        or not st.session_state.feedback_buffer.equals(editable_df)
    ):
        st.session_state.feedback_buffer = editable_df.copy()

    with st.form("feedback_form", clear_on_submit=False):
        st.write("Rows:", st.session_state.feedback_buffer.shape[0], 
                 " | Columns:", st.session_state.feedback_buffer.shape[1])
    
        edited_df = st.data_editor(
            st.session_state.feedback_buffer,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            height=600,   # 👈 Fixed height so scrollbar is stable
            column_config={
                "User Feedback/Remark": st.column_config.TextColumn("User Feedback/Remark"),
                "Status": st.column_config.TextColumn(
                    "Status", 
                    help="Pending = 🔴 Red, Resolved = 🟢 Green"
                )
            },
            disabled=[
                "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
                "Deficiencies Noted", "Inspection By", "Action By", "Feedback", "Status"
            ],
            key="feedback_editor"
        )

        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            submitted = st.form_submit_button("✅ Submit Feedback")
        with col2:
            refresh_clicked = st.form_submit_button("🔄 Refresh Data")
            if refresh_clicked:
                st.session_state.df = load_data()
                st.success("✅ Data refreshed successfully!")
     
                

        if submitted:
            # Make sure both edited_df and editable_filtered exist and have the expected column
            if "User Feedback/Remark" not in edited_df.columns or "Feedback" not in editable_filtered.columns:
                st.error("⚠️ Required columns are missing from the data.")
            else:
                # Calculate the common index
                common_index = edited_df.index.intersection(editable_filtered.index)
        
                if len(common_index) > 0:
                    # Check which rows actually changed
                    diffs_mask = (
                        editable_filtered.loc[common_index, "User Feedback/Remark"]
                        != edited_df.loc[common_index, "User Feedback/Remark"]
                    )
        
                    if diffs_mask.any():
                        diffs = edited_df.loc[common_index[diffs_mask]].copy()
                        diffs["_sheet_row"] = editable_filtered.loc[diffs.index, "_sheet_row"].values
                        diffs["User Feedback/Remark"] = diffs["User Feedback/Remark"].fillna("")
        
                        for idx, row in diffs.iterrows():
                            user_remark = row["User Feedback/Remark"]
        
                            if not user_remark.strip():
                                continue  # Skip empty remarks
        
                            # === Pertains to S&T check and update ===
                            if "Pertains to S&T" in user_remark:
                                st.session_state.df.at[idx, "Head"] = "SIGNAL & TELECOM"
                                st.session_state.df.at[idx, "Action By"] = "Sr.DSTE"
                                st.session_state.df.at[idx, "Sub Head"] = ""
                                st.session_state.df.at[idx, "Feedback"] = ""
        
                                diffs.at[idx, "Head"] = "SIGNAL & TELECOM"
                                diffs.at[idx, "Action By"] = "Sr.DSTE"
                                diffs.at[idx, "Sub Head"] = ""
                            # === End of S&T logic ===
                            if "Pertains to OPTG" in user_remark:
                                st.session_state.df.at[idx, "Head"] = "OPTG"
                                st.session_state.df.at[idx, "Action By"] = "Sr.DOM"
                                st.session_state.df.at[idx, "Sub Head"] = ""
                                st.session_state.df.at[idx, "Feedback"] = ""
        
                                diffs.at[idx, "Head"] = "OPTG"
                                diffs.at[idx, "Action By"] = "Sr.DOM"
                                diffs.at[idx, "Sub Head"] = ""

                            
                            if "Pertains to COMMERCIAL" in user_remark:
                                st.session_state.df.at[idx, "Head"] = "COMMERCIAL"
                                st.session_state.df.at[idx, "Action By"] = "Sr.DCM"
                                st.session_state.df.at[idx, "Sub Head"] = ""
                                st.session_state.df.at[idx, "Feedback"] = ""
        
                                diffs.at[idx, "Head"] = "COMMERCIAL"
                                diffs.at[idx, "Action By"] = "Sr.DCM"
                                diffs.at[idx, "Sub Head"] = ""

                            
                            if "Pertains to ELECT/G" in user_remark:
                                st.session_state.df.at[idx, "Head"] = "ELECT/G"
                                st.session_state.df.at[idx, "Action By"] = "Sr.DEE/G"
                                st.session_state.df.at[idx, "Sub Head"] = ""
                                st.session_state.df.at[idx, "Feedback"] = ""
        
                                diffs.at[idx, "Head"] = "ELECT/G"
                                diffs.at[idx, "Action By"] = "Sr.DEE/G"
                                diffs.at[idx, "Sub Head"] = ""
                            if "Pertains to ELECT/TRD" in user_remark:
                                st.session_state.df.at[idx, "Head"] = "ELECT/TRD"
                                st.session_state.df.at[idx, "Action By"] = "Sr.DEE/TRD"
                                st.session_state.df.at[idx, "Sub Head"] = ""
                                st.session_state.df.at[idx, "Feedback"] = ""
        
                                diffs.at[idx, "Head"] = "ELECT/TRD"
                                diffs.at[idx, "Action By"] = "Sr.DEE/TRD"
                                diffs.at[idx, "Sub Head"] = ""
                            # Existing feedback text
                            existing_feedback = st.session_state.df.loc[idx, "Feedback"]
        
                            # Append with full stop separator if existing feedback is not empty
                            if existing_feedback and existing_feedback.strip() != "":
                                combined = existing_feedback.strip()
                                if not combined.endswith("."):
                                    combined += "."
                                combined += " " + user_remark.strip()
                            else:
                                combined = user_remark.strip()
        
                            # Update in diffs
                            diffs.at[idx, "Feedback"] = combined
                            diffs.at[idx, "User Feedback/Remark"] = ""
        
                            # Update in session state dataframe
                            st.session_state.df.loc[idx, "Feedback"] = combined
                            st.session_state.df.loc[idx, "User Feedback/Remark"] = ""
        
                        # Update Google Sheet
                        update_feedback_column(diffs)
        
                        st.success(f"✅ Updated {len(diffs)} Feedback row(s) with appended remarks.")
                    else:
                        st.info("ℹ️ No changes detected to save.")
                else:
                    st.warning("⚠️ No rows matched for update.")


st.markdown(
    """
    <marquee behavior="scroll" direction="left" style="color: red; font-weight: bold; font-size:16px;">
        For any correction in data, contact Safety Department on sursafetyposition@gmail.com
    </marquee>
    """,
    unsafe_allow_html=True
)














