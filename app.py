import streamlit as st
import sqlite3
import requests
import json
import base64
import io
from datetime import datetime
from PIL import Image
from PyPDF2 import PdfReader
from streamlit_mic_recorder import speech_to_text

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="NovaCore AI",
    page_icon="🧠",
    layout="wide"
)

# =========================================================
# DATABASE
# =========================================================
conn = sqlite3.connect("novacore_memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_name TEXT,
    role TEXT,
    content TEXT,
    timestamp TEXT DEFAULT ''
)
""")
conn.commit()

try:
    cursor.execute("ALTER TABLE chats ADD COLUMN timestamp TEXT DEFAULT ''")
    conn.commit()
except Exception:
    pass

# =========================================================
# FUNCTIONS
# =========================================================
def save_message(chat_name, role, content):
    cursor.execute(
        "INSERT INTO chats (chat_name, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (chat_name, role, content, datetime.now().strftime("%H:%M"))
    )
    conn.commit()


def load_chat(chat_name):
    cursor.execute(
        "SELECT role, content, timestamp FROM chats WHERE chat_name=?",
        (chat_name,)
    )
    rows = cursor.fetchall()
    return [
        {"role": row[0], "content": row[1], "timestamp": row[2] or ""}
        for row in rows
    ]


def get_chat_names():
    cursor.execute("SELECT DISTINCT chat_name FROM chats")
    rows = cursor.fetchall()
    names = [row[0] for row in rows]
    if "New Chat" not in names:
        names.insert(0, "New Chat")
    return names


def rename_chat(old_name, new_name):
    cursor.execute(
        "UPDATE chats SET chat_name=? WHERE chat_name=?",
        (new_name, old_name)
    )
    conn.commit()


def clear_chat(chat_name):
    cursor.execute("DELETE FROM chats WHERE chat_name=?", (chat_name,))
    conn.commit()


def check_ollama():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

# =========================================================
# SESSION STATE
# =========================================================
if "current_chat" not in st.session_state:
    st.session_state.current_chat = "New Chat"

if "document_text" not in st.session_state:
    st.session_state.document_text = ""

# =========================================================
# DESIGN SYSTEM — Deep Space Tech
# Palette: Electric Cyan #22d3ee · Soft Violet #a78bfa
#          Space Navy  #020817  · Glass surfaces
# =========================================================
st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── BASE ─────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background: linear-gradient(160deg, #020817 0%, #0a0f1e 55%, #0d1527 100%);
    color: #e2e8f0;
}

.block-container {
    max-width: 1250px;
    padding-top: 1rem;
}

/* ── SIDEBAR ──────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: rgba(5, 8, 22, 0.96) !important;
    backdrop-filter: blur(28px);
    border-right: 1px solid rgba(34, 211, 238, 0.1);
}

section[data-testid="stSidebar"] h3 {
    color: #22d3ee !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    margin-top: 4px !important;
}

section[data-testid="stSidebar"] .stMarkdown hr {
    border-color: rgba(34, 211, 238, 0.08) !important;
}

/* ── TITLE & SUBTITLE ─────────────────────────────── */
.main-title {
    text-align: center;
    font-size: 72px;
    font-weight: 800;
    letter-spacing: -1px;
    background: linear-gradient(135deg, #22d3ee 0%, #a78bfa 60%, #818cf8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 40px rgba(34, 211, 238, 0.25));
    margin-bottom: 4px;
}

.subtitle {
    text-align: center;
    color: rgba(167, 139, 250, 0.75);
    margin-bottom: 36px;
    font-size: 17px;
    font-weight: 400;
    letter-spacing: 0.03em;
}

/* ── BUTTONS ──────────────────────────────────────── */
.stButton button {
    background: linear-gradient(135deg, #0891b2 0%, #6366f1 100%) !important;
    color: #ffffff !important;
    border-radius: 12px !important;
    border: 1px solid rgba(34, 211, 238, 0.2) !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    transition: opacity 0.2s ease, transform 0.15s ease !important;
}

.stButton button:hover {
    opacity: 0.88 !important;
    transform: translateY(-1px) !important;
}

/* ── DOWNLOAD BUTTON ──────────────────────────────── */
[data-testid="stDownloadButton"] button {
    background: rgba(34, 211, 238, 0.08) !important;
    color: #22d3ee !important;
    border: 1px solid rgba(34, 211, 238, 0.25) !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
}

/* ── CHAT INPUT ───────────────────────────────────── */
.stChatInput textarea {
    background: #f8fafc !important;
    color: #0f172a !important;
    border-radius: 18px !important;
    padding: 16px 20px !important;
    font-size: 15px !important;
    font-weight: 500 !important;
    outline: none !important;
    box-shadow: none !important;
    caret-color: #0891b2 !important;
}

.stChatInput textarea::placeholder {
    color: #64748b !important;
}

:root {
    --primary-color: #22d3ee !important;
}

.stChatInputContainer,
[data-testid="stChatInputContainer"],
div[class*="chatInput"] {
    border: 1px solid rgba(34, 211, 238, 0.15) !important;
    border-radius: 22px !important;
    outline: none !important;
    box-shadow: 0 0 0 0 transparent !important;
    background: rgba(10, 15, 30, 0.6) !important;
    backdrop-filter: blur(12px) !important;
}

.stChatInputContainer:focus-within,
[data-testid="stChatInputContainer"]:focus-within {
    border: 1px solid rgba(34, 211, 238, 0.45) !important;
    box-shadow: 0 0 20px rgba(34, 211, 238, 0.08) !important;
}

/* ── CHAT MESSAGES ────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: rgba(255, 255, 255, 0.03);
    border-radius: 18px;
    padding: 16px;
    border: 1px solid rgba(34, 211, 238, 0.07);
    backdrop-filter: blur(16px);
    margin-bottom: 4px;
}

/* ── TYPING INDICATOR ─────────────────────────────── */
.typing-container {
    display: flex;
    align-items: center;
    width: 80px;
    height: 40px;
    padding: 0 14px;
    border-radius: 30px;
    background: rgba(34, 211, 238, 0.07);
    border: 1px solid rgba(34, 211, 238, 0.15);
    backdrop-filter: blur(12px);
}

.typing-dot {
    width: 7px;
    height: 7px;
    margin: 0 3px;
    border-radius: 50%;
    background: #22d3ee;
    animation: bounce 1.2s infinite ease-in-out;
}

.typing-dot:nth-child(1) { animation-delay: 0s; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
    0%,80%,100% { transform: translateY(0px); opacity: 0.4; }
    40%          { transform: translateY(-7px); opacity: 1; }
}

/* ── FEATURE CARDS ────────────────────────────────── */
.feature-card {
    background: rgba(34, 211, 238, 0.03);
    border: 1px solid rgba(34, 211, 238, 0.12);
    padding: 24px 20px;
    border-radius: 20px;
    text-align: center;
    backdrop-filter: blur(14px);
    transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
    cursor: default;
}

.feature-card:hover {
    transform: translateY(-4px);
    border-color: rgba(34, 211, 238, 0.3);
    box-shadow: 0 12px 40px rgba(34, 211, 238, 0.1);
}

.feature-card h3 {
    color: #e2e8f0;
    margin-bottom: 8px;
    font-size: 18px;
}

.feature-card p {
    color: rgba(148, 163, 184, 0.85);
    font-size: 14px;
    margin: 0;
}

/* ── FOOTER ───────────────────────────────────────── */
.nova-footer {
    text-align: center;
    margin-top: 48px;
    padding: 18px;
    color: rgba(100, 116, 139, 0.6);
    font-size: 12px;
    letter-spacing: 0.05em;
    border-top: 1px solid rgba(34, 211, 238, 0.06);
}

.nova-footer span {
    color: rgba(34, 211, 238, 0.5);
}

/* ── ALERTS / STATUS ──────────────────────────────── */
.stSuccess {
    background: rgba(34, 211, 238, 0.07) !important;
    border: 1px solid rgba(34, 211, 238, 0.2) !important;
    color: #22d3ee !important;
    border-radius: 10px !important;
}

.stError {
    background: rgba(239, 68, 68, 0.07) !important;
    border: 1px solid rgba(239, 68, 68, 0.2) !important;
    border-radius: 10px !important;
}

/* ── CAPTION / TIMESTAMP ──────────────────────────── */
.stCaptionContainer p, caption {
    color: rgba(34, 211, 238, 0.45) !important;
    font-size: 11px !important;
}

</style>
""", unsafe_allow_html=True)

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:

    st.title("⚙️ NovaCore")

    if check_ollama():
        st.success("🟢 Ollama Online")
    else:
        st.error("🔴 Ollama Offline — run `ollama serve`")

    if st.button("➕ New Chat", use_container_width=True):
        new_name = f"Chat_{len(get_chat_names()) + 1}"
        st.session_state.current_chat = new_name
        st.rerun()

    st.markdown("### 💬 Chats")

    chat_names = get_chat_names()

    selected_chat = st.radio(
        "",
        chat_names,
        index=chat_names.index(st.session_state.current_chat)
        if st.session_state.current_chat in chat_names else 0
    )

    st.session_state.current_chat = selected_chat

    st.markdown("### ✏️ Chat Options")

    new_chat_name = st.text_input(
        "Rename current chat",
        value=st.session_state.current_chat,
        key="rename_input"
    )

    if st.button("✏️ Rename", use_container_width=True):
        new_chat_name = new_chat_name.strip()
        if new_chat_name and new_chat_name != st.session_state.current_chat:
            rename_chat(st.session_state.current_chat, new_chat_name)
            st.session_state.current_chat = new_chat_name
            st.rerun()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🗑️ Clear", use_container_width=True):
            clear_chat(st.session_state.current_chat)
            st.rerun()

    with col2:
        if st.button("❌ Delete", use_container_width=True):
            clear_chat(st.session_state.current_chat)
            st.session_state.current_chat = "New Chat"
            st.rerun()

    export_msgs = load_chat(st.session_state.current_chat)
    if export_msgs:
        export_text = f"# {st.session_state.current_chat}\n\n"
        for m in export_msgs:
            label = "You" if m["role"] == "user" else "NovaCore AI"
            ts = f" [{m['timestamp']}]" if m.get("timestamp") else ""
            export_text += f"**{label}{ts}:**\n{m['content']}\n\n---\n\n"
        st.download_button(
            "📥 Export Chat",
            export_text,
            file_name=f"{st.session_state.current_chat}.md",
            mime="text/markdown",
            use_container_width=True
        )

    st.markdown("---")

    st.markdown("### 🤖 Active Model")

    model_name = st.radio(
        "",
        [
            "llama3",
            "deepseek-r1:latest",
            "moondream",
            "mistral",
            "gemma",
            "phi3:latest"
        ]
    )

    st.success(f"🟢 {model_name} Active")

    st.markdown("---")

    st.markdown("### 📄 Upload PDF/TXT")

    uploaded_file = st.file_uploader(
        "",
        type=["pdf", "txt"]
    )

    if uploaded_file:

        extracted_text = ""

        if uploaded_file.type == "application/pdf":

            pdf_reader = PdfReader(uploaded_file)

            for page in pdf_reader.pages:

                text = page.extract_text()

                if text:
                    extracted_text += text + "\n"

        else:
            extracted_text = uploaded_file.read().decode("utf-8")

        st.session_state.document_text = extracted_text[:15000]

        st.success("Document uploaded.")

    else:
        st.session_state.document_text = ""

    st.markdown("---")

    st.markdown("### 🖼 Upload Image")

    uploaded_image = st.file_uploader(
        "",
        type=["png", "jpg", "jpeg"],
        key="image_uploader"
    )

    if uploaded_image:
        st.image(uploaded_image, use_container_width=True)

    st.markdown("---")

    st.markdown("### 🎤 Voice Input")

    voice_text = speech_to_text(
        language='en',
        start_prompt="🎙️ Start Recording",
        stop_prompt="⏹️ Stop Recording",
        just_once=True,
        use_container_width=True,
        key='voice_input'
    )

# =========================================================
# HEADER
# =========================================================
st.markdown(
    '<div class="main-title">NovaCore AI</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">Premium Multimodal AI Assistant Platform</div>',
    unsafe_allow_html=True
)

# =========================================================
# FEATURE CARDS
# =========================================================
if len(load_chat(st.session_state.current_chat)) == 0:

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="feature-card">
            <h3>🧠 Deep Reasoning</h3>
            <p>Multi-model AI with full conversation memory and context awareness.</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="feature-card">
            <h3>👁️ Vision AI</h3>
            <p>Analyse images, photos and diagrams using Moondream.</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="feature-card">
            <h3>🎤 Voice & Docs</h3>
            <p>Speak your prompts or upload PDF and TXT files as context.</p>
        </div>
        """, unsafe_allow_html=True)

# =========================================================
# LOAD CHAT
# =========================================================
messages = load_chat(st.session_state.current_chat)

# =========================================================
# DISPLAY CHAT
# =========================================================
for message in messages:

    with st.chat_message(message["role"]):

        if message["role"] == "user":
            st.markdown(f"🧑 {message['content']}")
        else:
            st.markdown(f"🤖 {message['content']}")

        if message.get("timestamp"):
            st.caption(message["timestamp"])

# =========================================================
# CHAT INPUT
# =========================================================
user_input = st.chat_input("Message NovaCore AI...")

if voice_text:
    user_input = voice_text

# =========================================================
# GENERATE RESPONSE
# =========================================================
if user_input:

    # Auto-name new chats from the first message
    if st.session_state.current_chat == "New Chat" and len(messages) == 0:
        auto_name = user_input[:40].strip().replace("\n", " ")
        if len(user_input) > 40:
            auto_name += "..."
        st.session_state.current_chat = auto_name

    save_message(
        st.session_state.current_chat,
        "user",
        user_input
    )

    with st.chat_message("user"):
        st.markdown(f"🧑 {user_input}")

    with st.chat_message("assistant"):

        typing_placeholder = st.empty()
        response_placeholder = st.empty()

        typing_placeholder.markdown("""
        <div class="typing-container">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
        """, unsafe_allow_html=True)

        try:

            # =========================================================
            # VISION AI — moondream with image
            # =========================================================
            if model_name == "moondream" and uploaded_image:

                uploaded_image.seek(0)
                image = Image.open(uploaded_image)

                buffered = io.BytesIO()
                image.save(buffered, format="PNG")
                image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

                api_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in messages
                ]
                api_messages.append({
                    "role": "user",
                    "content": user_input,
                    "images": [image_base64]
                })

                response = requests.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": "moondream",
                        "messages": api_messages,
                        "stream": False
                    },
                    timeout=300
                )

                data = response.json()
                full_response = data["message"]["content"]

                typing_placeholder.empty()
                response_placeholder.markdown(f"🤖 {full_response}")

            # =========================================================
            # TEXT MODELS — full conversation history
            # =========================================================
            else:

                doc_context = st.session_state.document_text

                api_messages = []

                if doc_context:
                    api_messages.append({
                        "role": "system",
                        "content": (
                            "The user has uploaded a document for reference. "
                            "Use it when the question relates to it, otherwise answer freely.\n\n"
                            f"{doc_context}"
                        )
                    })

                for m in messages:
                    api_messages.append({"role": m["role"], "content": m["content"]})

                api_messages.append({"role": "user", "content": user_input})

                response = requests.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": model_name,
                        "messages": api_messages,
                        "stream": True
                    },
                    stream=True,
                    timeout=300
                )

                typing_placeholder.empty()

                full_response = ""

                for line in response.iter_lines():

                    if line:

                        data = json.loads(line.decode("utf-8"))
                        token = data.get("message", {}).get("content", "")
                        full_response += token
                        response_placeholder.markdown(full_response + "▌")

                full_response = full_response.replace("▌", "")
                response_placeholder.markdown(f"🤖 {full_response}")

        except Exception as e:

            typing_placeholder.empty()

            err = str(e)
            if "Connection refused" in err or "ConnectionError" in err:
                response_placeholder.error(
                    "❌ Cannot reach Ollama. Make sure it's running: `ollama serve`"
                )
            else:
                response_placeholder.error(f"❌ Error: {err}")

            full_response = f"Error: {err}"

    save_message(
        st.session_state.current_chat,
        "assistant",
        full_response
    )

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
<div class="nova-footer">
    ⚡ <span>NovaCore AI</span> &nbsp;·&nbsp; Powered by Ollama &nbsp;·&nbsp; Built with Streamlit
</div>
""", unsafe_allow_html=True)
