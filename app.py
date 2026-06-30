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

# ── Weather ────────────────────────────────────────────────────────────────────
def get_weather_by_coords(lat, lon):
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,precipitation,weathercode,windspeed_10m"
            f"&daily=precipitation_sum,temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max"
            f"&timezone=Africa/Kampala&forecast_days=7"
        )
        r = requests.get(url, timeout=10)
        return r.json() if r.status_code == 200 else None
    except:
        return None

UGANDA_DISTRICTS = {
    "kampala":(0.3476,32.5825),"wakiso":(0.3988,32.4553),"mukono":(0.3536,32.7554),
    "jinja":(0.4478,33.2026),"mbarara":(-0.6072,30.6545),"gulu":(2.7748,32.2990),
    "lira":(2.2499,32.8997),"arua":(3.0200,30.9110),"fort portal":(0.6710,30.2750),
    "masaka":(-0.3333,31.7333),"kabale":(-1.2500,29.9833),"soroti":(1.7148,33.6112),
    "mbale":(1.0806,34.1750),"tororo":(0.6930,34.1808),"hoima":(1.4347,31.3522),
    "kasese":(0.1833,30.0833),"iganga":(0.6090,33.4685),"bushenyi":(-0.5500,30.1833),
    "ntungamo":(-0.8833,30.2667),"rukungiri":(-0.8333,29.9333),"nebbi":(2.4833,31.0833),
    "adjumani":(3.3667,31.7833),"moroto":(2.5333,34.6667),"kotido":(2.9833,34.1333),
    "ngora":(1.4833,33.7667),"serere":(1.5000,33.5500),"pallisa":(1.1333,33.7167),
    "kumi":(1.4600,33.9333),"kapchorwa":(1.4000,34.4500),"bukedea":(1.3500,34.0667),
}

def get_coords_for_district(district):
    key = district.lower().strip()
    if key in UGANDA_DISTRICTS:
        return UGANDA_DISTRICTS[key]
    try:
        r = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={district}+Uganda&count=1&language=en&format=json",
            timeout=8
        )
        data = r.json()
        if data.get("results"):
            res = data["results"][0]
            return res["latitude"], res["longitude"]
    except:
        pass
    return (1.3733, 32.2903)

WEATHER_CODES = {
    0:"Clear sky",1:"Mainly clear",2:"Partly cloudy",3:"Overcast",
    45:"Foggy",51:"Light drizzle",53:"Moderate drizzle",55:"Dense drizzle",
    61:"Slight rain",63:"Moderate rain",65:"Heavy rain",
    80:"Slight showers",81:"Moderate showers",82:"Violent showers",
    95:"Thunderstorm",96:"Thunderstorm + hail",99:"Thunderstorm + heavy hail",
}

def parse_weather_alerts(weather_data, location_name):
    alerts = []
    if not weather_data:
        return alerts
    try:
        current = weather_data.get("current", {})
        code    = current.get("weathercode", 0)
        temp    = current.get("temperature_2m", 0)
        precip  = current.get("precipitation", 0)
        wind    = current.get("windspeed_10m", 0)
        humidity= current.get("relative_humidity_2m", 0)

        if code in [61,63,65,80,81,82,95,96,99] or precip > 5:
            alerts.append({"level":"danger","icon":"🌧️","title":f"HEAVY RAIN — {location_name.upper()}",
                "message":f"Heavy rainfall ({precip}mm). Delay planting, secure crops and livestock.","sound":True})
        elif code in [51,53,55] or precip > 0.5:
            alerts.append({"level":"warning","icon":"🌦️","title":f"RAIN INCOMING — {location_name.upper()}",
                "message":"Light to moderate rain expected. Prepare irrigation and protect stored produce.","sound":False})
        if code in [95,96,99]:
            alerts.append({"level":"danger","icon":"⛈️","title":f"THUNDERSTORM — {location_name.upper()}",
                "message":"Severe thunderstorm. Stay indoors, unplug equipment, secure farm structures.","sound":True})
        if temp > 35:
            alerts.append({"level":"warning","icon":"🌡️","title":f"HEAT ALERT — {location_name.upper()}",
                "message":f"Temperature {temp}°C. Irrigate early morning/evening. Ensure livestock have water.","sound":False})
        if code in [0,1] and precip == 0 and humidity < 30:
            alerts.append({"level":"info","icon":"☀️","title":f"DRY CONDITIONS — {location_name.upper()}",
                "message":f"Very dry (humidity {humidity}%). Activate water conservation.","sound":False})
        if wind > 40:
            alerts.append({"level":"warning","icon":"💨","title":f"STRONG WINDS — {location_name.upper()}",
                "message":f"Wind {wind} km/h. Secure tall crops. Delay spraying.","sound":False})
        if code in [1,2] and 20<=temp<=28 and 50<=humidity<=75 and precip==0:
            alerts.append({"level":"success","icon":"✅","title":f"GOOD CONDITIONS — {location_name.upper()}",
                "message":f"Ideal for planting. Temp {temp}°C, humidity {humidity}%.","sound":False})
    except:
        pass
    return alerts

# ── Supabase helpers ───────────────────────────────────────────────────────────
def db_register(username, password, full_name, phone, district, role):
    try:
        existing = supa.table("users").select("username").eq("username", username).execute()
        if existing.data:
            return False, "Username already taken."
        supa.table("users").insert({
            "username": username, "password_hash": hash_password(password),
            "full_name": full_name, "phone": phone, "district": district,
            "role": role, "joined": datetime.now().strftime("%d %b %Y"),
        }).execute()
        return True, "Success"
    except Exception as e:
        return False, str(e)

def db_login(username, password):
    try:
        result = supa.table("users").select("*").eq("username", username).execute()
        if not result.data:
            return False, None, "Username not found. Please register first."
        user = result.data[0]
        if user["password_hash"] == hash_password(password):
            return True, user, "Success"
        return False, None, "Wrong password. Please try again."
    except Exception as e:
        return False, None, str(e)

def db_save_message(room, sender, display_name, encrypted_text):
    try:
        supa.table("chat_messages").insert({
            "room": room, "sender": sender, "display_name": display_name,
            "encrypted_text": encrypted_text,
            "msg_time": datetime.now().strftime("%H:%M"),
            "msg_date": datetime.now().strftime("%d %b %Y"),
        }).execute()
        return True
    except:
        return False

def db_get_messages(room, limit=50):
    try:
        result = supa.table("chat_messages").select("*").eq("room", room).order("created_at").limit(limit).execute()
        return result.data or []
    except:
        return []

def db_save_listing(title, description, seller, phone, location, district, price, type_, tag, image_bytes, username):
    try:
        image_b64 = base64.b64encode(image_bytes).decode() if image_bytes else None
        supa.table("listings").insert({
            "title": title, "description": description, "seller": seller,
            "phone": phone, "location": location, "district": district,
            "price": price, "type": type_, "tag": tag,
            "image_base64": image_b64, "username": username,
            "posted_on": datetime.now().strftime("%d %b %Y"),
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error saving listing: {e}")
        return False

def db_get_listings():
    try:
        result = supa.table("listings").select("*").order("created_at", desc=True).execute()
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
            model="openai/gpt-oss-120b", messages=messages, max_tokens=1200,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

def ask_groq_vision(user_message, image_base64, image_type="image/jpeg"):
    """Analyze a farm photo using Groq vision model"""
    try:
        # Ensure image type is valid
        if image_type not in ["image/jpeg","image/png","image/gif","image/webp"]:
            image_type = "image/jpeg"
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_type};base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": f"You are an expert Ugandan agricultural advisor. {user_message}"
                    }
                ]
            }],
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Vision error: {str(e)}"

def generate_image(description):
    """Generate image using Pollinations.ai — completely free, no API key"""
    try:
        # First improve the prompt with Groq
        prompt_resp = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{
                "role": "user",
                "content": f"Write a short, vivid image generation prompt (max 60 words) for: {description}. Focus on Ugandan farming. Be descriptive about colors, lighting, setting. No harmful content."
            }],
            max_tokens=100,
        )
        improved_prompt = prompt_resp.choices[0].message.content.strip()
        # Clean prompt for URL
        encoded = requests.utils.quote(improved_prompt)
        # Use Pollinations with a seed for consistency
        import random
        seed = random.randint(1, 9999)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=512&seed={seed}&nologo=true&enhance=true"
        return url, improved_prompt
    except Exception as e:
        # Fallback: use description directly
        encoded = requests.utils.quote(description[:200])
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=512&nologo=true"
        return url, description

def get_realtime_info(query):
    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role":"system","content":"You are an expert on Uganda agriculture, climate, and environment with knowledge up to 2026. Give specific, practical, Uganda-focused information."},
                {"role":"user","content":f"Give latest information about: {query}\nFocus on Uganda 2025-2026."}
            ],
            max_tokens=1200,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

# ── Session state ──────────────────────────────────────────────────────────────
DEFAULTS = {
    "current_user": None, "user_data": None,
    "farm_messages": [{"role":"assistant","content":"Hello! I'm your AI Farm Advisor 🌾\n\nI can:\n• Answer farming questions with Uganda context\n• Analyze photos of your crops, soil or pests\n• Generate farm visualisation images\n• Give real-time climate and market info"}],
    "active_room": "general",
    "user_lat": None, "user_lon": None,
    "location_permission": False,
    "weather_data": None, "weather_location": None,
    "last_weather_fetch": None,
    "active_tab": "home",
    "generated_image_url": None,
    "generated_image_prompt": None,
    "diagnosis_result": None,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

WASTE_CATEGORIES = [
    {"name":"Organic / Food Waste","icon":"🍌","color":"#4CAF50","tip":"Compost food scraps into rich soil fertilizer for farms."},
    {"name":"Plastic","icon":"🧴","color":"#2196F3","tip":"Rinse and take to a recycling point near you."},
    {"name":"Electronic Waste","icon":"📱","color":"#9C27B0","tip":"Never dump e-waste. Find certified e-waste collectors."},
    {"name":"Agricultural Waste","icon":"🌿","color":"#FF9800","tip":"Convert crop residues to biochar or biogas — both profitable!"},
    {"name":"Paper & Cardboard","icon":"📦","color":"#795548","tip":"Separate and dry before recycling."},
    {"name":"Glass","icon":"🍶","color":"#00BCD4","tip":"Reuse clean bottles or return them to manufacturers."},
]
CHAT_ROOMS = {
    "general":       {"name":"🌍 General",       "desc":"Open discussion for all farmers"},
    "agriculture":   {"name":"🌾 Agriculture",    "desc":"Crop advice, planting, harvesting"},
    "waste_trading": {"name":"♻️ Waste Trading",  "desc":"Buy & sell agricultural waste"},
    "climate_alerts":{"name":"🌦️ Climate Alerts","desc":"Share local weather updates"},
}

# ── CSS ────────────────────────────────────────────────────────────────────────
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
.section-label{font-family:'Space Mono',monospace;font-size:0.7rem;letter-spacing:3px;text-transform:uppercase;color:#81C784;margin-bottom:4px;}
.card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:20px;margin-bottom:12px;}
.card-green{border-color:rgba(76,175,80,0.25);}
.card-blue{border-color:rgba(33,150,243,0.25);}
.card-orange{border-color:rgba(255,152,0,0.25);}
.card-purple{border-color:rgba(156,39,176,0.25);}
.feature-card{border-radius:16px;padding:18px 16px 6px;margin-bottom:0;}
.feature-card-green{background:rgba(76,175,80,0.06);border:1px solid rgba(76,175,80,0.25);}
.feature-card-blue{background:rgba(33,150,243,0.06);border:1px solid rgba(33,150,243,0.25);}
.feature-card-orange{background:rgba(255,152,0,0.06);border:1px solid rgba(255,152,0,0.25);}
.feature-card-purple{background:rgba(156,39,176,0.06);border:1px solid rgba(156,39,176,0.25);}
.alert-danger{background:rgba(244,67,54,0.15);border:2px solid rgba(244,67,54,0.6);border-radius:12px;padding:14px 18px;margin-bottom:12px;}
.alert-warning{background:rgba(255,152,0,0.1);border:1px solid rgba(255,152,0,0.4);border-radius:12px;padding:14px 18px;margin-bottom:12px;}
.alert-info{background:rgba(33,150,243,0.1);border:1px solid rgba(33,150,243,0.3);border-radius:12px;padding:14px 18px;margin-bottom:12px;}
.alert-success{background:rgba(76,175,80,0.1);border:1px solid rgba(76,175,80,0.3);border-radius:12px;padding:14px 18px;margin-bottom:12px;}
.alert-text{color:#e8f5e9;font-size:0.88rem;line-height:1.6;}
.alert-region{font-family:'Space Mono',monospace;font-size:0.7rem;letter-spacing:1px;font-weight:700;margin-bottom:4px;}
.weather-card{background:rgba(255,255,255,0.04);border:1px solid rgba(33,150,243,0.2);border-radius:16px;padding:20px;margin-bottom:16px;}
.weather-big{font-size:3rem;font-weight:900;color:#64B5F6;font-family:'Space Mono',monospace;}
.weather-label{font-size:0.72rem;color:#546E7A;font-family:'Space Mono',monospace;text-transform:uppercase;letter-spacing:1px;}
.day-card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:8px 4px;text-align:center;margin-bottom:8px;}
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
.loc-banner{background:rgba(33,150,243,0.08);border:1px solid rgba(33,150,243,0.25);border-radius:12px;padding:12px 16px;margin-bottom:16px;font-size:0.82rem;color:#90CAF9;}
.stTextInput>div>div>input{background:rgba(255,255,255,0.05)!important;border:1px solid rgba(168,230,191,0.2)!important;border-radius:10px!important;color:#e8f5e9!important;}
.stButton>button{background:linear-gradient(135deg,#2d7a4f,#4CAF50)!important;border:none!important;border-radius:10px!important;color:#fff!important;font-weight:700!important;font-family:'DM Sans',sans-serif!important;}
div[data-testid="stTabs"] button{color:#81C784!important;font-family:'DM Sans',sans-serif!important;font-weight:700!important;}
.floating-alert{position:fixed;top:80px;right:20px;z-index:9999;background:#1a0a0a;border:2px solid #f44336;border-radius:16px;padding:16px 20px;max-width:300px;box-shadow:0 8px 32px rgba(244,67,54,0.4);animation:slideIn 0.4s ease;}
.floating-alert-warning{position:fixed;top:80px;right:20px;z-index:9999;background:#1a1200;border:2px solid #FF9800;border-radius:16px;padding:16px 20px;max-width:300px;box-shadow:0 8px 32px rgba(255,152,0,0.3);animation:slideIn 0.4s ease;}
@keyframes slideIn{from{transform:translateX(120%);opacity:0;}to{transform:translateX(0);opacity:1;}}
.floating-title{font-weight:800;font-size:0.82rem;color:#f44336;font-family:'Space Mono',monospace;margin-bottom:6px;}
.floating-title-w{font-weight:800;font-size:0.82rem;color:#FF9800;font-family:'Space Mono',monospace;margin-bottom:6px;}
.floating-msg{font-size:0.78rem;color:#e8f5e9;line-height:1.5;}
</style>
""", unsafe_allow_html=True)

GEOLOCATION_JS = """
<script>
function requestLocation() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            function(pos) {
                const url = new URL(window.location);
                url.searchParams.set('lat', pos.coords.latitude.toFixed(6));
                url.searchParams.set('lon', pos.coords.longitude.toFixed(6));
                window.location.href = url.toString();
            },
            function(err) { alert("Location access denied: " + err.message); },
            {enableHighAccuracy:true, timeout:10000}
        );
    }
}
</script>
<button onclick="requestLocation()" style="background:linear-gradient(135deg,#1565C0,#1E88E5);border:none;border-radius:10px;color:#fff;padding:10px 20px;font-weight:700;cursor:pointer;font-family:'DM Sans',sans-serif;font-size:0.85rem;">
📍 Allow Location Access
</button>
"""

ALERT_SOUND_JS = """
<script>
(function(){
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        function beep(f,s,d){
            const o=ctx.createOscillator(),g=ctx.createGain();
            o.connect(g);g.connect(ctx.destination);
            o.frequency.value=f;o.type='sine';
            g.gain.setValueAtTime(0.3,ctx.currentTime+s);
            g.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+s+d);
            o.start(ctx.currentTime+s);o.stop(ctx.currentTime+s+d+0.1);
        }
        beep(880,0,0.2);beep(660,0.25,0.2);beep(880,0.5,0.2);beep(440,0.75,0.5);
    } catch(e){}
})();
</script>
"""

# Navigate to tab via JS
def nav_to_tab_js(tab_label):
    st.components.v1.html(f"""
    <script>
    setTimeout(function(){{
        const tabs = window.parent.document.querySelectorAll('button[role="tab"]');
        for(let t of tabs){{
            if(t.innerText.trim().indexOf("{tab_label}")>=0){{
                t.click(); break;
            }}
        }}
    }}, 400);
    </script>
    """, height=0)

def read_location_from_params():
    try:
        params = st.query_params
        if "lat" in params and "lon" in params:
            lat = float(params["lat"])
            lon = float(params["lon"])
            if lat != 0 and lon != 0:
                st.session_state.user_lat = lat
                st.session_state.user_lon = lon
                st.session_state.location_permission = True
                return True
    except:
        pass
    return False

def fetch_weather(user_data):
    now  = datetime.now()
    last = st.session_state.last_weather_fetch
    if last and (now-last).seconds < 1800 and st.session_state.weather_data:
        return
    if st.session_state.location_permission and st.session_state.user_lat:
        lat, lon = st.session_state.user_lat, st.session_state.user_lon
        st.session_state.weather_location = "Your GPS Location"
    else:
        district = user_data.get("district","Kampala")
        lat, lon = get_coords_for_district(district)
        st.session_state.weather_location = f"{district} District"
    data = get_weather_by_coords(lat, lon)
    if data:
        st.session_state.weather_data = data
        st.session_state.last_weather_fetch = now

def show_floating_alerts(alerts):
    shown = [a for a in alerts if a["level"]=="danger"][:1] or [a for a in alerts if a["level"]=="warning"][:1]
    for alert in shown:
        is_d = alert["level"]=="danger"
        st.markdown(f"""
        <div class="{'floating-alert' if is_d else 'floating-alert-warning'}">
            <div class="{'floating-title' if is_d else 'floating-title-w'}">{alert['icon']} {alert['title']}</div>
            <div class="floating-msg">{alert['message']}</div>
        </div>""", unsafe_allow_html=True)
        if alert.get("sound"):
            st.components.v1.html(ALERT_SOUND_JS, height=0)

# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════
def show_auth():
    st.markdown("""
    <div style="text-align:center;margin-bottom:28px;">
        <h1 style="font-family:'Playfair Display',serif;color:#81C784;font-size:2.4rem;margin:0;">🌍 EcoPulse</h1>
        <p style="font-family:'Space Mono',monospace;font-size:0.65rem;color:#4CAF50;letter-spacing:2px;">ELIAS CREATIONS</p>
        <p style="color:#90A4AE;font-size:0.85rem;margin-top:8px;">Uganda's AI-powered green revolution platform</p>
    </div>""", unsafe_allow_html=True)

    auth_tab1, auth_tab2 = st.tabs(["🔑 Sign In","📝 Register"])

    with auth_tab1:
        st.markdown("<div class='auth-box'>", unsafe_allow_html=True)
        st.markdown("<p class='section-label'>SIGN IN TO ECOPULSE</p>", unsafe_allow_html=True)
        login_user = st.text_input("Username", placeholder="Enter your username", key="login_user")
        login_pass = st.text_input("Password", type="password", placeholder="Enter your password", key="login_pass")
        if st.button("Sign In →", key="signin_btn"):
            uname = login_user.strip().lower().replace(" ","_")
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
        st.markdown("""<br><div style="background:rgba(76,175,80,0.06);border:1px solid rgba(76,175,80,0.15);border-radius:10px;padding:10px 14px;font-size:0.78rem;color:#81C784;">
        💡 New user? Click the <b>Register</b> tab to create your free account.</div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with auth_tab2:
        st.markdown("<div class='auth-box'>", unsafe_allow_html=True)
        st.markdown("<p class='section-label'>CREATE YOUR FREE ACCOUNT</p>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            reg_fname = st.text_input("Full Name *", placeholder="e.g. Nakato Sarah", key="reg_fname")
            reg_uname = st.text_input("Username *", placeholder="e.g. nakato_sarah", key="reg_uname")
            reg_phone = st.text_input("Phone Number *", placeholder="+256 7XX XXXXXX", key="reg_phone")
        with c2:
            reg_dist  = st.text_input("District *", placeholder="e.g. Wakiso", key="reg_dist")
            reg_role  = st.selectbox("I am a *",["Farmer","Agri-business","Recycler","Student","Other"],key="reg_role")
            reg_pass  = st.text_input("Password *", type="password", placeholder="Min 6 characters", key="reg_pass")
        reg_pass2 = st.text_input("Confirm Password *", type="password", placeholder="Repeat password", key="reg_pass2")
        if st.button("Create Account →", key="register_btn"):
            uname = reg_uname.strip().lower().replace(" ","_")
            if not all([reg_fname, reg_uname, reg_phone, reg_dist, reg_pass, reg_pass2]):
                st.warning("⚠️ Please fill all required fields.")
            elif len(reg_pass) < 6:
                st.error("❌ Password must be at least 6 characters.")
            elif reg_pass != reg_pass2:
                st.error("❌ Passwords do not match.")
            else:
                with st.spinner("Creating your account…"):
                    success, msg = db_register(uname, reg_pass, reg_fname, reg_phone, reg_dist, reg_role)
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

    read_location_from_params()
    fetch_weather(user_data)

    # Floating alerts
    if st.session_state.weather_data:
        loc_name = st.session_state.weather_location or user_data.get("district","Uganda")
        alerts = parse_weather_alerts(st.session_state.weather_data, loc_name)
        if alerts:
            show_floating_alerts(alerts)

    # Header
    c_logo, c_user, c_out = st.columns([4,2,1])
    with c_logo:
        st.markdown("<h1 style='font-family:Playfair Display,serif;color:#81C784;margin:0;font-size:1.8rem;'>🌍 EcoPulse</h1>", unsafe_allow_html=True)
        st.markdown("<p style='font-family:Space Mono,monospace;font-size:0.65rem;color:#4CAF50;letter-spacing:2px;margin:0;'>ELIAS CREATION</p>", unsafe_allow_html=True)
    with c_user:
        loc_icon = "📍" if st.session_state.location_permission else "🏘️"
        loc_name = st.session_state.weather_location or user_data.get("district","—")
        st.markdown(f"""<div style="text-align:right;margin-top:8px;">
            <div style="font-size:0.8rem;font-weight:700;color:#81C784;">👤 {user_data['full_name']}</div>
            <div style="font-size:0.65rem;color:#546E7A;font-family:'Space Mono',monospace;">{loc_icon} {loc_name}</div>
        </div>""", unsafe_allow_html=True)
    with c_out:
        if st.button("Sign Out"):
            for k in ["current_user","user_data","weather_data","farm_messages","generated_image_url","diagnosis_result"]:
                st.session_state[k] = None
            st.session_state.active_tab = "home"
            st.rerun()

    st.markdown("<hr style='border-color:rgba(76,175,80,0.15);margin:10px 0 20px;'>", unsafe_allow_html=True)

    tab_home, tab_farm, tab_waste, tab_climate, tab_market, tab_chat = st.tabs([
        "🏠 Home","🌾 Farm AI","♻️ Waste Guide","🌦️ Climate","🤝 Marketplace","💬 Farmer Chat"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # HOME — clickable feature cards
    # ══════════════════════════════════════════════════════════════════════════
    with tab_home:
        st.markdown(f"""
        <div class="hero-box">
            <p class="section-label">CCIC 2026 — Track 2: Climate Tech & Digital Innovation</p>
            <h1 class="hero-title">Welcome back,<br><span class="hero-accent">{user_data['full_name'].split()[0]}</span> 👋</h1>
            <p class="hero-sub">Click any feature card below to get started instantly.</p>
            <span class="badge badge-green">🌾 AgriAI</span>
            <span class="badge badge-blue">♻️ Waste</span>
            <span class="badge badge-orange">🤝 Market</span>
            <span class="badge badge-purple">💬 Chat</span>
        </div>""", unsafe_allow_html=True)

        st.markdown("<p class='section-label' style='margin-bottom:14px;'>FEATURES — CLICK TO OPEN</p>", unsafe_allow_html=True)

        row1_c1, row1_c2 = st.columns(2)
        with row1_c1:
            st.markdown("""<div class="feature-card feature-card-green">
                <div style="font-size:2.2rem;">🌾</div>
                <div style="font-weight:800;color:#fff;font-size:0.95rem;margin:6px 0 4px;">Farm AI Advisor</div>
                <div style="color:#90A4AE;font-size:0.78rem;line-height:1.5;margin-bottom:8px;">Ask AI, diagnose crop photos, generate farm images & get real-time Uganda farming info.</div>
            </div>""", unsafe_allow_html=True)
            if st.button("🌾 Open Farm AI", key="go_farm", use_container_width=True):
                nav_to_tab_js("Farm AI")

        with row1_c2:
            st.markdown("""<div class="feature-card feature-card-blue">
                <div style="font-size:2.2rem;">🌦️</div>
                <div style="font-weight:800;color:#fff;font-size:0.95rem;margin:6px 0 4px;">Real-Time Climate</div>
                <div style="color:#90A4AE;font-size:0.78rem;line-height:1.5;margin-bottom:8px;">Live weather for your location. 7-day forecast, rain & emergency floating alerts with alarm.</div>
            </div>""", unsafe_allow_html=True)
            if st.button("🌦️ Open Climate", key="go_climate", use_container_width=True):
                nav_to_tab_js("Climate")

        st.markdown("<br>", unsafe_allow_html=True)
        row2_c1, row2_c2 = st.columns(2)
        with row2_c1:
            st.markdown("""<div class="feature-card feature-card-orange">
                <div style="font-size:2.2rem;">♻️</div>
                <div style="font-weight:800;color:#fff;font-size:0.95rem;margin:6px 0 4px;">Waste Guide</div>
                <div style="color:#90A4AE;font-size:0.78rem;line-height:1.5;margin-bottom:8px;">AI circular economy tips. Turn any waste category into income in Uganda.</div>
            </div>""", unsafe_allow_html=True)
            if st.button("♻️ Open Waste Guide", key="go_waste", use_container_width=True):
                nav_to_tab_js("Waste Guide")

        with row2_c2:
            st.markdown("""<div class="feature-card feature-card-orange">
                <div style="font-size:2.2rem;">🤝</div>
                <div style="font-weight:800;color:#fff;font-size:0.95rem;margin:6px 0 4px;">Green Marketplace</div>
                <div style="color:#90A4AE;font-size:0.78rem;line-height:1.5;margin-bottom:8px;">Buy & sell green products with photos. Verified seller details for full traceability.</div>
            </div>""", unsafe_allow_html=True)
            if st.button("🤝 Open Marketplace", key="go_market", use_container_width=True):
                nav_to_tab_js("Marketplace")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""<div class="feature-card feature-card-purple" style="padding:18px 16px 8px;">
            <div style="font-size:2.2rem;">💬</div>
            <div style="font-weight:800;color:#fff;font-size:0.95rem;margin:6px 0 4px;">Encrypted Farmer Chat</div>
            <div style="color:#90A4AE;font-size:0.78rem;line-height:1.5;margin-bottom:8px;">🔒 End-to-end encrypted group chat rooms. Connect with farmers, share tips & trade leads securely. All messages saved permanently.</div>
        </div>""", unsafe_allow_html=True)
        if st.button("💬 Open Farmer Chat", key="go_chat", use_container_width=True):
            nav_to_tab_js("Farmer Chat")

        st.markdown("""
        <div class="quote-box" style="margin-top:20px;">
            <p class="section-label">THEME 2026</p>
            <p style="font-family:'Playfair Display',serif;font-style:italic;color:#c8e6c9;font-size:1rem;line-height:1.7;margin:6px 0;">
            "Empowering Farmers on smart farming"</p>
            <p style="color:#66BB6A;font-size:0.8rem;margin:0;">ELIAS CREATIONS</p>
        </div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FARM AI
    # ══════════════════════════════════════════════════════════════════════════
    with tab_farm:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1a4731,#2d7a4f);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
            <p class="section-label" style="color:#a8e6bf;">AI-POWERED · REAL-TIME · IMAGE GENERATION</p>
            <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">🌾 Farm Advisory</h2>
            <p style="color:#a8e6bf;font-size:0.82rem;margin:0;">Ask questions · Upload crop photos for diagnosis · Generate farm images</p>
        </div>""", unsafe_allow_html=True)

        farm_sub1, farm_sub2, farm_sub3 = st.tabs(["💬 Ask AI","📷 Photo Diagnosis","🎨 Generate Image"])

        # ── ASK AI ──────────────────────────────────────────────────────────────
        with farm_sub1:
            col_rt1, col_rt2 = st.columns(2)
            with col_rt1:
                if st.button("🌍 Uganda Farming News", key="btn_news"):
                    with st.spinner("Fetching…"):
                        info = get_realtime_info("current farming season, crop prices, and weather in Uganda 2026")
                    st.session_state.farm_messages.append({"role":"user","content":"Latest Uganda farming news?"})
                    st.session_state.farm_messages.append({"role":"assistant","content":f"🌍 Real-Time Uganda Update:\n\n{info}"})
                    st.rerun()
            with col_rt2:
                if st.button("📈 Crop Market Prices", key="btn_prices"):
                    with st.spinner("Fetching…"):
                        prices = get_realtime_info("current market prices for maize, beans, tomatoes, coffee in Uganda 2025-2026")
                    st.session_state.farm_messages.append({"role":"user","content":"Current crop prices in Uganda?"})
                    st.session_state.farm_messages.append({"role":"assistant","content":f"📈 Uganda Crop Market Prices:\n\n{prices}"})
                    st.rerun()

            for msg in st.session_state.farm_messages:
                css = "chat-ai" if msg["role"]=="assistant" else "chat-user"
                pfx = "🤖" if msg["role"]=="assistant" else "👤"
                st.markdown(f"<div class='{css}'>{pfx} {msg['content']}</div>", unsafe_allow_html=True)

            with st.form("farm_form", clear_on_submit=True):
                user_input = st.text_input("", placeholder="e.g. What crops to plant now in Central Uganda?", label_visibility="collapsed")
                submitted  = st.form_submit_button("Send ↑")

            if submitted and user_input.strip():
                st.session_state.farm_messages.append({"role":"user","content":user_input})
                history = [{"role":m["role"],"content":m["content"]} for m in st.session_state.farm_messages[:-1]]
                with st.spinner("Getting AI advice…"):
                    reply = ask_groq(
                        "You are an expert Ugandan agricultural advisor. Give practical, actionable advice with current Uganda 2025-2026 context. Mention specific crops, regions, climate-smart practices.",
                        user_input, history
                    )
                st.session_state.farm_messages.append({"role":"assistant","content":reply})
                st.rerun()

            if st.button("🗑️ Clear Chat", key="clear_chat"):
                st.session_state.farm_messages = [st.session_state.farm_messages[0]]
                st.rerun()

        # ── PHOTO DIAGNOSIS ─────────────────────────────────────────────────────
        with farm_sub2:
            st.markdown("<div class='image-tip'>📌 Upload a clear photo of your crop, leaves, soil or pest. The AI will analyze it and give you specific Uganda-context treatment advice.</div>", unsafe_allow_html=True)

            farm_image = st.file_uploader("Upload farm photo", type=["jpg","jpeg","png"], key="farm_img", label_visibility="collapsed")

            if farm_image:
                col_img, col_info = st.columns([1,2])
                with col_img:
                    st.image(farm_image, use_container_width=True, caption="Uploaded photo")
                with col_info:
                    diag_q = st.text_input(
                        "What do you want to know about this photo?",
                        placeholder="e.g. What disease is on my maize leaves? How do I treat it?",
                        key="diag_q"
                    )
                    if st.button("🔬 Analyze Photo", key="analyze_btn"):
                        with st.spinner("AI is analyzing your photo…"):
                            farm_image.seek(0)
                            img_bytes = farm_image.read()
                            img_b64   = base64.b64encode(img_bytes).decode("utf-8")
                            # Normalize image type
                            raw_type  = farm_image.type or "image/jpeg"
                            if "png" in raw_type:
                                img_type = "image/png"
                            elif "gif" in raw_type:
                                img_type = "image/gif"
                            else:
                                img_type = "image/jpeg"

                            question = diag_q.strip() if diag_q.strip() else "Analyze this farm photo carefully. Identify any diseases, pests, nutrient deficiencies or soil problems. Give specific treatment and prevention advice relevant to Uganda farmers."

                            result = ask_groq_vision(question, img_b64, img_type)
                            st.session_state.diagnosis_result = result

            if st.session_state.diagnosis_result:
                st.markdown(f"""
                <div class="card card-green" style="margin-top:14px;">
                    <p class="section-label">📸 AI DIAGNOSIS RESULT</p>
                    <div style="color:#c8e6c9;font-size:0.9rem;line-height:1.8;white-space:pre-wrap;">{st.session_state.diagnosis_result}</div>
                </div>""", unsafe_allow_html=True)
                if st.button("🗑️ Clear Diagnosis", key="clear_diag"):
                    st.session_state.diagnosis_result = None
                    st.rerun()

        # ── IMAGE GENERATION ────────────────────────────────────────────────────
        with farm_sub3:
            st.markdown("""<div class="image-tip">
            🎨 Describe any farm scene and AI will generate a realistic image for you. Works best with specific descriptions.
            </div>""", unsafe_allow_html=True)

            quick_prompt = st.selectbox("Choose a quick example or type your own below:", [
                "— Type your own description below —",
                "Healthy maize farm in Uganda with green rows of tall plants",
                "Drip irrigation system on a small Uganda farm",
                "Severe soil erosion on a hillside farm Uganda",
                "Organic compost pit beside a Uganda farmhouse",
                "Banana plantation in Western Uganda lush green",
                "Coffee farm in Bugisu region Uganda sunrise",
                "Tomato greenhouse farming in Uganda",
                "Ugandan farmer applying organic fertilizer in the field",
                "Flooded farmland after heavy rains Uganda",
            ], key="quick_img")

            custom_prompt = st.text_area(
                "Or describe your own image:",
                placeholder="e.g. A healthy maize farm in Central Uganda during the rainy season, green crops, morning sunlight...",
                height=80, key="custom_img_prompt"
            )

            if st.button("🎨 Generate Farm Image", key="gen_img_btn", use_container_width=True):
                # Determine which prompt to use
                if custom_prompt.strip():
                    final_prompt = custom_prompt.strip()
                elif quick_prompt != "— Type your own description below —":
                    final_prompt = quick_prompt
                else:
                    final_prompt = None

                if not final_prompt:
                    st.warning("Please choose an example or type a description.")
                else:
                    with st.spinner("🎨 Generating image… this takes 10-20 seconds…"):
                        url, used_prompt = generate_image(final_prompt)
                        st.session_state.generated_image_url    = url
                        st.session_state.generated_image_prompt = used_prompt

            # Display generated image
            if st.session_state.generated_image_url:
                st.markdown(f"""
                <div class="card card-green" style="margin-top:12px;">
                    <p class="section-label">🎨 GENERATED IMAGE</p>
                    <p style="color:#90A4AE;font-size:0.75rem;margin-bottom:10px;font-style:italic;">"{st.session_state.generated_image_prompt}"</p>
                </div>""", unsafe_allow_html=True)
                st.image(st.session_state.generated_image_url, use_container_width=True)
                st.markdown(f"[📥 Download Image]({st.session_state.generated_image_url})")
                if st.button("🔄 Generate New Image", key="regen_btn"):
                    st.session_state.generated_image_url = None
                    st.session_state.generated_image_prompt = None
                    st.rerun()

    # ── WASTE GUIDE ─────────────────────────────────────────────────────────────
    with tab_waste:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1a2a1a,#2a4a2a);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
            <p class="section-label" style="color:#81C784;">CIRCULAR ECONOMY</p>
            <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">♻️ Waste Management Guide</h2>
        </div>""", unsafe_allow_html=True)

        selected_waste = st.selectbox("Choose a waste category:", options=[w["name"] for w in WASTE_CATEGORIES],
            format_func=lambda x: f"{next(w['icon'] for w in WASTE_CATEGORIES if w['name']==x)}  {x}")
        chosen = next(w for w in WASTE_CATEGORIES if w["name"]==selected_waste)
        st.markdown(f"""<div class="card" style="border-color:{chosen['color']}44;margin-top:10px;">
            <div style="font-size:2.5rem;margin-bottom:8px;">{chosen['icon']}</div>
            <div style="font-weight:800;color:{chosen['color']};font-size:1rem;margin-bottom:6px;">{chosen['name']}</div>
            <div style="color:#c8e6c9;font-size:0.85rem;line-height:1.6;">{chosen['tip']}</div>
        </div>""", unsafe_allow_html=True)

        cw1, cw2 = st.columns(2)
        with cw1:
            if st.button("🤖 Get AI Tips", key="waste_ai"):
                with st.spinner("Generating tips…"):
                    tip = ask_groq("Circular economy expert for Uganda. Give 3 practical numbered tips showing income opportunities. Max 2 sentences each.",f"Tips for: {selected_waste}")
                st.markdown(f"""<div class="card card-green" style="margin-top:12px;">
                    <p class="section-label">AI TIPS — {selected_waste.upper()}</p>
                    <div style="color:#c8e6c9;font-size:0.9rem;line-height:1.8;white-space:pre-wrap;">{tip}</div>
                </div>""", unsafe_allow_html=True)
        with cw2:
            if st.button("🌍 Real-Time Market Info", key="waste_market"):
                with st.spinner("Fetching…"):
                    info = get_realtime_info(f"current market for {selected_waste} recycling in Uganda 2025-2026")
                st.markdown(f"""<div class="realtime-box" style="margin-top:12px;">
                    <p class="section-label" style="color:#64B5F6;">MARKET INFO</p>
                    <div style="color:#c8e6c9;font-size:0.9rem;line-height:1.8;white-space:pre-wrap;">{info}</div>
                </div>""", unsafe_allow_html=True)

        cols = st.columns(3)
        for i, w in enumerate(WASTE_CATEGORIES):
            with cols[i%3]:
                st.markdown(f"""<div style="text-align:center;background:rgba(255,255,255,0.04);border:1px solid {w['color']}33;border-radius:12px;padding:14px 8px;margin-bottom:8px;">
                    <div style="font-size:1.8rem;">{w['icon']}</div>
                    <div style="font-size:0.72rem;font-weight:700;color:{w['color']};margin-top:4px;">{w['name']}</div>
                </div>""", unsafe_allow_html=True)

    # ── CLIMATE ─────────────────────────────────────────────────────────────────
    with tab_climate:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#0d2137,#1a3a5c);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
            <p class="section-label" style="color:#64B5F6;">REAL-TIME · LOCATION-BASED</p>
            <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">🌦️ Climate Dashboard</h2>
            <p style="color:#64B5F6;font-size:0.82rem;margin:0;">Live weather data for your location with automatic alerts.</p>
        </div>""", unsafe_allow_html=True)

        if not st.session_state.location_permission:
            st.markdown(f"""<div class="loc-banner">
                📍 Currently showing weather for <b>{user_data.get('district','your district')}</b> (from your profile).
                Grant precise location for more accurate real-time data.
            </div>""", unsafe_allow_html=True)
            st.components.v1.html(GEOLOCATION_JS, height=60)
        else:
            st.markdown(f"""<div style="background:rgba(76,175,80,0.08);border:1px solid rgba(76,175,80,0.25);border-radius:10px;padding:10px 14px;margin-bottom:16px;font-size:0.82rem;color:#81C784;">
                📍 <b>GPS Active</b> — Showing real-time weather for your exact location.
                <span style="font-size:0.7rem;color:#546E7A;margin-left:8px;">{st.session_state.user_lat:.4f}, {st.session_state.user_lon:.4f}</span>
            </div>""", unsafe_allow_html=True)

        if st.button("🔄 Refresh Weather"):
            st.session_state.last_weather_fetch = None
            fetch_weather(user_data)
            st.rerun()

        wd       = st.session_state.weather_data
        loc_name = st.session_state.weather_location or user_data.get("district","Uganda")

        if wd:
            current   = wd.get("current",{})
            daily     = wd.get("daily",{})
            temp      = current.get("temperature_2m","—")
            precip    = current.get("precipitation",0)
            humidity  = current.get("relative_humidity_2m","—")
            wind      = current.get("windspeed_10m","—")
            code      = current.get("weathercode",0)
            condition = WEATHER_CODES.get(code,"Unknown")

            st.markdown(f"""
            <div class="weather-card">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
                    <div>
                        <div class="weather-label">NOW · {loc_name.upper()}</div>
                        <div class="weather-big">{temp}°C</div>
                        <div style="color:#90CAF9;font-size:0.9rem;margin-top:4px;">{condition}</div>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:8px;">
                        <div style="text-align:center;"><div style="font-size:1.3rem;">🌧️</div>
                            <div style="font-family:'Space Mono',monospace;font-weight:700;color:#64B5F6;">{precip}mm</div>
                            <div class="weather-label">Rain</div></div>
                        <div style="text-align:center;"><div style="font-size:1.3rem;">💧</div>
                            <div style="font-family:'Space Mono',monospace;font-weight:700;color:#64B5F6;">{humidity}%</div>
                            <div class="weather-label">Humidity</div></div>
                        <div style="text-align:center;"><div style="font-size:1.3rem;">💨</div>
                            <div style="font-family:'Space Mono',monospace;font-weight:700;color:#64B5F6;">{wind}km/h</div>
                            <div class="weather-label">Wind</div></div>
                        <div style="text-align:center;"><div style="font-size:1.3rem;">🌡️</div>
                            <div style="font-family:'Space Mono',monospace;font-weight:700;color:#64B5F6;">{temp}°C</div>
                            <div class="weather-label">Temp</div></div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)

            # Alerts
            alerts = parse_weather_alerts(wd, loc_name)
            st.markdown("<p class='section-label'>⚠️ ACTIVE ALERTS FOR YOUR LOCATION</p>", unsafe_allow_html=True)
            if alerts:
                level_colors={"danger":"#f44336","warning":"#FF9800","info":"#2196F3","success":"#4CAF50"}
                for alert in alerts:
                    color = level_colors.get(alert["level"],"#81C784")
                    st.markdown(f"""<div class="alert-{alert['level']}">
                        <div class="alert-region" style="color:{color};">{alert['icon']} {alert['title']}</div>
                        <div class="alert-text">{alert['message']}</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown("""<div class="alert-success">
                    <div class="alert-region" style="color:#4CAF50;">✅ NO ACTIVE ALERTS</div>
                    <div class="alert-text">Conditions are normal. No weather emergencies detected.</div>
                </div>""", unsafe_allow_html=True)

            # 7-day forecast
            if daily.get("time"):
                st.markdown("<br><p class='section-label'>7-DAY FORECAST</p>", unsafe_allow_html=True)
                days   = daily["time"][:7]
                t_max  = daily.get("temperature_2m_max",[0]*7)[:7]
                t_min  = daily.get("temperature_2m_min",[0]*7)[:7]
                rain   = daily.get("precipitation_sum",[0]*7)[:7]
                pcodes = daily.get("weathercode",[0]*7)[:7]
                rprob  = daily.get("precipitation_probability_max",[0]*7)[:7]
                cols7  = st.columns(7)
                for i,(day,tmax,tmin,r,wc,rp) in enumerate(zip(days,t_max,t_min,rain,pcodes,rprob)):
                    try: day_str=datetime.strptime(day,"%Y-%m-%d").strftime("%a\n%d")
                    except: day_str=day
                    emoji = "⛈️" if wc>=95 else ("🌧️" if wc>=61 else ("🌦️" if wc>=51 else ("☁️" if wc>=2 else "☀️")))
                    with cols7[i]:
                        st.markdown(f"""<div class="day-card">
                            <div style="font-size:0.65rem;color:#546E7A;font-family:'Space Mono',monospace;white-space:pre;">{day_str}</div>
                            <div style="font-size:1.3rem;margin:3px 0;">{emoji}</div>
                            <div style="font-size:0.78rem;font-weight:700;color:#fff;">{tmax:.0f}°</div>
                            <div style="font-size:0.65rem;color:#546E7A;">{tmin:.0f}°</div>
                            <div style="font-size:0.62rem;color:#64B5F6;margin-top:3px;">{r:.1f}mm</div>
                            <div style="font-size:0.6rem;color:#90CAF9;">{rp}%🌧</div>
                        </div>""", unsafe_allow_html=True)

                # Charts
                st.markdown("<br><p class='section-label'>RAINFALL FORECAST (7 DAYS)</p>", unsafe_allow_html=True)
                chart_df = pd.DataFrame({
                    "Day":[datetime.strptime(d,"%Y-%m-%d").strftime("%a %d") for d in daily["time"][:7]],
                    "Rainfall (mm)":daily["precipitation_sum"][:7]
                }).set_index("Day")
                st.bar_chart(chart_df, color="#1E88E5", height=200)

                st.markdown("<p class='section-label'>TEMPERATURE FORECAST</p>", unsafe_allow_html=True)
                temp_df = pd.DataFrame({
                    "Day":[datetime.strptime(d,"%Y-%m-%d").strftime("%a %d") for d in daily["time"][:7]],
                    "Max °C":daily.get("temperature_2m_max",[])[:7],
                    "Min °C":daily.get("temperature_2m_min",[])[:7],
                }).set_index("Day")
                st.line_chart(temp_df, color=["#FF5722","#2196F3"], height=200)
        else:
            st.warning("Could not load weather data. Check your internet connection and try refreshing.")

    # ── MARKETPLACE — images saved to Supabase ───────────────────────────────
    with tab_market:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#2d1a00,#5d3a00);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
            <p class="section-label" style="color:#FFB74D;">GREEN ECONOMY · VERIFIED SELLERS · IMAGES SAVED</p>
            <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">🤝 Marketplace</h2>
            <p style="color:#FFB74D;font-size:0.82rem;margin:0;">Product photos & seller details saved permanently in database.</p>
        </div>""", unsafe_allow_html=True)

        filter_type = st.radio("Filter:", ["All","Selling 🟢","Buying 🔵"], horizontal=True)

        # Load from Supabase
        db_listings = db_get_listings()

        # Default listings if DB empty
        default_listings = [
            {"title":"Organic Compost — 50kg bags","seller":"Kakooza Farms","phone":"+256 772 123456","location":"Wakiso","district":"Wakiso","price":"UGX 25,000","type":"sell","tag":"Waste-to-Value","description":"High quality organic compost made from food waste.","image_base64":None},
            {"title":"Solar Water Pump — rental","seller":"GreenTech Hub","phone":"+256 701 234567","location":"Kampala","district":"Kampala","price":"UGX 15,000/day","type":"sell","tag":"Clean Energy","description":"Portable solar-powered water pump for irrigation.","image_base64":None},
            {"title":"Wanted: Crop Residue","seller":"BioGas Uganda","phone":"+256 754 345678","location":"Jinja","district":"Jinja","price":"UGX 8,000/bale","type":"buy","tag":"Circular Economy","description":"We buy maize stalks in bulk for biogas production.","image_base64":None},
            {"title":"Surplus Tomatoes — urgent sale","seller":"Nakato Agri","phone":"+256 782 456789","location":"Mbarara","district":"Mbarara","price":"UGX 10,000/crate","type":"sell","tag":"Fresh Produce","description":"Fresh tomatoes harvested this week.","image_base64":None},
        ]
        all_listings = db_listings if db_listings else default_listings

        for listing in all_listings:
            type_val = listing.get("type","sell")
            if filter_type=="Selling 🟢" and type_val!="sell": continue
            if filter_type=="Buying 🔵"  and type_val!="buy":  continue

            badge_class = "sell-badge" if type_val=="sell" else "buy-badge"
            badge_text  = "SELL"       if type_val=="sell" else "BUY"

            # Show image if stored
            img_b64 = listing.get("image_base64")
            if img_b64:
                try:
                    img_bytes = base64.b64decode(img_b64)
                    st.image(img_bytes, use_container_width=True, caption=listing["title"])
                except:
                    st.markdown("""<div style="background:rgba(255,255,255,0.03);border:1px dashed rgba(255,255,255,0.1);border-radius:10px 10px 0 0;padding:16px;text-align:center;color:#546E7A;font-size:0.8rem;">📷 Image unavailable</div>""", unsafe_allow_html=True)
            else:
                st.markdown("""<div style="background:rgba(255,255,255,0.03);border:1px dashed rgba(255,255,255,0.1);border-radius:10px 10px 0 0;padding:16px;text-align:center;color:#546E7A;font-size:0.8rem;">📷 No photo uploaded</div>""", unsafe_allow_html=True)

            st.markdown(f"""
            <div class="market-card" style="border-radius:0 0 14px 14px;border-top:none;">
                <div class="market-body">
                    <span class="{badge_class}">{badge_text}</span>
                    <div class="market-title">{listing['title']}</div>
                    <div class="market-meta">{listing.get('description','')}</div>
                    <div><span class="market-price">{listing['price']}</span><span class="market-tag">{listing.get('tag','')}</span></div>
                </div>
                <div class="seller-info">
                    👤 <strong>{listing['seller']}</strong>
                    <span class="verified-badge">✓ SELLER</span>
                    &nbsp;&nbsp;📞 {listing.get('phone','N/A')}
                    &nbsp;&nbsp;📍 {listing.get('district','N/A')} District
                    &nbsp;&nbsp;📅 {listing.get('posted_on','')}
                </div>
            </div><br>""", unsafe_allow_html=True)

        # Post new listing
        st.markdown("<p class='section-label'>POST A NEW LISTING</p>", unsafe_allow_html=True)
        with st.expander("➕ Add your listing with photo"):
            new_title = st.text_input("Title *", placeholder="e.g. Fresh Maize — 100kg")
            new_desc  = st.text_area("Description *", height=70)
            mc1, mc2  = st.columns(2)
            with mc1:
                new_type     = st.selectbox("Type *", ["Selling","Buying"])
                new_price    = st.text_input("Price (UGX) *")
                new_tag      = st.selectbox("Category *", ["Fresh Produce","Waste-to-Value","Clean Energy","AgriTech","Circular Economy","Recycling","Other"])
            with mc2:
                new_location = st.text_input("Village / Area *")
                new_district = st.text_input("District *")
                new_phone    = st.text_input("Phone *", value=user_data["phone"])
            new_image = st.file_uploader("Product Photo (saved permanently)", type=["jpg","jpeg","png"], key="new_img")
            if new_image:
                st.image(new_image, width=200, caption="Preview")

            if st.button("📤 Submit Listing", key="submit_listing"):
                if new_title and new_price and new_desc:
                    img_bytes = None
                    if new_image:
                        new_image.seek(0)
                        img_bytes = new_image.read()
                    price_str = f"UGX {new_price}" if not new_price.startswith("UGX") else new_price
                    saved = db_save_listing(
                        new_title, new_desc, user_data["full_name"],
                        new_phone, new_location, new_district,
                        price_str, "sell" if new_type=="Selling" else "buy",
                        new_tag, img_bytes, user
                    )
                    if saved:
                        st.success("✅ Listing posted and saved to database! Refresh to see it.")
                        st.rerun()
                else:
                    st.warning("Please fill in all required fields.")

    # ── FARMER CHAT ─────────────────────────────────────────────────────────────
    with tab_chat:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1a0a2e,#2d1a4f);border-radius:16px;padding:20px 22px;margin-bottom:20px;">
            <p class="section-label" style="color:#CE93D8;">END-TO-END ENCRYPTED · SAVED TO DATABASE</p>
            <h2 style="font-family:'Playfair Display',serif;color:#fff;margin:4px 0;font-size:1.5rem;">💬 Farmer Chat Rooms</h2>
            <p style="color:#CE93D8;font-size:0.82rem;margin:0;">🔒 All messages encrypted and saved. History always available.</p>
        </div>""", unsafe_allow_html=True)

        st.markdown("<p class='section-label'>CHOOSE A ROOM</p>", unsafe_allow_html=True)
        room_cols = st.columns(2)
        for idx,(room_key,room_info) in enumerate(CHAT_ROOMS.items()):
            with room_cols[idx%2]:
                is_active = st.session_state.active_room==room_key
                if st.button(f"{'✅ ' if is_active else ''}{room_info['name']}", key=f"room_{room_key}", help=room_info['desc']):
                    st.session_state.active_room = room_key
                    st.rerun()

        active_room = st.session_state.active_room
        room_info   = CHAT_ROOMS[active_room]
        st.markdown(f"""<div style="margin:16px 0 10px;">
            <span style="font-size:1rem;font-weight:800;color:#fff;">{room_info['name']}</span>
            <span style="font-size:0.7rem;color:#CE93D8;font-family:'Space Mono',monospace;margin-left:10px;">🔒 ENCRYPTED</span>
        </div>""", unsafe_allow_html=True)

        messages = db_get_messages(active_room, limit=60)
        if not messages:
            st.markdown("""<div style="text-align:center;padding:40px 20px;color:#546E7A;font-size:0.85rem;">
                💬 No messages yet. Be the first to say something!</div>""", unsafe_allow_html=True)
        else:
            for msg in messages:
                is_me     = msg["sender"]==user
                decrypted = decrypt_message(msg["encrypted_text"])
                if is_me:
                    st.markdown(f"""<div style="display:flex;flex-direction:column;align-items:flex-end;margin-bottom:8px;">
                        <div class="msg-bubble-me">{decrypted}
                            <div class="msg-time">🔒 {msg['msg_time']} · {msg['msg_date']}</div>
                        </div></div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""<div style="display:flex;flex-direction:column;align-items:flex-start;margin-bottom:8px;">
                        <div class="msg-name">{msg['display_name']}</div>
                        <div class="msg-bubble-other">{decrypted}
                            <div class="msg-time">🔒 {msg['msg_time']} · {msg['msg_date']}</div>
                        </div></div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        with st.form(f"chat_form_{active_room}", clear_on_submit=True):
            ci, cs = st.columns([5,1])
            with ci:
                new_msg = st.text_input("", placeholder=f"Message {room_info['name']}… (encrypted 🔒)", label_visibility="collapsed")
            with cs:
                send_btn = st.form_submit_button("Send")

        if send_btn and new_msg.strip():
            db_save_message(active_room, user, user_data["full_name"], encrypt_message(new_msg.strip()))
            st.rerun()

        if st.button("🔄 Refresh Messages", key="refresh_chat"):
            st.rerun()

        st.markdown("""<div style="background:rgba(156,39,176,0.06);border:1px solid rgba(156,39,176,0.15);border-radius:10px;padding:10px 14px;margin-top:12px;font-size:0.75rem;color:#CE93D8;text-align:center;">
        🔒 Messages are end-to-end encrypted and saved securely to the database.</div>""", unsafe_allow_html=True)

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
ECOPULSE · Elias Creations · 0705046024 · POWERED BY GROQ + SUPABASE + OPEN-METEO
</p>""", unsafe_allow_html=True)
