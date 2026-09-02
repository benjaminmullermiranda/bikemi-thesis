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

The feed is published under Italy's NLOD 2.0 open-data licence, which permits
redistribution and derivative use with attribution. Before collection began, per
the supervisor's instruction, this was verified by archiving BikeMi's open-data
page and the licence text itself (`docs/evidence/`), recording the required
attribution string for the appendix, and documenting the `Client-Identifier`
header used to identify this project as a sanctioned API consumer, not a
scraper.

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

The window opened 24 July 2026 and continues to the collection-close date. As of
the latest check: 653.1 hours running, 22,609 of ~38,543 expected polls logged
(58.7% coverage), of which 14,270 (63.1%) succeeded; the rest are logged
errors (mostly connection failures), not silent gaps. Coverage and success rate
are reported separately because an attempted-and-failed poll still tells the
collector something a genuine gap does not.

## 3.5 Known limitations

Two causes account for most gaps, both diagnosed from collector logs. First, the
collector's laptop is not kept on power overnight and suspends when its battery
drains. This was confirmed via Windows power-event logs and is accepted as a
fixed constraint for the rest of the window. Second, intermittent DNS failures
on the mobile-hotspot connection were traced to the hotspot's own DNS proxy and
mitigated with a public resolver and a wider retry backoff (2s→16s).

Class 4's full detector (§4.1) needs the feed's `station_information` endpoint
(capacity, coordinates), only collected from 8 August onward, reported as
partial-period coverage, not a resolved gap. Two corrupted raw snapshots are
excluded from analysis and counted, not silently dropped.

## 3.6 The certified injection substrate

Because collection gaps are collector-side, not random, injecting faults into
the full, gappy collection risks landing an anomaly inside a real gap and
measuring nothing. The injection substrate is instead the **longest continuous
run with no gap over 120 seconds** in the collection: the project's own data,
not an external dataset. This is an interim, monitored figure: 8.5 hours
(9 August, 10:15–18:46 UTC), unchanged for over three weeks despite continued
collection and the mitigations in §3.5. The remaining dominant cause (overnight
power loss, §3.5) was not addressable, so no further growth is expected. It will
be recomputed once, by the same procedure, at collection close, and that final
figure, not this interim one, is what the results chapter uses.
