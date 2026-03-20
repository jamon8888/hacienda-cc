# hacienda-maker

Autonomous plugin quality loop for Claude Cowork. Evaluates trigger precision and functional
correctness, then iterates until a score threshold is reached.

## Commands

| Command | What it does |
|---------|-------------|
| `/hacienda-maker` | Full pipeline or resume |
| `/hacienda-maker:collect` | Capture use cases, generate evals |
| `/hacienda-maker:build` | Scaffold plugin skeleton, run baseline |
| `/hacienda-maker:optimize` | Autonomous improvement loop |
| `/hacienda-maker:convert` | Convert Claude Code plugin to Cowork |

## Quick Start

```bash
# In your target plugin directory:
/hacienda-maker:collect   # describe what your plugin should do
/hacienda-maker:build     # scaffold + baseline score
/hacienda-maker:optimize  # run loop until score >= 85
```

## Configuration

Edit `hacienda-maker.json` to adjust:
- `scoring.threshold` (default 85) — stop when combined score reaches this
- `loop.max_iterations` (default 30) — hard iteration cap
- `scoring.noise_floor` (default 2.0) — minimum improvement to count as a KEEP

## Scripts

```bash
# Run tests
pytest tests/ -v

# Run scorer directly (stdin JSON)
echo '{"trigger_score":80,"functional_score":90,"previous_best":70,"weights":{"trigger":0.4,"functional":0.6},"noise_floor":2.0}' | python skills/hacienda-maker/scripts/score.py

# Validate plugin structure
python skills/hacienda-maker/scripts/validate_plugin.py ./path/to/plugin
```
