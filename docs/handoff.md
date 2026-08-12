# Session Handoff — 2026-08-10

## Goal

Master's thesis (Univ. of Cassino, Dept. of Economics and Law) on BikeMi bike-share data
quality: quantify how synthetic data-quality corruption (6 injected anomaly classes) propagates
through detection → forecasting model → dispatch decision → operating cost. Design frozen
2026-08-08 per Prof. Russo's approval (`docs/design_freeze.md`), covering his four named
categories: injection design, cost parameterisation, model, threshold. §8 (LLM agent comparison)
is a bounded, cut-first-if-needed extension, not core scope.

**Graduation target:** October 27, 2026.
- GOMP Graduation Application + €100 fee: due **August 27, 2026** (purely administrative,
  independent of thesis content — do this early, don't leave it for the last week of August).
- Thesis Confirmation (Almalaurea questionnaire + PDF upload + **Russo's confirmation in GOMP**,
  all three by the same date): due **October 7, 2026**. This is the real hard deadline governing
  the thesis timeline — not the collection close date. Target internal PDF-ready date ~1 week
  before (e.g. Sept 30) to leave Russo review margin.

## Current state of the code

- `docs/design_freeze.md` — frozen, committed (`c5e1a61`). All four categories fixed; the
  freeze/record distinction (procedure frozen now, final numeric values computed once at
  collection close) is documented and explicit.
- `src/features.py`, `model.py`, `costs.py`, `validation.py`, `injection.py` — all built.
- `notebooks/00`–`05` — built and run end-to-end at POC level (real collected data, but not the
  final collection-close run): injection grid generation, frozen-model training, dose-response
  analysis, H1/H2 hypothesis tests. Outputs in `reports/` (`t11_dose_response.csv`,
  `t14_h1_*`, `t14_h2_*`, `t15_clean_phat_vector.csv`).
- **Key open finding (not a bug, deliberately unfixed):** classes 1 (dropout), 2 (frozen
  counter), 4 (capacity inconsistency) show `flip_rate=0.0` / `delta_cost=0.0` across every
  injected intensity. Root-caused in `docs/model_diagnostics_2026-08-09.md` to the frozen
  model spec: the combined critical-state target (`bikes<=2 OR docks<=2`) is U-shaped in
  occupancy, which a linear model over raw counts can't represent (splitting the target into
  stockout/dockfull alone gives AUC 0.97 vs 0.66 combined). Left unfixed on purpose — changing
  the frozen model in response to which corruption classes show effects would be exactly the
  post-hoc tuning the freeze prohibits. **This needs to be raised with Russo as a finding, not
  silently resolved.**
- Collector has been running continuously since 2026-07-24. Overall poll coverage ~62%.
  Certified continuous gap-free substrate (the segment injection/H2/H3 actually run on) has
  been stuck at **6.2 hours** since 2026-07-30 — 11+ days of further collection added nothing.
- Two confirmed causes of substrate stagnation:
  1. Laptop loses power overnight (not charged/no battery overnight) → multi-hour nightly gap.
     **Confirmed unfixable** — user will not keep it charged overnight. Accepted as a fixed
     constraint for the rest of the window (already stated this way in `design_freeze.md`).
  2. Intermittent DNS resolution failures during active hours, because the collector runs over
     a phone Wi-Fi hotspot and was using the hotspot's own DNS proxy (`172.20.10.1`) — the
     target of this session's fix (see below).

## Files actively edited this session

- **`collector/poll.py`** — only file changed. `RETRY_ATTEMPTS` 2→5, `RETRY_WAIT_S` flat `2` →
  exponential backoff `[2, 4, 8, 16]` (~30s total, still leaves margin inside the 60s poll
  cycle). Applies only to the main `station_status` poll loop in `poll_once()`;
  `fetch_station_information()` untouched. Verified syntax-valid after edit
  (`ast.parse`), no other file imports `poll.py` as a module — it only runs as a standalone
  process via `run_collector.ps1`.

## What was tried, and what failed

1. **Claude tried to change the Wi-Fi adapter's DNS servers directly** via
   `Set-DnsClientServerAddress -InterfaceIndex 2 -ServerAddresses ("1.1.1.1","8.8.8.8")` from
   this session's PowerShell tool. **Failed**: `PermissionDenied: CIM` — the sandboxed session
   has no admin rights, and elevation (UAC) can't be triggered non-interactively. No workaround
   attempted (correctly out of scope for an automated session) — handed off to the user instead.
2. **User ran the same command manually in an elevated PowerShell.** Succeeded — verified via
   `Get-DnsClientServerAddress -InterfaceIndex 2` (now shows `1.1.1.1, 8.8.8.8`, previously
   `172.20.10.1`) and `Resolve-DnsName gbfs.urbansharing.com` (resolves to `35.195.45.71`, no
   errors).
3. **Restarted the collector to pick up the `poll.py` retry-logic change.** The running process
   (PID 16628) was killed; the existing supervisor loop (`run_collector.ps1`, PowerShell PID
   4040, already running since 2026-08-05) auto-relaunched `poll.py` within ~20s (new PID
   15628). Confirmed via fresh rows appearing in `data/metadata.csv` immediately after restart.
   No manual relaunch needed — this worked as expected, no failure here.
4. **Drafted (not sent) an email to Russo** covering: freeze complete (both parts), actively
   collecting to a private GitHub repo, next steps, and a writing-timeline estimate. **Not
   sent** — Gmail MCP in this session was never authenticated (only the OAuth-start tool was
   available, no send capability), and sending mail requires explicit user go-ahead regardless.
   The draft text is in this session's transcript only, not saved to a file.

Net result: both known causes of DNS-driven substrate stagnation are now addressed (public
resolver + more resilient retry). The physical power-loss cause remains and is out of scope by
the user's own choice.

## Next steps, in order

1. **Wait 2–3 days, then re-run `collector/integrity_report.py`** and re-check the certified
   substrate length (currently 6.2h, unchanged since 2026-07-30). If it's still not growing
   after the DNS fix + retry backoff, the DNS proxy wasn't the (sole) cause — the remaining
   daytime `ConnectionError`/`SSLError`/timeout entries in `data/metadata.csv` would need
   inspecting to see if they're genuine hotspot signal drops rather than DNS-specific failures.
2. **Decide the actual collection close date.** Originally planned for 2026-08-28; discussed
   extending toward ~2026-09-20 since the real hard deadline is Oct 7, not Aug 28 — but that
   only pays off if the substrate is actually growing post-fix. Revisit once step 1's answer is
   in.
3. **File the GOMP Graduation Application + pay the €100 fee — before August 27, 2026.**
   Independent of thesis content; don't let it slide into the same week as collection close.
4. **Send (or ask to send) the drafted status email to Russo** — currently just sitting in this
   session's transcript, not saved anywhere. Needs Gmail auth or manual send.
5. **At collection close:** run T34–T37 from the original execution plan — freeze the final
   substrate, retrain on the frozen spec, calibrate τ once by the frozen procedure, run the
   full injection grid against the certified substrate, run the cost sweep, run final H1–H4
   analysis. The pipeline itself is already built and validated at POC level in `notebooks/`
   — this should be a re-run against final data, not new development.
6. **Raise two open items with Russo, not resolve them silently:**
   - The zero-decision-impact finding for classes 1/2/4 (`docs/model_diagnostics_2026-08-09.md`)
     — a genuine model-specification finding, not something to fix inside the frozen model.
   - O4 partial coverage: `station_information` (capacity/lat/lon, needed for Class 4's full
     detector) was only collected from 2026-08-08 onward — the first 15 days of the window
     lack it. Report as partial-period coverage in the results, not full resolution.
7. **Target internal PDF-ready date ~2026-09-30**, a week ahead of the real Oct 7 deadline, to
   leave Russo time to review and confirm in GOMP.
