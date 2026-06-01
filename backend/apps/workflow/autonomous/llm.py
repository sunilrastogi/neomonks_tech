"""
Direct Ollama API wrapper
=========================
A global threading.Semaphore(1) ensures only ONE model call runs at a time.

Return convention
-----------------
call() returns a (text, error) tuple:
  - text  : model response string (may be "")
  - error : None on success, or a human-readable string on failure
"""
from __future__ import annotations

import logging
import threading
import time

import requests as req_lib

from django.conf import settings

logger = logging.getLogger(__name__)

_llm_semaphore = threading.Semaphore(1)

LLM_TIMEOUT: int = int(getattr(settings, "LLM_TIMEOUT_SECONDS", 300))


def _model_name() -> str:
    m = getattr(settings, "DEFAULT_AGENT_MODEL", "ollama/qwen2.5-coder:7b")
    return m.replace("ollama/", "")


def _host() -> str:
    return getattr(settings, "OLLAMA_HOST", "http://localhost:11434")


def is_ollama_running() -> bool:
    try:
        req_lib.get(f"{_host()}/api/tags", timeout=3)
        return True
    except Exception:
        return False


def _do_generate(prompt: str, system: str, num_predict: int) -> str:
    """Raw POST to Ollama — no semaphore, no error handling."""
    num_gpu = int(getattr(settings, "OLLAMA_NUM_GPU", 0))
    payload = {
        "model": _model_name(),
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0.1,
            "num_predict": num_predict,
            "num_gpu": num_gpu,
            "num_ctx": 4096,   # keep context window fixed to limit RAM usage
        },
    }
    if system:
        payload["system"] = system
    resp = req_lib.post(
        f"{_host()}/api/generate",
        json=payload,
        timeout=(600, LLM_TIMEOUT),
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def call(prompt: str, system: str = "", emit_log=None) -> tuple[str, str | None]:
    """
    Call Ollama and return (response_text, error).

    On Ollama 500 (model OOM mid-generation), retries once with a shorter
    prompt and halved num_predict before giving up.
    """
    model = _model_name()

    if not is_ollama_running():
        msg = "Ollama is not running — start it and retry."
        logger.warning("LLM: %s", msg)
        if emit_log:
            emit_log("LLM_UNAVAILABLE", msg)
        return "", msg

    if emit_log:
        emit_log("LLM_QUEUED", f"Waiting for LLM slot (model={model})")

    acquired = _llm_semaphore.acquire(timeout=LLM_TIMEOUT)
    if not acquired:
        msg = f"Timed out waiting for LLM slot after {LLM_TIMEOUT}s"
        logger.error("LLM semaphore: %s", msg)
        if emit_log:
            emit_log("LLM_TIMEOUT", msg)
        return "", msg

    try:
        if emit_log:
            emit_log("LLM_CALL", f"Sending prompt to {model} ({len(prompt)} chars)")
        t0 = time.monotonic()

        try:
            text = _do_generate(prompt, system, num_predict=4096)

        except req_lib.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 500:
                # Ollama 500 = model ran out of memory during generation.
                # Retry once with shorter prompt and smaller output window.
                logger.warning(
                    "LLM 500 (likely OOM) — retrying with reduced prompt/tokens"
                )
                if emit_log:
                    emit_log("LLM_RETRY", "Ollama returned 500 (model OOM) — retrying with shorter prompt")
                time.sleep(3)  # give Ollama a moment to recover
                short_prompt = prompt[:2000]
                try:
                    text = _do_generate(short_prompt, system, num_predict=2048)
                except req_lib.exceptions.HTTPError as exc2:
                    msg = (
                        "Ollama 500 on retry — model likely out of RAM. "
                        "Try a smaller model (e.g. qwen2.5-coder:1.5b) or add more RAM."
                    )
                    logger.error("LLM retry also failed: %s", exc2)
                    if emit_log:
                        emit_log("LLM_OOM", msg)
                    return "", msg
            else:
                raise

        elapsed = round(time.monotonic() - t0, 1)
        if emit_log:
            emit_log("LLM_DONE", f"Done in {elapsed}s ({len(text)} chars)")
        logger.info("LLM: model=%s elapsed=%.1fs chars=%d", model, elapsed, len(text))
        return text, None

    except req_lib.exceptions.ConnectionError:
        msg = "Ollama connection refused — is it still running?"
        logger.warning("LLM: %s", msg)
        if emit_log:
            emit_log("LLM_UNAVAILABLE", msg)
        return "", msg
    except req_lib.exceptions.Timeout:
        msg = f"LLM timed out after {LLM_TIMEOUT}s"
        logger.warning("LLM: %s", msg)
        if emit_log:
            emit_log("LLM_TIMEOUT", msg)
        return "", msg
    except Exception as exc:
        msg = f"LLM call failed: {exc}"
        logger.warning("LLM: %s", msg)
        if emit_log:
            emit_log("LLM_ERROR", str(exc)[:200])
        return "", msg
    finally:
        _llm_semaphore.release()
