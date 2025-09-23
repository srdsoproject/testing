import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from matplotlib import pyplot as plt
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode
from openpyxl.styles import Alignment, Font, Border, Side, NamedStyle
import requests
import os

# ---------- CONFIG ----------
st.set_page_config(page_title="Inspection App", layout="wide")
GITHUB_RAW_URL = "https://github.com/srdsoproject/testing/raw/main/responses.xlsx"
LOCAL_FILE = "responses_local.xlsx"

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

# ---------- DATA LOADING ----------
@st.cache_data(ttl=300)
def load_data_from_github():
    REQUIRED_COLS = [
        "Date of Inspection", "Type of Inspection", "Location",
        "Head", "Sub Head", "Deficiencies Noted",
        "Inspection By", "Action By", "Feedback",
        "User Feedback/Remark"
    ]
    try:
        resp = requests.get(GITHUB_RAW_URL)
        resp.raise_for_status()
        df = pd.read_excel(BytesIO(resp.content))
        for col in REQUIRED_COLS:
            if col not in df.columns:
                df[col] = ""
        df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
        df["Location"] = df["Location"].astype(str).str.strip().str.upper()
        df["_sheet_row"] = df.index + 2
        return df
    except Exception as e:
        st.error(f"❌ Could not load Excel from GitHub: {e}")
        return pd.DataFrame(columns=REQUIRED_COLS)

def load_data():
    if os.path.exists(LOCAL_FILE):
        df = pd.read_excel(LOCAL_FILE)
        df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
        if "_sheet_row" not in df.columns:
            df["_sheet_row"] = df.index + 2
        return df
    else:
        return load_data_from_github()

def save_to_local_excel(df):
    df.to_excel(LOCAL_FILE, index=False)
    st.success("✅ Feedback saved locally.")

if st.session_state.df.empty:
    st.session_state.df = load_data()
df = st.session_state.df

# ---------- UTILS ----------
def classify_feedback(feedback, remark=None):
    val = feedback or ""
    return "Pending" if val.strip() == "" else "Resolved"

def get_status(feedback, remark):
    return classify_feedback(feedback, remark)

def color_text_status(status):
    return "🔴 Pending" if status == "Pending" else ("🟢 Resolved" if status == "Resolved" else status)

def update_feedback_column(edited_df):
    df = st.session_state.df
    for _, row in edited_df.iterrows():
        r = int(row["_sheet_row"]) - 2
        for col in ["Feedback", "User Feedback/Remark", "Head", "Action By", "Sub Head"]:
            if col in df.columns and col in row:
                df.at[r, col] = row[col]
    st.session_state.df = df
    save_to_local_excel(df)  # persist locally

# ---------- HEADER ----------
st.markdown("""
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
    (Safety Abnormality Report & Action List – Local Version)
</h3>
""", unsafe_allow_html=True)

# ---------- FILTERS ----------
VALID_INSPECTIONS = df["Type of Inspection"].dropna().unique().tolist()
FOOTPLATE_LIST = df["Location"].dropna().unique().tolist()
HEAD_LIST = df["Head"].dropna().unique().tolist()
SUBHEAD_LIST = {h: df[df["Head"]==h]["Sub Head"].dropna().unique().tolist() for h in HEAD_LIST}

tabs = st.tabs(["📊 View Records", "📈 Analytics"])
with tabs[0]:
    if df.empty:
        st.warning("Deficiencies will be updated soon !")
        st.stop()

    # Filters
    start_date = df["Date of Inspection"].min()
    end_date = df["Date of Inspection"].max()

    c1, c2 = st.columns(2)
    type_filter = c1.multiselect("Type of Inspection", VALID_INSPECTIONS)
    location_filter = c2.multiselect("Location", FOOTPLATE_LIST)

    c3, c4 = st.columns(2)
    head_filter = c3.multiselect("Head", HEAD_LIST)
    sub_opts = sorted({s for h in head_filter for s in SUBHEAD_LIST.get(h, [])})
    sub_filter = c4.multiselect("Sub Head", sub_opts)

    selected_status = st.selectbox("🔘 Status", ["All", "Pending", "Resolved"])

    filtered = df.copy()
    if type_filter:
        filtered = filtered[filtered["Type of Inspection"].isin(type_filter)]
    if location_filter:
        filtered = filtered[filtered["Location"].isin(location_filter)]
    if head_filter:
        filtered = filtered[filtered["Head"].isin(head_filter)]
    if sub_filter:
        filtered = filtered[filtered["Sub Head"].isin(sub_filter)]
    if selected_status != "All":
        filtered = filtered[filtered["Feedback"].apply(classify_feedback) == selected_status]

    st.write(f"🔹 Showing {len(filtered)} record(s)")

    # ---------- AG GRID EDIT ----------
    st.markdown("### ✍️ Edit User Feedback/Remarks in Table")

    editable_filtered = filtered.copy()
    if not editable_filtered.empty:
        # Search box
        search_text = st.text_input("🔍 Search Deficiencies", "").strip().lower()
        if search_text:
            editable_filtered = editable_filtered[
                editable_filtered["Deficiencies Noted"].astype(str).str.lower().str.contains(search_text)
            ]

        if "_original_sheet_index" not in editable_filtered.columns:
            editable_filtered["_original_sheet_index"] = editable_filtered.index
        if "_sheet_row" not in editable_filtered.columns:
            editable_filtered["_sheet_row"] = editable_filtered.index + 2

        display_cols = [
            "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
            "Deficiencies Noted", "Inspection By", "Action By", "Feedback",
            "User Feedback/Remark"
        ]
        editable_df = editable_filtered.loc[:, display_cols].copy()

        if "Status" not in editable_df.columns:
            editable_df["Status"] = [
                get_status(r["Feedback"], r["User Feedback/Remark"]) 
                for _, r in editable_df.iterrows()
            ]
        editable_df["Status"] = editable_df["Status"].apply(color_text_status)

        editable_df["_original_sheet_index"] = editable_filtered["_original_sheet_index"].values
        editable_df["_sheet_row"] = editable_filtered["_sheet_row"].values

        # Remove duplicates
        editable_df = editable_df.loc[:, ~editable_df.columns.duplicated()]

        # Convert dates to string
        if "Date of Inspection" in editable_df.columns:
            editable_df["Date of Inspection"] = pd.to_datetime(
                editable_df["Date of Inspection"], errors="coerce"
            ).dt.strftime("%Y-%m-%d")

        # AG Grid config
        gb = GridOptionsBuilder.from_dataframe(editable_df)
        gb.configure_default_column(editable=False, wrapText=True, autoHeight=True, resizable=True)
        gb.configure_column("User Feedback/Remark", editable=True, wrapText=True, autoHeight=True)
        gb.configure_column("_original_sheet_index", hide=True)
        gb.configure_column("_sheet_row", hide=True)
        gb.configure_grid_options(singleClickEdit=True)

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
            height=500,
            allow_unsafe_jscode=True
        )

        edited_df = pd.DataFrame(grid_response["data"])

        # ---------- Buttons ----------
        c1, c2 = st.columns([1,1])
        if c1.button("✅ Submit Feedback"):
            update_feedback_column(edited_df)

        if c2.button("🔄 Refresh Data"):
            st.session_state.df = load_data_from_github()
            st.success("✅ Data refreshed!")

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

