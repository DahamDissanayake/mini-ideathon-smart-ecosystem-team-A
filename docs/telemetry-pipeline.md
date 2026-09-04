# Telemetry implementation

[`telemetry-schema.md`](telemetry-schema.md) says what the payloads contain.
This file says how they get there: the hops, the envelope each hop adds, what
the gateway does between receiving bytes and handing a feature window to an
agent, what happens when a hop is unavailable, and what the system reports about
its own health.

The distinction that matters throughout is between **child telemetry**, which is
about a child and is bound by the access control matrix, and **health
telemetry**, which is about the equipment and is deliberately built so that it
cannot be turned back into child telemetry. Section 7 covers the second, and it
is the section most likely to be got wrong in implementation.

---

## 1. The path, end to end

```
  Band ──BLE advertisement, 26 bytes, plaintext + tag──┐
                                                        ├──> heard by every
  Band ──BLE advertisement─────────────────────────────┘    anchor in range
                                                             (0, 1, or many)
                             │
                             ▼
  Anchor  ──── observation envelope, WiFi or ESP-NOW ────>  Gateway ingest
                             │
                             ▼
              ┌──────────── gateway pipeline ────────────┐
              │ receive → rate limit → dedupe → verify    │
              │ tag → resolve adv_id → decode → normalise │
              │ → zone resolve → message bus → agents     │
              │ → Safeguard → console / store             │
              └──────────────────────────────────────────┘
                             │
                             ▼
             Daily summary ── mTLS, store and forward ──> Cloud
```

Four properties of this path drive everything below.

**A band advertisement is heard zero, one, or many times.** The band does not
know and does not care. Duplication is normal, not an error, and the gateway is
the first place it can be resolved, because it is the first tier that can tell
which band it is looking at.

**Every hop after the band is store and forward.** No hop drops data because the
next hop is unavailable. The costs of that are ordering and lateness, handled in
sections 5 and 6.

**Nothing is trusted until the gateway verifies it.** An anchor is a transport,
and the observation envelope is a claim.

**Delivery is at-least-once, and processing is effectively-once.** The
deduplication key in section 4 is what turns the first into the second.

---

## 2. Hop 1, band to anchor

| Property | Value |
|---|---|
| Transport | Connectionless BLE advertising, no acknowledgement |
| Payload | 26 bytes, compact binary, layout in [`../spec.md`](../spec.md) section 9 |
| Cadence | One advertisement per `window_s`, currently 30 s, repeated on `adv_interval` within the window |
| Priority path | A strap breach advertises immediately and repeats, ahead of the normal cadence |
| Delivery guarantee | **None.** The band gets no feedback and does not retry on failure, it retries on schedule |
| Buffer | Unsent-window queue on the band, replayed on the band's replay schedule when it is next heard |

The band has no way to know whether it was heard, so "retry" here means
"advertise again", not "resend because delivery failed". Windows produced while
no anchor was in range sit in the band's queue and are re-advertised later,
carrying their original sequence numbers and their original band-reported
timestamps. This is why the gateway sees a dropout as a gap followed by an
out-of-order burst, and why `seq` rather than arrival order is what puts the
windows back in order.

---

## 3. Hop 2, anchor to gateway

An anchor adds an envelope around the bytes it heard, and changes nothing
inside them.

```json
{
  "schema_version": "1.0",
  "tier": "anchor",
  "anchor_id": "anc-004-b3",
  "rx_ts": "2026-09-03T09:12:44.812Z",
  "rssi_dbm": -61,
  "adv_bytes": "0102a4f1...",
  "adv_len": 26,
  "fw_version": "0.2.0",
  "envelope_seq": 88213
}
```

| Field | Meaning |
|---|---|
| `schema_version` | Envelope contract version. The gateway rejects a version it does not know. |
| `tier` | Payload discriminator. `anchor` for this type. |
| `anchor_id` | Which anchor is making the claim. The gateway maps it to a zone; the anchor does not know its own zone. |
| `rx_ts` | Anchor receive time, millisecond resolution. Used for smoothing and for the dedupe window, not as an authority on when the band produced the window. |
| `rssi_dbm` | How strongly this anchor heard it. A claim by the anchor, and the only field an anchor originates that affects output. |
| `adv_bytes` | The advertisement exactly as heard, hex encoded. Unmodified, unparsed, unauthenticated by the anchor. |
| `adv_len` | Length as received. A truncated advertisement is forwarded anyway and fails tag verification at the gateway, which is the correct place to fail. |
| `fw_version` | Anchor firmware, so a misbehaving anchor build is traceable. |
| `envelope_seq` | Monotonic per anchor. Detects anchor-side loss and lets the gateway measure a per-anchor gap rate without inspecting any child data. |

**An anchor asserts four things and no more:** who it is, when it heard
something, how strongly, and what bytes it heard. It does not assert a zone, a
band, a child, or that the advertisement is genuine. Everything an anchor says
is re-derived or verified at the gateway, except `rssi_dbm`, which cannot be,
and which is why zone data sits at the bottom of the trust hierarchy in
`../CLAUDE.md` section 6.

`adv_bytes` is hex in this representation for the same reason the band payload
is shown as JSON in `telemetry-schema.md`: it is the readable form. The wire
encoding between anchor and gateway is compact binary, and over ESP-NOW it has
to be, because the ESP-NOW payload limit does not leave room for hex.

---

## 4. The gateway pipeline, stage by stage

Nine stages between an anchor envelope arriving and an agent seeing anything.
Each stage either passes a record on or drops it with a logged reason. No stage
guesses.

| # | Stage | What it does | On failure |
|---|---|---|---|
| 1 | **Receive** | Terminate the anchor connection, authenticate the anchor credential, parse the envelope. | Unknown anchor, bad credential, or unknown `schema_version`: dropped and logged. Repeated failures raise an anchor health alert. |
| 2 | **Rate limit** | Per-anchor ingest ceiling, so one anchor cannot starve the others. | Excess dropped with a counter increment. The ceiling is not yet sized, see section 10. |
| 3 | **Dedupe** | Collapse copies of the same advertisement heard by several anchors into one logical observation, keeping every anchor's `rssi_dbm`. | Not a failure. This is the normal case and it is where the zone signal comes from. |
| 4 | **Verify tag** | Recompute the truncated HMAC over bytes 0 to 17 with each candidate per-device key and compare. | Fails: dropped, logged, counted per anchor and per `adv_id`, rate-limited. It never reaches an agent. |
| 5 | **Resolve** | Map the rotating `adv_id` to a band, and the band to a `child_ref`. | Unresolvable: dropped and counted. A rise in unresolvable rate is an anchor health signal or a rotation bug, and both need to be visible. |
| 6 | **Decode** | Expand the 26 bytes into the `band_window` structure in `telemetry-schema.md`. | Unknown `proto_ver`: dropped and logged. |
| 7 | **Normalise** | Attach gateway receive time, order by `seq`, mark late arrivals, apply scaling to the packed integers. | Duplicate `seq` for that band: dropped as a replay. Gap in `seq`: passed through, with the gap recorded. |
| 8 | **Zone resolve** | Smooth per band per anchor, apply hysteresis, compare against the calibration table, emit a zone or `unknown`. | Below the hysteresis margin: emits `unknown`, which is an answer and not a failure. |
| 9 | **Publish** | Put the window, the zone assignment, and their confidences on the message bus, where each agent reads only the fields its contract names. | An agent reading outside its contract is refused at the bus. |

Stages 4 and 5 are in that order deliberately. Verification is cheaper than
resolution when a forgery is being attempted at volume, and doing it first means
a flood of garbage never reaches the resolver.

### Deduplication, precisely

The dedupe key is **`(resolved_band, seq)`**, which is only available after stage
5. Before that, stage 3 groups on **`(adv_bytes, rx_ts within adv_dedupe_window)`**,
which is safe because two different bands cannot produce identical bytes: the
authenticated tag is computed with a per-device key over a payload containing a
per-band sequence number.

Grouping, not discarding, is the point. Five anchors hearing one advertisement
produce one observation carrying five `(anchor_id, rssi_dbm)` pairs, and that
set is exactly the input the Zone Resolver needs. A pipeline that deduplicated
by throwing four copies away would delete the zone signal.

`adv_dedupe_window` is a new parameter and it is not yet set. It has to be long
enough to cover clock skew between anchors and forwarding jitter, and short
enough not to merge two genuine repeats of the same window.

### Clocks

Three timestamps exist per observation and each answers a different question.

| Timestamp | Set by | Authority for |
|---|---|---|
| Band-reported window end | Band | When the child moved. Subject to band clock drift. |
| `rx_ts` | Anchor | Smoothing and the dedupe window. Subject to anchor clock skew. |
| Gateway receive time | Gateway | Ordering for alerting, and every latency measurement |

The gateway timestamps on receipt and records the band-reported time separately,
so drift is visible rather than corrected away. Anchors synchronise their clocks
to the gateway, which is the only tier whose clock has to be right, because a
skewed anchor widens the dedupe window rather than corrupting anything.

---

## 5. Delivery semantics

| Hop | Guarantee | Mechanism | What a failure looks like |
|---|---|---|---|
| Band to anchor | At-most-once per advertisement, at-least-once per window across repeats | Repeat on `adv_interval`, band-side queue and later replay | A window arrives late, or not at all if the band never comes back into range |
| Anchor to gateway | At-least-once | Short anchor queue, retry on reconnect, `envelope_seq` for gap detection | Duplicate envelopes, absorbed by dedupe |
| Gateway internal | Effectively-once | `(resolved_band, seq)` dedupe, replay rejection on `seq` | A replayed advertisement is rejected at stage 7 |
| Gateway to cloud | At-least-once, idempotent at ingest | Store and forward, `(gateway_id, seq)` plus `date` at ingest | A re-sent summary overwrites an identical one instead of creating a second |

**At-least-once with an idempotency key is deliberate.** The alternative,
exactly-once delivery, would require the band to hold a connection and receive
acknowledgements, which is the topology this system moved away from. A safety
system that discards a strap breach because it was uncertain whether it had
already been delivered is worse than one that delivers it twice.

The strap breach path takes this to its conclusion. A breach advertises
immediately and repeats, the gateway deduplicates, and the Anomaly Monitor
escalates once. If deduplication ever failed, the result would be a duplicate
alert on the console, which is a nuisance. The failure in the other direction is
a missed breach, which is the thing this whole system exists to prevent.

---

## 6. Buffering, backpressure, and what fills up first

Every hop has a bounded buffer, and bounded buffers overflow. Saying which one
overflows first, and what is lost when it does, is part of the design rather
than an operational surprise.

| Buffer | Where | Bounded by | Overflow behaviour |
|---|---|---|---|
| Unsent-window queue | Band | Band RAM and flash | Oldest feature windows dropped first. Strap events are never dropped, they are held ahead of the queue. |
| Forwarding queue | Anchor | Anchor RAM, deliberately small | Oldest envelopes dropped first, and the drop is counted and reported in anchor health |
| Ingest queue | Gateway | Gateway memory, per anchor | Per-anchor rate limit applies before the queue, so one anchor cannot fill it |
| Feature store | Gateway | Disk, and `feature_retention_window` | Retention job expires oldest first. Disk pressure raises a gateway health alert before it becomes lossy. |
| Cloud forward queue | Gateway | Disk | Daily summaries are small and the queue is sized for a multi-day outage. Overflow is a gateway health alert, not silent loss. |

**Priority within a buffer is not FIFO.** A strap breach jumps every queue at
every hop, which is the concrete form of the rule in `../CLAUDE.md` section 6
that a breach is never suppressed by batching.

**Backpressure never reaches the band.** The band cannot be told to slow down,
because it has no listener. That is a property of connectionless broadcast: the
only thing that changes the band's transmit rate is its own configuration, set
in the dock. So the gateway absorbs load by shedding at the rate limiter, where
the loss is counted and visible, rather than by asking anyone to send less.

---

## 7. Health telemetry, and the line it must not cross

The system reports on its own equipment. This is the part of telemetry design
most likely to quietly undo the privacy properties of everything else, because
metrics get added under time pressure, by people thinking about uptime rather
than about children, and monitoring stacks retain data far longer than
application stores do.

**The rule: health telemetry carries no `child_ref`, no `device_id`, no
`adv_id`, and no per-band series of any kind.** A metric labelled by band and by
anchor is a location history under a different name, with weaker retention and
weaker access control than the data the access control matrix protects. It would
be a complete bypass of section 2 of [`security.md`](security.md), and it would
be built by accident.

### What is collected

| Metric | Scope | Why it is safe |
|---|---|---|
| Envelopes forwarded per minute | Per anchor | A count, with no band identity in it |
| Gap rate from `envelope_seq` | Per anchor | Measures anchor-side loss without inspecting payloads |
| Tag verification failures | Per anchor, and per `adv_id` **in a short-lived counter only** | The `adv_id` counter exists to rate-limit forgery attempts and expires with the rotation period. It is never stored as a series. |
| Unresolvable `adv_id` rate | Facility total | A resolution or rotation problem, expressed as one number |
| Distinct bands heard | Per anchor, **count only** | A count of how many, never which ones |
| Anchor last-seen and uptime | Per anchor | About equipment |
| Pipeline stage latency | Percentiles, facility-wide | About software |
| Ingest queue depth, feature store size, cloud queue depth | Gateway | About capacity |
| Zone `unknown` rate | Per zone, aggregated over a window | Says a zone needs recalibration, without saying who was in it |
| Alerts raised, by type and grade | Facility total | Feeds alert-fatigue review, carries no child identity |
| Safeguard rejections, by reason | Facility total | The number that tells you whether the confidence floor is set wrong |

### What is not collected, and why

- **No per-band or per-child metric series.** See the rule above.
- **No per-anchor-per-band signal strength series.** That is a location history.
  Smoothing state exists in memory for the Zone Resolver and is not a metric.
- **No zone occupancy series.** Not per child, and not per zone, because a
  per-zone occupancy series in a facility with small groups identifies children
  by elimination.
- **No per-carer anything.** Consistent with the facility row of the threat
  model, and with the rule that the data is not generated at all.
- **No health telemetry leaves the facility by default.** It is for the local
  console. A multi-site operator that wants fleet health gets facility-level
  rollups, sent on the same mTLS link and validated by the same style of strict
  schema. If that is ever built, it needs its own allow-list, because a fleet
  health endpoint is exactly where per-band labels would reappear.

### The audit log is not health telemetry

They are separate stores with separate rules, and conflating them is the other
way this goes wrong.

| | Audit log | Health telemetry |
|---|---|---|
| Contains child identity | Yes, `child_ref` | **Never** |
| Purpose | Accountability for a decision about a child | Keeping the equipment working |
| Access | Read-only to the facility admin, no delete | Operational, local |
| Retention | Facility-set, typically longer | Short, and shorter than the feature retention window |
| Aggregation | Never. Every entry is a specific decision. | Always. |

---

## 8. Storage on the gateway

| Store | Contents | Retention | Notes |
|---|---|---|---|
| Feature store | Decoded feature windows per child | `feature_retention_window`, facility-set | The largest store, and the one a gateway seizure exposes. Bounding it is a security control, not housekeeping. |
| Classification store | Activity classes with confidences | Facility-set, tied to the feature window | |
| Zone state | Smoothing state, current assignment, transitions | Short. Current assignment plus a bounded transition history. | Never exported, never backed up, see [`backup-recovery.md`](backup-recovery.md) |
| Attendance store | State transitions, mismatches, resolutions | Facility-set, aligned with the facility's own attendance record | |
| Trend baselines | Per-child baselines and flags | Facility-set | Staff-reviewed before surfacing, never sent to a parent |
| Audit log | Append-only decision and access records | Facility-set, typically the longest | No delete path for any role |
| Cloud forward queue | Pending daily summaries | Until acknowledged | |
| Configuration | Anchor-to-zone map, calibration table, roster, parameters | Until changed, versioned | Expensive to recreate. This is the store that most needs a backup. |

Retention is enforced by a scheduled job that runs on the gateway, logs what it
expired, and covers backups as well as live data. A retention window nothing
enforces is a preference.

---

## 9. What the mock generator implements

[`../mock/generator.py`](../mock/generator.py) stands in for both the hardware
and the labelled dataset. Against this pipeline, it covers some stages and not
others, and the gap is worth stating so that nobody mistakes a passing run for a
validated pipeline.

| Pipeline element | In the generator |
|---|---|
| Band feature windows and the two-condition attendance rule | Yes |
| Strap events sent unbatched, ahead of the queue | Yes |
| Band-side store and forward, replayed out of order | Yes |
| Schema validation on every record before it is written | Yes, and the run exits non-zero on a failure |
| Daily summary built from windows and validated with `additionalProperties: false` | Yes |
| Anchor envelopes, multiple anchors hearing one advertisement | **No.** The generator emits gateway-side band windows directly. |
| Tag verification, `adv_id` resolution, dedupe | **No.** Signatures use a fixed demo key and authenticate nothing. |
| Zone resolution, smoothing, hysteresis, calibration | **No** |
| Safeguard, confidence floor | **No.** The floor cannot be set until labelled data exists. |

The largest missing piece is the anchor layer. The generator was written against
the previous point-to-point topology and emits what the gateway would hold
*after* stages 1 to 7, so it exercises the agents and not the ingest path.
Generating anchor envelopes with plausible per-anchor signal strengths is what
would let the Zone Resolver be tested at all, and it is logged as question 6.2
in [`../OPEN-QUESTIONS.md`](../OPEN-QUESTIONS.md).

---

## 10. Parameters this file introduces

Named here so they cannot be quietly hardcoded, in the same spirit as
[`../spec.md`](../spec.md) section 6.

| Parameter | Current value | What it controls |
|---|---|---|
| `adv_dedupe_window` | Not yet set | How close two identical advertisements must be in `rx_ts` to be treated as one observation heard by several anchors |
| `anchor_ingest_rate_limit` | Not yet set | Per-anchor ceiling at stage 2. Bounds a hostile or faulty anchor. |
| `anchor_queue_depth` | Not yet set | Anchor forwarding queue size, and therefore how long a WiFi blip is survivable |
| `cloud_queue_days` | Not yet set, target several days | How long an internet outage can last before the forward queue is a problem |
| `health_metric_retention` | Not yet set, shorter than `feature_retention_window` | How long operational metrics are kept |
| `anchor_clock_skew_budget` | Not yet set | Skew the dedupe window must tolerate before it starts merging distinct observations |

None of these has an empirical basis yet. `adv_dedupe_window` and
`anchor_ingest_rate_limit` are the two that need measuring first, because the
first decides whether zone resolution works at all and the second decides
whether one broken anchor takes the facility's ingest down.
