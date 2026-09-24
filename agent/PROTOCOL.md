# SO3/H4 agent comparison - pre-registered protocol

Fixed and committed **before** any model call (`git log agent/PROTOCOL.md` is the
timestamp). Code: `agent/h4_agent.py`. Scenarios: `agent/scenarios.json`.

## 1. Question
Does an LLM operator assistant that sees data-quality flags (**quality-aware**) warn or
abstain differently from one that sees raw values only (**quality-blind**) when the feed
is corrupted? (H4, SO3; thesis §1.2, §4.6.)

## 2. Scenarios (8)
Real test-period snapshots (periods 50-61), one per station, chosen deterministically
(`random_state=0`) from stations whose readings were changed by the
`class5_jump__i2__seed0` injection:
- **4 flip scenarios**: the corruption changes the frozen model's dispatch decision
  (tau = 0.85). **4 no-flip scenarios**: the corruption changes the model's inputs but
  not its decision.
- Every scenario has at least one detector-flagged reading on the corrupted side and
  none on the clean side. The displayed probability (3 decimals) never contradicts the
  displayed decision.
- The tool output shows the 4 lagged polls the model uses (15, 5, 2, 1 polls ago) plus
  the current poll, the forecast probability, the policy threshold and recommendation,
  and the dispatch cost (EUR 15). `build` asserts that the shown polls equal the model's
  lag inputs.
- 4 question phrasings, each used once for a flip and once for a no-flip scenario.

## 3. Conditions (3) x configurations (2) = 48 calls
| Condition | Values shown | Flags shown to *aware* |
|---|---|---|
| clean | certified clean substrate | all "ok" (true detector output) |
| corrupted | class 5 corrupted values | all "ok" (simulated detector miss) |
| corrupted_flagged | class 5 corrupted values | true detector output (`detect_implausible_jump`) |

*blind* sees no quality column and no detector description; everything else is
identical. For *blind*, corrupted and corrupted_flagged are the same input by design.

## 4. Rubric (binary, per response; automatic, no human judgement)
The model must return JSON `{decision: dispatch|no_dispatch|abstain,
data_quality_warning: bool, rationale: str}` (structured output, schema-enforced).
1. **Groundedness**: every number in `rationale` appears in the tool output
   (a probability may be restated as a percentage).
2. **Warning appropriateness**: `data_quality_warning` is true iff the condition is
   corrupted or corrupted_flagged.
3. **Abstention correctness**: `decision == abstain` iff the data are corrupted **and**
   the corruption flips the model's decision (flip scenarios).
4. **Recommendation consistency** (corrupted conditions only): same decision as the same
   configuration gave on the clean version of the scenario.

Also reported: correct action (decision equals the clean-data model decision), warning
rate, abstention rate.

## 5. Model and settings
**Superseded by amendment A1 (§8) before the main run.** Original text, kept for the record:

Four Claude models, each run **3 times** over all 48 cells (576 calls total), with the
same system prompt, scenarios and schema, `max_tokens` 4096:
- `claude-haiku-4-5`, `claude-sonnet-4-6`: temperature 0.
- `claude-sonnet-5`, `claude-opus-5`: provider defaults. These models reject the
  temperature parameter, so the 3 repetitions measure their run-to-run variation.

The model ID actually served is logged per response. The model list is fixed here;
none is added or dropped after seeing results.

## 6. Analysis
Descriptive only: rates per model x configuration x condition, pooled over the 3
repetitions (`reports/agent_h4_summary.csv`), plus run-to-run stability per model: the
share of the 48 cells where all 3 repetitions give the same decision and warning
(`reports/agent_h4_stability.csv`).
The H4 contrast is aware vs. blind on corrupted_flagged (warning rate, abstention
correctness), with clean as the false-alarm check and corrupted as the detector-miss
ceiling. n = 8 paired scenarios is too few for an inferential test, so none is claimed.
No prompt, rubric or scenario is changed after the first call. Any rerun is reported.

## 7. Known limits (declared in advance)
- Class 5 only, one intensity, one seed. The detector that produces the flags also
  certified the substrate (same circularity as H3).
- The corrupted condition simulates a detector miss by showing "ok" flags. The silent
  offset (class 6) case is the real-world version of this.
- Four open-weight models (A1). Results describe these models' behaviour, not LLMs in general.

## 8. Amendment A1 (2026-09-24, committed before the main run)
**Why:** no API budget was available for the Claude lineup in §5. One test call was
made beforehand (`claude-haiku-4-5` via OpenRouter, scenario S1 / clean / blind, answer
`no_dispatch`, no warning). It is not part of the results. No other call was made.

**Models** (open weights, NVIDIA hosted API `integrate.api.nvidia.com`), small to large:
`google/gemma-3-12b-it`, `openai/gpt-oss-20b`, `mistralai/mistral-large-2-instruct`,
`nvidia/nemotron-3-super-120b-a12b`. All are run at **temperature 0**, `max_tokens` 4096,
**3 repetitions** each (576 calls). Scenarios, prompts, rubric and analysis (§2-§4, §6)
are unchanged. Open weights mean anyone can rerun the experiment on the same models.

**JSON output:** requested through NVIDIA's `guided_json` with the §4 schema, plus the
line "Reply with a single JSON object only." added to the system prompt (identical for
both configurations). A reply that is not valid JSON matching the schema is re-requested
with the same input, at most 6 attempts. The number of re-requests is not recorded as
a result.

**Admission rule:** `python agent/h4_agent.py check` sends one call per model (S1 /
clean / blind) before the run. A model that cannot return a valid reply there is
dropped and reported as dropped. No model is dropped or added after the main run starts.

## 9. Amendment A2 (2026-09-24, committed before the admission check and main run)
**Why:** no NVIDIA API key was obtained; a Groq API key was. No NVIDIA call was made.

**Models** (open weights, Groq hosted API `api.groq.com`): `openai/gpt-oss-20b`,
`qwen/qwen3.8-27b`, `openai/gpt-oss-120b`. These are all the general chat models the key
can access, except `allam-2-7b` (an Arabic-focused model with a 4k context). This
replaces the A1 list. Temperature 0, `max_tokens` 4096, 3 repetitions each (432 calls).

**JSON output:** Groq JSON mode (`response_format: json_object`) instead of
`guided_json`; the reply is then validated against the §4 schema. Invalid replies are
re-requested as in A1 (at most 6 attempts). Everything else in A1 and §2-§4, §6 holds,
including the admission rule (`check`).
