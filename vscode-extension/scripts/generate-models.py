#!/usr/bin/env python3
"""Generate vision-capable model list from litellm for the VS Code extension."""
import json
from pathlib import Path

import litellm

models_by_provider: dict[str, list[str]] = {}
for model, info in litellm.model_cost.items():
    if not info.get("supports_vision"):
        continue
    provider = model.split("/")[0] if "/" in model else "openai"
    models_by_provider.setdefault(provider, []).append(model)

result = {k: sorted(v) for k, v in sorted(models_by_provider.items())}

out = Path(__file__).resolve().parent.parent / "src" / "models.json"
out.write_text(json.dumps(result, indent=2) + "\n")
print(f"Wrote {sum(len(v) for v in result.values())} models to {out}")
