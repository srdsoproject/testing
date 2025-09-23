import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode
import os
import re
import requests

# -------------------- CONSTANTS --------------------
LOCAL_FILE = "responses_local.xlsx"
GITHUB_RAW_URL = "https://github.com/srdsoproject/testing/raw/main/responses.xlsx"

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

VALID_INSPECTIONS = [
    "FOOTPLATE INSPECTION", "STATION INSPECTION", "LC GATE INSPECTION",
    "MISC", "COACHING DEPOT", "ON TRAIN", "SURPRISE/AMBUSH INSPECTION", "WORKSITE INSPECTION", "OTHER (UNUSUAL)",
]

FOOTPLATE_LIST = STATION_LIST + GATE_LIST + FOOTPLATE_ROUTES

# -------------------- HELPERS FOR STATUS --------------------
def normalize_str(text):
    return text.lower().strip() if isinstance(text, str) else ""

def classify_feedback(feedback, user_remark=""):
    """Smart classification: Pending / Resolved"""
    if isinstance(feedback, str) and feedback.strip() == "`":
        return ""
    def _classify(txt):
        if not txt:
            return None
        date_found = bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', txt))
        resolved_kw = [
            "attended","solved","done","completed","confirmed by","message given",
            "tdc work completed","replaced","msg given","msg sent","counseled","info shared",
            "communicated","sent successfully","counselled","gate will be closed soon",
            "attending at the time","handled","resolved","action taken","spoken to","warned",
            "counselling","hubli","working normal","met","discussion held","report sent",
            "notified","explained","nil","na","tlc","work completed","acknowledged","visited",
            "briefed","guided","handover","working properly","checked found working","supply restored",
            "updated by","adv to","counselled the staff","complied","checked and found",
            "maintained","for needful action","provided at","in working condition","is working",
            "this is not a deficiency","not deficiency","it is observation","found working",
            "equipment is working","item is working","as per plan","putright","put right",
            "operational feasibility","will be provided","will be supplied shortly","advised to ubl",
            "updated","letter has been sent","letter has been given"
        ]
        pending_kw = [
            "work is going on","tdc given","target date","expected by","likely by","planned by",
            "will be","needful","to be","pending","not done","awaiting","waiting","yet to","next time",
            "follow up","tdc.","tdc","t d c","will attend","will be attended","scheduled","reminder",
            "to inform","to counsel","to submit","to do","to replace","prior","remains","still",
            "under process","not yet","to be done","will ensure","during next","action will be taken",
            "will be supplied shortly","not available","not updated","progress","under progress",
            "noted please","to arrange","awaited","material awaited","approval awaited","to procure",
            "yet pending","incomplete","tentative","ongoing","in progress","being done","arranging",
            "waiting for","subject to","awaiting approval","awaiting material","awaiting confirmation",
            "next schedule","planned for","will arrange","proposed date","to complete","to be completed",
            "likely completion","expected completion","not received","awaiting response"
        ]
        if "tdc" in txt and any(k in txt for k in resolved_kw):
            return "Resolved"
        if any(k in txt for k in pending_kw):
            return "Pending"
        if date_found:
            return "Pending" if "tdc" in txt else "Resolved"
        if any(k in txt for k in resolved_kw):
            return "Resolved"
        return None

    fb = normalize_str(feedback)
    rm = normalize_str(user_remark)
    marks = re.findall(r"[!#]", f"{fb} {rm}")
    if marks:
        return "Resolved" if marks[-1] == "#" else "Pending"

    a = _classify(fb)
    b = _classify(rm)
    if a == "Resolved" or b == "Resolved": return "Resolved"
    if a == "Pending"  or b == "Pending":  return "Pending"
    return "Pending"

# -------------------- DATA LOAD/SAVE --------------------
def load_data():
    if os.path.exists(LOCAL_FILE):
        df = pd.read_excel(LOCAL_FILE)
    else:
        resp = requests.get(GITHUB_RAW_URL)
        resp.raise_for_status()
        df = pd.read_excel(BytesIO(resp.content))

    required_cols = [
        "Date of Inspection","Type of Inspection","Location",
        "Head","Sub Head","Deficiencies Noted",
        "Inspection By","Action By","Feedback","User Feedback/Remark"
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    if "_sheet_row" not in df.columns: df["_sheet_row"] = df.index + 2
    if "_original_sheet_index" not in df.columns: df["_original_sheet_index"] = df.index
    df["Feedback"] = df["Feedback"].fillna("").astype(str)
    df["User Feedback/Remark"] = df["User Feedback/Remark"].fillna("").astype(str)

    # ✅ Smart Pending/Resolved
    df["Status"] = df.apply(
        lambda r: classify_feedback(r["Feedback"], r["User Feedback/Remark"]),
        axis=1
    )
    return df

def save_to_local_excel(df):
    df.to_excel(LOCAL_FILE, index=False)

def color_text_status(status):
    return "🔴 Pending" if status == "Pending" else "🟢 Resolved"

# -------------------- SESSION STATE --------------------
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user" not in st.session_state: st.session_state.user = {}
if "df" not in st.session_state: st.session_state.df = pd.DataFrame()
if "alerts_log" not in st.session_state: st.session_state.alerts_log = []

# -------------------- LOGIN --------------------
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

# -------------------- LOAD DATA --------------------
if st.session_state.df.empty:
    st.session_state.df = load_data()

df_main = st.session_state.df.copy()

# -------------------- FILTERS --------------------
st.markdown("### 🔍 Filters")

df_main["Date of Inspection"] = pd.to_datetime(df_main["Date of Inspection"], errors="coerce")
from_date = st.date_input("📅 From Date", df_main["Date of Inspection"].min().date())
to_date   = st.date_input("📅 To Date",   df_main["Date of Inspection"].max().date())

from_dt = pd.to_datetime(from_date)
to_dt   = pd.to_datetime(to_date)

type_filter = st.multiselect("Type of Inspection", VALID_INSPECTIONS)
location_filter = st.multiselect("Location", FOOTPLATE_LIST)
head_filter = st.multiselect("Head", HEAD_LIST[1:])
sub_filter = st.multiselect("Sub Head", sorted({s for h in head_filter for s in SUBHEAD_LIST.get(h, [])}))
status_filter = st.selectbox("🔘 Status", ["All", "Pending", "Resolved"])

filtered_df = df_main.copy()
filtered_df = filtered_df[filtered_df["Date of Inspection"].notna()]
filtered_df = filtered_df[(filtered_df["Date of Inspection"] >= from_dt) &
                          (filtered_df["Date of Inspection"] <= to_dt)]
if type_filter: filtered_df = filtered_df[filtered_df["Type of Inspection"].isin(type_filter)]
if location_filter: filtered_df = filtered_df[filtered_df["Location"].isin(location_filter)]
if head_filter: filtered_df = filtered_df[filtered_df["Head"].isin(head_filter)]
if sub_filter: filtered_df = filtered_df[filtered_df["Sub Head"].isin(sub_filter)]
if status_filter != "All": filtered_df = filtered_df[filtered_df["Status"] == status_filter]

st.write(f"🔹 Showing {len(filtered_df)} record(s)")

# -------------------- METRICS --------------------
col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("🟨 Pending", (filtered_df["Status"]=="Pending").sum())
col_b.metric("⚠️ No Response", filtered_df["Feedback"].astype(str).str.strip().eq("").sum())
col_c.metric("🟩 Resolved", (filtered_df["Status"]=="Resolved").sum())
col_d.metric("📊 Total Records", len(filtered_df))

# -------------------- EDITABLE GRID --------------------
st.markdown("### ✍️ Edit User Feedback / Remarks")
editable_df = filtered_df.copy()
editable_df["Status"] = editable_df["Status"].apply(color_text_status)

gb = GridOptionsBuilder.from_dataframe(editable_df)
gb.configure_default_column(editable=False, wrapText=True, autoHeight=True, resizable=True)
gb.configure_column("User Feedback/Remark", editable=True, wrapText=True, autoHeight=True,
                    cellEditor="agTextCellEditor", cellEditorPopup=False,
                    cellEditorParams={"maxLength":4000})
gb.configure_column("_original_sheet_index", hide=True)
gb.configure_column("_sheet_row", hide=True)
auto_size_js = JsCode("""
function(params) {
    let allColumnIds = [];
    params.columnApi.getAllColumns().forEach(function(column) { allColumnIds.push(column.getColId()); });
    params.columnApi.autoSizeColumns(allColumnIds);
}
""")
gb.configure_grid_options(onFirstDataRendered=auto_size_js)
grid_response = AgGrid(
    editable_df,
    gridOptions=gb.build(),
    update_mode=GridUpdateMode.VALUE_CHANGED,
    height=600,
    allow_unsafe_jscode=True
)
edited_df = pd.DataFrame(grid_response["data"])

# -------------------- BUTTONS --------------------
c1, c2, _ = st.columns([1,1,1])
if c1.button("✅ Submit Feedback"):
    df_copy = st.session_state.df.copy()
    changes = 0
    edited_rows = edited_df[edited_df["User Feedback/Remark"].astype(str).str.strip() != ""]
    for _, row in edited_rows.iterrows():
        idx = int(row["_original_sheet_index"])
        new_remark = str(row["User Feedback/Remark"]).strip()
        if new_remark:
            df_copy.at[idx, "Feedback"] = new_remark
            df_copy.at[idx, "User Feedback/Remark"] = ""
            changes += 1
    if changes > 0:
        # Re-classify status after edits
        df_copy["Status"] = df_copy.apply(
            lambda r: classify_feedback(r["Feedback"], r["User Feedback/Remark"]), axis=1
        )
        save_to_local_excel(df_copy)
        st.session_state.df = df_copy
        st.success(f"✅ Updated {changes} feedback row(s).")
        st.rerun()
    else:
        st.info("ℹ️ No new feedback to submit.")

if c2.button("🔄 Refresh Data"):
    st.session_state.df = load_data()
    st.success("✅ Data refreshed successfully!")
    st.rerun()

# -------------------- ALERT LOG --------------------
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

# -------------------- FOOTER --------------------
st.markdown("""
<marquee behavior="scroll" direction="left" style="color:red;font-weight:bold;font-size:16px;">
    For any correction in data, contact Safety Department on sursafetyposition@gmail.com,
    Contact: Rly phone no. 55620, Cell: +91 9022507772
</marquee>
""", unsafe_allow_html=True)
