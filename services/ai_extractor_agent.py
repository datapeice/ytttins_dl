import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional

import requests
import yt_dlp

from config import DATA_DIR, AI_AUTOFIX_ENABLED, GROQ_API_KEY, GROQ_MODEL, BOT_TOKEN, ADMIN_USER_ID


AUTO_PLUGIN_ROOT = DATA_DIR / "auto_plugin_dirs"
PLUGIN_PACKAGE_DIR = AUTO_PLUGIN_ROOT / "yt_dlp_plugins"
PLUGIN_EXTRACTOR_DIR = PLUGIN_PACKAGE_DIR / "extractor"


def get_plugin_dirs() -> list[str]:
    _ensure_plugin_layout()
    return [str(AUTO_PLUGIN_ROOT)]


def _ensure_plugin_layout() -> None:
    PLUGIN_EXTRACTOR_DIR.mkdir(parents=True, exist_ok=True)
    for init_file in (PLUGIN_PACKAGE_DIR / "__init__.py", PLUGIN_EXTRACTOR_DIR / "__init__.py"):
        if not init_file.exists():
            init_file.write_text("", encoding="utf-8")


def should_attempt_ai_autofix(url: str, error_message: str) -> bool:
    if not AI_AUTOFIX_ENABLED or not GROQ_API_KEY:
        return False
    if not url.startswith(("http://", "https://")):
        return False
    err = (error_message or "").lower()
    ignored = (
        "private video",
        "login required",
        "sign in to confirm",
        "cookies",
        "file is too large",
        "request expired",
        "not enough rights",
    )
    if any(token in err for token in ignored):
        return False

    extraction_like = (
        "unable to extract",
        "cannot parse",
        "failed to parse",
        "no video formats",
        "unsupported url",
        "unable to download webpage",
        "extractorerror",
    )
    return any(token in err for token in extraction_like)


def _fetch_html_snippet(url: str) -> str:
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ytttins-ai-autofix/1.0)"},
        )
        if resp.ok:
            return (resp.text or "")[:5000]
    except Exception as e:
        logging.warning(f"[AI-AUTOFIX] Could not fetch HTML snippet: {e}")
    return ""


def _read_existing_extractor(filename: str) -> Optional[str]:
    path = PLUGIN_EXTRACTOR_DIR / filename
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _clean_json_response(text: str) -> str:
    payload = (text or "").strip()
    if payload.startswith("```"):
        payload = re.sub(r"^```(?:json)?\s*", "", payload, flags=re.IGNORECASE)
        payload = re.sub(r"\s*```$", "", payload)
    return payload.strip()


def _validate_agent_payload(payload: Dict) -> Optional[str]:
    action = payload.get("action")
    if action not in {"patch", "new_module", "cannot_fix"}:
        return "invalid action"
    if action == "cannot_fix":
        return None

    filename = payload.get("filename") or ""
    code = payload.get("code") or ""
    if not re.fullmatch(r"[A-Za-z0-9_]+\.py", filename):
        return "invalid filename"
    if not isinstance(code, str) or len(code.strip()) < 200:
        return "empty code"

    required = ("InfoExtractor", "_VALID_URL", "def _real_extract", "_TESTS")
    if not all(token in code for token in required):
        return "missing extractor primitives"

    forbidden = ("subprocess", "os.system", "eval(", "exec(", "socket.")
    if any(token in code for token in forbidden):
        return "unsafe code pattern detected"

    try:
        compile(code, filename, "exec")
    except Exception as e:
        return f"extractor code does not compile: {e}"
    return None


def _notify_admin(text: str) -> None:
    if not BOT_TOKEN or not ADMIN_USER_ID:
        return
    chat_id = str(ADMIN_USER_ID)
    if not re.fullmatch(r"-?\d+", chat_id):
        logging.warning("[AI-AUTOFIX] ADMIN_USERNAME is not numeric chat id; admin message skipped")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": int(chat_id), "text": text},
            timeout=10,
        )
    except Exception as e:
        logging.warning(f"[AI-AUTOFIX] Failed to notify admin: {e}")


def run_ai_extractor_autofix(url: str, error_message: str) -> Dict:
    if not AI_AUTOFIX_ENABLED:
        return {"attempted": False, "reason": "disabled"}
    if not GROQ_API_KEY:
        return {"attempted": False, "reason": "missing_groq_key"}

    _ensure_plugin_layout()
    html_snippet = _fetch_html_snippet(url)
    existing_filename = f"{re.sub(r'[^a-z0-9]+', '_', url.split('/')[2].lower()).strip('_')}_ie.py"
    existing_code = _read_existing_extractor(existing_filename)
    system_prompt = (
        "You are an expert Python developer specializing in yt-dlp extractor architecture. "
        "Return strict JSON only. "
        "If not fixable, use action=cannot_fix."
    )
    user_prompt = json.dumps({
        "url": url,
        "error": error_message,
        "existing_extractor": existing_code,
        "yt_dlp_version": yt_dlp.version.__version__,
        "html_snippet": html_snippet,
    }, ensure_ascii=False)

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=80,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        payload = json.loads(_clean_json_response(content))
    except Exception as e:
        _notify_admin(f"❌ AI extractor autofix failed to call Groq for {url}\nError: {e}")
        return {"attempted": True, "success": False, "reason": f"groq_call_failed: {e}"}

    validation_error = _validate_agent_payload(payload)
    if validation_error:
        _notify_admin(f"❌ AI extractor autofix rejected output for {url}\nReason: {validation_error}")
        return {"attempted": True, "success": False, "reason": validation_error, "payload": payload}

    if payload.get("action") == "cannot_fix":
        note = payload.get("notes") or "cannot_fix"
        _notify_admin(f"⚠️ AI extractor autofix cannot fix {url}\n{note}")
        return {"attempted": True, "success": False, "reason": note, "payload": payload}

    filename = payload["filename"]
    code = payload["code"]
    module_path = PLUGIN_EXTRACTOR_DIR / filename
    try:
        module_path.write_text(code, encoding="utf-8")
    except Exception as e:
        _notify_admin(f"❌ AI extractor autofix failed writing module {filename}\nError: {e}")
        return {"attempted": True, "success": False, "reason": f"write_failed: {e}", "payload": payload}

    _notify_admin(f"✅ AI extractor autofix applied module {filename} for {url}")
    return {
        "attempted": True,
        "success": True,
        "filename": filename,
        "module_path": str(module_path),
        "payload": payload,
    }
