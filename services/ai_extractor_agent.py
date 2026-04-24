import json
import os
import time
import logging
import re
import ast
import socket
import traceback
import base64
from pathlib import Path
from typing import Dict, Optional, List
from urllib.parse import urlparse
from datetime import datetime, timezone

import requests
import yt_dlp
try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

from config import (
    DATA_DIR,
    AI_AUTOFIX_ENABLED,
    GROQ_API_KEY,
    GROQ_MODEL,
    BOT_TOKEN,
    ADMIN_USER_ID,
    AI_AUTOFIX_REQUIRE_NETWORK,
    AI_AUTOFIX_CREATE_PR,
    GITHUB_TOKEN,
    GITHUB_REPO,
    GITHUB_PR_BASE,
)


AUTO_PLUGIN_ROOT = DATA_DIR / "auto_plugin_dirs"
PLUGIN_PACKAGE_DIR = AUTO_PLUGIN_ROOT / "yt_dlp_plugins"
PLUGIN_EXTRACTOR_DIR = PLUGIN_PACKAGE_DIR / "extractor"
MIN_EXTRACTOR_CODE_LENGTH = 200
GROQ_API_TIMEOUT_SECONDS = 80
TARGET_CONNECT_TIMEOUT_SECONDS = 10
GROQ_HEALTHCHECK_URL = "https://api.groq.com/openai/v1/models"
PERSISTED_EXTRACTORS_DIR = "services/generated_extractors"
GITHUB_API_BASE = "https://api.github.com"



def get_plugin_dirs() -> List[str]:
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


def _fetch_html_snippet(url: str, proxy: Optional[str] = None) -> str:
    """Fetches HTML using a fallback strategy: simple -> browser -> proxy."""
    # Attempt 1: Simple (like terminal curl)
    try:
        headers = {"User-Agent": "curl/7.81.0", "Accept": "*/*"}
        resp = requests.get(url, headers=headers, timeout=10, proxies={"http": None, "https": None})
        if resp.status_code == 200:
            logging.info("[AI-EXTRACTOR] HTML fetched via simple curl-like request.")
            return resp.text[:5000] + "\n...[TRUNCATED]...\n" + resp.text[-5000:] if len(resp.text) > 10000 else resp.text
    except Exception as e:
        logging.debug(f"[AI-EXTRACTOR] Simple fetch failed: {e}")

    # Attempt 2: curl_cffi (Browser impersonation)
    try:
        from curl_cffi import requests as curl_requests
        resp = curl_requests.get(url, impersonate="chrome110", timeout=15, verify=False)
        if resp.status_code == 200:
            logging.info("[AI-EXTRACTOR] HTML fetched via curl_cffi (chrome110).")
            return resp.text[:5000] + "\n...[TRUNCATED]...\n" + resp.text[-5000:] if len(resp.text) > 10000 else resp.text
    except Exception as e:
        logging.debug(f"[AI-EXTRACTOR] Browser fetch failed: {e}")

    # Attempt 3: Proxy (last resort)
    if proxy:
        try:
            from curl_cffi import requests as curl_requests
            proxies = {"http": proxy, "https": proxy}
            resp = curl_requests.get(url, impersonate="chrome110", timeout=20, verify=False, proxies=proxies)
            if resp.status_code == 200:
                logging.info("[AI-EXTRACTOR] HTML fetched via Proxy + curl_cffi.")
                return resp.text[:5000] + "\n...[TRUNCATED]...\n" + resp.text[-5000:] if len(resp.text) > 10000 else resp.text
        except Exception as e:
            logging.warning(f"[AI-EXTRACTOR] All HTML fetch attempts failed, including proxy: {e}")

    return "Error: Could not fetch HTML snippet after multiple attempts (including 403 Forbidden)."


def _is_network_resolution_error(message: str) -> bool:
    lower = (message or "").lower()
    return any(token in lower for token in (
        "failed to resolve",
        "name or service not known",
        "temporary failure in name resolution",
        "nodename nor servname provided",
        "no address associated with hostname",
        "dns",
    ))


def _check_network_readiness(url: str) -> Optional[str]:
    parsed = urlparse(url)
    target_host = parsed.hostname
    if not target_host:
        return "target_url_has_no_host"

    try:
        socket.getaddrinfo(target_host, 443)
    except Exception as e:
        return f"cannot_resolve_target_host:{target_host}:{e}"

    try:
        socket.getaddrinfo("api.groq.com", 443)
    except Exception as e:
        return f"cannot_resolve_groq_host:{e}"

    try:
        response = requests.get(
            GROQ_HEALTHCHECK_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            timeout=TARGET_CONNECT_TIMEOUT_SECONDS,
            verify=True,
            proxies={"http": None, "https": None},
        )
        if response.status_code in (401, 403):
            return "groq_auth_failed"
    except Exception as e:
        return f"cannot_reach_groq_api:{e}"

    try:
        requests.get(
            url,
            timeout=TARGET_CONNECT_TIMEOUT_SECONDS,
            verify=True,
            stream=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; yttins-ai-autofix/1.0)"},
        )
    except Exception as e:
        if _is_network_resolution_error(str(e)):
            return f"cannot_reach_target_url:{e}"
    return None


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
    if action not in {"patch", "new_module", "cannot_fix", "web_search"}:
        return "invalid action"
    if action in {"cannot_fix", "web_search"}:
        return None

    filename = payload.get("filename") or ""
    code = payload.get("code") or ""
    
    # RECOVERY LOGIC: if code is empty but some other key contains "InfoExtractor", 
    # it means the AI messed up the JSON structure.
    if not code or len(str(code).strip()) < 40:
        for k, v in payload.items():
            if isinstance(k, str) and "InfoExtractor" in k:
                payload["code"] = k # Code was in the key!
                code = k
                break
            if isinstance(v, str) and "InfoExtractor" in v and k != "code":
                payload["code"] = v
                code = v
                break

    if not re.fullmatch(r"[A-Za-z0-9_]+\.py", filename):
        return "invalid filename"
    if Path(filename).name != filename:
        return "invalid filename path"
    if not isinstance(code, str) or len(code.strip()) < MIN_EXTRACTOR_CODE_LENGTH:
        return "empty code"

    required = ("InfoExtractor", "_VALID_URL", "def _real_extract")
    if not all(token in code for token in required):
        return "missing extractor primitives"

    try:
        tree = ast.parse(code, filename=filename)
    except Exception as e:
        return f"extractor code does not compile: {e}"

    dangerous_modules = {"os", "subprocess", "importlib"}
    dangerous_calls = {"eval", "exec", "__import__"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in dangerous_modules:
                    return f"unsafe import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in dangerous_modules:
                return f"unsafe from-import: {node.module}"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in dangerous_calls:
                return f"unsafe call: {node.func.id}"
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "os" and node.func.attr == "system":
                        return "unsafe call: os.system"
                    if node.func.value.id == "subprocess":
                        return "unsafe call: subprocess"
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    mode = str(node.args[1].value).lower()
                    if any(flag in mode for flag in ("w", "a", "x", "+")):
                        return "unsafe file-write open()"
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = str(kw.value.value).lower()
                        if any(flag in mode for flag in ("w", "a", "x", "+")):
                            return "unsafe file-write open()"

    return None


def _notify_admin(text: str) -> None:
    if not BOT_TOKEN or not ADMIN_USER_ID or not text:
        return
    try:
        chat_id = int(ADMIN_USER_ID)
    except (TypeError, ValueError):
        return

    # Telegram message limit is 4096. Split with safety margin.
    limit = 4000
    parts = [text[i:i+limit] for i in range(0, len(text), limit)]
    
    for part in parts:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": part},
                timeout=10,
            )
        except Exception as e:
            logging.warning(f"[AI-AUTOFIX] Failed to notify admin: {e}")


def _extract_has_stream(info: Dict) -> bool:
    if not isinstance(info, dict):
        return False
    direct_url = info.get("url")
    formats = info.get("formats")
    if isinstance(direct_url, str) and direct_url.startswith(("http://", "https://")):
        return True
    if isinstance(formats, list):
        for fmt in formats:
            if isinstance(fmt, dict) and isinstance(fmt.get("url"), str):
                return True
    entries = info.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if _extract_has_stream(entry):
                return True
    return False


def _verify_generated_extractor(url: str, verify_opts_override: Optional[Dict] = None) -> Optional[str]:
    base_opts = {
        "skip_download": True,
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "plugin_dirs": get_plugin_dirs(),
    }
    if verify_opts_override:
        base_opts.update(verify_opts_override)
    base_opts["skip_download"] = True
    base_opts["extract_flat"] = False

    # Extract proxy for fallback, but try direct first
    proxy = base_opts.pop("proxy", "") or ""

    # --- Attempt 1: Direct (no proxy) ---
    direct_opts = {**base_opts, "proxy": ""}
    try:
        with yt_dlp.YoutubeDL(direct_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if _extract_has_stream(info):
            return None  # Success!
        return "verification_failed_no_stream_url (the generated extractor did not return any media links)"
    except Exception:
        direct_err = traceback.format_exc()
        logging.info(f"[AI-VERIFY] Direct verification failed, will try proxy fallback...")

    # --- Attempt 2: Via proxy (fallback) ---
    if proxy:
        logging.info(f"[AI-VERIFY] Retrying verification via proxy...")
        proxy_opts = {**base_opts, "proxy": proxy}
        try:
            with yt_dlp.YoutubeDL(proxy_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if _extract_has_stream(info):
                return None  # Success via proxy!
            return "verification_failed_no_stream_url (proxy attempt also returned no media links)"
        except Exception:
            proxy_err = traceback.format_exc()
            logging.warning(f"[AI-VERIFY] Proxy verification also failed:\n{proxy_err}")
            # Return the proxy error since it was the last attempt
            if _is_network_resolution_error(proxy_err):
                return f"verification_network_error: {proxy_err}"
            return f"verification_failed_runtime_error_traceback:\n{proxy_err}"

    # No proxy available, return direct error
    logging.warning(f"[AI-VERIFY] Verification failed (no proxy fallback):\n{direct_err}")
    if _is_network_resolution_error(direct_err):
        return f"verification_network_error: {direct_err}"
    return f"verification_failed_runtime_error_traceback:\n{direct_err}"


def _github_request(method: str, path: str, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.update({
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return requests.request(
        method=method,
        url=f"{GITHUB_API_BASE}{path}",
        headers=headers,
        timeout=20,
        **kwargs,
    )


def _create_persistence_pull_request(filename: str, code: str, source_url: str) -> Dict:
    if not AI_AUTOFIX_CREATE_PR:
        return {"created": False, "reason": "pr_disabled"}
    if not GITHUB_TOKEN or not GITHUB_REPO or "/" not in GITHUB_REPO:
        return {"created": False, "reason": "missing_github_config"}

    owner, repo = GITHUB_REPO.split("/", 1)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    base_branch = GITHUB_PR_BASE
    branch = f"ai-autofix/{filename.replace('.py', '')}-{timestamp}"

    try:
        ref_resp = _github_request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{base_branch}")
        ref_resp.raise_for_status()
        base_sha = ref_resp.json()["object"]["sha"]

        create_ref_resp = _github_request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        create_ref_resp.raise_for_status()

        persist_path = f"{PERSISTED_EXTRACTORS_DIR}/{filename}"
        put_resp = _github_request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{persist_path}",
            json={
                "message": f"feat(autofix): persist generated extractor {filename}",
                "content": base64.b64encode(code.encode("utf-8")).decode("ascii"),
                "branch": branch,
            },
        )
        put_resp.raise_for_status()

        pr_resp = _github_request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": f"Auto-fix extractor: {filename}",
                "head": branch,
                "base": base_branch,
                "body": (
                    f"Autogenerated extractor from AI autofix flow.\n\n"
                    f"- Source URL: {source_url}\n"
                    f"- Module: `{filename}`\n"
                    f"- Runtime verification: passed\n"
                ),
                "draft": True,
            },
        )
        pr_resp.raise_for_status()
        pr_data = pr_resp.json()
        return {
            "created": True,
            "url": pr_data.get("html_url"),
            "number": pr_data.get("number"),
            "branch": branch,
        }
    except Exception as e:
        return {"created": False, "reason": str(e)}


def _web_search(query: str) -> str:
    if not DDGS:
        return "Search tool not available (duckduckgo-search not installed)."
    try:
        # Using the latest DDGS API to avoid warnings
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=5)]
            return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        return f"Search failed: {e}"


def run_ai_extractor_autofix(url: str, error_message: str, verify_opts: Optional[Dict] = None) -> Dict:
    if not AI_AUTOFIX_ENABLED:
        return {"attempted": False, "reason": "disabled"}
    if not GROQ_API_KEY:
        return {"attempted": False, "reason": "missing_groq_key"}
    
    report_logs = []
    def log_report(msg: str, system_only_extra: Optional[str] = None):
        # Full content goes to system logs
        full_log = f"{msg}\n{system_only_extra}" if system_only_extra else msg
        logging.info(f"[AI-AUTOFIX] {full_log}")
        
        # Only the concise 'msg' goes to Telegram summary
        report_logs.append(msg)

    if AI_AUTOFIX_REQUIRE_NETWORK:
        network_issue = _check_network_readiness(url)
        if network_issue:
            log_report(f"❌ AI extractor autofix skipped for {url}\nReason: network readiness check failed ({network_issue}).")
            _notify_admin("\n".join(report_logs))
            return {"attempted": False, "success": False, "reason": f"network_not_ready:{network_issue}"}

    _ensure_plugin_layout()
    html_snippet = _fetch_html_snippet(url)
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    safe_domain = re.sub(r"[^a-z0-9_]+", "_", netloc).strip("_") or "site"
    candidate_filename = f"{safe_domain}_ie.py"
    existing_code = _read_existing_extractor(candidate_filename)
    
    log_report(f"🤖 Starting autofix session for: {url}")
    
    system_prompt = (
        "You are an expert autonomous AI agent specializing in yt-dlp extractor architecture.\n"
        "Your task is to write a yt-dlp InfoExtractor plugin.\n\n"
        "OPERATING MODE:\n"
        "1. FIRST PRIORITY: Analyze the provided HTML snippet (fetched via server-side curl) and write the fix immediately.\n"
        "2. SECOND PRIORITY: If your first fix fails or you are stuck, use 'web_search'.\n\n"
        "RULES FOR THE EXTRACTOR CODE:\n"
        "- NEVER import 'requests' or 'urllib' inside the extractor module.\n"
        "- ALWAYS use native yt-dlp methods like 'self._download_webpage', 'self._download_json', or 'self._request_webpage'.\n"
        "- This ensures that proxies and TLS impersonation settings are correctly inherited from the main process.\n\n"
        "JSON STRUCTURE EXAMPLE:\n"
        "{\n"
        "  \"action\": \"new_module\",\n"
        "  \"filename\": \"test_ie.py\",\n"
        "  \"code\": \"import re\\nfrom .common import InfoExtractor\\n...\",\n"
        "  \"notes\": \"explanation\"\n"
        "}\n\n"
        "ALWAYS return VALID JSON. Put the python code inside the \"code\" string value."
    )
    user_prompt = json.dumps({
        "url": url,
        "error": error_message,
        "existing_extractor": existing_code,
        "yt_dlp_version": yt_dlp.version.__version__,
        "html_snippet": html_snippet,
    }, ensure_ascii=False)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        for attempt in range(4):  # Steps allowed (e.g. search + search + fix)
            if attempt > 0:
                time.sleep(5)  # Backoff to avoid Groq 429
            try:
                payload_json = {
                    "model": GROQ_MODEL,
                    "temperature": 0.1,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "stream": False,
                }

                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload_json,
                    timeout=GROQ_API_TIMEOUT_SECONDS,
                    proxies={"http": None, "https": None},
                )
                response.raise_for_status()
                body = response.json()
                
                content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise ValueError("Empty response from Groq")
                
                # Log FULL response to system logs, but only a summary to TG
                log_report(f"Agent step {attempt+1} received. (Size: {len(content)} chars)", system_only_extra=f"--- FULL RESPONSE ---\n{content}")
                payload = json.loads(_clean_json_response(content), strict=False)
                
                # Manual tool handling
                if payload.get("action") == "web_search":
                    query = payload.get("query")
                    log_report(f"🔍 AI requesting search: {query}")
                    search_res = _web_search(query)
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"SEARCH RESULTS:\n{search_res}\n\nPlease proceed to write the extractor or perform another search if needed."})
                    continue

                validation_error = _validate_agent_payload(payload)
                if validation_error:
                    log_report(f"⚠️ Attempt {attempt+1} validation failed: {validation_error}")
                    if attempt == 0:
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": f"Validation failed: {validation_error}. Please correct the JSON structure or logic."})
                        continue
                    return {"attempted": True, "success": False, "reason": validation_error, "payload": payload}

                if payload.get("action") == "cannot_fix":
                    note = payload.get("notes") or "cannot_fix"
                    log_report(f"⚠️ AI cannot fix this URL: {note}")
                    return {"attempted": True, "success": False, "reason": note, "payload": payload}

                filename = payload["filename"]
                code = payload["code"]
                module_path = PLUGIN_EXTRACTOR_DIR / filename
                
                # Telegram: only AI explanation (notes). System Logs: FULL CODE.
                notes = payload.get("notes", "No notes provided")
                log_report(f"🛠️ Agent suggestion for {filename}:\nExplanation: {notes}", system_only_extra=f"--- FULL GENERATED CODE ---\n{code}")
                
                module_path.write_text(code, encoding="utf-8")

                verify_error = _verify_generated_extractor(url, verify_opts)
                if verify_error:
                    log_report(f"⚠️ Step {attempt+1} verification failed: {verify_error}")
                    if attempt == 0:
                        if module_path.exists():
                            module_path.unlink()
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": f"Verification failed with current code: {verify_error}. Please fix the issue and try again."})
                        continue
                    try:
                        if module_path.exists():
                            module_path.unlink()
                    except Exception:
                        pass
                    return {"attempted": True, "success": False, "reason": verify_error, "payload": payload}

                # Success!
                pr_result = _create_persistence_pull_request(filename, code, url)
                status_pr = f"PR: {pr_result.get('url')}" if pr_result.get('created') else f"PR status: not created ({pr_result.get('reason')})"
                log_report(f"✅ AI autofix SUCCESS for {url}\nModule: {filename}\n{status_pr}")
                return {
                    "attempted": True,
                    "success": True,
                    "filename": filename,
                    "module_path": str(module_path),
                    "pr": pr_result,
                    "payload": payload,
                }

            except Exception as e:
                log_report(f"❌ Critical agent error at step {attempt+1}: {e}")
                messages.append({"role": "user", "content": f"An error occurred: {e}. Please correct and try again."})
                if "429" in str(e):
                    time.sleep(5)
                if attempt >= 3:
                    return {"attempted": True, "success": False, "reason": f"agent_error: {e}"}

        return {"attempted": True, "success": False, "reason": "max_retries_exceeded_or_final_failure"}
    
    finally:
        # Guarantee admin notification even if the loop or code crashes
        if report_logs:
            try:
                _notify_admin("\n".join(report_logs))
            except Exception as nae:
                logging.error(f"[AI-AUTOFIX] Failed to notify admin: {nae}")



