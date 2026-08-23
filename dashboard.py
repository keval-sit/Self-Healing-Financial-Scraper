import streamlit as st
import pandas as pd
import time
import os
import sys

# Add src directory to path if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from src.config import FIELDS, MOCK_SITE_ID, MOCK_SERVER_PORT, MOCK_V1_SELECTORS
    from src.storage import Storage
    from src.selector_store import SelectorStore
    from src.pipeline import ScrapePipeline
    import src.mock_server as mock_server
except ImportError as e:
    st.error(f"Error importing modules: {e}")
    st.stop()

# --- Page Config ---
st.set_page_config(
    page_title="Self-Healing Financial Scraper",
    page_icon="🔧",
    layout="wide"
)

# --- Initialization ---
@st.cache_resource
def init_system():
    # Start mock server
    mock_server.start_server()
    
    # Initialize pipeline
    pipeline = ScrapePipeline()
    pipeline.initialize(MOCK_SITE_ID, MOCK_V1_SELECTORS)
    return pipeline

try:
    pipeline = init_system()
    storage = pipeline.storage
except Exception as e:
    st.error(f"Error initializing system: {e}")
    st.stop()

if 'last_cycle_result' not in st.session_state:
    st.session_state['last_cycle_result'] = None

# --- Sidebar ---
st.sidebar.title("🎮 Demo Controls")

st.sidebar.subheader("Mock Site Version")
try:
    current_version = mock_server.get_current_version()
except Exception as e:
    current_version = "unknown"
st.sidebar.info(f"Current Version: **{current_version}**")

col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("📄 Serve v1 (Original)"):
        try:
            mock_server.switch_version("v1")
            st.sidebar.success("Switched to v1")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error: {e}")
with col2:
    if st.button("🔄 Switch to v2 (Redesign)"):
        try:
            mock_server.switch_version("v2")
            st.sidebar.success("Switched to v2")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

st.sidebar.subheader("Scraping")
if st.sidebar.button("🚀 Run Scrape Cycle", type="primary"):
    with st.spinner("Running scrape cycle..."):
        try:
            # Fetch HTML from mock server
            html = mock_server.get_page_content(mock_server.get_current_version())
            # Run cycle
            result = pipeline.run_cycle(MOCK_SITE_ID, html)
            st.session_state['last_cycle_result'] = result
            st.sidebar.success("Cycle completed!")
        except Exception as e:
            st.sidebar.error(f"Error running cycle: {e}")

st.sidebar.subheader("Database")
if st.sidebar.button("🗑️ Reset Database"):
    try:
        pipeline.reset()
        st.session_state['last_cycle_result'] = None
        st.sidebar.success("Database reset!")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Error resetting DB: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown("""
**Instructions:**
1. Start with v1 and run a scrape cycle.
2. Switch to v2 to simulate a site redesign.
3. Run another scrape cycle to trigger the AI repair engine.
""")

# --- Main Content ---
st.title("🔧 Self-Healing Financial Scraper Dashboard")

# Top Metrics
try:
    fields_tracked = len(FIELDS)
    
    last_status = "N/A"
    if st.session_state['last_cycle_result']:
        last_status = st.session_state['last_cycle_result'].get('status', 'N/A')
        
    active_alerts = len(storage.get_active_alerts())
    total_repairs = len(storage.get_repair_log(1000))
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fields Tracked", fields_tracked)
    m2.metric("Last Cycle Status", last_status)
    m3.metric("Active Alerts", active_alerts)
    m4.metric("Total Repairs", total_repairs)
except Exception as e:
    st.error(f"Error loading metrics: {e}")

st.markdown("---")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Live Data", 
    "🔧 Repair History", 
    "🚨 Alerts", 
    "📋 Cycle Details", 
    "⚙️ Configuration"
])

# Tab 1: Live Data
with tab1:
    st.subheader("Latest Extracted Data")
    try:
        data = storage.get_extracted_data(MOCK_SITE_ID, limit=len(FIELDS))
        if data:
            df = pd.DataFrame(data)
            def style_status(val):
                color = 'green' if val == 'pass' else 'orange' if val == 'flagged' else 'red' if val == 'fail' else 'black'
                return f'color: {color}'
            
            if 'validation_status' in df.columns:
                st.dataframe(df.style.map(style_status, subset=['validation_status']), use_container_width=True)
            else:
                st.dataframe(df, use_container_width=True)
        else:
            st.info("No data extracted yet. Run a scrape cycle.")
    except Exception as e:
        st.error(f"Error fetching live data: {e}")

# Tab 2: Repair History
with tab2:
    st.subheader("Repair Log")
    try:
        repairs = storage.get_repair_log(limit=50)
        if repairs:
            df_repairs = pd.DataFrame(repairs)
            st.dataframe(df_repairs, use_container_width=True)
            st.caption(f"Showing last {len(repairs)} repairs.")
        else:
            st.info("No repairs have occurred yet.")
    except Exception as e:
        st.error(f"Error fetching repair history: {e}")

# Tab 3: Alerts
with tab3:
    st.subheader(f"Active Alerts ({active_alerts})")
    try:
        alerts = storage.get_active_alerts()
        if alerts:
            for alert in alerts:
                alert_type = alert.get('alert_type', 'info').lower()
                msg = f"**{alert.get('field_name', 'Unknown')}**: {alert.get('message', '')} ({alert.get('timestamp', '')})"
                if alert_type == 'error':
                    st.error(msg)
                elif alert_type == 'warning':
                    st.warning(msg)
                elif alert_type == 'success':
                    st.success(msg)
                else:
                    st.info(msg)
        else:
            st.info("No active alerts.")
    except Exception as e:
        st.error(f"Error fetching alerts: {e}")

# Tab 4: Cycle Details
with tab4:
    if st.session_state['last_cycle_result']:
        res = st.session_state['last_cycle_result']
        st.subheader(f"Cycle {res.get('cycle_number', 'N/A')} Details")
        st.write(f"**Status:** {res.get('status', 'N/A')}")
        
        ext_res = res.get('extraction_results', {})
        fail_det = res.get('failure_detection', {})
        rep_res = res.get('repair_results', {})
        val_res = res.get('validation_results', {})
        
        for field in FIELDS.keys():
            with st.expander(f"Field: {field}"):
                colA, colB = st.columns(2)
                
                with colA:
                    st.markdown("**Extraction & Validation**")
                    if field in ext_res:
                        e = ext_res[field]
                        st.write(f"Raw Value: `{e.get('raw_value')}`")
                        st.write(f"Success: {e.get('success')}")
                        st.write(f"Selector Used: `{e.get('selector')}`")
                    else:
                        st.write("No extraction data.")
                        
                    if field in val_res:
                        v = val_res[field]
                        st.write(f"Validation Status: **{v.get('status')}**")
                        if 'confidence' in v:
                            st.progress(v.get('confidence', 0.0), text=f"Validation Confidence: {v.get('confidence', 0.0):.2f}")
                
                with colB:
                    st.markdown("**Failure & Repair**")
                    if field in fail_det:
                        f = fail_det[field]
                        st.write(f"Failed: {f.get('failed')}")
                        if f.get('failed'):
                            st.write(f"Reasons: {', '.join(f.get('reasons', []))}")
                    else:
                        st.write("No failure data.")
                        
                    if field in rep_res:
                        r = rep_res[field]
                        st.write(f"Repair Success: {r.get('success')}")
                        if r.get('success'):
                            st.write(f"New Selector: `{r.get('new_selector')}`")
                            st.write(f"Method: {r.get('method')}")
                            if 'confidence' in r:
                                st.progress(r.get('confidence', 0.0), text=f"Repair Confidence: {r.get('confidence', 0.0):.2f}")
                            st.write(f"Justification: {r.get('justification')}")
    else:
        st.info("Run a scrape cycle to see details.")

# Tab 5: Configuration
with tab5:
    st.subheader("Field Configuration")
    st.json(FIELDS)
    
    st.subheader("Selector History")
    try:
        for field in FIELDS.keys():
            with st.expander(f"History for {field}"):
                history = storage.get_selector_history(MOCK_SITE_ID)
                field_history = [h for h in history if h.get('field_name') == field]
                if field_history:
                    st.dataframe(pd.DataFrame(field_history))
                else:
                    st.write("No history available.")
    except Exception as e:
        st.error(f"Error fetching selector history: {e}")
