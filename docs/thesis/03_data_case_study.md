# 3. Data and Case Study

## 3.1 The BikeMi feed

BikeMi is Milan's public docked bike-sharing system (320 stations observed). It
publishes real-time station state (bikes available, docks available, and
station status) through a GBFS feed refreshed at the source roughly every
10 seconds. This project polls it every 60 seconds, which captures anomalies
lasting about two minutes or longer while keeping an unattended collector
sustainable; shorter anomalies are under-observed by construction.

## 3.2 Licensing

The feed is published under the Norwegian Licence for Open Government Data
(NLOD) 2.0 (Norwegian Digitalisation Agency, 2023), the licence named on
BikeMi's open-data page because the feed runs on the platform of Urban Sharing,
a Norwegian provider. NLOD 2.0 permits redistribution and derivative use with
attribution. The open-data page and the licence text were archived before
collection began, and the collector identifies itself with a
`Client-Identifier` header as the feed's documentation requests.

*Attribution.* Contains data under the Norwegian licence for Open Government
Data (NLOD) 2.0 distributed by BikeMi (https://bikemi.com/en/open-data/realtime;
licence: https://data.norge.no/nlod/en/2.0). The information has been changed:
the corrupted datasets of Chapters 4 and 5 were created by the author and are
not BikeMi's data. Weather covariates are hourly temperature and precipitation
for Milan from the Open-Meteo historical archive (Zippenfenig, 2023), used
under CC BY 4.0; because Open-Meteo revises past values, the series used is
frozen in the repository.

## 3.3 Acquisition and coverage

Because a live feed's history cannot be recovered after the fact, the collector was the first component built. Every
60 seconds it fetches the feed, archives the raw payload, and logs acquisition metadata (timestamp, HTTP status, latency, payload size and hash, and station count), whether or not the fetch succeeded. The feed's own `last_updated` field is kept in each archived payload; comparing it with the request time separates staleness at the publisher from a collection failure on this end. A failed fetch is retried up
to four times within the cycle (waits of 2, 4, 8, and 16 seconds), and a fetch
that fails all five attempts is logged as an error.

The analysis window runs from 24 July 2026, 09:46 UTC, to the census of
19 September 2026, 14:22 UTC (last poll 14:12 UTC), 1,372.6 hours in all;
later polls are not used. Two rates describe it. Coverage, the share of polls
that happened at all, was 46.8% (38,503 of the 82,356 a continuous loop would
make). Success, the share of those polls that returned a valid payload, was
59.7% (22,998); the 15,505 failures are logged errors, almost all connection
failures on a mobile hotspot. After discarding unreadable payloads and polls in
which the feed had not refreshed, 22,986 distinct feed states remain:
7,352,042 station-level observations.

## 3.4 Known limitations of the collection

Two causes explain most gaps, both traced through the logs. The collector's
laptop suspends overnight when its battery drains (confirmed in the system's power-event logs), and the hotspot's DNS proxy produced
intermittent lookup failures, resolved with a public resolver and the retry
schedule above. The first cause leaves the early morning almost unobserved: hours 05:00–09:00 each hold under 1% of observations, so hourly patterns are interpreted only for about 10:00 to 04:00 (§5.2). Two smaller gaps are recorded rather
than hidden: station capacity was collected only from
8 August, which limits the Class 4 detector (§4.4), and ten snapshots written
incompletely during interruptions are excluded.

## 3.5 The certified injection substrate

The collection is a sequence of stretches separated by gaps that the collector
causes and that are not random. Injecting faults into it directly could place
an anomaly inside a gap and measure nothing, and a lag or two-hour label
computed across a gap would combine readings hours apart. Faults are therefore
injected only into continuous stretches, each treated as an independent period
that no lag or forecast horizon crosses.

A period is a maximal run of polls with no gap over 120 seconds that lasts at
least 2.25 hours, the shortest run able to produce one complete example: a row
with a full 15-minute lag window (§4.3) and a valid label two hours ahead.
Using only the single longest run (8.5 hours, 9 August) was rejected: one part of one day would
under-represent the near-empty and near-full situations that rebalancing
exists for.

Each period is certified with the detectors of §4.1. Implausible jumps are
excluded, since that detector is precise enough to treat a flag as a fault.
Frozen-counter flags are kept: over a 60-minute window the detector flags
1,560,435 observations, a third of the clean substrate, because many stations
genuinely do not change for an hour, so a flag means "unchanged", not
"broken".

Of the 211 continuous runs, 62 qualify, spanning 36 days (UTC) and 251.5 hours
(4.06 hours on average, 2.27 to 8.53). The 149 shorter runs (137.4 hours) are
excluded because they cannot yield a single complete example, not because they
were judged unclean. The periods hold 4,734,225 observations; 72,891 (1.5%)
are excluded as jumps, leaving 4,661,334 clean observations, of which 879,008
(18.9%) are critical, forming 9,682 critical episodes at 319 of the 320
stations. Only 1,953,928 clean observations (42%) are forecastable: the first
15 minutes of each period lack a lag history and the last two hours lack a
label. Among forecastable rows, 19.1% are labelled critical. Per-period figures are listed in the repository (Appendix A); the census was fixed before any experiment was run on it.
