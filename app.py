"""
app.py — CMT SA Voice Assistant V2 (Full Feature)
Developed by Mzwandile Zulu | Creative Minds Technologies AI | Sala Innovation Labs

Run with: streamlit run app.py
"""

import streamlit as st
import datetime
import secrets
import time
import os

import db
import voices
import brain
import audio_helper
import payments_yoco
import whitelabel

# Optional imports — app still works if these services aren't configured
try:
    import email_service
except Exception:
    email_service = None

try:
    import voice_cloning
except Exception:
    voice_cloning = None

st.set_page_config(page_title="CMT SA Voice Assistant", page_icon="🇿🇦", layout="wide")
db.init_db()

# Auto-grant admin to the configured admin email
_admin = os.environ.get("CMT_ADMIN_EMAIL", "")
if not _admin:
    try:
        _admin = st.secrets.get("CMT_ADMIN_EMAIL", "")
    except Exception:
        pass
if _admin:
    try:
        db.make_admin(_admin)
    except Exception:
        pass

# ── Mobile-responsive CSS ─────────────────────────────────────────────────────
st.markdown("""<style>
    @media (max-width: 768px) {
        .stSidebar { min-width: 0 !important; width: 260px !important; }
        .block-container { padding: 1rem 0.5rem !important; }
        .stChatMessage { font-size: 14px !important; }
        h1 { font-size: 1.5rem !important; }
        h2 { font-size: 1.2rem !important; }
    }
    .read-along-word { display: inline; padding: 2px 4px; border-radius: 4px; transition: background 0.2s; }
    .read-along-word.active { background: #FFB703; color: #0D1B2A; font-weight: bold; }
</style>""", unsafe_allow_html=True)

# ── Session defaults ──────────────────────────────────────────────────────────
DEFAULTS = {
    "logged_in": False, "email": None, "history": [], "session_id": None,
    "personality": "assistant", "subject": None, "mode": "chat",
    "dark_mode": False, "show_upgrade": False, "quiz_data": None,
    "show_plans": False, "just_registered": False,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.session_id is None:
    st.session_state.session_id = secrets.token_urlsafe(8)


# ── Theme ─────────────────────────────────────────────────────────────────────
def apply_theme():
    if st.session_state.dark_mode:
        st.markdown("""<style>
            .stApp { background-color: #0D1B2A; color: #F0F4F8; }
            .stChatMessage { background-color: #1B2E44 !important; }
            .stSidebar { background-color: #1B2E44 !important; }
            h1,h2,h3,h4,p,span,label { color: #F0F4F8 !important; }
        </style>""", unsafe_allow_html=True)

apply_theme()


# ── Account deletion ──────────────────────────────────────────────────────────
def _delete_user_account(email):
    """Permanently delete a user and all their data."""
    c = db.get_conn()
    for table in ['users', 'chat_history', 'usage', 'subscriptions',
                   'rate_limits', 'shared_chats', 'flashcards',
                   'verification_codes', 'cloned_voices']:
        c.execute(f"DELETE FROM {table} WHERE email = ?", (email,))
    c.commit()
    c.close()


# ══════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════
def show_auth():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Apply white-label branding if org_id in URL
        org_id = st.query_params.get("org", None)
        wl = whitelabel.get_config(org_id)
        if org_id:
            whitelabel.apply_streamlit_theme(wl)

        st.markdown(f"# 🇿🇦 {wl['name']}")
        st.caption(wl["tagline"])
        st.markdown("---")

        tab1, tab2, tab3 = st.tabs(["Log In", "Sign Up", "Forgot Password"])

        with tab1:
            email = st.text_input("Email", key="li_email")
            pw = st.text_input("Password", type="password", key="li_pw")
            if st.button("Log In", use_container_width=True, type="primary"):
                if db.verify_login(email, pw):
                    st.session_state.logged_in = True
                    st.session_state.email = email
                    st.rerun()
                else:
                    st.error("Incorrect email or password.")

        with tab2:
            new_email = st.text_input("Email", key="su_email")
            new_pw = st.text_input("Password (min 6 chars)", type="password", key="su_pw")
            ref_code = st.text_input("Referral code (optional)", key="su_ref")

            if st.session_state.get("verify_step"):
                st.info(f"Verification code sent to {st.session_state.get('verify_email', '')}")
                code_input = st.text_input("Enter 6-digit code", key="verify_code")
                if st.button("Verify & Create Account", type="primary"):
                    if db.check_verification_code(st.session_state.verify_email, code_input, "verify"):
                        if db.create_user(st.session_state.verify_email,
                                         st.session_state.verify_pw,
                                         st.session_state.get("verify_ref") or None):
                            st.session_state.logged_in = True
                            st.session_state.email = st.session_state.verify_email
                            st.session_state.show_plans = True
                            st.session_state.just_registered = True
                            st.session_state.verify_step = False
                            st.rerun()
                        else:
                            st.error("Email already registered.")
                    else:
                        st.error("Invalid or expired code.")
            else:
                if st.button("Create Account", use_container_width=True):
                    if not new_email or "@" not in new_email:
                        st.error("Enter a valid email.")
                    elif len(new_pw) < 6:
                        st.error("Password must be at least 6 characters.")
                    elif db.user_exists(new_email):
                        st.error("Email already registered.")
                    elif email_service:
                        code = email_service.generate_code()
                        db.save_verification_code(new_email, code, "verify")
                        try:
                            email_service.send_verification_email(new_email, code)
                            st.session_state.verify_step = True
                            st.session_state.verify_email = new_email
                            st.session_state.verify_pw = new_pw
                            st.session_state.verify_ref = ref_code
                            st.rerun()
                        except Exception as e:
                            st.warning(f"Could not send email ({e}). Creating account without verification.")
                            db.create_user(new_email, new_pw, ref_code or None)
                            st.session_state.logged_in = True
                            st.session_state.email = new_email
                            st.session_state.show_plans = True
                            st.session_state.just_registered = True
                            st.rerun()
                    else:
                        if db.create_user(new_email, new_pw, ref_code or None):
                            st.session_state.logged_in = True
                            st.session_state.email = new_email
                            st.session_state.show_plans = True
                            st.session_state.just_registered = True
                            st.rerun()
                        else:
                            st.error("Email already registered.")

        with tab3:
            reset_email = st.text_input("Your email address", key="reset_email_input")

            if st.session_state.get("reset_step"):
                code_input = st.text_input("Enter 6-digit reset code", key="reset_code_input")
                new_pass = st.text_input("New password (min 6 chars)", type="password", key="reset_new_pw")
                if st.button("Reset Password", type="primary"):
                    if len(new_pass) < 6:
                        st.error("Password must be at least 6 characters.")
                    elif db.check_verification_code(st.session_state.pending_reset_email, code_input, "reset"):
                        db.reset_password(st.session_state.pending_reset_email, new_pass)
                        st.success("Password reset! Log in with your new password.")
                        st.session_state.reset_step = False
                    else:
                        st.error("Invalid or expired code.")
            else:
                if st.button("Send Reset Code", use_container_width=True):
                    if not reset_email or not db.user_exists(reset_email):
                        st.error("No account with that email.")
                    elif email_service:
                        code = email_service.generate_code()
                        db.save_verification_code(reset_email, code, "reset")
                        try:
                            email_service.send_password_reset_email(reset_email, code)
                            st.session_state.reset_step = True
                            st.session_state.pending_reset_email = reset_email
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not send email: {e}")
                    else:
                        st.warning("Email service not configured. Contact admin to reset your password.")


# ══════════════════════════════════════════════════════════
# ONBOARDING
# ══════════════════════════════════════════════════════════
def show_onboarding():
    user = db.get_user(st.session_state.email)
    if user and user["onboarded"]:
        return True

    st.markdown("# 👋 Welcome to CMT SA Voice Assistant!")
    st.markdown("""
    **Here's what you can do:**

    🎤 **Speak or type** in any of the 11 official South African languages

    🤖 **Choose an AI personality** — tutor, career advisor, wellness advisor, coder, and more

    📚 **Education tools** — quiz mode, exam prep, essay helper, flashcards

    📄 **Upload documents or images** — ask questions about them in your language

    🌍 **Translate** between any SA languages

    🔊 **Hear replies** in male or female SA voice
    """)
    if st.button("Let's go! →", type="primary", use_container_width=True):
        db.set_onboarded(st.session_state.email)
        st.rerun()
    return False


# ══════════════════════════════════════════════════════════
# PLANS PAGE (shown after signup — like Claude's upgrade flow)
# ══════════════════════════════════════════════════════════
def show_plans_page():
    st.markdown("# 🇿🇦 Choose Your Plan")
    st.markdown("Pick the plan that works for you. You can always upgrade later.")
    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        ### 🆓 Free
        **R0 / forever**
        """)
        st.markdown("""
        - 10 prompts total
        - All 11 SA languages
        - Voice replies (male & female)
        - Quiz & exam prep
        - No chat history
        """)
        if st.button("Start Free", use_container_width=True):
            st.session_state.show_plans = False
            st.session_state.just_registered = False
            st.rerun()

    with col2:
        st.markdown("""
        ### ⭐ Basic
        **R49 / month**
        """)
        st.markdown("""
        - 100 prompts per month
        - All 11 SA languages
        - Voice replies (male & female)
        - Chat history saved
        - Quiz & exam prep
        - Document & image input
        - Download MP3
        """)
        if st.button("Get Basic — R49", use_container_width=True, type="primary"):
            start_payment("basic")

    with col3:
        st.markdown("""
        ### 🚀 Pro
        **R99 / month**
        """)
        st.markdown("""
        - **Unlimited** prompts
        - All 11 SA languages
        - Voice replies (male & female)
        - Chat history saved
        - Quiz & exam prep
        - Document & image input
        - Download MP3
        - Voice cloning (your own voice)
        - API access for developers
        - Priority support
        """)
        if st.button("Get Pro — R99", use_container_width=True, type="primary"):
            start_payment("pro")

    st.markdown("---")
    st.caption("All plans include all 11 SA languages, male & female voices, and AI-powered replies.")

    if st.session_state.get("pending_checkout_id"):
        st.divider()
        if st.button("✅ I've paid — verify now", type="primary"):
            try:
                status = payments_yoco.check_checkout_status(st.session_state.pending_checkout_id)
                if status == "completed":
                    p = st.session_state.get("pending_plan", "pro")
                    db.activate_subscription(st.session_state.email, plan=p,
                        days=db.PLANS[p]["days"], checkout_id=st.session_state.pending_checkout_id)
                    st.success(f"You're now on {db.PLANS[p]['label']}! 🎉")
                    st.session_state.pending_checkout_id = None
                    st.session_state.show_plans = False
                    st.rerun()
                else:
                    st.warning(f"Status: {status} — try again in a few seconds.")
            except Exception as e:
                st.error(f"Verification error: {e}")


# ══════════════════════════════════════════════════════════
# ADMIN DASHBOARD (accessible via ?page=admin)
# ══════════════════════════════════════════════════════════
def show_admin_page():
    if not st.session_state.logged_in:
        st.error("Please log in first.")
        return
    if not db.is_admin(st.session_state.email):
        st.error("🚫 Access denied. Admin only.")
        return

    st.markdown("# 📊 Admin Dashboard")
    st.markdown(f"Logged in as: **{st.session_state.email}** (Admin)")
    st.markdown("---")

    stats = db.admin_stats()

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("👥 Total Users", stats["total_users"])
    col2.metric("⭐ Pro Users", stats["pro_users"])
    col3.metric("💬 Total Messages", stats["total_messages"])
    col4.metric("👍 / 👎", f"{stats['positive_reactions']} / {stats['negative_reactions']}")

    st.markdown("---")

    # Two columns for details
    left, right = st.columns(2)

    with left:
        st.markdown("### 🌍 Languages Used")
        if stats["languages_used"]:
            for lang in stats["languages_used"]:
                display = voices.LANGUAGES.get(lang, {}).get("display", lang) if lang else "Unknown"
                st.write(f"• {display}")
        else:
            st.caption("No messages yet.")

        st.markdown("### 👤 Recent Signups")
        for u in stats["recent_signups"]:
            st.caption(f"📧 {u['email']} — {u['created_at'][:10]}")

    with right:
        st.markdown("### 🔧 Admin Actions")

        st.markdown("**Make someone admin:**")
        admin_email = st.text_input("Email to make admin", key="admin_grant_email")
        if st.button("Grant Admin", use_container_width=True):
            if admin_email and db.user_exists(admin_email):
                db.make_admin(admin_email)
                st.success(f"✅ {admin_email} is now admin.")
            else:
                st.error("User not found.")

        st.markdown("**Activate subscription manually:**")
        sub_email = st.text_input("Email", key="admin_sub_email")
        sub_plan = st.selectbox("Plan", ["basic", "pro"], key="admin_sub_plan")
        if st.button("Activate Subscription", use_container_width=True):
            if sub_email and db.user_exists(sub_email):
                db.activate_subscription(sub_email, plan=sub_plan, days=30)
                st.success(f"✅ {sub_email} upgraded to {sub_plan}.")
            else:
                st.error("User not found.")

        st.markdown("**Reset user's prompt count:**")
        reset_email = st.text_input("Email", key="admin_reset_email")
        if st.button("Reset Prompts", use_container_width=True):
            if reset_email:
                from db import get_conn
                c = get_conn()
                c.execute("UPDATE usage SET prompt_count=0 WHERE email=?", (reset_email,))
                c.commit()
                c.close()
                st.success(f"✅ Prompts reset for {reset_email}.")

    # Feedback / learning from users
    st.markdown("---")
    st.markdown("### 🧠 AI Learning — User Feedback")
    st.caption("Messages that users rated negatively (👎) — review these to improve the AI.")

    c = db.get_conn()
    bad_replies = c.execute(
        "SELECT email, content, language, personality, created_at FROM chat_history "
        "WHERE reaction = -1 ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    c.close()

    if bad_replies:
        for r in bad_replies:
            with st.expander(f"👎 {r['created_at'][:16]} — {r['email']} ({r['language'] or '?'})"):
                st.write(r["content"])
                st.caption(f"Personality: {r['personality'] or 'assistant'}")
    else:
        st.success("No negative feedback yet — users are happy! 🎉")

    st.markdown("---")
    if st.button("🚪 Back to App", use_container_width=True):
        st.query_params.clear()
        st.rerun()

    # ── Voice Management (record + clone per language) ────────────────────────
    st.markdown("---")
    st.markdown("### 🎙️ Voice Management — Record & Clone")
    st.markdown(
        "Record yourself (or a native speaker) for each language. "
        "The recording is sent to ElevenLabs which clones the voice, "
        "then all AI replies in that language will use the cloned voice."
    )

    elevenlabs_key = os.environ.get("CMT_ELEVENLABS_KEY")
    if not elevenlabs_key:
        st.warning(
            "Set CMT_ELEVENLABS_KEY in your Streamlit secrets to enable voice cloning.\n"
            "Get a free key at https://elevenlabs.io/"
        )
    else:
        # Languages that need custom voices (already have native Azure voices: isizulu, afrikaans, english)
        NEEDS_VOICE = {
            "isixhosa": "isiXhosa",
            "sesotho": "Sesotho",
            "setswana": "Setswana",
            "sepedi": "Sepedi",
            "siswati": "siSwati",
            "isindebele": "isiNdebele",
            "tshivenda": "Tshivenda",
            "xitsonga": "Xitsonga",
        }

        # Show current status
        st.markdown("#### Current voice status")
        existing = db.get_all_language_voices()
        existing_map = {v["language_key"]: v for v in existing}

        status_data = []
        for key, display in NEEDS_VOICE.items():
            if key in existing_map:
                v = existing_map[key]
                status_data.append([display, f"✅ {v['voice_name']}", v.get("recorded_by", "—")])
            else:
                status_data.append([display, "❌ Using default Azure voice", "—"])

        status_table = [[
            Paragraph("Language", s_th) if False else "Language",
            "Voice Status",
            "Recorded by",
        ]] + status_data
        st.table(status_data)

        st.markdown("#### Record a new voice")
        sel_lang = st.selectbox(
            "Choose language to record",
            list(NEEDS_VOICE.keys()),
            format_func=lambda k: NEEDS_VOICE[k],
            key="admin_voice_lang",
        )

        st.info(
            f"🎤 Record yourself speaking {NEEDS_VOICE[sel_lang]} for at least 1 minute. "
            f"Read a paragraph of text naturally — don't rush. The more natural you sound, "
            f"the better the clone will be."
        )

        sample_texts = {
            "isixhosa": "Molo. Igama lam nguMzwandile. Ndivela eMzantsi Afrika. Ndithanda ukufunda ngekhompyutha.",
            "sesotho": "Dumela. Lebitso la ka ke Mzwandile. Ke tswa Afrika Borwa. Ke rata ho ithuta ka likhomphutha.",
            "setswana": "Dumela. Leina la me ke Mzwandile. Ke tswa Aforika Borwa. Ke rata go ithuta ka dikhomphiutha.",
            "sepedi": "Thobela. Leina la ka ke Mzwandile. Ke tšwa Afrika Borwa. Ke rata go ithuta ka dikhomphiutha.",
            "siswati": "Sawubona. Ligama lami nguMzwandile. Ngiphuma eNingizimu Afrika. Ngitsandza kufundza ngemacomputer.",
            "isindebele": "Lotjhani. Ibizo lami nguMzwandile. Ngivela eSewula Afrika. Ngithanda ukufunda ngamakhompyutha.",
            "tshivenda": "Ndaa. Dzina langa ndi Mzwandile. Ndi bva Afrika Tshipembe. Ndi funa u guda nga khomphyutha.",
            "xitsonga": "Avuxeni. Vito ra mina i Mzwandile. Ndzi huma Afrika Dzonga. Ndzi rhandza ku dyondza hi tikhomphyutha.",
        }

        st.markdown(f"**Suggested text to read (read this out loud):**")
        st.text_area("Sample text", sample_texts.get(sel_lang, ""), height=80, key="sample_text_display", disabled=True)

        recorder_name = st.text_input("Who is recording? (your name)", value="Mzwandile", key="admin_recorder")
        voice_recording = st.audio_input(f"🎤 Record {NEEDS_VOICE[sel_lang]} voice (1+ minute)", key="admin_voice_rec")

        if st.button(f"🧬 Clone {NEEDS_VOICE[sel_lang]} voice", type="primary") and voice_recording:
            with st.spinner(f"Cloning {NEEDS_VOICE[sel_lang]} voice... this takes about 30 seconds"):
                try:
                    audio_bytes = voice_recording.read()
                    clone_name = f"CMT-{NEEDS_VOICE[sel_lang]}-{recorder_name}"
                    vid = voice_cloning.clone_voice(clone_name, audio_bytes,
                        description=f"South African {NEEDS_VOICE[sel_lang]} voice for Fuze AI")
                    db.set_language_voice(sel_lang, vid, clone_name, recorder_name)
                    st.success(f"✅ {NEEDS_VOICE[sel_lang]} voice cloned successfully as '{clone_name}'!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Cloning failed: {e}")

        # Test existing cloned voices
        if existing:
            st.markdown("#### Test cloned voices")
            for v in existing:
                lang_display = NEEDS_VOICE.get(v["language_key"], v["language_key"])
                col1, col2, col3 = st.columns([2, 3, 1])
                with col1:
                    st.write(f"🎙️ {lang_display}: {v['voice_name']}")
                with col2:
                    test = st.text_input("Test", value="Sawubona, unjani namhlanje?",
                        key=f"admin_test_{v['language_key']}")
                with col3:
                    if st.button("🔊", key=f"admin_play_{v['language_key']}"):
                        try:
                            ab = voice_cloning.speak_with_clone(test, v["elevenlabs_voice_id"])
                            st.audio(ab, format="audio/mp3")
                        except Exception as e:
                            st.error(str(e))

            # Remove a voice
            st.markdown("#### Remove a cloned voice")
            remove_lang = st.selectbox("Language to remove", [v["language_key"] for v in existing],
                format_func=lambda k: NEEDS_VOICE.get(k, k), key="admin_remove_lang")
            if st.button("🗑️ Remove this voice"):
                v = existing_map.get(remove_lang)
                if v:
                    try:
                        voice_cloning.delete_cloned_voice(v["elevenlabs_voice_id"])
                    except Exception:
                        pass
                    db.remove_language_voice(remove_lang)
                    st.success(f"Removed {NEEDS_VOICE.get(remove_lang, remove_lang)} voice.")
                    st.rerun()


# ══════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════
def show_sidebar():
    email = st.session_state.email
    plan = db.get_plan(email)
    plan_info = db.PLANS.get(plan, db.PLANS["free"])

    with st.sidebar:
        st.markdown(f"### 🇿🇦 CMT SA Voice Assistant")
        st.caption(f"Logged in as: {email}")

        # Plan status
        if plan == "free":
            rem = db.remaining(email)
            st.info(f"Free plan — {rem}/{plan_info['limit']} prompts left")
        else:
            sub = db.get_subscription_info(email)
            if sub and sub.get("expires_at"):
                exp = datetime.datetime.fromisoformat(sub["expires_at"])
                st.success(f"✅ {plan_info['label']} plan — expires {exp.strftime('%d %b %Y')}")

        st.divider()

        # ── Language ──
        st.markdown("#### 🌍 Language")
        lang_opts = voices.language_options()
        lang_labels = [d for _, d in lang_opts]
        lang_keys = [k for k, _ in lang_opts]
        idx = st.selectbox("Chat language", range(len(lang_labels)),
                           format_func=lambda i: lang_labels[i], index=0)
        selected_lang = lang_keys[idx]

        # ── Voice ──
        st.markdown("#### 🔊 Voice")
        gender = st.radio("Voice", ["Female", "Male"], horizontal=True)
        read_aloud = st.checkbox("Read replies aloud", value=True)
        speed = st.slider("Voice speed", -50, 50, 0, 5, format="%d%%")

        st.divider()

        # ── Personality ──
        st.markdown("#### 🧠 AI Personality")
        personality_labels = {k: v["label"] for k, v in brain.PERSONALITIES.items()}
        personality = st.selectbox(
            "Choose personality", list(personality_labels.keys()),
            format_func=lambda k: personality_labels[k])
        st.session_state.personality = personality

        # ── Subject ──
        if personality == "tutor":
            st.markdown("#### 📚 Subject")
            subj_labels = {k: v.split("(")[0].strip() for k, v in brain.SUBJECTS.items()}
            subj = st.selectbox("Subject", [None] + list(subj_labels.keys()),
                                format_func=lambda k: "All subjects" if k is None else subj_labels[k])
            st.session_state.subject = subj

        st.divider()

        # ── Mode ──
        st.markdown("#### 🎯 Mode")
        mode = st.radio("Select mode", [
            "💬 Chat", "📝 Quiz", "📖 Exam Prep", "✏️ Essay Helper",
            "🃏 Flashcards", "🌍 Translate", "📄 Document Q&A",
            "🖼️ Image Input", "💻 Code Helper", "📝 Summariser",
            "🎤 Voice Cloning", "💬 Chat History",
        ], index=0)
        mode_map = {
            "💬 Chat": "chat", "📝 Quiz": "quiz", "📖 Exam Prep": "exam",
            "✏️ Essay Helper": "essay", "🃏 Flashcards": "flashcards",
            "🌍 Translate": "translate", "📄 Document Q&A": "document",
            "🖼️ Image Input": "image", "💻 Code Helper": "code",
            "📝 Summariser": "summarise", "🎤 Voice Cloning": "voice_clone",
            "💬 Chat History": "history",
        }
        st.session_state.mode = mode_map.get(mode, "chat")

        st.divider()

        # ── Read-along ──
        st.session_state["read_along"] = st.checkbox("📖 Read-along mode", value=False,
            help="Highlights words as they're spoken")

        # ── Theme ──
        st.session_state.dark_mode = st.toggle("🌙 Dark mode", st.session_state.dark_mode)

        # ── Actions ──
        if plan != "free":
            if st.button("🗑️ Clear chat history", use_container_width=True):
                db.clear_history(email)
                st.session_state.history = []
                st.rerun()

        # ── Referral ──
        ref_code = db.get_referral_code(email)
        if ref_code:
            st.caption(f"Referral code: `{ref_code}` (share for 5 bonus prompts each)")

        # ── Share chat ──
        if st.button("🔗 Share this chat", use_container_width=True):
            share_id = db.create_shared_chat(email, st.session_state.session_id)
            st.success(f"Share link: ?shared={share_id}")

        st.divider()
        col_logout, col_delete = st.columns(2)
        with col_logout:
            if st.button("🚪 Log Out", use_container_width=True):
                for k in DEFAULTS:
                    st.session_state[k] = DEFAULTS[k]
                st.rerun()
        with col_delete:
            if st.button("🗑️ Delete Account", use_container_width=True):
                st.session_state["confirm_delete"] = True

        if st.session_state.get("confirm_delete"):
            st.warning("⚠️ This will permanently delete your account and all data.")
            if st.button("Yes, delete my account permanently", type="primary"):
                _delete_user_account(email)
                for k in DEFAULTS:
                    st.session_state[k] = DEFAULTS[k]
                st.session_state.confirm_delete = False
                st.rerun()

        # ── Admin ──
        if db.is_admin(email):
            st.divider()
            st.markdown("#### 🔧 Admin")
            st.markdown("[📊 Open Admin Dashboard](?page=admin)")

    return selected_lang, gender, read_aloud, speed


# ══════════════════════════════════════════════════════════
# UPGRADE SCREEN
# ══════════════════════════════════════════════════════════
def show_upgrade():
    st.warning("You've used all your free prompts!")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Basic — R49/month")
        st.markdown("100 prompts per month\nChat history\nAll languages")
        if st.button("Get Basic", use_container_width=True):
            start_payment("basic")
    with col2:
        st.markdown("### Pro — R99/month")
        st.markdown("Unlimited prompts\nChat history\nAll languages\nPriority support")
        if st.button("Get Pro", use_container_width=True, type="primary"):
            start_payment("pro")


def start_payment(plan):
    try:
        plan_info = db.PLANS[plan]
        # Detect the real app URL (works on Streamlit Cloud and localhost)
        import streamlit.web.bootstrap as _bs
        try:
            # Try to get the real URL from headers
            headers = st.context.headers
            host = headers.get("Host", "localhost:8501")
            protocol = "https" if "streamlit.app" in host or "https" in headers.get("X-Forwarded-Proto", "") else "http"
            base_url = f"{protocol}://{host}"
        except Exception:
            base_url = "https://fuze-app-du93kdqgp5hvyd9awvu5cz.streamlit.app"

        checkout = payments_yoco.create_checkout(
            email=st.session_state.email,
            success_url=f"{base_url}/?payment_success=1",
            cancel_url=f"{base_url}/?payment_cancelled=1",
        )
        # Override price for the selected plan
        st.session_state.pending_checkout_id = checkout.get("id")
        st.session_state.pending_plan = plan
        st.markdown(f"[💳 Complete payment on Yoco]({checkout.get('redirectUrl')})")
        st.info("After paying, click 'Verify payment' below.")
    except Exception as e:
        st.error(f"Payment error: {e}")

    if st.session_state.get("pending_checkout_id"):
        if st.button("✅ Verify payment"):
            try:
                status = payments_yoco.check_checkout_status(st.session_state.pending_checkout_id)
                if status == "completed":
                    p = st.session_state.get("pending_plan", "pro")
                    db.activate_subscription(st.session_state.email, plan=p,
                        days=db.PLANS[p]["days"], checkout_id=st.session_state.pending_checkout_id)
                    st.success(f"You're now on {db.PLANS[p]['label']}! 🎉")
                    st.session_state.pending_checkout_id = None
                    st.rerun()
                else:
                    st.warning(f"Status: {status} — try again in a few seconds.")
            except Exception as e:
                st.error(f"Verification error: {e}")


# ══════════════════════════════════════════════════════════
# VOICE HELPERS
# ══════════════════════════════════════════════════════════
def speak_reply(text, lang_key, gender, speed):
    # Check if this language has a custom cloned voice (set by admin)
    custom = db.get_language_voice(lang_key)
    if custom and voice_cloning:
        try:
            import tempfile
            audio_bytes = voice_cloning.speak_with_clone(text, custom["elevenlabs_voice_id"])
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.write(audio_bytes)
            tmp.close()
            st.audio(tmp.name, format="audio/mp3", autoplay=True)
            with open(tmp.name, "rb") as f:
                st.download_button("⬇️ Download MP3", f.read(), file_name="reply.mp3", mime="audio/mp3")
            os.unlink(tmp.name)
            return
        except Exception:
            pass  # Fall back to Azure voice below

    # Default: use Azure voice
    voice_id = voices.get_voice_id(lang_key, gender)
    rate = f"{speed:+d}%"
    try:
        path = audio_helper.synthesize_to_file(text, voice_id, rate=rate)
        st.audio(path, format="audio/mp3", autoplay=True)
        with open(path, "rb") as f:
            st.download_button("⬇️ Download MP3", f.read(), file_name="reply.mp3",
                               mime="audio/mp3")

        if st.session_state.get("read_along"):
            words = text.split()
            html_words = " ".join(
                f'<span class="read-along-word" id="w{i}">{w}</span>'
                for i, w in enumerate(words)
            )
            duration_per_word = max(200, int(len(text) / max(len(words), 1) * 80))
            js = "".join(
                f"setTimeout(()=>{{document.getElementById('w{i}').classList.add('active');"
                f"if(document.getElementById('w{i-1}'))document.getElementById('w{i-1}').classList.remove('active');}},{i*duration_per_word});"
                for i in range(len(words))
            )
            st.markdown(
                f'<div style="padding:12px;background:rgba(0,0,0,0.3);border-radius:8px;line-height:2;">'
                f'{html_words}</div>'
                f'<script>{js}</script>',
                unsafe_allow_html=True,
            )
    except Exception as e:
        st.warning(f"Voice error: {e}")


def transcribe_audio(audio_bytes, lang_key):
    locale = voices.LANGUAGES[lang_key]["stt_locale"]
    text, _ = audio_helper.transcribe_audio_bytes(
        audio_bytes, locale=locale,
        auto_detect_locales=voices.AUTO_DETECT_LOCALES)
    return text


# ══════════════════════════════════════════════════════════
# DISPLAY CHAT HISTORY
# ══════════════════════════════════════════════════════════
def show_chat_history(email, plan):
    if plan == "free":
        st.caption("💡 Upgrade to Basic or Pro to save and view chat history.")
        return

    history = db.get_history(email, st.session_state.session_id)
    for msg in history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant" and msg.get("id"):
                c1, c2 = st.columns([1, 20])
                with c1:
                    if st.button("👍", key=f"up_{msg['id']}"):
                        db.set_reaction(msg["id"], 1)
                with c2:
                    if st.button("👎", key=f"dn_{msg['id']}"):
                        db.set_reaction(msg["id"], -1)


# ══════════════════════════════════════════════════════════
# MODE: CHAT
# ══════════════════════════════════════════════════════════
def mode_chat(lang_key, lang_display, gender, read_aloud, speed):
    email = st.session_state.email
    plan = db.get_plan(email)

    show_chat_history(email, plan)

    st.markdown("#### 🎤 Speak or type")
    audio_val = st.audio_input("Record voice message")
    typed = st.chat_input("Type your message...")

    user_text = None
    if audio_val:
        with st.spinner("Transcribing..."):
            user_text = transcribe_audio(audio_val.read(), lang_key)
    elif typed:
        user_text = typed

    if user_text:
        if not db.can_send(email):
            show_upgrade()
            return
        if not db.check_rate_limit(email):
            st.warning("Slow down — too many messages in a short time.")
            return

        with st.chat_message("user"):
            st.write(user_text)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply = brain.think(user_text, lang_display,
                    personality=st.session_state.personality,
                    history=st.session_state.history,
                    subject=st.session_state.subject)
            st.write(reply)
            if read_aloud:
                speak_reply(reply, lang_key, gender, speed)

        st.session_state.history.append({"role": "user", "content": user_text})
        st.session_state.history.append({"role": "assistant", "content": reply})
        if plan != "free":
            db.save_message(email, "user", user_text, lang_key,
                          st.session_state.personality, st.session_state.session_id)
            db.save_message(email, "assistant", reply, lang_key,
                          st.session_state.personality, st.session_state.session_id)
        db.increment_prompt(email)


# ══════════════════════════════════════════════════════════
# MODE: QUIZ
# ══════════════════════════════════════════════════════════
def mode_quiz(lang_key, lang_display, gender, read_aloud, speed):
    st.markdown("### 📝 Quiz Mode")
    subj_labels = {k: v.split("(")[0].strip() for k, v in brain.SUBJECTS.items()}
    subj = st.selectbox("Subject", list(subj_labels.keys()),
                        format_func=lambda k: subj_labels[k], key="quiz_subj")
    grade = st.selectbox("Grade level", ["10", "11", "12", "University"], key="quiz_grade")
    num = st.slider("Number of questions", 3, 10, 5, key="quiz_num")

    if st.button("Generate Quiz", type="primary"):
        if not db.can_send(st.session_state.email):
            show_upgrade()
            return
        with st.spinner("Creating quiz..."):
            quiz = brain.generate_quiz(subj, lang_display, grade, num)
        st.session_state.quiz_data = quiz
        db.increment_prompt(st.session_state.email)

    if st.session_state.quiz_data:
        st.markdown(st.session_state.quiz_data)
        if read_aloud:
            speak_reply(st.session_state.quiz_data, lang_key, gender, speed)


# ══════════════════════════════════════════════════════════
# MODE: EXAM PREP
# ══════════════════════════════════════════════════════════
def mode_exam(lang_key, lang_display, gender, read_aloud, speed):
    st.markdown("### 📖 Exam Preparation")
    subj_labels = {k: v.split("(")[0].strip() for k, v in brain.SUBJECTS.items()}
    subj = st.selectbox("Subject", list(subj_labels.keys()),
                        format_func=lambda k: subj_labels[k], key="exam_subj")
    topic = st.text_input("Specific topic (e.g. 'Newton's laws', 'Apartheid timeline')")
    level = st.radio("Level", ["matric", "university"], horizontal=True, key="exam_lvl")

    if st.button("Generate Practice Questions", type="primary") and topic:
        if not db.can_send(st.session_state.email):
            show_upgrade()
            return
        with st.spinner("Preparing questions..."):
            result = brain.exam_prep(subj, topic, lang_display, level=level)
        st.markdown(result)
        if read_aloud:
            speak_reply(result, lang_key, gender, speed)
        db.increment_prompt(st.session_state.email)


# ══════════════════════════════════════════════════════════
# MODE: ESSAY
# ══════════════════════════════════════════════════════════
def mode_essay(lang_key, lang_display, gender, read_aloud, speed):
    st.markdown("### ✏️ Essay Helper")
    instruction = st.selectbox("What do you need?", [
        "Review and improve my essay",
        "Help me plan an essay structure",
        "Check grammar and spelling",
        "Make my argument stronger",
    ])
    essay = st.text_area("Paste your essay or essay plan here:", height=250)

    if st.button("Get feedback", type="primary") and essay:
        if not db.can_send(st.session_state.email):
            show_upgrade()
            return
        with st.spinner("Reviewing..."):
            result = brain.essay_help(essay, instruction, lang_display)
        st.markdown(result)
        if read_aloud:
            speak_reply(result, lang_key, gender, speed)
        db.increment_prompt(st.session_state.email)


# ══════════════════════════════════════════════════════════
# MODE: FLASHCARDS
# ══════════════════════════════════════════════════════════
def mode_flashcards(lang_key, lang_display, gender, read_aloud, speed):
    st.markdown("### 🃏 Flashcard Generator")
    topic = st.text_input("Topic (e.g. 'Periodic table', 'SA Constitution')")
    num = st.slider("Number of cards", 5, 20, 10, key="fc_num")

    if st.button("Generate Flashcards", type="primary") and topic:
        if not db.can_send(st.session_state.email):
            show_upgrade()
            return
        with st.spinner("Creating flashcards..."):
            result = brain.generate_flashcards(topic, lang_display, num)
        st.markdown(result)
        # Parse and save
        lines = result.strip().split("\n")
        front, back = "", ""
        for line in lines:
            if line.upper().startswith("FRONT:"):
                front = line.split(":", 1)[1].strip()
            elif line.upper().startswith("BACK:"):
                back = line.split(":", 1)[1].strip()
                if front and back:
                    db.save_flashcard(st.session_state.email, front, back, topic, lang_key)
                    front, back = "", ""
        st.success(f"Flashcards saved!")
        db.increment_prompt(st.session_state.email)

    # Show saved flashcards
    cards = db.get_flashcards(st.session_state.email)
    if cards:
        st.divider()
        st.markdown("#### Your saved flashcards")
        for card in cards[:20]:
            with st.expander(card["front"]):
                st.write(card["back"])
                if read_aloud:
                    if st.button("🔊 Read", key=f"fc_read_{card['id']}"):
                        speak_reply(f"{card['front']}. {card['back']}", lang_key, gender, speed)


# ══════════════════════════════════════════════════════════
# MODE: TRANSLATE
# ══════════════════════════════════════════════════════════
def mode_translate(lang_key, lang_display, gender, read_aloud, speed):
    st.markdown("### 🌍 Translation")
    lang_opts = voices.language_options()
    lang_names = {k: d for k, d in lang_opts}

    col1, col2 = st.columns(2)
    with col1:
        from_lang = st.selectbox("From", list(lang_names.keys()),
                                 format_func=lambda k: lang_names[k], key="tr_from")
    with col2:
        to_lang = st.selectbox("To", list(lang_names.keys()),
                               format_func=lambda k: lang_names[k], index=2, key="tr_to")

    text = st.text_area("Text to translate:")
    audio_val = st.audio_input("Or record voice to translate")

    if audio_val:
        with st.spinner("Transcribing..."):
            text = transcribe_audio(audio_val.read(), from_lang)
            st.write(f"Heard: {text}")

    if st.button("Translate", type="primary") and text:
        if not db.can_send(st.session_state.email):
            show_upgrade()
            return
        with st.spinner("Translating..."):
            result = brain.translate(text, lang_names[from_lang], lang_names[to_lang])
        st.success(result)
        if read_aloud:
            speak_reply(result, to_lang, gender, speed)
        db.increment_prompt(st.session_state.email)


# ══════════════════════════════════════════════════════════
# MODE: DOCUMENT Q&A
# ══════════════════════════════════════════════════════════
def mode_document(lang_key, lang_display, gender, read_aloud, speed):
    st.markdown("### 📄 Document Q&A")
    uploaded = st.file_uploader("Upload PDF or text file", type=["pdf", "txt", "docx"])

    if uploaded:
        if uploaded.name.endswith(".txt"):
            doc_text = uploaded.read().decode("utf-8", errors="replace")
        elif uploaded.name.endswith(".pdf"):
            try:
                import fitz  # PyMuPDF
                pdf = fitz.open(stream=uploaded.read(), filetype="pdf")
                doc_text = "\n".join(page.get_text() for page in pdf)
            except ImportError:
                st.error("PDF reading requires PyMuPDF: pip install PyMuPDF")
                return
        else:
            doc_text = uploaded.read().decode("utf-8", errors="replace")

        st.success(f"Document loaded: {len(doc_text)} characters")
        st.session_state["doc_text"] = doc_text

    if st.session_state.get("doc_text"):
        question = st.text_input("Ask a question about the document:")
        audio_val = st.audio_input("Or ask with your voice")

        if audio_val:
            with st.spinner("Transcribing..."):
                question = transcribe_audio(audio_val.read(), lang_key)
                st.write(f"Heard: {question}")

        if st.button("Ask", type="primary") and question:
            if not db.can_send(st.session_state.email):
                show_upgrade()
                return
            with st.spinner("Reading document..."):
                result = brain.ask_document(st.session_state["doc_text"], question, lang_display)
            st.write(result)
            if read_aloud:
                speak_reply(result, lang_key, gender, speed)
            db.increment_prompt(st.session_state.email)


# ══════════════════════════════════════════════════════════
# MODE: IMAGE
# ══════════════════════════════════════════════════════════
def mode_image(lang_key, lang_display, gender, read_aloud, speed):
    st.markdown("### 🖼️ Image Input")
    uploaded = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png", "gif", "webp"])

    if uploaded:
        st.image(uploaded, width=400)
        img_bytes = uploaded.getvalue()

        # Detect actual image type from file extension
        ext = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else "jpeg"
        media_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                     "gif": "image/gif", "webp": "image/webp"}
        media = media_map.get(ext, "image/jpeg")

        question = st.text_input("Ask about this image (or leave blank for description):")
        audio_val = st.audio_input("Or ask with your voice")

        if audio_val:
            with st.spinner("Transcribing..."):
                question = transcribe_audio(audio_val.read(), lang_key)
                st.write(f"Heard: {question}")

        if st.button("Analyse image", type="primary"):
            if not db.can_send(st.session_state.email):
                show_upgrade()
                return
            with st.spinner("Looking at image..."):
                result = brain.describe_image(img_bytes, question or "Describe this image.", lang_display, media_type=media)
            st.write(result)
            if read_aloud:
                speak_reply(result, lang_key, gender, speed)
            db.increment_prompt(st.session_state.email)


# ══════════════════════════════════════════════════════════
# MODE: CODE
# ══════════════════════════════════════════════════════════
def mode_code(lang_key, lang_display, gender, read_aloud, speed):
    st.markdown("### 💻 Code Helper")
    request = st.text_area("Describe what code you need:", placeholder="e.g. Write a Python function that...")

    if st.button("Generate Code", type="primary") and request:
        if not db.can_send(st.session_state.email):
            show_upgrade()
            return
        with st.spinner("Writing code..."):
            result = brain.generate_code(request, lang_display)
        st.markdown(result)
        if read_aloud:
            speak_reply(result, lang_key, gender, speed)
        db.increment_prompt(st.session_state.email)


# ══════════════════════════════════════════════════════════
# MODE: SUMMARISE
# ══════════════════════════════════════════════════════════
def mode_summarise(lang_key, lang_display, gender, read_aloud, speed):
    st.markdown("### 📝 Summariser")
    text = st.text_area("Paste text to summarise:", height=200)

    if st.button("Summarise", type="primary") and text:
        if not db.can_send(st.session_state.email):
            show_upgrade()
            return
        with st.spinner("Summarising..."):
            result = brain.summarise(text, lang_display)
        st.success(result)
        if read_aloud:
            speak_reply(result, lang_key, gender, speed)
        db.increment_prompt(st.session_state.email)


# ══════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ══════════════════════════════════════════════════════════
def mode_admin():
    if not db.is_admin(st.session_state.email):
        st.error("Access denied.")
        return

    st.markdown("### 📊 Admin Dashboard")
    stats = db.admin_stats()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Users", stats["total_users"])
    col2.metric("Pro Users", stats["pro_users"])
    col3.metric("Total Messages", stats["total_messages"])
    col4.metric("👍 / 👎", f"{stats['positive_reactions']} / {stats['negative_reactions']}")

    st.markdown("#### Languages used")
    st.write(", ".join(stats["languages_used"]) if stats["languages_used"] else "None yet")

    st.markdown("#### Recent signups")
    for u in stats["recent_signups"]:
        st.caption(f"{u['email']} — {u['created_at'][:10]}")

    st.divider()
    admin_email = st.text_input("Make someone admin (email):")
    if st.button("Grant admin") and admin_email:
        db.make_admin(admin_email)
        st.success(f"{admin_email} is now admin.")


# ══════════════════════════════════════════════════════════
# MODE: VOICE CLONING
# ══════════════════════════════════════════════════════════
def _mode_voice_clone(lang_key, lang_display, gender, read_aloud, speed):
    st.markdown("### 🎤 Voice Cloning")
    st.markdown(
        "Record your voice (at least 30 seconds) and the AI will learn to speak like you. "
        "Your cloned voice is private — only you can use it."
    )

    elevenlabs_key = os.environ.get("CMT_ELEVENLABS_KEY")
    if not elevenlabs_key:
        st.warning("Voice cloning requires an ElevenLabs API key.")
        st.markdown("Get a free key at [elevenlabs.io](https://elevenlabs.io/)")
        st.markdown("Then set it: `setx CMT_ELEVENLABS_KEY \"your-key\"`")
        return

    email = st.session_state.email
    plan = db.get_plan(email)
    if plan == "free":
        st.warning("Voice cloning is a Pro feature. Upgrade to use it.")
        show_upgrade()
        return

    voice_name = st.text_input("Name for your voice (e.g. 'Mzwandile')")
    audio_val = st.audio_input("Record at least 30 seconds of you speaking clearly")

    if st.button("Clone My Voice", type="primary") and audio_val and voice_name:
        with st.spinner("Cloning your voice... (this takes about 30 seconds)"):
            try:
                audio_bytes = audio_val.read()
                vid = voice_cloning.clone_voice(voice_name, audio_bytes)
                db.save_cloned_voice(email, vid, voice_name)
                st.success(f"Voice '{voice_name}' cloned successfully!")
            except Exception as e:
                st.error(f"Cloning failed: {e}")

    cloned = db.get_cloned_voices(email)
    if cloned:
        st.divider()
        st.markdown("#### Your cloned voices")
        for v in cloned:
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.write(f"🎙️ {v['voice_name']}")
            with col2:
                test_text = st.text_input("Test text", value="Sawubona!", key=f"test_{v['voice_id']}")
            with col3:
                if st.button("🔊", key=f"play_{v['voice_id']}"):
                    try:
                        ab = voice_cloning.speak_with_clone(test_text, v["voice_id"])
                        st.audio(ab, format="audio/mp3")
                    except Exception as e:
                        st.error(str(e))


# ══════════════════════════════════════════════════════════
# MODE: CHAT HISTORY (for Basic/Pro users)
# ══════════════════════════════════════════════════════════
def _mode_chat_history(lang_key, lang_display, gender, read_aloud, speed):
    email = st.session_state.email
    plan = db.get_plan(email)

    st.markdown("### 💬 Chat History")

    if plan == "free":
        st.warning("Chat history is available on Basic and Pro plans.")
        show_upgrade()
        return

    all_messages = db.get_history(email)

    if not all_messages:
        st.info("No chat history yet. Start chatting in Chat mode!")
        return

    sessions = {}
    for msg in all_messages:
        sid = msg.get("session_id") or "unknown"
        if sid not in sessions:
            sessions[sid] = []
        sessions[sid].append(msg)

    if st.button("➕ Start New Chat", type="primary", use_container_width=True):
        import secrets as _s
        st.session_state.session_id = _s.token_urlsafe(8)
        st.session_state.history = []
        st.session_state.mode = "chat"
        st.rerun()

    st.divider()

    for sid, messages in reversed(list(sessions.items())):
        first_msg = next((m for m in messages if m["role"] == "user"), None)
        preview = (first_msg["content"][:60] + "...") if first_msg else "Chat"
        date = messages[0].get("created_at", "")[:16] if messages else ""
        lang = messages[0].get("language", "") or ""
        lang_label = voices.LANGUAGES.get(lang, {}).get("display", "") if lang else ""

        with st.expander(f"📅 {date}  —  {preview}  ({lang_label})"):
            for msg in messages:
                role_icon = "🗣️" if msg["role"] == "user" else "🤖"
                st.markdown(f"**{role_icon} {msg['role'].title()}:** {msg['content']}")

                if msg["role"] == "assistant" and read_aloud:
                    if st.button(f"🔊 Replay", key=f"replay_{msg.get('id', sid)}_{messages.index(msg)}"):
                        speak_reply(msg["content"], lang_key, gender, speed)

            if st.button("💬 Continue this chat", key=f"continue_{sid}"):
                st.session_state.session_id = sid
                st.session_state.history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in messages
                ]
                st.session_state.mode = "chat"
                st.rerun()


# ══════════════════════════════════════════════════════════
# MAIN ROUTER
# ══════════════════════════════════════════════════════════

# Check for admin URL: ?page=admin
page = st.query_params.get("page", None)

if page == "admin":
    if not st.session_state.logged_in:
        show_auth()
    else:
        show_admin_page()
elif not st.session_state.logged_in:
    show_auth()
elif st.session_state.get("show_plans") or st.session_state.get("just_registered"):
    show_plans_page()
else:
    if not show_onboarding():
        st.stop()

    lang_key, gender, read_aloud, speed = show_sidebar()
    lang_display = voices.LANGUAGES[lang_key]["display"]

    mode = st.session_state.mode
    if mode == "chat":
        mode_chat(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "quiz":
        mode_quiz(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "exam":
        mode_exam(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "essay":
        mode_essay(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "flashcards":
        mode_flashcards(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "translate":
        mode_translate(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "document":
        mode_document(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "image":
        mode_image(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "code":
        mode_code(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "summarise":
        mode_summarise(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "voice_clone":
        _mode_voice_clone(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "history":
        _mode_chat_history(lang_key, lang_display, gender, read_aloud, speed)
    elif mode == "admin":
        mode_admin()
