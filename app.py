import streamlit as st
from groq import Groq
import pandas as pd

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="EcoPulse | CCIC 2026",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Configure Groq ─────────────────────────────────────────────────────────────
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

def ask_groq(system_prompt, user_message, history=None):
    try:
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for m in history[-6:]:
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_message})
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",,
            messages=messages,
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;600;800&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background-color: #0a0f0a;
    color: #e8f5e9;
}
.stApp { background: #0a0f0a; }
h1, h2, h3 { font-family: 'Playfair Display', serif !important; }

.hero-box {
    background: linear-gradient(135deg, #0a2016 0%, #1a4731 50%, #0d2137 100%);
    border-radius: 20px;
    padding: 32px 28px;
    margin-bottom: 24px;
    border: 1px solid rgba(76,175,80,0.2);
}
.hero-title {
    font-family: 'Playfair Display', serif;
    font-size: 2.2rem;
    font-weight: 900;
    color: #ffffff;
    margin: 0 0 8px 0;
    line-height: 1.2;
}
.hero-accent { color: #81C784; }
.hero-sub {
    font-size: 1rem;
    color: #a8d5b5;
    margin: 0 0 16px 0;
    line-height: 1.6;
}
.badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 8px;
    font-family: 'Space Mono', monospace;
    font-size: 0.7rem;
    font-weight: 700;
    margin-right: 6px;
}
.badge-green  { background: rgba(76,175,80,0.2);  border: 1px solid rgba(76,175,80,0.4);  color: #81C784; }
.badge-blue   { background: rgba(33,150,243,0.2); border: 1px solid rgba(33,150,243,0.4); color: #64B5F6; }
.badge-orange { background: rgba(255,152,0,0.2);  border: 1px solid rgba(255,152,0,0.4);  color: #FFB74D; }
.badge-live   { background: rgba(76,175,80,0.15); border: 1px solid rgba(76,175,80,0.3);  color: #81C784; }

.section-label {
    font-family: 'Space Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #81C784;
    margin-bottom: 4px;
}
.card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 12px;
}
.card-green  { border-color: rgba(76,175,80,0.25); }
.card-blue   { border-color: rgba(33,150,243,0.25); }
.card-orange { border-color: rgba(255,152,0,0.25); }

.alert-warning { background: rgba(255,152,0,0.1);  border: 1px solid rgba(255,152,0,0.3);  border-radius: 10px; padding: 12px 16px; margin-bottom: 10px; }
.alert-info    { background: rgba(33,150,243,0.1); border: 1px solid rgba(33,150,243,0.3); border-radius: 10px; padding: 12px 16px; margin-bottom: 10px; }
.alert-success { background: rgba(76,175,80,0.1);  border: 1px solid rgba(76,175,80,0.3);  border-radius: 10px; padding: 12px 16px; margin-bottom: 10px; }
.alert-text    { color: #e8f5e9; font-size: 0.88rem; line-height: 1.6; }
.alert-region  { font-family: 'Space Mono', monospace; font-size: 0.65rem; letter-spacing: 1px; font-weight: 700; margin-bottom: 4px; }

.market-card  {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 10px;
}
.market-title { font-size: 0.95rem; font-weight: 800; color: #fff; margin-bottom: 6px; }
.market-meta  { font-size: 0.78rem; color: #90A4AE; margin-bottom: 8px; }
.market-price { font-family: 'Space Mono', monospace; font-size: 1rem; font-weight: 700; color: #FFB74D; }
.market-tag   { display: inline-block; background: rgba(255,183,77,0.15); color: #FFB74D; font-size: 0.7rem; padding: 2px 8px; border-radius: 4px; margin-left: 8px; }
.sell-badge   { background: rgba(76,175,80,0.2);  color: #81C784; font-size: 0.65rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; float: right; font-family: 'Space Mono', monospace; }
.buy-badge    { background: rgba(33,150,243,0.2); color: #64B5F6; font-size: 0.65rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; float: right; font-family: 'Space Mono', monospace; }

.chat-user {
    background: linear-gradient(135deg, #2d7a4f, #1a4731);
    border-radius: 16px 16px 4px 16px;
    padding: 10px 14px;
    margin: 6px 0 6px auto;
    max-width: 80%;
    font-size: 0.9rem;
    color: #e8f5e9;
    line-height: 1.6;
}
.chat-ai {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(168,230,191,0.2);
    border-radius: 16px 16px 16px 4px;
    padding: 10px 14px;
    margin: 6px auto 6px 0;
    max-width: 80%;
    font-size: 0.9rem;
    color: #e8f5e9;
    line-height: 1.6;
    white-space: pre-wrap;
}
.quote-box {
    background: rgba(76,175,80,0.06);
    border: 1px solid rgba(76,175,80,0.15);
    border-radius: 14px;
    padding: 18px 20px;
    margin-top: 20px;
}
.stTextInput > div > div > input {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(168,230,191,0.2) !important;
    border-radius: 10px !important;
    color: #e8f5e9 !important;
}
.stButton > button {
    background: linear-gradient(135deg, #2d7a4f, #4CAF50) !important;
    border: none !important;
    border-radius: 10px !important;
    color: #fff !important;
    font-weight: 700 !important;
    font-family: 'DM Sans', sans-serif !important;
}
div[data-testid="stTabs"] button {
    color: #81C784 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Data ───────────────────────────────────────────────────────────────────────
WASTE_CATEGORIES = [
    {"name": "Organic / Food Waste",  "icon": "🍌", "color": "#4CAF50", "tip": "Compost food scraps into rich soil fertilizer for farms."},
    {"name": "Plastic",               "icon": "🧴", "color": "#2196F3", "tip": "Rinse and take to a recycling point near you."},
    {"name": "Electronic Waste",      "icon": "📱", "color": "#9C27B0", "tip": "Never dump e-waste. Find certified e-waste collectors."},
    {"name": "Agricultural Waste",    "icon": "🌿", "color": "#FF9800", "tip": "Convert crop residues to biochar or biogas — both profitable!"},
    {"name": "Paper & Cardboard",     "icon": "📦", "color": "#795548", "tip": "Separate and dry before recycling. Avoid oil contamination."},
    {"name": "Glass",                 "icon": "🍶", "color": "#00BCD4", "tip": "Reuse clean bottles or return them to manufacturers."},
]

CLIMATE_DATA = {
    "Month": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
    "Rainfall (mm)": [48,62,130,178,142,72,55,88,110,155,148,82],
    "Avg Temp (°C)": [26,27,26,25,24,23,22,23,24,24,25,26],
}

ALERTS = [
    {"level":"warning","region":"Central",    "text":"Heavy rains expected — delay planting by 5–7 days."},
    {"level":"info",   "region":"North East", "text":"Dry spell forecast in Karamoja. Activate water conservation measures."},
    {"level":"success","region":"Western",    "text":"Optimal planting window open for beans & maize this season."},
]

MARKET_LISTINGS = [
    {"title":"Organic Compost — 50kg bags",        "seller":"Kakooza Farms",  "location":"Wakiso",  "price":"UGX 25,000",      "type":"sell","tag":"Waste-to-Value"},
    {"title":"Solar Water Pump — rental",           "seller":"GreenTech Hub",  "location":"Kampala", "price":"UGX 15,000/day",  "type":"sell","tag":"Clean Energy"},
    {"title":"Wanted: Crop Residue (Maize stalks)", "seller":"BioGas Uganda",  "location":"Jinja",   "price":"UGX 8,000/bale",  "type":"buy", "tag":"Circular Economy"},
    {"title":"Surplus Tomatoes — urgent sale",      "seller":"Nakato Agri",    "location":"Mbarara", "price":"UGX 10,000/crate","type":"sell","tag":"Fresh Produce"},
    {"title":"Drip Irrigation Kit — 1 acre",        "seller":"SmartFarm Ltd",  "location":"Entebbe", "price":"UGX 320,000",     "type":"sell","tag":"AgriTech"},
    {"title":"Wanted: Plastic scrap (PET)",         "seller":"RecycleMore UG", "location":"Kampala", "price":"UGX 500/kg",      "type":"buy", "tag":"Recycling"},
]

# ── HEADER ──────────────────────────────────────────────────────────────────────
col_logo, col_live = st.columns([5, 1])
with col_logo:
    st.markdown("<h1 style='font-family:Playfair Display,serif;color:#81C784;margin:0;font-size:1.8rem;'>🌍 EcoPulse</h1>", unsafe_allow_html=True)
    st.markdown("<p style='font-family:Space Mono,monospace;font-size:0.65rem;color:#4CAF50;letter-spacing:2px;margin:0;'>CCIC 2026 · MAKERERE UNIVERSITY</p>", unsafe_allow_html=True)
with col_live:
    st.markdown("<div class='badge badge-live' style='margin-top:12px;'>🟢 LIVE</div>", unsafe_allow_html=True)

st.markdown("<hr style='border-color:rgba(76,175,80,0.15);margin:10px 0 20px;'>", unsafe_allow_html=True)

# ── TABS ────────────────────────────────────────────────────────────────────────
tab_home, tab_farm, tab_waste, tab_climate, tab_market = st.tabs([
    "🏠 Home", "🌾 Farm AI", "♻️ Waste Guide", "🌦️ Climate", "🤝 Marketplace"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — HOME
# ══════════════════════════════════════════════════════════════════════════════
with tab_home:
    st.markdown("""
    <div class="hero-box">
        <p class="section-label">CCIC 2026 — Track 2: Climate Tech & Digital Innovation</p>
        <h1 class="hero-title">Uganda's Green<br><span class="hero-accent">Revolution</span> Starts Here</h1>
        <p class="hero-sub">AI-powered tools for climate-resilient agriculture, circular waste management & green enterprise — all in one platform.</p>
        <span class="badge badge-green">🌾 AgriAI</span>
        <span class="badge badge-blue">♻️ Waste</span>
        <span class="badge badge-orange">🤝 Market</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<p class='section-label'>WHAT THIS PLATFORM DOES</p>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        <div class="card card-green">
            <div style="font-size:2rem;margin-bottom:8px;">🌾</div>
            <div style="font-weight:800;color:#fff;margin-bottom:6px;font-size:1rem;">Farm AI Advisor</div>
            <div style="color:#90A4AE;font-size:0.82rem;line-height:1.6;">Get real-time AI guidance on crops, soil health, pest control & climate adaptation.</div>
            <div style="color:#81C784;font-size:0.75rem;margin-top:10px;font-family:'Space Mono',monospace;">→ Open Farm AI tab</div>
        </div>
        <div class="card card-blue">
            <div style="font-size:2rem;margin-bottom:8px;">🌦️</div>
            <div style="font-weight:800;color:#fff;margin-bottom:6px;font-size:1rem;">Climate Dashboard</div>
            <div style="color:#90A4AE;font-size:0.82rem;line-height:1.6;">Rainfall trends, temperature data & regional climate alerts for all of Uganda.</div>
            <div style="color:#64B5F6;font-size:0.75rem;margin-top:10px;font-family:'Space Mono',monospace;">→ Open Climate tab</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="card card-green">
            <div style="font-size:2rem;margin-bottom:8px;">♻️</div>
            <div style="font-weight:800;color:#fff;margin-bottom:6px;font-size:1rem;">Waste Guide</div>
            <div style="color:#90A4AE;font-size:0.82rem;line-height:1.6;">Circular economy tips for every waste category — turn waste into income.</div>
            <div style="color:#81C784;font-size:0.75rem;margin-top:10px;font-family:'Space Mono',monospace;">→ Open Waste Guide tab</div>
        </div>
        <div class="card card-orange">
            <div style="font-size:2rem;margin-bottom:8px;">🤝</div>
            <div style="font-weight:800;color:#fff;margin-bottom:6px;font-size:1rem;">Green Marketplace</div>
            <div style="color:#90A4AE;font-size:0.82rem;line-height:1.6;">Connect farmers, recyclers and green entrepreneurs across Uganda.</div>
            <div style="color:#FFB74D;font-size:0.75rem;margin-top:10px;font-family:'Space Mono',monospace;">→ Open Marketplace tab</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="quote-box">
        <p class="section-label">THEME 2026</p>
        <p style="font-family:'Playfair Display',serif;font-style:italic;color:#c8e6c9;font-size:1rem;line-height:1.7;margin:6px 0;">
        "Empowering University Students to Design Real Solutions for Climate Resilience"
        </p>
        <p style="color:#66BB6A;font-size:0.8rem;margin:0;">Makerere University Students Guild · CCIC 2026</p>
    </div>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — FARM AI
# ══════════════════════════════════════════════════════════════════════════════
with tab_farm:
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a4731,#2d7a4f);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
        <p class="section-label" style="color:#a8e6bf;">AI-POWERED · GROQ LLAMA 3</p>
        <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">🌾 Farm Advisory</h2>
        <p style="color:#a8e6bf;font-size:0.82rem;margin:0;">Ask anything about crops, soil, pests, water & climate-smart farming in Uganda.</p>
    </div>
    """, unsafe_allow_html=True)

    FARM_SYSTEM = """You are an expert agricultural advisor specializing in Ugandan farming conditions,
    climate resilience, and sustainable agriculture. Give practical, actionable advice.
    Mention specific crops, regions, and techniques relevant to Uganda.
    Connect farming to waste management and circular economy where relevant.
    Keep answers clear, structured and useful for Ugandan farmers."""

    if "farm_messages" not in st.session_state:
        st.session_state.farm_messages = [
            {"role": "assistant", "content": "Hello! I'm your AI Farm Advisor 🌾\n\nAsk me about crops, soil, pests, rainfall patterns, or any sustainable farming challenge in Uganda."}
        ]

    for msg in st.session_state.farm_messages:
        if msg["role"] == "assistant":
            st.markdown(f"<div class='chat-ai'>🤖 {msg['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-user'>👤 {msg['content']}</div>", unsafe_allow_html=True)

    with st.form("farm_form", clear_on_submit=True):
        user_input = st.text_input("", placeholder="e.g. What crops should I plant in April in Central Uganda?", label_visibility="collapsed")
        submitted = st.form_submit_button("Send ↑")

    if submitted and user_input.strip():
        st.session_state.farm_messages.append({"role": "user", "content": user_input})
        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.farm_messages[:-1]]
        with st.spinner("Getting AI advice…"):
            reply = ask_groq(FARM_SYSTEM, user_input, history)
        st.session_state.farm_messages.append({"role": "assistant", "content": reply})
        st.rerun()

    if st.button("🗑️ Clear Chat", key="clear_farm"):
        st.session_state.farm_messages = [st.session_state.farm_messages[0]]
        st.rerun()

    st.markdown("""
    <p style="font-size:0.75rem;color:#546E7A;text-align:center;margin-top:12px;font-family:'Space Mono',monospace;">
    Try: "Best crops for erratic rainfall" · "How to improve clay soil" · "Organic pest control for maize"
    </p>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — WASTE GUIDE
# ══════════════════════════════════════════════════════════════════════════════
with tab_waste:
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a2a1a,#2a4a2a);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
        <p class="section-label" style="color:#81C784;">CIRCULAR ECONOMY</p>
        <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">♻️ Waste Management Guide</h2>
        <p style="color:#81C784;font-size:0.82rem;margin:0;">Select a waste type to get AI-powered circular economy tips.</p>
    </div>
    """, unsafe_allow_html=True)

    selected_waste = st.selectbox(
        "Choose a waste category:",
        options=[w["name"] for w in WASTE_CATEGORIES],
        format_func=lambda x: f"{next(w['icon'] for w in WASTE_CATEGORIES if w['name']==x)}  {x}"
    )

    chosen = next(w for w in WASTE_CATEGORIES if w["name"] == selected_waste)

    st.markdown(f"""
    <div class="card" style="border-color:{chosen['color']}44;margin-top:10px;">
        <div style="font-size:2.5rem;margin-bottom:8px;">{chosen['icon']}</div>
        <div style="font-weight:800;color:{chosen['color']};font-size:1rem;margin-bottom:6px;">{chosen['name']}</div>
        <div style="color:#c8e6c9;font-size:0.85rem;line-height:1.6;">{chosen['tip']}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🤖 Get Detailed AI Tips for this Waste Type"):
        WASTE_SYSTEM = """You are a circular economy expert specializing in Uganda.
        Give 3 practical numbered tips. Show how each waste type can generate income or benefit farmers.
        Be concise — max 2 sentences per point. Focus on Uganda-specific solutions."""
        with st.spinner("Generating Uganda-specific circular economy tips…"):
            tip = ask_groq(
                WASTE_SYSTEM,
                f"Give me 3 practical Uganda-specific circular economy tips for managing: {selected_waste}"
            )
        st.markdown(f"""
        <div class="card card-green" style="margin-top:12px;">
            <p class="section-label">AI TIPS — {selected_waste.upper()}</p>
            <div style="color:#c8e6c9;font-size:0.9rem;line-height:1.8;white-space:pre-wrap;">{tip}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<hr style='border-color:rgba(255,255,255,0.06);margin:20px 0;'>", unsafe_allow_html=True)
    st.markdown("<p class='section-label'>ALL CATEGORIES AT A GLANCE</p>", unsafe_allow_html=True)

    cols = st.columns(3)
    for i, w in enumerate(WASTE_CATEGORIES):
        with cols[i % 3]:
            st.markdown(f"""
            <div style="text-align:center;background:rgba(255,255,255,0.04);border:1px solid {w['color']}33;border-radius:12px;padding:14px 8px;margin-bottom:8px;">
                <div style="font-size:1.8rem;">{w['icon']}</div>
                <div style="font-size:0.72rem;font-weight:700;color:{w['color']};margin-top:4px;line-height:1.3;">{w['name']}</div>
            </div>
            """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — CLIMATE DATA
# ══════════════════════════════════════════════════════════════════════════════
with tab_climate:
    st.markdown("""
    <div style="background:linear-gradient(135deg,#0d2137,#1a3a5c);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
        <p class="section-label" style="color:#64B5F6;">UGANDA 2026</p>
        <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">🌦️ Climate Dashboard</h2>
        <p style="color:#64B5F6;font-size:0.82rem;margin:0;">Rainfall trends, temperature data & regional alerts.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<p class='section-label'>REGIONAL ALERTS</p>", unsafe_allow_html=True)
    for a in ALERTS:
        icon  = "⚠️" if a["level"]=="warning" else ("ℹ️" if a["level"]=="info" else "✅")
        color = "#FF9800" if a["level"]=="warning" else ("#2196F3" if a["level"]=="info" else "#4CAF50")
        st.markdown(f"""
        <div class="alert-{a['level']}">
            <div class="alert-region" style="color:{color};">{icon} {a['region'].upper()}</div>
            <div class="alert-text">{a['text']}</div>
        </div>
        """, unsafe_allow_html=True)

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
            <div style="font-size:0.72rem;color:#90A4AE;">Avg Monthly Rain</div>
        </div>""", unsafe_allow_html=True)
    with s2:
        st.markdown("""<div class="card card-orange" style="text-align:center;padding:14px 10px;">
            <div style="font-size:1.8rem;">🌡️</div>
            <div style="font-family:'Space Mono',monospace;font-size:1rem;font-weight:700;color:#FFB74D;">24.8°C</div>
            <div style="font-size:0.72rem;color:#90A4AE;">Avg Temperature</div>
        </div>""", unsafe_allow_html=True)
    with s3:
        st.markdown("""<div class="card card-green" style="text-align:center;padding:14px 10px;">
            <div style="font-size:1.8rem;">📅</div>
            <div style="font-family:'Space Mono',monospace;font-size:1rem;font-weight:700;color:#81C784;">2 wet</div>
            <div style="font-size:0.72rem;color:#90A4AE;">Seasons/Year</div>
        </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — MARKETPLACE
# ══════════════════════════════════════════════════════════════════════════════
with tab_market:
    st.markdown("""
    <div style="background:linear-gradient(135deg,#2d1a00,#5d3a00);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
        <p class="section-label" style="color:#FFB74D;">GREEN ECONOMY</p>
        <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">🤝 Marketplace</h2>
        <p style="color:#FFB74D;font-size:0.82rem;margin:0;">Connect farmers, recyclers & green innovators across Uganda.</p>
    </div>
    """, unsafe_allow_html=True)

    filter_type = st.radio("Filter listings:", ["All", "Selling 🟢", "Buying 🔵"], horizontal=True)

    for listing in MARKET_LISTINGS:
        if filter_type == "Selling 🟢" and listing["type"] != "sell": continue
        if filter_type == "Buying 🔵"  and listing["type"] != "buy":  continue

        badge_class = "sell-badge" if listing["type"] == "sell" else "buy-badge"
        badge_text  = "SELL"       if listing["type"] == "sell" else "BUY"

        st.markdown(f"""
        <div class="market-card">
            <div>
                <span class="{badge_class}">{badge_text}</span>
                <div class="market-title">{listing['title']}</div>
            </div>
            <div class="market-meta">📍 {listing['location']} &nbsp;·&nbsp; 👤 {listing['seller']}</div>
            <div>
                <span class="market-price">{listing['price']}</span>
                <span class="market-tag">{listing['tag']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<p class='section-label'>POST A NEW LISTING</p>", unsafe_allow_html=True)

    with st.expander("➕ Add your listing"):
        new_title = st.text_input("What are you selling or buying?")
        col_a, col_b = st.columns(2)
        with col_a:
            new_type     = st.selectbox("Type", ["Selling", "Buying"])
            new_location = st.text_input("Location (district)")
        with col_b:
            new_price  = st.text_input("Price (UGX)")
            new_seller = st.text_input("Your name / organization")
        if st.button("📤 Submit Listing"):
            if new_title and new_price:
                st.success(f"✅ Listing '{new_title}' submitted! It will appear after review.")
            else:
                st.warning("Please fill in the title and price at minimum.")

# ── Footer ──────────────────────────────────────────────────────────────────────
st.markdown("""
<hr style='border-color:rgba(76,175,80,0.1);margin:32px 0 16px;'>
<p style='text-align:center;font-family:Space Mono,monospace;font-size:0.65rem;color:#37474F;letter-spacing:1px;'>
ECOPULSE · CCIC 2026 · MAKERERE UNIVERSITY STUDENTS GUILD · POWERED BY GROQ LLAMA 3
</p>
""", unsafe_allow_html=True)
