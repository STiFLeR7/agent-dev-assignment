import streamlit as st
import json
import time
from pathlib import Path
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from typing import List, Dict, Any, Optional
import base64

st.set_page_config(
    page_title="Invoice Reconciliation Agent",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 2rem;
    }
    .agent-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem;
    }
    .confidence-high { color: #4CAF50; font-weight: bold; }
    .confidence-medium { color: #FF9800; font-weight: bold; }
    .confidence-low { color: #f44336; font-weight: bold; }
    .status-auto-approve { 
        background-color: #4CAF50; 
        color: white; 
        padding: 0.3rem 0.8rem; 
        border-radius: 15px;
        font-weight: bold;
    }
    .status-review { 
        background-color: #FF9800; 
        color: white; 
        padding: 0.3rem 0.8rem; 
        border-radius: 15px;
        font-weight: bold;
    }
    .status-escalate { 
        background-color: #f44336; 
        color: white; 
        padding: 0.3rem 0.8rem; 
        border-radius: 15px;
        font-weight: bold;
    }
    .stMetric > div {
        background-color: rgba(28, 131, 225, 0.1);
        padding: 10px;
        border-radius: 5px;
    }
    .stMetric label {
        color: #666 !important;
    }
    .stMetric > div > div {
        color: #1E88E5 !important;
    }
    div[data-testid="stMetricValue"] {
        color: #333 !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: rgba(28, 131, 225, 0.1);
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

def init_session_state():
    if 'processing_results' not in st.session_state:
        st.session_state.processing_results = []
    if 'current_invoice' not in st.session_state:
        st.session_state.current_invoice = None
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'process_all' not in st.session_state:
        st.session_state.process_all = False
    if 'po_database' not in st.session_state:
        st.session_state.po_database = None

def load_po_database():
    po_file = Path(__file__).parent / "purchase_orders.json"
    if po_file.exists():
        with open(po_file, 'r') as f:
            data = json.load(f)
            return data.get("purchase_orders", [])
    return []

def get_invoice_files() -> List[Path]:
    base_dir = Path(__file__).parent
    invoice_files = list(base_dir.glob("Invoice_*.pdf"))
    return sorted(invoice_files)

def display_pdf_preview(pdf_path: str):
    try:
        import fitz
        doc = fitz.open(pdf_path)
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        img_bytes = pix.tobytes("png")
        st.image(img_bytes, caption=f"Preview: {Path(pdf_path).name}", width="stretch")
        doc.close()
    except Exception as e:
        st.warning(f"Could not preview PDF: {e}")

def render_confidence_badge(confidence: float) -> str:
    percentage = confidence * 100
    if percentage >= 90:
        return f'<span class="confidence-high">●</span> {percentage:.1f}%'
    elif percentage >= 70:
        return f'<span class="confidence-medium">●</span> {percentage:.1f}%'
    else:
        return f'<span class="confidence-low">●</span> {percentage:.1f}%'

def render_status_badge(status: str) -> str:
    badges = {
        "auto_approve": '<span class="status-auto-approve">✅ AUTO APPROVE</span>',
        "flag_for_review": '<span class="status-review">🔶 FLAG FOR REVIEW</span>',
        "escalate_to_human": '<span class="status-escalate">🔴 ESCALATE</span>',
    }
    return badges.get(status, status)

def render_agent_workflow():
    st.markdown("### 🔄 Agent Workflow")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div class="agent-card">
            <h4>📄 Document Intelligence</h4>
            <p>Extract data from invoice</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="agent-card">
            <h4>🔗 Matching Agent</h4>
            <p>Match to Purchase Order</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="agent-card">
            <h4>🔍 Discrepancy Detection</h4>
            <p>Find variances</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div class="agent-card">
            <h4>✅ Resolution</h4>
            <p>Recommend action</p>
        </div>
        """, unsafe_allow_html=True)

def process_invoice(invoice_path: str, progress_callback=None) -> Dict[str, Any]:
    from src.orchestrator import InvoiceReconciliationWorkflow
    
    try:
        workflow = InvoiceReconciliationWorkflow()
        result = workflow.process_invoice(invoice_path)
        return result.model_dump()
    except Exception as e:
        st.error(f"Error processing invoice: {e}")
        return None

def render_extraction_results(result: Dict[str, Any]):
    if not result:
        return
    
    pr = result.get("processing_results", {})
    if isinstance(pr, dict):
        extracted = pr.get("extracted_data", {}) or {}
    else:
        extracted = {}
    
    if not extracted:
        st.warning("No extraction data available - processing may have failed.")
        return
    
    st.markdown("### 📄 Extraction Results")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Invoice Number", extracted.get("invoice_number", "N/A"))
    with col2:
        st.metric("Invoice Date", extracted.get("invoice_date", "N/A"))
    with col3:
        st.metric("Total Amount", f"£{extracted.get('total', 0):,.2f}")
    
    col4, col5, col6 = st.columns(3)
    with col4:
        supplier = extracted.get("supplier_name", "N/A")
        st.metric("Supplier", supplier[:30] if supplier else "N/A")
    with col5:
        po_ref = extracted.get("po_reference") or "⚠️ Missing"
        st.metric("PO Reference", po_ref)
    with col6:
        st.metric("Currency", extracted.get("currency", "GBP"))
    
    st.markdown("#### Line Items")
    line_items = extracted.get("line_items", [])
    if line_items:
        import pandas as pd
        df = pd.DataFrame(line_items)
        df.columns = [col.replace("_", " ").title() for col in df.columns]
        st.dataframe(df, width="stretch", hide_index=True)

def render_matching_results(result: Dict[str, Any]):
    if not result:
        return
    
    pr = result.get("processing_results", {}) or {}
    matching = pr.get("matching_results", {}) if isinstance(pr, dict) else {}
    
    if not matching:
        matching = {}
    
    st.markdown("### 🔗 Matching Results")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        matched_po = matching.get("matched_po") or "No Match"
        st.metric("Matched PO", matched_po)
    with col2:
        confidence = matching.get("po_match_confidence", 0)
        st.metric("Match Confidence", f"{confidence*100:.1f}%")
    with col3:
        method = matching.get("match_method", "N/A")
        if method:
            method = method.replace("_", " ").title()
        st.metric("Match Method", method)
    
    col4, col5 = st.columns(2)
    with col4:
        supplier_match = "✅ Yes" if matching.get("supplier_match") else "❌ No"
        st.metric("Supplier Match", supplier_match)
    with col5:
        items_matched = matching.get("line_items_matched", 0)
        items_total = matching.get("line_items_total", 0)
        st.metric("Items Matched", f"{items_matched}/{items_total}")
    
    reasoning = matching.get("agent_reasoning", "")
    if reasoning:
        with st.expander("🧠 Agent Reasoning", expanded=False):
            st.info(reasoning)

def render_discrepancy_results(result: Dict[str, Any]):
    if not result:
        return
    
    pr = result.get("processing_results", {}) or {}
    if isinstance(pr, dict):
        discrepancies = pr.get("discrepancies", []) or []
        total_variance = pr.get("total_variance", {}) or {}
    else:
        discrepancies = []
        total_variance = {}
    
    st.markdown("### 🔍 Discrepancy Analysis")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        count = len(discrepancies)
        st.metric("Discrepancies Found", count)
    with col2:
        variance_amt = total_variance.get("amount", 0)
        st.metric("Total Variance", f"£{variance_amt:+,.2f}")
    with col3:
        variance_pct = total_variance.get("percentage", 0)
        st.metric("Variance %", f"{variance_pct:+.1f}%")
    
    if discrepancies:
        st.markdown("#### Discrepancy Details")
        for i, disc in enumerate(discrepancies, 1):
            severity = disc.get("severity", "medium")
            severity_color = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(severity, "⚪")
            
            with st.expander(f"{severity_color} {disc.get('type', 'Unknown').replace('_', ' ').title()}", expanded=True):
                st.write(f"**Details:** {disc.get('details', 'N/A')}")
                st.write(f"**Severity:** {severity.upper()}")
                st.write(f"**Invoice Value:** {disc.get('invoice_value', 'N/A')}")
                st.write(f"**PO Value:** {disc.get('po_value', 'N/A')}")
                if disc.get("variance_percentage"):
                    st.write(f"**Variance:** {disc.get('variance_percentage', 0):+.1f}%")
    else:
        st.success("✅ No discrepancies detected!")

def render_resolution_results(result: Dict[str, Any]):
    if not result:
        return
    
    pr = result.get("processing_results", {}) or {}
    
    st.markdown("### ✅ Resolution Recommendation")
    
    action = pr.get("recommended_action", "unknown") if pr else "unknown"
    confidence = pr.get("confidence", 0) if pr else 0
    risk_level = pr.get("risk_level", "unknown") if pr else "unknown"
    
    status_colors = {
        "auto_approve": ("success", "✅ AUTO APPROVE", "This invoice can be automatically approved."),
        "flag_for_review": ("warning", "🔶 FLAG FOR REVIEW", "This invoice requires human review."),
        "escalate_to_human": ("error", "🔴 ESCALATE", "This invoice has critical issues requiring immediate attention."),
    }
    
    color, label, desc = status_colors.get(action, ("info", action, ""))
    
    if color == "success":
        st.success(f"**{label}**\n\n{desc}")
    elif color == "warning":
        st.warning(f"**{label}**\n\n{desc}")
    elif color == "error":
        st.error(f"**{label}**\n\n{desc}")
    else:
        st.info(f"**{label}**\n\n{desc}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Confidence", f"{confidence*100:.1f}%")
    with col2:
        st.metric("Risk Level", risk_level.upper() if risk_level else "N/A")
    
    reasoning = pr.get("agent_reasoning", "")
    if reasoning:
        with st.expander("🧠 Full Agent Reasoning", expanded=True):
            st.info(reasoning)

def render_agent_trace(result: Dict[str, Any]):
    if not result:
        return
    
    traces = result.get("agent_execution_trace", {})
    
    st.markdown("### 📊 Agent Execution Trace")
    
    agent_names = ["document_intelligence", "matching", "discrepancy_detection", "resolution"]
    display_names = ["Document Intelligence", "Matching", "Discrepancy Detection", "Resolution"]
    
    trace_data = []
    for name, display in zip(agent_names, display_names):
        trace = traces.get(name, {})
        if trace:
            trace_data.append({
                "Agent": display,
                "Duration (ms)": trace.get("duration_ms", 0),
                "Confidence": trace.get("confidence", 0) * 100,
                "Status": trace.get("status", "unknown"),
            })
    
    if trace_data:
        import pandas as pd
        df = pd.DataFrame(trace_data)
        
        fig = px.bar(
            df, 
            x="Agent", 
            y="Duration (ms)",
            color="Status",
            color_discrete_map={"success": "#4CAF50", "error": "#f44336"},
            title="Agent Processing Time"
        )
        st.plotly_chart(fig, width="stretch", key="agent_duration_chart")
        
        fig2 = go.Figure()
        for i, row in df.iterrows():
            fig2.add_trace(go.Indicator(
                mode="gauge+number",
                value=row["Confidence"],
                domain={'x': [i*0.25, (i+1)*0.25-0.02], 'y': [0, 1]},
                title={'text': row["Agent"][:10]},
                gauge={
                    'axis': {'range': [0, 100]},
                    'bar': {'color': "#1E88E5"},
                    'steps': [
                        {'range': [0, 70], 'color': "#ffcdd2"},
                        {'range': [70, 90], 'color': "#fff9c4"},
                        {'range': [90, 100], 'color': "#c8e6c9"},
                    ],
                }
            ))
        
        fig2.update_layout(height=200, title="Agent Confidence Levels")
        st.plotly_chart(fig2, width="stretch", key="agent_confidence_chart")

def render_po_database():
    st.markdown("### 📋 Purchase Order Database")
    
    po_data = load_po_database()
    
    if not po_data:
        st.warning("No purchase orders found in database.")
        return
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total POs", len(po_data))
    with col2:
        total_value = sum(po.get("total", 0) for po in po_data)
        st.metric("Total Value", f"£{total_value:,.2f}")
    with col3:
        suppliers = set(po.get("supplier", "") for po in po_data)
        st.metric("Unique Suppliers", len(suppliers))
    
    import pandas as pd
    po_summary = []
    for po in po_data:
        po_summary.append({
            "PO Number": po.get("po_number", ""),
            "Supplier": po.get("supplier", ""),
            "Date": po.get("date", ""),
            "Total": f"£{po.get('total', 0):,.2f}",
            "Items": len(po.get("line_items", [])),
        })
    
    df = pd.DataFrame(po_summary)
    st.dataframe(df, width="stretch", hide_index=True)
    
    st.markdown("#### PO Details")
    selected_po = st.selectbox("Select PO to view details:", [po.get("po_number") for po in po_data])
    
    if selected_po:
        po = next((p for p in po_data if p.get("po_number") == selected_po), None)
        if po:
            st.json(po)

def render_statistics():
    st.markdown("### 📈 Processing Statistics")
    
    results = st.session_state.processing_results
    
    if not results:
        st.info("No processing data available yet.")
        return
    
    actions = []
    confidences = []
    totals = []
    
    for r in results:
        pr = r.get("processing_results", {})
        action = pr.get("recommended_action", "unknown")
        if hasattr(action, 'value'):
            action = action.value
        actions.append(action)
        confidences.append(pr.get("confidence", 0))
        extracted = pr.get("extracted_data", {})
        totals.append(extracted.get("total", 0) if extracted else 0)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Processed", len(results))
    with col2:
        auto_approved = actions.count("auto_approve")
        st.metric("Auto Approved", auto_approved)
    with col3:
        flagged = actions.count("flag_for_review")
        st.metric("Flagged", flagged)
    with col4:
        escalated = actions.count("escalate_to_human")
        st.metric("Escalated", escalated)
    
    import pandas as pd
    
    if actions:
        action_counts = pd.Series(actions).value_counts()
        fig = px.pie(
            values=action_counts.values,
            names=action_counts.index,
            title="Decision Distribution",
            color_discrete_sequence=["#4CAF50", "#FF9800", "#f44336"]
        )
        st.plotly_chart(fig, width="stretch")

def main():
    init_session_state()
    
    st.markdown('<h1 class="main-header">🧾 Invoice Reconciliation Agent</h1>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.markdown("## 🎛️ Control Panel")
        
        st.markdown("---")
        st.markdown("### 📂 Invoice Selection")
        
        invoice_files = get_invoice_files()
        
        if invoice_files:
            invoice_options = {f.name: str(f) for f in invoice_files}
            selected = st.selectbox(
                "Select Invoice:",
                options=list(invoice_options.keys()),
                key="invoice_selector"
            )
            
            if selected:
                st.session_state.current_invoice = invoice_options[selected]
            
            st.markdown("---")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("▶️ Process", use_container_width=True):
                    st.session_state.processing = True
                    st.rerun()
            
            with col2:
                if st.button("🔄 Clear", use_container_width=True):
                    st.session_state.processing_results = []
                    st.session_state.processing = False
                    st.rerun()
            
            st.markdown("---")
            
            if st.button("📦 Process All Invoices", use_container_width=True):
                st.session_state.process_all = True
                st.rerun()
        else:
            st.warning("No invoice files found. Add Invoice_*.pdf files to the project directory.")
        
        st.markdown("---")
        st.markdown("### 📊 Quick Stats")
        
        total_processed = len(st.session_state.processing_results)
        st.metric("Invoices Processed", total_processed)
        
        if total_processed > 0:
            actions = []
            for r in st.session_state.processing_results:
                pr = r.get("processing_results", {})
                action = pr.get("recommended_action", "unknown")
                if hasattr(action, 'value'):
                    action = action.value
                actions.append(action)
            
            auto_count = actions.count("auto_approve")
            flag_count = actions.count("flag_for_review")
            escalate_count = actions.count("escalate_to_human")
            
            st.write(f"✅ Auto-approved: {auto_count}")
            st.write(f"🔶 Flagged: {flag_count}")
            st.write(f"🔴 Escalated: {escalate_count}")
    
    tabs = st.tabs(["🔄 Workflow", "📄 Process Invoice", "📋 PO Database", "📜 History", "ℹ️ About"])
    
    with tabs[0]:
        render_agent_workflow()
        st.markdown("---")
        render_statistics()
    
    with tabs[1]:
        if st.session_state.process_all:
            st.markdown("### 📦 Processing All Invoices")
            
            invoice_files = get_invoice_files()
            total = len(invoice_files)
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_container = st.container()
            
            for idx, invoice_file in enumerate(invoice_files):
                status_text.text(f"Processing {invoice_file.name}... ({idx + 1}/{total})")
                
                result = process_invoice(str(invoice_file))
                
                if result:
                    st.session_state.processing_results.append(result)
                    pr = result.get("processing_results", {})
                    action = pr.get("recommended_action", "unknown")
                    if hasattr(action, 'value'):
                        action = action.value
                    emoji = {"auto_approve": "✅", "flag_for_review": "🔶", "escalate_to_human": "🔴"}.get(action, "❓")
                    
                    with results_container:
                        st.write(f"{emoji} {invoice_file.name}: **{action.replace('_', ' ').title()}**")
                
                progress_bar.progress((idx + 1) / total)
            
            status_text.text("✅ All invoices processed!")
            st.session_state.process_all = False
            st.rerun()
        
        elif st.session_state.current_invoice:
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.markdown("### 📄 Invoice Preview")
                display_pdf_preview(st.session_state.current_invoice)
            
            with col2:
                if st.session_state.processing:
                    st.markdown("### ⚙️ Processing...")
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    status_text.text("🔍 Extracting invoice data...")
                    progress_bar.progress(25)
                    
                    result = process_invoice(st.session_state.current_invoice)
                    
                    if result:
                        progress_bar.progress(100)
                        status_text.text("✅ Processing complete!")
                        
                        st.session_state.processing_results.append(result)
                        st.session_state.processing = False
                        
                        render_extraction_results(result)
                        render_matching_results(result)
                        render_discrepancy_results(result)
                        render_resolution_results(result)
                        render_agent_trace(result)
                    else:
                        st.error("Processing failed. Check the logs.")
                        st.session_state.processing = False
                
                elif st.session_state.processing_results:
                    last_result = st.session_state.processing_results[-1]
                    render_extraction_results(last_result)
                    render_matching_results(last_result)
                    render_discrepancy_results(last_result)
                    render_resolution_results(last_result)
                    render_agent_trace(last_result)
                else:
                    st.info("👈 Click 'Process' in the sidebar to start processing.")
        else:
            st.warning("Please select an invoice from the sidebar.")
    
    with tabs[2]:
        render_po_database()
    
    with tabs[3]:
        st.markdown("### 📜 Processing History")
        
        if st.session_state.processing_results:
            for i, result in enumerate(st.session_state.processing_results, 1):
                pr = result.get("processing_results", {})
                extracted = pr.get("extracted_data", {}) or {}
                action = pr.get("recommended_action", "unknown")
                if hasattr(action, 'value'):
                    action = action.value
                elif not isinstance(action, str):
                    action = str(action)
                
                status_emoji = {"auto_approve": "✅", "flag_for_review": "🔶", "escalate_to_human": "🔴"}.get(action, "❓")
                
                supplier_name = extracted.get('supplier_name', 'Unknown')
                if supplier_name:
                    supplier_name = supplier_name[:30]
                else:
                    supplier_name = 'Unknown'
                
                with st.expander(f"{status_emoji} {extracted.get('invoice_number', 'Unknown')} - {supplier_name}"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total", f"£{extracted.get('total', 0):,.2f}")
                    with col2:
                        st.metric("PO Match", pr.get("matching_results", {}).get("matched_po") or "None")
                    with col3:
                        st.metric("Action", action.replace("_", " ").title())
                    
                    st.json(result)
            
            if st.button("📥 Export Results as JSON"):
                json_str = json.dumps(st.session_state.processing_results, indent=2, default=str)
                st.download_button(
                    label="Download JSON",
                    data=json_str,
                    file_name=f"invoice_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
        else:
            st.info("No invoices processed yet. Process some invoices to see history.")
    
    with tabs[4]:
        st.markdown("### ℹ️ About This System")
        
        st.markdown("""
        **Multi-Agent Invoice Reconciliation System**
        
        This system uses a team of AI agents to automatically process and reconcile invoices:
        
        1. **Document Intelligence Agent**: Extracts structured data from invoice PDFs using Gemini Vision
        2. **Matching Agent**: Matches invoices to Purchase Orders using exact and fuzzy matching
        3. **Discrepancy Detection Agent**: Identifies price, quantity, and total variances
        4. **Resolution Agent**: Recommends actions based on business rules
        
        **Technologies Used:**
        - Google Gemini 2.0 Flash (Vision API)
        - LangGraph for agent orchestration
        - Streamlit for the user interface
        - PyMuPDF for PDF processing
        """)
        
        st.markdown("---")
        st.markdown("### 🔧 Configuration")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            **Thresholds:**
            - Price tolerance: 5%
            - Quantity tolerance: 2%
            - Min extraction confidence: 70%
            """)
        with col2:
            st.markdown("""
            **Matching:**
            - Fuzzy match threshold: 80%
            - Supplier match required: Yes
            - Date variance: ±30 days
            """)

if __name__ == "__main__":
    main()
