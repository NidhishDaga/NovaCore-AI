import streamlit as st
import sqlite3
import json
import base64
import io
import os
import requests as _requests
from urllib.parse import urlencode
from datetime import datetime
from PIL import Image
from PyPDF2 import PdfReader
from streamlit_mic_recorder import speech_to_text
from groq import Groq

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="NovaCore AI",
    page_icon="🧠",
    layout="wide"
)

# =========================================================
# CONSTANTS
# =========================================================
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

TEXT_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    VISION_MODEL,
]

# =========================================================
# LOGO — SVG nova-burst icon (no external files needed)
# =========================================================
def _nova_icon(size: int, uid: str) -> str:
    """Return the NovaCore star-burst as a self-contained inline SVG.
    uid must be unique per page so gradient IDs don't collide."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 100 100">'
        f'<defs>'
        f'<linearGradient id="nlg{uid}" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="#22d3ee"/>'
        f'<stop offset="100%" stop-color="#a855f7"/>'
        f'</linearGradient>'
        f'<radialGradient id="nrg{uid}" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="#22d3ee" stop-opacity="0.22"/>'
        f'<stop offset="100%" stop-color="#a855f7" stop-opacity="0"/>'
        f'</radialGradient>'
        f'<filter id="nfl{uid}" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feGaussianBlur in="SourceGraphic" stdDeviation="2.8" result="b"/>'
        f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        f'</filter>'
        f'</defs>'
        # soft radial glow behind the star
        f'<circle cx="50" cy="50" r="46" fill="url(#nrg{uid})"/>'
        # 8-pointed star: alternating outer (r=45) and inner (r=18) vertices
        f'<polygon '
        f'points="50,5 62.7,37.3 95,50 62.7,62.7 50,95 37.3,62.7 5,50 37.3,37.3" '
        f'fill="url(#nlg{uid})" filter="url(#nfl{uid})"/>'
        # thin outer ring
        f'<circle cx="50" cy="50" r="44" fill="none" stroke="url(#nlg{uid})" stroke-width="0.6" opacity="0.35"/>'
        # bright core
        f'<circle cx="50" cy="50" r="11" fill="white" opacity="0.92"/>'
        f'<circle cx="50" cy="50" r="6.5" fill="url(#nlg{uid})"/>'
        f'</svg>'
    )

# Pre-compute base64 favicon (SVG injected via <link> tag)
_FAV_B64 = base64.b64encode(_nova_icon(64, "fav").encode()).decode()

# =========================================================
# GOOGLE OAUTH — lightweight manual implementation
# No external auth library; uses only `requests` which is
# already in requirements.txt.  Session state holds auth;
# st.query_params.clear() prevents code reuse on reruns.
# =========================================================
_GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USER_URL  = "https://www.googleapis.com/oauth2/v3/userinfo"

def _get_redirect_uri():
    try:
        return st.secrets.get("REDIRECT_URI", "http://localhost:8501")
    except Exception:
        return "http://localhost:8501"

def _get_google_auth_url():
    """Build the Google OAuth consent-screen URL."""
    try:
        client_id = st.secrets["GOOGLE_CLIENT_ID"]
    except KeyError:
        st.error("❌ Missing secret: GOOGLE_CLIENT_ID. Add it in Streamlit Cloud → Settings → Secrets.")
        st.stop()
    params = {
        "client_id":     client_id,
        "redirect_uri":  _get_redirect_uri(),
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
        "prompt":        "select_account",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"

def _exchange_code(code: str):
    """Exchange an OAuth code for user info. Returns (user_dict, error_str)."""
    try:
        client_id     = st.secrets["GOOGLE_CLIENT_ID"]
        client_secret = st.secrets["GOOGLE_CLIENT_SECRET"]
    except KeyError as exc:
        return None, f"Missing secret: {exc}"

    token_resp = _requests.post(_GOOGLE_TOKEN_URL, data={
        "code":          code,
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  _get_redirect_uri(),
        "grant_type":    "authorization_code",
    }, timeout=10)
    token_data = token_resp.json()

    if "error" in token_data:
        return None, token_data.get("error_description", token_data["error"])

    access_token = token_data.get("access_token")
    if not access_token:
        return None, "No access token in response."

    user_resp = _requests.get(
        _GOOGLE_USER_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    user_data = user_resp.json()
    return user_data, None

def _google_logout():
    """Clear all auth-related session state keys."""
    for key in ("connected", "user_info", "_oauth_error"):
        st.session_state.pop(key, None)

# ── Process OAuth callback (runs on every rerun; safe to call repeatedly) ──
_code = st.query_params.get("code")
if _code and not st.session_state.get("connected", False):
    with st.spinner("Signing you in…"):
        _user, _err = _exchange_code(_code)
    # Clear the ?code= from the URL immediately so it can't be reused
    st.query_params.clear()
    if _user and _user.get("email"):
        st.session_state.connected = True
        st.session_state.user_info = {
            "email":   _user["email"],
            "name":    _user.get("name", _user["email"]),
            "picture": _user.get("picture", ""),
        }
        st.session_state.pop("_oauth_error", None)
    else:
        st.session_state.connected = False
        st.session_state["_oauth_error"] = _err or "Authentication failed. Please try again."
    st.rerun()

# =========================================================
# DATABASE
# =========================================================
conn = sqlite3.connect("novacore_memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT,
    chat_name  TEXT,
    role       TEXT,
    content    TEXT,
    timestamp  TEXT DEFAULT ''
)
""")
conn.commit()

# Safe migrations for older DBs
for col, defn in [("timestamp", "TEXT DEFAULT ''"), ("user_email", "TEXT DEFAULT ''")]:
    try:
        cursor.execute(f"ALTER TABLE chats ADD COLUMN {col} {defn}")
        conn.commit()
    except Exception:
        pass

# =========================================================
# FUNCTIONS
# =========================================================
def save_message(user_email, chat_name, role, content):
    cursor.execute(
        "INSERT INTO chats (user_email, chat_name, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_email, chat_name, role, content, datetime.now().strftime("%H:%M"))
    )
    conn.commit()


def load_chat(user_email, chat_name):
    cursor.execute(
        "SELECT role, content, timestamp FROM chats WHERE user_email=? AND chat_name=?",
        (user_email, chat_name)
    )
    rows = cursor.fetchall()
    return [
        {"role": row[0], "content": row[1], "timestamp": row[2] or ""}
        for row in rows
    ]


def get_chat_names(user_email):
    cursor.execute(
        "SELECT DISTINCT chat_name FROM chats WHERE user_email=?",
        (user_email,)
    )
    rows = cursor.fetchall()
    names = [row[0] for row in rows]
    if "New Chat" not in names:
        names.insert(0, "New Chat")
    return names


def rename_chat(user_email, old_name, new_name):
    cursor.execute(
        "UPDATE chats SET chat_name=? WHERE user_email=? AND chat_name=?",
        (new_name, user_email, old_name)
    )
    conn.commit()


def clear_chat(user_email, chat_name):
    cursor.execute(
        "DELETE FROM chats WHERE user_email=? AND chat_name=?",
        (user_email, chat_name)
    )
    conn.commit()


def get_groq_client(api_key):
    return Groq(api_key=api_key)


def classify_error(err: str) -> str:
    e = err.lower()
    if "invalid_api_key" in e or "authentication" in e or "api key" in e or "401" in e:
        return "❌ Invalid API key. Please check your Groq API key in the sidebar."
    if "rate_limit" in e or "429" in e or "quota" in e:
        return "❌ Rate limit reached. Please wait a moment and try again."
    if "connection" in e or "network" in e or "timeout" in e:
        return "❌ Connection error. Please check your internet connection."
    if "model_not_found" in e or "404" in e or "decommissioned" in e:
        return "❌ Model not available. It may have been deprecated by Groq."
    return f"❌ Error: {err}"

# =========================================================
# SESSION STATE
# =========================================================
if "current_chat" not in st.session_state:
    st.session_state.current_chat = "New Chat"

if "document_text" not in st.session_state:
    st.session_state.document_text = ""

# =========================================================
# DESIGN SYSTEM — Deep Space Tech
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

.feature-card h3 { color: #e2e8f0; margin-bottom: 8px; font-size: 18px; }
.feature-card p  { color: rgba(148, 163, 184, 0.85); font-size: 14px; margin: 0; }

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

.nova-footer span { color: rgba(34, 211, 238, 0.5); }

/* ── ALERTS ───────────────────────────────────────── */
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

/* ── API KEY INPUT ────────────────────────────────── */
[data-testid="stTextInput"] input[type="password"] {
    background: rgba(34, 211, 238, 0.05) !important;
    border: 1px solid rgba(34, 211, 238, 0.2) !important;
    color: #e2e8f0 !important;
    border-radius: 10px !important;
}

/* ── LOGIN PAGE ───────────────────────────────────── */
.login-wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 70vh;
    padding: 40px 20px;
}

.login-card {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(34, 211, 238, 0.15);
    border-radius: 28px;
    padding: 52px 48px;
    text-align: center;
    backdrop-filter: blur(20px);
    max-width: 460px;
    width: 100%;
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.4), 0 0 60px rgba(34, 211, 238, 0.05);
}

.login-logo {
    font-size: 56px;
    margin-bottom: 16px;
    filter: drop-shadow(0 0 20px rgba(34, 211, 238, 0.4));
}

.login-title {
    font-size: 38px;
    font-weight: 800;
    letter-spacing: -1px;
    background: linear-gradient(135deg, #22d3ee 0%, #a78bfa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
}

.login-subtitle {
    color: rgba(167, 139, 250, 0.7);
    font-size: 15px;
    margin-bottom: 10px;
}

.login-desc {
    color: rgba(148, 163, 184, 0.7);
    font-size: 13px;
    line-height: 1.6;
    margin-bottom: 32px;
}

.login-divider {
    height: 1px;
    background: rgba(34, 211, 238, 0.08);
    margin: 28px 0;
}

/* Style the Google login link button */
[data-testid="stLinkButton"] a {
    background: linear-gradient(135deg, #0891b2, #6366f1) !important;
    color: white !important;
    border-radius: 14px !important;
    padding: 14px 28px !important;
    font-weight: 700 !important;
    font-size: 15px !important;
    text-decoration: none !important;
    border: 1px solid rgba(34, 211, 238, 0.3) !important;
    display: inline-block !important;
    transition: opacity 0.2s !important;
}

/* ── USER PROFILE CARD ────────────────────────────── */
.user-profile-card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    background: rgba(34, 211, 238, 0.04);
    border: 1px solid rgba(34, 211, 238, 0.12);
    border-radius: 14px;
    margin-bottom: 4px;
}

.user-profile-card img {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: 2px solid rgba(34, 211, 238, 0.35);
}

.user-name  { font-weight: 600; font-size: 14px; color: #e2e8f0; }
.user-email { font-size: 11px; color: rgba(34, 211, 238, 0.55); }

</style>
""", unsafe_allow_html=True)

# Inject SVG favicon (overrides the emoji set in st.set_page_config)
st.markdown(
    f'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,{_FAV_B64}">',
    unsafe_allow_html=True,
)

# =========================================================
# AUTHENTICATION GATE
# =========================================================
if not st.session_state.get("connected", False):

    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:center;
                gap:18px;padding:36px 0 6px;">
        {_nova_icon(72, "lghdr")}
        <div>
            <div class="main-title" style="text-align:left;margin-bottom:2px;">
                NovaCore AI
            </div>
            <div class="subtitle" style="text-align:left;margin-bottom:0;">
                Premium Multimodal AI Assistant Platform
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1, 1.4, 1])
    with col_c:
        st.markdown(f"""
        <div class="login-card">
            <div class="login-logo">{_nova_icon(68, "lgcard")}</div>
            <div class="login-title">Welcome back</div>
            <div class="login-subtitle">Sign in to your personal workspace</div>
            <div class="login-desc">
                Your chats, documents, and AI conversations are
                private and tied to your Google account.
            </div>
            <div class="login-divider"></div>
        </div>
        """, unsafe_allow_html=True)

        st.link_button("🔐  Sign in with Google", _get_google_auth_url(), use_container_width=True)

        # Show a friendly message if a previous auth attempt failed
        if st.session_state.get("_oauth_error"):
            st.warning(f"⚠️ {st.session_state['_oauth_error']}")

    st.markdown("""
    <div class="nova-footer" style="margin-top:60px;">
        ⚡ <span>NovaCore AI</span> &nbsp;·&nbsp; Powered by Groq &nbsp;·&nbsp; Built with Streamlit
    </div>
    """, unsafe_allow_html=True)

    st.stop()

# =========================================================
# USER INFO (only reached when logged in)
# =========================================================
user_email   = st.session_state["user_info"]["email"]
user_name    = st.session_state["user_info"]["name"]
user_picture = st.session_state["user_info"].get("picture", "")

# =========================================================
# RESOLVE GROQ API KEY
# =========================================================
try:
    _secret_key = st.secrets.get("GROQ_API_KEY", "")
except Exception:
    _secret_key = ""

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:

    # ── Sidebar logo ──────────────────────────────────
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;padding:6px 0 14px;">
        {_nova_icon(32, "sblogo")}
        <span style="font-size:17px;font-weight:800;letter-spacing:-0.4px;
                     background:linear-gradient(135deg,#22d3ee,#a855f7);
                     -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
            NovaCore AI
        </span>
    </div>
    """, unsafe_allow_html=True)

    # ── User profile ──────────────────────────────────
    if user_picture:
        st.markdown(f"""
        <div class="user-profile-card">
            <img src="{user_picture}" alt="avatar">
            <div>
                <div class="user-name">{user_name}</div>
                <div class="user-email">{user_email}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="user-profile-card">
            <div style="width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#0891b2,#6366f1);display:flex;align-items:center;justify-content:center;font-size:18px;">
                {user_name[0].upper()}
            </div>
            <div>
                <div class="user-name">{user_name}</div>
                <div class="user-email">{user_email}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    if st.button("🚪 Logout", use_container_width=True):
        _google_logout()
        st.rerun()

    st.markdown("---")

    # ── Groq API key ──────────────────────────────────
    st.markdown("### 🔑 Groq API Key")

    if _secret_key:
        api_key = _secret_key
        st.success("🔒 API Key configured via Secrets")
    else:
        api_key_input = st.text_input(
            "",
            type="password",
            placeholder="gsk_...",
            help="Get your free key at console.groq.com",
            key="groq_api_key_input"
        )
        api_key = api_key_input.strip() if api_key_input else ""
        if api_key:
            st.success("🟢 API Key set")
        else:
            st.error("🔴 No API key — enter one above")

    st.markdown("---")

    # ── Chat management ───────────────────────────────
    if st.button("➕ New Chat", use_container_width=True):
        new_name = f"Chat_{len(get_chat_names(user_email)) + 1}"
        st.session_state.current_chat = new_name
        st.rerun()

    st.markdown("### 💬 Chats")

    chat_names = get_chat_names(user_email)

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
            rename_chat(user_email, st.session_state.current_chat, new_chat_name)
            st.session_state.current_chat = new_chat_name
            st.rerun()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🗑️ Clear", use_container_width=True):
            clear_chat(user_email, st.session_state.current_chat)
            st.rerun()

    with col2:
        if st.button("❌ Delete", use_container_width=True):
            clear_chat(user_email, st.session_state.current_chat)
            st.session_state.current_chat = "New Chat"
            st.rerun()

    export_msgs = load_chat(user_email, st.session_state.current_chat)
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

    # ── Model selection ───────────────────────────────
    st.markdown("### 🤖 Active Model")

    model_name = st.radio(
        "",
        TEXT_MODELS,
        format_func=lambda m: {
            "llama-3.3-70b-versatile":                     "🦙 LLaMA 3.3 70B",
            "llama-3.1-8b-instant":                        "⚡ LLaMA 3.1 8B",
            "openai/gpt-oss-120b":                         "🧠 GPT OSS 120B",
            "openai/gpt-oss-20b":                          "🤖 GPT OSS 20B",
            VISION_MODEL:                                  "👁️ LLaMA 4 Scout (Vision)",
        }.get(m, m)
    )

    st.success(f"🟢 {model_name} Active")

    st.markdown("---")

    # ── File uploads ──────────────────────────────────
    st.markdown("### 📄 Upload PDF/TXT")

    uploaded_file = st.file_uploader("", type=["pdf", "txt"])

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
        "", type=["png", "jpg", "jpeg"], key="image_uploader"
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
st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:center;
            gap:20px;padding:16px 0 4px;">
    {_nova_icon(76, "mainhdr")}
    <div>
        <div class="main-title" style="text-align:left;margin-bottom:2px;">
            NovaCore AI
        </div>
        <div class="subtitle" style="text-align:left;margin-bottom:0;">
            Premium Multimodal AI Assistant Platform
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================================================
# API KEY GATE
# =========================================================
if not api_key:
    st.markdown("""
    <div style="
        text-align:center; padding:60px 20px;
        background:rgba(34,211,238,0.04);
        border:1px solid rgba(34,211,238,0.12);
        border-radius:24px; margin-top:20px;">
        <div style="font-size:48px;margin-bottom:16px;">🔑</div>
        <h2 style="color:#22d3ee;margin-bottom:10px;">API Key Required</h2>
        <p style="color:#94a3b8;font-size:16px;max-width:440px;margin:0 auto;">
            Enter your <strong style="color:#e2e8f0;">Groq API key</strong> in the sidebar to start chatting.<br><br>
            Get a free key at <a href="https://console.groq.com" target="_blank" style="color:#22d3ee;">console.groq.com</a>
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# =========================================================
# FEATURE CARDS (empty chat only)
# =========================================================
if len(load_chat(user_email, st.session_state.current_chat)) == 0:

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
            <p>Analyse images and photos — select the LLaMA 4 Scout Vision model.</p>
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
# LOAD & DISPLAY CHAT
# =========================================================
messages = load_chat(user_email, st.session_state.current_chat)

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

    save_message(user_email, st.session_state.current_chat, "user", user_input)

    with st.chat_message("user"):
        st.markdown(f"🧑 {user_input}")

    with st.chat_message("assistant"):

        typing_placeholder  = st.empty()
        response_placeholder = st.empty()

        typing_placeholder.markdown("""
        <div class="typing-container">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
        """, unsafe_allow_html=True)

        full_response = ""

        try:
            client = get_groq_client(api_key)

            # ── Vision AI ────────────────────────────────
            if model_name == VISION_MODEL and uploaded_image:

                uploaded_image.seek(0)
                image = Image.open(uploaded_image)
                buffered = io.BytesIO()
                image.save(buffered, format="PNG")
                image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

                vision_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in messages
                ]
                vision_messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_input},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                    ]
                })

                response = client.chat.completions.create(
                    model=VISION_MODEL,
                    messages=vision_messages,
                    max_tokens=1024
                )

                full_response = response.choices[0].message.content
                typing_placeholder.empty()
                response_placeholder.markdown(f"🤖 {full_response}")

            # ── Text models with streaming ────────────────
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

                stream = client.chat.completions.create(
                    model=model_name,
                    messages=api_messages,
                    stream=True
                )

                typing_placeholder.empty()

                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_response += delta.content
                        response_placeholder.markdown(full_response + "▌")

                full_response = full_response.replace("▌", "")
                response_placeholder.markdown(f"🤖 {full_response}")

        except Exception as e:
            typing_placeholder.empty()
            response_placeholder.error(classify_error(str(e)))
            full_response = f"Error: {e}"

    save_message(user_email, st.session_state.current_chat, "assistant", full_response)

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
<div class="nova-footer">
    ⚡ <span>NovaCore AI</span> &nbsp;·&nbsp; Powered by Groq &nbsp;·&nbsp; Built with Streamlit
</div>
""", unsafe_allow_html=True)
