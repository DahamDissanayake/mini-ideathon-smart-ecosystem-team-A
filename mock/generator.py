#!/usr/bin/env python3
"""Mock telemetry generator for LetGo Band.

There is no hardware yet, and there is no labelled child activity dataset, so
this script stands in for both. It simulates N bands across a configurable day
and emits the two payload types defined in schema/telemetry.schema.json: band
to gateway feature windows, and the gateway to cloud daily summary.

We use it for two things. It lets the gateway pipeline be developed and tested
without bands, and it reproduces the failure paths we need to demonstrate:
radio dropout, strap breach, early power-off, and prolonged stillness.

Every record is validated against the schema before it is written. The script
exits non-zero if any record fails, because a generator that quietly emits
invalid data is worse than no generator.

What this models faithfully:
  - The two-condition attendance rule. A band clips, and only becomes PRESENT
    once wear-consistent motion appears inside the motion confirmation window.
  - Strap events sent unbatched, ahead of queued feature windows.
  - Store and forward. Windows produced during a radio dropout are held on the
    band and replayed after the link returns, so the gateway sees them late
    rather than never. Records are written in arrival order, so a dropout looks
    like a gap followed by an out-of-order burst.
  - Data minimisation. The daily summary is built from the windows and then
    validated against a schema with additionalProperties false, so a leaked
    field fails the run.

What this does not model:
  - The Movement Classifier. Activity classes here come from a scripted daily
    routine plus noise. They are not inferred from the features, so the
    features and the class agree by construction in a way real data will not.
  - The Safeguard. Nothing here is suppressed by a confidence floor, because
    the floor cannot be set until labelled data exists.
  - BLE, encryption, and real HMAC keys. Signatures are computed with a fixed
    demo key so that the field is well formed. They authenticate nothing.

Usage:
    python -m pip install -r mock/requirements.txt
    python mock/generator.py --bands 12 --date 2026-09-03 --seed 42 --out out/
    python mock/generator.py --seed 42 --signal-loss
    python mock/generator.py --seed 42 --strap-breach --prolonged-stillness

See OPEN-QUESTIONS.md for the values this generator has to invent because the
design does not settle them yet.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    sys.exit(
        "jsonschema is required. Run: python -m pip install -r mock/requirements.txt"
    )

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "telemetry.schema.json"

SCHEMA_VERSION = "1.0"
FW_VERSION = "0.4.1"
MODEL_VERSION = "act-cls-1.2"

# Demo key only. Real deployments hold a per-device key in the ESP32-S3 secure
# element and never in a source file.
DEMO_KEY = b"letgo-band-mock-generator-not-a-real-key"

# Placeholder activity vocabulary. The real list comes with the labelled
# dataset, see OPEN-QUESTIONS.md question 2.6.
ACTIVITY_CLASSES = ("still", "sitting_active", "walking", "running", "climbing")

# Which classes count towards active_minutes, see OPEN-QUESTIONS.md 2.3.
ACTIVE_CLASSES = frozenset({"walking", "running", "climbing"})

# Feature profile per class: acceleration magnitude, variance, cadence, posture.
CLASS_PROFILE = {
    "still": (1.00, 0.02, 0, "supine"),
    "sitting_active": (1.06, 0.18, 0, "seated"),
    "walking": (1.28, 0.62, 78, "upright"),
    "running": (1.72, 1.65, 148, "upright"),
    "climbing": (1.44, 1.10, 34, "upright"),
}

# A scripted day. Each block is (label, start, end, class weights).
DAY_BLOCKS = (
    ("arrival", time(8, 30), time(9, 15), {"walking": 4, "sitting_active": 3, "still": 1}),
    ("free_play", time(9, 15), time(10, 30), {"walking": 4, "running": 3, "climbing": 2, "sitting_active": 2}),
    ("fitness", time(10, 30), time(11, 15), {"running": 5, "walking": 3, "climbing": 3, "sitting_active": 1}),
    ("outdoor", time(11, 15), time(12, 0), {"walking": 4, "running": 3, "climbing": 3, "sitting_active": 1}),
    ("lunch", time(12, 0), time(12, 45), {"sitting_active": 6, "still": 3, "walking": 1}),
    ("nap", time(12, 45), time(14, 15), {"still": 9, "sitting_active": 1}),
    ("quiet_play", time(14, 15), time(15, 30), {"sitting_active": 5, "walking": 3, "climbing": 1, "still": 2}),
    ("pickup", time(15, 30), time(16, 30), {"walking": 4, "sitting_active": 3, "still": 2}),
)

FITNESS_BLOCK = "fitness"

SCENARIOS = ("signal-loss", "strap-breach", "early-poweroff", "prolonged-stillness")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def iso_z(dt: datetime) -> str:
    """RFC 3339 timestamp with a Z suffix, whole seconds."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hms_z(dt: datetime) -> str:
    """Time of day with a Z suffix, as the cloud summary carries it."""
    return dt.astimezone(timezone.utc).strftime("%H:%M:%SZ")


def sign(payload: dict) -> str:
    """Signature over the payload with every field except sig itself."""
    body = json.dumps(
        {k: v for k, v in payload.items() if k != "sig"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(DEMO_KEY, body, hashlib.sha256).hexdigest()


def block_for(t: time) -> tuple[str, dict]:
    """The scripted day block covering a time of day."""
    for label, start, end, weights in DAY_BLOCKS:
        if start <= t < end:
            return label, weights
    return "unstructured", {"sitting_active": 3, "walking": 2, "still": 2}


def variety_index(counts: dict[str, int]) -> float:
    """Normalised Shannon entropy over the classes seen in a session.

    Placeholder. The real formula is not specified, see OPEN-QUESTIONS.md 2.2.
    """
    total = sum(counts.values())
    if total == 0 or len(ACTIVITY_CLASSES) < 2:
        return 0.0
    entropy = 0.0
    for n in counts.values():
        if n <= 0:
            continue
        p = n / total
        entropy -= p * math.log(p)
    return round(min(entropy / math.log(len(ACTIVITY_CLASSES)), 1.0), 2)


# ---------------------------------------------------------------------------
# simulation
# ---------------------------------------------------------------------------


@dataclass
class Band:
    index: int
    device_id: str
    child_ref: str
    scenario: str | None = None
    seq: int = 0
    battery: float = 0.0
    windows: list = field(default_factory=list)
    check_in: datetime | None = None
    check_out: datetime | None = None
    anomalies: int = 0
    class_counts: dict = field(default_factory=dict)
    active_windows: int = 0
    fitness_active: bool = False


class DaySim:
    """One facility, one day, N bands."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.rng = random.Random(args.seed)
        self.day = Date.fromisoformat(args.date)
        self.window = timedelta(seconds=args.window_s)
        self.day_start = self._at(args.day_start)
        self.day_end = self._at(args.day_end)
        self.bands = self._make_bands()

    def _at(self, hhmm: str) -> datetime:
        hh, mm = (int(part) for part in hhmm.split(":"))
        return datetime.combine(self.day, time(hh, mm), tzinfo=timezone.utc)

    def _make_bands(self) -> list[Band]:
        bands = [
            Band(
                index=i,
                device_id=f"lgb-{140 + i:04d}",
                child_ref=f"enr-{8890 + i:04d}",
                battery=self.rng.uniform(72.0, 96.0),
            )
            for i in range(self.args.bands)
        ]
        self._assign_scenarios(bands)
        return bands

    def _assign_scenarios(self, bands: list[Band]) -> None:
        """Hand each requested scenario to a distinct band, deterministically."""
        wanted: list[str] = []
        for name in SCENARIOS:
            wanted.extend([name] * getattr(self.args, name.replace("-", "_")))
        if not wanted:
            return
        if len(wanted) > len(bands):
            sys.exit(
                f"asked for {len(wanted)} scenario injections across "
                f"{len(bands)} bands. Raise --bands."
            )
        chosen = self.rng.sample(range(len(bands)), len(wanted))
        for band_index, scenario in zip(chosen, wanted):
            bands[band_index].scenario = scenario

    # -- record builders ---------------------------------------------------

    def _record(
        self,
        band: Band,
        ts: datetime,
        *,
        clip_state: str,
        strap_closed: bool,
        attendance_state: str,
        strap_event: str | None,
        activity_class: str,
    ) -> dict:
        mean, var, cadence, posture = CLASS_PROFILE[activity_class]
        jitter = self.rng.uniform(0.88, 1.12)
        steps = int(cadence * self.args.window_s / 60.0 * jitter)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "device_id": band.device_id,
            "child_ref": band.child_ref,
            "ts": iso_z(ts),
            "tier": "band",
            "window_s": self.args.window_s,
            "strap_closed": strap_closed,
            "clip_state": clip_state,
            "strap_event": strap_event,
            "attendance_state": attendance_state,
            "activity_features": {
                "mean_accel_mag": round(mean * jitter, 2),
                "accel_variance": round(var * jitter, 2),
                "step_count": steps,
                "cadence_spm": int(cadence * jitter),
                "posture_est": posture,
            },
            "battery_pct": int(max(0.0, min(100.0, band.battery))),
            "rssi_dbm": int(self.rng.gauss(-62, 7)),
            "confidence": round(self.rng.uniform(0.71, 0.98), 2),
            "fw_version": FW_VERSION,
            "model_version": MODEL_VERSION,
            "seq": band.seq,
            "sig": "",
        }
        payload["rssi_dbm"] = max(-127, min(0, payload["rssi_dbm"]))
        payload["sig"] = sign(payload)
        band.seq += 1
        return payload

    def _tally(self, band: Band, ts: datetime, activity_class: str) -> None:
        band.class_counts[activity_class] = band.class_counts.get(activity_class, 0) + 1
        if activity_class in ACTIVE_CLASSES:
            band.active_windows += 1
            if block_for(ts.time())[0] == FITNESS_BLOCK:
                band.fitness_active = True

    # -- the day -----------------------------------------------------------

    def run(self) -> tuple[list[dict], list[dict]]:
        windows: list[dict] = []
        for band in self.bands:
            windows.extend(self._run_band(band))
        summaries = [self._summarise(band) for band in self.bands]
        return windows, [s for s in summaries if s is not None]

    def _run_band(self, band: Band) -> list[dict]:
        out: list[dict] = []
        clip_at = self.day_start + timedelta(minutes=self.rng.uniform(0, 25))
        release_at = self.day_end - timedelta(minutes=self.rng.uniform(0, 35))

        # Scenario timings. The first three sit in the middle of the session.
        mid = clip_at + (release_at - clip_at) * 0.45
        gap_start = mid
        gap_end = mid + timedelta(minutes=self.args.signal_loss_minutes)
        breach_at = mid
        poweroff_at = mid
        # Stillness goes in the morning free play block instead. Stillness
        # during the nap block is normal and would demonstrate nothing.
        still_start = clip_at + (release_at - clip_at) * 0.15
        still_end = still_start + timedelta(minutes=self.args.stillness_minutes)

        # The band buffers windows produced while the link is down, and replays
        # them in order once it returns.
        buffered: list[dict] = []
        clipped = True
        confirmed = False
        breached = False
        reclip_at: datetime | None = None
        # Motion confirmation is measured from the most recent clip, so a
        # re-clip after a breach has to earn PRESENT again.
        clip_ref = clip_at

        ts = clip_at + self.window
        while ts <= release_at:
            band.battery -= self.args.window_s / 3600.0 * 0.9

            if band.scenario == "early-poweroff" and ts >= poweroff_at:
                break

            if band.scenario == "strap-breach" and not breached and ts >= breach_at:
                # Strap events are unbatched and jump the queue, so this record
                # is emitted immediately even though windows are queued.
                event = self.rng.choice(["BREAKAWAY", "CUT"])
                out.append(
                    self._record(
                        band,
                        ts,
                        clip_state=event,
                        strap_closed=False,
                        attendance_state="STRAP_BREACH",
                        strap_event=event,
                        activity_class="still",
                    )
                )
                band.anomalies += 1
                breached = True
                clipped = False
                confirmed = False
                reclip_at = ts + timedelta(minutes=self.args.reclip_minutes)
                ts += self.window
                continue

            if not clipped:
                if reclip_at is not None and ts >= reclip_at:
                    clipped = True
                    clip_ref = ts
                    out.append(
                        self._record(
                            band,
                            ts,
                            clip_state="CLIPPED",
                            strap_closed=True,
                            attendance_state="CLIP_PENDING",
                            strap_event=None,
                            activity_class="sitting_active",
                        )
                    )
                    ts += self.window
                    continue
                out.append(
                    self._record(
                        band,
                        ts,
                        clip_state="UNCLIPPED",
                        strap_closed=False,
                        attendance_state="STRAP_BREACH",
                        strap_event=None,
                        activity_class="still",
                    )
                )
                ts += self.window
                continue

            # Attendance: circuit closed is not enough. Motion has to confirm.
            elapsed = (ts - clip_ref).total_seconds()
            if not confirmed:
                if elapsed <= self.args.motion_confirmation_window:
                    state = "CLIP_PENDING"
                else:
                    state = "PRESENT"
                    confirmed = True
                    band.check_in = band.check_in or ts
            else:
                state = "PRESENT"

            if band.scenario == "prolonged-stillness" and still_start <= ts < still_end:
                activity_class = "still"
            else:
                label, weights = block_for(ts.time())
                classes = list(weights)
                activity_class = self.rng.choices(
                    classes, weights=[weights[c] for c in classes], k=1
                )[0]

            record = self._record(
                band,
                ts,
                clip_state="CLIPPED",
                strap_closed=True,
                attendance_state=state,
                strap_event=None,
                activity_class=activity_class,
            )
            if state == "PRESENT":
                self._tally(band, ts, activity_class)

            if band.scenario == "signal-loss" and gap_start <= ts < gap_end:
                if not buffered:
                    band.anomalies += 1
                buffered.append(record)
            else:
                out.append(record)
                if buffered:
                    # Link is back. The band sends the live window first and
                    # then drains its backlog, so replayed windows arrive after
                    # newer ones. Records are in arrival order, so a dropout
                    # shows up as a gap followed by an out-of-order burst.
                    out.extend(buffered)
                    buffered = []

            ts += self.window

        if band.scenario == "prolonged-stillness":
            band.anomalies += 1
        if band.scenario == "early-poweroff":
            band.anomalies += 1
            out.extend(buffered)
            return out

        out.extend(buffered)

        # Normal end of day: staff tool release, attributed to a badge.
        release_record = self._record(
            band,
            release_at,
            clip_state="RELEASED_BY_TOOL",
            strap_closed=False,
            attendance_state="CHECKED_OUT",
            strap_event="RELEASED_BY_TOOL",
            activity_class="still",
        )
        out.append(release_record)
        band.check_out = release_at
        return out

    def _summarise(self, band: Band) -> dict | None:
        if band.check_in is None:
            print(
                f"note: {band.device_id} never confirmed attendance, no summary emitted",
                file=sys.stderr,
            )
            return None
        active_minutes = int(band.active_windows * self.args.window_s / 60)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "facility_id": self.args.facility_id,
            "child_ref": band.child_ref,
            "date": self.day.isoformat(),
            "check_in": hms_z(band.check_in),
            "check_out": hms_z(band.check_out) if band.check_out else None,
            "active_minutes": active_minutes,
            "movement_variety_index": variety_index(band.class_counts),
            "fitness_session_participation": band.fitness_active,
            "anomaly_events_resolved": band.anomalies,
            "gateway_id": self.args.gateway_id,
            "seq": 4470 + band.index,
            "sig": "",
        }
        payload["sig"] = sign(payload)
        return payload


# ---------------------------------------------------------------------------
# validation and output
# ---------------------------------------------------------------------------


def validator_for(definition: str) -> Draft202012Validator:
    with SCHEMA_PATH.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    return Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": f"#/$defs/{definition}",
        }
    )


def validate_all(records: list[dict], definition: str) -> int:
    validator = validator_for(definition)
    failures = 0
    for record in records:
        for error in validator.iter_errors(record):
            failures += 1
            path = "/".join(str(p) for p in error.absolute_path) or "<root>"
            print(
                f"schema violation in {definition} at {path}: {error.message}",
                file=sys.stderr,
            )
    return failures


def write_jsonl(records: list[dict], destination: Path | None, label: str) -> None:
    lines = [json.dumps(record, separators=(",", ":")) for record in records]
    if destination is None:
        for line in lines:
            print(line)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{label}: {len(records)} records -> {destination}", file=sys.stderr)


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate LetGo Band telemetry for a facility day.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--bands", type=int, default=12, help="number of bands")
    parser.add_argument("--date", default="2026-09-03", help="day to simulate, YYYY-MM-DD")
    parser.add_argument("--seed", type=int, default=None, help="seed, for a reproducible run")
    parser.add_argument("--out", type=Path, default=None, help="output directory, stdout if omitted")
    parser.add_argument("--day-start", default="08:30", help="first clip time, HH:MM")
    parser.add_argument("--day-end", default="16:30", help="last release time, HH:MM")
    parser.add_argument("--window-s", type=int, default=30, help="feature window length")
    parser.add_argument("--facility-id", default="fac-004")
    parser.add_argument("--gateway-id", default="gw-004-a")

    scenarios = parser.add_argument_group(
        "scenario injection",
        "each flag affects one band by default, or N bands if given a number",
    )
    scenarios.add_argument(
        "--signal-loss", nargs="?", const=1, type=int, default=0,
        help="band goes quiet mid-session, then replays its buffer",
    )
    scenarios.add_argument(
        "--strap-breach", nargs="?", const=1, type=int, default=0,
        help="breakaway or cut mid-session, then a re-clip",
    )
    scenarios.add_argument(
        "--early-poweroff", nargs="?", const=1, type=int, default=0,
        help="band stops reporting before the staff release",
    )
    scenarios.add_argument(
        "--prolonged-stillness", nargs="?", const=1, type=int, default=0,
        help="clipped and worn, but not moving for an extended run",
    )

    tuning = parser.add_argument_group(
        "scenario tuning",
        "values the design does not settle, see OPEN-QUESTIONS.md",
    )
    tuning.add_argument("--signal-loss-minutes", type=float, default=14.0)
    tuning.add_argument("--stillness-minutes", type=float, default=42.0)
    tuning.add_argument("--reclip-minutes", type=float, default=6.0)
    tuning.add_argument(
        "--motion-confirmation-window", type=float, default=120.0,
        help="seconds allowed between clip and wear-consistent motion",
    )

    args = parser.parse_args(argv)
    if args.bands < 1:
        parser.error("--bands must be at least 1")
    if args.window_s < 1:
        parser.error("--window-s must be at least 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sim = DaySim(args)
    windows, summaries = sim.run()

    failures = validate_all(windows, "band_window")
    failures += validate_all(summaries, "cloud_daily_summary")
    if failures:
        print(f"{failures} records failed schema validation, nothing written", file=sys.stderr)
        return 1

    if args.out is None:
        write_jsonl(windows, None, "band windows")
        write_jsonl(summaries, None, "daily summaries")
    else:
        write_jsonl(windows, args.out / "band_windows.jsonl", "band windows")
        write_jsonl(summaries, args.out / "daily_summaries.jsonl", "daily summaries")

    injected = [(b.device_id, b.scenario) for b in sim.bands if b.scenario]
    for device_id, scenario in injected:
        print(f"injected {scenario} on {device_id}", file=sys.stderr)
    print(
        f"{len(windows)} band windows, {len(summaries)} daily summaries, all valid",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
