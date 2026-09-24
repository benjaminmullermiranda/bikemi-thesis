# 3. Data and Case Study

## 3.1 The BikeMi feed

BikeMi is Milan's public docked bike-sharing system (320 stations observed). It
publishes real-time station state (bikes available, docks available,
installed/renting/returning status) through a GBFS feed, refreshed at the source
roughly every 10 seconds. This project polls it every 60 seconds: frequent
enough to reliably capture anomalies lasting about two minutes or longer, while
keeping an unattended, long-running collector sustainable. Sub-two-minute
transients remain under-observed by construction.

## 3.2 Licensing

The feed is published under the Norwegian Licence for Open Government Data
(NLOD) 2.0, which is the licence BikeMi's own open-data page names even though
BikeMi is an Italian system; the operator's platform provider is Norwegian, and
the licence travels with the platform. NLOD 2.0 permits redistribution and
derivative use with attribution. Before collection began, per the supervisor's
instruction, this was verified by archiving BikeMi's open-data page and the
licence text itself (`docs/evidence/`) and documenting the `Client-Identifier`
header used to identify this project as a sanctioned API consumer, not a
scraper.

<!-- TODO: the required NLOD attribution string still needs to be drafted and
     placed where the final thesis will actually carry it. There is no
     Appendix in this thesis's structure (Contents, §00); either add one for
     the licence attribution and the modification-label text quoted in §4.2,
     or place the attribution here in §3.2 directly. Decide before submission. -->

## 3.3 Acquisition architecture

Because a live feed's history cannot be recovered retroactively, the collector
(`collector/poll.py`) was built and started before any other part of the
project. It runs a continuous 60-second loop: fetch, archive the raw payload as
gzip JSON, and log acquisition metadata (timestamp, HTTP status, latency,
payload size and hash, feed-declared `last_updated`, and station count),
independent of whether the fetch succeeded. Recording the feed's own
`last_updated` alongside the collector's request time is what keeps feed-level
staleness (the publisher not refreshing) distinguishable from collection failure
(this project not reaching the feed).

A single in-cycle retry recovers transient network blips without masking a real
outage; a failure that survives both attempts is logged as before. Because the
GitHub repository is version history, not a backup, the raw archive is
additionally copied off-machine on a schedule.

## 3.4 Collection window and coverage

The window opened on 24 July 2026 at 09:46 UTC and closed on 19 September 2026
at 14:22 UTC, spanning 1,372.6 hours (57.2 days). Within it the collector logged
38,503 of the 82,356 poll attempts a perfectly uninterrupted 60-second loop would
have made (46.8%), and 22,998 of those attempts returned a valid feed payload
(59.7% of attempts logged). Coverage and success rate are reported separately
because an attempted-and-failed poll still tells the collector something a
genuine gap does not: the 15,505 failures are logged errors, almost all
connection failures on the mobile-hotspot link (§3.5), not silent absences.
After discarding polls whose payload was unreadable and polls in which the feed
had not refreshed since the previous request, 22,986 distinct feed states
remain, giving 7,352,042 station-level observations across 320 stations.

## 3.5 Known limitations

Two causes account for most gaps, both diagnosed from collector logs. First, the
collector's laptop is not kept on power overnight and suspends when its battery
drains. This was confirmed via Windows power-event logs and is accepted as a
fixed constraint for the rest of the window. Second, intermittent DNS failures
on the mobile-hotspot connection were traced to the hotspot's own DNS proxy and
mitigated with a public resolver and a wider retry backoff (2s→16s).

Class 4's full detector (§4.1) needs the feed's `station_information` endpoint
(capacity, coordinates), only collected from 8 August onward, reported as
partial-period coverage, not a resolved gap. Ten archived snapshots were written
incompletely when the collector was interrupted mid-write and cannot be parsed;
they are excluded from analysis and counted here, not silently dropped.

The third limitation is the one that shapes the experimental design of §3.6: the
overnight power loss means the dataset covers daytime periods only. Nothing in
this thesis speaks to night-time system behaviour, and the results should not be
read as if it did.

## 3.6 The certified injection substrate

Because collection gaps are collector-side, not random, injecting faults into
the full, gappy collection risks landing an anomaly inside a real gap and
measuring nothing. A first version of the substrate kept only the single
**longest continuous run with no gap over 120 seconds** in the whole
collection: 8.5 hours (9 August, 10:15-18:46 UTC), unchanged for three weeks
because the dominant remaining gap cause, overnight power loss (§3.5), could
not be fixed. The supervisor judged one part of one day too narrow a basis for
the experiments, in particular too likely to under-represent critical
situations (near-empty or near-full stations), and instructed using every
day's valid stretch instead, each day kept as its own independent continuous
period so that no lag or forecast horizon crosses the gap between two days
(email, 14 September 2026).

The substrate is therefore every maximal run of polls with no gap over 120
seconds that is also long enough to yield at least one row with a complete
15-minute lag window and a valid 2-hour label (2.25 hours at the 60-second poll
cadence), certified per period by the same per-class detectors used for the
original single-segment substrate (§4.1): implausible jumps are excluded from
each period, and frozen-counter rows are counted but kept, since the detector's
natural false-positive rate is high enough (roughly 45% on earlier checks) that
blind exclusion would be too aggressive without first resolving that
calibration question. Of 211 continuous runs
found across the closed collection, 62 qualify, spanning 36 distinct days
(21 of them contributing more than one period, split by a daytime gap such as a
lunchtime connectivity drop). Retained periods total 251.5 hours: 4.06 hours on
average, ranging from 2.27 to 8.53 hours (the old single-segment figure is now
simply the longest of the 62). The 149 shorter runs, 137.4 hours combined, are
excluded because a period below the minimum cannot contribute a single
complete training example, not because they were judged unclean.

Across the 62 periods: 4,734,225 station-observations, 72,891 excluded as
implausible jumps, 1,953,928 forecastable rows (complete lag features and a
valid label), and 879,008 critical-state observations (18.9% of clean rows),
representing 9,682 distinct critical episodes (a station's continuous run of
critical state, not double-counted per poll) across 319 of the 320 stations,
for 15,167 critical station-hours (879,008 critical polls at the observed
dwell time between consecutive polls, capped at the 120-second gap threshold so
no boundary row over-claims; the naive count/60 estimate is 14,650 hours,
consistent within 3.5%). Full per-period figures are in
`reports/t38_daily_periods.csv`; the summary numbers above are in
`reports/t38_substrate_summary.json`, generated by
`notebooks/07_multiday_substrate.py`.
