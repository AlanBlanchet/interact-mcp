#!/usr/bin/env python3
"""Generate vision-capable model list from litellm for the VS Code extension."""

import json
import os
import re
import signal
from contextlib import contextmanager
from pathlib import Path

import litellm

_ENV_PATTERNS = re.compile(
    r"_(API_KEY|API_BASE|API_SECRET|ACCESS_KEY|SECRET_KEY|API_VERSION)$"
)

FAKE_PROVIDER_RE = re.compile(r"^\d+[-_x]+\d+$|^v\d+$")
FAKE_PROVIDER_NAMES = {"high", "low", "medium", "standard"}

# Providers where litellm.validate_environment() misses required keys.
# These use get_secret_str() in their transformation class instead.
_EXTRA_ENV_KEYS: dict[str, list[str]] = {
    "zai": ["ZAI_API_KEY"],
}


@contextmanager
def _cleared_api_env():
    saved = {k: os.environ.pop(k) for k in list(os.environ) if _ENV_PATTERNS.search(k)}
    try:
        yield
    finally:
        os.environ.update(saved)


def _get_env_keys(models: list[str]) -> list[str]:
    for model in models:
        signal.alarm(3)
        try:
            with _cleared_api_env():
                info = litellm.validate_environment(model)
            keys = info.get("missing_keys", [])
            if keys:
                return keys
        except Exception:
            continue
        finally:
            signal.alarm(0)
    return []


signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError()))

providers: dict[str, list[str]] = {}
for model, info in litellm.model_cost.items():
    if not info.get("supports_vision"):
        continue
    provider = info.get("litellm_provider", "")
    if not provider or " " in provider or provider in FAKE_PROVIDER_NAMES or FAKE_PROVIDER_RE.match(provider):
        continue
    providers.setdefault(provider, []).append(model)

result = {
    "providers": {
        k: {"envKeys": _get_env_keys(v) or _EXTRA_ENV_KEYS.get(k, []), "models": sorted(v)}
        for k, v in sorted(providers.items())
    }
}

out = Path(__file__).resolve().parent.parent / "src" / "models.json"
out.write_text(json.dumps(result, indent=2) + "\n")
total = sum(len(p["models"]) for p in result["providers"].values())
print(f"Wrote {total} models across {len(result['providers'])} providers to {out}")
