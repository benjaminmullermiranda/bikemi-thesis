"""BikeMi GBFS collector - polls station_status every 60 s.

Writes: data/raw/<UTC timestamp>.json.gz   (immutable raw archive)
        data/metadata.csv                  (acquisition metadata, one row per poll)
Paths resolve relative to the repo root, so it works from any directory:
    python collector/poll.py
"""
import requests, gzip, time, csv, hashlib
from pathlib import Path
from datetime import datetime, timezone

URL = "https://gbfs.urbansharing.com/bikemi.com/station_status.json"
HEADERS = {"Client-Identifier": "unicas-benjamin-thesis"}  # required by feed terms
POLL_SECONDS = 60

BASE = Path(__file__).resolve().parents[1]
RAW_DIR = BASE / "data" / "raw"
META = BASE / "data" / "metadata.csv"
RAW_DIR.mkdir(parents=True, exist_ok=True)

def poll_once():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    t0 = time.time()
    try:
        r = requests.get(URL, headers=HEADERS, timeout=20)
        latency = round((time.time() - t0) * 1000)
        with gzip.open(RAW_DIR / f"{ts}.json.gz", "wt", encoding="utf-8") as f:
            f.write(r.text)                      # raw response, exactly as received
        n_st = len(r.json()["data"]["stations"])
        row = [ts, r.status_code, latency, len(r.content), n_st,
               hashlib.sha256(r.content).hexdigest()[:16]]
    except Exception as e:
        row = [ts, "ERROR", "", "", "", str(e)[:80]]  # failures are DATA (RQ1), not crashes
    with open(META, "a", newline="") as f:
        csv.writer(f).writerow(row)
    print(row, flush=True)

if __name__ == "__main__":
    while True:
        poll_once()
        time.sleep(POLL_SECONDS)
