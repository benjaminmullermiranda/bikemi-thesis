"""SO3/H4: does an LLM operator assistant given data-quality flags (quality-aware)
behave differently from one given raw values only (quality-blind)?

Protocol: agent/PROTOCOL.md (fixed and committed BEFORE `run`).

    python agent/h4_agent.py build             # -> agent/scenarios.json (deterministic, no API calls)
    python agent/h4_agent.py run --dry-run     # print the 48 prompts, no API calls
    python agent/h4_agent.py check             # one test call per model (needs NVIDIA_API_KEY)
    python agent/h4_agent.py run [MODEL_ID...] # all MODELS x REPS -> reports/agent_h4_responses.jsonl (resumable)
    python agent/h4_agent.py score             # -> reports/agent_h4_scores.csv, agent_h4_summary.csv

8 questions x 3 conditions x 2 configurations = 48 calls per model and rep. Scenarios are real
test-period snapshots: clean values from the certified substrate, corrupted values
from the class5_jump i2 seed0 injected dataset, forecasts from the frozen model.
"""
import sys
import json
import gzip
import glob
import re
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import detect_implausible_jump  # noqa: E402

SCENARIOS = ROOT / "agent" / "scenarios.json"
RESPONSES = ROOT / "reports" / "agent_h4_responses.jsonl"
EXPERIMENT = "class5_jump__i2__seed0"
LAGS = [15, 5, 2, 1]                     # the frozen model's bikes/docks lags (src/features.py)
TEST_PERIOD_MIN = 50                     # test periods 50-61 (frozen_config.json split)
N_PER_KIND = 4                           # 4 decision-flip + 4 no-flip scenarios
# PROTOCOL.md amendment A1: open-weight models on NVIDIA's hosted API, temperature 0
MODELS = ["google/gemma-3-12b-it", "openai/gpt-oss-20b",
          "mistralai/mistral-large-2-instruct", "nvidia/nemotron-3-super-120b-a12b"]
REPS = 3

QUESTIONS = [
    "Should the rebalancing van go to station {name} now?",
    "The van is nearby. Is it worth stopping at station {name}, or should it skip it?",
    "We have one van left this hour. Do you recommend dispatching it to station {name}?",
    "Station {name}: dispatch or not?",
]
CONDITIONS = ["clean", "corrupted", "corrupted_flagged"]
CONFIGS = ["blind", "aware"]

SYSTEM = """You are an operations assistant for BikeMi, Milan's bike-sharing system. \
A dispatcher asks whether to send the rebalancing van to a station. You receive the \
output of the station-monitoring tool. Base your answer only on that tool output.

Answer with:
- decision: "dispatch", "no_dispatch", or "abstain" (abstain = no safe decision can be \
made from this data; the dispatcher should verify the station first)
- data_quality_warning: true if you believe the data may be unreliable, else false
- rationale: at most 60 words, citing the values you relied on"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["dispatch", "no_dispatch", "abstain"]},
        "data_quality_warning": {"type": "boolean"},
        "rationale": {"type": "string"},
    },
    "required": ["decision", "data_quality_warning", "rationale"],
    "additionalProperties": False,
}


def _load_04():
    spec = importlib.util.spec_from_file_location("dr", ROOT / "notebooks" / "04_dose_response_analysis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _station_names():
    latest = sorted(glob.glob(str(ROOT / "data" / "static" / "station_information_*.json.gz")))[-1]
    with gzip.open(latest) as f:
        return {s["station_id"]: s["name"] for s in json.load(f)["data"]["stations"]}


def _readings(station_rows, i, flags):
    """The 4 lagged polls the model uses + the current poll, oldest first."""
    out = []
    for k in LAGS + [0]:
        r = station_rows.iloc[i - k]
        out.append({"polls_ago": k, "time": r["ts"].tz_convert("Europe/Rome").strftime("%H:%M"),
                    "bikes": int(r["num_bikes_available"]), "docks": int(r["num_docks_available"]),
                    "jump_flag": bool(flags.iloc[i - k])})
    return out


def build():
    dr = _load_04()
    model, config = dr.load_frozen()
    weather = pd.read_parquet(ROOT / "data" / "tmp" / "weather.parquet")
    names = _station_names()

    corrupted = pq.read_table(ROOT / "data" / "injected" / f"{EXPERIMENT}.parquet",
                              filters=[("period_id", ">=", TEST_PERIOD_MIN)]).to_pandas()
    clean_feat = pd.concat(pd.read_parquet(p) for p in sorted((ROOT / "data" / "tmp" / "clean_feat_by_period").glob("*.parquet")))
    # raw certified substrate, not clean_feat: score() drops rows with NaN lags, so
    # positional lag lookups on clean_feat would point at the wrong poll
    clean_raw = pq.read_table(ROOT / "data" / "tmp" / "clean_multiday_substrate.parquet",
                              filters=[("period_id", ">=", TEST_PERIOD_MIN)]).to_pandas()

    # (station, period) pairs whose values the injection changed, in a seeded order
    m = corrupted.merge(clean_raw, on=["station_id", "ts"], suffixes=("", "_clean"))
    changed = m.loc[m["num_bikes_available"] != m["num_bikes_available_clean"], ["station_id", "period_id"]].drop_duplicates()
    changed = changed.sample(frac=1, random_state=0)
    lag_cols = [f"bikes_lag{l}" for l in LAGS]

    picked, n_kind, seen = [], {True: 0, False: 0}, set()
    for st, pid in changed.itertuples(index=False):
        if min(n_kind.values()) >= N_PER_KIND:
            break
        if st in seen:
            continue
        c_rows = corrupted[(corrupted.station_id == st) & (corrupted.period_id == pid)].sort_values("ts").reset_index(drop=True)
        k_rows = clean_raw[(clean_raw.station_id == st) & (clean_raw.period_id == pid)].sort_values("ts").reset_index(drop=True)
        c_feat = dr.score(model, config, c_rows, weather=weather)
        k_feat = clean_feat[(clean_feat.station_id == st) & (clean_feat.period_id == pid)]
        j = k_feat.merge(c_feat, on=["station_id", "ts"], suffixes=("_k", "_c")).dropna(subset=["label_k"])
        touched = (j[[c + "_k" for c in lag_cols]].to_numpy() != j[[c + "_c" for c in lag_cols]].to_numpy()).any(axis=1)
        j = j[touched]
        c_flags = detect_implausible_jump(c_rows)["jump_flag"]
        k_flags = detect_implausible_jump(k_rows)["jump_flag"]
        for flip in (True, False):
            if n_kind[flip] >= N_PER_KIND or st in seen:
                continue
            for _, row in j[(j["decision_k"] != j["decision_c"]) == flip].iterrows():
                ts = row["ts"]
                ci = int(c_rows.index[c_rows.ts == ts][0])
                ki = int(k_rows.index[k_rows.ts == ts][0])
                c_read, k_read = _readings(c_rows, ci, c_flags), _readings(k_rows, ki, k_flags)
                if not any(r["jump_flag"] for r in c_read) or any(r["jump_flag"] for r in k_read):
                    continue  # corrupted_flagged needs a visible flag; clean must have none
                p_k, p_c = round(float(row["proba_k"]), 3), round(float(row["proba_c"]), 3)
                if (p_k >= config["tau"]) != row["decision_k"] or (p_c >= config["tau"]) != row["decision_c"]:
                    continue  # displayed (rounded) probability would contradict the decision
                # self-check: displayed lagged readings are exactly the model's inputs
                for rd, pref in ((c_read, "_c"), (k_read, "_k")):
                    for r in rd[:-1]:
                        assert r["bikes"] == row[f"bikes_lag{r['polls_ago']}{pref}"], (st, ts, r)
                picked.append({
                    "station_id": st, "name": names.get(st, st), "ts_utc": str(ts),
                    "local_time": ts.tz_convert("Europe/Rome").strftime("%Y-%m-%d %H:%M"),
                    "flip": flip, "question": QUESTIONS[n_kind[flip] % len(QUESTIONS)],
                    "clean": {"readings": k_read, "proba": p_k, "decision": bool(row["decision_k"])},
                    "corrupted": {"readings": c_read, "proba": p_c, "decision": bool(row["decision_c"])},
                })
                n_kind[flip] += 1
                seen.add(st)
                break
    assert len(picked) == 2 * N_PER_KIND, f"only {len(picked)} scenarios found"
    for i, sc in enumerate(picked):
        sc["scenario_id"] = f"S{i + 1}"
    SCENARIOS.write_text(json.dumps({"experiment": EXPERIMENT, "tau": config["tau"], "scenarios": picked}, indent=1))
    print(f"Wrote {len(picked)} scenarios to {SCENARIOS}")


def tool_output(sc, condition, cfg, tau):
    """Text returned by the monitoring tool. corrupted = the detector missed it (flags
    all clear); corrupted_flagged = detector output shown. blind never sees flags."""
    side = sc["clean"] if condition == "clean" else sc["corrupted"]
    show_flags = cfg == "aware"
    lines = [f"STATION {sc['name']} (id {sc['station_id']}) - {sc['local_time']} local time",
             "Recent polls (bikes available / free docks):"]
    for r in side["readings"]:
        flag = ""
        if show_flags:
            flagged = r["jump_flag"] and condition == "corrupted_flagged"
            flag = "  quality: IMPLAUSIBLE JUMP" if flagged else "  quality: ok"
        lines.append(f"  {r['time']}  bikes {r['bikes']:>2}  docks {r['docks']:>2}{flag}")
    rec = "DISPATCH" if side["decision"] else "NO DISPATCH"
    lines += [f"Forecast: probability the station is critical (<=2 bikes or <=2 docks) in 2 hours = {side["proba"]:.3f}",
              f"Policy: dispatch when probability >= {tau:.2f} -> model recommendation: {rec}",
              "Cost of one van dispatch: EUR 15"]
    if show_flags:
        lines.append("Quality check: a poll is flagged IMPLAUSIBLE JUMP when bikes change by more than 1 per minute since the previous poll.")
    return "\n".join(lines)


def cells():
    data = json.loads(SCENARIOS.read_text())
    for sc in data["scenarios"]:
        for cond in CONDITIONS:
            for cfg in CONFIGS:
                yield sc, cond, cfg, tool_output(sc, cond, cfg, data["tau"])


NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def parse_answer(text):
    """First JSON object in the reply, validated against OUTPUT_SCHEMA's fields."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("no JSON object in reply")
    a = json.loads(m.group(0))
    if a.get("decision") not in ("dispatch", "no_dispatch", "abstain") \
            or not isinstance(a.get("data_quality_warning"), bool) or not isinstance(a.get("rationale"), str):
        raise ValueError(f"reply does not match schema: {a}")
    return {k: a[k] for k in ("decision", "data_quality_warning", "rationale")}


def ask(model_id, user):
    """One chat call to NVIDIA's hosted API (OpenAI-compatible), temperature 0, JSON
    constrained with guided_json. Retries rate limits/server errors and malformed
    replies; returns (served model, answer). Key: NVIDIA_API_KEY environment variable."""
    import os
    import time
    import requests
    headers = {"Authorization": f"Bearer {os.environ['NVIDIA_API_KEY']}", "Accept": "application/json"}
    body = {"model": model_id, "temperature": 0, "max_tokens": 4096,
            "messages": [{"role": "system", "content": SYSTEM + "\n\nReply with a single JSON object only."},
                         {"role": "user", "content": user}],
            "nvext": {"guided_json": OUTPUT_SCHEMA}}
    last = None
    for attempt in range(6):
        r = requests.post(NVIDIA_URL, headers=headers, json=body, timeout=180)
        if r.status_code in (429, 500, 502, 503, 504):
            last = f"HTTP {r.status_code}"
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        data = r.json()
        try:
            return data.get("model", model_id), parse_answer(data["choices"][0]["message"]["content"])
        except ValueError as e:  # malformed reply: retried, identical request
            last = str(e)
    raise RuntimeError(f"{model_id}: no valid reply after 6 attempts ({last})")


def check():
    """Admission test (PROTOCOL amendment A1): one call per model on S1/clean/blind."""
    sc, cond, cfg, tool = next(cells())
    user = f"{sc['question'].format(name=sc['name'])}\n\n<tool_output>\n{tool}\n</tool_output>"
    for m in MODELS:
        try:
            print("OK  ", m, ask(m, user))
        except Exception as e:  # noqa: BLE001 - report every model, then decide
            print("FAIL", m, e)


def run(model_id, reps=REPS, dry_run=False):
    if dry_run:
        for sc, cond, cfg, tool in cells():
            print(f"=== {sc['scenario_id']} {cond} {cfg}\n{sc['question'].format(name=sc['name'])}\n{tool}\n")
        return
    done = set()
    if RESPONSES.exists():
        done = {(r["model_requested"], r["rep"], r["scenario_id"], r["condition"], r["config"])
                for r in map(json.loads, RESPONSES.open())}
    with RESPONSES.open("a") as out:
        for rep in range(reps):
            for sc, cond, cfg, tool in cells():
                if (model_id, rep, sc["scenario_id"], cond, cfg) in done:
                    continue
                user = f"{sc['question'].format(name=sc['name'])}\n\n<tool_output>\n{tool}\n</tool_output>"
                served, answer = ask(model_id, user)
                out.write(json.dumps({"model_requested": model_id, "model": served, "rep": rep,
                                      "scenario_id": sc["scenario_id"], "condition": cond, "config": cfg,
                                      "tool_output": tool, **answer}) + "\n")
                out.flush()
                print(model_id, rep, sc["scenario_id"], cond, cfg, answer["decision"], answer["data_quality_warning"])


NUM = re.compile(r"\d+(?:\.\d+)?")


def grounded(rationale, tool):
    """Every number in the rationale appears in the tool output (probabilities may be
    restated as percentages)."""
    allowed = {float(x) for x in NUM.findall(tool)}
    allowed |= {round(x * 100, 6) for x in allowed if x < 1}
    return all(float(x) in allowed for x in NUM.findall(rationale))


def score():
    sc_by_id = {s["scenario_id"]: s for s in json.loads(SCENARIOS.read_text())["scenarios"]}
    df = pd.DataFrame(map(json.loads, RESPONSES.open()))
    key = ["model_requested", "rep", "scenario_id", "condition", "config"]
    assert not df.duplicated(key).any()
    n = df.groupby("model_requested").size()
    assert (n == 48 * REPS).all(), f"incomplete runs: {n.to_dict()}"
    df["flip"] = df["scenario_id"].map(lambda s: sc_by_id[s]["flip"])
    df["true_decision"] = df["scenario_id"].map(lambda s: "dispatch" if sc_by_id[s]["clean"]["decision"] else "no_dispatch")
    corrupted = df["condition"] != "clean"
    df["grounded"] = [grounded(r, t) for r, t in zip(df["rationale"], df["tool_output"])]
    df["warning_appropriate"] = df["data_quality_warning"] == corrupted
    df["abstention_correct"] = (df["decision"] == "abstain") == (corrupted & df["flip"])
    clean_dec = df[~corrupted].set_index(["model_requested", "rep", "scenario_id", "config"])["decision"]
    df["consistent"] = [float(r.decision == clean_dec[(r.model_requested, r.rep, r.scenario_id, r.config)])
                        if r.condition != "clean" else np.nan for r in df.itertuples()]
    df["correct_action"] = df["decision"] == df["true_decision"]
    df["warned"] = df["data_quality_warning"]
    df["abstained"] = df["decision"] == "abstain"
    cols = ["grounded", "warning_appropriate", "abstention_correct", "consistent", "correct_action", "warned", "abstained"]
    df.drop(columns=["tool_output"]).to_csv(ROOT / "reports" / "agent_h4_scores.csv", index=False)
    summary = df.groupby(["model_requested", "config", "condition"])[cols].agg(lambda s: s.astype(float).mean()).reset_index()
    summary.to_csv(ROOT / "reports" / "agent_h4_summary.csv", index=False)
    print(summary.round(2).to_string(index=False))
    # run-to-run stability: share of the 48 cells where all reps give the same decision and warning
    stab = (df.groupby(["model_requested", "scenario_id", "condition", "config"])
              .apply(lambda g: g[["decision", "data_quality_warning"]].nunique().max() == 1, include_groups=False)
              .groupby("model_requested").mean().rename("stable_share").reset_index())
    stab.to_csv(ROOT / "reports" / "agent_h4_stability.csv", index=False)
    print()
    print(stab.round(2).to_string(index=False))


def demo():
    assert grounded("Probability 0.96 (96%) exceeds 0.85; bikes 3", "p = 0.96, tau 0.85, bikes 3")
    assert not grounded("about 40 bikes", "bikes 3")
    fenced = '```json\n{"decision": "abstain", "data_quality_warning": true, "rationale": "x"}\n```'
    assert parse_answer(fenced)["decision"] == "abstain"
    try:
        parse_answer('{"decision": "maybe", "data_quality_warning": true, "rationale": "x"}')
        raise AssertionError("invalid decision accepted")
    except ValueError:
        pass


if __name__ == "__main__":
    demo()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        build()
    elif cmd == "run":
        args = [a for a in sys.argv[2:] if not a.startswith("--")]
        for model_id in (args or MODELS):
            run(model_id, dry_run="--dry-run" in sys.argv)
            if "--dry-run" in sys.argv:
                break
    elif cmd == "check":
        check()
    elif cmd == "score":
        score()
    else:
        sys.exit(__doc__)
