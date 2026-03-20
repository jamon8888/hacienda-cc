# hacienda-maker Improvements Design

**Date:** 2026-03-20
**Status:** Draft
**Scope:** Correctifs de fiabilité et améliorations architecturales du plugin hacienda-maker v0.1.0

---

## Contexte

L'évaluation post-build de hacienda-maker v0.1.0 a identifié deux catégories de problèmes :

- **Catégorie A — Signal de mesure** : trigger detection fragile, grader LLM non calibré
- **Catégorie B — Robustesse opérationnelle** : flags CLI incorrects, pas de timeout, état non mis à jour automatiquement, pas de validation des grading.json

Ce document spécifie les correctifs pour les deux catégories.

---

## Fichiers modifiés

| Fichier | Type de changement |
|---|---|
| `skills/hacienda-maker/scripts/run_evals.py` | Flags corrigés, timeout, auto-update état, validation grading.json |
| `skills/hacienda-maker/scripts/grader.py` | Nouveau script Python (grader hybride) |
| `skills/hacienda-maker/agents/grader.md` | Mis à jour pour déléguer au script Python |
| `skills/hacienda-maker/references/scoring.md` | Documenter les nouveaux types d'expectations |
| `tests/test_run_evals_generate.py` | Mise à jour des mocks pour nouveaux flags |
| `tests/test_grader.py` | Nouveau fichier de tests TDD pour grader.py |
| `tests/test_run_evals_score.py` | Ajout tests auto-update état |

---

## Section 1 : Corrections des flags CLI

### Problème
`run_evals.py mode_generate_transcripts` utilise des flags inexistants dans `claude -p` :
- `--plugin` → n'existe pas (correct : `--plugin-dir`)
- `--system` → n'existe pas (correct : `--append-system-prompt`)
- `--context` → n'existe pas (correct : `--add-dir`)

### Correctif
Dans `mode_generate_transcripts`, remplacer :

```python
# AVANT (cassé)
["claude", "-p", entry["query"], "--plugin", str(cwd), "--system", system_msg]

# APRÈS (correct)
["claude", "-p", entry["query"], "--plugin-dir", str(cwd),
 "--append-system-prompt", system_msg, "--output-format", "json"]
```

Et pour les fichiers de contexte des evals fonctionnelles :
```python
# AVANT (cassé)
context_flags += ["--context", str(cwd / f)]

# APRÈS (correct)
context_flags += ["--add-dir", str(cwd / f)]
```

---

## Section 2 : Timeout sur les appels `claude -p`

### Problème
Aucun timeout — un appel bloqué suspend la boucle indéfiniment.

### Correctif
Ajouter `timeout=60` sur chaque `subprocess.run` vers `claude -p`. En cas de `TimeoutExpired` :
- Capturer l'exception
- Logger un avertissement
- Traiter comme transcript vide (résultat = échec propre, pas crash)

```python
try:
    result = subprocess.run([...], capture_output=True, text=True, timeout=60)
except subprocess.TimeoutExpired:
    result = type('r', (), {'stdout': '', 'returncode': 1, 'stderr': 'timeout'})()
```

---

## Section 3 : Trigger detection via `--output-format json`

### Problème
La détection SKILL_USED dans les 3 dernières lignes est fragile — Claude peut ajouter du texte après le marqueur.

### Correctif
Utiliser `--output-format json` pour obtenir une sortie structurée. Le champ `result` contient le texte complet de la réponse. Chercher le marqueur dans le `result` entier :

```python
# Parser le JSON de sortie
try:
    output = json.loads(result.stdout)
    text = output.get("result", "")
except json.JSONDecodeError:
    text = result.stdout  # fallback texte brut

triggered = f"SKILL_USED: {skill_name}".lower() in text.lower()
```

**Rétrocompatibilité** : si le JSON ne parse pas (ancienne version de claude), fallback sur le texte brut — même comportement qu'avant mais sans les 3 lignes arbitraires.

---

## Section 4 : Grader hybride (déterministe + LLM sémantique)

### Problème
Le grader LLM est non calibré — ses scores varient selon le prompt, le modèle, et la formulation des expectations. Impossible de distinguer "bon plugin" de "grader trop indulgent".

### Solution : `grader.py` (nouveau script Python)

Les expectations dans `evals.json` gagnent un champ optionnel `type` :

| Type | Vérification | Valeur de `text` |
|---|---|---|
| `contains` (défaut) | substring présent (case-insensitive) | Le texte à chercher |
| `not_contains` | substring absent | Le texte à ne pas trouver |
| `regex` | pattern Python `re.search` | Le pattern regex |
| `json_valid` | `json.loads()` sans exception | ignoré |
| `max_words` | `len(text.split()) <= N` | Nombre entier en string |
| `semantic` | Délégué au LLM grader agent | Description en langage naturel |

**Rétrocompatibilité** : une expectation sans `type` est traitée comme `contains`.

### Interface de `grader.py`

```bash
python skills/hacienda-maker/scripts/grader.py \
  --transcript evals/transcripts/eval-001-run-1.md \
  --expectations '[{"text": "mentionne GDPR", "type": "contains"}, ...]' \
  --output evals/transcripts/eval-001-run-1-grading.json \
  --eval-id eval-001 \
  --run-n 1
```

Le script :
1. Lit le transcript
2. Pour chaque expectation déterministe → évalue directement
3. Pour les expectations `semantic` → appelle le LLM grader agent via `claude -p`
4. Agrège en `grading.json` avec le schéma existant + champ `"grader_type"` par expectation

### Schéma `grading.json` (étendu)

```json
{
  "eval_id": "eval-001",
  "run_id": "run-1",
  "transcript_path": "evals/transcripts/eval-001-run-1.md",
  "expectations": [
    {
      "text": "mentionne GDPR",
      "type": "contains",
      "grader_type": "deterministic",
      "passed": true,
      "evidence": "...GDPR compliance requires..."
    },
    {
      "text": "le ton est neutre",
      "type": "semantic",
      "grader_type": "llm",
      "passed": true,
      "evidence": "Verbatim quote from transcript"
    }
  ],
  "summary": { "passed": 2, "failed": 0, "total": 2, "pass_rate": 1.0 }
}
```

### Mise à jour de `grader.md`

L'agent `grader.md` est mis à jour pour :
1. Être invoqué uniquement pour les expectations `semantic`
2. Recevoir uniquement ces expectations (pas les déterministes)
3. Retourner uniquement les résultats des expectations sémantiques

### Mise à jour de `run_evals.py`

`mode_generate_transcripts` dispatch `grader.py` (script Python) au lieu de l'agent grader. L'agent grader n'est appelé que si des expectations `semantic` existent dans le transcript à noter.

---

## Section 5 : Auto-update de l'état dans `run_evals.py --score`

### Problème
`best_score` et `best_commit` ne sont mis à jour que lors d'un `--baseline` ou par le LLM manuellement.

### Correctif
Dans `mode_score`, après calcul du score :

```python
if score_out["is_improvement"]:
    state["history"]["best_score"] = score_out["combined"]
    state["history"]["best_commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True
    ).stdout.strip()
    write_state(cwd, state)
```

Également : valider `grading.json` avant extraction de `pass_rate` :

```python
def safe_pass_rate(grading: dict) -> float:
    summary = grading.get("summary", {})
    rate = summary.get("pass_rate")
    if not isinstance(rate, (int, float)):
        print(f"WARNING: malformed grading.json — missing pass_rate", file=sys.stderr)
        return 0.0
    return float(rate)
```

---

## Tests

### `tests/test_grader.py` (nouveau, TDD)

Tests pour chaque type d'expectation :
- `test_contains_passes` / `test_contains_fails`
- `test_not_contains_passes` / `test_not_contains_fails`
- `test_regex_passes` / `test_regex_fails`
- `test_json_valid_passes` / `test_json_valid_fails`
- `test_max_words_passes` / `test_max_words_fails`
- `test_no_type_defaults_to_contains`
- `test_grading_json_schema_valid`
- `test_grader_type_field_present`

### `tests/test_run_evals_score.py` (mis à jour)

Ajouter :
- `test_best_score_updated_on_improvement`
- `test_best_commit_updated_on_improvement`
- `test_best_score_not_updated_when_no_improvement`
- `test_malformed_grading_json_returns_zero`

### `tests/test_run_evals_generate.py` (mis à jour)

Mettre à jour les mocks pour les nouveaux flags (`--plugin-dir`, `--append-system-prompt`, `--output-format json`).

---

## Dépendances

Aucune nouvelle dépendance runtime. `grader.py` utilise uniquement stdlib + le `claude` CLI pour les expectations sémantiques.

---

## Non-inclus (hors scope)

- Calibration du grader LLM par exemples annotés (complexité trop élevée pour ce cycle)
- Détection d'activation de skill via métadonnées internes de claude (non exposé dans le CLI)
- Tests end-to-end de `/hacienda-maker:convert`
