# hacienda-maker/tests/test_score.py
import json
import subprocess
import sys
import pytest
from pathlib import Path

SCORE_PY = Path(__file__).parent.parent / "skills/hacienda-maker/scripts/score.py"

def run_score(payload: dict) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCORE_PY)],
        input=json.dumps(payload),
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"score.py failed: {result.stderr}"
    return json.loads(result.stdout)

def test_combined_formula():
    out = run_score({"trigger_score": 60.0, "functional_score": 80.0,
                     "previous_best": 0.0, "weights": {"trigger": 0.4, "functional": 0.6},
                     "noise_floor": 2.0})
    assert out["combined"] == pytest.approx(72.0)  # 60*0.4 + 80*0.6

def test_is_improvement_true_when_delta_exceeds_noise():
    out = run_score({"trigger_score": 80.0, "functional_score": 80.0,
                     "previous_best": 70.0, "weights": {"trigger": 0.4, "functional": 0.6},
                     "noise_floor": 2.0})
    assert out["delta"] == pytest.approx(10.0)
    assert out["is_improvement"] is True

def test_is_improvement_false_when_delta_at_noise_floor():
    # delta == noise_floor is NOT improvement (requires strictly >)
    out = run_score({"trigger_score": 72.0, "functional_score": 72.0,
                     "previous_best": 70.0, "weights": {"trigger": 0.4, "functional": 0.6},
                     "noise_floor": 2.0})
    assert out["delta"] == pytest.approx(2.0)
    assert out["is_improvement"] is False

def test_is_improvement_false_when_no_change():
    out = run_score({"trigger_score": 70.0, "functional_score": 70.0,
                     "previous_best": 70.0, "weights": {"trigger": 0.4, "functional": 0.6},
                     "noise_floor": 2.0})
    assert out["is_improvement"] is False

def test_negative_delta():
    out = run_score({"trigger_score": 50.0, "functional_score": 50.0,
                     "previous_best": 70.0, "weights": {"trigger": 0.4, "functional": 0.6},
                     "noise_floor": 2.0})
    assert out["delta"] < 0
    assert out["is_improvement"] is False
