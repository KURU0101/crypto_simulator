from __future__ import annotations

import json
from pathlib import Path


def load_saved_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def assert_saved_normalized_exists(observation: dict) -> None:
    assert Path(observation["saved_paths"]["normalized"]).exists()


def assert_saved_summary_matches_observation(observation: dict) -> dict:
    assert_saved_normalized_exists(observation)
    assert Path(observation["saved_paths"]["summary"]).exists()
    saved_summary = load_saved_json(observation["saved_paths"]["summary"])
    assert saved_summary == observation
    return saved_summary


def assert_summary_not_saved(observation: dict) -> None:
    assert "summary" not in observation["saved_paths"]
    assert_saved_normalized_exists(observation)
