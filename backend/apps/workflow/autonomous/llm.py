"""
Direct Ollama API wrapper
=========================
Bypasses CrewAI entirely for LLM calls. Ollama manages model memory itself,
so there are no CUDA buffer allocation conflicts when multiple agents run.

A global threading.Semaphore(1) ensures only ONE model call runs at a time —
queuing subsequent requests instead of crashing with OOM errors.

Return convention
-----------------
call() returns a (text, error) tuple:
  - text  : model response string (may be "")
  - error : None on success, or a short human-readable string on failure
            e.g. "Ollama not running", "Timed out after 300s"
"""
from __future__ import annotations

import logging
import threading
import time

import requests as req_lib

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Global semaphore: only 1 LLM call at a time ──────────────────────────────
_llm_semaphore = threading.Semaphore(1)

OLLAMA_HOST: str = getattr(settings, "OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL: str = getattr(settings, "DEFAULT_AGENT_MODEL", "ollama/qwen2.5-coder:7b")
LLM_TIMEOUT: int = int(getattr(settings, "LLM_TIMEOUT_SECONDS", 300))


def _model_name() -> str:
    """Strip 'ollama/' prefix if present."""
    m = getattr(settings, "DEFAULT_AGENT_MODEL", "ollama/qwen2.5-coder:7b")
    return m.replace("ollama/", "")


def is_ollama_running() -> bool:
    """Quick check — does Ollama respond at all?"""
    host = getattr(settings, "OLLAMA_HOST", "http://localhost:11434")
    try:
        req_lib.get(f"{host}/api/tags", timeout=3)
        return True
    except Exception:
        return False


def call(prompt: str, system: str = "", emit_log=None) -> tuple[str, str | None]:
    """
    Call Ollama /api/generate and return (response_text, error).

    error is None on success, or a short human-readable string explaining
    the failure (e.g. "Ollama not running", "Timed out after 300s").

    emit_log: optional callable(step, detail) for live dashboard updates.
    """
    model = _model_name()

    # Fast-fail if Ollama is not reachable at all
    if not is_ollama_running():
        msg = "Ollama is not running — agent cannot execute. Start Ollama and retry."
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
            emit_log("LLM_CALL", f"Calling {model} via Ollama REST API")
        t0 = time.monotonic()

        num_gpu = int(getattr(settings, "OLLAMA_NUM_GPU", 0))
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": -1,
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
                "num_gpu": num_gpu,
            },
        }
        if system:
            payload["system"] = system

        resp = req_lib.post(
            f"{OLLAMA_HOST}/api/generate",
            json=payload,
            timeout=(600, LLM_TIMEOUT),
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")
        elapsed = round(time.monotonic() - t0, 1)

        if emit_log:
            emit_log("LLM_DONE", f"Done in {elapsed}s ({len(text)} chars)")

        logger.info("LLM call: model=%s elapsed=%.1fs chars=%d", model, elapsed, len(text))
        return text, None

    except req_lib.exceptions.ConnectionError:
        msg = "Ollama is not running — agent cannot execute. Start Ollama and retry."
        logger.warning("LLM connection error: %s", msg)
        if emit_log:
            emit_log("LLM_UNAVAILABLE", msg)
        return "", msg
    except req_lib.exceptions.Timeout:
        msg = f"LLM call timed out after {LLM_TIMEOUT}s"
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
