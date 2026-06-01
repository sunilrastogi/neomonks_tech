"""
Management command: warmup_model
Pre-loads the configured Ollama model into RAM.
Run this once after starting the server so the first agent task doesn't wait.

Usage:
    python manage.py warmup_model
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Pre-load the Ollama model into RAM (run once after server start)."

    def handle(self, *args, **options):
        import time, requests
        from django.conf import settings

        host  = getattr(settings, "OLLAMA_HOST", "http://localhost:11434")
        model = getattr(settings, "DEFAULT_AGENT_MODEL", "ollama/qwen2.5-coder:7b").replace("ollama/", "")
        num_gpu = int(getattr(settings, "OLLAMA_NUM_GPU", 0))

        self.stdout.write(f"Loading {model} (num_gpu={num_gpu})...")
        self.stdout.write("This may take 3-10 minutes on CPU. Do not cancel.")
        t0 = time.monotonic()

        try:
            resp = requests.post(
                f"{host}/api/generate",
                json={
                    "model": model,
                    "prompt": "Say READY",
                    "stream": False,
                    "keep_alive": -1,
                    "options": {"num_predict": 5, "num_gpu": num_gpu},
                },
                timeout=(900, 120),
            )
            elapsed = round(time.monotonic() - t0, 1)
            if resp.ok:
                reply = resp.json().get("response", "").strip()
                self.stdout.write(self.style.SUCCESS(
                    f"Model loaded in {elapsed}s. Response: '{reply}'"
                ))
                self.stdout.write("Model is now resident in RAM. Agents can start immediately.")
            else:
                self.stdout.write(self.style.ERROR(
                    f"Load failed ({resp.status_code}) after {elapsed}s: {resp.text[:200]}"
                ))
        except Exception as e:
            elapsed = round(time.monotonic() - t0, 1)
            self.stdout.write(self.style.ERROR(f"Error after {elapsed}s: {e}"))
