from __future__ import annotations

import json
from pathlib import Path


def load_config(config_path: str | Path) -> dict:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
