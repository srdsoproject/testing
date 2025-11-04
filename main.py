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

# ---------- LANGUAGE SUPPORT ----------

LANGUAGES = {

    "en": {

        "title": "🔐 Login to S.A.R.A.L (Safety Abnormality Report & Action List)",

        "welcome": "✅ Welcome, {name}!",

        "invalid_credentials": "❌ Invalid email or password.",

        "ack_title": "📢 Pending Deficiencies Compliance",

        "ack_notice": """

        The compliance of deficiencies of previous dates are pending & needs to be completed immediately.

        I hereby declare that I have read this notice and will ensure compliance.

        """,

        "ack_submit": "Submit Acknowledgment",

        "ack_error": "❌ Please enter your name before submitting.",

        "ack_success": "✅ Thank you, {name}, for acknowledging.",

        "responses_title": "📝 Responses Received",

        "no_responses": "No responses submitted yet.",

        "clear_responses": "🗑️ Clear All Responses",

        "clear_success": "✅ All responses have been cleared.",

        "gsheet_success": "✅ Connected to Google Sheets!",

        "logout": "🚪 Logout",

        "view_records": "📊 View Records",

        "analytics": "📈 Analytics",

        "no_data": "No data available. Please check Google Sheets connection or refresh.",

        "showing_records": "🔹 Showing {count} record(s) from **{start}** to **{end}**",

        "pending": "🟨 Pending",

        "no_response": "⚠️ No Response",

        "resolved": "🟩 Resolved",

        "total_records": "📊 Total Records",

        "resolution_rate": "🟢 Resolution Rate",

        "subhead_dist": "📊 Sub Head Distribution",

        "download_subhead": "📥 Download Sub Head Distribution (PNG)",

        "export_filtered": "📥 Export Filtered Records to Excel",

        "edit_table": "✍️ Edit User Feedback/Remarks in Table",

        "table_caption": "Edit 'User Feedback/Remark' column. Use column headers to sort or filter.",

        "submit_feedback": "✅ Submit Feedback",

        "refresh_data": "🔄 Refresh Data",

        "refresh_success": "✅ Data refreshed successfully!",

        "no_changes": "ℹ️ No changes detected to save.",

        "deficiencies_soon": "Deficiencies will be updated soon!",

        "alerts_log": "📋 Alerts Log",

        "no_alerts": "✅ No pending alerts.",

        "mark_read": "Mark as Read",

        "footer": """

        For any correction in data, contact Safety Department on sursafetyposition@gmail.com, Contact: Rly phone no. 55620, Cell: +91 9022507772

        """,

        "forward_instructions": """

        **Use the following syntax to forward attention to other department:**

        - For Operating: Pertains to **OPTG**

        - For Signal & Telecom: Pertains to **S&T**

        - For Commercial: Pertains to **COMMERCIAL**

        - For ELECT/G: Pertains to **ELECT/G**

        - For ELECT/TRD: Pertains to **ELECT/TRD**

        - For ELECT/TRO: Pertains to **ELECT/TRO**

        - For Engineering South: Pertains to **Sr.DEN/S**

        - For Engineering North: Pertains to **Sr.DEN/C**

        - For Engineering Coordination: Pertains to **Sr.DEN/Co**

        - For Finance Department: Pertains to **FINAINCE**

        - For Store Department: Pertains to **STORE**

        - For Medical Department: Pertains to **MEDICAL**

        """,

        "credit": """

        **Designed & Developed by** <span class="highlight">Safety Department</span>, <em>Solapur Division</em>

        """,

        "pending_trend": "📊 Pending Deficiencies Trend (Bar + Trend Line)",

        "dept_pending": "🏢 Department-wise Pending Counts",

        "critical_depts": "Critical Departments with Pending Compliances: {text}",

        "critical_locations": "🚨 Top 3 Critical Locations",

        "loc_pending": "📍 Pending Deficiencies by Location / Gate / Section",

        "no_pending": "No pending deficiencies to display.",

        "filter_form": "🔍 Apply Filters",

        "apply_filters": "Apply Filters",

        "search_label": "Search All Columns (case-insensitive)",

        "search_info": "Found {count} matching rows after search.",

        "filter_info": "Applied filters to {count} rows.",

        "sheet_error": "❌ Error accessing Google Sheet: {error}",

        "column_missing": "⚠️ Missing required columns in sheet: {columns}",

    },

    "hi": {

        "title": "🔐 S.A.R.A.L में लॉगिन करें (संरक्षा असामान्यता रिपोर्ट और कार्य सूची)",

        "welcome": "✅ स्वागत है, {name}!",

        "invalid_credentials": "❌ अमान्य ईमेल या पासवर्ड।",

        "ack_title": "📢 लंबित कमी अनुपालन",

        "ack_notice": """

        पिछली तारीखों की कमियों का अनुपालन लंबित है और इसे तत्काल पूरा करना होगा।

        मैं hereby घोषणा करता हूँ कि मैंने इस नोटिस को पढ़ लिया है और अनुपालन सुनिश्चित करूँगा।

        """,

        "ack_submit": "स्वीकृति जमा करें",

        "ack_error": "❌ कृपया जमा करने से पहले अपना नाम दर्ज करें।",

        "ack_success": "✅ धन्यवाद, {name}, स्वीकृति के लिए।",

        "responses_title": "📝 प्राप्त प्रतिक्रियाएँ",

        "no_responses": "अभी तक कोई प्रतिक्रिया जमा नहीं की गई।",

        "clear_responses": "🗑️ सभी प्रतिक्रियाएँ हटाएँ",

        "clear_success": "✅ सभी प्रतिक्रियाएँ हटा दी गई हैं।",

        "gsheet_success": "✅ Google Sheets से जुड़ा!",

        "logout": "🚪 लॉगआउट",

        "view_records": "📊 रिकॉर्ड देखें",

        "analytics": "📈 विश्लेषण",

        "no_data": "कोई डेटा उपलब्ध नहीं है। कृपया Google Sheets कनेक्शन जांचें या रिफ्रेश करें।",

        "showing_records": "🔹 {count} रिकॉर्ड दिखा रहा है **{start}** से **{end}** तक",

        "pending": "🟨 लंबित",

        "no_response": "⚠️ कोई प्रतिक्रिया नहीं",

        "resolved": "🟩 हल किया गया",

        "total_records": "📊 कुल रिकॉर्ड",

        "resolution_rate": "🟢 समाधान दर",

        "subhead_dist": "📊 उप-शीर्षक वितरण",

        "download_subhead": "📥 उप-शीर्षक वितरण डाउनलोड करें (PNG)",

        "export_filtered": "📥 फ़िल्टर किए गए रिकॉर्ड Excel में निर्यात करें",

        "edit_table": "✍️ तालिका में उपयोगकर्ता प्रतिक्रिया/टिप्पणी संपादित करें",

        "table_caption": "'उपयोगकर्ता प्रतिक्रिया/टिप्पणी' कॉलम संपादित करें। कॉलम हेडर का उपयोग क्रमबद्ध करने या फ़िल्टर करने के लिए करें।",

        "submit_feedback": "✅ प्रतिक्रिया जमा करें",

        "refresh_data": "🔄 डेटा रिफ्रेश करें",

        "refresh_success": "✅ डेटा सफलतापूर्वक रिफ्रेश किया गया!",

        "no_changes": "ℹ️ कोई परिवर्तन सहेजने के लिए नहीं मिला।",

        "deficiencies_soon": "कमियाँ जल्द ही अपडेट की जाएँगी!",

        "alerts_log": "📋 अलर्ट लॉग",

        "no_alerts": "✅ कोई लंबित अलर्ट नहीं।",

        "mark_read": "पढ़ा गया के रूप में चिह्नित करें",

        "footer": """

        डेटा में किसी भी सुधार के लिए, संरक्षा विभाग से संपर्क करें: sursafetyposition@gmail.com, संपर्क: रेलवे फोन नं. 55620, सेल: +91 9022507772

        """,

        "forward_instructions": """

        **अन्य विभाग को ध्यान देने के लिए निम्नलिखित सिंटेक्स का उपयोग करें:**

        - ऑपरेटिंग के लिए: **OPTG** से संबंधित

        - सिग्नल और टेलीकॉम के लिए: **S&T** से संबंधित

        - कमर्शियल के लिए: **COMMERCIAL** से संबंधित

        - ELECT/G के लिए: **ELECT/G** से संबंधित

        - ELECT/TRD के लिए: **ELECT/TRD** से संबंधित

        - ELECT/TRO के लिए: **ELECT/TRO** से संबंधित

        - इंजीनियरिंग साउथ के लिए: **Sr.DEN/S** से संबंधित

        - इंजीनियरिंग नॉर्थ के लिए: **Sr.DEN/C** से संबंधित

        - इंजीनियरिंग समन्वय के लिए: **Sr.DEN/Co** से संबंधित

        - वित्त विभाग के लिए: **FINAINCE** से संबंधित

        - स्टोर विभाग के लिए: **STORE** से संबंधित

        - मेडिकल विभाग के लिए: **MEDICAL** से संबंधित

        """,

        "credit": """

        **डिज़ाइन और विकसित किया गया** <span class="highlight">सुरक्षा विभाग</span>, <em>सोलापुर डिवीजन</em> द्वारा

        """,

        "pending_trend": "📊 लंबित कमियों का रुझान (बार + ट्रेंड लाइन)",

        "dept_pending": "🏢 विभाग-वार लंबित गणना",

        "critical_depts": "लंबित अनुपालन वाले महत्वपूर्ण विभाग: {text}",

        "critical_locations": "🚨 शीर्ष 3 महत्वपूर्ण स्थान",

        "loc_pending": "📍 स्थान / गेट / अनुभाग द्वारा लंबित कमियाँ",

        "no_pending": "प्रदर्शित करने के लिए कोई लंबित कमियाँ नहीं।",

        "filter_form": "🔍 फ़िल्टर लागू करें",

        "apply_filters": "फ़िल्टर लागू करें",

        "search_label": "सभी कॉलम खोजें (केस-असंवेदनशील)",

        "search_info": "खोज के बाद {count} मिलान करने वाली पंक्तियाँ मिलीं।",

        "filter_info": "{count} पंक्तियों पर फ़िल्टर लागू किए गए।",

        "sheet_error": "❌ Google Sheet तक पहुँचने में त्रुटि: {error}",

        "column_missing": "⚠️ शीट में आवश्यक कॉलम अनुपस्थित: {columns}",

    }

}

# Initialize language

if "language" not in st.session_state:

    st.session_state.language = "en"

lang = LANGUAGES[st.session_state.language]

# ---------- SESSION STATE INITIALIZATION ----------

if "logged_in" not in st.session_state:

    st.session_state.logged_in = False

if "user" not in st.session_state:

    st.session_state.user = {}

if "alerts_log" not in st.session_state:

    st.session_state.alerts_log = []

if "df" not in st.session_state:

    st.session_state.df = None

if "global_search" not in st.session_state:

    st.session_state.global_search = ""

# ---------- LOGIN ----------

def login(email, password):

    """Check credentials against st.secrets['users']"""

    try:

        for user in st.secrets["users"]:

            if user["email"] == email and user["password"] == password:

                return user

        return None

    except KeyError:

        st.error("❌ Configuration error: User credentials not found.")

        return None

if not st.session_state.logged_in:

    st.title(lang["title"])

    with st.form("login_form", clear_on_submit=True):

        email = st.text_input("📧 Email")

        password = st.text_input("🔒 Password", type="password")

        submitted = st.form_submit_button("Login")

        if submitted:

            user = login(email, password)

            if user:

                st.session_state.logged_in = True

                st.session_state.user = user

                st.success(lang["welcome"].format(name=user['name']))

                st.rerun()

            else:

                st.error(lang["invalid_credentials"])

    st.stop()

# ---------- GOOGLE SHEETS CONNECTION ----------

@st.cache_resource

def connect_to_gsheet():

    try:

        SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

        service_account_info = dict(st.secrets["gcp_service_account"])

        if "private_key" in service_account_info:

            service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")

        creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)

        gc = gspread.authorize(creds)

        SHEET_ID = "1_WQyJCtdXuAIQn3IpFTI4KfkrveOHosNsvsZn42jAvw"

        return gc.open_by_key(SHEET_ID)

    except Exception as e:

        st.error(lang["sheet_error"].format(error=str(e)))

        st.stop()

gsheet = connect_to_gsheet()

sheet = gsheet.worksheet("Sheet1")

try:

    ack_sheet = gsheet.worksheet("Acknowledgments")

except gspread.exceptions.WorksheetNotFound:

    ack_sheet = gsheet.add_worksheet(title="Acknowledgments", rows=100, cols=2)

    ack_sheet.append_row(["UserID", "Name"])

st.sidebar.success(lang["gsheet_success"])

# ---------- ACKNOWLEDGMENT ----------

user_id = st.session_state.user["email"]

try:

    ack_data = ack_sheet.get_all_values()

    ack_df = pd.DataFrame(ack_data[1:], columns=ack_data[0]) if len(ack_data) > 1 else pd.DataFrame(columns=["UserID", "Name"])

except Exception as e:

    st.error(lang["sheet_error"].format(error=str(e)))

    st.stop()

user_ack_done = user_id in ack_df["UserID"].values

if not user_ack_done:

    st.title(lang["ack_title"])

    with st.expander(lang["ack_title"], expanded=True):

        st.info(lang["ack_notice"])

        with st.form("ack_form"):

            responder_name = st.text_input("✍️ Your Name")

            ack_submitted = st.form_submit_button(lang["ack_submit"])

            if ack_submitted:

                if responder_name.strip():

                    try:

                        ack_sheet.append_row([user_id, responder_name.strip()])

                        st.success(lang["ack_success"].format(name=responder_name))

                        st.rerun()

                    except Exception as e:

                        st.error(lang["sheet_error"].format(error=str(e)))

                else:

                    st.error(lang["ack_error"])

    st.stop()

# ---------- DISPLAY ALL RESPONSES ----------

st.markdown(f"### {lang['responses_title']}")

try:

    if not ack_df.empty:

        st.dataframe(ack_df)

    else:

        st.write(lang["no_responses"])

except Exception as e:

    st.error(lang["sheet_error"].format(error=str(e)))

if st.button(lang["clear_responses"], key="clear_responses_btn"):

    try:

        ack_sheet.clear()

        ack_sheet.append_row(["UserID", "Name"])

        st.success(lang["clear_success"])

        st.rerun()

    except Exception as e:

        st.error(lang["sheet_error"].format(error=str(e)))

# ---------- SIDEBAR ----------

st.sidebar.markdown(f"👤 {lang['welcome'].format(name=st.session_state.user['name'])}")

st.sidebar.markdown(f"📧 {st.session_state.user['email']}")

if st.sidebar.button(lang["logout"]):

    st.session_state.logged_in = False

    st.session_state.user = {}

    st.rerun()

# Language Toggle

st.sidebar.selectbox(

    "🌐 Language",

    options=["English", "Hindi"],

    index=0 if st.session_state.language == "en" else 1,

    key="language_select",

    on_change=lambda: st.session_state.update(

        {"language": "en" if st.session_state.language_select == "English" else "hi"}

    )

)

# ---------- CONSTANT LISTS ----------

STATION_LIST = sorted(set([

    'BRB', 'MLM', 'BGVN', 'JNTR', 'PRWD', 'WSB', 'PPJ', 'JEUR', 'KEM', 'BLNI', 'DHS', 'KWV', 'WDS', 'MA', 'AAG',

    'MKPT', 'MO', 'MVE', 'PK', 'BALE', "SUR", 'TKWD', 'HG', 'TLT', 'AKOR', 'NGS', 'BOT', 'DUD', 'KUI', 'GDGN', 'GUR',

    'HHD', 'SVG', 'BBD', 'TJSP', 'KLBG', 'HQR', 'MR', 'SDB', 'WADI', 'ARAG', 'BLNK', 'SGRE', 'KVK', 'LNP', 'DLGN',

    'JTRD', 'MSDG', 'JVA', 'WSD', 'SGLA', 'PVR', 'MLB', 'SEI', 'BTW', 'PJR', 'DRSV', 'YSI', 'KMRD', 'DKY', 'MRX',

    'OSA', 'HGL', 'LUR', 'NTPC', 'MRJ', 'BHLI'

]))

GATE_LIST = sorted(set([

    'LC-19', 'LC-22A', 'LC-25', 'LC-26', 'LC-27C', 'LC-28', 'LC-30', 'LC-31', 'LC-35', 'LC-37', 'LC-40', 'LC-41',

    'LC-43', 'LC-44', 'LC-45', 'LC-46C', 'LC-54', 'LC-61', 'LC-66', 'LC-74', 'LC-76', 'LC-78', 'LC-82', 'LC-1',

    'LC-60A', 'LC-1 TLT ZCL', 'LC-1 ACC', 'LC-2 ACC', 'LC-91', 'LC-22', 'LC-24', 'LC-32', 'LC-49', 'LC-70',

    'LC-10', 'LC-34', 'LC-36', 'LC-47', 'LC-55', 'LC-59', 'LC-2', 'LC-4', 'LC-42', 'LC-02', 'LC-128', 'LC-63',

    'LC-04', 'LC-67', 'LC-77', 'LC-75', 'LC-64', 'LC-65', 'LC-5', 'LC-6', 'LC-57', 'LC-62', 'LC-39', 'LC-2/C',

    'LC-6/C', 'LC-11', 'LC-03', 'LC-15/C', 'LC-21', 'LC-26-A', 'LC-60'

]))

FOOTPLATE_ROUTES = sorted(set(["SUR-DD", "SUR-WADI", "LUR-KWV", 'KWV-MRJ', 'DD-SUR', 'WADI-SUR', 'KWV-LUR', 'MRJ-KWV']))

ALL_LOCATIONS = sorted(set(STATION_LIST + GATE_LIST + FOOTPLATE_ROUTES))

HEAD_LIST = ["", "ELECT/TRD", "ELECT/G", "ELECT/TRO", "SIGNAL & TELECOM", "OPTG", "MECHANICAL",

             "ENGINEERING", "COMMERCIAL", "C&W", "PERSONNEL", "SECURITY", "FINANCE", "MEDICAL", "STORE"]

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

# ---------- HELPERS ----------

def normalize_str(text):

    if not isinstance(text, str):

        return ""

    return re.sub(r'\s+', ' ', text.lower()).strip()

def classify_feedback(feedback, user_remark=""):

    text = normalize_str(feedback + " " + user_remark)

    if not text or text == "`":

        return "Pending"

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

        "under process", "not yet", "to be done", "will ensure", "during next", "action will be taken", 'noted please tdc',

        "will be supplied shortly", "not available", "not updated", "progress", "under progress",

        "to arrange", "awaited", "material awaited", "approval awaited", "to procure", "yet pending",

        "incomplete", "tentative", "ongoing", "in progress", "being done", "arranging", "waiting for",

        "subject to", "awaiting approval", "awaiting material", "awaiting confirmation", "next schedule",

        "planned for", "will arrange", "proposed date", "to complete", "to be completed",

        "likely completion", "expected completion", "not received", "awaiting response"

    ]

    if re.search(r'[#!]', text):

        return "Resolved" if text.endswith('#') else "Pending"

    if any(kw in text for kw in resolved_kw):

        return "Resolved"

    if any(kw in text for kw in pending_kw) or re.search(r'\d{1,2}[/-]\d{1,2}', text):

        return "Pending"

    return "Pending"

def color_text_status(status):

    return "🔴 Pending" if status == "Pending" else ("🟢 Resolved" if status == "Resolved" else status)

def filter_dataframe(df: pd.DataFrame, include_index: bool = False) -> pd.DataFrame:

    df_filtered = df.copy()

    for column in st.session_state.get("selected_columns_for_filter", []):

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

    try:

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

    except Exception as e:

        st.error(lang["sheet_error"].format(error=str(e)))

# ---------- LOAD DATA ----------

@st.cache_data(ttl=300)

def load_data():

    REQUIRED_COLS = [

        "Date of Inspection", "Type of Inspection", "Location",

        "Head", "Sub Head", "Deficiencies Noted",

        "Inspection By", "Action By", "Feedback",

        "User Feedback/Remark", "Gate", "Section"

    ]

    try:

        data = sheet.get_all_values()

        if not data or len(data) < 2:

            st.warning(lang["no_data"])

            return pd.DataFrame(columns=REQUIRED_COLS)

        headers = [c.strip() for c in data[0]]

        missing = [col for col in REQUIRED_COLS if col not in headers]

        if missing:

            st.error(lang["column_missing"].format(columns=", ".join(missing)))

            st.stop()

        df = pd.DataFrame(data[1:], columns=headers)

        for col in REQUIRED_COLS:

            if col not in df.columns:

                df[col] = ""

        df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")

        df["Location"] = df["Location"].astype(str).str.strip().str.upper()

        df["Gate"] = df["Gate"].astype(str).str.strip().str.upper()

        df["Section"] = df["Section"].astype(str).str.strip().str.upper()

        df["_sheet_row"] = df.index + 2

        return df

    except Exception as e:

        st.error(lang["sheet_error"].format(error=str(e)))

        return pd.DataFrame(columns=REQUIRED_COLS)

# Initialize df if None

if st.session_state.df is None:

    st.session_state.df = load_data()

# ---------- HEADER ----------

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

    <style>

    @media (prefers-color-scheme: light) {

      :root {

        --text-color: #1a1a1a;

        --text-highlight: #0d47a1;

        --text-sub: #1565c0;

        --bg-glass: rgba(255, 255, 255, 0.75);

        --border-color: #40c4ff;

        --shadow-base: rgba(64, 196, 255, 0.2);

        --shadow-hover: rgba(64, 196, 255, 0.35);

        --glow-color: rgba(179, 229, 252, 0.9);

      }

    }

    @media (prefers-color-scheme: dark) {

      :root {

        --text-color: #ffffff;

        --text-highlight: #e3f2fd;

        --text-sub: #bbdefb;

        --bg-glass: rgba(15, 25, 45, 0.65);

        --border-color: #40c4ff;

        --shadow-base: rgba(64, 196, 255, 0.15);

        --shadow-hover: rgba(64, 196, 255, 0.4);

        --glow-color: rgba(179, 229, 252, 0.95);

      }

    }

    .stTable { overflow-x: auto; }

    </style>

    """,

    unsafe_allow_html=True

)

# ---------- TABS ----------

tabs = st.tabs([lang["view_records"], lang["analytics"]])

with tabs[0]:

    df = st.session_state.df

    if df is None or df.empty:

        st.warning(lang["no_data"])

        st.stop()

    for col in ["Type of Inspection", "Location", "Head", "Sub Head", "Deficiencies Noted",

                "Inspection By", "Action By", "Feedback", "User Feedback/Remark", "Gate", "Section"]:

        if col not in df.columns:

            df[col] = ""

    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")

    df["_original_sheet_index"] = df.index

    df["Status"] = df.apply(lambda r: classify_feedback(r["Feedback"], r.get("User Feedback/Remark", "")), axis=1)

    # ---------- FILTER FORM ----------

    with st.form("filters_form"):

        st.markdown(f"### {lang['filter_form']}")

        col1, col2 = st.columns(2)

        with col1:

            type_filter = st.multiselect(lang["view_records"], VALID_INSPECTIONS, key="view_type_filter")

            head_filter = st.multiselect("Head", HEAD_LIST[1:], key="view_head_filter")

            insp_filter = st.multiselect("Inspection By", INSPECTION_BY_LIST[1:], key="view_insp_filter")

            from_date = st.date_input("📅 From Date", value=df["Date of Inspection"].min(), key="view_from_date")

        with col2:

            loc_filter = st.multiselect("Location", ALL_LOCATIONS, key="view_location_filter")

            sub_opts = sorted({s for h in head_filter for s in SUBHEAD_LIST.get(h, [])})

            sub_filter = st.multiselect("Sub Head", sub_opts, key="view_sub_filter")

            action_filter = st.multiselect("Action By", ACTION_BY_LIST[1:], key="view_action_filter")

            to_date = st.date_input("📅 To Date", value=df["Date of Inspection"].max(), key="view_to_date")

        status_filter = st.selectbox("🔘 Status", ["All", "Pending", "Resolved"], key="view_status_filter")

        apply_filters = st.form_submit_button(lang["apply_filters"])

    # Apply Filters

    filtered = df.copy()

    if apply_filters:

        if type_filter:

            filtered = filtered[filtered["Type of Inspection"].isin(type_filter)]

        if loc_filter:

            filtered = filtered[filtered["Location"].isin(loc_filter)]

        if head_filter:

            filtered = filtered[filtered["Head"].isin(head_filter)]

        if sub_filter:

            filtered = filtered[filtered["Sub Head"].isin(sub_filter)]

        if insp_filter:

            filtered = filtered[filtered["Inspection By"].apply(

                lambda x: any(s.strip() in str(x).split(",") for s in insp_filter)

            )]

        if action_filter:

            filtered = filtered[filtered["Action By"].apply(

                lambda x: any(s.strip() in str(x).split(",") for s in action_filter)

            )]

        if from_date and to_date:

            filtered = filtered[

                (filtered["Date of Inspection"] >= pd.to_datetime(from_date)) &

                (filtered["Date of Inspection"] <= pd.to_datetime(to_date))

            ]

        if status_filter != "All":

            filtered = filtered[filtered["Status"] == status_filter]

    filtered = filtered.apply(lambda x: x.str.replace("\n", " ") if x.dtype == "object" else x)

    filtered = filtered.sort_values("Date of Inspection")

    start_date = filtered["Date of Inspection"].min() if not filtered["Date of Inspection"].isna().all() else pd.Timestamp.today()

    end_date = filtered["Date of Inspection"].max() if not filtered["Date of Inspection"].isna().all() else pd.Timestamp.today()

    st.write(lang["showing_records"].format(

        count=len(filtered),

        start=start_date.strftime('%d.%m.%Y'),

        end=end_date.strftime('%d.%m.%Y')

    ))

    # ---------- METRICS ----------

    pending_count = (filtered["Status"] == "Pending").sum()

    no_response_count = filtered["Feedback"].isna().sum() + (filtered["Feedback"].astype(str).str.strip() == "").sum()

    resolved_count = (filtered["Status"] == "Resolved").sum()

    resolution_rate = resolved_count / max(1, len(filtered)) * 100

    col_a, col_b, col_c, col_d = st.columns(4)

    col_a.metric(lang["pending"], pending_count)

    col_b.metric(lang["no_response"], no_response_count)

    col_c.metric(lang["resolved"], resolved_count)

    col_d.metric(lang["resolution_rate"], f"{resolution_rate:.1f}%")

    st.progress(resolution_rate / 100, text="Resolution Progress")

    # ---------- SUBHEAD DISTRIBUTION ----------

    if head_filter and not filtered.empty:

        st.markdown(f"### {lang['subhead_dist']}")

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

            pie = alt.Chart(major).mark_arc().encode(

                theta=alt.Theta("Count:Q"),

                color=alt.Color("Sub Head:N"),

                tooltip=["Sub Head", "Count"]

            ).properties(width="container", height=400)

            st.altair_chart(pie, use_container_width=True)

            st.download_button(

                lang["download_subhead"],

                data=pie.to_json(),

                file_name="subhead_distribution.json",

                mime="application/json"

            )

    # ---------- EXPORT FILTERED DATA ----------

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

            adjusted_width = (max_length + 2) if max_length < 50 else 50

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

        lang["export_filtered"],

        data=towb,

        file_name=f"filtered_records_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.xlsx",

        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    )

    # ---------- EDITOR ----------

    st.markdown(f"### {lang['edit_table']}")

    if not filtered.empty:

        display_cols = [

            "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",

            "Deficiencies Noted", "Inspection By", "Action By", "Feedback",

            "User Feedback/Remark"

        ]

        valid_cols = [col for col in display_cols if col in filtered.columns]

        if not valid_cols:

            st.error(lang["column_missing"].format(columns=", ".join(display_cols)))

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

            editable_df["Date of Inspection"] = pd.to_datetime(editable_df["Date of Inspection"]).dt.date

        if "Feedback" in editable_df.columns and "User Feedback/Remark" in editable_df.columns:

            editable_df.insert(

                editable_df.columns.get_loc("User Feedback/Remark") + 1,

                "Status",

                [classify_feedback(r["Feedback"], r["User Feedback/Remark"]) for _, r in editable_df.iterrows()]

            )

            editable_df["Status"] = editable_df["Status"].apply(color_text_status)

        # Global Search

        st.markdown("#### 🔍 Search")

        st.session_state.global_search = st.text_input(lang["search_label"], value=st.session_state.global_search)

        if st.session_state.global_search:

            mask = editable_df[valid_cols].astype(str).apply(

                lambda col: col.str.contains(st.session_state.global_search, case=False, na=False)

            ).any(axis=1)

            editable_df = editable_df[mask].copy()

            st.info(lang["search_info"].format(count=len(editable_df)))

        # Column Filtering

        max_cols = st.slider("Max columns to filter on", 1, len(valid_cols), min(5, len(valid_cols)), key="max_cols_filter")

        candidate_columns = valid_cols[:max_cols]

        if "selected_columns_for_filter" not in st.session_state:

            st.session_state.selected_columns_for_filter = []

        selected_columns = st.multiselect("Select columns to filter", candidate_columns, default=st.session_state.selected_columns_for_filter, key="column_select_filter")

        st.session_state.selected_columns_for_filter = selected_columns

        if selected_columns:

            editable_df = filter_dataframe(editable_df)

            st.info(lang["filter_info"].format(count=len(editable_df)))

        # AgGrid Configuration

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

        gb.configure_column("_original_sheet_index", hide=True)

        gb.configure_column("_sheet_row", hide=True)

        gb.configure_grid_options(singleClickEdit=True, enablePagination=True, paginationPageSize=50)

        gb.configure_grid_options(quickFilterText=st.session_state.global_search)

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

        # Render AgGrid

        st.caption(lang["table_caption"])

        grid_response = AgGrid(

            editable_df,

            gridOptions=grid_options,

            update_mode=GridUpdateMode.VALUE_CHANGED,

            height=600,

            allow_unsafe_jscode=True,

            use_container_width=True

        )

        edited_df = pd.DataFrame(grid_response["data"])

        # Export Edited Data

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

                adjusted_width = (max_length + 2) if max_length < 50 else 50

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

            label=lang["export_filtered"],

            data=towb_edited,

            file_name=f"edited_records_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",

            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        )

        # Buttons

        c1, c2, _ = st.columns([1, 1, 1])

        submitted = c1.button(lang["submit_feedback"])

        if c2.button(lang["refresh_data"]):

            load_data.clear()

            st.session_state.df = load_data()

            st.success(lang["refresh_success"])

            st.rerun()

        # Submit Logic

        if submitted:

            need_cols = {"_original_sheet_index", "User Feedback/Remark"}

            if not need_cols.issubset(edited_df.columns) or "Feedback" not in editable_filtered.columns:

                st.error(lang["column_missing"].format(columns=", ".join(need_cols | {"Feedback"})))

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

                        "Pertains to S&T": ("SIGNAL & TELECOM", "Sr.DSTE"),

                        "Pertains to OPTG": ("OPTG", "Sr.DOM"),

                        "Pertains to COMMERCIAL": ("COMMERCIAL", "Sr.DCM"),

                        "Pertains to ELECT/G": ("ELECT/G", "Sr.DEE/G"),

                        "Pertains to ELECT/TRD": ("ELECT/TRD", "Sr.DEE/TRD"),

                        "Pertains to ELECT/TRO": ("ELECT/TRO", "Sr.DEE/TRO"),

                        "Pertains to Sr.DEN/S": ("ENGINEERING", "Sr.DEN/S"),

                        "Pertains to Sr.DEN/C": ("ENGINEERING", "Sr.DEN/C"),

                        "Pertains to Sr.DEN/Co": ("ENGINEERING", "Sr.DEN/Co"),

                        "Pertains to FINAINCE": ("FINANCE", "Sr.DFM"),

                        "Pertains to STORE": ("STORE", "Sr.DMM"),

                        "Pertains to MEDICAL": ("MEDICAL", "CMS"),

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

                    st.success(f"✅ Updated {len(changed_ids)} Feedback row(s) with new remarks.")

                else:

                    st.info(lang["no_changes"])

    else:

        st.info(lang["deficiencies_soon"])

    # ---------- ALERTS LOG ----------

    st.markdown(f"## {lang['alerts_log']}")

    if st.session_state.alerts_log:

        for i, log in enumerate(st.session_state.alerts_log):

            with st.expander(f"🔔 Alert {i+1}", expanded=True):

                st.markdown(log, unsafe_allow_html=True)

                if st.button(lang["mark_read"], key=f"mark_{i}"):

                    st.session_state.alerts_log.pop(i)

                    st.session_state.last_alert_clicked = i

                    st.rerun()

    else:

        st.info(lang["no_alerts"])

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

with tabs[1]:

    st.markdown(f"### {lang['pending_trend']}")

    df = st.session_state.df.copy()

    if "Status" not in df.columns:

        df["Status"] = df["Feedback"].apply(classify_feedback)

    if df.empty:

        st.info(lang["no_pending"])

    else:

        df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")

        min_date = df["Date of Inspection"].min()

        max_date = df["Date of Inspection"].max()

        start_date, end_date = st.date_input(

            "Select Inspection Date Range",

            value=(min_date, max_date),

            min_value=min_date,

            max_value=max_date

        )

        df = df[(df["Date of Inspection"] >= pd.to_datetime(start_date)) &

                (df["Date of Inspection"] <= pd.to_datetime(end_date))]

        pending = df[

            df["Status"].str.upper().eq("PENDING") |

            df["Feedback"].isna() |

            (df["Feedback"].astype(str).str.strip() == "")

        ].copy()

        pending["Head"] = pending["Head"].astype(str).str.strip().str.upper()

        trend = pending.groupby(pd.Grouper(key="Date of Inspection", freq="M")).size().reset_index(name="PendingCount")

        if not trend.empty:

            trend = trend.sort_values("Date of Inspection").reset_index(drop=True)

            trend["MonthIndex"] = trend.index

            bars = alt.Chart(trend).mark_bar(color="#1f77b4").encode(

                x=alt.X("yearmonth(Date of Inspection):T", title="Inspection Month"),

                y=alt.Y("PendingCount:Q", title="Pending Deficiencies"),

                tooltip=["yearmonth(Date of Inspection):T", "PendingCount"]

            )

            line = alt.Chart(trend).transform_regression("MonthIndex", "PendingCount").mark_line(

                color="red", strokeDash=[5,5], strokeWidth=2

            ).encode(

                x=alt.X("yearmonth(Date of Inspection):T"),

                y="PendingCount:Q"

            )

            st.altair_chart(bars + line, use_container_width=True)

        else:

            st.info(lang["no_pending"])

        st.markdown(f"### {lang['dept_pending']}")

        if not pending.empty:

            dept_counts = pending.groupby("Head").size().reset_index(name="PendingCount").sort_values("PendingCount", ascending=False)

            total_pending = dept_counts["PendingCount"].sum()

            dept_counts["color"] = "#ff7f0e"

            dept_counts.loc[:2, "color"] = "red"

            for _, row in dept_counts.iterrows():

                st.markdown(f"- **{row['Head']}** : {row['PendingCount']}")

            st.markdown(f"**Total Pending : {total_pending}**")

            dept_chart = alt.Chart(dept_counts).mark_bar().encode(

                x=alt.X("PendingCount:Q", title="Pending Deficiencies"),

                y=alt.Y("Head:N", sort='-x', title="Department"),

                color=alt.Color("color:N", scale=None),

                tooltip=["Head", "PendingCount"]

            ).properties(width="container", height=400)

            st.altair_chart(dept_chart, use_container_width=True)

            top3 = dept_counts.head(3)

            critical_text = ", ".join([f"{row['Head']} ({row['PendingCount']})" for _, row in top3.iterrows()])

            st.markdown(lang["critical_depts"].format(text=critical_text))

        else:

            st.info(lang["no_pending"])

        st.markdown(f"### {lang['critical_locations']}")

        for col in ["Location", "Gate", "Section"]:

            if col not in pending.columns:

                pending[col] = ""

        pending["Location"] = pending["Location"].astype(str).str.strip().str.upper()

        pending["Gate"] = pending["Gate"].astype(str).str.strip().str.upper()

        pending["Section"] = pending["Section"].astype(str).str.strip().str.upper()

        combined_counts = pd.concat([

            pending[pending["Location"].isin(STATION_LIST)].groupby("Location").size().reset_index(name="PendingCount"),

            pending[pending["Gate"].isin(GATE_LIST)].groupby("Gate").size().reset_index(name="PendingCount"),

            pending[pending["Section"].isin([s.upper() for s in FOOTPLATE_ROUTES])].groupby("Section").size().reset_index(name="PendingCount")

        ])

        combined_counts = combined_counts.groupby(combined_counts.columns[0]).sum().reset_index()

        combined_counts = combined_counts.sort_values("PendingCount", ascending=False)

        if not combined_counts.empty:

            top3_critical = combined_counts.head(3)

            top3_critical["color"] = "red"

            critical_loc_chart = alt.Chart(top3_critical).mark_bar().encode(

                x=alt.X("PendingCount:Q", title="Pending Deficiencies"),

                y=alt.Y(top3_critical.columns[0]+":N", sort='-x', title="Location / Gate / Section"),

                color=alt.Color("color:N", scale=None),

                tooltip=[top3_critical.columns[0], "PendingCount"]

            ).properties(width="container", height=300)

            st.altair_chart(critical_loc_chart, use_container_width=True)

        else:

            st.info(lang["no_pending"])

        st.markdown(f"### {lang['loc_pending']}")

        selected_locations = st.multiselect("Select Locations", pending["Location"].unique(), default=pending["Location"].unique())

        selected_gates = st.multiselect("Select Gates", pending["Gate"].unique(), default=pending["Gate"].unique())

        selected_sections = st.multiselect("Select Sections", pending["Section"].unique(), default=pending["Section"].unique())

        filtered_pending_final = pending[

            (pending["Location"].isin(selected_locations)) |

            (pending["Gate"].isin(selected_gates)) |

            (pending["Section"].isin(selected_sections))

        ]

        if not filtered_pending_final.empty:

            loc_counts_final = pd.concat([

                filtered_pending_final.groupby("Location").size().reset_index(name="PendingCount"),

                filtered_pending_final.groupby("Gate").size().reset_index(name="PendingCount"),

                filtered_pending_final.groupby("Section").size().reset_index(name="PendingCount")

            ])

            loc_counts_final = loc_counts_final[loc_counts_final.iloc[:,0] != ""]

            loc_counts_final = loc_counts_final.groupby(loc_counts_final.columns[0]).sum().reset_index().sort_values("PendingCount", ascending=False)

            loc_counts_final["color"] = "#ff7f0e"

            loc_counts_final.loc[:2,"color"] = "red"

            loc_chart = alt.Chart(loc_counts_final).mark_bar().encode(

                x=alt.X("PendingCount:Q", title="Pending Deficiencies"),

                y=alt.Y(loc_counts_final.columns[0]+":N", sort='-x', title="Location / Gate / Section"),

                color=alt.Color("color:N", scale=None),

                tooltip=[loc_counts_final.columns[0], "PendingCount"]

            ).properties(width="container", height=500)

            st.altair_chart(loc_chart, use_container_width=True)

        else:

            st.info(lang["no_pending"])

# ---------- FOOTER ----------

st.markdown(

    f"""

    <marquee behavior="scroll" direction="left" style="color:red;font-weight:bold;font-size:16px;">

        {lang['footer']}

    </marquee>

    """,

    unsafe_allow_html=True

)

st.markdown(lang["forward_instructions"], unsafe_allow_html=True)

st.markdown(

    f"""

    <div style="text-align: center; margin: 35px 0;">

      <div class="adaptive-credit">

        <p>

            {lang['credit']}

        </p>

      </div>

    </div>

    <style>

    .adaptive-credit {{

      display: inline-block;

      padding: 14px 36px;

      background: var(--bg-glass);

      border: 2px solid var(--border-color);

      border-radius: 18px;

      backdrop-filter: blur(12px);

      -webkit-backdrop-filter: blur(12px);

      box-shadow: 0 8px 25px var(--shadow-base);

      transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);

      font-family: 'Roboto', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;

      font-size: 15px;

      line-height: 1.5;

    }}

    .adaptive-credit p {{

      margin: 0;

      color: var(--text-color);

      font-weight: 500;

      letter-spacing: 0.8px;

      text-shadow: none;

      transition: text-shadow 0.4s ease;

    }}

    .adaptive-credit p span.highlight {{

      color: var(--text-highlight);

      font-weight: 700;

    }}

    .adaptive-credit p em {{

      font-style: normal;

      color: var(--text-sub);

    }}

    .adaptive-credit:hover {{

      transform: translateY(-4px);

      box-shadow:

        0 14px 35px var(--shadow-hover),

        0 0 40px var(--glow-color),

        0 0 0 1px var(--border-color);

    }}

    .adaptive-credit:hover p {{

      text-shadow:

        0 0 10px var(--glow-color),

        0 0 20px var(--glow-color),

        0 0 30px var(--glow-color),

        0 0 40px rgba(179, 229, 252, 0.6);

    }}

    </style>

    """,

    unsafe_allow_html=True

)

