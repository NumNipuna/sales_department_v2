import calendar
from datetime import datetime
import re

import gspread
import numpy as np
import pandas as pd
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials

def show():
    # ============================================================
    # 1. CONNECTION
    # ============================================================
    SCOPE = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    @st.cache_resource
    def get_client():
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            "service_account.json", SCOPE
        )
        return gspread.authorize(creds)

    @st.cache_resource
    def get_sheets():
        client = get_client()
        sheet2 = client.open("Sales data2")
        return sheet2

    # ============================================================
    # 2. LOAD RAW DATA (cached, refreshed based on ttl)
    # ============================================================
    @st.cache_data(ttl=600, show_spinner=False)
    def load_raw_data():
        sheet2 = get_sheets()

        master_ws = sheet2.worksheet("MasterData")
        targets_ws = sheet2.worksheet("MonthlyTargets")
        sales_ws = sheet2.worksheet("Sales_day_book")
        working_days_ws = sheet2.worksheet("Working_Days")

        master_df = pd.DataFrame(master_ws.get_all_records())
        targets_df = pd.DataFrame(targets_ws.get_all_records())
        sales_df = pd.DataFrame(sales_ws.get_all_records())
        working_days_df = pd.DataFrame(working_days_ws.get_all_records())

        return master_df, targets_df, sales_df, working_days_df

    def clear_raw_cache():
        load_raw_data.clear()

    # නම (First Name) වෙන්කරගැනීම සඳහා
    def _normalize_name(name):
        if not isinstance(name, str): 
            return ""
        parts = str(name).strip().split()
        return parts[0].lower() if parts else ""

    # ============================================================
    # 3. CALCULATION - MASTER TABLE
    # ============================================================
    def build_master_table(selected_date_str: str):
        master_df, targets_df, sales_df, working_days_df = load_raw_data()

        select_date_obj = pd.to_datetime(selected_date_str)
        selected_year = select_date_obj.year
        selected_month_name = select_date_obj.strftime("%B")
        selected_month_str = select_date_obj.strftime("%Y-%m")
        alt_month_str = select_date_obj.strftime("%Y-%b") # e.g., 2026-Jul

        # ---- Working Days ----
        working_days_filtered = working_days_df[
            (working_days_df["Year"].astype(str) == str(selected_year)) & 
            (working_days_df["Month"].astype(str).str.lower() == selected_month_name.lower())
        ]
        
        wd, worked_days = 0, 0
        if not working_days_filtered.empty:
            wd = pd.to_numeric(working_days_filtered["Working Days"].iloc[0], errors='coerce')
            worked_days = pd.to_numeric(working_days_filtered.get("Worked Days", pd.Series([0])).iloc[0], errors='coerce')
        
        wd = wd if pd.notna(wd) else 0
        worked_days = worked_days if pd.notna(worked_days) else 0

        # ---- Targets Filter ----
        targets_filtered = targets_df[
            (targets_df["Month"].astype(str) == selected_month_str) | 
            (targets_df["Month"].astype(str) == alt_month_str)
        ].copy()
        
        # Fallback to Month Name Match if above fails
        if targets_filtered.empty:
            targets_filtered = targets_df[targets_df["Month"].astype(str).str.lower() == selected_month_name.lower()].copy()

        # If no target data, fallback to master data
        if targets_filtered.empty:
            base_df = master_df[["No", "Manager", "Route", "Representative", "Status"]].copy()
            base_df["Target"] = 0
        else:
            base_df = targets_filtered[["No", "Manager", "Route", "Representative", "Status", "Target"]].copy()
            base_df["Target"] = pd.to_numeric(base_df["Target"], errors='coerce').fillna(0)

        base_df["rep_key"] = base_df["Representative"].apply(_normalize_name)

        # ---- Sales ----
        date_col = "New_date" if "New_date" in sales_df.columns else "new_date" if "new_date" in sales_df.columns else None

        if date_col and not sales_df.empty:
            sales_df["_parsed_date"] = pd.to_datetime(sales_df[date_col], errors="coerce")
            sales_month = sales_df[
                (sales_df["_parsed_date"].dt.year == selected_year) & 
                (sales_df["_parsed_date"].dt.month == select_date_obj.month)
            ].copy()
            
            sales_month["Qty"] = pd.to_numeric(sales_month["Qty"], errors='coerce').fillna(0)
            sales_month["rep_key"] = sales_month["Agent"].apply(_normalize_name)
            
            sales_grouped = sales_month.groupby("rep_key")["Qty"].sum().reset_index()
            sales_grouped.rename(columns={"Qty": "Sales"}, inplace=True)
        else:
            sales_grouped = pd.DataFrame(columns=["rep_key", "Sales"])
            
        # ---- Merge ----
        master_table = pd.merge(base_df, sales_grouped, on="rep_key", how="left")
        master_table["Sales"] = master_table["Sales"].fillna(0)
        
        # ---- Calculations ----
        master_table["Day Target"] = np.where(wd > 0, master_table["Target"] / wd, 0)
        master_table["Balance"] = master_table["Sales"] - master_table["Target"]
        master_table["Achievement %"] = np.where(master_table["Target"] > 0, (master_table["Sales"] / master_table["Target"]) * 100, 0)
        master_table["Day Target 2"] = master_table["Day Target"] * worked_days
        master_table["Day Achievement %"] = np.where(master_table["Day Target 2"] > 0, (master_table["Sales"] / master_table["Day Target 2"]) * 100, 0)
        
        cols_order = [
            "No", "Manager", "Route", "Representative", "Status", 
            "Day Target", "Sales", "Target", "Balance", "Achievement %", 
            "Day Target 2", "Day Achievement %"
        ]
        master_table = master_table[cols_order]
        master_table = master_table.replace([np.inf, -np.inf], 0)
        return master_table

    # ============================================================
    # 4. CALCULATION - WEEKLY BREAKDOWN
    # ============================================================
    def build_weekly_breakdown(selected_date_str: str) -> pd.DataFrame:
        master_df, targets_df, sales_df, working_days_df = load_raw_data()
        
        select_date_obj = pd.to_datetime(selected_date_str)
        selected_year, selected_month = select_date_obj.year, select_date_obj.month
        selected_month_name = select_date_obj.strftime("%B")
        selected_month_str = select_date_obj.strftime("%Y-%m")
        alt_month_str = select_date_obj.strftime("%Y-%b")

        # ---- Targets Filter ----
        targets_filtered = targets_df[
            (targets_df["Month"].astype(str) == selected_month_str) | 
            (targets_df["Month"].astype(str) == alt_month_str)
        ].copy()
        if targets_filtered.empty:
            targets_filtered = targets_df[targets_df["Month"].astype(str).str.lower() == selected_month_name.lower()].copy()
            
        if targets_filtered.empty:
            base_df = master_df[["No", "Manager", "Route", "Representative", "Status"]].copy()
            base_df["Target"] = 0
        else:
            base_df = targets_filtered[["No", "Manager", "Route", "Representative", "Status", "Target"]].copy()
            base_df["Target"] = pd.to_numeric(base_df["Target"], errors='coerce').fillna(0)

        base_df["rep_key"] = base_df["Representative"].apply(_normalize_name)
        
        # ---- Weeks Calculation (Monday Start) ----
        days_in_month = calendar.monthrange(selected_year, selected_month)[1]
        first_weekday = datetime(selected_year, selected_month, 1).weekday() # Mon=0, Sun=6
        total_weeks = ((days_in_month - 1 + first_weekday) // 7) + 1
        week_cols = [f"Week {i}" for i in range(1, total_weeks + 1)]
        
        # ---- Sales Day Book ----
        date_col = "New_date" if "New_date" in sales_df.columns else "new_date" if "new_date" in sales_df.columns else None
        if date_col and not sales_df.empty:
            sales_df["_parsed_date"] = pd.to_datetime(sales_df[date_col], errors="coerce")
            df = sales_df[
                (sales_df["_parsed_date"].dt.year == selected_year) & 
                (sales_df["_parsed_date"].dt.month == selected_month)
            ].copy()
            
            df["Qty"] = pd.to_numeric(df.get("Qty", 0), errors="coerce").fillna(0)
            df["rep_key"] = df["Agent"].apply(_normalize_name)
            
            # Map Date to Week Number
            df["day"] = df["_parsed_date"].dt.day
            df["week_num"] = ((df["day"] - 1 + first_weekday) // 7) + 1
            df["week_label"] = "Week " + df["week_num"].astype(int).astype(str)
            
            weekly_pivot = (
                df.groupby(["rep_key", "week_label"])["Qty"]
                .sum().reset_index()
                .pivot(index="rep_key", columns="week_label", values="Qty").reset_index()
            )
        else:
            weekly_pivot = pd.DataFrame(columns=["rep_key"] + week_cols)
            
        # ---- Merge & Finalize ----
        weekly_table = base_df.merge(weekly_pivot, on="rep_key", how="left")
        
        for c in week_cols:
            if c not in weekly_table.columns:
                weekly_table[c] = 0
        weekly_table[week_cols] = weekly_table[week_cols].fillna(0)
        weekly_table["Total Sales"] = weekly_table[week_cols].sum(axis=1)
        
        cols_order = ["No", "Manager", "Route", "Representative", "Status", "Target", "Total Sales"] + week_cols
        weekly_table = weekly_table[cols_order]
        
        return weekly_table

    # ============================================================
    # 5. STYLING, FORMATTING & PDF EXPORT
    # ============================================================
    def style_dataframe(df: pd.DataFrame, is_weekly=False):
        """Applies colors, % formatting, and returns a Pandas Styler"""
        df_display = df.copy()
        
        exclude_cols = ["No", "Manager", "Route", "Representative", "Status"]
        numeric_cols = [c for c in df_display.columns if c not in exclude_cols]
        pct_cols = [c for c in numeric_cols if "%" in c]

        def safe_formatter(val, is_pct=False):
            try:
                v = float(val)
                if pd.isna(v) or v == 0: return "-"
                return f"{v:,.2f}%" if is_pct else f"{v:,.2f}"
            except:
                return str(val)

        format_dict = {c: (lambda x, flag=(c in pct_cols): safe_formatter(x, flag)) for c in numeric_cols}
        styler = df_display.style.format(format_dict)

        # Conditional Colors for Target Achievements (Green, Yellow, Red)
        def color_achievement(val):
            try:
                v = float(val)
                if v >= 100: return 'background-color: #D4EDDA; color: #155724; font-weight: 700;'
                elif v >= 75: return 'background-color: #FFF3CD; color: #856404; font-weight: 700;'
                elif v > 0: return 'background-color: #F8D7DA; color: #721C24; font-weight: 700;'
            except: pass
            return ''

        if not is_weekly:
            if "Achievement %" in df_display.columns:
                styler = styler.map(color_achievement, subset=["Achievement %"])
            if "Day Achievement %" in df_display.columns:
                styler = styler.map(color_achievement, subset=["Day Achievement %"])
            
            grad_cols = [c for c in ["Sales", "Target", "Balance", "Day Target", "Day Target 2"] if c in df_display.columns]
            if grad_cols:
                try: styler = styler.background_gradient(subset=grad_cols, cmap="Blues")
                except: pass

        else:
            week_cols = [c for c in df_display.columns if "Week" in c]
            if week_cols:
                try: styler = styler.background_gradient(subset=week_cols, cmap="Blues", vmin=0)
                except: pass
            if "Total Sales" in df_display.columns:
                try: styler = styler.background_gradient(subset=["Total Sales"], cmap="PuBu", vmin=0)
                except: pass

        styler = styler.set_table_styles([
            {'selector': 'th', 'props': [('background-color', '#03045E'), ('color', 'white'), ('text-align', 'center'), ('padding', '10px'), ('border', '1px solid #ADE8F4')]},
            {'selector': 'td', 'props': [('border', '1px solid #ADE8F4'), ('padding', '8px')]},
            {'selector': 'tr:nth-child(even)', 'props': [('background-color', '#F8FDFF')]}
        ])
        
        try: styler = styler.hide(axis="index")
        except: pass
            
        return styler

    def generate_pdf_or_html(styler, title, date_str):
        import base64
        try: import pdfkit
        except ImportError: pdfkit = None
            
        try:
            with open("logo.png", "rb") as image_file:
                logo_base64 = base64.b64encode(image_file.read()).decode()
            img_tag = f'<img src="data:image/png;base64,{logo_base64}" style="height: 55px;" />'
        except: img_tag = ''

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title}</title>
            <style>
                @page {{ size: landscape; margin: 10mm; }}
                body {{ font-family: 'Helvetica', 'Arial', sans-serif; color: #03045E; margin: 0; }}
                table.header-table {{ width: 100%; background-color: #00245E; color: white; border-bottom: 5px solid #DE9C40; border-radius: 8px 8px 0 0; margin-bottom: 15px; border-collapse: collapse; }}
                table.header-table td {{ border: none; padding: 15px; background-color: #00245E; text-align: left; vertical-align: middle; }}
                .info-section {{ background-color: #CAF0F8; padding: 12px 20px; border-left: 6px solid #0096C7; margin-bottom: 20px; border-radius: 4px; }}
                .info-section h3 {{ margin: 0; color: #023E8A; font-size: 15px; }}
                table {{ width: 100%; border-collapse: collapse; font-size: 10px !important; }}
                th, td {{ border: 1px solid #ADE8F4; padding: 5px 6px; text-align: right; }}
                th {{ background-color: #03045E !important; color: white !important; text-align: center; font-weight: bold; }}
            </style>
        </head>
        <body>
            <table class="header-table">
                <tr>
                    <td style="width: 70px;">{img_tag}</td>
                    <td><h1 style="margin: 0; font-size: 26px; font-weight: 800; letter-spacing: 1px; color: white;">Imo Chicken & Agro (Pvt) Ltd</h1></td>
                </tr>
            </table>
            <div class="info-section">
                <table style="width: 100%; border: none;">
                    <tr>
                        <td style="text-align: left; border: none; padding: 0;"><h3>Department: Sales & Admin</h3></td>
                        <td style="text-align: center; border: none; padding: 0;"><h3>Report: {title}</h3></td>
                        <td style="text-align: right; border: none; padding: 0;"><h3>Date: {date_str}</h3></td>
                    </tr>
                </table>
            </div>
            <!-- Color Condition Legend for PDF -->
            <div style="display: flex; gap: 15px; margin-bottom: 10px; font-size: 11px; font-weight: bold; justify-content: flex-end; color: #03045E;">
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #D4EDDA; border: 1px solid #155724;"></div> Achieved &ge; 100%</div>
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #FFF3CD; border: 1px solid #856404;"></div> 75% - 99%</div>
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #F8D7DA; border: 1px solid #721C24;"></div> &lt; 75%</div>
            </div>
            {styler.to_html()}
        </body>
        </html>
        """
        
        options = {
            'page-size': 'A4',
            'orientation': 'Landscape',
            'margin-top': '0.3in',
            'margin-right': '0.3in',
            'margin-bottom': '0.3in',
            'margin-left': '0.3in',
            'encoding': "UTF-8",
            'enable-local-file-access': None
        }
        
        if pdfkit:
            try: return pdfkit.from_string(html_content, False, options=options), "pdf", "application/pdf"
            except Exception: pass 
        
        return html_content.encode('utf-8'), "html", "text/html"

    # ============================================================
    # 6. SAVE / LOAD helpers for Google Sheet tabs
    # ============================================================
    def _get_or_create_ws(sheet, tab_name, headers=None, rows=2000, cols=30):
        try:
            ws = sheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sheet.add_worksheet(title=tab_name, rows=rows, cols=cols)
            if headers:
                ws.append_row(headers)
        return ws

    def _save_df_to_tab(sheet, tab_name: str, df: pd.DataFrame, key_col_name: str, key_value: str):
        df = df.copy()
        df = df.replace([np.inf, -np.inf], 0).fillna(0)
        df.insert(0, key_col_name, key_value)

        headers = df.columns.tolist()
        ws = _get_or_create_ws(sheet, tab_name, headers=headers)

        all_values = ws.get_all_values()
        if not all_values:
            ws.append_row(headers)
            all_values = [headers]

        header = all_values[0]
        if key_col_name not in header:
            raise ValueError(f"The '{tab_name}' tab is missing a '{key_col_name}' column. Clear the tab and try again.")

        key_col_idx = header.index(key_col_name)
        rows_to_delete = []
        match_val = str(key_value).strip()
        
        for idx, row in enumerate(all_values, start=1):
            if idx > 1 and len(row) > key_col_idx:
                sheet_val = str(row[key_col_idx]).strip()
                if key_col_name == "Date":
                    try: sheet_val = pd.to_datetime(sheet_val).strftime("%Y-%m-%d")
                    except: pass
                elif key_col_name == "Month":
                    try: sheet_val = pd.to_datetime(sheet_val).strftime("%Y-%m")
                    except: pass
                if sheet_val == match_val:
                    rows_to_delete.append(idx)

        if rows_to_delete:
            rows_to_delete.sort()
            ranges = []
            start = prev = rows_to_delete[0]
            for r in rows_to_delete[1:]:
                if r == prev + 1: prev = r
                else:
                    ranges.append((start, prev))
                    start = prev = r
            ranges.append((start, prev))

            sheet_id = ws.id
            requests = []
            for (start_row, end_row) in reversed(ranges):
                requests.append({
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": start_row - 1,
                            "endIndex": end_row,
                        }
                    }
                })
            ws.spreadsheet.batch_update({"requests": requests})

        values = df.astype(str).values.tolist()
        ws.append_rows(values, value_input_option="USER_ENTERED")
        return True

    def _load_df_from_tab(sheet, tab_name: str, key_col_name: str, key_value: str):
        try: ws = sheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound: return None

        all_values = ws.get_all_values()
        if len(all_values) < 2: return None

        header = all_values[0]
        if key_col_name not in header: return None

        key_col_idx = header.index(key_col_name)
        match_val = str(key_value).strip()
        rows = []
        
        for row in all_values[1:]:
            if len(row) > key_col_idx:
                sheet_val = str(row[key_col_idx]).strip()
                if key_col_name == "Date":
                    try: sheet_val = pd.to_datetime(sheet_val).strftime("%Y-%m-%d")
                    except: pass
                elif key_col_name == "Month":
                    try: sheet_val = pd.to_datetime(sheet_val).strftime("%Y-%m")
                    except: pass
                
                if sheet_val == match_val: rows.append(row)
                    
        if not rows: return None

        fixed_rows = [row + [""] * (len(header) - len(row)) for row in rows]
        return pd.DataFrame(fixed_rows, columns=header)

    def save_report_to_sheet(sheet, df_report: pd.DataFrame, selected_date_str: str):
        return _save_df_to_tab(sheet, "Rep_Report", df_report, "Date", selected_date_str)

    def load_report_for_date(sheet, selected_date_str: str):
        return _load_df_from_tab(sheet, "Rep_Report", "Date", selected_date_str)

    def save_weekly_report_to_sheet(sheet, df_weekly: pd.DataFrame, month_str: str):
        return _save_df_to_tab(sheet, "Rep_Weekly", df_weekly, "Month", month_str)

    def load_weekly_report_for_month(sheet, month_str: str):
        return _load_df_from_tab(sheet, "Rep_Weekly", "Month", month_str)

    # ============================================================
    # 7. STREAMLIT UI
    # ============================================================
    st.set_page_config(page_title="Rep Sales Report", layout="wide")
    
        # Custom CSS for an Attractive UI
    st.markdown("""
        <style>
        :root {
            --c-900: #03045E;
            --c-800: #023E8A;
            --c-700: #0077B6;
            --c-600: #0096C7;
            --c-500: #00B4D8;
            --c-400: #48CAE4;
            --c-300: #90E0EF;
            --c-200: #ADE8F4;
            --c-100: #CAF0F8;
            --accent: #DE9C40;
        }

        /* App Background */
        .stApp {
            background: linear-gradient(135deg, var(--c-100) 0%, #FFFFFF 100%);
            color: var(--c-900);
        }

        /* Hide Header background */
        [data-testid="stHeader"] {
            background: transparent !important;
        }

        /* Hide Top Padding & Overflow fixes */
        .block-container {
            padding-top: 0rem !important;
            margin-top: -30px !important;
            padding-bottom: 1rem !important;
            max-width: 98% !important;
            overflow-x: hidden !important;
        }

        /* Keep Fullscreen button visible but contain inner Plotly tooltips */
        .stPlotlyChart {
            overflow: visible !important;
        }
        .stPlotlyChart > div {
            overflow: hidden !important; 
        }

        .stApp { background: linear-gradient(135deg, #CAF0F8 0%, #FFFFFF 100%); }
        h1, h2, h3 { color: var(--c-900) !important; }

        /* Light Blue Background */
        .stApp { background-color: #d5f3f9 !important; }
        /* Clean Header */
        [data-testid="stHeader"] { background: transparent !important; }
        
        /* Padding adjustments */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            max-width: 98% !important;
            overflow-x: hidden !important;
        }
        /* DataFrame Styling for sharp edges and shadows */
        [data-testid="stDataFrame"] {
            border: 1px solid #D1E5EB;
            border-radius: 8px;
            box-shadow: 0 4px 15px rgba(3, 4, 94, 0.08);
            background-color: white;
            padding: 5px;
        }
        
        /* Save and Calculate Buttons Styling */
        button[kind="primary"] {
            background-color: #03045E !important;
            color: white !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
        }
        button[kind="primary"]:hover {
            background-color: #0077B6 !important;
        }
        
        /* Secondary Buttons Styling */
        button[kind="secondary"] {
            background-color: #0096C7 !important;
            color: white !important;
            border-color: #0096C7 !important;
            border-radius: 6px !important;
        }
        button[kind="secondary"]:hover {
            background-color: #023E8A !important;
            border-color: #023E8A !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("Rep Sales & Targets Report")

    # 🚀 SINGLE ROW BUTTONS (vertical_alignment="bottom" aligns buttons with Date input)
    col1, col2, col3, col4, col5, col6 = st.columns([1.8, 1, 1, 1, 2,1], vertical_alignment="bottom")
    
    with col1:
        selected_date = st.date_input("Report Date", value=datetime.now())
    with col3:
        btn_refresh = st.button("🔄 Refresh Data")
    with col4:
        btn_calculate = st.button("▶ Calculate Report", type="primary")
    with col6:
        btn_save = st.button("💾 Save to Database")

    selected_date_str = selected_date.strftime("%Y-%m-%d")
    selected_month_str = pd.to_datetime(selected_date_str).strftime("%Y-%m")

    if btn_refresh:
        clear_raw_cache()
        st.success("Cache cleared. Please calculate again for the latest data.")

    if st.session_state.get("rep_loaded_for_date") != selected_date_str:
        sheet2 = get_sheets()
        existing_df = load_report_for_date(sheet2, selected_date_str)
        if existing_df is not None:
            st.session_state["rep_master_table"] = existing_df
            st.session_state["rep_report_date"] = selected_date_str
            st.session_state["rep_source"] = "saved"
        else:
            st.session_state.pop("rep_master_table", None)
            st.session_state.pop("rep_report_date", None)
            st.session_state["rep_source"] = None

        existing_weekly = load_weekly_report_for_month(sheet2, selected_month_str)
        if existing_weekly is not None:
            st.session_state["rep_weekly_table"] = existing_weekly
            st.session_state["rep_weekly_source"] = "saved"
        else:
            st.session_state.pop("rep_weekly_table", None)
            st.session_state["rep_weekly_source"] = None

        st.session_state["rep_loaded_for_date"] = selected_date_str

    if st.session_state.get("rep_source") == "saved":
        st.info(f"A previously generated report already exists for '{selected_date_str}'. Showing that.")

    if btn_calculate:
        with st.spinner("Calculating..."):
            try:
                master_table = build_master_table(selected_date_str)
                weekly_table = build_weekly_breakdown(selected_date_str)

                st.session_state["rep_master_table"] = master_table
                st.session_state["rep_report_date"] = selected_date_str
                st.session_state["rep_source"] = "calculated"

                st.session_state["rep_weekly_table"] = weekly_table
                st.session_state["rep_weekly_month"] = selected_month_str
                st.session_state["rep_weekly_source"] = "calculated"
            except Exception as e:
                st.error(f"Error: {e}")

    if btn_save:
        if "rep_master_table" in st.session_state and "rep_weekly_table" in st.session_state:
            with st.spinner("Saving to Google Sheet..."):
                try:
                    sheet2 = get_sheets() 
                    save_report_to_sheet(sheet2, st.session_state["rep_master_table"], st.session_state["rep_report_date"])
                    save_weekly_report_to_sheet(sheet2, st.session_state["rep_weekly_table"], st.session_state.get("rep_weekly_month", selected_month_str))
                    st.success(f"Report for '{st.session_state['rep_report_date']}' and its weekly breakdown were saved!")
                    st.session_state["rep_source"] = "saved"
                    st.session_state["rep_weekly_source"] = "saved"
                except Exception as e:
                    st.error(f"Failed to save: {e}")
        else:
            st.warning("⚠️ Please click 'Calculate Report' before saving.")

    if "rep_master_table" in st.session_state:
        st.divider()
        st.subheader(f"Report for {st.session_state['rep_report_date']}")
        
        # 🚀 Color Condition Legend for Web App
        st.markdown("""
        <div style="display: flex; gap: 15px; margin-bottom: 10px; font-size: 14px; font-weight: 600; color: #03045E;">
            <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 15px; height: 15px; background-color: #D4EDDA; border: 1px solid #155724; border-radius: 3px;"></div> Achieved &ge; 100%</div>
            <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 15px; height: 15px; background-color: #FFF3CD; border: 1px solid #856404; border-radius: 3px;"></div> 75% - 99%</div>
            <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 15px; height: 15px; background-color: #F8D7DA; border: 1px solid #721C24; border-radius: 3px;"></div> &lt; 75%</div>
        </div>
        """, unsafe_allow_html=True)

        styled_master = style_dataframe(st.session_state["rep_master_table"], is_weekly=False)
        st.dataframe(styled_master, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            csv_bytes = st.session_state["rep_master_table"].to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="⬇ Download Report CSV",
                data=csv_bytes,
                file_name=f"rep_sales_report_{st.session_state['rep_report_date']}.csv",
                mime="text/csv",
            )
        with c2:
            export_data, ext, mime = generate_pdf_or_html(styled_master, "Representative Sales & Targets", st.session_state['rep_report_date'])
            st.download_button(
                label=f"🖨️ Download as PDF/HTML",
                data=export_data,
                file_name=f"rep_sales_report_{st.session_state['rep_report_date']}.{ext}",
                mime=mime,
            )

        st.divider()
        st.subheader(f"Weekly Breakdown — {pd.to_datetime(st.session_state['rep_report_date']).strftime('%B %Y')}")

        if "rep_weekly_table" not in st.session_state:
            with st.spinner("Building weekly breakdown..."):
                try:
                    st.session_state["rep_weekly_table"] = build_weekly_breakdown(st.session_state["rep_report_date"])
                    st.session_state["rep_weekly_month"] = selected_month_str
                    st.session_state["rep_weekly_source"] = "calculated"
                except Exception as e:
                    st.error(f"Could not build weekly breakdown: {e}")

        if "rep_weekly_table" in st.session_state:
            styled_weekly = style_dataframe(st.session_state["rep_weekly_table"], is_weekly=True)
            st.dataframe(styled_weekly, use_container_width=True)

            wc1, wc2 = st.columns(2)
            with wc1:
                weekly_csv_bytes = st.session_state["rep_weekly_table"].to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="⬇ Download Weekly Breakdown CSV",
                    data=weekly_csv_bytes,
                    file_name=f"rep_weekly_breakdown_{selected_month_str}.csv",
                    mime="text/csv",
                )
            with wc2:
                w_export_data, w_ext, w_mime = generate_pdf_or_html(styled_weekly, "Weekly Sales Breakdown", selected_month_str)
                st.download_button(
                    label=f"🖨️ Download Weekly as PDF/HTML",
                    data=w_export_data,
                    file_name=f"rep_weekly_breakdown_{selected_month_str}.{w_ext}",
                    mime=w_mime,
                )

if __name__ == "__main__":
    show()