"""
brain.py — AI engine for CMT SA Voice Assistant V2.
"""

import os
import base64

PERSONALITIES = {
    "assistant": {"label": "🤖 General Assistant", "prompt": "You are a friendly, helpful South African AI assistant."},
    "tutor": {"label": "👩‍🏫 Tutor", "prompt": "You are a patient, encouraging South African tutor. Explain concepts step by step. Use real-world SA examples."},
    "therapist": {"label": "🧠 Wellness Advisor", "prompt": "You are a compassionate wellness advisor. Listen empathetically. Never diagnose. Be warm and caring."},
    "career": {"label": "💼 Career Advisor", "prompt": "You are a knowledgeable South African career advisor. Help with CVs, interview prep, career paths, bursaries and SETA learnerships."},
    "coder": {"label": "💻 Coding Helper", "prompt": "You are a coding mentor. Write clean, commented code. Explain what each part does in simple language."},
    "translator": {"label": "🌍 Translator", "prompt": "You are a professional translator between South African languages. Translate accurately, preserving meaning and tone."},
    "summariser": {"label": "📝 Summariser", "prompt": "You summarise text clearly and concisely. Keep the key points. Deliver in spoken style."},
}

SUBJECTS = {
    "maths": "Mathematics (algebra, geometry, calculus, statistics, trigonometry)",
    "science": "Physical Science (physics, chemistry, experiments, formulas)",
    "life_science": "Life Sciences (biology, human body, ecology, genetics)",
    "history": "History (South African history, world history, apartheid, democracy)",
    "business": "Business Studies (entrepreneurship, management, marketing, finance)",
    "geography": "Geography (maps, climate, population, resources, SA provinces)",
    "english": "English (grammar, comprehension, literature, writing)",
    "accounting": "Accounting (financial statements, journals, ledgers, ratios)",
    "economics": "Economics (supply & demand, inflation, GDP, fiscal policy)",
    "computer": "Computer Applications Technology / IT",
}


def _get_client(claude_key=None):
    import anthropic
    key = claude_key or os.environ.get("CMT_CLAUDE_KEY")
    if not key:
        raise EnvironmentError("No Claude API key. Set CMT_CLAUDE_KEY.")
    return anthropic.Anthropic(api_key=key)


def _call(client, system, messages, model="claude-sonnet-4-5", max_tokens=800):
    resp = client.messages.create(model=model, max_tokens=max_tokens, system=system, messages=messages)
    return "".join(b.text for b in resp.content if b.type == "text")


def _lang_rule(lang_display):
    return (
        f"CRITICAL LANGUAGE RULE: You MUST reply ENTIRELY in {lang_display}. "
        f"Every single word of your reply must be in {lang_display} — no exceptions, "
        f"no mixing with other languages. If the user writes in a different language, "
        f"still reply in {lang_display}. This is the user's chosen language."
    )


def think(user_text, lang_display, personality="assistant", claude_key=None, history=None, subject=None):
    client = _get_client(claude_key)
    p = PERSONALITIES.get(personality, PERSONALITIES["assistant"])
    system = f"{p['prompt']} {_lang_rule(lang_display)} Keep replies conversational — no markdown, no bullets, no asterisks (this will be read aloud). Be concise but thorough."
    if subject:
        system += f" Focus on {SUBJECTS.get(subject, subject)}."
    msgs = list(history) if history else []
    msgs.append({"role": "user", "content": user_text})
    return _call(client, system, msgs)


def generate_quiz(subject, lang_display, grade="12", num_questions=5, claude_key=None):
    client = _get_client(claude_key)
    subj_desc = SUBJECTS.get(subject, subject)
    system = (
        f"You are a South African exam setter. Generate exactly {num_questions} "
        f"multiple-choice questions for Grade {grade} {subj_desc}. "
        f"{_lang_rule(lang_display)} Format each question as:\n"
        f"Q1: [question]\nA) [option]\nB) [option]\nC) [option]\nD) [option]\nAnswer: [letter]\n\n"
        f"Make questions progressively harder. Include SA-relevant content."
    )
    return _call(client, system, [{"role": "user", "content": f"Generate a {subj_desc} quiz."}], max_tokens=1500)


def mark_answer(question, user_answer, correct_answer, lang_display, claude_key=None):
    client = _get_client(claude_key)
    system = f"You are a friendly tutor marking an answer. {_lang_rule(lang_display)} If correct, praise. If wrong, explain why the correct answer is right. Keep it concise."
    msg = f"Question: {question}\nStudent answered: {user_answer}\nCorrect answer: {correct_answer}"
    return _call(client, system, [{"role": "user", "content": msg}])


def exam_prep(subject, topic, lang_display, grade="12", level="matric", claude_key=None):
    client = _get_client(claude_key)
    subj_desc = SUBJECTS.get(subject, subject)
    level_label = {"matric": "Grade 12 NSC", "university": "University/Honours"}.get(level, level)
    system = f"You are a South African {level_label} exam preparation expert for {subj_desc}. {_lang_rule(lang_display)} Generate practice questions with model answers. Include mark allocations. Follow CAPS curriculum style."
    return _call(client, system, [{"role": "user", "content": f"Prepare exam questions on: {topic}"}], max_tokens=1500)


def essay_help(essay_text, instruction, lang_display, claude_key=None):
    client = _get_client(claude_key)
    system = f"You are an essay writing tutor. {_lang_rule(lang_display)} Help improve structure, argument flow, grammar, and style. Be specific about what to fix and why."
    msg = f"Instruction: {instruction}\n\nEssay:\n{essay_text}"
    return _call(client, system, [{"role": "user", "content": msg}], max_tokens=1500)


def generate_flashcards(topic, lang_display, num=10, claude_key=None):
    client = _get_client(claude_key)
    system = f"Generate exactly {num} study flashcards on the topic. {_lang_rule(lang_display)} Format each as:\nFRONT: [question or term]\nBACK: [answer or definition]\n\nKeep each card concise."
    return _call(client, system, [{"role": "user", "content": f"Topic: {topic}"}], max_tokens=1500)


def translate(text, from_lang, to_lang, claude_key=None):
    client = _get_client(claude_key)
    system = f"You are a professional South African language translator. Translate from {from_lang} to {to_lang}. Preserve meaning, tone, and cultural context. Show only the translation."
    return _call(client, system, [{"role": "user", "content": text}])


def summarise(text, lang_display, claude_key=None):
    client = _get_client(claude_key)
    system = f"Summarise this text concisely. {_lang_rule(lang_display)} Keep it spoken-style (no bullets, no markdown) since it will be read aloud."
    return _call(client, system, [{"role": "user", "content": text}])


def ask_document(doc_text, question, lang_display, claude_key=None):
    client = _get_client(claude_key)
    system = f"You are answering questions about a document. {_lang_rule(lang_display)} Base your answer only on the document content. If the answer isn't in the document, say so."
    msg = f"Document:\n{doc_text[:15000]}\n\nQuestion: {question}"
    return _call(client, system, [{"role": "user", "content": msg}], max_tokens=1000)


def describe_image(image_bytes, question, lang_display, claude_key=None, media_type="image/jpeg"):
    client = _get_client(claude_key)
    system = f"Describe or answer questions about this image. {_lang_rule(lang_display)} Be detailed but conversational."
    b64 = base64.standard_b64encode(image_bytes).decode()
    msgs = [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
        {"type": "text", "text": question or "Describe this image."},
    ]}]
    return _call(client, system, msgs)


def generate_code(request, lang_display, claude_key=None):
    client = _get_client(claude_key)
    system = f"You are a coding assistant. Write clean, well-commented code. Explain what each part does in {lang_display}."
    return _call(client, system, [{"role": "user", "content": request}], max_tokens=1500)
