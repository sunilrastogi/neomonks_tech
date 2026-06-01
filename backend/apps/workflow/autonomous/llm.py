"""
Direct Ollama API wrapper
=========================
Bypasses CrewAI entirely for LLM calls. Ollama manages model memory itself,
so there are no CUDA buffer allocation conflicts when multiple agents run.

A global threading.Semaphore(1) ensures only ONE model call runs at a time —
queuing subsequent requests instead of crashing with OOM errors.
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


def call(prompt: str, system: str = "", emit_log=None) -> str:
    """
    Call Ollama /api/generate and return the response text.

    :param prompt:    The user prompt
    :param system:    Optional system message
    :param emit_log:  Optional callable(step, detail) for live dashboard updates
    :returns:         Model response text, or "" on failure
    """
    model = _model_name()

    if emit_log:
        emit_log("LLM_QUEUED", f"Waiting for LLM slot (model={model})")

    acquired = _llm_semaphore.acquire(timeout=LLM_TIMEOUT)
    if not acquired:
        logger.error("LLM semaphore timed out after %ds", LLM_TIMEOUT)
        if emit_log:
            emit_log("LLM_TIMEOUT", "Gave up waiting for LLM slot")
        return ""

    try:
        if emit_log:
            emit_log("LLM_CALL", f"Calling {model} via Ollama REST API")
        t0 = time.monotonic()

        num_gpu = int(getattr(settings, "OLLAMA_NUM_GPU", 0))
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": -1,          # keep model loaded in RAM permanently
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
                "num_gpu": num_gpu,    # 0 = CPU only
            },
        }
        if system:
            payload["system"] = system

        # Model loading on CPU can take 5-10 minutes on first call — use a
        # very long connect timeout but still cap the total request time.
        resp = req_lib.post(
            f"{OLLAMA_HOST}/api/generate",
            json=payload,
            timeout=(600, LLM_TIMEOUT),   # (connect_timeout, read_timeout)
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")
        elapsed = round(time.monotonic() - t0, 1)

        if emit_log:
            emit_log("LLM_DONE", f"Done in {elapsed}s ({len(text)} chars)")

        logger.info("LLM call: model=%s elapsed=%.1fs chars=%d", model, elapsed, len(text))
        return text

    except req_lib.exceptions.Timeout:
        logger.warning("LLM call timed out after %ds", LLM_TIMEOUT)
        if emit_log:
            emit_log("LLM_TIMEOUT", f"Timed out after {LLM_TIMEOUT}s")
        return ""
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        if emit_log:
            emit_log("LLM_ERROR", str(exc)[:150])
        return ""
    finally:
        _llm_semaphore.release()
