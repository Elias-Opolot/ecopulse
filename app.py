import streamlit as st
from groq import Groq
from supabase import create_client, Client
import pandas as pd
import base64 as b64lib
import hashlib
import hmac
import html
import requests
import random
import os
from datetime import datetime
from pathlib import Path

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="EcoPulse",
    page_icon=":herb:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Logo helper ────────────────────────────────────────────────────────────────
# Put your logo file in the repo root as one of these names:
#   logo.png, logo.jpg, logo.jpeg, logo.webp, logo.svg
# Or under assets/logo.png
_LOGO_CANDIDATES = [
    "logo.png", "logo.jpg", "logo.jpeg", "logo.webp", "logo.svg",
    "assets/logo.png", "assets/logo.jpg", "assets/logo.webp",
    "static/logo.png", "images/logo.png",
]

def find_logo_path():
    for name in _LOGO_CANDIDATES:
        p = Path(name)
        if p.is_file():
            return str(p)
    # Also search next to this script
    here = Path(__file__).resolve().parent if "__file__" in dir() else Path.cwd()
    for name in _LOGO_CANDIDATES:
        p = here / name
        if p.is_file():
            return str(p)
    return None

def logo_as_data_uri(path, max_height_px=48):
    """Return a data-URI for embedding logo in HTML, or None."""
    try:
        data = Path(path).read_bytes()
        suffix = Path(path).suffix.lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }.get(suffix, "image/png")
        b64 = b64lib.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None

LOGO_PATH = find_logo_path()
LOGO_DATA_URI = logo_as_data_uri(LOGO_PATH) if LOGO_PATH else None

# ── Clients & secrets (graceful failure) ───────────────────────────────────────
def _get_secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return default

GROQ_API_KEY = _get_secret("GROQ_API_KEY")
SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_KEY = _get_secret("SUPABASE_KEY")
SECRET_KEY   = _get_secret("CHAT_SECRET", "ecopulse-ccic-2026")
PEXELS_KEY   = _get_secret("PEXELS_API_KEY", "")

if not GROQ_API_KEY:
    st.error("Missing GROQ_API_KEY in Streamlit secrets. App cannot start.")
    st.stop()
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing SUPABASE_URL or SUPABASE_KEY in Streamlit secrets. App cannot start.")
    st.stop()

groq_client  = Groq(api_key=GROQ_API_KEY)
supa: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TEXT_MODEL   = "openai/gpt-oss-120b"
# Official Groq vision model: https://console.groq.com/docs/vision
VISION_MODEL = "qwen/qwen3.8-27b"

# ── Security helpers ───────────────────────────────────────────────────────────
def escape(text):
    """HTML-escape user content before inserting into unsafe_allow_html."""
    if text is None:
        return ""
    return html.escape(str(text), quote=True)

def render_ai_response(text, title=None, kind="success"):
    """Show AI text as proper Markdown (bold, lists, tables) inside a styled box."""
    if not text:
        return
    # Soft-clean common raw artifacts without destroying real markdown
    cleaned = str(text).strip()
    # Prefer Streamlit's markdown renderer over escaped HTML
    box_class = {
        "success": "ep-alert ep-alert-success",
        "info": "ep-alert ep-alert-info",
        "ai": "chat-ai",
    }.get(kind, "ep-alert ep-alert-success")
    if title:
        st.markdown(
            f'<div class="{box_class}"><div class="ep-alert-title">{escape(title)}</div></div>',
            unsafe_allow_html=True,
        )
    elif kind == "ai":
        st.markdown('<div class="chat-ai"><strong>Advisor</strong></div>', unsafe_allow_html=True)
    st.markdown(cleaned)

def encrypt_message(text):
    """Simple obfuscation (NOT real E2E encryption). Shared secret only."""
    if not text:
        return ""
    key_bytes = (SECRET_KEY * ((len(text) // len(SECRET_KEY)) + 1)).encode()[:len(text)]
    encrypted = bytes([ord(c) ^ k for c, k in zip(text, key_bytes)])
    return b64lib.b64encode(encrypted).decode()

def decrypt_message(token):
    try:
        encrypted = b64lib.b64decode(token.encode())
        key_bytes = (SECRET_KEY * ((len(encrypted) // len(SECRET_KEY)) + 1)).encode()[:len(encrypted)]
        return bytes([b ^ k for b, k in zip(encrypted, key_bytes)]).decode()
    except Exception:
        return "[could not decrypt message]"

def hash_password(pw):
    """PBKDF2-HMAC-SHA256 with fixed app salt. Better than plain SHA256.
    For production prefer bcrypt/argon2 with a dedicated library."""
    salt = (SECRET_KEY + "ecopulse-salt").encode()
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 120000).hex()

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
    except Exception:
        return None

UGANDA_DISTRICTS = {
    "kampala": (0.3476, 32.5825), "wakiso": (0.3988, 32.4553), "mukono": (0.3536, 32.7554),
    "jinja": (0.4478, 33.2026), "mbarara": (-0.6072, 30.6545), "gulu": (2.7748, 32.2990),
    "lira": (2.2499, 32.8997), "arua": (3.0200, 30.9110), "fort portal": (0.6710, 30.2750),
    "masaka": (-0.3333, 31.7333), "kabale": (-1.2500, 29.9833), "soroti": (1.7148, 33.6112),
    "mbale": (1.0806, 34.1750), "tororo": (0.6930, 34.1808), "hoima": (1.4347, 31.3522),
    "kasese": (0.1833, 30.0833), "iganga": (0.6090, 33.4685), "bushenyi": (-0.5500, 30.1833),
    "ngora": (1.4833, 33.7667), "serere": (1.5000, 33.5500), "pallisa": (1.1333, 33.7167),
    "kumi": (1.4600, 33.9333), "kapchorwa": (1.4000, 34.4500), "bukedea": (1.3500, 34.0667),
}

def get_coords_for_district(district):
    key = district.lower().strip()
    if key in UGANDA_DISTRICTS:
        return UGANDA_DISTRICTS[key]
    try:
        r = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={district}+Uganda&count=1&language=en&format=json",
            timeout=8,
        )
        data = r.json()
        if data.get("results"):
            res = data["results"][0]
            return res["latitude"], res["longitude"]
    except Exception:
        pass
    return (1.3733, 32.2903)

WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm + hail", 99: "Thunderstorm + heavy hail",
}

def parse_weather_alerts(weather_data, location_name):
    alerts = []
    if not weather_data:
        return alerts
    try:
        current = weather_data.get("current", {})
        code = current.get("weathercode", 0)
        temp = current.get("temperature_2m", 0)
        precip = current.get("precipitation", 0)
        wind = current.get("windspeed_10m", 0)
        humidity = current.get("relative_humidity_2m", 0)
        if code in [61, 63, 65, 80, 81, 82, 95, 96, 99] or precip > 5:
            alerts.append({
                "level": "danger",
                "title": f"HEAVY RAIN — {location_name.upper()}",
                "message": f"Heavy rainfall ({precip}mm). Delay planting, secure crops and livestock.",
                "sound": True,
            })
        elif code in [51, 53, 55] or precip > 0.5:
            alerts.append({
                "level": "warning",
                "title": f"RAIN INCOMING — {location_name.upper()}",
                "message": "Light to moderate rain expected. Protect stored produce.",
                "sound": False,
            })
        if code in [95, 96, 99]:
            alerts.append({
                "level": "danger",
                "title": f"THUNDERSTORM — {location_name.upper()}",
                "message": "Severe thunderstorm. Stay indoors, unplug equipment.",
                "sound": True,
            })
        if temp > 35:
            alerts.append({
                "level": "warning",
                "title": f"HEAT ALERT — {location_name.upper()}",
                "message": f"Temperature {temp}C. Irrigate early morning/evening.",
                "sound": False,
            })
        if code in [0, 1] and precip == 0 and humidity < 30:
            alerts.append({
                "level": "info",
                "title": f"DRY CONDITIONS — {location_name.upper()}",
                "message": f"Very dry (humidity {humidity}%). Activate water conservation.",
                "sound": False,
            })
        if wind > 40:
            alerts.append({
                "level": "warning",
                "title": f"STRONG WINDS — {location_name.upper()}",
                "message": f"Wind {wind} km/h. Secure tall crops. Delay spraying.",
                "sound": False,
            })
        if code in [1, 2] and 20 <= temp <= 28 and 50 <= humidity <= 75 and precip == 0:
            alerts.append({
                "level": "success",
                "title": f"GOOD CONDITIONS — {location_name.upper()}",
                "message": f"Ideal for planting. Temp {temp}C, humidity {humidity}%.",
                "sound": False,
            })
    except Exception:
        pass
    return alerts

# ── Supabase ───────────────────────────────────────────────────────────────────
def db_register(username, password, full_name, phone, district, role):
    try:
        existing = supa.table("users").select("username").eq("username", username).execute()
        if existing.data:
            return False, "Username already taken."
        supa.table("users").insert({
            "username": username,
            "password_hash": hash_password(password),
            "full_name": full_name,
            "phone": phone,
            "district": district,
            "role": role,
            "joined": datetime.now().strftime("%d %b %Y"),
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
        return False, None, "Wrong password."
    except Exception as e:
        return False, None, str(e)

def _normalize_phone(phone):
    """Strip spaces/dashes for comparison so +256 772 123456 matches +256772123456."""
    if not phone:
        return ""
    return "".join(ch for ch in str(phone) if ch.isdigit() or ch == "+")

def db_reset_password(username, phone, new_password):
    """Reset password if username + registered phone match."""
    try:
        result = supa.table("users").select("*").eq("username", username).execute()
        if not result.data:
            return False, "Username not found."
        user = result.data[0]
        stored_phone = _normalize_phone(user.get("phone", ""))
        given_phone = _normalize_phone(phone)
        if not stored_phone or stored_phone != given_phone:
            return False, "Phone number does not match this account."
        if len(new_password) < 6:
            return False, "Password must be at least 6 characters."
        supa.table("users").update({
            "password_hash": hash_password(new_password)
        }).eq("username", username).execute()
        return True, "Password updated successfully. You can now sign in."
    except Exception as e:
        return False, str(e)

def db_save_message(room, sender, display_name, encrypted_text):
    try:
        supa.table("chat_messages").insert({
            "room": room,
            "sender": sender,
            "display_name": display_name,
            "encrypted_text": encrypted_text,
            "msg_time": datetime.now().strftime("%H:%M"),
            "msg_date": datetime.now().strftime("%d %b %Y"),
        }).execute()
        return True
    except Exception:
        return False

def db_get_messages(room, limit=50):
    """Fetch messages. Prefer created_at; fall back to unordered list sorted in Python."""
    try:
        result = (
            supa.table("chat_messages")
            .select("*")
            .eq("room", room)
            .order("created_at")
            .limit(limit)
            .execute()
        )
        data = result.data or []
        return data
    except Exception:
        try:
            # Fallback if created_at column is missing
            result = (
                supa.table("chat_messages")
                .select("*")
                .eq("room", room)
                .limit(limit)
                .execute()
            )
            data = result.data or []
            # Best-effort sort by msg_date + msg_time strings
            data.sort(key=lambda m: (m.get("msg_date", ""), m.get("msg_time", "")))
            return data
        except Exception:
            return []

def db_save_listing(title, description, seller, phone, location, district, price, type_, tag, image_bytes, username):
    try:
        image_b64 = b64lib.b64encode(image_bytes).decode() if image_bytes else None
        # Cap image size roughly to avoid huge DB rows (~500KB base64 ~ 375KB binary)
        if image_b64 and len(image_b64) > 700_000:
            return False
        supa.table("listings").insert({
            "title": title,
            "description": description,
            "seller": seller,
            "phone": phone,
            "location": location,
            "district": district,
            "price": price,
            "type": type_,
            "tag": tag,
            "image_base64": image_b64,
            "username": username,
            "posted_on": datetime.now().strftime("%d %b %Y"),
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error saving listing: {e}")
        return False

def db_get_listings():
    try:
        result = (
            supa.table("listings")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception:
        try:
            result = supa.table("listings").select("*").execute()
            return result.data or []
        except Exception:
            return []

# ── Groq ───────────────────────────────────────────────────────────────────────
def ask_groq(system_prompt, user_message, history=None):
    try:
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for m in history[-6:]:
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_message})
        response = groq_client.chat.completions.create(
            model=TEXT_MODEL, messages=messages, max_tokens=1200
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

def ask_groq_vision(user_message, image_base64, image_type="image/jpeg"):
    try:
        if image_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
            image_type = "image/jpeg"
        response = groq_client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{image_type};base64,{image_base64}"}},
                    {"type": "text", "text": f"You are an expert Ugandan agricultural advisor. {user_message}"},
                ],
            }],
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Vision error: {str(e)}"

def get_realtime_info(query):
    try:
        response = groq_client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert on Uganda agriculture, climate, and environment up to 2026. "
                        "Give specific, practical, Uganda-focused information. "
                        "Format with clear markdown: short headings (##), bullet lists, and bold key figures. "
                        "Avoid complex pipe tables; prefer bullets like '- **Label:** value'. Keep it readable on mobile."
                    ),
                },
                {"role": "user", "content": f"Give latest information about: {query}. Focus on Uganda 2025-2026."},
            ],
            max_tokens=1200,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

def search_real_photo(query):
    if not PEXELS_KEY:
        return None
    try:
        headers = {"Authorization": PEXELS_KEY}
        params = {"query": query, "per_page": 1, "orientation": "landscape"}
        r = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            photos = r.json().get("photos", [])
            if photos:
                photo = photos[0]
                return {
                    "url": photo["src"]["large"],
                    "photographer": photo.get("photographer", "Unknown"),
                    "source": "real_photo",
                }
        return None
    except Exception:
        return None

def generate_ai_image(description):
    try:
        prompt_resp = groq_client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[{
                "role": "user",
                "content": f"Write a short vivid image generation prompt (max 60 words) for: {description}. Ugandan farming context. Reply with ONLY the prompt text.",
            }],
            max_tokens=150,
        )
        improved = (
            prompt_resp.choices[0].message.content.strip()
            .replace("**", "")
            .replace("Prompt:", "")
            .strip()
            or description
        )
        encoded = requests.utils.quote(improved)
        seed = random.randint(1, 9999)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=512&seed={seed}&nologo=true&enhance=true"
        return {"url": url, "prompt": improved, "source": "ai_generated"}
    except Exception:
        encoded = requests.utils.quote(description[:200])
        return {
            "url": f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=512&nologo=true",
            "prompt": description,
            "source": "ai_generated",
        }

def generate_architectural_plan(description):
    try:
        prompt_resp = groq_client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[{
                "role": "user",
                "content": f"Write a short image prompt (max 60 words) for a 2D architectural floor plan of: {description}. Style: technical line drawing, top-down view, labeled sections, white background, black outlines, blueprint style. Reply with ONLY the prompt text.",
            }],
            max_tokens=150,
        )
        improved = (
            prompt_resp.choices[0].message.content.strip()
            .replace("**", "")
            .replace("Prompt:", "")
            .strip()
        )
        if not improved:
            improved = f"architectural blueprint floor plan of {description}, technical line drawing, top-down, labeled, black and white"
        encoded = requests.utils.quote(improved)
        seed = random.randint(1, 9999)
        return {
            "url": f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=512&seed={seed}&nologo=true",
            "prompt": improved,
            "source": "architectural_plan",
        }
    except Exception:
        encoded = requests.utils.quote(f"blueprint floor plan {description}")
        return {
            "url": f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=512&nologo=true",
            "prompt": description,
            "source": "architectural_plan",
        }

def get_image(description, mode="auto"):
    if mode == "plan":
        return generate_architectural_plan(description)
    if mode in ("auto", "photo"):
        real = search_real_photo(description)
        if real:
            return real
        if mode == "photo":
            return None
    return generate_ai_image(description)

# ── Session state ──────────────────────────────────────────────────────────────
DEFAULTS = {
    "current_user": None,
    "user_data": None,
    "farm_messages": [{
        "role": "assistant",
        "content": (
            "Hello! I am your Farm Advisor.\n\n"
            "I can:\n"
            "- Answer farming questions with Uganda context\n"
            "- Analyze photos of your crops, soil or pests\n"
            "- Find real photos or generate AI images\n"
            "- Give real-time climate and market info"
        ),
    }],
    "active_room": "general",
    "user_lat": None,
    "user_lon": None,
    "location_permission": False,
    "weather_data": None,
    "weather_location": None,
    "last_weather_fetch": None,
    "generated_image_url": None,
    "generated_image_prompt": None,
    "generated_image_source": None,
    "generated_image_credit": None,
    "diagnosis_result": None,
    "active_nav": "Home",
    "auth_mode": "signin",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

WASTE_CATEGORIES = [
    {"name": "Organic / Food Waste", "color": "#2E7D32", "tip": "Compost food scraps into rich soil fertilizer for farms."},
    {"name": "Plastic", "color": "#1565C0", "tip": "Rinse and take to a recycling point near you."},
    {"name": "Electronic Waste", "color": "#6A1B9A", "tip": "Never dump e-waste. Find certified e-waste collectors."},
    {"name": "Agricultural Waste", "color": "#E65100", "tip": "Convert crop residues to biochar or biogas."},
    {"name": "Paper & Cardboard", "color": "#4E342E", "tip": "Separate and dry before recycling."},
    {"name": "Glass", "color": "#00695C", "tip": "Reuse clean bottles or return them to manufacturers."},
]

CHAT_ROOMS = {
    "general": {"name": "General", "desc": "Open discussion for all farmers"},
    "agriculture": {"name": "Agriculture", "desc": "Crop advice, planting, harvesting"},
    "waste_trading": {"name": "Waste Trading", "desc": "Buy and sell agricultural waste"},
    "climate_alerts": {"name": "Climate Alerts", "desc": "Share local weather updates"},
}

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Poppins:wght@600;700;800&display=swap');

/* ── Theme tokens (light default) ── */
:root {
    --ep-bg: #ffffff;
    --ep-bg-soft: #f8faf8;
    --ep-surface: #ffffff;
    --ep-text: #1a1a1a;
    --ep-text-muted: #5f6b5f;
    --ep-border: #e2ebe2;
    --ep-primary: #2E7D32;
    --ep-primary-dark: #1B5E20;
    --ep-primary-soft: #e8f5e9;
    --ep-header-bg: #f1f8e9;
    --ep-shadow: rgba(0,0,0,0.06);
}

/* Streamlit dark theme */
@media (prefers-color-scheme: dark) {
    :root {
        --ep-bg: #0e1117;
        --ep-bg-soft: #161b22;
        --ep-surface: #1c2128;
        --ep-text: #e6edf3;
        --ep-text-muted: #9da7b3;
        --ep-border: #30363d;
        --ep-primary: #4caf50;
        --ep-primary-dark: #388e3c;
        --ep-primary-soft: #1b3d1f;
        --ep-header-bg: #1b3d1f;
        --ep-shadow: rgba(0,0,0,0.35);
    }
}
/* Streamlit applies data-theme on the app */
[data-theme="dark"], .stApp[data-theme="dark"],
html[data-theme="dark"] {
    --ep-bg: #0e1117;
    --ep-bg-soft: #161b22;
    --ep-surface: #1c2128;
    --ep-text: #e6edf3;
    --ep-text-muted: #9da7b3;
    --ep-border: #30363d;
    --ep-primary: #4caf50;
    --ep-primary-dark: #388e3c;
    --ep-primary-soft: #1b3d1f;
    --ep-header-bg: #1b3d1f;
    --ep-shadow: rgba(0,0,0,0.35);
}

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background: var(--ep-bg) !important;
    color: var(--ep-text);
}
.stApp { background: var(--ep-bg) !important; }
section.main > div { background: var(--ep-bg) !important; }

.block-container { padding-top: 0 !important; max-width: 100% !important; }

.topnav {
    display: flex; align-items: center; justify-content: space-between;
    background: var(--ep-surface); border-bottom: 2px solid var(--ep-border);
    padding: 0 24px; height: 64px; position: sticky; top: 0; z-index: 1000;
    box-shadow: 0 2px 8px var(--ep-shadow);
}
.topnav-brand-wrap {
    display: flex; align-items: center; gap: 10px;
}
.topnav-logo {
    height: 36px; width: auto; object-fit: contain; display: block;
}
.topnav-brand {
    font-family: 'Poppins', sans-serif; font-size: 1.35rem;
    font-weight: 800; color: var(--ep-primary); letter-spacing: -0.5px;
    text-decoration: none;
}
.nav-user-area { display: flex; align-items: center; gap: 12px; }
.nav-username { font-size: 0.82rem; color: var(--ep-text-muted); font-weight: 500; }

.page-wrap { padding: 28px 32px; max-width: 1200px; margin: 0 auto; }

/* Full-page auth background + centered card */
.auth-hero {
    min-height: 100vh;
    width: 100%;
    background:
        linear-gradient(135deg, rgba(27, 94, 32, 0.55) 0%, rgba(0, 0, 0, 0.55) 100%),
        url('https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=1600&q=80') center/cover no-repeat;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px 20px;
}
.auth-hero-tagline {
    text-align: center;
    color: #fff;
    margin-bottom: 28px;
    max-width: 520px;
}
.auth-hero-tagline h1 {
    font-family: 'Poppins', sans-serif;
    font-size: 2.2rem;
    font-weight: 800;
    margin: 0 0 10px 0;
    color: #fff !important;
    text-shadow: 0 2px 12px rgba(0,0,0,0.35);
}
.auth-hero-tagline p {
    font-size: 1rem;
    line-height: 1.6;
    color: rgba(255,255,255,0.92) !important;
    margin: 0;
    text-shadow: 0 1px 6px rgba(0,0,0,0.3);
}
.auth-card {
    width: 100%;
    max-width: 420px;
    background: #ffffff;
    border-radius: 20px;
    padding: 36px 32px 28px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.35);
    margin: 0 auto;
}
.auth-brand-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    margin-bottom: 22px;
    text-align: center;
}
.auth-logo {
    height: 64px;
    width: auto;
    max-width: 180px;
    object-fit: contain;
    display: block;
}
.auth-brand {
    font-family: 'Poppins', sans-serif;
    font-size: 1.55rem;
    font-weight: 800;
    color: #2E7D32;
    display: block;
    letter-spacing: -0.3px;
}
.auth-title {
    font-family: 'Poppins', sans-serif;
    font-size: 1.35rem;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 4px;
    text-align: center;
}
.auth-sub {
    font-size: 0.88rem;
    color: #666;
    margin-bottom: 22px;
    line-height: 1.5;
    text-align: center;
}
.auth-foot {
    font-size: 0.84rem;
    color: #666;
    margin-top: 18px;
    text-align: center;
}

.page-hdr {
    background: var(--ep-header-bg); border-left: 4px solid var(--ep-primary);
    border-radius: 0 12px 12px 0; padding: 20px 24px; margin-bottom: 28px;
}
.page-hdr-title { font-family: 'Poppins', sans-serif; font-size: 1.25rem; font-weight: 700; color: var(--ep-primary-dark); }
.page-hdr-sub   { font-size: 0.83rem; color: var(--ep-text-muted); margin-top: 4px; }

.feat-card {
    background: var(--ep-surface); border: 1.5px solid var(--ep-border); border-radius: 16px;
    padding: 24px; transition: all 0.18s;
    box-shadow: 0 2px 8px var(--ep-shadow);
}
.feat-card:hover {
    border-color: var(--ep-primary); transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(46,125,50,0.15);
}
.feat-icon {
    width: 44px; height: 44px; border-radius: 10px; background: var(--ep-primary-soft);
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 14px; font-size: 0.7rem; font-weight: 800;
    color: var(--ep-primary); letter-spacing: 0.5px;
}
.feat-title { font-family: 'Poppins', sans-serif; font-size: 0.95rem; font-weight: 700; color: var(--ep-text); margin-bottom: 6px; }
.feat-desc  { font-size: 0.81rem; color: var(--ep-text-muted); line-height: 1.55; }

.ep-alert         { border-radius: 8px; padding: 14px 18px; margin-bottom: 10px; }
.ep-alert-danger  { background: #ffebee; border-left: 4px solid #c62828; color: #1a1a1a; }
.ep-alert-warning { background: #fff8e1; border-left: 4px solid #f57f17; color: #1a1a1a; }
.ep-alert-info    { background: #e3f2fd; border-left: 4px solid #1565C0; color: #1a1a1a; }
.ep-alert-success { background: var(--ep-primary-soft); border-left: 4px solid var(--ep-primary); color: var(--ep-text); }
.ep-alert-title   { font-weight: 700; font-size: 0.8rem; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 4px; }
.ep-alert-text    { font-size: 0.87rem; line-height: 1.6; color: inherit; }

.wx-card {
    background: var(--ep-header-bg); border: 1.5px solid var(--ep-border);
    border-radius: 16px; padding: 24px; margin-bottom: 20px;
}
.wx-temp  { font-family: 'Poppins', sans-serif; font-size: 3rem; font-weight: 800; color: var(--ep-primary); line-height: 1; }
.wx-cond  { font-size: 0.95rem; color: var(--ep-text-muted); margin-top: 6px; }
.wx-stat  { background: var(--ep-surface); border: 1px solid var(--ep-border); border-radius: 10px; padding: 14px; text-align: center; }
.wx-val   { font-family: 'Poppins', sans-serif; font-size: 1.05rem; font-weight: 700; color: var(--ep-primary); }
.wx-label { font-size: 0.7rem; color: var(--ep-text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 3px; }
.day-card {
    background: var(--ep-surface); border: 1px solid var(--ep-border); border-radius: 10px;
    padding: 10px 4px; text-align: center; color: var(--ep-text);
}

.mkt-card  { background: var(--ep-surface); border: 1.5px solid var(--ep-border); border-radius: 14px; overflow: hidden; margin-bottom: 16px; box-shadow: 0 2px 8px var(--ep-shadow); }
.mkt-body  { padding: 16px; }
.mkt-title { font-weight: 700; color: var(--ep-text); font-size: 0.95rem; margin-bottom: 4px; }
.mkt-meta  { font-size: 0.78rem; color: var(--ep-text-muted); margin-bottom: 8px; }
.mkt-price { font-family: 'Poppins', sans-serif; font-size: 1rem; font-weight: 700; color: var(--ep-primary); }
.mkt-tag   { display: inline-block; background: var(--ep-primary-soft); color: var(--ep-primary); font-size: 0.7rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; margin-left: 8px; }
.sell-bdg  { background: var(--ep-primary-soft); color: var(--ep-primary); font-size: 0.65rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; float: right; }
.buy-bdg   { background: #e3f2fd; color: #1565C0; font-size: 0.65rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; float: right; }
.seller-row { background: var(--ep-header-bg); border-top: 1px solid var(--ep-border); padding: 10px 16px; font-size: 0.78rem; color: var(--ep-text-muted); }
.vfy-badge  { display: inline-block; background: var(--ep-primary-soft); color: var(--ep-primary); font-size: 0.65rem; font-weight: 700; padding: 2px 7px; border-radius: 4px; margin-left: 6px; }

.msg-me    { background: var(--ep-primary); color: #fff; border-radius: 16px 16px 4px 16px; padding: 10px 14px; margin: 4px 0 4px auto; max-width: 72%; font-size: 0.88rem; line-height: 1.5; }
.msg-other { background: var(--ep-bg-soft); color: var(--ep-text); border: 1px solid var(--ep-border); border-radius: 16px 16px 16px 4px; padding: 10px 14px; margin: 4px auto 4px 0; max-width: 72%; font-size: 0.88rem; line-height: 1.5; }
.msg-name  { font-size: 0.68rem; font-weight: 700; color: var(--ep-primary); margin-bottom: 3px; }
.msg-time  { font-size: 0.62rem; color: var(--ep-text-muted); margin-top: 3px; text-align: right; }
.chat-ai   { background: var(--ep-header-bg); border-left: 3px solid var(--ep-primary); border-radius: 0 10px 10px 0; padding: 12px 16px; margin: 8px 0; font-size: 0.9rem; color: var(--ep-text); line-height: 1.6; white-space: pre-wrap; }
.chat-user { background: var(--ep-primary-soft); border-radius: 10px; padding: 10px 14px; margin: 6px 0 6px auto; max-width: 80%; font-size: 0.9rem; color: var(--ep-text); line-height: 1.6; }

.info-box { background: #e3f2fd; border-left: 4px solid #1565C0; border-radius: 0 8px 8px 0; padding: 10px 14px; font-size: 0.82rem; color: #1565C0; margin-bottom: 14px; }

.float-alert { position:fixed;top:80px;right:20px;z-index:9999;background:var(--ep-surface);border:2px solid #c62828;border-radius:12px;padding:14px 18px;max-width:300px;box-shadow:0 8px 24px var(--ep-shadow); }
.float-title { font-weight:700;font-size:0.82rem;color:#c62828;margin-bottom:6px; }
.float-msg   { font-size:0.78rem;color:var(--ep-text);line-height:1.5; }

.stButton > button {
    background: #2E7D32 !important; border: none !important;
    border-radius: 8px !important; color: #fff !important;
    font-weight: 600 !important; font-family: 'Inter', sans-serif !important;
    padding: 10px 20px !important; transition: background 0.15s !important;
}
.stButton > button:hover { background: #1B5E20 !important; }

/* Readable text in both themes */
label, .stMarkdown, .stTextInput label, .stTextArea label,
.stSelectbox label, .stRadio label, div[data-testid="stWidgetLabel"] {
    color: var(--ep-text) !important;
}
div[data-testid="stWidgetLabel"] p,
div[data-testid="stWidgetLabel"] label {
    color: var(--ep-text) !important;
    font-weight: 500 !important;
}

.stTextInput > div > div > input,
.stTextInput input {
    border: 1.5px solid var(--ep-border) !important; border-radius: 8px !important;
    background: var(--ep-surface) !important; color: var(--ep-text) !important;
    font-family: 'Inter', sans-serif !important; padding: 10px 14px !important;
    -webkit-text-fill-color: var(--ep-text) !important;
}
.stTextInput > div > div > input:focus {
    border-color: var(--ep-primary) !important;
    box-shadow: 0 0 0 3px rgba(46,125,50,0.15) !important;
}
.stTextInput > div > div > input::placeholder {
    color: var(--ep-text-muted) !important;
    -webkit-text-fill-color: var(--ep-text-muted) !important;
    opacity: 1 !important;
}
.stTextInput input:-webkit-autofill,
.stTextInput input:-webkit-autofill:hover,
.stTextInput input:-webkit-autofill:focus {
    -webkit-text-fill-color: var(--ep-text) !important;
    -webkit-box-shadow: 0 0 0px 1000px var(--ep-surface) inset !important;
    background-color: var(--ep-surface) !important;
    color: var(--ep-text) !important;
}

.stTextArea textarea {
    border: 1.5px solid var(--ep-border) !important; border-radius: 8px !important;
    background: var(--ep-surface) !important; color: var(--ep-text) !important;
    font-family: 'Inter', sans-serif !important;
    -webkit-text-fill-color: var(--ep-text) !important;
}
.stSelectbox > div > div {
    border: 1.5px solid var(--ep-border) !important; border-radius: 8px !important;
    background: var(--ep-surface) !important; color: var(--ep-text) !important;
}

div[data-testid="stAlert"] { color: var(--ep-text) !important; }
div[data-testid="stAlert"] * { color: inherit !important; }

div[data-testid="stTabs"] button { color: var(--ep-text-muted) !important; font-family: 'Inter', sans-serif !important; }
div[data-testid="stTabs"] button[aria-selected="true"] { color: var(--ep-primary) !important; font-weight: 700 !important; }
h1,h2,h3 { font-family: 'Poppins', sans-serif !important; color: var(--ep-text) !important; }
footer { display: none !important; }
</style>
""", unsafe_allow_html=True)

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
<button onclick="requestLocation()" style="background:#2E7D32;border:none;border-radius:8px;color:#fff;padding:10px 20px;font-weight:600;cursor:pointer;font-family:Inter,sans-serif;font-size:0.85rem;">
    Allow Location Access
</button>
"""

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
    except Exception:
        pass
    return False

def fetch_weather(user_data):
    now = datetime.now()
    last = st.session_state.last_weather_fetch
    if last and (now - last).seconds < 1800 and st.session_state.weather_data:
        return
    if st.session_state.location_permission and st.session_state.user_lat:
        lat, lon = st.session_state.user_lat, st.session_state.user_lon
        st.session_state.weather_location = "Your GPS Location"
    else:
        district = user_data.get("district", "Kampala")
        lat, lon = get_coords_for_district(district)
        st.session_state.weather_location = f"{district} District"
    data = get_weather_by_coords(lat, lon)
    if data:
        st.session_state.weather_data = data
        st.session_state.last_weather_fetch = now

def show_floating_alerts(alerts):
    shown = [a for a in alerts if a["level"] == "danger"][:1] or [a for a in alerts if a["level"] == "warning"][:1]
    for alert in shown:
        st.markdown(
            f"""<div class="float-alert">
            <div class="float-title">{escape(alert["title"])}</div>
            <div class="float-msg">{escape(alert["message"])}</div>
        </div>""",
            unsafe_allow_html=True,
        )
        if alert.get("sound"):
            st.components.v1.html(ALERT_SOUND_JS, height=0)

# ══════════════════════════════════════════════════════════════════════════════
# AUTH PAGE
# ══════════════════════════════════════════════════════════════════════════════
def show_auth():
    st.markdown(
        """<style>
    section.main > div { padding: 0 !important; }
    .block-container {
        padding: 0 !important;
        max-width: 100% !important;
        padding-top: 0 !important;
    }
    /* Full-page farm background on auth only */
    .stApp {
        background:
            linear-gradient(135deg, rgba(27, 94, 32, 0.55) 0%, rgba(0, 0, 0, 0.5) 100%),
            url('https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=1600&q=80') center/cover no-repeat fixed !important;
    }
    .auth-card label, .auth-card p, .auth-card [data-testid="stWidgetLabel"] p {
        color: #1a1a1a !important;
    }
    .auth-hero-tagline h1 { color: #fff !important; }
    .auth-hero-tagline p { color: rgba(255,255,255,0.95) !important; }
    </style>""",
        unsafe_allow_html=True,
    )

    # Spacer + centered column
    st.markdown("<div style='height:48px;'></div>", unsafe_allow_html=True)

    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.markdown(
            """
        <div class="auth-hero-tagline">
            <h1>Smart Farming Starts Here</h1>
            <p>AI climate advice, weather alerts, a green marketplace and a farmer community — built for Uganda.</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="auth-card">', unsafe_allow_html=True)

        # Logo + brand (centered)
        if LOGO_DATA_URI:
            st.markdown(
                f"""<div class="auth-brand-wrap">
                <img src="{LOGO_DATA_URI}" class="auth-logo" alt="EcoPulse logo" />
                <span class="auth-brand">EcoPulse</span>
            </div>""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """<div class="auth-brand-wrap">
                <span class="auth-brand">EcoPulse</span>
            </div>""",
                unsafe_allow_html=True,
            )
            st.caption("Add logo.png next to app.py to show your logo")

        if st.session_state.auth_mode == "signin":
            st.markdown('<div class="auth-title">Welcome back</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-sub">Sign in to your account to continue</div>', unsafe_allow_html=True)

            with st.form("signin_form", clear_on_submit=False):
                login_user = st.text_input("Username", placeholder="Enter your username")
                login_pass = st.text_input("Password", type="password", placeholder="Enter your password")
                submitted = st.form_submit_button("Sign In", use_container_width=True)

            if submitted:
                uname = (login_user or "").strip().lower().replace(" ", "_")
                if not uname or not login_pass:
                    st.warning("Please enter your username and password.")
                else:
                    with st.spinner("Signing in..."):
                        success, user, msg = db_login(uname, login_pass)
                    if success:
                        st.session_state.current_user = uname
                        st.session_state.user_data = user
                        st.rerun()
                    else:
                        st.error(msg)

            if st.button("Forgot password?", key="go_forgot", use_container_width=True):
                st.session_state.auth_mode = "forgot"
                st.rerun()

            st.markdown('<div class="auth-foot">Do not have an account?</div>', unsafe_allow_html=True)
            if st.button("Create a new account", key="go_register", use_container_width=True):
                st.session_state.auth_mode = "register"
                st.rerun()

        elif st.session_state.auth_mode == "forgot":
            st.markdown('<div class="auth-title">Reset password</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="auth-sub">Enter your username and the phone number on your account to set a new password.</div>',
                unsafe_allow_html=True,
            )

            with st.form("forgot_form", clear_on_submit=False):
                fp_user = st.text_input("Username *", placeholder="e.g. elias_opolot")
                fp_phone = st.text_input("Registered phone number *", placeholder="+256 7XX XXXXXX")
                fp_pass = st.text_input("New password *", type="password", placeholder="Min 6 characters")
                fp_pass2 = st.text_input("Confirm new password *", type="password", placeholder="Repeat new password")
                fp_submitted = st.form_submit_button("Reset password", use_container_width=True)

            if fp_submitted:
                uname = (fp_user or "").strip().lower().replace(" ", "_")
                if not uname or not fp_phone or not fp_pass or not fp_pass2:
                    st.warning("Please fill all fields.")
                elif fp_pass != fp_pass2:
                    st.error("Passwords do not match.")
                elif len(fp_pass) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    with st.spinner("Updating password..."):
                        ok, msg = db_reset_password(uname, fp_phone, fp_pass)
                    if ok:
                        st.success(msg)
                        st.session_state.auth_mode = "signin"
                        st.rerun()
                    else:
                        st.error(msg)

            st.markdown('<div class="auth-foot">Remember your password?</div>', unsafe_allow_html=True)
            if st.button("Back to Sign In", key="forgot_back_signin", use_container_width=True):
                st.session_state.auth_mode = "signin"
                st.rerun()

        else:
            st.markdown('<div class="auth-title">Create account</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-sub">Join the EcoPulse farmer community</div>', unsafe_allow_html=True)

            with st.form("register_form", clear_on_submit=False):
                reg_fname = st.text_input("Full Name *", placeholder="e.g. Nakato Sarah")
                reg_uname = st.text_input("Username *", placeholder="e.g. nakato_sarah")
                reg_phone = st.text_input("Phone Number *", placeholder="+256 7XX XXXXXX")
                reg_dist = st.text_input("District *", placeholder="e.g. Wakiso")
                reg_role = st.selectbox("I am a *", ["Farmer", "Agri-business", "Recycler", "Student", "Other"])
                reg_pass = st.text_input("Password *", type="password", placeholder="Min 6 characters")
                reg_pass2 = st.text_input("Confirm Password *", type="password", placeholder="Repeat password")
                reg_submitted = st.form_submit_button("Create Account", use_container_width=True)

            if reg_submitted:
                uname = (reg_uname or "").strip().lower().replace(" ", "_")
                if not all([reg_fname, reg_uname, reg_phone, reg_dist, reg_pass, reg_pass2]):
                    st.warning("Please fill all required fields.")
                elif len(reg_pass) < 6:
                    st.error("Password must be at least 6 characters.")
                elif reg_pass != reg_pass2:
                    st.error("Passwords do not match.")
                else:
                    with st.spinner("Creating your account..."):
                        success, msg = db_register(uname, reg_pass, reg_fname, reg_phone, reg_dist, reg_role)
                    if success:
                        _, user, _ = db_login(uname, reg_pass)
                        st.session_state.current_user = uname
                        st.session_state.user_data = user
                        st.rerun()
                    else:
                        st.error(msg)

            st.markdown('<div class="auth-foot">Already have an account?</div>', unsafe_allow_html=True)
            if st.button("Back to Sign In", key="go_signin", use_container_width=True):
                st.session_state.auth_mode = "signin"
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
def show_main_app():
    user = st.session_state.current_user
    user_data = st.session_state.user_data

    read_location_from_params()
    fetch_weather(user_data)

    if st.session_state.weather_data:
        loc_name = st.session_state.weather_location or user_data.get("district", "Uganda")
        alerts = parse_weather_alerts(st.session_state.weather_data, loc_name)
        if alerts:
            show_floating_alerts(alerts)

    # ── TOP NAV (visible, working buttons) ───────────────────────────────────
    nav_items = ["Home", "Farm AI", "Waste Guide", "Climate", "Marketplace", "Farmer Chat"]
    active = st.session_state.active_nav
    loc_show = "GPS Active" if st.session_state.location_permission else user_data.get("district", "")

    brand_html = (
        f'<div class="topnav-brand-wrap">'
        f'<img src="{LOGO_DATA_URI}" class="topnav-logo" alt="EcoPulse" />'
        f'<span class="topnav-brand">EcoPulse</span></div>'
        if LOGO_DATA_URI
        else '<span class="topnav-brand">EcoPulse</span>'
    )
    st.markdown(
        f"""
    <div class="topnav">
        {brand_html}
        <div class="nav-user-area">
            <span class="nav-username">{escape(user_data.get('full_name', ''))} &nbsp;|&nbsp; {escape(loc_show)}</span>
        </div>
    </div>""",
        unsafe_allow_html=True,
    )

    # Visible navigation buttons — these actually change pages
    st.markdown(
        """<style>
    /* Nav row buttons */
    div[data-testid="stHorizontalBlock"] button[kind="secondary"],
    div[data-testid="stHorizontalBlock"] button[kind="primary"] {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
        padding: 0.4rem 0.6rem !important;
        min-height: 2.2rem !important;
    }
    </style>""",
        unsafe_allow_html=True,
    )

    nav_cols = st.columns(len(nav_items) + 1)
    for i, item in enumerate(nav_items):
        with nav_cols[i]:
            is_active = item == active
            if st.button(
                item,
                key=f"navbtn_{item}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.active_nav = item
                st.rerun()
    with nav_cols[-1]:
        if st.button("Sign Out", key="top_signout", use_container_width=True):
            for k in list(DEFAULTS.keys()):
                if k in st.session_state:
                    st.session_state[k] = DEFAULTS[k]
            st.session_state.current_user = None
            st.session_state.user_data = None
            st.session_state.active_nav = "Home"
            st.rerun()

    st.markdown('<div class="page-wrap">', unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # HOME
    # ══════════════════════════════════════════════════════════════════════════
    if active == "Home":
        name = user_data.get("full_name", "Farmer").split()[0]
        st.markdown(
            f"""
        <div style="margin-bottom:32px;">
            <div style="font-family:'Poppins',sans-serif;font-size:1.7rem;font-weight:700;color:#1a1a1a;margin-bottom:4px;">
                Welcome back, {escape(name)}
            </div>
            <div style="font-size:0.9rem;color:#888;">Here is what you can do with EcoPulse today.</div>
        </div>""",
            unsafe_allow_html=True,
        )

        features = [
            {"title": "Farm AI Advisor", "desc": "Ask AI for crop guidance, diagnose diseases from photos, and get Uganda-specific farming advice in real time.", "page": "Farm AI", "icon": "AI"},
            {"title": "Climate Dashboard", "desc": "Live weather alerts for your exact location. 7-day forecast with automatic emergency notifications.", "page": "Climate", "icon": "WX"},
            {"title": "Waste Guide", "desc": "Turn agricultural and household waste into income with AI-powered circular economy guidance.", "page": "Waste Guide", "icon": "RCY"},
            {"title": "Green Marketplace", "desc": "Buy and sell agricultural products with verified seller profiles and product photos.", "page": "Marketplace", "icon": "MKT"},
            {"title": "Farmer Chat", "desc": "Encrypted group chat rooms connecting Uganda's farming community securely.", "page": "Farmer Chat", "icon": "CHT"},
        ]

        c1, c2 = st.columns(2)
        for i, f in enumerate(features):
            col = c1 if i % 2 == 0 else c2
            with col:
                st.markdown(
                    f"""
                <div class="feat-card">
                    <div class="feat-icon">{f["icon"]}</div>
                    <div class="feat-title">{escape(f["title"])}</div>
                    <div class="feat-desc">{escape(f["desc"])}</div>
                </div>""",
                    unsafe_allow_html=True,
                )
                if st.button(f"Open {f['title']}", key=f"hbtn_{i}", use_container_width=True):
                    st.session_state.active_nav = f["page"]
                    st.rerun()
                st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        st.markdown(
            """
        <div style="background:#f9fbe7;border-radius:16px;padding:24px 28px;margin-top:8px;border:1.5px solid #dcedc8;">
            <div style="font-family:'Poppins',sans-serif;font-weight:700;font-size:1rem;color:#1B5E20;margin-bottom:8px;">About EcoPulse</div>
            <div style="font-size:0.88rem;color:#555;line-height:1.7;">
                EcoPulse is an AI-powered platform built for Ugandan farmers and agro-entrepreneurs.
                It brings together climate intelligence, agricultural advisory, waste management guidance,
                a green trading marketplace, and secure farmer communication — all accessible from any smartphone.
            </div>
            <div style="margin-top:14px;font-size:0.8rem;color:#999;">
                Built by Team GreenPulse &nbsp;|&nbsp; Elias Creations &nbsp;|&nbsp; Busitema University
            </div>
        </div>""",
            unsafe_allow_html=True,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # FARM AI
    # ══════════════════════════════════════════════════════════════════════════
    elif active == "Farm AI":
        st.markdown(
            """<div class="page-hdr">
            <div class="page-hdr-title">Farm AI Advisor</div>
            <div class="page-hdr-sub">Ask questions, diagnose crop photos, find real images and get real-time Uganda farming info</div>
        </div>""",
            unsafe_allow_html=True,
        )

        farm_sub1, farm_sub2, farm_sub3 = st.tabs(["Ask AI", "Photo Diagnosis", "Find / Generate Image"])

        with farm_sub1:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Uganda Farming News", key="btn_news"):
                    with st.spinner("Fetching latest farming news..."):
                        info = get_realtime_info("current farming season, crop prices, and weather in Uganda 2026")
                    st.session_state.farm_messages.append({"role": "user", "content": "Latest Uganda farming news?"})
                    st.session_state.farm_messages.append({"role": "assistant", "content": f"Real-Time Uganda Update:\n\n{info}"})
                    st.rerun()
            with c2:
                if st.button("Crop Market Prices", key="btn_prices"):
                    with st.spinner("Fetching market prices..."):
                        prices = get_realtime_info("current market prices for maize, beans, tomatoes, coffee in Uganda 2025-2026")
                    st.session_state.farm_messages.append({"role": "user", "content": "Current crop prices in Uganda?"})
                    st.session_state.farm_messages.append({"role": "assistant", "content": f"Uganda Crop Market Prices:\n\n{prices}"})
                    st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)
            for msg in st.session_state.farm_messages:
                if msg["role"] == "assistant":
                    st.markdown('<div class="chat-ai"><strong>Advisor</strong></div>', unsafe_allow_html=True)
                    st.markdown(msg["content"])
                else:
                    st.markdown(
                        f"<div class='chat-user'><strong>You:</strong> {escape(msg['content'])}</div>",
                        unsafe_allow_html=True,
                    )

            with st.form("farm_form", clear_on_submit=True):
                user_input = st.text_input("", placeholder="Ask anything about farming in Uganda...", label_visibility="collapsed")
                submitted = st.form_submit_button("Send")

            if submitted and user_input.strip():
                st.session_state.farm_messages.append({"role": "user", "content": user_input})
                history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.farm_messages[:-1]]
                with st.spinner("Getting AI advice..."):
                    reply = ask_groq(
                        "You are an expert Ugandan agricultural advisor. Give practical, actionable advice with current Uganda 2025-2026 context. "
                        "Format clearly with short headings and bullet lists. Use simple markdown only. Do not use messy tables unless necessary.",
                        user_input,
                        history,
                    )
                st.session_state.farm_messages.append({"role": "assistant", "content": reply})
                st.rerun()

            if st.button("Clear Chat", key="clear_chat"):
                st.session_state.farm_messages = [st.session_state.farm_messages[0]]
                st.rerun()

        with farm_sub2:
            st.markdown(
                '<div class="info-box">Upload a clear photo of your crop, leaves, soil or pest. The AI will analyze it and give Uganda-specific treatment advice.</div>',
                unsafe_allow_html=True,
            )
            farm_image = st.file_uploader("Upload farm photo", type=["jpg", "jpeg", "png"], key="farm_img", label_visibility="collapsed")
            if farm_image:
                col_img, col_info = st.columns([1, 2])
                with col_img:
                    st.image(farm_image, use_container_width=True, caption="Uploaded photo")
                with col_info:
                    diag_q = st.text_input("What do you want to know?", placeholder="e.g. What disease is on my maize leaves?", key="diag_q")
                    if st.button("Analyze Photo", key="analyze_btn"):
                        with st.spinner("Analyzing your photo..."):
                            farm_image.seek(0)
                            img_b64 = b64lib.b64encode(farm_image.read()).decode("utf-8")
                            raw_type = farm_image.type or "image/jpeg"
                            img_type = "image/png" if "png" in raw_type else "image/jpeg"
                            question = (
                                diag_q.strip()
                                if diag_q.strip()
                                else "Analyze this farm photo carefully. Identify any diseases, pests, soil problems and give specific Uganda-relevant treatment advice."
                            )
                            result = ask_groq_vision(question, img_b64, img_type)
                            st.session_state.diagnosis_result = result

            if st.session_state.diagnosis_result:
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(
                    '<div class="ep-alert ep-alert-success"><div class="ep-alert-title" style="color:#2E7D32;">Diagnosis Result</div></div>',
                    unsafe_allow_html=True,
                )
                st.markdown(st.session_state.diagnosis_result)
                if st.button("Clear Diagnosis", key="clear_diag"):
                    st.session_state.diagnosis_result = None
                    st.rerun()

        with farm_sub3:
            st.markdown(
                '<div class="info-box">Search for real photos from the web, generate AI images, or create architectural plans for farm structures.</div>',
                unsafe_allow_html=True,
            )
            image_mode = st.radio(
                "What do you need?",
                ["Real Photo (search the web)", "AI Generated Image", "Architectural Plan / Diagram"],
                key="image_mode_select",
            )
            quick_prompt = st.selectbox(
                "Choose a quick example or type your own:",
                [
                    "Type your own description below",
                    "Healthy maize farm in Uganda",
                    "Dairy cow in a Uganda farm",
                    "Drip irrigation system on a small farm",
                    "Goat shed / animal house",
                    "Chicken coop / poultry house",
                    "Organic compost pit",
                    "Banana plantation in Western Uganda",
                    "Coffee farm in Bugisu region",
                ],
                key="quick_img",
            )
            custom_prompt = st.text_area(
                "Or describe your own image:",
                placeholder="e.g. A dairy cow in a green pasture in Uganda...",
                height=80,
                key="custom_img_prompt",
            )

            if st.button("Get Image", key="gen_img_btn", use_container_width=True):
                final = custom_prompt.strip() if custom_prompt.strip() else (quick_prompt if quick_prompt != "Type your own description below" else None)
                if not final:
                    st.warning("Please choose an example or type a description.")
                else:
                    mode = "auto" if "Real" in image_mode else ("ai" if "AI" in image_mode else "plan")
                    spinner_text = (
                        "Searching for a real photo..."
                        if mode == "auto"
                        else ("Generating image..." if mode == "ai" else "Generating architectural plan...")
                    )
                    with st.spinner(spinner_text):
                        result = get_image(final, mode=mode)
                        if result:
                            st.session_state.generated_image_url = result["url"]
                            st.session_state.generated_image_prompt = result.get("prompt", final)
                            st.session_state.generated_image_source = result.get("source", "unknown")
                            st.session_state.generated_image_credit = result.get("photographer")
                        else:
                            st.session_state.generated_image_url = None
                            st.warning("No real photo found. Try AI Generated Image instead.")

            if st.session_state.generated_image_url:
                source = st.session_state.get("generated_image_source", "")
                label = "Real Photo" if source == "real_photo" else ("Architectural Plan" if source == "architectural_plan" else "AI Generated Image")
                credit = st.session_state.get("generated_image_credit")
                sub = f"Photo by {escape(credit)} on Pexels" if credit else f'"{escape(st.session_state.generated_image_prompt)}"'
                st.markdown(f"<strong>{label}</strong> &nbsp; <span style='color:#888;font-size:0.8rem;'>{sub}</span>", unsafe_allow_html=True)
                st.image(st.session_state.generated_image_url, use_container_width=True)
                st.markdown(f"[Download Image]({st.session_state.generated_image_url})")
                if st.button("Search / Generate Another", key="regen_btn"):
                    st.session_state.generated_image_url = None
                    st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # WASTE GUIDE
    # ══════════════════════════════════════════════════════════════════════════
    elif active == "Waste Guide":
        st.markdown(
            """<div class="page-hdr">
            <div class="page-hdr-title">Waste Management Guide</div>
            <div class="page-hdr-sub">Turn agricultural and household waste into income using circular economy principles</div>
        </div>""",
            unsafe_allow_html=True,
        )

        selected_waste = st.selectbox("Choose a waste category:", options=[w["name"] for w in WASTE_CATEGORIES])
        chosen = next(w for w in WASTE_CATEGORIES if w["name"] == selected_waste)
        st.markdown(
            f"""<div style="background:#fff;border:1.5px solid #e0e0e0;border-left:4px solid {chosen['color']};border-radius:10px;padding:16px;margin-bottom:16px;">
            <div style="font-weight:700;color:#1a1a1a;margin-bottom:4px;">{escape(chosen['name'])}</div>
            <div style="font-size:0.85rem;color:#666;line-height:1.5;">{escape(chosen['tip'])}</div>
        </div>""",
            unsafe_allow_html=True,
        )

        cw1, cw2 = st.columns(2)
        with cw1:
            if st.button("Get AI Tips", key="waste_ai"):
                with st.spinner("Generating tips..."):
                    tip = ask_groq(
                        "Circular economy expert for Uganda. Give 3 practical numbered tips showing income opportunities. "
                        "Max 2 sentences each. Use clean markdown: numbered list only, no tables.",
                        f"Tips for: {selected_waste}",
                    )
                st.session_state["waste_tip"] = tip
                st.session_state["waste_tip_title"] = selected_waste
        with cw2:
            if st.button("Real-Time Market Info", key="waste_market"):
                with st.spinner("Fetching..."):
                    info = get_realtime_info(
                        f"current market for {selected_waste} recycling in Uganda 2025-2026. "
                        f"Reply with clear short headings and bullet points. Avoid complex markdown tables; use simple lists."
                    )
                st.session_state["waste_market"] = info

        if st.session_state.get("waste_tip"):
            st.markdown(
                f'<div class="ep-alert ep-alert-success" style="margin-top:12px;"><div class="ep-alert-title" style="color:#2E7D32;">AI Tips — {escape(st.session_state.get("waste_tip_title", ""))}</div></div>',
                unsafe_allow_html=True,
            )
            st.markdown(st.session_state["waste_tip"])

        if st.session_state.get("waste_market"):
            st.markdown(
                '<div class="ep-alert ep-alert-info" style="margin-top:12px;"><div class="ep-alert-title" style="color:#1565C0;">Market Info</div></div>',
                unsafe_allow_html=True,
            )
            st.markdown(st.session_state["waste_market"])

        st.markdown("<br><strong>All Waste Categories</strong><br><br>", unsafe_allow_html=True)
        cols = st.columns(3)
        for i, w in enumerate(WASTE_CATEGORIES):
            with cols[i % 3]:
                st.markdown(
                    f"""<div style="background:#fff;border:1.5px solid #e0e0e0;border-left:4px solid {w['color']};border-radius:10px;padding:14px;margin-bottom:10px;">
                    <div style="font-weight:700;color:#1a1a1a;font-size:0.85rem;">{escape(w['name'])}</div>
                </div>""",
                    unsafe_allow_html=True,
                )

    # ══════════════════════════════════════════════════════════════════════════
    # CLIMATE
    # ══════════════════════════════════════════════════════════════════════════
    elif active == "Climate":
        st.markdown(
            """<div class="page-hdr">
            <div class="page-hdr-title">Climate Dashboard</div>
            <div class="page-hdr-sub">Real-time weather data and alerts for your location</div>
        </div>""",
            unsafe_allow_html=True,
        )

        if not st.session_state.location_permission:
            st.markdown(
                f"""<div class="ep-alert ep-alert-info">
                <div class="ep-alert-title" style="color:#1565C0;">Location</div>
                <div class="ep-alert-text">Currently showing weather for <strong>{escape(user_data.get('district', 'your district'))}</strong> from your profile. Allow precise location for more accurate data.</div>
            </div>""",
                unsafe_allow_html=True,
            )
            st.components.v1.html(GEOLOCATION_JS, height=60)
        else:
            st.markdown(
                f"""<div class="ep-alert ep-alert-success">
                <div class="ep-alert-title" style="color:#2E7D32;">GPS Active</div>
                <div class="ep-alert-text">Showing real-time weather for your exact location. Coordinates: {st.session_state.user_lat:.4f}, {st.session_state.user_lon:.4f}</div>
            </div>""",
                unsafe_allow_html=True,
            )

        if st.button("Refresh Weather"):
            st.session_state.last_weather_fetch = None
            fetch_weather(user_data)
            st.rerun()

        wd = st.session_state.weather_data
        loc_name = st.session_state.weather_location or user_data.get("district", "Uganda")

        if wd:
            current = wd.get("current", {})
            daily = wd.get("daily", {})
            temp = current.get("temperature_2m", "--")
            precip = current.get("precipitation", 0)
            humidity = current.get("relative_humidity_2m", "--")
            wind = current.get("windspeed_10m", "--")
            code = current.get("weathercode", 0)
            condition = WEATHER_CODES.get(code, "Unknown")

            st.markdown(
                f"""<div class="wx-card">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:20px;">
                    <div>
                        <div style="font-size:0.78rem;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">NOW — {escape(loc_name.upper())}</div>
                        <div class="wx-temp">{temp}°C</div>
                        <div class="wx-cond">{escape(condition)}</div>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px;">
                        <div class="wx-stat"><div class="wx-val">{precip}mm</div><div class="wx-label">Rain</div></div>
                        <div class="wx-stat"><div class="wx-val">{humidity}%</div><div class="wx-label">Humidity</div></div>
                        <div class="wx-stat"><div class="wx-val">{wind}km/h</div><div class="wx-label">Wind</div></div>
                        <div class="wx-stat"><div class="wx-val">{temp}°C</div><div class="wx-label">Temp</div></div>
                    </div>
                </div>
            </div>""",
                unsafe_allow_html=True,
            )

            alerts = parse_weather_alerts(wd, loc_name)
            st.markdown("<strong>Active Alerts</strong><br>", unsafe_allow_html=True)
            if alerts:
                level_colors = {"danger": "#c62828", "warning": "#f57f17", "info": "#1565C0", "success": "#2E7D32"}
                for alert in alerts:
                    color = level_colors.get(alert["level"], "#2E7D32")
                    st.markdown(
                        f"""<div class="ep-alert ep-alert-{alert['level']}">
                        <div class="ep-alert-title" style="color:{color};">{escape(alert['title'])}</div>
                        <div class="ep-alert-text">{escape(alert['message'])}</div>
                    </div>""",
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    """<div class="ep-alert ep-alert-success">
                    <div class="ep-alert-title" style="color:#2E7D32;">No Active Alerts</div>
                    <div class="ep-alert-text">Current conditions are normal for your location.</div>
                </div>""",
                    unsafe_allow_html=True,
                )

            if daily.get("time"):
                st.markdown("<br><strong>7-Day Forecast</strong><br><br>", unsafe_allow_html=True)
                days = daily["time"][:7]
                t_max = daily.get("temperature_2m_max", [0] * 7)[:7]
                t_min = daily.get("temperature_2m_min", [0] * 7)[:7]
                rain = daily.get("precipitation_sum", [0] * 7)[:7]
                pcodes = daily.get("weathercode", [0] * 7)[:7]
                rprob = daily.get("precipitation_probability_max", [0] * 7)[:7]
                cols7 = st.columns(7)
                for i, (day, tmax, tmin, r, wc, rp) in enumerate(zip(days, t_max, t_min, rain, pcodes, rprob)):
                    try:
                        day_str = datetime.strptime(day, "%Y-%m-%d").strftime("%a %d")
                    except Exception:
                        day_str = day
                    cond = "Storm" if wc >= 95 else ("Rain" if wc >= 61 else ("Shwr" if wc >= 51 else ("Cld" if wc >= 2 else "Sun")))
                    with cols7[i]:
                        st.markdown(
                            f"""<div class="day-card">
                            <div style="font-size:0.65rem;color:#888;font-weight:600;">{day_str}</div>
                            <div style="font-size:0.75rem;font-weight:700;color:#2E7D32;margin:4px 0;">{cond}</div>
                            <div style="font-size:0.8rem;font-weight:700;color:#1a1a1a;">{tmax:.0f}°</div>
                            <div style="font-size:0.65rem;color:#888;">{tmin:.0f}°</div>
                            <div style="font-size:0.63rem;color:#1565C0;margin-top:3px;">{r:.1f}mm</div>
                            <div style="font-size:0.6rem;color:#888;">{rp}% rain</div>
                        </div>""",
                            unsafe_allow_html=True,
                        )

                st.markdown("<br>", unsafe_allow_html=True)
                df_rain = pd.DataFrame({
                    "Day": [datetime.strptime(d, "%Y-%m-%d").strftime("%a %d") for d in daily["time"][:7]],
                    "Rainfall (mm)": daily["precipitation_sum"][:7],
                }).set_index("Day")
                st.bar_chart(df_rain, color="#2E7D32", height=200)

                df_temp = pd.DataFrame({
                    "Day": [datetime.strptime(d, "%Y-%m-%d").strftime("%a %d") for d in daily["time"][:7]],
                    "Max C": daily.get("temperature_2m_max", [])[:7],
                    "Min C": daily.get("temperature_2m_min", [])[:7],
                }).set_index("Day")
                st.line_chart(df_temp, color=["#c62828", "#1565C0"], height=180)
        else:
            st.warning("Could not load weather data. Check your connection and try refreshing.")

    # ══════════════════════════════════════════════════════════════════════════
    # MARKETPLACE
    # ══════════════════════════════════════════════════════════════════════════
    elif active == "Marketplace":
        st.markdown(
            """<div class="page-hdr">
            <div class="page-hdr-title">Green Marketplace</div>
            <div class="page-hdr-sub">Buy and sell agricultural products with verified seller details and product photos</div>
        </div>""",
            unsafe_allow_html=True,
        )

        filter_type = st.radio("Filter:", ["All", "Selling", "Buying"], horizontal=True)

        db_listings = db_get_listings()
        default_listings = [
            {"title": "Organic Compost — 50kg bags", "seller": "Kakooza Farms", "phone": "+256 772 123456", "location": "Wakiso", "district": "Wakiso", "price": "UGX 25,000", "type": "sell", "tag": "Waste-to-Value", "description": "High quality organic compost made from food waste.", "image_base64": None},
            {"title": "Solar Water Pump — rental", "seller": "GreenTech Hub", "phone": "+256 701 234567", "location": "Kampala", "district": "Kampala", "price": "UGX 15,000/day", "type": "sell", "tag": "Clean Energy", "description": "Portable solar-powered water pump for irrigation.", "image_base64": None},
            {"title": "Wanted: Crop Residue", "seller": "BioGas Uganda", "phone": "+256 754 345678", "location": "Jinja", "district": "Jinja", "price": "UGX 8,000/bale", "type": "buy", "tag": "Circular Economy", "description": "We buy maize stalks in bulk for biogas production.", "image_base64": None},
            {"title": "Surplus Tomatoes — urgent sale", "seller": "Nakato Agri", "phone": "+256 782 456789", "location": "Mbarara", "district": "Mbarara", "price": "UGX 10,000/crate", "type": "sell", "tag": "Fresh Produce", "description": "Fresh tomatoes harvested this week.", "image_base64": None},
        ]
        all_listings = db_listings if db_listings else default_listings

        for listing in all_listings:
            type_val = listing.get("type", "sell")
            if filter_type == "Selling" and type_val != "sell":
                continue
            if filter_type == "Buying" and type_val != "buy":
                continue
            badge_class = "sell-bdg" if type_val == "sell" else "buy-bdg"
            badge_text = "SELLING" if type_val == "sell" else "BUYING"

            img_b64 = listing.get("image_base64")
            if img_b64:
                try:
                    st.image(b64lib.b64decode(img_b64), use_container_width=True, caption=listing.get("title", ""))
                except Exception:
                    pass
            st.markdown(
                f"""<div class="mkt-card">
                <div class="mkt-body">
                    <span class="{badge_class}">{badge_text}</span>
                    <div class="mkt-title">{escape(listing.get('title', ''))}</div>
                    <div class="mkt-meta">{escape(listing.get('description', ''))}</div>
                    <div><span class="mkt-price">{escape(listing.get('price', ''))}</span><span class="mkt-tag">{escape(listing.get('tag', ''))}</span></div>
                </div>
                <div class="seller-row">
                    <strong>{escape(listing.get('seller', ''))}</strong>
                    <span class="vfy-badge">Verified</span>
                    &nbsp;&nbsp;Tel: {escape(listing.get('phone', 'N/A'))}
                    &nbsp;&nbsp;{escape(listing.get('district', 'N/A'))} District
                    &nbsp;&nbsp;{escape(listing.get('posted_on', ''))}
                </div>
            </div>""",
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("Post a New Listing"):
            new_title = st.text_input("Title *", placeholder="e.g. Fresh Maize — 100kg")
            new_desc = st.text_area("Description *", height=70)
            mc1, mc2 = st.columns(2)
            with mc1:
                new_type = st.selectbox("Type *", ["Selling", "Buying"])
                new_price = st.text_input("Price (UGX) *")
                new_tag = st.selectbox("Category *", ["Fresh Produce", "Waste-to-Value", "Clean Energy", "AgriTech", "Circular Economy", "Recycling", "Other"])
            with mc2:
                new_location = st.text_input("Village / Area *")
                new_district = st.text_input("District *")
                new_phone = st.text_input("Phone *", value=user_data.get("phone", ""))
            new_image = st.file_uploader("Product Photo", type=["jpg", "jpeg", "png"], key="new_img")
            if new_image:
                st.image(new_image, width=200)
            if st.button("Submit Listing", key="submit_listing"):
                if new_title and new_price and new_desc:
                    img_bytes = None
                    if new_image:
                        new_image.seek(0)
                        img_bytes = new_image.read()
                    price_str = f"UGX {new_price}" if not new_price.startswith("UGX") else new_price
                    saved = db_save_listing(
                        new_title, new_desc, user_data.get("full_name", ""), new_phone,
                        new_location, new_district, price_str,
                        "sell" if new_type == "Selling" else "buy", new_tag, img_bytes, user,
                    )
                    if saved:
                        st.success("Listing posted successfully!")
                        st.rerun()
                    else:
                        st.error("Could not save listing (image may be too large or DB error).")
                else:
                    st.warning("Please fill in all required fields.")

    # ══════════════════════════════════════════════════════════════════════════
    # FARMER CHAT
    # ══════════════════════════════════════════════════════════════════════════
    elif active == "Farmer Chat":
        st.markdown(
            """<div class="page-hdr">
            <div class="page-hdr-title">Farmer Chat</div>
            <div class="page-hdr-sub">Secure group chat rooms — messages are obfuscated and saved to the database</div>
        </div>""",
            unsafe_allow_html=True,
        )

        st.markdown("<strong>Select a Room</strong><br><br>", unsafe_allow_html=True)
        room_cols = st.columns(4)
        for idx, (room_key, room_info) in enumerate(CHAT_ROOMS.items()):
            with room_cols[idx]:
                is_active = st.session_state.active_room == room_key
                label = f"[ {room_info['name']} ]" if is_active else room_info["name"]
                if st.button(label, key=f"room_{room_key}", use_container_width=True):
                    st.session_state.active_room = room_key
                    st.rerun()

        active_room = st.session_state.active_room
        room_info = CHAT_ROOMS[active_room]
        st.markdown(
            f"""<div style="margin:16px 0 12px;display:flex;align-items:center;gap:10px;">
            <span style="font-weight:700;font-size:1rem;color:#1a1a1a;">{escape(room_info['name'])}</span>
            <span style="font-size:0.75rem;background:#e8f5e9;color:#2E7D32;padding:3px 8px;border-radius:4px;font-weight:600;">Secured</span>
        </div>""",
            unsafe_allow_html=True,
        )

        messages = db_get_messages(active_room, limit=60)
        if not messages:
            st.markdown(
                '<div class="ep-alert ep-alert-info"><div class="ep-alert-text">No messages yet in this room. Be the first to say something.</div></div>',
                unsafe_allow_html=True,
            )
        else:
            for msg in messages:
                is_me = msg.get("sender") == user
                decrypted = decrypt_message(msg.get("encrypted_text", ""))
                safe_text = escape(decrypted)
                safe_name = escape(msg.get("display_name", "User"))
                safe_time = escape(f"{msg.get('msg_time', '')} — {msg.get('msg_date', '')}")
                if is_me:
                    st.markdown(
                        f"""<div style="display:flex;flex-direction:column;align-items:flex-end;margin-bottom:8px;">
                        <div class="msg-me">{safe_text}<div class="msg-time">{safe_time}</div></div>
                    </div>""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"""<div style="display:flex;flex-direction:column;align-items:flex-start;margin-bottom:8px;">
                        <div class="msg-name">{safe_name}</div>
                        <div class="msg-other">{safe_text}<div class="msg-time">{safe_time}</div></div>
                    </div>""",
                        unsafe_allow_html=True,
                    )

        st.markdown("<br>", unsafe_allow_html=True)
        with st.form(f"chat_form_{active_room}", clear_on_submit=True):
            ci, cs = st.columns([5, 1])
            with ci:
                new_msg = st.text_input("", placeholder=f"Message {room_info['name']}...", label_visibility="collapsed")
            with cs:
                send_btn = st.form_submit_button("Send")

        if send_btn and new_msg.strip():
            db_save_message(active_room, user, user_data.get("full_name", user), encrypt_message(new_msg.strip()))
            st.rerun()

        if st.button("Refresh Messages", key="refresh_chat"):
            st.rerun()

        st.markdown(
            """<div class="ep-alert ep-alert-success" style="margin-top:12px;">
            <div class="ep-alert-text">Messages are obfuscated with a shared application secret and stored in the database. This is not true end-to-end encryption.</div>
        </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # Footer
    st.markdown(
        """
    <div style="text-align:center;padding:32px 20px;font-size:0.75rem;color:#bbb;border-top:1px solid #f0f0f0;margin-top:48px;">
        EcoPulse &nbsp;|&nbsp; Team GreenPulse &nbsp;|&nbsp; Elias Creations &nbsp;|&nbsp; Busitema University
    </div>""",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.current_user is None:
    show_auth()
else:
    show_main_app()
