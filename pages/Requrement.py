import calendar
from datetime import datetime
import re

import gspread
import numpy as np
import pandas as pd
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials
import base64

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
        sheet1 = client.open("Sales data")
        sheet2 = client.open("Sales data2")
        return sheet1, sheet2

    # ============================================================
    # 2. LOAD RAW DATA (cached, refreshed based on ttl)
    # ============================================================
    @st.cache_data(ttl=600, show_spinner=False)
    def load_raw_data():
        sheet1, sheet2 = get_sheets()

        working_days_ws = sheet1.worksheet("Working_Days")
        sales_day_book_ws = sheet2.worksheet("Sales_day_book") 
        inventory_ws = sheet1.worksheet("Inventory")
        items_master_ws = sheet1.worksheet("Items_Master")
        forecast_ws = sheet1.worksheet("Forecast")

        working_days_df = pd.DataFrame(working_days_ws.get_all_records())
        sales_day_book_df = pd.DataFrame(sales_day_book_ws.get_all_records())
        inventory_df = pd.DataFrame(inventory_ws.get_all_records())
        items_master_df = pd.DataFrame(items_master_ws.get_all_records())
        forecast_df = pd.DataFrame(forecast_ws.get_all_records())

        return working_days_df, sales_day_book_df, inventory_df, items_master_df, forecast_df

    def clear_raw_cache():
        load_raw_data.clear()

    # ============================================================
    # 3. CALCULATION
    # ============================================================
    def safe_float(val):
        """Helper function to safely clean and convert any value to a float using Regex."""
        if pd.isna(val) or val is None: 
            return 0.0
        if isinstance(val, (int, float)): 
            return float(val)
        
        val_str = str(val).strip()
        if val_str == "-" or val_str == "":
            return 0.0
            
        cleaned = re.sub(r'[^\d.-]', '', val_str)
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def build_master_table(selected_date_str: str):
        """selected_date_str: 'YYYY-MM-DD' format"""

        working_days, sales_day_book, inventory, items_master, forecast = load_raw_data()

        select_date_obj = pd.to_datetime(selected_date_str)
        selected_year = select_date_obj.year
        selected_month = select_date_obj.strftime("%B")

        # ---- filters ----
        working_days_filtered = working_days[
            (working_days["Year"].astype(str) == str(selected_year))
            & (working_days["Month"].astype(str) == str(selected_month))
        ]
        
        working_days_value = 1.0
        if not working_days_filtered.empty:
            working_days_value = safe_float(working_days_filtered["Working Days"].iloc[0])
            if working_days_value == 0: working_days_value = 1.0

        date_col = "New_date" if "New_date" in sales_day_book.columns else "new_date" if "new_date" in sales_day_book.columns else "Date"
        if date_col in sales_day_book.columns:
            sales_day_book["Parsed_Date_Obj"] = pd.to_datetime(sales_day_book[date_col], errors="coerce")
            
            daily_sale_filtered = sales_day_book[
                (sales_day_book["Parsed_Date_Obj"].dt.year == selected_year) &
                (sales_day_book["Parsed_Date_Obj"].dt.month == select_date_obj.month) &
                (sales_day_book["Parsed_Date_Obj"] <= select_date_obj)
            ].copy()
        else:
            daily_sale_filtered = pd.DataFrame()

        inventory_filtered = inventory[inventory["Date"].astype(str) == selected_date_str].copy()
        if "Available Qty" in inventory_filtered.columns:
            inventory_filtered["Available Qty"] = inventory_filtered["Available Qty"].apply(safe_float)

        forecast_filtered = forecast[
            (forecast["Year"].astype(str) == str(selected_year)) & (forecast["Month"].astype(str) == str(selected_month))
        ].copy()
        if "Forecast Qty" in forecast_filtered.columns:
            forecast_filtered["Forecast Qty"] = forecast_filtered["Forecast Qty"].apply(safe_float)

        # ---- sale qty per product ----
        if not daily_sale_filtered.empty and "Item" in daily_sale_filtered.columns:
            daily_sale_filtered["Qty"] = daily_sale_filtered.get("Qty", 0).apply(safe_float)
            sale_qty_grouped = daily_sale_filtered.groupby("Item")["Qty"].sum().reset_index()
            sale_qty = pd.merge(items_master, sale_qty_grouped, left_on="Item Name", right_on="Item", how="left")
            sale_qty["Qty"] = sale_qty["Qty"].fillna(0)
            sale_qty = sale_qty.drop(columns=["Item"], errors="ignore")
        else:
            sale_qty = items_master.copy()
            sale_qty["Qty"] = 0.0

        # ---- forecast achievement % ----
        forecast_achievement = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]],
            on="Product Code",
            how="left",
        )
        forecast_achievement["forecast_achivement %"] = np.where(
            forecast_achievement["Forecast Qty"] > 0,
            (forecast_achievement["Qty"] / forecast_achievement["Forecast Qty"]) * 100,
            0
        )
        forecast_achievement = forecast_achievement.drop(
            columns=["Item Name", "Qty", "Forecast Qty"]
        )

        # ---- balance ----
        balance = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]],
            on="Product Code",
            how="left",
        )
        balance["Balance"] = balance["Qty"] - balance["Forecast Qty"]
        balance = balance.drop(columns=["Item Name", "Qty", "Forecast Qty"])

        # 🚀 FIX: Calculate average per week strictly based on the Selected Date (not current computer date)
        dates_up_to_selected = select_date_obj.day
        denom = (dates_up_to_selected - 1) if dates_up_to_selected > 1 else 1

        avg_sale_per_week = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]],
            on="Product Code",
            how="left",
        )
        avg_sale_per_week["avg sale per week"] = (avg_sale_per_week["Qty"] / denom) * 6
        avg_sale_per_week = avg_sale_per_week.drop(
            columns=["Item Name", "Qty", "Forecast Qty"]
        )

        # ---- available balance ----
        availabel_balance = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]],
            on="Product Code",
            how="left",
        )
        inv_avail = inventory_filtered.set_index("Item Code")["Available Qty"] \
            if not inventory_filtered.empty else pd.Series(dtype=float)
        avg_week_series = avg_sale_per_week.set_index("Product Code")["avg sale per week"]

        availabel_balance = availabel_balance.set_index("Product Code")
        availabel_balance["avilable balance"] = (
            inv_avail.reindex(availabel_balance.index).fillna(0)
            - avg_week_series.reindex(availabel_balance.index).fillna(0)
        )
        availabel_balance = availabel_balance.reset_index().drop(
            columns=["Item Name", "Qty", "Forecast Qty"]
        )

        # ---- day target ----
        day_target = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]],
            on="Product Code",
            how="left",
        )
        day_target["Day Target"] = day_target["Forecast Qty"] / working_days_value
        day_target = day_target.drop(columns=["Item Name", "Qty", "Forecast Qty"])

        # ---- average sales ----
        days_in_month = calendar.monthrange(select_date_obj.year, select_date_obj.month)[1]
        average_sales = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]],
            on="Product Code",
            how="left",
        )
        average_sales["Average Sales"] = average_sales["Qty"] / days_in_month
        average_sales = average_sales.drop(columns=["Item Name", "Qty", "Forecast Qty"])

        # ---- average daily target % ----
        avg_daily_target = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]],
            on="Product Code",
            how="left",
        )
        avg_sales_series = average_sales.set_index("Product Code")["Average Sales"]
        day_target_series = day_target.set_index("Product Code")["Day Target"]
        avg_daily_target = avg_daily_target.set_index("Product Code")
        
        avg_daily_target["Average Daily Target"] = np.where(
            day_target_series.reindex(avg_daily_target.index).fillna(0) > 0,
            (avg_sales_series.reindex(avg_daily_target.index).fillna(0)
            / day_target_series.reindex(avg_daily_target.index).fillna(1.0)) * 100,
            0,
        )
        avg_daily_target = avg_daily_target.reset_index().drop(
            columns=["Item Name", "Qty", "Forecast Qty"]
        )

        inventory_filtered_clean = inventory_filtered.drop(
            columns=[c for c in ["Date", "Product Name"] if c in inventory_filtered.columns]
        )

        # ---- master table ----
        master_table = (
            sale_qty
            .merge(forecast_filtered[["Product Code", "Forecast Qty"]], on="Product Code", how="left")
            .merge(forecast_achievement, on="Product Code", how="left")
            .merge(balance, on="Product Code", how="left")
            .merge(
                inventory_filtered_clean[["Item Code", "Available Qty"]]
                if not inventory_filtered_clean.empty else pd.DataFrame(columns=["Item Code", "Available Qty"]),
                left_on="Product Code", right_on="Item Code", how="left",
            )
            .drop(columns=["Item Code"], errors="ignore")
            .merge(avg_sale_per_week, on="Product Code", how="left")
            .merge(availabel_balance, on="Product Code", how="left")
            .merge(day_target, on="Product Code", how="left")
            .merge(average_sales, on="Product Code", how="left")
            .merge(avg_daily_target, on="Product Code", how="left")
            .fillna(0)
        )

        master_table = master_table.replace([np.inf, -np.inf], 0)
        return master_table

    def build_weekly_breakdown(selected_date_str: str, items_master: pd.DataFrame) -> pd.DataFrame:
        _, sales_day_book, _, _, _ = load_raw_data()

        select_date_obj = pd.to_datetime(selected_date_str)
        year, month = select_date_obj.year, select_date_obj.month
        
        # 🚀 FIX: Aligning Weeks dynamically based on the actual Calendar
        days_in_month = calendar.monthrange(year, month)[1]
        first_weekday = datetime(year, month, 1).weekday() # Mon=0, Sun=6
        total_weeks = ((days_in_month - 1 + first_weekday) // 7) + 1
        week_cols = [f"Week {i}" for i in range(1, total_weeks + 1)]

        df = sales_day_book.copy()
        date_col = "New_date" if "New_date" in df.columns else "new_date" if "new_date" in df.columns else "Date"

        if not df.empty and date_col in df.columns:
            df["Date_parsed"] = pd.to_datetime(df[date_col], errors="coerce")
            df = df[
                (df["Date_parsed"].dt.year == year) & 
                (df["Date_parsed"].dt.month == month) &
                (df["Date_parsed"] <= select_date_obj)
            ].copy()

        if df.empty or "Item" not in df.columns:
            weekly_pivot = pd.DataFrame(columns=["Item Name"] + week_cols)
        else:
            df["Qty"] = df.get("Qty", 0).apply(safe_float)
                
            # 🚀 FIX: Apply the Calendar-based calculation logic to avoid mapping into wrong weeks
            df["day"] = df["Date_parsed"].dt.day
            df["week_num"] = ((df["day"] - 1 + first_weekday) // 7) + 1
            df["week_label"] = "Week " + df["week_num"].astype(int).astype(str)

            weekly_pivot = (
                df.groupby(["Item", "week_label"])["Qty"]
                .sum()
                .reset_index()
                .pivot(index="Item", columns="week_label", values="Qty")
                .reset_index()
            )
            weekly_pivot = weekly_pivot.rename(columns={"Item": "Item Name"})

        id_cols = [c for c in ["Product Code", "Item Name"] if c in items_master.columns]
        weekly_table = items_master[id_cols].merge(weekly_pivot, on="Item Name", how="left")

        for c in week_cols:
            if c not in weekly_table.columns:
                weekly_table[c] = 0
        weekly_table[week_cols] = weekly_table[week_cols].fillna(0)

        weekly_table["Total"] = weekly_table[week_cols].sum(axis=1)
        weekly_table = weekly_table[id_cols + week_cols + ["Total"]]
        return weekly_table

    def style_dataframe(df: pd.DataFrame, is_weekly=False):
        """Applies formatting and Conditional Colors for multiple targets safely"""
        df_display = df.copy()
        
        def safe_formatter(val, is_pct):
            if pd.isna(val) or val == "": return "-"
            try:
                num = float(val)
                return f"{num:,.2f}%" if is_pct else f"{num:,.2f}"
            except:
                return str(val)
                
        format_dict = {}
        for c in df_display.columns:
            if c not in ["Product Code", "Item Code", "Item Name", "Category", "Brand", "Item", "No"]:
                is_pct_col = "%" in c or ("Target" in c and "Daily" in c)
                format_dict[c] = lambda x, p=is_pct_col: safe_formatter(x, p)
                
        styler = df_display.style.format(format_dict)
        
        def safe_get_float(val):
            try:
                if pd.isna(val) or val == "": return None
                if isinstance(val, str):
                    val = val.replace(',', '').replace('%', '').strip()
                return float(val)
            except: return None

        if not is_weekly:
            def highlight_rows(row):
                styles = [''] * len(row)
                
                # Condition for 'forecast_achivement %'
                if 'forecast_achivement %' in row.index:
                    ach_idx = row.index.get_loc('forecast_achivement %')
                    ach_val = safe_get_float(row['forecast_achivement %'])
                    if ach_val is not None:
                        if ach_val >= 100: styles[ach_idx] = 'background-color: #D4EDDA; color: #155724; font-weight: bold;'
                        elif ach_val >= 75: styles[ach_idx] = 'background-color: #FFF3CD; color: #856404; font-weight: bold;'
                        elif ach_val >= 50: styles[ach_idx] = 'background-color: #FFE8CC; color: #A04000; font-weight: bold;'
                        elif ach_val >= 0: styles[ach_idx] = 'background-color: #F8D7DA; color: #721C24; font-weight: bold;'
                        else: styles[ach_idx] = 'background-color: #F5C6CB; color: #721C24; font-weight: bold;'
                
                # Condition for 'Average Daily Target'
                if 'Average Daily Target' in row.index:
                    adt_idx = row.index.get_loc('Average Daily Target')
                    adt_val = safe_get_float(row['Average Daily Target'])
                    if adt_val is not None:
                        if adt_val >= 100: styles[adt_idx] = 'background-color: #D4EDDA; color: #155724; font-weight: bold;'
                        elif adt_val >= 75: styles[adt_idx] = 'background-color: #FFF3CD; color: #856404; font-weight: bold;'
                        elif adt_val >= 50: styles[adt_idx] = 'background-color: #FFE8CC; color: #A04000; font-weight: bold;'
                        elif adt_val >= 0: styles[adt_idx] = 'background-color: #F8D7DA; color: #721C24; font-weight: bold;'
                        else: styles[adt_idx] = 'background-color: #F5C6CB; color: #721C24; font-weight: bold;'
                
                # Condition for 'Balance'
                if 'Balance' in row.index:
                    bal_idx = row.index.get_loc('Balance')
                    bal_val = safe_get_float(row['Balance'])
                    if bal_val is not None:
                        if bal_val >= 0: styles[bal_idx] = 'background-color: #E2F0CB; color: #2D5A27; font-weight: bold;'
                        else: styles[bal_idx] = 'background-color: #FFD1D1; color: #900000; font-weight: bold;'
                
                # Condition for 'Qty' (Sale) based on 'Forecast Qty'
                if 'Qty' in row.index and 'Forecast Qty' in row.index:
                    qty_idx = row.index.get_loc('Qty')
                    qty_val = safe_get_float(row['Qty'])
                    fq_val = safe_get_float(row['Forecast Qty'])
                    if qty_val is not None and fq_val is not None and fq_val > 0:
                        pct = (qty_val / fq_val) * 100
                        if pct >= 100: styles[qty_idx] = 'background-color: #D4EDDA; color: #155724; font-weight: bold;'
                        elif pct >= 75: styles[qty_idx] = 'background-color: #FFF3CD; color: #856404; font-weight: bold;'
                        elif pct >= 50: styles[qty_idx] = 'background-color: #FFE8CC; color: #A04000; font-weight: bold;'
                        elif pct >= 0: styles[qty_idx] = 'background-color: #F8D7DA; color: #721C24; font-weight: bold;'
                        else: styles[qty_idx] = 'background-color: #F5C6CB; color: #721C24; font-weight: bold;'
                return styles
            
            styler = styler.apply(highlight_rows, axis=1)

        # Base Table CSS Styling
        styler = styler.set_table_styles([
            {'selector': 'th', 'props': [('background-color', '#03045E'), ('color', 'white'), ('text-align', 'center'), ('padding', '10px'), ('border', '1px solid #ADE8F4'), ('white-space', 'nowrap')]},
            {'selector': 'td', 'props': [('border', '1px solid #ADE8F4'), ('padding', '8px'), ('text-align', 'right'), ('white-space', 'nowrap')]},
            {'selector': 'tr:nth-child(even)', 'props': [('background-color', '#F8FDFF')]}
        ])
        
        try: styler = styler.hide(axis="index")
        except: pass
            
        return styler

    def generate_pdf_or_html(styler, title, date_str):
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
                @page {{ size: A4 landscape; margin: 10mm; }}
                body {{ font-family: 'Helvetica', 'Arial', sans-serif; color: #03045E; margin: 0; background-color: #ffffff; }}
                table.header-table {{ width: 100%; background-color: #00245E; color: white; border-bottom: 5px solid #DE9C40; border-radius: 8px 8px 0 0; margin-bottom: 15px; border-collapse: collapse; }}
                table.header-table td {{ border: none; padding: 15px; background-color: #00245E; text-align: left; vertical-align: middle; }}
                .info-section {{ background-color: #CAF0F8; padding: 12px 20px; border-left: 6px solid #0096C7; margin-bottom: 15px; border-radius: 4px; }}
                .info-section h3 {{ margin: 0; color: #023E8A; font-size: 14px; }}
                table {{ width: 100%; border-collapse: collapse; font-size: 11px !important; table-layout: auto; }}
                th, td {{ border: 1px solid #ADE8F4; padding: 6px 8px; text-align: right; white-space: nowrap; }}
                th {{ background-color: #03045E !important; color: white !important; text-align: center; font-weight: bold; }}
            </style>
        </head>
        <body>
            <table class="header-table">
                <tr>
                    <td style="width: 70px;">{img_tag}</td>
                    <td><h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: 1px; color: white;">Imo Chicken & Agro (Pvt) Ltd</h1></td>
                </tr>
            </table>
            <div class="info-section">
                <table style="width: 100%; border: none;">
                    <tr>
                        <td style="text-align: left; border: none; padding: 0;"><h3>Department: Sales & Marketing</h3></td>
                        <td style="text-align: center; border: none; padding: 0;"><h3>Report: {title}</h3></td>
                        <td style="text-align: right; border: none; padding: 0;"><h3>Date: {date_str}</h3></td>
                    </tr>
                </table>
            </div>
            
            <div style="display: flex; gap: 15px; margin-bottom: 10px; font-size: 11px; font-weight: bold; justify-content: flex-end; color: #03045E;">
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #D4EDDA; border: 1px solid #155724;"></div> Target &ge; 100%</div>
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #FFF3CD; border: 1px solid #856404;"></div> 75% - 99%</div>
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #FFE8CC; border: 1px solid #A04000;"></div> 50% - 74%</div>
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #F8D7DA; border: 1px solid #721C24;"></div> &lt; 50%</div>
                <div style="display: flex; align-items: center; gap: 5px; margin-left:10px;"><div style="width: 12px; height: 12px; background-color: #E2F0CB; border: 1px solid #2D5A27;"></div> Balance &ge; 0</div>
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #FFD1D1; border: 1px solid #900000;"></div> Balance &lt; 0</div>
            </div>
            
            {styler.to_html()}
        </body>
        </html>
        """
        
        options = {
            'page-size': 'A4', 'orientation': 'Landscape', 'margin-top': '0.3in', 'margin-right': '0.3in',
            'margin-bottom': '0.3in', 'margin-left': '0.3in', 'encoding': "UTF-8", 'enable-local-file-access': None,
            'zoom': 1.0, 'dpi': 300, 'no-outline': None
        }
        
        if pdfkit:
            try:
                pdf_bytes = pdfkit.from_string(html_content, False, options=options)
                return pdf_bytes, "pdf", "application/pdf"
            except Exception: pass 
        
        return html_content.encode('utf-8'), "html", "text/html"

    # ============================================================
    # 4. SAVE / LOAD helpers
    # ============================================================
    def _get_or_create_ws(sheet, tab_name, headers=None, rows=2000, cols=30):
        try:
            ws = sheet.worksheet(tab_name)
            if headers:
                existing_header = ws.row_values(1)
                if existing_header != headers:
                    ws.update("A1", [headers])
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
            raise ValueError(f"The '{tab_name}' tab is missing a '{key_col_name}' column.")

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
                        "range": { "sheetId": sheet_id, "dimension": "ROWS", "startIndex": start_row - 1, "endIndex": end_row }
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
        return _save_df_to_tab(sheet, "Req_Report", df_report, "Date", selected_date_str)

    def load_report_for_date(sheet, selected_date_str: str):
        return _load_df_from_tab(sheet, "Req_Report", "Date", selected_date_str)

    def save_weekly_report_to_sheet(sheet, df_weekly: pd.DataFrame, month_str: str):
        return _save_df_to_tab(sheet, "Req_Weekly", df_weekly, "Month", month_str)

    def load_weekly_report_for_month(sheet, month_str: str):
        return _load_df_from_tab(sheet, "Req_Weekly", "Month", month_str)

    def enforce_numeric_types(df: pd.DataFrame) -> pd.DataFrame:
        text_cols = ["Date", "Month", "Product Code", "Item Code", "Item Name", "Item", "No", "Category", "Brand"]
        for col in df.columns:
            if col not in text_cols:
                df[col] = df[col].astype(str).str.replace(',', '', regex=False).str.replace('%', '', regex=False).str.strip()
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        return df

    # ============================================================
    # 5. STREAMLIT UI
    # ============================================================
    st.set_page_config(page_title="Requirement Report", layout="wide")
    
    # Custom CSS for an Attractive UI
    st.markdown("""
        <style>
        :root {
            --c-900: #03045E; --c-800: #023E8A; --c-700: #0077B6;
            --c-600: #0096C7; --c-500: #00B4D8; --c-400: #48CAE4;
            --c-300: #90E0EF; --c-200: #ADE8F4; --c-100: #CAF0F8;
            --accent: #DE9C40;
        }

        .stApp { background: linear-gradient(135deg, var(--c-100) 0%, #FFFFFF 100%); color: var(--c-900); }
        [data-testid="stHeader"] { background: transparent !important; }
        .block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; max-width: 98% !important; overflow-x: hidden !important; }
        
        h1, h2, h3 { color: var(--c-900) !important; }

        [data-testid="stDataFrame"] {
            border: 1px solid #D1E5EB; border-radius: 8px; box-shadow: 0 4px 15px rgba(3, 4, 94, 0.08); background-color: white; padding: 5px;
        }
        
        button[kind="primary"] { background-color: #03045E !important; color: white !important; border-radius: 6px !important; font-weight: 600 !important; }
        button[kind="primary"]:hover { background-color: #0077B6 !important; }
        
        button[kind="secondary"] { background-color: #0096C7 !important; color: white !important; border-color: #0096C7 !important; border-radius: 6px !important; }
        button[kind="secondary"]:hover { background-color: #023E8A !important; border-color: #023E8A !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title("Production Requirement Report")
    
    # 🚀 SINGLE ROW LAYOUT FOR ALL BUTTONS
    col1, col2, col3, col4 = st.columns([1.5, 1, 1.5, 2], vertical_alignment="bottom")
    
    with col1:
        selected_date = st.date_input("Report Date", value=datetime.now())
    with col2:
        btn_refresh = st.button("🔄 Refresh Data")
    with col3:
        btn_calculate = st.button("▶ Calculate Report", type="primary")
    with col4:
        btn_save = st.button("💾 Save to Database")
        
    selected_date_str = selected_date.strftime("%Y-%m-%d")
    selected_month_str = pd.to_datetime(selected_date_str).strftime("%Y-%m")
    
    if btn_refresh:
        clear_raw_cache()
        st.success("Cache cleared. Please calculate again for the latest data.")
        
    if btn_save:
        if "req_master_table" in st.session_state and "req_weekly_table" in st.session_state:
            with st.spinner("Saving to Google Sheet..."):
                try:
                    sheet1, _ = get_sheets()
                    save_report_to_sheet(sheet1, st.session_state["req_master_table"], st.session_state["req_report_date"])
                    save_weekly_report_to_sheet(sheet1, st.session_state["req_weekly_table"], st.session_state.get("req_weekly_month", selected_month_str))
                    st.success(f"Report for '{st.session_state['req_report_date']}' successfully saved!")
                    st.session_state["req_source"] = "saved"
                    st.session_state["req_weekly_source"] = "saved"
                except Exception as e:
                    st.error(f"Failed to save: {e}")
        else:
            st.error("⚠️ Please click 'Calculate Report' before saving.")

    if st.session_state.get("req_loaded_for_date") != selected_date_str:
        sheet1, _ = get_sheets()
        existing_df = load_report_for_date(sheet1, selected_date_str)
        if existing_df is not None:
            existing_df = enforce_numeric_types(existing_df)
            st.session_state["req_master_table"] = existing_df
            st.session_state["req_report_date"] = selected_date_str
            st.session_state["req_source"] = "saved"
        else:
            st.session_state.pop("req_master_table", None)
            st.session_state.pop("req_report_date", None)
            st.session_state["req_source"] = None
            
        existing_weekly = load_weekly_report_for_month(sheet1, selected_month_str)
        if existing_weekly is not None:
            existing_weekly = enforce_numeric_types(existing_weekly)
            st.session_state["req_weekly_table"] = existing_weekly
            st.session_state["req_weekly_source"] = "saved"
        else:
            st.session_state.pop("req_weekly_table", None)
            st.session_state["req_weekly_source"] = None
            
        st.session_state["req_loaded_for_date"] = selected_date_str

    if st.session_state.get("req_source") == "saved":
        st.info(f"A previously generated report already exists for '{selected_date_str}'. Showing that.")

    if btn_calculate:
        with st.spinner("Calculating..."):
            try:
                master_table = build_master_table(selected_date_str)
                _, _, _, items_master_raw, _ = load_raw_data()
                weekly_table = build_weekly_breakdown(selected_date_str, items_master_raw)
                
                st.session_state["req_master_table"] = master_table
                st.session_state["req_report_date"] = selected_date_str
                st.session_state["req_source"] = "calculated"
                st.session_state["req_weekly_table"] = weekly_table
                st.session_state["req_weekly_month"] = selected_month_str
                st.session_state["req_weekly_source"] = "calculated"
            except Exception as e:
                st.error(f"Error: {e}")

    if "req_master_table" in st.session_state:
        st.divider()
        st.subheader(f"Report for {st.session_state['req_report_date']}")
        
        # 🚀 Expanded Color Condition Legend Display
        st.markdown("""
        <div style="display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 12px; font-size: 14px; font-weight: 600; color: #03045E; background: white; padding: 10px; border-radius: 6px; border: 1px solid #D1E5EB;">
            <span style="color: #666;">Targets:</span>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #D4EDDA; border: 1px solid #155724; border-radius: 4px;"></div> &ge; 100%</div>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #FFF3CD; border: 1px solid #856404; border-radius: 4px;"></div> 75% - 99%</div>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #FFE8CC; border: 1px solid #A04000; border-radius: 4px;"></div> 50% - 74%</div>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #F8D7DA; border: 1px solid #721C24; border-radius: 4px;"></div> &lt; 50%</div>
            <span style="color: #ccc; margin: 0 10px;">|</span>
            <span style="color: #666;">Balance:</span>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #E2F0CB; border: 1px solid #2D5A27; border-radius: 4px;"></div> &ge; 0 (Good)</div>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #FFD1D1; border: 1px solid #900000; border-radius: 4px;"></div> &lt; 0 (Short)</div>
        </div>
        """, unsafe_allow_html=True)
        
        styled_master = style_dataframe(st.session_state["req_master_table"], is_weekly=False)
        st.dataframe(styled_master, use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1:
            csv_bytes = st.session_state["req_master_table"].to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="⬇ Download Report CSV",
                data=csv_bytes,
                file_name=f"requirement_report_{st.session_state['req_report_date']}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with c2:
            export_data, ext, mime = generate_pdf_or_html(styled_master, "Production Requirement", st.session_state['req_report_date'])
            st.download_button(
                label=f"🖨️ Download as PDF/HTML",
                data=export_data,
                file_name=f"requirement_report_{st.session_state['req_report_date']}.{ext}",
                mime=mime,
                use_container_width=True,
            )

        st.divider()
        st.subheader(f"Weekly Breakdown — {pd.to_datetime(st.session_state['req_report_date']).strftime('%B %Y')}")
        
        if "req_weekly_table" not in st.session_state:
            with st.spinner("Building weekly breakdown..."):
                try:
                    _, _, _, items_master_raw, _ = load_raw_data()
                    st.session_state["req_weekly_table"] = build_weekly_breakdown(
                        st.session_state["req_report_date"], items_master_raw
                    )
                    st.session_state["req_weekly_month"] = selected_month_str
                    st.session_state["req_weekly_source"] = "calculated"
                except Exception as e:
                    st.error(f"Could not build weekly breakdown: {e}")
                    
        if "req_weekly_table" in st.session_state:
            styled_weekly = style_dataframe(st.session_state["req_weekly_table"], is_weekly=True)
            st.dataframe(styled_weekly, use_container_width=True)
            
            wc1, wc2 = st.columns(2)
            with wc1:
                weekly_csv_bytes = st.session_state["req_weekly_table"].to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="⬇ Download Weekly Breakdown CSV",
                    data=weekly_csv_bytes,
                    file_name=f"req_weekly_breakdown_{selected_month_str}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with wc2:
                w_export_data, w_ext, w_mime = generate_pdf_or_html(styled_weekly, "Weekly Breakdown Report", selected_month_str)
                st.download_button(
                    label=f"🖨️ Download Weekly as PDF/HTML",
                    data=w_export_data,
                    file_name=f"req_weekly_breakdown_{selected_month_str}.{w_ext}",
                    mime=w_mime,
                    use_container_width=True,
                )