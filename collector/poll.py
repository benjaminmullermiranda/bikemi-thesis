"""BikeMi GBFS collector - polls station_status every 60 s."""
import requests, gzip, time, csv, hashlib
from pathlib import Path
from datetime import datetime, timezone

URL = "https://gbfs.urbansharing.com/bikemi.com/station_status.json"
STATION_INFO_URL = "https://gbfs.urbansharing.com/bikemi.com/station_information.json"
HEADERS = {"Client-Identifier": "unicas-benjamin-thesis"}
POLL_SECONDS = 60

BASE = Path(__file__).resolve().parents[1]
RAW_DIR = BASE / "data" / "raw"
STATIC_DIR = BASE / "data" / "static"
META = BASE / "data" / "metadata.csv"
RAW_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)


def fetch_station_information():
    """station_information (capacity, lat/lon, name) - GBFS static data, changes
    rarely. Never collected before 2026-08-08 (O4): this backfills what's left of
    the window rather than nothing. One snapshot per calendar day (UTC) is plenty;
    re-fetching every poll would be pointless for data that doesn't change minute
    to minute. Failures here are non-fatal to the main station_status loop -
    a missed day just means one fewer static snapshot, not lost time-series data."""
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out = STATIC_DIR / f"station_information_{day}.json.gz"
    if out.exists():
        return
    try:
        r = requests.get(STATION_INFO_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        with gzip.open(out, "wt", encoding="utf-8") as f:
            f.write(r.text)
        print(f"station_information snapshot saved: {out.name}", flush=True)
    except Exception as e:
        print(f"station_information fetch FAILED ({day}): {type(e).__name__}: {e}", flush=True)

RETRY_ATTEMPTS = 2   # 1 initial + 1 retry, not more - a real outage should still show
RETRY_WAIT_S = 2      # up as a logged ERROR, not be hidden by looping forever

def poll_once():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    t0 = time.time()
    last_exc = None
    r = None
    # 2026-08-08: collector runs on a phone hotspot - most failures are single-poll
    # DNS/connect blips (error latency ~single-digit ms, i.e. instant failure, not a
    # timeout), not real outages. A real outage still exhausts both attempts and logs
    # ERROR exactly as before; this only recovers the transient case.
    for attempt in range(RETRY_ATTEMPTS):
        try:
            r = requests.get(URL, headers=HEADERS, timeout=20)
            last_exc = None
            break
        except Exception as e:
            last_exc = e
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_WAIT_S)
    try:
        if last_exc is not None:
            raise last_exc
        latency = round((time.time() - t0) * 1000)
        with gzip.open(RAW_DIR / f"{ts}.json.gz", "wt", encoding="utf-8") as f:
            f.write(r.text)
        n_st = len(r.json()["data"]["stations"])
        row = [ts, r.status_code, latency, len(r.content), n_st,
               hashlib.sha256(r.content).hexdigest()[:16]]
    except Exception as e:
        # full error text + exception type: needed to tell DNS / timeout /
        # refused / SSL apart. Truncating this was a design mistake.
        latency = round((time.time() - t0) * 1000)
        row = [ts, "ERROR", latency, "", "",
               f"{type(e).__name__}: {str(e)}".replace("\n", " ")[:500]]
    try:
        with open(META, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)
    except Exception as e:
        print(f"METADATA WRITE FAILED {ts}: {e}", flush=True)
    print(row, flush=True)

if __name__ == "__main__":
    while True:
        fetch_station_information()
        poll_once()
        time.sleep(POLL_SECONDS)
