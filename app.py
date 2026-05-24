import streamlit as st
import sqlite3
import requests
import json
import base64
import io
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
    content TEXT
)
""")

conn.commit()

# =========================================================
# FUNCTIONS
# =========================================================
def save_message(chat_name, role, content):

    cursor.execute(
        "INSERT INTO chats (chat_name, role, content) VALUES (?, ?, ?)",
        (chat_name, role, content)
    )

    conn.commit()


def load_chat(chat_name):

    cursor.execute(
        "SELECT role, content FROM chats WHERE chat_name=?",
        (chat_name,)
    )

    rows = cursor.fetchall()

    return [
        {
            "role": row[0],
            "content": row[1]
        }
        for row in rows
    ]


def get_chat_names():

    cursor.execute(
        "SELECT DISTINCT chat_name FROM chats"
    )

    rows = cursor.fetchall()

    names = [row[0] for row in rows]

    if "New Chat" not in names:
        names.insert(0, "New Chat")

    return names

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

.scroll-to-bottom-btn {
    position: fixed;
    bottom: 100px;
    right: 30px;
    width: 46px;
    height: 46px;
    border-radius: 50%;
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    color: white;
    z-index: 9999;
    box-shadow: 0 4px 20px rgba(37,99,235,0.5);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.scroll-to-bottom-btn:hover {
    transform: scale(1.15);
    box-shadow: 0 6px 28px rgba(37,99,235,0.75);
}

</style>
""", unsafe_allow_html=True)

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:

    st.title("⚙️ NovaCore")

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

# =========================================================
# SCROLL TO BOTTOM BUTTON
# =========================================================
st.markdown("""
<button class="scroll-to-bottom-btn"
    title="Jump to latest"
    onclick="
        const el = window.parent.document.querySelector('[data-testid=stAppViewContainer]')
            || window.parent.document.querySelector('.main')
            || window.parent.document.body;
        el.scrollTo({top: el.scrollHeight, behavior: 'smooth'});
    ">
    &#8595;
</button>
""", unsafe_allow_html=True)

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
            # LLAVA VISION AI
            # =========================================================
            if model_name == "moondream" and uploaded_image:

                uploaded_image.seek(0)
                image = Image.open(uploaded_image)

                buffered = io.BytesIO()

                image.save(buffered, format="PNG")

                image_base64 = base64.b64encode(
                    buffered.getvalue()
                ).decode("utf-8")

                response = requests.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": "moondream",
                        "messages": [
                            {
                                "role": "user",
                                "content": user_input,
                                "images": [image_base64]
                            }
                        ],
                        "stream": False
                    },
                    timeout=300
                )

                data = response.json()

                full_response = data["message"]["content"]

                typing_placeholder.empty()

                response_placeholder.markdown(
                    f"🤖 {full_response}"
                )

            # =========================================================
            # TEXT MODELS
            # =========================================================
            else:

                doc_context = st.session_state.document_text
                prompt = (
                    f"The user has uploaded a document for reference. Use it if the question is related to it, otherwise answer freely from your own knowledge.\n\nDocument:\n{doc_context}\n\nUser question: {user_input}"
                    if doc_context else user_input
                )

                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": model_name,
                        "prompt": prompt,
                        "stream": True
                    },
                    stream=True,
                    timeout=300
                )

                typing_placeholder.empty()

                full_response = ""

                for line in response.iter_lines():

                    if line:

                        decoded_line = line.decode("utf-8")

                        data = json.loads(decoded_line)

                        token = data.get("response", "")

                        full_response += token

                        response_placeholder.markdown(
                            full_response + "▌"
                        )

                full_response = full_response.replace("▌", "")

                response_placeholder.markdown(
                    f"🤖 {full_response}"
                )

        except Exception as e:

            typing_placeholder.empty()

            response_placeholder.error(
                f"Error: {str(e)}"
            )

            full_response = str(e)

    save_message(
        st.session_state.current_chat,
        "assistant",
        full_response
    )