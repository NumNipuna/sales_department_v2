import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder
from datetime import datetime
import numpy as np
import json
import time

try:
    from util import connect_to_sheets, connect_to_sheets2
except ImportError:
    st.error("Error: Could not import connection functions from util.py")

PRODUCT_GROUPS = {
    "Chicken": [
        "01CW01", "01CW02", "01CW03", "01CW05", "01CW06",
        "02CW01", "02CW03", "02CW04", "02CW05", "02CW09",
        "03CW01", "03CW03", "03CW04", "03CW05", "03CW08"
    ],
    "Potion": [
        "04CP01", "04CP02", "04CP03", "04CP04", "04CP05", "04CP06", "04CP07",
        "04CP08", "04CP09", "04CP10", "04CP11", "04CP12", "04CP13", "04CP14",
        "04CP16", "04CP17", "04CP19", "04CP20", "04CP23", "04CP24", "04CP26",
        "04CP28", "04CP29", "04CP30", "04CP31", "04CP32", "04CP33", "04CP34",
        "04CP37", "04CP40", "04CP41", "05CM01", "05CM02"
    ],
    "Easy": [
        "05CM03", "06CE01", "06CE02", "06CE03", "06CE05"
    ]
}

def get_category(item_code):
    if pd.isna(item_code):
        return "Other"
    item_str = str(item_code).strip().upper()
    for cat, codes in PRODUCT_GROUPS.items():
        if item_str in codes:
            return cat
    return "Other"

# Custom CSS for Color Palette, Layout fixes & Chart Animations
def apply_custom_css():
    st.markdown("""
        <style>
        /* Color Palette Variables */
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

        /* Page spacing and overflow fixes */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            max-width: 98% !important;
            overflow-x: hidden !important;
            min-height: 85vh !important;
        }

        div[data-testid="stDateInput"] label p {
            font-family: 'Arial', sans-serif !important;
            font-weight: 600 !important;
            font-size: 16px !important;
            color: var(--c-900) !important;
        }
        div[data-testid="stDateInput"] div[data-baseweb="input"] {
            border: 2px solid var(--c-600) !important;
            border-radius: 8px !important;
            background-color: #F8FDFF !important;
            transition: all 0.3s ease-in-out;
            padding-left: 5px;
        }
        div[data-testid="stDateInput"] div[data-baseweb="input"]:focus-within {
            border: 2px solid var(--c-900) !important;
            box-shadow: 0 0 8px rgba(3, 4, 94, 0.4) !important;
        }

        /* 🚀 MASTER FIX: Complete Scrollbar Removal for Charts */
        [data-testid="stPlotlyChart"] {
            box-sizing: border-box !important;
            overflow: hidden !important;
        }
        [data-testid="stPlotlyChart"] > div, 
        [data-testid="stPlotlyChart"] iframe {
            overflow: hidden !important;
            box-sizing: border-box !important;
        }
        /* Completely hide scrollbars in all inner elements */
        [data-testid="stPlotlyChart"] *::-webkit-scrollbar {
            display: none !important;
            width: 0 !important;
            height: 0 !important;
        }
        [data-testid="stPlotlyChart"] * {
            scrollbar-width: none !important;
            -ms-overflow-style: none !important;
        }

        /* 🚀 Text Colors (Scoped to main container to avoid breaking sidebar) */
        .block-container h1, .block-container h2, .block-container h3, .block-container h4, .block-container p, .block-container label {
            color: var(--c-900) !important;
        }

        /* Chart & Table Card Styling */
        [data-testid="stPlotlyChart"], .stDataFrame {
            background-color: rgba(255, 255, 255, 0.85);
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(2, 62, 138, 0.08);
            border: 1px solid var(--c-200);
            padding: 10px;
            margin-bottom: 1rem;
            animation: fadeSlideUp 0.8s ease-out forwards;
            backdrop-filter: blur(10px);
        }

        /* KPI Cards */
        .kpi-container {
            display: flex;
            gap: 1.5rem;
            margin-bottom: 1.5rem;
        }
        .kpi-card {
            flex: 1;
            background: rgba(255, 255, 255, 0.9);
            padding: 1.5rem;
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(3, 4, 94, 0.06);
            border-top: 5px solid var(--c-700);
            border-left: 1px solid var(--c-200);
            border-right: 1px solid var(--c-200);
            border-bottom: 1px solid var(--c-200);
            position: relative;
            overflow: hidden;
        }
        .kpi-card::before {
            content: "";
            position: absolute;
            top: -50px;
            right: -50px;
            width: 100px;
            height: 100px;
            background: var(--c-100);
            border-radius: 50%;
            opacity: 0.5;
            z-index: 0;
        }
        .kpi-title {
            color: var(--c-800);
            font-size: 0.95rem;
            font-weight: 700;
            text-transform: uppercase;
            margin-bottom: 0.5rem;
            letter-spacing: 0.5px;
            z-index: 1;
            position: relative;
        }
        .kpi-value {
            color: var(--c-900);
            font-size: 2.5rem;
            font-weight: 800;
            z-index: 1;
            position: relative;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.05);
        }
        .kpi-sub {
            font-size: 0.85rem;
            color: var(--c-600);
            margin-top: 0.25rem;
            font-weight: 600;
            z-index: 1;
            position: relative;
        }
        </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=300, show_spinner=False)
def load_dashboard_data():
    try:
        sh1 = connect_to_sheets()
        sh2 = connect_to_sheets2()
        
        req_ws = sh1.worksheet("Req_Report")
        req_df = pd.DataFrame(req_ws.get_all_records())
        
        rep_ws = sh2.worksheet("Rep_Report")
        rep_df = pd.DataFrame(rep_ws.get_all_records())
        
        req_df.columns = req_df.columns.str.strip()
        rep_df.columns = rep_df.columns.str.strip()
        
        return req_df, rep_df
    except Exception as e:
        st.error(f"Error loading report data: {e}")
        return pd.DataFrame(), pd.DataFrame()

# Common Layout function to disable zoom/pan scrolling & set styling
def apply_plotly_layout(fig, title=""):
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=18, color="#03045E"), x=0.02, y=0.95),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_family="'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
        font_color="#023E8A",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        dragmode=False, # Disables mouse drag to zoom/pan
        transition=dict(duration=700, easing="cubic-in-out"),
        margin=dict(t=60, b=40, l=15, r=15) # 🚀 Increased bottom margin to prevent scrollbars inside iframe
    )
    # fixedrange=True disables the internal scrolling of axes
    fig.update_xaxes(showgrid=False, linecolor="#ADE8F4", tickfont=dict(color="#023E8A"), fixedrange=True)
    fig.update_yaxes(showgrid=True, gridcolor="#CAF0F8", linecolor="#ADE8F4", tickfont=dict(color="#023E8A"), fixedrange=True)
    return fig

# 🚀 Plotly Modebar Configuration (Turned off completely to fix Scrollbars)
plotly_config = {
    'displayModeBar': False, 
    'displaylogo': False,
    'staticPlot': False
}

def render_kpi_cards(total_sale, total_target, forecast_ach, active_reps):
    """Animate the KPI values from zero to their final values."""
    placeholder = st.empty()
    steps = 20

    for step in range(steps + 1):
        progress = step / steps
        placeholder.markdown(f"""
            <div class="kpi-container">
                <div class="kpi-card" style="border-top-color: #03045E;">
                    <div class="kpi-title">Total Sales (Up to Today)</div>
                    <div class="kpi-value"><span>{total_sale * progress:,.0f}</span></div>
                    <div class="kpi-sub" style="color: #0096C7;">Total Volume Sold</div>
                </div>
                <div class="kpi-card" style="border-top-color: #023E8A;">
                    <div class="kpi-title">Total Target</div>
                    <div class="kpi-value"><span>{total_target * progress:,.0f}</span></div>
                    <div class="kpi-sub" style="color: #0077B6;">Monthly Quota</div>
                </div>
                <div class="kpi-card" style="border-top-color: #0077B6;">
                    <div class="kpi-title">Forecast Achievement</div>
                    <div class="kpi-value"><span>{forecast_ach * progress:,.1f}%</span></div>
                    <div class="kpi-sub" style="color: #0096C7;">Vs Projected Forecast</div>
                </div>
                <div class="kpi-card" style="border-top-color: #0096C7;">
                    <div class="kpi-title">Active Reps</div>
                    <div class="kpi-value"><span>{active_reps * progress:,.0f}</span></div>
                    <div class="kpi-sub" style="color: #0077B6;">Engaged in Sales</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        if step < steps:
            time.sleep(0.025)

def render_animated_chart(fig, height, animation_kind="default"):
    """Render a Plotly chart without scrollbars and animate its first appearance."""
    def as_list(values):
        """Convert Plotly/Pandas/Numpy values to a list without boolean-testing arrays."""
        return [] if values is None else list(values)

    target = json.loads(fig.to_json())

    # Plotly can serialize Pandas/Numpy values in a typed internal format.
    # Convert animated axes to ordinary lists so Python and JavaScript can slice them safely.
    for index, trace in enumerate(target.get("data", [])):
        source_trace = fig.data[index]
        for axis in ("x", "y", "values"):
            source_values = getattr(source_trace, axis, None)
            if source_values is not None:
                trace[axis] = as_list(source_values)

    initial = json.loads(json.dumps(target, cls=PlotlyJSONEncoder))

    for index, trace in enumerate(initial.get("data", [])):
        source_trace = fig.data[index]
        trace_type = trace.get("type")
        if trace_type == "indicator":
            trace["value"] = 0
        elif trace_type == "pie":
            values = as_list(getattr(source_trace, "values", None))
            trace["values"] = [1] * len(values)
        elif trace_type == "bar":
            value_axis = "x" if trace.get("orientation") == "h" else "y"
            values = as_list(getattr(source_trace, value_axis, None))
            trace[value_axis] = [0] * len(values)
        elif trace_type == "scatter":
            if animation_kind == "line":
                for axis in ("x", "y"):
                    values = as_list(getattr(source_trace, axis, None))
                    if values:
                        trace[axis] = values[:1]
            elif "y" in trace:
                values = as_list(getattr(source_trace, "y", None))
                trace["y"] = [0] * len(values)

    chart_html = f"""
    <style>
        html, body {{ margin: 0; padding: 0; overflow: hidden; background: transparent; }}
        #animated-chart {{ width: 100%; height: {height}px; overflow: hidden; }}
    </style>
    <div id="animated-chart"></div>
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <script>
        const chart = document.getElementById("animated-chart");
        const initial = {json.dumps(initial, cls=PlotlyJSONEncoder)};
        const target = {json.dumps(target, cls=PlotlyJSONEncoder)};
        const config = {json.dumps(plotly_config)};

        Plotly.newPlot(chart, initial.data, initial.layout, config).then(() => {{
            if ("{animation_kind}" === "line") {{
                const lineTrace = target.data.find(trace => trace.type === "scatter" && (trace.mode || "").includes("lines"));
                const totalPoints = lineTrace && lineTrace.x ? lineTrace.x.length : 1;
                const steps = Math.min(24, Math.max(1, totalPoints));
                let currentStep = 0;
                const timer = setInterval(() => {{
                    currentStep += 1;
                    const progress = currentStep / steps;
                    const pointCount = Math.max(1, Math.ceil(totalPoints * progress));
                    const frameData = target.data.map(trace => {{
                        const nextTrace = JSON.parse(JSON.stringify(trace));
                        if (nextTrace.type === "scatter" && (nextTrace.mode || "").includes("lines")) {{
                            nextTrace.x = nextTrace.x.slice(0, pointCount);
                            nextTrace.y = nextTrace.y.slice(0, pointCount);
                        }} else if (nextTrace.type === "bar") {{
                            const axis = nextTrace.orientation === "h" ? "x" : "y";
                            nextTrace[axis] = nextTrace[axis].map(value => value * progress);
                        }}
                        return nextTrace;
                    }});
                    Plotly.react(chart, frameData, target.layout, config);
                    if (currentStep >= steps) {{
                        clearInterval(timer);
                        Plotly.react(chart, target.data, target.layout, config);
                    }}
                }}, 45);
            }} else {{
                Plotly.animate(chart, {{data: target.data, layout: target.layout}}, {{
                    transition: {{duration: 1100, easing: "cubic-in-out"}},
                    frame: {{duration: 1100, redraw: true}},
                    mode: "afterall"
                }});
            }}
        }});
    </script>
    """
    components.html(chart_html, height=height, scrolling=False)

# STREAMING_CHUNK:Rendering Dashboard...
def show():
    apply_custom_css()
    
    st.markdown("<h2 style='text-align: center; color: #03045E; font-weight: 800;'>📊 Monthly Overview Dashboard</h2>", unsafe_allow_html=True)
    
    # Date Pickers
    today = datetime.now()
    first_day = today.replace(day=1)
    
    col1, col2, _ = st.columns([2, 2, 3], vertical_alignment="bottom")
    with col1:
        start_date = st.date_input("Start Date:", value=first_day)
    with col2:
        end_date = st.date_input("End Date (Snapshot):", value=today)

    st.divider()

    if start_date > end_date:
        st.error("Start Date cannot be after End Date.")
        return

    with st.spinner("Processing Analytics..."):
        req_df_all, rep_df_all = load_dashboard_data()

        if req_df_all.empty or rep_df_all.empty:
            st.warning("⚠️ Data missing. Please ensure Requirement and Rep Target reports are generated.")
            return

        req_df_all["Date"] = pd.to_datetime(req_df_all["Date"], errors="coerce")
        rep_df_all["Date"] = pd.to_datetime(rep_df_all["Date"], errors="coerce")
        
        valid_dates = rep_df_all[rep_df_all["Date"].dt.date <= end_date]["Date"]
        
        if valid_dates.empty:
            st.warning(f"No reports found on or before {end_date.strftime('%Y-%m-%d')}.")
            return
            
        latest_date = valid_dates.max()
        if latest_date.date() != end_date:
            st.info(f"💡 Showing latest snapshot for **{latest_date.strftime('%Y-%m-%d')}**")
            
        req_df = req_df_all[req_df_all["Date"] == latest_date].copy()
        rep_df = rep_df_all[rep_df_all["Date"] == latest_date].copy()

        # 🚀 CLEAN NUMERIC DATA & FIX "-" ERROR
        # 'Sale' -> 'Qty', 'Forecast' -> 'Forecast Qty' (Sheet Column Names)
        for col in ["Qty", "Forecast Qty"]:
            if col in req_df.columns:
                # Replace '-' and empty spaces with '0' to avoid KeyError/ValueError safely
                req_df[col] = req_df[col].astype(str).replace(r'^\s*-\s*$', '0', regex=True)
                req_df[col] = pd.to_numeric(req_df[col], errors='coerce').fillna(0)
                
        for col in ["Sales", "Target"]:
            if col in rep_df.columns:
                rep_df[col] = rep_df[col].astype(str).replace(r'^\s*-\s*$', '0', regex=True)
                rep_df[col] = pd.to_numeric(rep_df[col], errors='coerce').fillna(0)

        # Calculate KPIs
        total_sale = rep_df["Sales"].sum() if "Sales" in rep_df.columns else 0
        total_target = rep_df["Target"].sum() if "Target" in rep_df.columns else 0
        overall_ach = (total_sale / total_target * 100) if total_target > 0 else 0
        
        # Fixed specific columns to look for Qty and Forecast Qty
        total_forecast = req_df["Forecast Qty"].sum() if "Forecast Qty" in req_df.columns else 0
        total_req_sale = req_df["Qty"].sum() if "Qty" in req_df.columns else 0
        forecast_ach = (total_req_sale / total_forecast * 100) if total_forecast > 0 else 0
        
        active_reps = len(rep_df[rep_df["Sales"] > 0]) if "Sales" in rep_df.columns else 0

        render_kpi_cards(total_sale, total_target, forecast_ach, active_reps)

        # STREAMING_CHUNK:Rendering Charts...
        # ================== ROW 1 ==================
        r1c1, r1c2 = st.columns([1, 1])

        with r1c1:
            # Overall Target Achievement Gauge
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=overall_ach,
                number={'suffix': "%", 'font': {'size': 45, 'color': '#03045E', 'weight': 'bold'}},
                delta={'reference': 100, 'position': "top", 'font': {'color': "#0077B6"}},
                gauge={
                    'axis': {'range': [None, max(100, overall_ach)], 'visible': False},
                    'bar': {'color': "#0096C7", 'thickness': 0.8},
                    'bgcolor': "#CAF0F8",
                    'shape': "angular",
                }
            ))
            fig_gauge = apply_plotly_layout(fig_gauge, "Overall Target Achievement")
            fig_gauge.update_layout(height=320, margin=dict(t=60, b=10, l=20, r=20))
            st.plotly_chart(fig_gauge, use_container_width=True, config=plotly_config)

        with r1c2:
            # Sales by Product Group (Pie)
            if "Product Code" in req_df.columns and "Qty" in req_df.columns:
                req_df["Category"] = req_df["Product Code"].apply(get_category)
                cat_sales = req_df.groupby("Category")["Qty"].sum().reset_index()
                
                # Dark Blue to Light Blue palette
                color_map = {"Chicken": "#03045E", "Potion": "#0077B6", "Easy": "#48CAE4", "Other": "#ADE8F4"}
                
                fig_pie = px.pie(
                    cat_sales, names="Category", values="Qty", hole=0.6,
                    color="Category", color_discrete_map=color_map
                )
                fig_pie.update_traces(textinfo='percent+label', textfont_size=14, marker=dict(line=dict(color='#FFFFFF', width=2)))
                fig_pie = apply_plotly_layout(fig_pie, "Sales by Product Group")
                fig_pie.update_layout(height=320, showlegend=False, margin=dict(t=60, b=20, l=10, r=10))
                st.plotly_chart(fig_pie, use_container_width=True, config=plotly_config)
            else:
                st.info("Product Code / Qty data not available for pie chart.")

        # ================== ROW 2 ==================
        r2c1, r2c2 = st.columns(2)
        
        with r2c1:
            # Item Wise: Forecast vs Actual
            if "Qty" in req_df.columns and "Forecast Qty" in req_df.columns:
                req_valid = req_df[(req_df["Qty"] > 0) | (req_df["Forecast Qty"] > 0)].sort_values("Qty", ascending=False).head(15)
                fig_combo = go.Figure()
                fig_combo.add_trace(go.Bar(x=req_valid["Item Name"], y=req_valid["Qty"], name="Actual Sales", marker_color="#0096C7", opacity=0.95))
                fig_combo.add_trace(go.Scatter(x=req_valid["Item Name"], y=req_valid["Forecast Qty"], name="Forecast", mode="lines+markers", line=dict(color="#03045E", width=3), marker=dict(size=8, color="#FFFFFF", line=dict(width=2, color="#03045E"))))
                
                fig_combo = apply_plotly_layout(fig_combo, "Item Wise: Forecast vs Actual Sales")
                fig_combo.update_layout(height=380, barmode='group', margin=dict(t=60, b=30, l=20, r=20))
                fig_combo.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_combo, use_container_width=True, config=plotly_config)
            else:
                st.info("Qty / Forecast Qty data not available for bar chart.")

        with r2c2:
            # Item Wise: Forecast Achievement %
            if "Qty" in req_df.columns and "Forecast Qty" in req_df.columns:
                req_valid["Ach %"] = np.where(req_valid["Forecast Qty"] > 0, (req_valid["Qty"] / req_valid["Forecast Qty"]) * 100, 0)
                req_sorted = req_valid.sort_values("Ach %", ascending=True)
                
                # Color logic based on blue palette
                colors = ["#023E8A" if val >= 100 else "#00B4D8" if val >= 75 else "#90E0EF" for val in req_sorted["Ach %"]]
                
                fig_hbar = go.Figure(go.Bar(
                    x=req_sorted["Ach %"].clip(upper=150),
                    y=req_sorted["Item Name"],
                    orientation='h',
                    marker_color=colors,
                    text=req_sorted["Ach %"].apply(lambda x: f"{x:.0f}%"),
                    textposition='outside',
                    textfont=dict(color="#03045E", weight="bold")
                ))
                fig_hbar = apply_plotly_layout(fig_hbar, "Item Wise: Target Achievement %")
                fig_hbar.update_layout(height=380, showlegend=False, margin=dict(t=60, b=30, l=20, r=20))
                fig_hbar.update_xaxes(showgrid=True, range=[0, 160])
                fig_hbar.update_yaxes(showgrid=False)
                st.plotly_chart(fig_hbar, use_container_width=True, config=plotly_config)
            else:
                st.info("Data not available for achievement chart.")

        # STREAMING_CHUNK:Rendering Bottom Table...
        # ================== ROW 4 ==================
        st.markdown("<h4 style='color: #03045E; margin-top: 1rem; font-weight: 800;'>👥 Manager vs Representative Hierarchy & Completion</h4>", unsafe_allow_html=True)
        
        required_columns = {"Manager", "Representative", "Sales", "Target"}
        if required_columns.issubset(rep_df.columns):
            rep_clean = rep_df[(rep_df["Sales"] > 0) | (rep_df["Target"] > 0)].copy()

            if not rep_clean.empty:
                rep_clean["Manager"] = (
                    rep_clean["Manager"].fillna("Unassigned").astype(str)
                    .str.replace("Mr.", "", regex=False).str.strip()
                )
                rep_clean["Representative"] = (
                    rep_clean["Representative"].fillna("Unknown").astype(str).str.strip()
                )

                hierarchy_rows = []
                for manager, manager_df in rep_clean.groupby("Manager", sort=True):
                    manager_sales = manager_df["Sales"].sum()
                    manager_target = manager_df["Target"].sum()
                    hierarchy_rows.append({
                        "Manager": manager,
                        "Representative": "Manager total",
                        "Sales": manager_sales,
                        "Target": manager_target,
                        "Achievement %": (manager_sales / manager_target * 100) if manager_target > 0 else 0,
                        "Row type": "manager",
                    })

                    for representative, rep_values in manager_df.groupby("Representative", sort=True):
                        rep_sales = rep_values["Sales"].sum()
                        rep_target = rep_values["Target"].sum()
                        hierarchy_rows.append({
                            "Manager": "",
                            "Representative": f"↳ {representative}",
                            "Sales": rep_sales,
                            "Target": rep_target,
                            "Achievement %": (rep_sales / rep_target * 100) if rep_target > 0 else 0,
                            "Row type": "representative",
                        })

                grand_sales = rep_clean["Sales"].sum()
                grand_target = rep_clean["Target"].sum()
                hierarchy_rows.append({
                    "Manager": "Grand Total",
                    "Representative": "All representatives",
                    "Sales": grand_sales,
                    "Target": grand_target,
                    "Achievement %": (grand_sales / grand_target * 100) if grand_target > 0 else 0,
                    "Row type": "grand_total",
                })

                hierarchy_df = pd.DataFrame(hierarchy_rows)
                display_df = hierarchy_df.drop(columns="Row type")

                def style_hierarchy(row):
                    row_type = hierarchy_df.loc[row.name, "Row type"]
                    if row_type == "manager":
                        return ["background-color: #ADE8F4; color: #03045E; font-weight: 800;"] * len(row)
                    if row_type == "grand_total":
                        return ["background-color: #03045E; color: white; font-weight: 800;"] * len(row)
                    return [""] * len(row)

                styled_hierarchy = (
                    display_df.style
                    .format({"Sales": "{:,.0f}", "Target": "{:,.0f}", "Achievement %": "{:.1f}%"})
                    .apply(style_hierarchy, axis=1)
                    .set_table_styles([
                        {"selector": "th", "props": [
                            ("background-color", "#03045E"), ("color", "white"),
                            ("font-weight", "800"), ("text-align", "center")
                        ]},
                        {"selector": "td", "props": [
                            ("border-bottom", "1px solid #CAF0F8"), ("padding", "10px")
                        ]},
                    ])
                )
                try:
                    styled_hierarchy = styled_hierarchy.hide(axis="index")
                except AttributeError:
                    pass

                st.dataframe(styled_hierarchy, use_container_width=True)
            else:
                st.info("No representative sales or target data is available for this date.")
        else:
            st.info("Manager, Representative, Sales, or Target data is not available for the summary table.")

if __name__ == "__main__":
    show()
