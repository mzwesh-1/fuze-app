"""
whitelabel.py — White-label configuration for businesses.

Businesses can brand the assistant as their own by setting their
org config in the database.

Usage:
    import whitelabel
    config = whitelabel.get_config("acme-corp")
    # config = {"name": "Acme AI", "logo_url": "...", "primary_color": "#FF0000", ...}
"""

import json
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "cmt_sa_app.db")

DEFAULT_CONFIG = {
    "org_id": "cmt",
    "name": "CMT SA Voice Assistant",
    "tagline": "Speak. It thinks. It replies — in your language.",
    "logo_url": "",
    "primary_color": "#00C9A7",
    "secondary_color": "#FFB703",
    "background_dark": "#0D1B2A",
    "background_light": "#F0F4F8",
    "footer_text": "🇿🇦 Sikhona · We exist · Powered by CMT",
    "allowed_languages": None,  # None = all languages
    "allowed_personalities": None,  # None = all
    "max_free_prompts": 10,
    "custom_system_prompt": None,  # Override the default AI system prompt
}


def init_whitelabel_table():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS whitelabel (
            org_id TEXT PRIMARY KEY,
            config_json TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_config(org_id: str, config: dict):
    """Save or update a white-label config."""
    init_whitelabel_table()
    merged = {**DEFAULT_CONFIG, **config, "org_id": org_id}
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        "INSERT INTO whitelabel (org_id, config_json) VALUES (?, ?) "
        "ON CONFLICT(org_id) DO UPDATE SET config_json = ?",
        (org_id, json.dumps(merged), json.dumps(merged)),
    )
    conn.commit()
    conn.close()


def get_config(org_id: str = None) -> dict:
    """
    Get white-label config. If org_id is None or not found,
    returns the default CMT branding.
    """
    if not org_id:
        return DEFAULT_CONFIG.copy()

    init_whitelabel_table()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT config_json FROM whitelabel WHERE org_id = ?", (org_id,)).fetchone()
    conn.close()

    if row:
        return json.loads(row["config_json"])
    return DEFAULT_CONFIG.copy()


def list_orgs() -> list:
    """List all white-label organizations."""
    init_whitelabel_table()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    rows = conn.execute("SELECT org_id FROM whitelabel").fetchall()
    conn.close()
    return [r[0] for r in rows]


def apply_streamlit_theme(config: dict):
    """Apply white-label colors to Streamlit via CSS injection."""
    import streamlit as st

    primary = config.get("primary_color", "#00C9A7")
    secondary = config.get("secondary_color", "#FFB703")
    bg_dark = config.get("background_dark", "#0D1B2A")
    bg_light = config.get("background_light", "#F0F4F8")

    st.markdown(f"""<style>
        .stApp {{ background-color: {bg_dark}; color: {bg_light}; }}
        .stSidebar {{ background-color: {bg_dark} !important; }}
        .stButton > button[kind="primary"] {{ background-color: {primary} !important; }}
        h1, h2, h3 {{ color: {primary} !important; }}
        .stChatMessage {{ background-color: rgba(255,255,255,0.05) !important; }}
        a {{ color: {secondary} !important; }}
    </style>""", unsafe_allow_html=True)


# ── Example: create a white-label config for a business ───────────────────────
# save_config("acme-corp", {
#     "name": "Acme AI Assistant",
#     "tagline": "Your Acme-powered AI helper",
#     "logo_url": "https://acme.com/logo.png",
#     "primary_color": "#FF4444",
#     "secondary_color": "#4444FF",
#     "footer_text": "Powered by Acme Corp",
#     "allowed_languages": ["isizulu", "english", "afrikaans"],
#     "max_free_prompts": 5,
# })
