import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode
from io import BytesIO
import os

LOCAL_FILE = "responses.xlsx"
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from matplotlib import pyplot as plt
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode
from openpyxl.styles import Alignment, Font, Border, Side
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
# ----------------- Helper Functions -----------------

def load_data():
    if os.path.exists(LOCAL_FILE):
        df = pd.read_excel(LOCAL_FILE)
    else:
        # create empty dataframe with required columns
        df = pd.DataFrame(columns=[
            "Date of Inspection", "Type of Inspection", "Location",
            "Head", "Sub Head", "Deficiencies Noted",
            "Inspection By", "Action By", "Feedback",
            "User Feedback/Remark"
        ])
    # Ensure required columns
    required_cols = [
        "Date of Inspection", "Type of Inspection", "Location",
        "Head", "Sub Head", "Deficiencies Noted",
        "Inspection By", "Action By", "Feedback",
        "User Feedback/Remark"
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""
    df["Date of Inspection"] = pd.to_datetime(df["Date of Inspection"], errors="coerce")
    df["Location"] = df["Location"].astype(str).str.strip().str.upper()

    # Add helper columns for AG-Grid
    if "_sheet_row" not in df.columns:
        df["_sheet_row"] = df.index + 2
    if "_original_sheet_index" not in df.columns:
        df["_original_sheet_index"] = df.index
    df["Feedback"] = df["Feedback"].fillna("").astype(str)
    df["User Feedback/Remark"] = df["User Feedback/Remark"].fillna("").astype(str)
    return df

def save_to_local_excel(df):
    df.to_excel(LOCAL_FILE, index=False)

def classify_feedback(feedback):
    val = "" if pd.isna(feedback) else str(feedback)
    return "Pending" if val.strip() == "" else "Resolved"

def get_status(feedback, remark):
    # Use Feedback column only for status
    return classify_feedback(feedback)

def color_text_status(status):
    return "🔴 Pending" if status == "Pending" else ("🟢 Resolved" if status == "Resolved" else status)

# ----------------- Load Data -----------------
if "df" not in st.session_state:
    st.session_state.df = load_data()
df_main = st.session_state.df.copy()

st.markdown("### ✍️ Edit User Feedback / Remarks")

editable_df = df_main.copy()

# Ensure text columns are strings
editable_df["User Feedback/Remark"] = editable_df["User Feedback/Remark"].fillna("").astype(str)
editable_df["Feedback"] = editable_df["Feedback"].fillna("").astype(str)

# Add Status column
editable_df["Status"] = editable_df.apply(lambda r: color_text_status(get_status(r["Feedback"], r["User Feedback/Remark"])), axis=1)

# ----------------- AG-Grid Configuration -----------------
gb = GridOptionsBuilder.from_dataframe(editable_df)
gb.configure_default_column(editable=False, wrapText=True, autoHeight=True, resizable=True)

# Make only User Feedback/Remark editable and force as text
gb.configure_column(
    "User Feedback/Remark",
    editable=True,
    wrapText=True,
    autoHeight=True,
    cellEditor="agTextCellEditor",
    cellEditorPopup=False,
    cellEditorParams={"maxLength": 4000},
)

# Hide helper ID columns
gb.configure_column("_original_sheet_index", hide=True)
gb.configure_column("_sheet_row", hide=True)

# Auto-size all columns
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

# ----------------- Submit Button -----------------
if st.button("✅ Submit Feedback"):
    if "_original_sheet_index" not in edited_df.columns:
        st.error("⚠️ Cannot find original row index. Please refresh.")
    else:
        changes = 0
        df_main = st.session_state.df.copy()

        # Only update rows where user typed a remark
        edited_rows = edited_df[edited_df["User Feedback/Remark"].astype(str).str.strip() != ""]
        for _, row in edited_rows.iterrows():
            idx = int(row["_original_sheet_index"])
            val = row["User Feedback/Remark"]
            new_remark = "" if pd.isna(val) else str(val).strip()
            if new_remark:
                df_main.at[idx, "Feedback"] = new_remark
                df_main.at[idx, "User Feedback/Remark"] = ""
                changes += 1

        if changes > 0:
            save_to_local_excel(df_main)
            st.session_state.df = df_main
            st.success(f"✅ Updated {changes} feedback row(s).")
            st.rerun()
        else:
            st.info("ℹ️ No new feedback to submit.")



    if c2.button("🔄 Refresh Data"):
        st.session_state.df = load_data()
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


















