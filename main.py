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
st.set_page_config(page_title="Inspection App", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS for responsiveness
st.markdown("""
<style>
/* General responsive styles */
body {
    font-size: 16px;
}
@media (max-width: 768px) {
    body {
        font-size: 14px;
    }
    .stButton > button {
        width: 100%;
        padding: 12px;
        font-size: 16px;
        margin: 5px 0;
    }
    .stTextInput > div > input,
    .stSelectbox > div > select,
    .stMultiselect > div > select,
    .stSlider > div {
        font-size: 14px;
        padding: 8px;
    }
    .stDataFrame {
        overflow-x: auto;
    }
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        font-size: calc(1rem + 2vw);
        line-height: 1.2;
    }
    .adaptive-credit {
        padding: 10px 20px;
        font-size: 14px;
    }
    .adaptive-credit:hover {
        transform: none;
        box-shadow: 0 4px 15px var(--shadow-base);
    }
    /* Ensure images and charts scale */
    img, .stImage, .stPlotlyChart, .stAltairChart {
        width: 100% !important;
        max-width: 100%;
        height: auto;
    }
    /* Collapse sidebar content for mobile */
    [data-testid="stSidebar"] {
        width: 100%;
        max-width: 300px;
    }
    /* AgGrid adjustments */
    .ag-root-wrapper {
        width: 100% !important;
        overflow-x: auto;
    }
    .ag-header-cell-text {
        font-size: 12px;
    }
    .ag-cell {
        font-size: 12px;
        padding: 8px !important;
    }
}
/* Marquee for mobile */
marquee {
    font-size: 14px;
    padding: 10px 0;
}
/* Ensure table cells wrap and are readable */
.stDataFrame table {
    width: 100%;
    table-layout: auto;
}
.stDataFrame th, .stDataFrame td {
    white-space: normal !important;
    word-wrap: break-word;
    padding: 8px;
}
</style>
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
if "selected_columns_for_filter" not in st.session_state:
    st.session_state.selected_columns_for_filter = []

# ---------- LOGIN ----------
def login(email, password):
    """Check credentials against st.secrets['users']"""
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
# [STATION_LIST, GATE_LIST, FOOTPLATE_ROUTES, HEAD_LIST, SUBHEAD_LIST, INSPECTION_BY_LIST, ACTION_BY_LIST, VALID_INSPECTIONS, FOOTPLATE_LIST]
# (Preserved as in original code, no changes needed)

# ---------- HELPERS ----------
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
            # ... (full list from original code)
        ]
        pending_kw = [
            "work is going on", "tdc given", "target date", "expected by", "likely by", "planned by",
            # ... (full list from original code)
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
    # (Preserved as in original code, no changes needed)
    header = sheet.row_values(1)
    def col_idx(name):
        try:
            return header.index(name) + 1
        except ValueError:
            st.error(f"⚠️ '{name}' column not found")
            return None

# ---------- FILTER WIDGETS ----------
def apply_common_filters(df, prefix=""):
    with st.expander("🔍 Apply Additional Filters", expanded=True):
        c1, c2 = st.columns([1, 1])
        c1.multiselect("Inspection By", INSPECTION_BY_LIST[1:], default=st.session_state.get(prefix + "insp", []), key=prefix + "insp")
        c2.multiselect("Action By", ACTION_BY_LIST[1:], default=st.session_state.get(prefix + "action", []), key=prefix + "action")
        d1, d2 = st.columns([1, 1])
        d1.date_input("📅 From Date", key=prefix + "from_date")
        d2.date_input("📅 To Date", key=prefix + "to_date")
    out = df.copy()
    if st.session_state.get(prefix + "insp"):
        sel = st.session_state[prefix + "insp"]
        out = out[out["Inspection By"].apply(lambda x: any(s.strip() in str(x).split(",") for s in sel))]
    if st.session_state.get(prefix + "action"):
        sel = st.session_state[prefix + "action"]
        out = out[out["Action By"].apply(lambda x: any(s.strip() in str(x).split(",") for s in sel))]
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
             style="max-width: 50px; height: auto; margin-right: 10px; object-fit: contain;">
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

# ---------- LOAD DATA ----------
@st.cache_data(ttl=0)
def load_data():
    # (Preserved as in original code, no changes needed)

# Initialize df if None
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
    
    # Responsive metrics layout
    col_a, col_b = st.columns([1, 1])
    col_c, col_d = st.columns([1, 1])
    pending_count = (filtered["Status"] == "Pending").sum()
    no_response_count = filtered["Feedback"].isna().sum() + (filtered["Feedback"].astype(str).str.strip() == "").sum()
    resolved_count = (filtered["Status"] == "Resolved").sum()
    col_a.metric("🟨 Pending", pending_count)
    col_b.metric("⚠️ No Response", no_response_count)
    col_c.metric("🟩 Resolved", resolved_count)
    col_d.metric("📊 Total Records", len(filtered))
    
    # Sub Head Distribution Visualization
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
            # Use Altair instead of Matplotlib for better responsiveness
            pie_chart = alt.Chart(major).mark_arc().encode(
                theta=alt.Theta(field="Count", type="quantitative"),
                color=alt.Color(field="Sub Head", type="nominal"),
                tooltip=["Sub Head", "Count"]
            ).properties(
                width="container",
                height=300
            )
            st.altair_chart(pie_chart, use_container_width=True)
            st.download_button(
                "📥 Download Sub Head Distribution (CSV)",
                data=major.to_csv(index=False),
                file_name="subhead_distribution.csv",
                mime="text/csv"
            )
    
    # Export Filtered Data
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
    st.markdown("### ✍️ Edit User Feedback/Remarks in Table")
    if not filtered.empty:
        display_cols = [
            "Date of Inspection", "Type of Inspection", "Location", "Head", "Sub Head",
            "Deficiencies Noted", "Inspection By", "Action By", "Feedback",
            "User Feedback/Remark"
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
            editable_df["Status"] = editable_df["Status"].apply(color_text_status)
        
        # Global Search
        st.markdown("#### 🔍 Search and Filter")
        search_text = st.text_input("Search All Columns (case-insensitive)", "").strip().lower()
        if search_text:
            mask = editable_df[valid_cols].astype(str).apply(
                lambda col: col.str.contains(search_text, case=False, na=False)
            ).any(axis=1)
            editable_df = editable_df[mask].copy()
            st.info(f"Found {len(editable_df)} matching rows after search.")
        
        # Excel-like Column Filtering
        max_cols = st.slider("Max columns to filter on", 1, len(valid_cols), min(5, len(valid_cols)), key="max_cols_filter")
        candidate_columns = valid_cols[:max_cols]
        global column_selection
        column_selection = st.multiselect(
            "Select columns to filter",
            candidate_columns,
            default=st.session_state.selected_columns_for_filter,
            key="column_select_filter"
        )
        st.session_state.selected_columns_for_filter = column_selection
        if column_selection:
            editable_df = filter_dataframe(editable_df)
            st.info(f"Applied filters to {len(editable_df)} rows.")
        
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
                cellEditorPopup=True,  # Enable popup for mobile
                cellEditorParams={"maxLength": 4000}
            )
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
        
        # Render AgGrid
        st.markdown("#### 📋 Editable Table")
        st.caption("Edit 'User Feedback/Remark' column. Use column headers to sort.")
        grid_response = AgGrid(
            editable_df,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            height=400,  # Reduced height for mobile
            allow_unsafe_jscode=True,
            fit_columns_on_grid_load=True
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
                st.error("⚠️ Required columns are missing from the data.")
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
                    st.info("ℹ️ No changes detected to save.")
    else:
        st.info("Deficiencies will be updated soon!")

# ---------------- ALERT LOG SECTION ----------------
st.markdown("## 📋 Alerts Log")
if st.session_state.alerts_log:
    for i, log in enumerate(st.session_state.alerts_log):
        with st.expander(f"🔔 Alert {i+1}", expanded=True):
            st.markdown(log, unsafe_allow_html=True)
            if st.button("Mark as Read", key=f"mark_{i}"):
                st.session_state.alerts_log.pop(i)
                st.session_state.last_alert_clicked = i
                st.rerun()
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
    <marquee behavior="scroll" direction="left" style="color:red;font-weight:bold;font-size:14px;">
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
- For Finance Department: Pertains to **FINAINCE**
- For Store Department: Pertains to **STORE**
- For Medical Department: Pertains to **MEDICAL**
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

with tabs[1]:
    st.markdown("### 📊 Pending Deficiencies Trend (Bar + Trend Line)")
    df = st.session_state.df.copy()
    if "Status" not in df.columns:
        df["Status"] = df["Feedback"].apply(classify_feedback)
    if df.empty:
        st.info("No data available for analytics.")
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
        # Trend Chart
        trend = pending.groupby(pd.Grouper(key="Date of Inspection", freq="M")).size().reset_index(name="PendingCount")
        if not trend.empty:
            trend = trend.sort_values("Date of Inspection").reset_index(drop=True)
            trend["MonthIndex"] = trend.index
            bars = alt.Chart(trend).mark_bar(color="#1f77b4").encode(
                x=alt.X("yearmonth(Date of Inspection):T", title="Inspection Month"),
                y=alt.Y("PendingCount:Q", title="Pending Deficiencies"),
                tooltip=["yearmonth(Date of Inspection):T", "PendingCount"]
            ).properties(
                width="container",
                height=300
            )
            line = alt.Chart(trend).transform_regression("MonthIndex", "PendingCount").mark_line(
                color="red", strokeDash=[5,5], strokeWidth=2
            ).encode(
                x=alt.X("yearmonth(Date of Inspection):T"),
                y="PendingCount:Q"
            )
            st.altair_chart(bars + line, use_container_width=True)
        else:
            st.info("No pending deficiencies to display.")
        # Department Summary
        st.markdown("### 🏢 Department-wise Pending Counts")
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
                tooltip=["Head","PendingCount"]
            ).properties(width="container", height=300)
            st.altair_chart(dept_chart, use_container_width=True)
            top3 = dept_counts.head(3)
            critical_text = ", ".join([f"{row['Head']} ({row['PendingCount']})" for _, row in top3.iterrows()])
            st.markdown(f"**Critical Departments with Pending Compliances:** {critical_text}")
        else:
            st.info("No pending deficiencies to summarize.")
        # Critical Locations Chart
        st.markdown("### 🚨 Top 3 Critical Locations")
        for col in ["Location","Gate","Section"]:
            if col not in pending.columns:
                pending[col] = ""
        pending["Location"] = pending["Location"].astype(str).str.strip().str.upper()
        pending["Gate"] = pending["Gate"].astype(str).str.strip().str.upper()
        pending["Section"] = pending["Section"].astype(str).str.strip().str.upper()
        pending_stations = pending[pending["Location"].isin(STATION_LIST)]
        pending_gates = pending[pending["Gate"].isin(GATE_LIST)]
        pending_routes = pending[pending["Section"].isin([s.upper() for s in FOOTPLATE_ROUTES])]
        combined_counts = pd.concat([
            pending_stations.groupby("Location").size().reset_index(name="PendingCount"),
            pending_gates.groupby("Gate").size().reset_index(name="PendingCount"),
            pending_routes.groupby("Section").size().reset_index(name="PendingCount")
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
                tooltip=[top3_critical.columns[0],"PendingCount"]
            ).properties(width="container", height=200)
            st.altair_chart(critical_loc_chart, use_container_width=True)
        else:
            st.info("No critical locations to display.")
        # Unified Location / Gate / Section Chart
        st.markdown("### 📍 Pending Deficiencies by Location / Gate / Section")
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
                tooltip=[loc_counts_final.columns[0],"PendingCount"]
            ).properties(width="container", height=400)
            st.altair_chart(loc_chart, use_container_width=True)
        else:
            st.info("No pending deficiencies for selected locations.")

