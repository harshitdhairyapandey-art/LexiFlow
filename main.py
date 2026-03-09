import streamlit as st
import threading
import os
import time
from pathlib import Path
import queue

# --- Engine & Provider Imports ---
from engine import LexiFlowMasterEngine
from out import OutputAssembler
from flash import init_engine as init_flash_engine
from pro import init_engine as init_pro_engine
from flash import DEFAULT_PROMPT as FLASH_PROMPT
from pro import DEFAULT_PROMPT as PRO_PROMPT

# --- MODEL REGISTRY ---
MODELS = {
    "gemini": [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3-flash",
        "gemini-3-pro-preview",
    ],
    "openai": [
        "gpt-5-nano",
        "gpt-3.5-turbo",
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1",
    ],
    "anthropic": [
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-5",
        "claude-sonnet-4",
        "claude-opus-4",
    ],
    "lightning": [
        "google/gemini-2.5-flash-lite",
        "google/gemini-2.5-flash",
        "deepseek-ai/deepseek-v3",
        "meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo",
        "openai/gpt-4o",
        "anthropic/claude-haiku-4-5-20251001",
    ],
}

# --- Page Configuration ---
st.set_page_config(
    page_title="LEXIFLOW | Master Control",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Theme Styling ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #262730; }
    .stButton>button:hover { border-color: #2ecc71; color: #2ecc71; }
    code { color: #2ecc71 !important; white-space: pre-wrap !important; }
    </style>
    """, unsafe_allow_html=True)

# --- Persistence Layer (Session State) ---
if "logs" not in st.session_state:
    st.session_state.logs = []
if "progress" not in st.session_state:
    st.session_state.progress = 0
if "status" not in st.session_state:
    st.session_state.status = "READY"
if "is_running" not in st.session_state:
    st.session_state.is_running = False

# --- Callback Bridge ---
def process_ui_queue():
    while not st.session_state.ui_queue.empty():
        data = st.session_state.ui_queue.get()
        st.session_state.status = data.get('status', 'Processing')
        st.session_state.progress = data.get('progress', 0)
        log_entry = f"[{data['status']}] {data['log']}"
        if not st.session_state.logs or st.session_state.logs[-1] != log_entry:
            st.session_state.logs.append(log_entry)
        if data['status'] in ["Complete", "Error", "Stopped"]:
            st.session_state.is_running = False

if "ui_queue" not in st.session_state:
    st.session_state.ui_queue = queue.Queue()

if "engine" not in st.session_state:
    st.session_state.engine = LexiFlowMasterEngine(ui_callback=lambda data: st.session_state.ui_queue.put(data))

# --- Sidebar Logic ---
with st.sidebar:
    st.title("⚡ LEXIFLOW")
    st.caption("Universal AI Orchestrator")
    st.markdown("---")

    st.subheader("🛠️ Configuration")

    st.markdown("**⚡ Flash Engine**")
    f_prov = st.selectbox("Flash Provider", ["gemini", "lightning", "openai", "anthropic"], index=0)
    f_api_key = st.text_input("Flash API Key", type="password")
    f_model = st.selectbox("Flash Model", MODELS[f_prov])

    st.markdown("**✨ Pro Engine**")
    p_prov = st.selectbox("Pro Provider", ["gemini", "lightning", "openai", "anthropic"], index=0)
    p_api_key = st.text_input("Pro API Key", type="password")
    p_model = st.selectbox("Pro Model", MODELS[p_prov])

    st.markdown("---")
    if st.button("🛑 EMERGENCY STOP", type="primary"):
        st.session_state.engine.stop_event.set()
        st.session_state.is_running = False
        st.error("Stop signal sent to engines.")

# --- Main Dashboard ---
col_main, col_ctrl = st.columns([3, 1])

with col_main:
    st.header(f"Mission: {st.session_state.status}")
    progress_val = float(min(max(st.session_state.progress / 100, 0.0), 1.0))
    st.progress(progress_val)

    process_ui_queue()
    st.subheader("📟 System Console")
    console_out = "\n".join(st.session_state.logs[-15:])
    st.code(console_out if console_out else "System Idle... Waiting for Launch.", language="bash")

with col_ctrl:
    st.subheader("🕹️ Controls")

    file_upload = st.file_uploader("Upload Novel", type=["pdf", "docx", "epub"])

    # --- START MISSION ---
    if st.button("🚀 LAUNCH MISSION", disabled=st.session_state.is_running):
        if not file_upload or not f_api_key or not p_api_key:
            st.warning("⚠️ File and API Keys required!")
        else:
            try:
                temp_path = Path(f"LexiFlow/1_input_copy/{file_upload.name}")
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                with open(temp_path, "wb") as f:
                    f.write(file_upload.getbuffer())

                f_engine = init_flash_engine(f_prov, f_api_key, f_model)
                p_engine = init_pro_engine(p_prov, p_api_key, p_model)
                st.session_state.engine.configure_engines(f_engine, p_engine, FLASH_PROMPT, PRO_PROMPT)

                st.session_state.is_running = True
                st.session_state.logs.append("Initiating background engine...")

                launcher = threading.Thread(
                    target=st.session_state.engine.start_engine,
                    args=(str(temp_path),),
                    daemon=True
                )
                launcher.start()
                st.success("Mission Launched!")
            except Exception as e:
                st.error(f"Initialization Failed: {e}")

    # --- RESUME MISSION ---
    if st.button("⏩ RESUME MISSION", disabled=st.session_state.is_running):
        if not f_api_key or not p_api_key:
            st.warning("⚠️ API Keys required to resume.")
        else:
            try:
                f_engine = init_flash_engine(f_prov, f_api_key, f_model)
                p_engine = init_pro_engine(p_prov, p_api_key, p_model)
                st.session_state.engine.configure_engines(f_engine, p_engine, FLASH_PROMPT, PRO_PROMPT)
                st.session_state.is_running = True
                threading.Thread(
                    target=st.session_state.engine.start_engine,
                    args=(None,),
                    daemon=True
                ).start()
                st.info("Resuming from last saved state...")
            except Exception as e:
                st.error(f"Resume Failed: {e}")

    # --- RESTART FRESH ---
    if st.button("🔄 RESTART FRESH"):
        st.session_state.logs = ["Archiving previous session..."]
        for folder_key in ["trans", "pro"]:
            folder = st.session_state.engine.paths[folder_key]
            for f in folder.glob("*.txt"):
                if not f.name.startswith("OLD_"):
                    f.rename(folder / f"OLD_{f.name}")
        st.session_state.engine.state = {"completed_y": [], "polished_y": []}
        st.session_state.engine.save_session()
        st.session_state.progress = 0
        st.session_state.status = "READY"
        st.rerun()

    st.markdown("---")

    # --- EXPORT ---
    if st.button("📂 EXPORT DOCX"):
        try:
            with st.spinner("Merging files..."):
                assembler = OutputAssembler(title=f"LexiFlow_Export_{int(time.time())}")
                assembler.merge_files(st.session_state.engine.paths["pro"])
                st.balloons()
                st.success("Document generated in 5_final_novel folder!")
        except Exception as e:
            st.error(f"Export Error: {e}")

# --- Auto-Refresh ---
if st.session_state.is_running:
    time.sleep(2)
    st.rerun()