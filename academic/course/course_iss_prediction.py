"""Course exercise 6 alternative using published ISS orbital elements."""

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import urlopen

import skyfield
from skyfield.api import EarthSatellite, load, wgs84

TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"
LATITUDE, LONGITUDE = 37.78, -122.41


def predict(output):
    with urlopen(TLE_URL, timeout=20) as response:
        raw = response.read(4097)
    if len(raw) > 4096:
        raise ValueError("Unexpected TLE response size")
    name, first, second = raw.decode("ascii").strip().splitlines()
    for index, line in enumerate((first, second), 1):
        if len(line) != 69 or not line.startswith(f"{index} 25544"):
            raise ValueError("Expected an ISS TLE")
        checksum = sum(int(c) if c.isdigit() else int(c == "-") for c in line[:68]) % 10
        if not line[68].isdigit() or checksum != int(line[68]):
            raise ValueError("Invalid TLE checksum")
    now = datetime.now(timezone.utc)
    ts = load.timescale(builtin=True)
    satellite = EarthSatellite(first, second, name.strip(), ts)
    if abs(now - satellite.epoch.utc_datetime()) > timedelta(days=7):
        raise ValueError("TLE epoch is too far from prediction time")
    observer = wgs84.latlon(LATITUDE, LONGITUDE)
    start, stop = ts.from_datetime(now), ts.from_datetime(now + timedelta(days=7))
    times, events = satellite.find_events(observer, start, stop, altitude_degrees=0.0)
    rise = None
    passes = []
    for instant, event in zip(times, events, strict=True):
        if event == 0:
            rise = instant
        elif event == 2 and rise is not None:
            duration = int(round((instant - rise) * 86400))
            passes.append({"rise_utc": rise.utc_iso(), "set_utc": instant.utc_iso(), "duration": duration})
            break
    if not passes:
        raise ValueError("No complete pass in the prediction interval")
    result = {
        "source": TLE_URL,
        "input_sha256": sha256(raw).hexdigest(),
        "tle_epoch_utc": satellite.epoch.utc_iso(),
        "generated_at": now.isoformat(),
        "skyfield": skyfield.__version__,
        "norad_id": 25544,
        "lat": LATITUDE,
        "lon": LONGITUDE,
        "elevation_threshold_degrees": 0.0,
        "method": "Local Skyfield SGP4 geometric pass prediction",
        "response": passes,
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "iss.tle").write_bytes(raw)
    (output / "iss_pass_prediction.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    predict(parser.parse_args().output)
