import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from io import BytesIO
import matplotlib.pyplot as plt
import altair as alt
import re
import numpy as np
from openpyxl.styles import Alignment, Font, Border, Side, NamedStyle
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

# ==================== PAGE CONFIG ====================
st.set_page_config(page_title="S.A.R.A.L", layout="wide")

# ==================== CUSTOM CSS ====================
st.markdown("""
<style>
    .main > div {padding-top: 2rem;}
    .stApp {background: #f8fafc;}
    .header-container {display: flex; align-items: center; gap: 16px; margin-bottom: 1rem;}
    .logo {height: 60px; object-fit: contain;}
    .card {border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 16px;}
    .tag {display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 13px; font-weight: 600;}
    .tag-head {background: #dbeafe; color: #1e40af;}
    .tag-sub {background: #fef3c7; color: #92400e;}
    .tag-loc {background: #ecfdf5; color: #065f46;}
    .deficiency-box {background: #fefce8; padding: 12px; border-radius: 8px; border-left: 4px solid #f59e0b; font-size: 14px; line-height: 1.6; color: #92400e;}
    .feedback-box {background: #f0fdf4; padding: 10px; border-radius: 6px; border-left: 4px solid #22c55e; color: #166534;}
    .textarea {width: 100%; min-height: 100px; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-family: inherit; font-size: 14px; margin-top: 6px;}
    .copy-btn {background: #f1f5f9; border: 1px solid #cbd5e1; color: #475569; padding: 6px 12px; border-radius: 6px; font-size: 13px; cursor: pointer;}
    .status-pending {color: #dc2626;}
    .status-resolved {color: #16a34a;}
    .hidden-btn {display: none;}
    .ag-header-cell-label {font-weight: 600;}
    .ag-row:hover {background-color: #f5f7fa !important;}
    .ag-cell {border-right: 1px solid #e2e8f0 !important;}
</style>
""", unsafe_allow_html=True)

# ==================== SESSION STATE INIT ====================
for key in ["logged_in", "user", "ack_done", "df", "alerts_log", "detail_idx"]:
    if key not in st.session_state:
        st.session_state[key] = False if key == "logged_in" else {} if key == "user" else [] if key == "alerts_log" else None

# ==================== LOGIN SYSTEM ====================
def login(email, password):
    for user in st.secrets["users"]:
        if user["email"] == email and user["password"] == password:
            return user
    return None

if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align:center;'>S.A.R.A.L</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#64748b;'>Safety Abnormality Report & Action List</p>", unsafe_allow_html=True)
    with st.form("login_form", clear_on_submit=True):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            email = st.text_input("Email", placeholder="Enter your email")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            submitted = st.form_submit_button("Login", use_container_width=True)
            if submitted:
                user = login(email, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.success(f"Welcome, {user['name']}!")
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
    st.stop()

# ==================== ACKNOWLEDGMENT ====================
user_id = st.session_state.user["email"]
try:
    ack_df = pd.read_excel("responses.xlsx")
    if "UserID" not in ack_df.columns:
        ack_df = pd.DataFrame(columns=["UserID", "Name"])
except:
    ack_df = pd.DataFrame(columns=["UserID", "Name"])

if user_id not in ack_df["UserID"].values:
    st.warning("Pending Deficiencies Compliance")
    with st.expander("Read Notice & Acknowledge", expanded=True):
        st.info("The compliance of deficiencies of previous dates are pending & needs to be completed immediately. I hereby declare that I have read this notice and will ensure compliance.")
        with st.form("ack_form"):
            name = st.text_input("Your Name")
            if st.form_submit_button("Submit Acknowledgment"):
                if name.strip():
                    new = pd.DataFrame([{"UserID": user_id, "Name": name.strip()}])
                    ack_df = pd.concat([ack_df, new], ignore_index=True)
                    ack_df.to_excel("responses.xlsx", index=False)
                    st.success("Acknowledgment submitted.")
                    st.rerun()
                else:
                    st.error("Name required.")
    st.stop()

# ==================== SIDEBAR ====================
with st.sidebar:
    st.image("https://raw.githubusercontent.com/srdsoproject/testing/main/Central%20Railway%20Logo.png", width=120)
    st.markdown(f"**{st.session_state.user['name']}**")
    st.markdown(f"_{st.session_state.user['email']}_")
    if st.button("Logout"):
        for k in ["logged_in", "user", "detail_idx"]:
            st.session_state[k] = False if k == "logged_in" else {}
        st.rerun()

# ==================== GOOGLE SHEETS CONNECTION ====================
@st.cache_resource
def connect_to_gsheet():
    service_account_info = dict(st.secrets["gcp_service_account"])
    if "private_key" in service_account_info:
        service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(service_account_info, scopes=[
        "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"
    ])
    gc = gspread.authorize(creds)
    return gc.open_by_key("1_WQyJCtdXuAIQn3IpFTI4KfkrveOHosNsvsZn42jAvw").worksheet("Sheet1")

sheet = connect_to_gsheet()
st.sidebar.success("Connected to Google Sheets")

# ==================== CONSTANTS (LISTS) ====================
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
ALL_LOCATIONS = STATION_LIST + GATE_LIST + FOOTPLATE_ROUTES

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

VALID_INSPECTIONS = [
    "FOOTPLATE INSPECTION", "STATION INSPECTION", "LC GATE INSPECTION",
    "MISC", "COACHING DEPOT", "ON TRAIN", "SURPRISE/AMBUSH INSPECTION", "WORKSITE INSPECTION", "OTHER (UNUSUAL)",
]

INSPECTION_BY_LIST = [""] + ["HQ OFFICER CCE/CR",'DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                             'Sr.DEE/TRD', 'Sr.DEE/G','Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC',
                             'DME,DEE/TRD', 'DFM', 'DSTE/HQ', 'DSTE/KLBG', 'ADEN/T/SUR', 'ADEN/W/SUR', 'ADEN/KWV',
                             'ADEN/PVR', 'ADEN/LUR', 'ADEN/KLBG', 'ADSTE/SUR', 'ADSTE/I/KWV', 'ADSTE/II/KWV',
                             'ADME/SUR', 'AOM/GD', 'AOM/GEN', 'ACM/Cog', 'ACM/TC', 'ACM/GD', 'APO/GEN', 'APO/WEL',
                             'ADFM/I', 'ADFMII', 'ASC', 'ADSO/SUR']

ACTION_BY_LIST = [""] + ['DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                         'Sr.DEE/TRD', 'Sr.DEE/G','Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC', 'CMS']

# ==================== HELPER FUNCTIONS ====================
def normalize_str(text):
    if not isinstance(text, str): return ""
    return re.sub(r'\s+', ' ', text.lower()).strip()

def classify_feedback(feedback, user_remark=""):
    if isinstance(feedback, str) and feedback.strip() == "`": return ""
    def _classify(text_normalized):
        if not text_normalized: return None
        date_found = bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text_normalized))
        resolved_kw = ["attended", "solved", "done", "completed", "confirmed by", "message given", "#"]
        pending_kw = ["work is going on", "tdc", "target date", "will be", "pending", "yet to", "!"]
        if any(k in text_normalized for k in resolved_kw): return "Resolved"
        if any(k in text_normalized for k in pending_kw): return "Pending"
        if date_found: return "Pending" if "tdc" in text_normalized else "Resolved"
        return None
    fb = normalize_str(feedback)
    rm = normalize_str(user_remark)
    m = re.findall(r"[!#]", f"{fb} {rm}")
    if m: return "Resolved" if m[-1] == "#" else "Pending"
    a = _classify(fb)
    b = _classify(rm)
    if a == "Resolved" or b == "Resolved": return "Resolved"
    if a == "Pending" or b == "Pending": return "Pending"
    return "Pending"

def get_status(fb, rm): return classify_feedback(fb, rm)
def color_text_status(s): return f"<span class='status-{'resolved' if s=='Resolved' else 'pending'}'>{'Resolved' if s=='Resolved' else 'Pending'}</span>"

# ==================== LOAD DATA FROM GOOGLE SHEETS ====================
@st.cache_data(ttl=60)
def load_data():
    REQUIRED_COLS = ["Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head", "Deficiencies Noted",
                     "Inspection By", "Action By", "Feedback", "User Feedback/Remark"]
    try:
        data = sheet.get_all_values()
        if not data or len(data) < 2: return pd.DataFrame(columns=REQUIRED_COLS)
        headers = [c.strip() for c in data[0]]
        df = pd.DataFrame(data[1:], columns=headers)
        for col in REQUIRED_COLS:
            if col not in df.columns: df[col] = ""
        df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
        df["_sheet_row"] = df.index + 2
        df["_original_sheet_index"] = df.index
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame(columns=REQUIRED_COLS)

if "df" not in st.session_state:
    st.session_state.df = load_data()
df = st.session_state.df

# ==================== GOOGLE SHEET UPDATE FUNCTION ====================
def update_feedback_column(edited_df):
    header = sheet.row_values(1)
    def col_idx(name):
        try: return header.index(name) + 1
        except: return None
    feedback_col = col_idx("Feedback")
    remark_col = col_idx("User Feedback/Remark")
    if None in (feedback_col, remark_col): return
    updates = []
    for _, row in edited_df.iterrows():
        r = int(row["_sheet_row"])
        def a1(c): return gspread.utils.rowcol_to_a1(r, c)
        updates += [
            {"range": a1(feedback_col), "values": [[row.get("Feedback", "")]]},
            {"range": a1(remark_col), "values": [[row.get("User Feedback/Remark", "")]]}
        ]
    if updates:
        sheet.spreadsheet.values_batch_update({"valueInputOption": "USER_ENTERED", "data": updates})

# ==================== HEADER ====================
st.markdown("""
<div class="header-container">
    <img src="https://raw.githubusercontent.com/srdsoproject/testing/main/Central%20Railway%20Logo.png" class="logo">
    <div>
        <h2 style="margin:0;">S.A.R.A.L</h2>
        <p style="margin:0; color:#64748b;">Safety Abnormality Report & Action List – Version 1.1.8</p>
    </div>
</div>
""", unsafe_allow_html=True)

# ==================== TABS ====================
tabs = st.tabs(["View Records", "Analytics", "Edit Remarks"])

# ==================== TAB 1: VIEW RECORDS ====================
with tabs[0]:
    if df.empty:
        st.info("No data available.")
    else:
        filtered = df.copy()
        with st.expander("Filters", expanded=False):
            c1, c2 = st.columns(2)
            c1.multiselect("Type", VALID_INSPECTIONS, key="v_type")
            c2.multiselect("Location", ALL_LOCATIONS, key="v_loc")
            c3, c4 = st.columns(2)
            c3.multiselect("Head", HEAD_LIST[1:], key="v_head")
            sub_opts = sorted({s for h in st.session_state.v_head for s in SUBHEAD_LIST.get(h, [])})
            c4.multiselect("Sub Head", sub_opts, key="v_sub")

        for key, col in [("v_type","Type of Inspection"), ("v_loc","Location"), ("v_head","Head"), ("v_sub","Sub Head")]:
            if st.session_state.get(key):
                filtered = filtered[filtered[col].isin(st.session_state[key])]

        st.write(f"**{len(filtered)} records**")
        st.dataframe(filtered.drop(columns=["_sheet_row", "_original_sheet_index"], errors="ignore"), use_container_width=True)

# ==================== TAB 2: ANALYTICS ====================
with tabs[1]:
    st.markdown("### Pending Deficiencies Trend")
    # (Keep your original analytics code here — unchanged)
    pass

# ==================== TAB 3: EDITOR WITH CARD ====================
with tabs[2]:
    st.markdown("### Edit User Feedback/Remark")

    search = st.text_input("Search Deficiencies", placeholder="Type to filter...")
    edit_df = df.copy()
    if search:
        edit_df = edit_df[edit_df["Deficiencies Noted"].astype(str).str.contains(search, case=False)]

    if edit_df.empty:
        st.info("No records.")
    else:
        edit_df["_id"] = edit_df.index
        edit_df["_sheet_row"] = edit_df.index + 2

        # Hidden buttons for each row
        for idx in edit_df["_id"]:
            if st.button("", key=f"btn_{idx}", help="Open card"):
                st.session_state.detail_idx = idx
                st.rerun()

        # AG Grid (read-only)
        display_cols = ["Date of Inspection", "Location", "Deficiencies Noted", "Feedback"]
        grid_df = edit_df[display_cols].copy()
        grid_df["Date of Inspection"] = pd.to_datetime(grid_df["Date of Inspection"]).dt.strftime("%d.%m.%Y")
        gb = GridOptionsBuilder.from_dataframe(grid_df)
        gb.configure_default_column(wrapText=True, autoHeight=True, resizable=True)
        gb.configure_column("Deficiencies Noted", flex=70, minWidth=420)
        gb.configure_column("Details", cellRenderer=JsCode("""
        function() { return `<button class="copy-btn">Details</button>`; }
        """), width=90, pinned="right")
        gb.configure_grid_options(onCellClicked=JsCode(f"""
        function(params) {{
            if (params.column.colId === 'Details') {{
                document.getElementById('btn_{{}}').click();
            }}
        }}
        """))
        AgGrid(grid_df, gb.build(), height=500, theme="balham", fit_columns_on_grid_load=False)

        # CARD WHEN CLICKED
        if st.session_state.detail_idx is not None:
            row = edit_df[edit_df["_id"] == st.session_state.detail_idx].iloc[0]
            st.markdown(f"<div class='card'>", unsafe_allow_html=True)

            st.markdown(f"""
            <h4>Details – Row {row['_sheet_row']}</h4>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; font-size:14px;">
                <div><strong>Head</strong><br><span class="tag tag-head">{row['Head']}</span></div>
                <div><strong>Sub Head</strong><br><span class="tag tag-sub">{row['Sub Head']}</span></div>
                <div><strong>Inspection By</strong><br>{row['Inspection By']}</div>
                <div><strong>Date</strong><br>{row['Date of Inspection'].strftime('%d.%m.%Y') if pd.notna(row['Date of Inspection']) else '-'}</div>
                <div><strong>Location</strong><br><span class="tag tag-loc">{row['Location']}</span></div>
                <div><strong>Action By</strong><br>{row['Action By']}</div>
            </div>
            <hr style='border:0; border-top:1px solid #e2e8f0; margin:20px 0;'>
            """, unsafe_allow_html=True)

            st.markdown(f"<strong>Deficiency</strong><div class='deficiency-box'>{row['Deficiencies Noted']}</div>", unsafe_allow_html=True)

            if row.get("Feedback"):
                st.markdown(f"<div style='margin-top:16px;'><strong>Feedback</strong><div class='feedback-box'>{row['Feedback']}</div></div>", unsafe_allow_html=True)

            remark = st.text_area("User Feedback / Remark", value=row.get("User Feedback/Remark", ""), height=100, key=f"remark_{row['_id']}")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save Remark", use_container_width=True):
                    df.at[row.name, "User Feedback/Remark"] = remark
                    update_feedback_column(pd.DataFrame([{
                        "_sheet_row": row["_sheet_row"],
                        "User Feedback/Remark": remark
                    }]))
                    st.success("Saved!")
                    st.session_state.detail_idx = None
                    st.rerun()
            with col2:
                if st.button("Close", use_container_width=True):
                    st.session_state.detail_idx = None
                    st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

# ==================== FOOTER ====================
st.markdown("""
<marquee behavior="scroll" direction="left" style="color:red;font-weight:bold;font-size:16px;">
    For any correction in data, contact Safety Department on sursafetyposition@gmail.com, Contact: Rly phone no. 55620, Cell: +91 9022507772
</marquee>
""", unsafe_allow_html=True)
else:
    st.info("No data to display.")
    # ----------------- BUTTONS -----------------
    c1, c2, _ = st.columns([1, 1, 1])
    submitted = c1.button("✅ Submit Feedback")
    if c2.button("🔄 Refresh Data"):
        st.session_state.df = load_data()
        st.success("✅ Data refreshed successfully!")

    # ----------------- SUBMIT LOGIC -----------------
    if submitted:
        # Validate needed columns
        need_cols = {"_original_sheet_index", "User Feedback/Remark"}
        if not need_cols.issubset(edited_df.columns) or "Feedback" not in editable_filtered.columns:
            st.error("⚠️ Required columns are missing from the data.")
        else:
            # Compare remarks using the stable ID to find changes
            orig = editable_filtered.set_index("_original_sheet_index")
            new = edited_df.set_index("_original_sheet_index")

            old_remarks = orig["User Feedback/Remark"].fillna("").astype(str)
            new_remarks = new["User Feedback/Remark"].fillna("").astype(str)

            # Align indexes before comparing
            common_ids = new_remarks.index.intersection(old_remarks.index)
            diff_mask = new_remarks.loc[common_ids] != old_remarks.loc[common_ids]
            changed_ids = diff_mask[diff_mask].index.tolist()

            if changed_ids:
                diffs = new.loc[changed_ids].copy()
                diffs["_sheet_row"] = orig.loc[changed_ids, "_sheet_row"].values

                # Routing dictionary
                routing = {
                    "Pertains to S&T":        ("SIGNAL & TELECOM", "Sr.DSTE"),
                    "Pertains to SECURITY": ("SECURITY","DSC"),
                    "Pertains to OPTG":       ("OPTG", "Sr.DOM"),
                    "Pertains to COMMERCIAL": ("COMMERCIAL", "Sr.DCM"),
                    "Pertains to ELECT/G":    ("ELECT/G", "Sr.DEE/G"),
                    "Pertains to ELECT/TRD":  ("ELECT/TRD", "Sr.DEE/TRD"),
                    "Pertains to MECHANICAL":  ("MECHANICAL", "Sr.DME"),
                    "Pertains to ELECT/TRO":  ("ELECT/TRO", "Sr.DEE/TRO"),
                    "Pertains to Sr.DEN/S":   ("ENGINEERING", "Sr.DEN/S"),
                    "Pertains to Sr.DEN/C":   ("ENGINEERING", "Sr.DEN/C"),
                    "Pertains to Sr.DEN/Co":  ("ENGINEERING", "Sr.DEN/Co"),
                    "Pertains to FINAINCE": ("FINANCE","Sr.DFM"),
                    "Pertains to STORE" : ("STORE","Sr.DMM"),
                    "Pertains to MEDICAL" : ("MEDICAL", "CMS"),
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

                            # 👉 Collect extra info
                            date_str = orig.loc[oid, "Date of Inspection"]
                            deficiency = orig.loc[oid, "Deficiencies Noted"]
                            forwarded_by = orig.loc[oid, "Head"]

                            # 👉 Build alert message
                            alert_msg = (
                                f"📌 **{head} Department Alert**\n"
                                f"- Date: {date_str}\n"
                                f"- Deficiency: {deficiency}\n"
                                f"- Forwarded By: {forwarded_by}\n"
                                f"- Forwarded Remark: {user_remark}"
                            )
                            st.session_state.alerts_log.insert(0, alert_msg)

                    # ✅ Replace Feedback with new remark (clear remark column)
                    diffs.at[oid, "Feedback"] = user_remark
                    diffs.at[oid, "User Feedback/Remark"] = ""

                    st.session_state.df.at[oid, "Feedback"] = user_remark
                    st.session_state.df.at[oid, "User Feedback/Remark"] = ""

                # Persist to storage
                update_feedback_column(
                    diffs.reset_index().rename(columns={"index": "_original_sheet_index"})
                )
                st.success(f"✅ Updated {len(changed_ids)} Feedback row(s) with new remarks.")
            else:
                st.info("ℹ️ No changes detected to save.")
#else:
    #st.info("Deficiencies will be updated soon !")







