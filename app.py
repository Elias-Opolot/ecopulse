import streamlit as st
from groq import Groq
from supabase import create_client, Client
import pandas as pd
import base64
import hashlib
import requests
from datetime import datetime

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="EcoPulse",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Clients ────────────────────────────────────────────────────────────────────
groq_client  = Groq(api_key=st.secrets["GROQ_API_KEY"])
supa: Client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
SECRET_KEY   = st.secrets.get("CHAT_SECRET", "ecopulse-ccic-2026")

# ── Encryption ─────────────────────────────────────────────────────────────────
def encrypt_message(text: str) -> str:
    key_bytes = (SECRET_KEY * ((len(text) // len(SECRET_KEY)) + 1)).encode()[:len(text)]
    encrypted = bytes([ord(c) ^ k for c, k in zip(text, key_bytes)])
    return base64.b64encode(encrypted).decode()

def decrypt_message(token: str) -> str:
    try:
        encrypted = base64.b64decode(token.encode())
        key_bytes = (SECRET_KEY * ((len(encrypted) // len(SECRET_KEY)) + 1)).encode()[:len(encrypted)]
        return bytes([b ^ k for b, k in zip(encrypted, key_bytes)]).decode()
    except:
        return "[encrypted message]"

def hash_password(pw: str) -> str:
    return hashlib.sha256((pw + SECRET_KEY).encode()).hexdigest()

# ── Supabase helpers ───────────────────────────────────────────────────────────
def db_register(username, password, full_name, phone, district, role):
    try:
        existing = supa.table("users").select("username").eq("username", username).execute()
        if existing.data:
            return False, "Username already taken."
        supa.table("users").insert({
            "username":      username,
            "password_hash": hash_password(password),
            "full_name":     full_name,
            "phone":         phone,
            "district":      district,
            "role":          role,
            "joined":        datetime.now().strftime("%d %b %Y"),
        }).execute()
        return True, "Success"
    except Exception as e:
        return False, str(e)

def db_login(username, password):
    try:
        result = supa.table("users").select("*").eq("username", username).execute()
        if not result.data:
            return False, None, "Username not found."
        user = result.data[0]
        if user["password_hash"] == hash_password(password):
            return True, user, "Success"
        return False, None, "Wrong password."
    except Exception as e:
        return False, None, str(e)

def db_save_message(room, sender, display_name, encrypted_text):
    try:
        supa.table("chat_messages").insert({
            "room":           room,
            "sender":         sender,
            "display_name":   display_name,
            "encrypted_text": encrypted_text,
            "msg_time":       datetime.now().strftime("%H:%M"),
            "msg_date":       datetime.now().strftime("%d %b %Y"),
        }).execute()
        return True
    except Exception as e:
        return False

def db_get_messages(room, limit=50):
    try:
        result = supa.table("chat_messages").select("*").eq("room", room).order("created_at").limit(limit).execute()
        return result.data or []
    except:
        return []

# ── Groq AI helpers ────────────────────────────────────────────────────────────
def ask_groq(system_prompt, user_message, history=None):
    try:
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for m in history[-6:]:
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_message})
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=1200,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

def ask_groq_vision(system_prompt, user_message, image_base64, image_type="image/jpeg"):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{image_type};base64,{image_base64}"}},
                    {"type": "text", "text": user_message}
                ]}
            ],
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing image: {str(e)}"

def get_realtime_info(query):
    """Use Groq with web-aware prompt to get current Uganda agriculture/climate info"""
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": """You are an expert on Uganda agriculture, climate, and environment.
                Answer with the most current and accurate information available up to your knowledge cutoff.
                Be specific about Uganda regions, current seasons, market prices, and climate conditions.
                Always mention if something might have changed recently."""},
                {"role": "user", "content": f"Give me the latest information about: {query}\nFocus on Uganda 2025-2026 context."}
            ],
            max_tokens=1200,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

def generate_farm_image_prompt(description):
    """Generate a detailed image prompt using AI, then fetch image from Pollinations"""
    try:
        # Step 1: Generate a good image prompt using Groq
        prompt_response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"Create a detailed, vivid image generation prompt for: {description}. Focus on Ugandan farming context. Keep it under 100 words. Do not include any harmful content."}],
            max_tokens=150,
        )
        image_prompt = prompt_response.choices[0].message.content.strip()

        # Step 2: Use Pollinations.ai (free, no API key needed)
        encoded_prompt = requests.utils.quote(image_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
        return image_url, image_prompt
    except Exception as e:
        return None, str(e)

# ── Session state ──────────────────────────────────────────────────────────────
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "farm_messages" not in st.session_state:
    st.session_state.farm_messages = [
        {"role": "assistant", "content": "Hello! I'm your AI Farm Advisor 🌾\n\nI can:\n• Answer farming questions with real-time Uganda context\n• Analyze photos of your crops, soil or pests\n• Generate farm visualisation images\n• Give up-to-date climate and market info"}
    ]
if "listings" not in st.session_state:
    st.session_state.listings = [
        {"title":"Organic Compost — 50kg bags","seller":"Kakooza Farms","phone":"+256 772 123456","location":"Wakiso","district":"Wakiso","price":"UGX 25,000","type":"sell","tag":"Waste-to-Value","description":"High quality organic compost made from food waste.","image":None},
        {"title":"Solar Water Pump — rental","seller":"GreenTech Hub","phone":"+256 701 234567","location":"Kampala","district":"Kampala","price":"UGX 15,000/day","type":"sell","tag":"Clean Energy","description":"Portable solar-powered water pump for irrigation.","image":None},
        {"title":"Wanted: Crop Residue (Maize stalks)","seller":"BioGas Uganda","phone":"+256 754 345678","location":"Jinja","district":"Jinja","price":"UGX 8,000/bale","type":"buy","tag":"Circular Economy","description":"We buy maize stalks and crop residues in bulk for biogas production.","image":None},
        {"title":"Surplus Tomatoes — urgent sale","seller":"Nakato Agri","phone":"+256 782 456789","location":"Mbarara","district":"Mbarara","price":"UGX 10,000/crate","type":"sell","tag":"Fresh Produce","description":"Fresh tomatoes harvested this week. Bulk discount available.","image":None},
    ]
if "active_room" not in st.session_state:
    st.session_state.active_room = "general"

# ── Data ───────────────────────────────────────────────────────────────────────
WASTE_CATEGORIES = [
    {"name":"Organic / Food Waste","icon":"🍌","color":"#4CAF50","tip":"Compost food scraps into rich soil fertilizer for farms."},
    {"name":"Plastic","icon":"🧴","color":"#2196F3","tip":"Rinse and take to a recycling point near you."},
    {"name":"Electronic Waste","icon":"📱","color":"#9C27B0","tip":"Never dump e-waste. Find certified e-waste collectors."},
    {"name":"Agricultural Waste","icon":"🌿","color":"#FF9800","tip":"Convert crop residues to biochar or biogas — both profitable!"},
    {"name":"Paper & Cardboard","icon":"📦","color":"#795548","tip":"Separate and dry before recycling."},
    {"name":"Glass","icon":"🍶","color":"#00BCD4","tip":"Reuse clean bottles or return them to manufacturers."},
]
CLIMATE_DATA = {
    "Month":["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
    "Rainfall (mm)":[48,62,130,178,142,72,55,88,110,155,148,82],
    "Avg Temp (°C)":[26,27,26,25,24,23,22,23,24,24,25,26],
}
ALERTS = [
    {"level":"warning","region":"Central","text":"Heavy rains expected — delay planting by 5–7 days."},
    {"level":"info","region":"North East","text":"Dry spell forecast in Karamoja. Activate water conservation measures."},
    {"level":"success","region":"Western","text":"Optimal planting window open for beans & maize this season."},
]
CHAT_ROOMS = {
    "general":        {"name":"🌍 General",        "desc":"Open discussion for all farmers"},
    "agriculture":    {"name":"🌾 Agriculture",     "desc":"Crop advice, planting, harvesting"},
    "waste_trading":  {"name":"♻️ Waste Trading",   "desc":"Buy & sell agricultural waste"},
    "climate_alerts": {"name":"🌦️ Climate Alerts", "desc":"Share local weather updates"},
}

# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;600;800&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;background-color:#0a0f0a;color:#e8f5e9;}
.stApp{background:#0a0f0a;}
h1,h2,h3{font-family:'Playfair Display',serif!important;}
.hero-box{background:linear-gradient(135deg,#0a2016,#1a4731 50%,#0d2137);border-radius:20px;padding:32px 28px;margin-bottom:24px;border:1px solid rgba(76,175,80,0.2);}
.hero-title{font-family:'Playfair Display',serif;font-size:2.2rem;font-weight:900;color:#fff;margin:0 0 8px;line-height:1.2;}
.hero-accent{color:#81C784;}
.hero-sub{font-size:1rem;color:#a8d5b5;margin:0 0 16px;line-height:1.6;}
.badge{display:inline-block;padding:4px 12px;border-radius:8px;font-family:'Space Mono',monospace;font-size:0.7rem;font-weight:700;margin-right:6px;}
.badge-green{background:rgba(76,175,80,0.2);border:1px solid rgba(76,175,80,0.4);color:#81C784;}
.badge-blue{background:rgba(33,150,243,0.2);border:1px solid rgba(33,150,243,0.4);color:#64B5F6;}
.badge-orange{background:rgba(255,152,0,0.2);border:1px solid rgba(255,152,0,0.4);color:#FFB74D;}
.badge-purple{background:rgba(156,39,176,0.2);border:1px solid rgba(156,39,176,0.4);color:#CE93D8;}
.badge-live{background:rgba(76,175,80,0.15);border:1px solid rgba(76,175,80,0.3);color:#81C784;}
.section-label{font-family:'Space Mono',monospace;font-size:0.7rem;letter-spacing:3px;text-transform:uppercase;color:#81C784;margin-bottom:4px;}
.card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:20px;margin-bottom:12px;}
.card-green{border-color:rgba(76,175,80,0.25);}
.card-blue{border-color:rgba(33,150,243,0.25);}
.card-orange{border-color:rgba(255,152,0,0.25);}
.card-purple{border-color:rgba(156,39,176,0.25);}
.alert-warning{background:rgba(255,152,0,0.1);border:1px solid rgba(255,152,0,0.3);border-radius:10px;padding:12px 16px;margin-bottom:10px;}
.alert-info{background:rgba(33,150,243,0.1);border:1px solid rgba(33,150,243,0.3);border-radius:10px;padding:12px 16px;margin-bottom:10px;}
.alert-success{background:rgba(76,175,80,0.1);border:1px solid rgba(76,175,80,0.3);border-radius:10px;padding:12px 16px;margin-bottom:10px;}
.alert-text{color:#e8f5e9;font-size:0.88rem;line-height:1.6;}
.alert-region{font-family:'Space Mono',monospace;font-size:0.65rem;letter-spacing:1px;font-weight:700;margin-bottom:4px;}
.market-card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:14px;padding:0;margin-bottom:16px;overflow:hidden;}
.market-body{padding:14px 16px;}
.market-title{font-size:0.95rem;font-weight:800;color:#fff;margin-bottom:4px;}
.market-meta{font-size:0.78rem;color:#90A4AE;margin-bottom:8px;}
.market-price{font-family:'Space Mono',monospace;font-size:1rem;font-weight:700;color:#FFB74D;}
.market-tag{display:inline-block;background:rgba(255,183,77,0.15);color:#FFB74D;font-size:0.7rem;padding:2px 8px;border-radius:4px;margin-left:8px;}
.sell-badge{background:rgba(76,175,80,0.2);color:#81C784;font-size:0.65rem;font-weight:700;padding:3px 8px;border-radius:6px;float:right;font-family:'Space Mono',monospace;}
.buy-badge{background:rgba(33,150,243,0.2);color:#64B5F6;font-size:0.65rem;font-weight:700;padding:3px 8px;border-radius:6px;float:right;font-family:'Space Mono',monospace;}
.seller-info{background:rgba(76,175,80,0.06);border-top:1px solid rgba(76,175,80,0.15);padding:10px 16px;font-size:0.78rem;color:#a8d5b5;}
.verified-badge{display:inline-block;background:rgba(76,175,80,0.2);color:#81C784;font-size:0.65rem;font-weight:700;padding:2px 7px;border-radius:4px;margin-left:6px;font-family:'Space Mono',monospace;}
.chat-user{background:linear-gradient(135deg,#2d7a4f,#1a4731);border-radius:16px 16px 4px 16px;padding:10px 14px;margin:6px 0 6px auto;max-width:80%;font-size:0.9rem;color:#e8f5e9;line-height:1.6;}
.chat-ai{background:rgba(255,255,255,0.06);border:1px solid rgba(168,230,191,0.2);border-radius:16px 16px 16px 4px;padding:10px 14px;margin:6px auto 6px 0;max-width:85%;font-size:0.9rem;color:#e8f5e9;line-height:1.6;white-space:pre-wrap;}
.msg-bubble-me{background:linear-gradient(135deg,#1a4731,#2d7a4f);border-radius:16px 16px 4px 16px;padding:10px 14px;margin:4px 0 4px auto;max-width:75%;font-size:0.88rem;color:#e8f5e9;line-height:1.5;}
.msg-bubble-other{background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.1);border-radius:16px 16px 16px 4px;padding:10px 14px;margin:4px auto 4px 0;max-width:75%;font-size:0.88rem;color:#e8f5e9;line-height:1.5;}
.msg-name{font-size:0.68rem;font-weight:700;color:#81C784;font-family:'Space Mono',monospace;margin-bottom:3px;}
.msg-time{font-size:0.62rem;color:#546E7A;margin-top:3px;text-align:right;}
.auth-box{background:rgba(255,255,255,0.03);border:1px solid rgba(76,175,80,0.2);border-radius:20px;padding:32px;max-width:500px;margin:0 auto;}
.image-tip{background:rgba(33,150,243,0.08);border:1px solid rgba(33,150,243,0.2);border-radius:10px;padding:10px 14px;font-size:0.8rem;color:#90CAF9;margin-bottom:12px;}
.quote-box{background:rgba(76,175,80,0.06);border:1px solid rgba(76,175,80,0.15);border-radius:14px;padding:18px 20px;margin-top:20px;}
.realtime-box{background:rgba(33,150,243,0.06);border:1px solid rgba(33,150,243,0.2);border-radius:14px;padding:16px;margin-bottom:16px;}
.stTextInput>div>div>input{background:rgba(255,255,255,0.05)!important;border:1px solid rgba(168,230,191,0.2)!important;border-radius:10px!important;color:#e8f5e9!important;}
.stButton>button{background:linear-gradient(135deg,#2d7a4f,#4CAF50)!important;border:none!important;border-radius:10px!important;color:#fff!important;font-weight:700!important;font-family:'DM Sans',sans-serif!important;}
div[data-testid="stTabs"] button{color:#81C784!important;font-family:'DM Sans',sans-serif!important;font-weight:700!important;}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# AUTH SCREEN
# ══════════════════════════════════════════════════════════════════════════════
def show_auth():
    st.markdown("""
    <div style="text-align:center;margin-bottom:28px;">
        <h1 style="font-family:'Playfair Display',serif;color:#81C784;font-size:2.4rem;margin:0;">🌍 EcoPulse</h1>
        <p style="font-family:'Space Mono',monospace;font-size:0.65rem;color:#4CAF50;letter-spacing:2px;">ELIAS CREATIONS</p>
        <p style="color:#90A4AE;font-size:0.85rem;margin-top:8px;">Uganda's AI-powered green revolution platform</p>
    </div>
    """, unsafe_allow_html=True)

    auth_tab1, auth_tab2 = st.tabs(["🔑 Sign In", "📝 Register"])

    with auth_tab1:
        st.markdown("<div class='auth-box'>", unsafe_allow_html=True)
        st.markdown("<p class='section-label'>SIGN IN TO ECOPULSE</p>", unsafe_allow_html=True)
        login_user = st.text_input("Username", placeholder="Enter your username", key="login_user")
        login_pass = st.text_input("Password", placeholder="Enter your password", type="password", key="login_pass")
        if st.button("Sign In →", key="signin_btn"):
            uname = login_user.strip().lower()
            if not uname or not login_pass:
                st.warning("Please enter username and password.")
            else:
                with st.spinner("Signing in…"):
                    success, user, msg = db_login(uname, login_pass)
                if success:
                    st.session_state.current_user = uname
                    st.session_state.user_data    = user
                    st.success(f"Welcome back, {user['full_name']}! 🌱")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
        <div style="background:rgba(76,175,80,0.06);border:1px solid rgba(76,175,80,0.15);border-radius:10px;padding:10px 14px;font-size:0.78rem;color:#81C784;">
        💡 New user? Click the <b>Register</b> tab to create your free account.
        </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with auth_tab2:
        st.markdown("<div class='auth-box'>", unsafe_allow_html=True)
        st.markdown("<p class='section-label'>CREATE YOUR FREE ACCOUNT</p>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            reg_fname    = st.text_input("Full Name *",      placeholder="e.g. Nakato Sarah",    key="reg_fname")
            reg_username = st.text_input("Username *",       placeholder="e.g. nakato_sarah",    key="reg_uname")
            reg_phone    = st.text_input("Phone Number *",   placeholder="+256 7XX XXXXXX",      key="reg_phone")
        with col2:
            reg_district = st.text_input("District *",       placeholder="e.g. Wakiso",          key="reg_district")
            reg_role     = st.selectbox("I am a *",          ["Farmer","Agri-business","Recycler","Student","Other"], key="reg_role")
            reg_pass     = st.text_input("Password *",       type="password", placeholder="Min 6 characters", key="reg_pass")
        reg_pass2 = st.text_input("Confirm Password *", type="password", placeholder="Repeat password", key="reg_pass2")
        if st.button("Create Account →", key="register_btn"):
            uname = reg_username.strip().lower().replace(" ", "_")
            if not all([reg_fname, reg_username, reg_phone, reg_district, reg_pass, reg_pass2]):
                st.warning("⚠️ Please fill in all required fields.")
            elif len(reg_pass) < 6:
                st.error("❌ Password must be at least 6 characters.")
            elif reg_pass != reg_pass2:
                st.error("❌ Passwords do not match.")
            else:
                with st.spinner("Creating your account…"):
                    success, msg = db_register(uname, reg_pass, reg_fname, reg_phone, reg_district, reg_role)
                if success:
                    _, user, _ = db_login(uname, reg_pass)
                    st.session_state.current_user = uname
                    st.session_state.user_data    = user
                    st.success(f"✅ Account created! Welcome, {reg_fname}! 🌱")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")
        st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
def show_main_app():
    user      = st.session_state.current_user
    user_data = st.session_state.user_data

    # ── Header ──────────────────────────────────────────────────────────────────
    col_logo, col_user, col_out = st.columns([4, 2, 1])
    with col_logo:
        st.markdown("<h1 style='font-family:Playfair Display,serif;color:#81C784;margin:0;font-size:1.8rem;'>🌍 EcoPulse</h1>", unsafe_allow_html=True)
        st.markdown("<p style='font-family:Space Mono,monospace;font-size:0.65rem;color:#4CAF50;letter-spacing:2px;margin:0;'>ELIAS CREATION</p>", unsafe_allow_html=True)
    with col_user:
        st.markdown(f"""
        <div style="text-align:right;margin-top:8px;">
            <div style="font-size:0.8rem;font-weight:700;color:#81C784;">👤 {user_data['full_name']}</div>
            <div style="font-size:0.68rem;color:#546E7A;font-family:'Space Mono',monospace;">{user_data['role']} · {user_data['district']}</div>
        </div>""", unsafe_allow_html=True)
    with col_out:
        if st.button("Sign Out"):
            st.session_state.current_user = None
            st.session_state.user_data    = None
            st.rerun()

    st.markdown("<hr style='border-color:rgba(76,175,80,0.15);margin:10px 0 20px;'>", unsafe_allow_html=True)

    tab_home, tab_farm, tab_waste, tab_climate, tab_market, tab_chat = st.tabs([
        "🏠 Home", "🌾 Farm AI", "♻️ Waste Guide", "🌦️ Climate", "🤝 Marketplace", "💬 Farmer Chat"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # HOME
    # ══════════════════════════════════════════════════════════════════════════
    with tab_home:
        st.markdown(f"""
        <div class="hero-box">
            <p class="section-label">CCIC 2026 — Track 2: Climate Tech & Digital Innovation</p>
            <h1 class="hero-title">Welcome back,<br><span class="hero-accent">{user_data['full_name'].split()[0]}</span> 👋</h1>
            <p class="hero-sub">AI-powered tools for climate-resilient agriculture, circular waste management & green enterprise — all in one platform.</p>
            <span class="badge badge-green">🌾 AgriAI</span>
            <span class="badge badge-blue">♻️ Waste</span>
            <span class="badge badge-orange">🤝 Market</span>
            <span class="badge badge-purple">💬 Chat</span>
        </div>""", unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("""
            <div class="card card-green"><div style="font-size:2rem;margin-bottom:8px;">🌾</div>
            <div style="font-weight:800;color:#fff;margin-bottom:6px;">Farm AI Advisor</div>
            <div style="color:#90A4AE;font-size:0.82rem;line-height:1.6;">AI guidance on crops, soil, pests. Upload photos for diagnosis. Generate farm visualisations. Real-time Uganda info.</div>
            <div style="color:#81C784;font-size:0.75rem;margin-top:10px;font-family:'Space Mono',monospace;">→ Open Farm AI tab</div></div>
            <div class="card card-blue"><div style="font-size:2rem;margin-bottom:8px;">🌦️</div>
            <div style="font-weight:800;color:#fff;margin-bottom:6px;">Climate Dashboard</div>
            <div style="color:#90A4AE;font-size:0.82rem;line-height:1.6;">Rainfall trends, temperature data & real-time regional climate alerts for Uganda.</div>
            <div style="color:#64B5F6;font-size:0.75rem;margin-top:10px;font-family:'Space Mono',monospace;">→ Open Climate tab</div></div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown("""
            <div class="card card-orange"><div style="font-size:2rem;margin-bottom:8px;">🤝</div>
            <div style="font-weight:800;color:#fff;margin-bottom:6px;">Green Marketplace</div>
            <div style="color:#90A4AE;font-size:0.82rem;line-height:1.6;">Post products with photos & verified seller details for full traceability.</div>
            <div style="color:#FFB74D;font-size:0.75rem;margin-top:10px;font-family:'Space Mono',monospace;">→ Open Marketplace tab</div></div>
            <div class="card card-purple"><div style="font-size:2rem;margin-bottom:8px;">💬</div>
            <div style="font-weight:800;color:#fff;margin-bottom:6px;">Encrypted Farmer Chat</div>
            <div style="color:#90A4AE;font-size:0.82rem;line-height:1.6;">End-to-end encrypted group chats. Connect with farmers, share tips & trade leads securely.</div>
            <div style="color:#CE93D8;font-size:0.75rem;margin-top:10px;font-family:'Space Mono',monospace;">→ Open Farmer Chat tab</div></div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div class="quote-box">
            <p class="section-label">THEME 2026</p>
            <p style="font-family:'Playfair Display',serif;font-style:italic;color:#c8e6c9;font-size:1rem;line-height:1.7;margin:6px 0;">
            "Empowering Farmers on smart farming"</p>
            <p style="color:#66BB6A;font-size:0.8rem;margin:0;">ELIAS CREATIONS</p>
        </div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FARM AI — with vision, image generation, real-time info
    # ══════════════════════════════════════════════════════════════════════════
    with tab_farm:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1a4731,#2d7a4f);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
            <p class="section-label" style="color:#a8e6bf;">AI-POWERED · REAL-TIME · IMAGE GENERATION</p>
            <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">🌾 Farm Advisory</h2>
            <p style="color:#a8e6bf;font-size:0.82rem;margin:0;">Ask questions · Upload crop photos · Generate farm images · Get real-time Uganda info</p>
        </div>""", unsafe_allow_html=True)

        farm_sub1, farm_sub2, farm_sub3 = st.tabs(["💬 Ask AI", "📷 Photo Diagnosis", "🎨 Generate Image"])

        # ── ASK AI ──────────────────────────────────────────────────────────────
        with farm_sub1:
            st.markdown("<p class='section-label' style='margin-bottom:8px;'>💬 CHAT WITH FARM ADVISOR</p>", unsafe_allow_html=True)

            # Real-time info button
            col_rt1, col_rt2 = st.columns(2)
            with col_rt1:
                if st.button("🌍 Get Real-Time Uganda Farming News"):
                    with st.spinner("Fetching latest Uganda farming info…"):
                        info = get_realtime_info("current farming season, crop prices, and weather conditions in Uganda 2026")
                    st.session_state.farm_messages.append({"role": "user",      "content": "What is the latest farming news and conditions in Uganda right now?"})
                    st.session_state.farm_messages.append({"role": "assistant", "content": f"🌍 Real-Time Uganda Update:\n\n{info}"})
                    st.rerun()
            with col_rt2:
                if st.button("📈 Current Uganda Crop Market Prices"):
                    with st.spinner("Getting current market prices…"):
                        prices = get_realtime_info("current market prices for maize, beans, tomatoes, coffee, and other major crops in Uganda 2025-2026")
                    st.session_state.farm_messages.append({"role": "user",      "content": "What are the current crop market prices in Uganda?"})
                    st.session_state.farm_messages.append({"role": "assistant", "content": f"📈 Uganda Crop Market Prices:\n\n{prices}"})
                    st.rerun()

            # Chat history
            for msg in st.session_state.farm_messages:
                if msg["role"] == "assistant":
                    st.markdown(f"<div class='chat-ai'>🤖 {msg['content']}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='chat-user'>👤 {msg['content']}</div>", unsafe_allow_html=True)

            with st.form("farm_form", clear_on_submit=True):
                user_input = st.text_input("", placeholder="e.g. What crops should I plant now in Central Uganda?", label_visibility="collapsed")
                submitted  = st.form_submit_button("Send ↑")

            if submitted and user_input.strip():
                st.session_state.farm_messages.append({"role": "user", "content": user_input})
                FARM_SYSTEM = """You are an expert agricultural advisor specializing in Ugandan farming.
                Give practical, actionable advice with current Uganda context for 2025-2026.
                Mention specific crops, regions, and techniques relevant to Uganda.
                Include current seasonal advice, market insights, and climate-smart practices."""
                history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.farm_messages[:-1]]
                with st.spinner("Getting AI advice…"):
                    reply = ask_groq(FARM_SYSTEM, user_input, history)
                st.session_state.farm_messages.append({"role": "assistant", "content": reply})
                st.rerun()

            if st.button("🗑️ Clear Chat"):
                st.session_state.farm_messages = [st.session_state.farm_messages[0]]
                st.rerun()

        # ── PHOTO DIAGNOSIS ─────────────────────────────────────────────────────
        with farm_sub2:
            st.markdown("<div class='image-tip'>📌 Upload a photo of your crop, leaves, soil or pest — AI will diagnose it instantly.</div>", unsafe_allow_html=True)
            farm_image = st.file_uploader("Upload farm photo", type=["jpg","jpeg","png"], key="farm_img", label_visibility="collapsed")
            if farm_image:
                col_img, col_info = st.columns([1, 2])
                with col_img:
                    st.image(farm_image, use_container_width=True, caption="Your photo")
                with col_info:
                    diag_q = st.text_input("Specific question about this photo?",
                        placeholder="e.g. What disease is on my maize leaves?", key="diag_q")
                    if st.button("🔬 Analyze Photo"):
                        farm_image.seek(0)
                        img_b64  = base64.b64encode(farm_image.read()).decode()
                        question = diag_q if diag_q.strip() else "Analyze this farm photo. Identify any diseases, pests, soil issues and give Uganda-specific treatment advice."
                        with st.spinner("AI is analyzing your photo…"):
                            vision_reply = ask_groq_vision(
                                "You are an expert Ugandan agricultural advisor. Analyze this farm image carefully. Give specific, practical treatment and management advice relevant to Uganda.",
                                question, img_b64, farm_image.type
                            )
                        st.success("Analysis complete!")
                        st.markdown(f"""
                        <div class="card card-green" style="margin-top:12px;">
                            <p class="section-label">📸 AI DIAGNOSIS</p>
                            <div style="color:#c8e6c9;font-size:0.9rem;line-height:1.8;white-space:pre-wrap;">{vision_reply}</div>
                        </div>""", unsafe_allow_html=True)

        # ── IMAGE GENERATION ────────────────────────────────────────────────────
        with farm_sub3:
            st.markdown("""
            <div class="image-tip">
            🎨 Describe what you want to visualise — a healthy farm, a planting layout, crop disease symptoms, irrigation system — and the AI will generate an image for you.
            </div>""", unsafe_allow_html=True)

            img_prompt = st.text_area("Describe the farm image you want to generate:",
                placeholder="e.g. A healthy maize farm in Uganda during rainy season with green rows of tall maize plants...",
                height=100, key="img_gen_prompt")

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                quick_prompt = st.selectbox("Or choose a quick example:", [
                    "Custom (type above)",
                    "Healthy maize farm in Uganda",
                    "Drip irrigation system on a small Uganda farm",
                    "Soil erosion on a hillside farm in Uganda",
                    "Organic compost pit on a farm",
                    "Banana plantation in Western Uganda",
                    "Coffee farm in Bugisu region",
                    "Tomato greenhouse farming Uganda",
                    "Farmer applying organic fertilizer",
                ], key="quick_img")

            with col_g2:
                st.markdown("<br>", unsafe_allow_html=True)
                generate_btn = st.button("🎨 Generate Image", key="gen_img_btn")

            if generate_btn:
                final_prompt = img_prompt.strip() if quick_prompt == "Custom (type above)" else quick_prompt
                if not final_prompt:
                    st.warning("Please describe the image or choose an example.")
                else:
                    with st.spinner("🎨 AI is generating your farm image… (may take 10-20 seconds)"):
                        image_url, used_prompt = generate_farm_image_prompt(final_prompt)

                    if image_url:
                        st.markdown(f"""
                        <div class="card card-green" style="margin-top:12px;">
                            <p class="section-label">🎨 GENERATED IMAGE</p>
                            <p style="color:#90A4AE;font-size:0.78rem;margin-bottom:10px;">Prompt used: {used_prompt}</p>
                        </div>""", unsafe_allow_html=True)
                        st.image(image_url, caption=final_prompt, use_container_width=True)
                        st.markdown(f"[📥 Download Image]({image_url})", unsafe_allow_html=False)
                    else:
                        st.error("Could not generate image. Please try again.")

    # ══════════════════════════════════════════════════════════════════════════
    # WASTE GUIDE
    # ══════════════════════════════════════════════════════════════════════════
    with tab_waste:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1a2a1a,#2a4a2a);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
            <p class="section-label" style="color:#81C784;">CIRCULAR ECONOMY</p>
            <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">♻️ Waste Management Guide</h2>
        </div>""", unsafe_allow_html=True)

        selected_waste = st.selectbox("Choose a waste category:", options=[w["name"] for w in WASTE_CATEGORIES],
            format_func=lambda x: f"{next(w['icon'] for w in WASTE_CATEGORIES if w['name']==x)}  {x}")
        chosen = next(w for w in WASTE_CATEGORIES if w["name"] == selected_waste)

        st.markdown(f"""
        <div class="card" style="border-color:{chosen['color']}44;margin-top:10px;">
            <div style="font-size:2.5rem;margin-bottom:8px;">{chosen['icon']}</div>
            <div style="font-weight:800;color:{chosen['color']};font-size:1rem;margin-bottom:6px;">{chosen['name']}</div>
            <div style="color:#c8e6c9;font-size:0.85rem;line-height:1.6;">{chosen['tip']}</div>
        </div>""", unsafe_allow_html=True)

        col_w1, col_w2 = st.columns(2)
        with col_w1:
            if st.button("🤖 Get AI Tips"):
                with st.spinner("Generating tips…"):
                    tip = ask_groq(
                        "You are a circular economy expert for Uganda. Give 3 practical numbered tips. Show income opportunities. Max 2 sentences per tip.",
                        f"3 Uganda-specific circular economy tips for: {selected_waste}"
                    )
                st.markdown(f"""
                <div class="card card-green" style="margin-top:12px;">
                    <p class="section-label">AI TIPS — {selected_waste.upper()}</p>
                    <div style="color:#c8e6c9;font-size:0.9rem;line-height:1.8;white-space:pre-wrap;">{tip}</div>
                </div>""", unsafe_allow_html=True)
        with col_w2:
            if st.button("🌍 Real-Time Waste Market Info"):
                with st.spinner("Getting current waste market info…"):
                    info = get_realtime_info(f"current market for {selected_waste} recycling and circular economy in Uganda 2025-2026")
                st.markdown(f"""
                <div class="realtime-box" style="margin-top:12px;">
                    <p class="section-label" style="color:#64B5F6;">REAL-TIME MARKET INFO</p>
                    <div style="color:#c8e6c9;font-size:0.9rem;line-height:1.8;white-space:pre-wrap;">{info}</div>
                </div>""", unsafe_allow_html=True)

        cols = st.columns(3)
        for i, w in enumerate(WASTE_CATEGORIES):
            with cols[i % 3]:
                st.markdown(f"""
                <div style="text-align:center;background:rgba(255,255,255,0.04);border:1px solid {w['color']}33;border-radius:12px;padding:14px 8px;margin-bottom:8px;">
                    <div style="font-size:1.8rem;">{w['icon']}</div>
                    <div style="font-size:0.72rem;font-weight:700;color:{w['color']};margin-top:4px;">{w['name']}</div>
                </div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # CLIMATE
    # ══════════════════════════════════════════════════════════════════════════
    with tab_climate:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#0d2137,#1a3a5c);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
            <p class="section-label" style="color:#64B5F6;">UGANDA 2026 · REAL-TIME</p>
            <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">🌦️ Climate Dashboard</h2>
        </div>""", unsafe_allow_html=True)

        if st.button("🔄 Get Real-Time Climate Update for Uganda"):
            with st.spinner("Fetching latest climate information…"):
                climate_info = get_realtime_info("current weather conditions, rainfall forecast, and climate advisories for Uganda farmers June 2026")
            st.markdown(f"""
            <div class="realtime-box">
                <p class="section-label" style="color:#64B5F6;">🌍 REAL-TIME CLIMATE UPDATE</p>
                <div style="color:#c8e6c9;font-size:0.9rem;line-height:1.8;white-space:pre-wrap;">{climate_info}</div>
            </div>""", unsafe_allow_html=True)

        for a in ALERTS:
            icon  = "⚠️" if a["level"]=="warning" else ("ℹ️" if a["level"]=="info" else "✅")
            color = "#FF9800" if a["level"]=="warning" else ("#2196F3" if a["level"]=="info" else "#4CAF50")
            st.markdown(f"""<div class="alert-{a['level']}">
                <div class="alert-region" style="color:{color};">{icon} {a['region'].upper()}</div>
                <div class="alert-text">{a['text']}</div></div>""", unsafe_allow_html=True)

        df = pd.DataFrame(CLIMATE_DATA).set_index("Month")
        st.markdown("<br><p class='section-label'>MONTHLY RAINFALL (MM)</p>", unsafe_allow_html=True)
        st.bar_chart(df[["Rainfall (mm)"]], color="#1E88E5", height=220)
        st.markdown("<p class='section-label'>AVERAGE TEMPERATURE (°C)</p>", unsafe_allow_html=True)
        st.line_chart(df[["Avg Temp (°C)"]], color="#FF9800", height=180)

        s1, s2, s3 = st.columns(3)
        with s1:
            st.markdown("""<div class="card card-blue" style="text-align:center;padding:14px 10px;">
                <div style="font-size:1.8rem;">🌧️</div>
                <div style="font-family:'Space Mono',monospace;font-size:1rem;font-weight:700;color:#64B5F6;">97mm</div>
                <div style="font-size:0.72rem;color:#90A4AE;">Avg Monthly Rain</div></div>""", unsafe_allow_html=True)
        with s2:
            st.markdown("""<div class="card card-orange" style="text-align:center;padding:14px 10px;">
                <div style="font-size:1.8rem;">🌡️</div>
                <div style="font-family:'Space Mono',monospace;font-size:1rem;font-weight:700;color:#FFB74D;">24.8°C</div>
                <div style="font-size:0.72rem;color:#90A4AE;">Avg Temperature</div></div>""", unsafe_allow_html=True)
        with s3:
            st.markdown("""<div class="card card-green" style="text-align:center;padding:14px 10px;">
                <div style="font-size:1.8rem;">📅</div>
                <div style="font-family:'Space Mono',monospace;font-size:1rem;font-weight:700;color:#81C784;">2 wet</div>
                <div style="font-size:0.72rem;color:#90A4AE;">Seasons/Year</div></div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # MARKETPLACE
    # ══════════════════════════════════════════════════════════════════════════
    with tab_market:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#2d1a00,#5d3a00);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
            <p class="section-label" style="color:#FFB74D;">GREEN ECONOMY · VERIFIED SELLERS</p>
            <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">🤝 Marketplace</h2>
            <p style="color:#FFB74D;font-size:0.82rem;margin:0;">Every listing includes product photos & seller contact details for full traceability.</p>
        </div>""", unsafe_allow_html=True)

        filter_type = st.radio("Filter:", ["All","Selling 🟢","Buying 🔵"], horizontal=True)

        for listing in st.session_state.listings:
            if filter_type == "Selling 🟢" and listing["type"] != "sell": continue
            if filter_type == "Buying 🔵"  and listing["type"] != "buy":  continue
            badge_class = "sell-badge" if listing["type"]=="sell" else "buy-badge"
            badge_text  = "SELL"       if listing["type"]=="sell" else "BUY"

            if listing.get("image"):
                st.image(listing["image"], use_container_width=True, caption=listing["title"])
            else:
                st.markdown("""<div style="background:rgba(255,255,255,0.03);border:1px dashed rgba(255,255,255,0.1);
                border-radius:10px 10px 0 0;padding:16px;text-align:center;color:#546E7A;font-size:0.8rem;">📷 No photo uploaded</div>""", unsafe_allow_html=True)

            st.markdown(f"""
            <div class="market-card" style="border-radius:0 0 14px 14px;border-top:none;">
                <div class="market-body">
                    <span class="{badge_class}">{badge_text}</span>
                    <div class="market-title">{listing['title']}</div>
                    <div class="market-meta">{listing.get('description','')}</div>
                    <div><span class="market-price">{listing['price']}</span><span class="market-tag">{listing['tag']}</span></div>
                </div>
                <div class="seller-info">
                    👤 <strong>{listing['seller']}</strong>
                    <span class="verified-badge">✓ SELLER</span>
                    &nbsp;&nbsp;📞 {listing.get('phone','N/A')}
                    &nbsp;&nbsp;📍 {listing.get('district','N/A')} District
                </div>
            </div><br>""", unsafe_allow_html=True)

        st.markdown("<p class='section-label'>POST A NEW LISTING</p>", unsafe_allow_html=True)
        with st.expander("➕ Add your listing with photo"):
            new_title = st.text_input("Title *", placeholder="e.g. Fresh Maize — 100kg")
            new_desc  = st.text_area("Description *", height=70)
            c1, c2 = st.columns(2)
            with c1:
                new_type     = st.selectbox("Type *", ["Selling","Buying"])
                new_price    = st.text_input("Price (UGX) *")
                new_tag      = st.selectbox("Category *", ["Fresh Produce","Waste-to-Value","Clean Energy","AgriTech","Circular Economy","Recycling","Other"])
            with c2:
                new_location = st.text_input("Village / Area *")
                new_district = st.text_input("District *")
                new_phone    = st.text_input("Phone *", value=user_data["phone"])
            new_image = st.file_uploader("Product Photo", type=["jpg","jpeg","png"], key="new_img")
            if new_image:
                st.image(new_image, width=180)
            if st.button("📤 Submit Listing"):
                if new_title and new_price and new_desc:
                    img_data = None
                    if new_image:
                        new_image.seek(0)
                        img_data = new_image.read()
                    st.session_state.listings.insert(0, {
                        "title":       new_title,
                        "seller":      user_data["full_name"],
                        "phone":       new_phone,
                        "location":    new_location,
                        "district":    new_district,
                        "price":       f"UGX {new_price}" if not new_price.startswith("UGX") else new_price,
                        "type":        "sell" if new_type=="Selling" else "buy",
                        "tag":         new_tag,
                        "description": new_desc,
                        "image":       img_data,
                        "posted_on":   datetime.now().strftime("%d %b %Y"),
                    })
                    st.success("✅ Listing posted!")
                    st.rerun()
                else:
                    st.warning("Please fill required fields.")

    # ══════════════════════════════════════════════════════════════════════════
    # FARMER CHAT — Encrypted, saved to Supabase
    # ══════════════════════════════════════════════════════════════════════════
    with tab_chat:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1a0a2e,#2d1a4f);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
            <p class="section-label" style="color:#CE93D8;">END-TO-END ENCRYPTED · SAVED TO DATABASE</p>
            <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">💬 Farmer Chat Rooms</h2>
            <p style="color:#CE93D8;font-size:0.82rem;margin:0;">🔒 Messages are encrypted and saved. Your chat history is always here when you return.</p>
        </div>""", unsafe_allow_html=True)

        # Room selector
        st.markdown("<p class='section-label'>CHOOSE A ROOM</p>", unsafe_allow_html=True)
        room_cols = st.columns(2)
        for idx, (room_key, room_info) in enumerate(CHAT_ROOMS.items()):
            with room_cols[idx % 2]:
                is_active = st.session_state.active_room == room_key
                if st.button(
                    f"{'✅ ' if is_active else ''}{room_info['name']}",
                    key=f"room_{room_key}",
                    help=room_info['desc']
                ):
                    st.session_state.active_room = room_key
                    st.rerun()

        active_room = st.session_state.active_room
        room_info   = CHAT_ROOMS[active_room]

        st.markdown(f"""
        <div style="display:flex;align-items:center;justify-content:space-between;margin:16px 0 10px;">
            <div>
                <span style="font-size:1rem;font-weight:800;color:#fff;">{room_info['name']}</span>
                <span style="font-size:0.7rem;color:#CE93D8;font-family:'Space Mono',monospace;margin-left:10px;">🔒 ENCRYPTED</span>
            </div>
        </div>""", unsafe_allow_html=True)

        # Load messages from Supabase
        messages = db_get_messages(active_room, limit=60)

        if not messages:
            st.markdown("""<div style="text-align:center;padding:40px 20px;color:#546E7A;font-size:0.85rem;">
                💬 No messages yet in this room. Be the first to say something!</div>""", unsafe_allow_html=True)
        else:
            for msg in messages:
                is_me    = msg["sender"] == user
                decrypted = decrypt_message(msg["encrypted_text"])
                if is_me:
                    st.markdown(f"""
                    <div style="display:flex;flex-direction:column;align-items:flex-end;margin-bottom:8px;">
                        <div class="msg-bubble-me">{decrypted}
                            <div class="msg-time">🔒 {msg['msg_time']} · {msg['msg_date']}</div>
                        </div>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="display:flex;flex-direction:column;align-items:flex-start;margin-bottom:8px;">
                        <div class="msg-name">{msg['display_name']}</div>
                        <div class="msg-bubble-other">{decrypted}
                            <div class="msg-time">🔒 {msg['msg_time']} · {msg['msg_date']}</div>
                        </div>
                    </div>""", unsafe_allow_html=True)

        # Send message
        st.markdown("<br>", unsafe_allow_html=True)
        with st.form(f"chat_form_{active_room}", clear_on_submit=True):
            col_input, col_send = st.columns([5, 1])
            with col_input:
                new_msg = st.text_input("", placeholder=f"Message {room_info['name']}… (encrypted 🔒)", label_visibility="collapsed")
            with col_send:
                send_btn = st.form_submit_button("Send")

        if send_btn and new_msg.strip():
            encrypted = encrypt_message(new_msg.strip())
            db_save_message(active_room, user, user_data["full_name"], encrypted)
            st.rerun()

        if st.button("🔄 Refresh Messages"):
            st.rerun()

        st.markdown("""
        <div style="background:rgba(156,39,176,0.06);border:1px solid rgba(156,39,176,0.15);border-radius:10px;padding:10px 14px;margin-top:12px;font-size:0.75rem;color:#CE93D8;text-align:center;">
        🔒 Messages are end-to-end encrypted and saved securely to the database.
        </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.current_user is None:
    show_auth()
else:
    show_main_app()

st.markdown("""
<hr style='border-color:rgba(76,175,80,0.1);margin:32px 0 16px;'>
<p style='text-align:center;font-family:Space Mono,monospace;font-size:0.65rem;color:#37474F;letter-spacing:1px;'>
ECOPULSE · Elias Creations Reasch out to 0705046024 for any inquiries · POWERED BY GROQ + SUPABASE
</p>""", unsafe_allow_html=True)
