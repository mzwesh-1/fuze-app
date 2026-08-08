"""
db.py — Full SQLite database layer for CMT SA Voice Assistant V2.
"""

import sqlite3
import hashlib
import secrets
import datetime
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "cmt_sa_app.db")

PLANS = {
    "free":  {"limit": 10,   "price_zar": 0,    "label": "Free",  "days": 0},
    "basic": {"limit": 100,  "price_zar": 49,   "label": "Basic", "days": 30},
    "pro":   {"limit": 99999,"price_zar": 99,    "label": "Pro",   "days": 30},
}


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    c = get_conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            referral_code TEXT UNIQUE,
            referred_by TEXT,
            onboarded INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            session_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            language TEXT,
            personality TEXT,
            reaction INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS usage (
            email TEXT PRIMARY KEY,
            prompt_count INTEGER DEFAULT 0,
            last_reset TEXT
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            email TEXT PRIMARY KEY,
            plan TEXT DEFAULT 'free',
            expires_at TEXT,
            checkout_id TEXT
        );
        CREATE TABLE IF NOT EXISTS rate_limits (
            email TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shared_chats (
            share_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS flashcards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            front TEXT NOT NULL,
            back TEXT NOT NULL,
            subject TEXT,
            language TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS verification_codes (
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            purpose TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS cloned_voices (
            email TEXT NOT NULL,
            voice_id TEXT NOT NULL,
            voice_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS language_voices (
            language_key TEXT PRIMARY KEY,
            elevenlabs_voice_id TEXT NOT NULL,
            voice_name TEXT NOT NULL,
            recorded_by TEXT,
            created_at TEXT NOT NULL
        );
    """)
    c.commit()
    c.close()


# ── Password ──────────────────────────────────────────────────────────────────
def _hash(pw, salt):
    return hashlib.sha256((salt + pw).encode()).hexdigest()


def create_user(email, password, referred_by_code=None):
    c = get_conn()
    if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        c.close()
        return False
    salt = secrets.token_hex(16)
    ref_code = secrets.token_urlsafe(8)
    now = datetime.datetime.now().isoformat()
    c.execute(
        "INSERT INTO users (email,password_hash,salt,referral_code,referred_by,created_at) VALUES (?,?,?,?,?,?)",
        (email, _hash(password, salt), salt, ref_code, referred_by_code, now))
    c.execute("INSERT INTO usage (email,prompt_count,last_reset) VALUES (?,0,?)", (email, now))
    c.execute("INSERT INTO subscriptions (email,plan) VALUES (?,'free')", (email,))
    # Referral bonus
    if referred_by_code:
        row = c.execute("SELECT email FROM users WHERE referral_code=?", (referred_by_code,)).fetchone()
        if row:
            _add_referral_bonus(c, row["email"])
            _add_referral_bonus(c, email)
    c.commit()
    c.close()
    return True


def _add_referral_bonus(conn, email, bonus=5):
    conn.execute(
        "UPDATE usage SET prompt_count = MAX(0, prompt_count - ?) WHERE email=?",
        (bonus, email))


def verify_login(email, password):
    c = get_conn()
    row = c.execute("SELECT password_hash,salt FROM users WHERE email=?", (email,)).fetchone()
    c.close()
    return row and _hash(password, row["salt"]) == row["password_hash"]


def get_user(email):
    c = get_conn()
    row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    c.close()
    return dict(row) if row else None


def set_onboarded(email):
    c = get_conn()
    c.execute("UPDATE users SET onboarded=1 WHERE email=?", (email,))
    c.commit()
    c.close()


def get_referral_code(email):
    c = get_conn()
    row = c.execute("SELECT referral_code FROM users WHERE email=?", (email,)).fetchone()
    c.close()
    return row["referral_code"] if row else None


# ── Chat history ──────────────────────────────────────────────────────────────
def save_message(email, role, content, language=None, personality=None, session_id=None):
    c = get_conn()
    c.execute(
        "INSERT INTO chat_history (email,session_id,role,content,language,personality,created_at) VALUES (?,?,?,?,?,?,?)",
        (email, session_id, role, content, language, personality, datetime.datetime.now().isoformat()))
    c.commit()
    c.close()


def get_history(email, session_id=None, limit=200):
    c = get_conn()
    if session_id:
        rows = c.execute(
            "SELECT * FROM chat_history WHERE email=? AND session_id=? ORDER BY id ASC LIMIT ?",
            (email, session_id, limit)).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM chat_history WHERE email=? ORDER BY id ASC LIMIT ?",
            (email, limit)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def clear_history(email):
    c = get_conn()
    c.execute("DELETE FROM chat_history WHERE email=?", (email,))
    c.commit()
    c.close()


def set_reaction(msg_id, reaction):
    c = get_conn()
    c.execute("UPDATE chat_history SET reaction=? WHERE id=?", (reaction, msg_id))
    c.commit()
    c.close()


# ── Usage & limits ────────────────────────────────────────────────────────────
def get_prompt_count(email):
    c = get_conn()
    row = c.execute("SELECT prompt_count FROM usage WHERE email=?", (email,)).fetchone()
    c.close()
    return row["prompt_count"] if row else 0


def increment_prompt(email):
    c = get_conn()
    c.execute("UPDATE usage SET prompt_count=prompt_count+1 WHERE email=?", (email,))
    c.commit()
    c.close()


def get_plan(email):
    c = get_conn()
    row = c.execute("SELECT plan,expires_at FROM subscriptions WHERE email=?", (email,)).fetchone()
    c.close()
    if not row:
        return "free"
    if row["plan"] != "free" and row["expires_at"]:
        if datetime.datetime.now() > datetime.datetime.fromisoformat(row["expires_at"]):
            return "free"
    return row["plan"]


def get_plan_limit(email):
    plan = get_plan(email)
    return PLANS.get(plan, PLANS["free"])["limit"]


def can_send(email):
    return get_prompt_count(email) < get_plan_limit(email)


def remaining(email):
    return max(0, get_plan_limit(email) - get_prompt_count(email))


def get_subscription_info(email):
    c = get_conn()
    row = c.execute("SELECT * FROM subscriptions WHERE email=?", (email,)).fetchone()
    c.close()
    return dict(row) if row else None


def activate_subscription(email, plan="pro", days=30, checkout_id=None):
    expires = (datetime.datetime.now() + datetime.timedelta(days=days)).isoformat()
    c = get_conn()
    c.execute(
        "INSERT INTO subscriptions (email,plan,expires_at,checkout_id) VALUES (?,?,?,?) "
        "ON CONFLICT(email) DO UPDATE SET plan=?,expires_at=?,checkout_id=?",
        (email, plan, expires, checkout_id, plan, expires, checkout_id))
    c.execute("UPDATE usage SET prompt_count=0 WHERE email=?", (email,))
    c.commit()
    c.close()


# ── Rate limiting ─────────────────────────────────────────────────────────────
def check_rate_limit(email, max_per_minute=5):
    c = get_conn()
    cutoff = (datetime.datetime.now() - datetime.timedelta(minutes=1)).isoformat()
    c.execute("DELETE FROM rate_limits WHERE timestamp < ?", (cutoff,))
    count = c.execute(
        "SELECT COUNT(*) as n FROM rate_limits WHERE email=? AND timestamp>=?",
        (email, cutoff)).fetchone()["n"]
    if count >= max_per_minute:
        c.close()
        return False
    c.execute("INSERT INTO rate_limits (email,timestamp) VALUES (?,?)",
              (email, datetime.datetime.now().isoformat()))
    c.commit()
    c.close()
    return True


# ── Shared chats ──────────────────────────────────────────────────────────────
def create_shared_chat(email, session_id):
    share_id = secrets.token_urlsafe(12)
    c = get_conn()
    c.execute("INSERT INTO shared_chats VALUES (?,?,?,?)",
              (share_id, email, session_id, datetime.datetime.now().isoformat()))
    c.commit()
    c.close()
    return share_id


def get_shared_chat(share_id):
    c = get_conn()
    row = c.execute("SELECT * FROM shared_chats WHERE share_id=?", (share_id,)).fetchone()
    if not row:
        c.close()
        return None
    messages = c.execute(
        "SELECT role,content,language FROM chat_history WHERE email=? AND session_id=? ORDER BY id",
        (row["email"], row["session_id"])).fetchall()
    c.close()
    return [dict(m) for m in messages]


# ── Flashcards ────────────────────────────────────────────────────────────────
def save_flashcard(email, front, back, subject=None, language=None):
    c = get_conn()
    c.execute("INSERT INTO flashcards (email,front,back,subject,language,created_at) VALUES (?,?,?,?,?,?)",
              (email, front, back, subject, language, datetime.datetime.now().isoformat()))
    c.commit()
    c.close()


def get_flashcards(email, subject=None):
    c = get_conn()
    if subject:
        rows = c.execute("SELECT * FROM flashcards WHERE email=? AND subject=? ORDER BY id DESC",
                         (email, subject)).fetchall()
    else:
        rows = c.execute("SELECT * FROM flashcards WHERE email=? ORDER BY id DESC", (email,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def delete_flashcards(email):
    c = get_conn()
    c.execute("DELETE FROM flashcards WHERE email=?", (email,))
    c.commit()
    c.close()


# ── Admin ─────────────────────────────────────────────────────────────────────
def is_admin(email):
    c = get_conn()
    row = c.execute("SELECT is_admin FROM users WHERE email=?", (email,)).fetchone()
    c.close()
    return row and row["is_admin"] == 1


def make_admin(email):
    c = get_conn()
    c.execute("UPDATE users SET is_admin=1 WHERE email=?", (email,))
    c.commit()
    c.close()


# ── Email verification & password reset ───────────────────────────────────────
def save_verification_code(email, code, purpose="verify"):
    """purpose: 'verify' or 'reset'"""
    expires = (datetime.datetime.now() + datetime.timedelta(minutes=15)).isoformat()
    c = get_conn()
    c.execute("DELETE FROM verification_codes WHERE email=? AND purpose=?", (email, purpose))
    c.execute("INSERT INTO verification_codes (email,code,purpose,expires_at) VALUES (?,?,?,?)",
              (email, code, purpose, expires))
    c.commit()
    c.close()


def check_verification_code(email, code, purpose="verify"):
    c = get_conn()
    row = c.execute(
        "SELECT * FROM verification_codes WHERE email=? AND code=? AND purpose=? AND used=0",
        (email, code, purpose)).fetchone()
    if not row:
        c.close()
        return False
    if datetime.datetime.now() > datetime.datetime.fromisoformat(row["expires_at"]):
        c.close()
        return False
    c.execute("UPDATE verification_codes SET used=1 WHERE email=? AND code=? AND purpose=?",
              (email, code, purpose))
    c.commit()
    c.close()
    return True


def set_email_verified(email):
    c = get_conn()
    c.execute("UPDATE users SET onboarded=1 WHERE email=?", (email,))
    c.commit()
    c.close()


def reset_password(email, new_password):
    c = get_conn()
    salt = secrets.token_hex(16)
    pw_hash = _hash(new_password, salt)
    c.execute("UPDATE users SET password_hash=?, salt=? WHERE email=?", (pw_hash, salt, email))
    c.commit()
    c.close()


def user_exists(email):
    c = get_conn()
    row = c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
    c.close()
    return row is not None


# ── Cloned voices ─────────────────────────────────────────────────────────────
def save_cloned_voice(email, voice_id, voice_name):
    c = get_conn()
    c.execute("INSERT INTO cloned_voices (email,voice_id,voice_name,created_at) VALUES (?,?,?,?)",
              (email, voice_id, voice_name, datetime.datetime.now().isoformat()))
    c.commit()
    c.close()


def get_cloned_voices(email):
    c = get_conn()
    rows = c.execute("SELECT * FROM cloned_voices WHERE email=? ORDER BY created_at DESC",
                     (email,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def delete_cloned_voice_record(email, voice_id):
    c = get_conn()
    c.execute("DELETE FROM cloned_voices WHERE email=? AND voice_id=?", (email, voice_id))
    c.commit()
    c.close()


# ── Language voice overrides (admin-set voices per language) ──────────────────
def set_language_voice(language_key, elevenlabs_voice_id, voice_name, recorded_by=None):
    c = get_conn()
    c.execute(
        "INSERT INTO language_voices (language_key, elevenlabs_voice_id, voice_name, recorded_by, created_at) "
        "VALUES (?,?,?,?,?) ON CONFLICT(language_key) DO UPDATE SET "
        "elevenlabs_voice_id=?, voice_name=?, recorded_by=?",
        (language_key, elevenlabs_voice_id, voice_name, recorded_by,
         datetime.datetime.now().isoformat(),
         elevenlabs_voice_id, voice_name, recorded_by))
    c.commit()
    c.close()


def get_language_voice(language_key):
    """Returns the ElevenLabs voice_id for a language, or None if not set."""
    c = get_conn()
    row = c.execute(
        "SELECT elevenlabs_voice_id, voice_name FROM language_voices WHERE language_key=?",
        (language_key,)).fetchone()
    c.close()
    return dict(row) if row else None


def get_all_language_voices():
    c = get_conn()
    rows = c.execute("SELECT * FROM language_voices ORDER BY language_key").fetchall()
    c.close()
    return [dict(r) for r in rows]


def remove_language_voice(language_key):
    c = get_conn()
    c.execute("DELETE FROM language_voices WHERE language_key=?", (language_key,))
    c.commit()
    c.close()


def admin_stats():
    c = get_conn()
    stats = {
        "total_users": c.execute("SELECT COUNT(*) as n FROM users").fetchone()["n"],
        "pro_users": c.execute("SELECT COUNT(*) as n FROM subscriptions WHERE plan='pro'").fetchone()["n"],
        "basic_users": c.execute("SELECT COUNT(*) as n FROM subscriptions WHERE plan='basic'").fetchone()["n"],
        "total_messages": c.execute("SELECT COUNT(*) as n FROM chat_history").fetchone()["n"],
        "positive_reactions": c.execute("SELECT COUNT(*) as n FROM chat_history WHERE reaction=1").fetchone()["n"],
        "negative_reactions": c.execute("SELECT COUNT(*) as n FROM chat_history WHERE reaction=-1").fetchone()["n"],
        "languages_used": [r["language"] for r in c.execute(
            "SELECT DISTINCT language FROM chat_history WHERE language IS NOT NULL").fetchall()],
    }
    recent = c.execute(
        "SELECT email,created_at FROM users ORDER BY created_at DESC LIMIT 10").fetchall()
    stats["recent_signups"] = [dict(r) for r in recent]
    c.close()
    return stats
