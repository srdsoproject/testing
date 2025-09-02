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
# -------------------- IMPORTS --------------------
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
                             'ADFM/I', 'ADFMII', 'ASC', 'ADSO/SUR']

ACTION_BY_LIST = [""] + ['DRM/SUR', 'ADRM', 'Sr.DSO', 'Sr.DOM', 'Sr.DEN/S', 'Sr.DEN/C', 'Sr.DEN/Co', 'Sr.DSTE',
                         'Sr.DEE/TRD', 'Sr.DEE/G','Sr.DEE/TRO', 'Sr.DME', 'Sr.DCM', 'Sr.DPO', 'Sr.DFM', 'Sr.DMM', 'DSC']

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
            "noted please", "updated by", "adv to", "counselled the staff", "complied", "checked and found",
            "maintained", "for needful action", "provided at", "in working condition", "is working",
            "found working", "equipment is working", "item is working", "as per plan", "putright", "put right",
            "operational feasibility", "will be provided", "will be supplied shortly", "advised to ubl", "updated"
        ]

        pending_kw = [
            "work is going on", "tdc given", "target date", "expected by", "likely by", "planned by",
            "will be", "needful", "to be", "pending", "not done", "awaiting", "waiting", "yet to", "next time",
            "follow up", "tdc.", "tdc", "t d c", "will attend", "will be attended", "scheduled", "reminder",
            "to inform", "to counsel", "to submit", "to do", "to replace", "prior", "remains", "still",
            "under process", "not yet", "to be done", "will ensure", "during next", "action will be taken",
            "will be supplied shortly", "not available", "not updated", "progress", "under progress",
            "to arrange", "awaited", "material awaited", "approval awaited", "to procure", "yet pending",
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
    remark_col   = col_idx("User Feedback/Remark")
    head_col     = col_idx("Head")
    action_col   = col_idx("Action By")
    subhead_col  = col_idx("Sub Head")

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
            {"range": a1(remark_col),   "values": [[rv]]},
            {"range": a1(head_col),     "values": [[hv]]},
            {"range": a1(action_col),   "values": [[av]]},
            {"range": a1(subhead_col),  "values": [[sv]]},
        ]

        # keep session_state in sync
        s = st.session_state.df
        s.loc[s["_sheet_row"] == r, ["Feedback","User Feedback/Remark","Head","Action By","Sub Head"]] = [fv, rv, hv, av, sv]

    if updates:
        sheet.spreadsheet.values_batch_update({"valueInputOption": "USER_ENTERED", "data": updates})

# ---------- FILTER WIDGETS (no date pickers – you set full range below) ----------
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

# -------------------- SESSION DATA --------------------
if "df" not in st.session_state:
    st.session_state.df = load_data()
df = st.session_state.df

tabs = st.tabs(["📊 View Records"])
with tabs[0]:
    if df.empty:
        st.warning("Deficiencies will be updated soon !")
        st.stop()

    # Ensure required cols exist
    for col in ["Type of Inspection", "Location", "Head", "Sub Head", "Deficiencies Noted",
                "Inspection By", "Action By", "Feedback", "User Feedback/Remark"]:
        if col not in df.columns:
            df[col] = ""

    # Dates & status
    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], format="%d.%m.%y", errors="coerce")
    df["_original_sheet_index"] = df.index
    df["Status"] = df["Feedback"].apply(classify_feedback)

    # ---------- FILTERS (no date pickers) ----------
    start_date = df["Date of Inspection"].min()
    end_date   = df["Date of Inspection"].max()

    c1, c2 = st.columns(2)
    c1.multiselect("Type of Inspection", VALID_INSPECTIONS, key="view_type_filter")
    c2.multiselect("Location", FOOTPLATE_LIST, key="view_location_filter")   # ⬅️ changed to multiselect

    c3, c4 = st.columns(2)
    c3.multiselect("Head", HEAD_LIST[1:], key="view_head_filter")
    sub_opts = sorted({s for h in st.session_state.view_head_filter for s in SUBHEAD_LIST.get(h, [])})
    c4.multiselect("Sub Head", sub_opts, key="view_sub_filter")   # ⬅️ changed to multiselect

    selected_status = st.selectbox("🔘 Status", ["All", "Pending", "Resolved"], key="view_status_filter")

    # Apply filters
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
    filtered = filtered.applymap(lambda x: x.replace("\n", " ") if isinstance(x, str) else x)
    filtered = filtered.sort_values("Date of Inspection")

    st.write(f"🔹 Showing {len(filtered)} record(s) from **{start_date.strftime('%d.%m.%Y')}** "
             f"to **{end_date.strftime('%d.%m.%Y')}**")
    # Summary metrics
    col_a, col_b, col_c, col_d = st.columns(4)    
    pending_count     = (filtered["Status"] == "Pending").sum()
    no_response_count = filtered["Feedback"].isna().sum() + (filtered["Feedback"].astype(str).str.strip() == "").sum()
    resolved_count    = (filtered["Status"] == "Resolved").sum()
    
    col_a.metric("🟨 Pending", pending_count)
    col_b.metric("⚠️ No Response", no_response_count)
    col_c.metric("🟩 Resolved", resolved_count)
    col_d.metric("📊 Total Records", len(filtered))

    # ---------- SUB HEAD DISTRIBUTION CHART ----------
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

            # group very small into Others
            thresh = 0.02
            display_data["Percent"] = display_data["Count"] / total_subs
            major = display_data[display_data["Percent"] >= thresh][["Sub Head","Count"]]
            minor = display_data[display_data["Percent"] <  thresh]
            if not minor.empty:
                major = pd.concat([major, pd.DataFrame([{"Sub Head":"Others","Count": minor["Count"].sum()}])],
                                  ignore_index=True)

            # one figure, two axes
            fig, axes = plt.subplots(1, 2, figsize=(16, 8))

            # Pie
            wedges, texts, autotexts = axes[0].pie(
                major["Count"], startangle=90, autopct='%1.1f%%',
                textprops=dict(color='black', fontsize=8)
            )

            # Label fan-out
            for i, (wedge, (_, row)) in enumerate(zip(wedges, major.iterrows())):
                ang = (wedge.theta2 + wedge.theta1) / 2.0
                x = np.cos(np.deg2rad(ang))
                y = np.sin(np.deg2rad(ang))
                place_right = (i % 2 == 0)
                lx = 1.5 if place_right else -1.5
                ly = 1.2 * y
                axes[0].text(lx, ly, f"{row['Sub Head']} ({row['Count']})",
                             ha="left" if place_right else "right",
                             va="center", fontsize=8,
                             bbox=dict(facecolor="white", edgecolor="gray", alpha=0.7, pad=1))
                axes[0].annotate("", xy=(0.9*x, 0.9*y), xytext=(lx, ly),
                                 arrowprops=dict(arrowstyle="-", lw=0.8, color="black"))

            # Table
            table_data = [["Sub Head", "Count"]] + subhead_summary.values.tolist() + [["Total", total_subs]]
            axes[1].axis('off')
            tbl = axes[1].table(cellText=table_data, loc='center')
            tbl.auto_set_font_size(False); tbl.set_fontsize(10); tbl.scale(1, 1.5)

            # Title & context
            fig.suptitle("📊 Sub Head Breakdown", fontsize=14, fontweight="bold")
            dr = f"{start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}"
            heads = ", ".join(st.session_state.view_head_filter)
            type_display = ", ".join(st.session_state.view_type_filter) if st.session_state.view_type_filter else "All Types"
            location_display = st.session_state.view_location_filter or "All Locations"
            fig.text(0.5, 0.02 + 0.015,
                     f"Date Range: {dr}   |   Department: {heads}   |   Type: {type_display}   |   Location: {location_display}",
                     ha='center', fontsize=9, color='gray')
            if st.session_state.view_sub_filter:
                fig.text(0.5, 0.02, f"Sub Head Filter: {st.session_state.view_sub_filter}",
                         ha='center', fontsize=9, color='black', fontweight='bold')

            plt.tight_layout(rect=[0, 0.06, 1, 0.94])
            buf = BytesIO(); plt.savefig(buf, format="png", dpi=200, bbox_inches="tight"); buf.seek(0); plt.close()
            st.image(buf, use_column_width=True)
            st.download_button("📥 Download Sub Head Distribution (PNG)", data=buf,
                               file_name="subhead_distribution.png", mime="image/png")

    # ---------- EXPORT ----------
    from io import BytesIO
    import pandas as pd
    from openpyxl.styles import Alignment, Font, Border, Side, NamedStyle
    
    # Export dataframe
    export_df = filtered[[
        "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
        "Deficiencies Noted", "Inspection By", "Action By", "Feedback", "User Feedback/Remark",
        "Status"
    ]].copy()
    
    # 🔹 Ensure date column is only a date (no time part)
    export_df["Date of Inspection"] = pd.to_datetime(export_df["Date of Inspection"]).dt.date
    
    towb = BytesIO()
    with pd.ExcelWriter(towb, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Filtered Records")
        ws = writer.sheets["Filtered Records"]
    
        # 🔹 Define date format style
        date_style = NamedStyle(name="date_style", number_format="DD-MM-YYYY")
    
        # Apply alignment + wrap text for ALL cells
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    
        # Apply date format only to "Date of Inspection" column
        date_col_idx = export_df.columns.get_loc("Date of Inspection") + 1
        for row in ws.iter_rows(min_row=2, min_col=date_col_idx, max_col=date_col_idx, max_row=len(export_df) + 1):
            for cell in row:
                cell.style = date_style
    
        # Auto column widths
        for col in ws.columns:
            max_length = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except:
                    pass
            adjusted_width = (max_length + 2) if max_length < 50 else 50  # cap width
            ws.column_dimensions[col_letter].width = adjusted_width
    
        # Apply border to all cells
        thin_border = Border(left=Side(style='thin'),
                             right=Side(style='thin'),
                             top=Side(style='thin'),
                             bottom=Side(style='thin'))
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.border = thin_border
    
        # Apply color formatting to Status column
        status_col_idx = export_df.columns.get_loc("Status") + 1
        for row in ws.iter_rows(min_row=2, min_col=status_col_idx, max_col=status_col_idx, max_row=len(export_df) + 1):
            for cell in row:
                if str(cell.value).strip().lower() == "pending":
                    cell.font = Font(color="FF0000")  # Red
                elif str(cell.value).strip().lower() == "resolved":
                    cell.font = Font(color="008000")  # Green
    
    towb.seek(0)
    
    # Streamlit download button
    st.download_button(
        "📥 Export Filtered Records to Excel", 
        data=towb,
        file_name="filtered_records.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# -------------------- STATUS UTILS --------------------
def get_status(feedback, remark):
    return classify_feedback(feedback, remark)

def color_text_status(status):
    return "🔴 Pending" if status == "Pending" else ("🟢 Resolved" if status == "Resolved" else status)

# -------------------- SCROLLBAR & CELL WRAP CSS --------------------
st.markdown(
    """
    <style>
    ::-webkit-scrollbar { width:16px; height:16px; }
    ::-webkit-scrollbar-track { background:#f1f1f1; border-radius:8px; }
    ::-webkit-scrollbar-thumb { background:#888; border-radius:8px; border:3px solid #f1f1f1; }
    ::-webkit-scrollbar-thumb:hover { background:#555; }
    * { scrollbar-width:auto; scrollbar-color:#888 #f1f1f1; }
    </style>
    """,
    unsafe_allow_html=True
)

# -------------------- EDITOR --------------------
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import pandas as pd
import streamlit as st
from datetime import datetime

st.markdown("### ✍️ Edit User Feedback/Remarks in Table")

# Initialize alerts log
if "alerts_log" not in st.session_state:
    st.session_state.alerts_log = []

editable_filtered = filtered.copy()
if not editable_filtered.empty:
    # Ensure stable IDs exist for reliable updates
    if "_original_sheet_index" not in editable_filtered.columns:
        editable_filtered["_original_sheet_index"] = editable_filtered.index
    if "_sheet_row" not in editable_filtered.columns:
        editable_filtered["_sheet_row"] = editable_filtered.index + 2  # sheet row (header + 1)

    display_cols = [
        "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
        "Deficiencies Noted", "Inspection By", "Action By", "Feedback",
        "User Feedback/Remark"
    ]
    editable_df = editable_filtered[display_cols].copy()

    # Show only date part (YYYY-MM-DD)
    if "Date of Inspection" in editable_df.columns:
        editable_df["Date of Inspection"] = pd.to_datetime(
            editable_df["Date of Inspection"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")

    # Status column
    editable_df.insert(
        editable_df.columns.get_loc("User Feedback/Remark") + 1,
        "Status",
        [get_status(r["Feedback"], r["User Feedback/Remark"]) for _, r in editable_df.iterrows()]
    )
    editable_df["Status"] = editable_df["Status"].apply(color_text_status)

    # Carry ID columns through grid (hidden)
    editable_df["_original_sheet_index"] = editable_filtered["_original_sheet_index"].values
    editable_df["_sheet_row"] = editable_filtered["_sheet_row"].values

    # -------- AG GRID CONFIG (wrap + auto height, only remarks editable) --------
    gb = GridOptionsBuilder.from_dataframe(editable_df)
    gb.configure_default_column(editable=False, wrapText=True, autoHeight=True)

    # Make ONLY "User Feedback/Remark" editable with a large text editor popup
    gb.configure_column(
        "User Feedback/Remark",
        editable=True,
        wrapText=True,
        autoHeight=True,
        cellEditor="agLargeTextCellEditor",
        cellEditorPopup=True,
        cellEditorParams={"maxLength": 4000, "rows": 10, "cols": 60}
    )

    # Hide helper ID columns
    gb.configure_column("_original_sheet_index", hide=True)
    gb.configure_column("_sheet_row", hide=True)

    # Easier editing UX
    gb.configure_grid_options(singleClickEdit=True)

    grid_options = gb.build()

    grid_response = AgGrid(
        editable_df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        height=600,
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True
    )

    edited_df = pd.DataFrame(grid_response["data"])

    c1, c2, _ = st.columns([1, 1, 1])
    submitted = c1.button("✅ Submit Feedback")
    if c2.button("🔄 Refresh Data"):
        st.session_state.df = load_data()
        st.success("✅ Data refreshed successfully!")

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

            # 🔧 Fix: Align indexes before comparing
            common_ids = new_remarks.index.intersection(old_remarks.index)
            diff_mask = new_remarks.loc[common_ids] != old_remarks.loc[common_ids]
            changed_ids = diff_mask[diff_mask].index.tolist()

            if changed_ids:
                diffs = new.loc[changed_ids].copy()
                diffs["_sheet_row"] = orig.loc[changed_ids, "_sheet_row"].values

                # Routing dictionary
                routing = {
                    "Pertains to S&T":        ("SIGNAL & TELECOM", "Sr.DSTE"),
                    "Pertains to OPTG":       ("OPTG", "Sr.DOM"),
                    "Pertains to COMMERCIAL": ("COMMERCIAL", "Sr.DCM"),
                    "Pertains to ELECT/G":    ("ELECT/G", "Sr.DEE/G"),
                    "Pertains to ELECT/TRD":  ("ELECT/TRD", "Sr.DEE/TRD"),
                    "Pertains to ELECT/TRO":  ("ELECT/TRO", "Sr.DEE/TRO"),
                    "Pertains to Sr.DEN/S":   ("ENGINEERING", "Sr.DEN/S"),
                    "Pertains to Sr.DEN/C":   ("ENGINEERING", "Sr.DEN/C"),
                    "Pertains to Sr.DEN/Co":  ("ENGINEERING", "Sr.DEN/Co"),
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

                            # 👉 Build alert message (now includes Forwarded By)
                            alert_msg = (
                                f"📌 **{head} Department Alert**\n"
                                f"- Date: {date_str}\n"
                                f"- Deficiency: {deficiency}\n"
                                f"- Forwarded By: {forwarded_by}\n"
                                f"- Forwarded Remark: {user_remark}"
                            )

                            # Insert at top of log
                            st.session_state.alerts_log.insert(0, alert_msg)

                    # ✅ Replace Feedback with new remark (no append)
                    diffs.at[oid, "Feedback"] = user_remark
                    diffs.at[oid, "User Feedback/Remark"] = ""

                    st.session_state.df.at[oid, "Feedback"] = user_remark
                    st.session_state.df.at[oid, "User Feedback/Remark"] = ""

                # Persist to storage (expects _sheet_row in diffs)
                update_feedback_column(diffs.reset_index().rename(columns={"index": "_original_sheet_index"}))
                st.success(f"✅ Updated {len(changed_ids)} Feedback row(s) with new remarks.")
            else:
                st.info("ℹ️ No changes detected to save.")

    # ---------------- PENDING COMPLIANCE DATES ----------------
    head_selected = editable_filtered["Head"].dropna().unique()
    if len(head_selected) == 1:  # only when exactly one head is selected
        head_selected = head_selected[0]

        # ✅ Ensure dates are parsed
        editable_filtered["Date of Inspection"] = pd.to_datetime(
            editable_filtered["Date of Inspection"], format="%Y-%m-%d", errors="coerce"
        )

        start_date = datetime(2025, 7, 1)
        end_date = datetime.today()

        pending_df = editable_filtered[
            (editable_filtered["Head"] == head_selected)
            & (editable_filtered["Date of Inspection"].between(start_date, end_date))
        ][["Date of Inspection"]].copy()

        if not pending_df.empty:
            pending_df["Date of Inspection"] = pending_df["Date of Inspection"].dt.strftime("%Y-%m-%d")
            st.markdown("#### 📅 Pending Compliance Dates")
            st.table(pending_df)
        else:
            st.info("ℹ️ No pending compliance dates found in the given range.")

else:
    st.info("Deficiencies will be updated soon !")




# ---------------- ALERT LOG SECTION ----------------
st.markdown("## 📋 Alerts Log")

if st.session_state.alerts_log:
    for i, log in enumerate(st.session_state.alerts_log):
        with st.expander(f"🔔 Alert {i+1}", expanded=True):
            st.markdown(log, unsafe_allow_html=True)
            if st.button("Mark as Read", key=f"mark_{i}"):
                st.session_state.alerts_log.pop(i)
                st.session_state.last_alert_clicked = i  # save position
                st.rerun()

# After rerun, if we just clicked
if "last_alert_clicked" in st.session_state:
    st.markdown(
        f"""
        <script>
            var el = window.document.querySelector('details');
            if (el) {{
                el.scrollIntoView({{behavior: "smooth", block: "start"}});
            }}
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
    <marquee behavior="scroll" direction="left" style="color:red;font-weight:bold;font-size:16px;">
        For any correction in data, contact Safety Department on sursafetyposition@gmail.com, Contact: Rly phone no. 55620, Cell: +91 9022507772
    </marquee>
    """,
    unsafe_allow_html=True
)

st.markdown("""
**Use the following syntax or copy to forward attention to other department:**  

- For Operating: Pertains to **OPTG**  
- For Signal & Telecom: Pertains to **S&T** 
- For Commercial: Pertains to **COMMERCIAL**
- For ELECT/G: Pertains to **ELECT/G**
- For ELECT/TRD: Pertains to **ELECT/TRD**
- For ELECT/TRO: Pertains to **ELECT/TRO**
- For Engineering South: Pertains to **Sr.DEN/S**
- For Engineering North: Pertains to **Sr.DEN/C**

""")











