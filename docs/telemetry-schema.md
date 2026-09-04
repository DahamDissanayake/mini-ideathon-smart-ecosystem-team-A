# Telemetry schema

Two payload types cross a tier boundary and get stored. Everything else stays
where it was computed. The machine-readable version of both is
[`../schema/telemetry.schema.json`](../schema/telemetry.schema.json), and
[`../mock/generator.py`](../mock/generator.py) emits records that validate
against it.

This file is the **what**. The **how** is in
[`telemetry-pipeline.md`](telemetry-pipeline.md): the hops, the anchor
observation envelope that carries a band advertisement to the gateway, the nine
ingest stages, delivery guarantees, buffering, and health telemetry. What is and
is not backed up is in [`backup-recovery.md`](backup-recovery.md).

---

## 1. Band to gateway, per feature window

**This is the gateway-side representation, after decoding.** The band broadcasts
a 26-byte binary advertisement, laid out in [`../spec.md`](../spec.md) section
9, which an anchor forwards to the gateway. The JSON below is what the gateway
holds once it has verified the authentication tag, resolved the rotating
identifier to a band, deduplicated the copies several anchors forwarded, and
decoded the bytes. No JSON is ever transmitted by a band.

One per `window_s` (currently 30 s). Strap events are advertised unbatched and
ahead of any queued window.

```json
{
  "schema_version": "1.0",
  "device_id": "lgb-0142",
  "child_ref": "enr-8891",
  "ts": "2026-09-03T09:12:44Z",
  "tier": "band",
  "window_s": 30,
  "strap_closed": true,
  "clip_state": "CLIPPED",
  "strap_event": null,
  "attendance_state": "PRESENT",
  "activity_features": {
    "mean_accel_mag": 1.42,
    "accel_variance": 0.87,
    "step_count": 41,
    "cadence_spm": 82,
    "posture_est": "upright"
  },
  "battery_pct": 74,
  "rssi_dbm": -61,
  "confidence": 0.94,
  "fw_version": "0.4.1",
  "model_version": "act-cls-1.2",
  "seq": 10428,
  "sig": "<hmac-sha256>"
}
```

| Field | Meaning |
|---|---|
| `schema_version` | Payload contract version. Bumped on any breaking field change. |
| `device_id` | Band identity. Facility-local, never leaves the gateway. |
| `child_ref` | Pseudonymous enrolment reference. Not a name, not a date of birth. |
| `ts` | Band-reported window end time, UTC. The gateway also timestamps on receipt. |
| `tier` | Payload discriminator. `band` for this type. |
| `window_s` | Length of the window these features summarise. |
| `strap_closed` | Circuit continuity. `true` means closed, which means worn. |
| `clip_state` | Strap state machine state. See [`../spec.md`](../spec.md) section 3. |
| `strap_event` | `null` in the normal case. Carries `BREAKAWAY`, `CUT`, `FAULT`, or `RELEASED_BY_TOOL` when the state changes. |
| `attendance_state` | Attendance state as the band last knew it. The gateway holds the authoritative copy. |
| `activity_features` | The extracted features. Raw samples never appear here. |
| `battery_pct` | Remaining charge. Drives the battery critical escalation. |
| `rssi_dbm` | Strongest signal strength across the anchors that heard this window, used to separate radio dropout from removal. The per-anchor set of readings, which is what the Zone Resolver consumes, lives in the anchor observation envelope in [`telemetry-pipeline.md`](telemetry-pipeline.md) section 3 and is not part of this record. |
| `confidence` | On-band segmentation confidence for this window. |
| `fw_version`, `model_version` | Provenance, so a bad firmware or model version can be traced through the audit log. |
| `seq` | Monotonic per device. Orders windows and detects gaps. |
| `sig` | HMAC-SHA256 over the payload with the per-device key. The gateway drops anything it cannot authenticate. |

---

## 2. Gateway to cloud, per child per day

Sent over mTLS 1.3, once per child per day, store-and-forward on the gateway.

```json
{
  "schema_version": "1.0",
  "facility_id": "fac-004",
  "child_ref": "enr-8891",
  "date": "2026-09-03",
  "check_in": "08:41:12Z",
  "check_out": "16:22:07Z",
  "active_minutes": 187,
  "movement_variety_index": 0.68,
  "fitness_session_participation": true,
  "anomaly_events_resolved": 1,
  "gateway_id": "gw-004-a",
  "seq": 4471,
  "sig": "<hmac-sha256>"
}
```

| Field | Meaning |
|---|---|
| `schema_version` | Payload contract version. |
| `facility_id` | Which facility. Needed for multi-site administration. |
| `child_ref` | The same pseudonymous reference. The map to a real child stays in the facility. |
| `date` | The day this summary covers. |
| `check_in`, `check_out` | Attendance record times. |
| `active_minutes` | Total, for the day. Not a series. |
| `movement_variety_index` | Single 0 to 1 figure for the day. |
| `fitness_session_participation` | Boolean. |
| `anomaly_events_resolved` | A count. Not which anomaly, not when, not what the strap state was. |
| `gateway_id` | Which gateway sent it, for certificate and revocation purposes. |
| `seq` | Monotonic per gateway. With `date`, this is the replay protection. |
| `sig` | HMAC-SHA256 over the payload. |

Everything in this payload is a daily total, a timestamp, or a count. There is
no field here whose resolution is finer than one day.

---

## 3. Forbidden in the cloud payload

Four classes of data may not cross the gateway-to-cloud boundary. The concrete
field names each class rules out are listed alongside.

| Forbidden class | Fields this rules out |
|---|---|
| **Raw motion** | `activity_features` and every field inside it, and any representation of the IMU sample stream at any resolution |
| **Location** | `rssi_dbm`, and any field that would let a receiver infer where in the facility a child is |
| **Per-window data** | `window_s`, `ts` at window resolution, per-window `confidence`, per-window activity classifications, and any array of per-window records |
| **Trend flags** | Trend Analyst output in any form, reviewed or unreviewed |

Also excluded, for reasons that follow from the same principle: `device_id`
(band identity is facility-local), `clip_state` and `strap_event` (the cloud
receives the attendance outcome, and never the strap-level detail), and
`fw_version` and `model_version` (provenance is an audit concern that stays on
the gateway).

**This is enforced structurally.** The cloud payload schema sets
`additionalProperties: false`, so a payload carrying any field outside the
allowed set is rejected at ingest by the validator rather than by review. Data
minimisation is a property of the code path and not of a policy document that
someone has to remember to follow.

Rejected payloads are quarantined on the gateway with the validator error and
retried after correction. Nothing is silently dropped, and nothing is silently
accepted.

---

## 4. What is computed where

| Computation | Band | Gateway | Cloud |
|---|---|---|---|
| IMU sampling and filtering | Yes | No | No |
| Strap circuit monitoring | Yes | No | No |
| Step and motion segmentation | Yes | No | No |
| Feature extraction | Yes | No | No |
| Packet signing | Yes | Yes, for the cloud payload | No |
| Activity classification | No | Yes | No |
| Anomaly detection and grading | No | Yes | No |
| Attendance reconciliation | No | Yes | No |
| Day summarisation | No | Yes | No |
| Trend analysis | No | Yes | No |
| Safeguard policy evaluation | No | Yes | No |
| Alert ranking for the staff console | No | Yes | No |
| Schema validation at ingest | No | No | Yes |
| Parent portal view scoping | No | No | Yes |
| Multi-site aggregation | No | No | Yes |

No row in this table has a `Yes` in the cloud column for anything a carer needs
in order to act.

---

## 5. What is stored where

| Data class | Band | Gateway | Cloud |
|---|---|---|---|
| Raw IMU samples | Rolling buffer, hours | Retained locally, short window | **Never** |
| Extracted features | Transient | Yes, retention set by facility | **Never** |
| Activity classifications | No | Yes | Aggregated daily only |
| Strap and clip events | Yes | Yes | Attendance record only |
| Attendance record | No | Yes | Yes |
| Daily summary | No | Yes | Yes |
| Anomaly flags | No | Yes | Only if escalated and resolved |
| Trend flags | No | Yes, staff-reviewed | **Never sent unreviewed** |
| Zone assignments and zone history | No | Yes, gateway only | **Never** |

Stored is not the same as backed up, and the difference is deliberate. Features,
classifications, and all zone data are excluded from every backup, so their
retention window is the whole of their life. Configuration, keys, attendance,
consent, and the audit log are backed up, because those are the things that
cannot be recreated. The full register is in
[`backup-recovery.md`](backup-recovery.md).

One row in this table needs resolving. "Raw IMU samples, gateway, retained
locally, short window" does not sit cleanly with the pipeline above, in which
the band extracts features and transmits only feature windows. Under that
pipeline the gateway never receives raw samples and has none to retain. The
stricter reading (band-only raw samples) is what [`../spec.md`](../spec.md)
specifies and what the schema allows. The looser reading would require a raw
sample upload path that does not exist in this design. This is logged as
question 4.1 in [`../OPEN-QUESTIONS.md`](../OPEN-QUESTIONS.md), and it matters
because it changes what a seized or compromised gateway exposes.

---

## 6. Versioning

`schema_version` is present on both payload types and is bumped on any breaking
field change. The gateway rejects band payloads whose version it does not know.
The cloud ingest endpoint rejects gateway payloads whose version it does not
know, rather than ignoring unknown fields, which is the same rule
`additionalProperties: false` enforces within a version.
