"""
Model warmup — call once at startup to pre-load the model into RAM.
Subsequent calls will be fast (model already resident).
Run as: python manage.py warmup_model
"""
import logging
import threading

logger = logging.getLogger(__name__)


def warmup_in_background() -> None:
    """Kick off model warmup in a daemon thread — non-blocking."""
    t = threading.Thread(target=_warmup, daemon=True, name="model-warmup")
    t.start()


def _warmup() -> None:
    import time
    from django.conf import settings
    try:
        import requests as req_lib
        host = getattr(settings, "OLLAMA_HOST", "http://localhost:11434")
        model = getattr(settings, "DEFAULT_AGENT_MODEL", "ollama/qwen2.5-coder:7b").replace("ollama/", "")
        num_gpu = int(getattr(settings, "OLLAMA_NUM_GPU", 0))

        logger.info("Warmup: loading %s into memory (num_gpu=%d) — first call may take several minutes on CPU", model, num_gpu)
        t0 = time.monotonic()

        resp = req_lib.post(
            f"{host}/api/generate",
            json={
                "model": model,
                "prompt": "Hi",
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 1, "num_gpu": num_gpu},
            },
            timeout=(900, 60),  # up to 15 min to load, 60s to generate 1 token
        )
        elapsed = round(time.monotonic() - t0, 1)
        if resp.ok:
            logger.info("Warmup: model loaded in %.1fs — ready for inference", elapsed)
        else:
            logger.warning("Warmup: model load returned %d in %.1fs", resp.status_code, elapsed)
    except Exception as exc:
        logger.warning("Warmup failed (non-fatal): %s", exc)
