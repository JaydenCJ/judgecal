# Judge log format

judgecal reads **JSON Lines** (one JSON object per line) or a single **JSON
array** of objects. Each object is one pairwise comparison: two responses were
shown to a judge model, and the judge picked a side (or called a tie).

Only `verdict` is required. Every other field unlocks an additional check:

| Field | Unlocks | Notes |
|---|---|---|
| `verdict` | everything | `a` / `b` / `tie` (see accepted spellings below) |
| `human` | human agreement (kappa), human-adjusted bias deltas | same value domain as `verdict` |
| `judge` | self-preference, `--judge` filtering | the judge model's name as logged |
| `model_a`, `model_b` | self-preference, model-aware swap pairing | candidate model names |
| `len_a`, `len_b` | length bias | integer lengths (characters or tokens — any unit, used only relatively) |
| `response_a`, `response_b` | length bias (derived), models (nested) | plain string, or `{"model": …, "text": …}` / `{"name": …, "tokens": …}` |
| `pair_id` | swap-consistency analysis | any string/number linking the two orderings of one prompt |
| `swapped` | swap pairing without model names | `true`/`false`, `"original"`/`"swapped"`, `"ab"`/`"ba"` |

## Canonical example

```json
{"pair_id": "q17", "judge": "aurora-8b",
 "model_a": "nimbus-9", "model_b": "cobalt-1",
 "len_a": 512, "len_b": 380,
 "verdict": "a", "human": "b", "swapped": false}
```

## Field aliases

Real exports never agree on names, so each canonical field accepts common
aliases (checked in this order, first hit wins):

| Canonical | Accepted keys |
|---|---|
| `verdict` | `verdict`, `choice`, `winner`, `judgement`, `judgment`, `preference`, `decision`, `label` |
| `human` | `human`, `human_verdict`, `human_label`, `human_choice`, `gold`, `gold_label`, `annotation`, `annotator_label` |
| `judge` | `judge`, `judge_model`, `evaluator`, `grader` |
| `pair_id` | `pair_id`, `prompt_id`, `question_id`, `group_id`, `example_id` |
| `swapped` | `swapped`, `swap`, `is_swapped`, `order` |
| `text_a` / `text_b` | `response_*`, `text_*`, `answer_*`, `output_*`, `completion_*` |
| `len_a` / `len_b` | `len_*`, `length_*`, `tokens_*` |

When the alias table is wrong for your export, `--map field=key` overrides it
per field and disables the fallback for that field:

```bash
judgecal audit log.jsonl --map verdict=final_call --map human=annotator_vote
```

## Verdict value spellings

All of these fold to the canonical `a` / `b` / `tie`:

| Canonical | Accepted values (case-insensitive) |
|---|---|
| `a` | `a`, `model_a`, `model_1`, `assistant_a`, `response_a`, `first`, `left`, `1` (string or int) |
| `b` | `b`, `model_b`, `model_2`, `assistant_b`, `response_b`, `second`, `right`, `2` (string or int) |
| `tie` | `tie`, `tied`, `equal`, `both`, `same`, `draw`, `neither` |

A verdict equal to one of the side **model names** (`"winner": "nimbus-9"`)
resolves to whichever side that model occupies — common in arena exports.

## Error handling

- A line that is not valid JSON, has no recognizable verdict, or carries a
  negative length is **skipped** and reported with its line number.
- An unrecognizable `human` or `swapped` value **degrades**: the record is
  kept, the field is dropped, and a warning is reported.
- `judgecal validate log.jsonl` prints every issue and exits 1 if any row was
  skipped — wire it before `audit` in scripts.
