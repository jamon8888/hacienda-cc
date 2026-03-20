#!/usr/bin/env python3
"""score.py — reads JSON from stdin, writes JSON to stdout."""
import json
import sys

def main():
    payload = json.loads(sys.stdin.read())
    trigger = payload["trigger_score"]
    functional = payload["functional_score"]
    previous_best = payload["previous_best"]
    w_trigger = payload["weights"]["trigger"]
    w_functional = payload["weights"]["functional"]
    noise_floor = payload["noise_floor"]

    combined = round(trigger * w_trigger + functional * w_functional, 4)
    delta = round(combined - previous_best, 4)
    is_improvement = delta > noise_floor

    print(json.dumps({"combined": combined, "delta": delta, "is_improvement": is_improvement}))

if __name__ == "__main__":
    main()
