from __future__ import annotations

from pathlib import Path

import pytest

import src.graph.seeds as seeds


@pytest.mark.unit
def test_sanitize_settings_includes_math_flags() -> None:
    settings = seeds._sanitize_settings({})  # pylint: disable=protected-access

    assert settings["hierarchy_engine"] == "v1"
    assert settings["membership_engine"] == "off"
    assert settings["obs_weighting"] == "off"
    assert settings["obs_p_min"] == 0.01
    assert settings["obs_completeness_floor"] == 0.01


@pytest.mark.unit
def test_sanitize_settings_clamps_and_validates_math_flags() -> None:
    raw = {
        "hierarchy_engine": "V2",
        "membership_engine": "GRF",
        "obs_weighting": "IPW",
        "obs_p_min": 0.0,
        "obs_completeness_floor": 999,
    }

    settings = seeds._sanitize_settings(raw)  # pylint: disable=protected-access

    assert settings["hierarchy_engine"] == "v2"
    assert settings["membership_engine"] == "grf"
    assert settings["obs_weighting"] == "ipw"
    assert settings["obs_p_min"] == 1e-4
    assert settings["obs_completeness_floor"] == 0.5


@pytest.mark.unit
def test_update_graph_settings_persists_math_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    preset_file = tmp_path / "seed_presets.json"
    preset_file.write_text('{"adi_tpot": ["alice"]}')
    state_file = tmp_path / "graph_settings.json"
    state_file.write_text("{}")

    monkeypatch.setattr(seeds, "_DEFAULT_PRESET_FILE", preset_file, raising=False)
    monkeypatch.setattr(seeds, "_SEED_STATE_FILE", state_file, raising=False)

    updated = seeds.update_graph_settings(
        {
            "hierarchy_engine": "v2",
            "membership_engine": "grf",
            "obs_weighting": "ipw",
            "obs_p_min": 0.02,
            "obs_completeness_floor": 0.03,
        }
    )

    cfg = updated["settings"]
    assert cfg["hierarchy_engine"] == "v2"
    assert cfg["membership_engine"] == "grf"
    assert cfg["obs_weighting"] == "ipw"
    assert cfg["obs_p_min"] == 0.02
    assert cfg["obs_completeness_floor"] == 0.03
