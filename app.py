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

# Safe migration: add timestamp to existing databases without it
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
# PREMIUM CSS
# =========================================================
st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background: linear-gradient(135deg,#020617 0%,#0f172a 100%);
    color: white;
}

.block-container {
    max-width: 1250px;
    padding-top: 1rem;
}

section[data-testid="stSidebar"] {
    background: rgba(10,15,30,0.85);
    backdrop-filter: blur(24px);
    border-right: 1px solid rgba(255,255,255,0.08);
}

.main-title {
    text-align: center;
    font-size: 70px;
    font-weight: 800;
    background: linear-gradient(90deg,#ffffff,#60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0;
}

.subtitle {
    text-align: center;
    color: #94a3b8;
    margin-bottom: 30px;
    font-size: 18px;
}

.stChatInput textarea {
    background: rgba(255,255,255,0.97) !important;
    color: black !important;
    border-radius: 20px !important;
    padding: 16px !important;
    font-size: 16px !important;
    outline: none !important;
    box-shadow: none !important;
}

.stChatInput textarea::placeholder {
    color: #444 !important;
}

:root {
    --primary-color: #2563eb !important;
}

.stChatInputContainer,
[data-testid="stChatInputContainer"],
div[class*="chatInput"] {
    border: 1px solid rgba(255,255,255,0.08) !important;
    outline: none !important;
    box-shadow: none !important;
}

.stChatInputContainer:focus-within,
[data-testid="stChatInputContainer"]:focus-within {
    border: 1px solid rgba(96,165,250,0.3) !important;
    outline: none !important;
    box-shadow: none !important;
}

.stButton button {
    background: linear-gradient(135deg,#2563eb,#1d4ed8) !important;
    color: white !important;
    border-radius: 14px !important;
    border: none !important;
    font-weight: 700 !important;
}

[data-testid="stChatMessage"] {
    background: rgba(255,255,255,0.04);
    border-radius: 20px;
    padding: 14px;
    border: 1px solid rgba(255,255,255,0.06);
    backdrop-filter: blur(18px);
}

.typing-container {
    display: flex;
    align-items: center;
    width: 85px;
    height: 42px;
    padding: 0 15px;
    border-radius: 30px;
    background: rgba(255,255,255,0.08);
    backdrop-filter: blur(18px);
}

.typing-dot {
    width: 8px;
    height: 8px;
    margin: 0 4px;
    border-radius: 50%;
    background: white;
    animation: bounce 1.2s infinite ease-in-out;
}

.typing-dot:nth-child(1) { animation-delay: 0s; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
    0%,80%,100% {
        transform: translateY(0px);
        opacity: 0.5;
    }
    40% {
        transform: translateY(-7px);
        opacity: 1;
    }
}

.feature-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    padding: 18px;
    border-radius: 20px;
    text-align: center;
    backdrop-filter: blur(12px);
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

    temperature = st.slider(
        "🌡️ Temperature",
        min_value=0.0,
        max_value=1.5,
        value=0.7,
        step=0.1,
        help="Higher = more creative. Lower = more focused and precise."
    )

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
            <h3>🧠 DeepSeek AI</h3>
            <p>Advanced reasoning and problem solving.</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="feature-card">
            <h3>👁️ Vision AI</h3>
            <p>Analyze images using Moondream.</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="feature-card">
            <h3>🎤 Voice Assistant</h3>
            <p>Speak naturally using voice input.</p>
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
                        "stream": False,
                        "options": {"temperature": temperature}
                    },
                    timeout=300
                )

                data = response.json()
                full_response = data["message"]["content"]

                typing_placeholder.empty()
                response_placeholder.markdown(f"🤖 {full_response}")

            # =========================================================
            # TEXT MODELS — with full conversation history
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
                        "stream": True,
                        "options": {"temperature": temperature}
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
