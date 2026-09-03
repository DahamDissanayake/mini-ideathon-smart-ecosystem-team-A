# LetGo Band, system scope and agent contracts

This file defines what the system is and who each part answers to. It is the
authority for scope, agent responsibilities, and the safety contract. The HOW
(interfaces, state machines, parameters, failure handling) lives in `spec.md`.

Project context: IEEE Computer Society R10 Summer School 2026 Mini Ideathon,
SDG 3 track (Good Health and Well-being).

---

## 1. What the system is

LetGo Band is a child-worn activity band with a tamper-evident strap. The band
broadcasts, it does not connect. Mains-powered scanner anchors placed one per
zone hear those broadcasts and forward them to a facility edge gateway, which
runs the entire agent workflow locally. The system automates daycare
attendance, detects safety anomalies in seconds, resolves which zone a child is
in, and produces a daily activity record for parents.

The scope is one facility per gateway, with a cloud tier that serves parents and
multi-site administration only.

### In scope

- Attendance state, derived from strap circuit state, wear-consistent motion, presence inside the building via anchor coverage, and the daily roster.
- Safety anomaly detection: strap breach, signal loss after check-in, early device power-off, prolonged stillness inconsistent with wear.
- Unaccompanied perimeter crossing, detected from boundary anchor coverage.
- Zone-level presence at room resolution, with a confidence value.
- Activity classification and a per-day activity summary, including movement variety across zones.
- Multi-day activity pattern deviation flags, including zone preference patterns, for staff review only.
- Local staff console, and a parent portal fed by minimised daily summaries.

### Out of scope, permanently

- Diagnosis of any kind. The system produces flags for a human to review, and never a conclusion about a child.
- Calorie, weight, body composition, or fitness-scoring output.
- Any restriction of a child's movement. The band observes, it does not confine.
- Comparison of one child against another.
- Per-carer performance measurement. This data is not generated at all.
- Position, coordinates, or distance. We resolve which zone a child is in, and never where in the zone. See `spec.md` section 10.
- Continuous location tracking, audio, or video. Zone assignments stay on the gateway and no location data of any kind reaches the cloud.

---

## 2. Who each tier answers to

Four tiers, each existing for a reason the others cannot satisfy. The anchors
are numbered 0.5 because they were added after the tier numbers were already in
use across these files, and renumbering would have changed what Tier 1 and Tier
2 mean everywhere else.

### Tier 0, the band

Runs sampling, filtering, strap circuit monitoring, step and motion
segmentation, feature extraction, a local buffer, and connectionless BLE
advertising.

It exists because the band has to keep working with no listener in range, and
because strap events have to be registered in the instant they happen. A band
that depends on radio contact to notice its own strap opening is not a safety
device.

The band never associates with anything during normal operation. It holds no
network credentials, no WiFi password, and no connection state. BLE connections
are used only for provisioning and firmware update, in the dock, one device at a
time, and never in the field.

### Tier 0.5, the scanner anchors

Mains-powered ESP32 scanners, one per zone. Each hears every band advertisement
in range, records its own received signal strength, and forwards the raw
advertisement to the gateway over WiFi, with ESP-NOW as the fallback when
facility WiFi is unavailable.

They exist because a broadcast is heard by every listener in range at once,
which makes multi-anchor zone detection nearly free. A point-to-point connection
would be heard by one receiver and would give us no zone information at all.

Anchors are dumb forwarders. They hold no band keys, they do not decode or
authenticate what they hear, and they do not decide which zone a band is in. The
anchor-to-zone map lives on the gateway, so a compromised anchor can report a
signal strength but cannot claim a zone or forge a band.

### Tier 1, the edge gateway

Runs the movement classification model, all five agents, the deterministic Zone
Resolver, the deterministic Safeguard, attendance reconciliation, the staff
console, and local storage of raw features. It verifies the authentication tag
on every advertisement an anchor forwards, and it is the only tier that holds
band keys.

It exists for three reasons that resolve to one decision. Raw child motion must
not leave the premises, so the processing has to happen inside the building.
Safety alert latency must be sub-second, so it cannot wait for a round trip. The
facility must keep operating with no internet, so nothing safety-critical can
sit on the far side of the WAN link.

### Tier 2, the cloud

Runs the parent portal, storage of encrypted daily summaries, and multi-site
administration.

It exists because parents are off-site. Nothing here is safety-critical.

**Design rule, enforced everywhere:** no safety decision depends on Tier 2. If
the internet fails, the facility loses the parent portal and loses nothing else.

---

## 3. The five agents

All five execute on the edge gateway (Tier 1). Each reads only the fields its
contract names, enforced at the message bus rather than by convention.

The *May not* clauses below are the safety contract. They are binding on
implementation, and they are the reason a reviewer can trust the output.

---

### 1. Movement Classifier

| | |
|---|---|
| **Purpose** | Turn IMU feature windows into named activity types with a confidence score. |
| **Consumes** | Feature windows from the band (mean acceleration magnitude, acceleration variance, step count, cadence, posture estimate). |
| **Produces** | Activity classifications with confidence scores. |
| **Type** | Model-backed. A trained classifier over feature windows. |

*May not:* interpret clinically, make recommendations, or output anything about
a child's development.

---

### 2. Anomaly Monitor

| | |
|---|---|
| **Purpose** | Detect and grade the conditions that need a carer's attention now. |
| **Consumes** | Strap events, link state, motion, and anchor coverage (which anchors are currently hearing this band). |
| **Produces** | Graded anomaly events: signal loss after check-in, early device power-off, prolonged stillness inconsistent with wear, strap breach. |
| **Type** | Deterministic. Rules over strap state, link state, anchor coverage, and elapsed time. It reads classifier output as context, and no safety event depends on the classifier being right. |

*May not:* suppress a strap breach event under any circumstance. Breaches always
escalate.

*Also may not:* raise or withhold a safety escalation on zone confidence alone.
See the signal trust hierarchy in section 6.

Anchor coverage changes what silence means. Under the old point-to-point
topology a band that stopped reporting and a band that moved out of range of the
one receiver were the same observation, which was a real weakness. With several
anchors listening at once the Anomaly Monitor separates three cases: heard by a
different anchor than before (a handover, and not an anomaly), heard by fewer
anchors and weakening (a coverage edge, which may be a perimeter approach), and
heard by no anchor at all (genuine silence, which escalates).

---

### 3. Day Summariser

| | |
|---|---|
| **Purpose** | Reduce a session's classifications to the record a parent sees. |
| **Consumes** | Activity classifications across a session, and the zone assignments those classifications happened in. |
| **Produces** | Active minutes, movement variety (across activity classes and across zones), fitness session participation. |
| **Type** | Deterministic. Aggregation over classifier and Zone Resolver output, with no model of its own. |

*May not:* produce calorie, weight, body composition, or fitness-scoring output.
Never compares one child to another.

Movement variety now accounts for how many zones a child moved through, which
says more than raw motion alone. A child who was active in one corner all day
and a child who moved through every zone produce different variety figures. The
zone identifiers themselves stay on the gateway. What reaches the cloud is the
single variety figure that already existed.

---

### 4. Trend Analyst

| | |
|---|---|
| **Purpose** | Notice that a child's activity pattern has moved away from that child's own baseline across days. |
| **Consumes** | Multi-day summaries, and per-day zone occupancy for that child. |
| **Produces** | Activity pattern deviation flags, including zone preference deviation over weeks. |
| **Type** | Model-backed. Deviation detection against a per-child baseline. |

*May not:* produce a conclusion, diagnosis, or characterisation of a child.
Output is a flag for staff review only, never surfaced to parents unreviewed.

The may-not clause applies to zone preference exactly as it applies to activity.
A child who stopped using a zone they used to favour is a flag for a carer to
look at, and it is never a statement about that child.

---

### 5. Attendance Manager

| | |
|---|---|
| **Purpose** | Reconcile four independent sources of truth about who is present. |
| **Consumes** | Clip events, motion confirmation, presence inside the building via anchor coverage, and the daily roster. |
| **Produces** | Attendance state transitions including perimeter crossing, and the set of mismatches between the four sources. |
| **Type** | Deterministic. A state machine plus a reconciliation rule set. |

*May not:* mark a child present on clip state alone.

Anchor coverage is the third signal, and the roster is the fourth. It buys one
thing the other signals cannot give: whether the child is still inside the
building. A crossing of the facility boundary with no staff attribution is the
highest-severity event this system produces, and it escalates on its own path
alongside strap breach. That detection is far easier and far more reliable than
indoor position, because it asks whether any interior anchor can hear the band
at all rather than asking where the band is.

---

## 4. The Zone Resolver

The Zone Resolver is a deterministic component and not an agent. It holds no
model. It sits between anchor input and the agents, so that no agent ever sees a
raw signal strength reading.

| | |
|---|---|
| **Purpose** | Turn signal strength observations from many anchors into one zone assignment per band. |
| **Consumes** | Anchor observations (anchor id, received signal strength, receive timestamp, the raw advertisement), the anchor-to-zone map, and the facility calibration table. |
| **Produces** | Zone assignments with a confidence value, and zone transition events including boundary crossings. |
| **Type** | Deterministic, rule-based. Smoothing, then hysteresis, then comparison against the calibration table. No model, no training, no inference. |

*May not:* emit a position, a coordinate, or a distance. Its output vocabulary
is the facility's configured zone list plus `unknown`. When the smoothed margin
between the best and second-best anchor is below the hysteresis threshold, it
emits `unknown` rather than picking a winner.

The three stability mechanisms it applies, and the parameters each one needs,
are specified in `spec.md` sections 6 and 10. All three exist because a single raw
reading is not a usable signal in a room full of moving children.

---

## 5. The Safeguard

The Safeguard is a deterministic policy engine. It is not an agent, it holds no
model, and it does not reason. It applies rules to every agent proposal before
that proposal reaches a human.

It holds:

- Who may see which child's data.
- What escalates to staff, and what goes to parents.
- The confidence floor below which nothing is surfaced.
- The contraindication list for the Trend Analyst.
- The signal trust hierarchy, and the rule that zone data never stands alone.

Every agent output passes through it. It has three verdicts: approve as urgent
(to the staff console), approve as routine (to the cloud summary), or reject
(logged, not surfaced).

**Veto, and no override path.** There is no flag, no configuration value, and no
staff role that lets an agent proposal bypass the Safeguard. If a future feature
needs an exception, the rule changes and the change is reviewed. Nothing routes
around it at run time.

Carers can silence, dismiss, or escalate an alert the Safeguard has already
approved. That is a human action on an approved alert, it is logged, and the
alert is not deleted. It does not override the Safeguard.

---

## 6. Precedence when agents conflict

Safety outranks summary, always. When two agent outputs disagree, or when
several want the same carer's attention at once, the Safeguard applies this
order, highest first:

1. **Strap breach** (breakaway, cut, or fault) from the Anomaly Monitor, and **unaccompanied perimeter crossing** from the Attendance Manager. Both bypass batching and escalate immediately, and no other agent state can delay or suppress either. When both fire for the same child, the strap breach is shown first, because it is deterministic and the crossing is probabilistic.
2. **Other safety anomalies**: signal loss after check-in (no anchor hearing the band), early device power-off, prolonged stillness inconsistent with wear, battery critical.
3. **Attendance state and reconciliation mismatches** from the Attendance Manager.
4. **Day summary** output.
5. **Trend flags**, which are queued for staff review and never escalated as alerts.

### The signal trust hierarchy

The three signals this system runs on are not equally trustworthy, and the
Safeguard ranks them explicitly:

| Rank | Signal | Character |
|---|---|---|
| 1 | Strap circuit | Deterministic. A closed circuit is measured, not inferred. |
| 2 | Motion | Reliable. Derived from the IMU, and wrong only when the classifier is wrong. |
| 3 | Signal strength and zone | Probabilistic. A room full of moving children is a moving radio environment. |

**Zone data may enrich an alert. It may never be the sole basis for a
safety-critical decision.** Zone can say which room to check first, it can rank
one alert above another, and it can raise a perimeter crossing for a human to go
and look at. It cannot contradict the strap circuit, it cannot mark a child
present or absent on its own, and no automatic action is taken on it.

The perimeter crossing sits at the top of the precedence order and still obeys
this rule, because the response to it is a carer going to look. The system takes
no action of its own on a zone signal.

Three rules cut across the order:

- **Attendance never wins over safety.** A clean attendance state does not
  suppress an anomaly. A child recorded as `CHECKED_OUT` whose band reports a
  strap breach still generates the breach.
- **The classifier never gates a safety event.** Anomaly Monitor conclusions
  that rest on strap state or link state stand on their own, whatever the
  Movement Classifier says or fails to say.
- **Zone never stands alone.** A perimeter crossing alert carries the
  corroborating evidence it was raised on (last strap state, last motion, which
  anchors last heard the band) and its confidence value. An alert that cannot
  carry that evidence is still raised, and it is marked as uncorroborated.

Below the confidence floor, the Safeguard suppresses and logs. It does not guess
and it does not surface a hedged result.

---

## 7. Where to look next

| Question | File |
|---|---|
| Interfaces, state machines, parameters, failure paths | `spec.md` |
| Radio choice per tier, the advertisement layout, zone determination | `spec.md` sections 8, 9 and 10 |
| Components, the strap circuit, the breakaway clip | `docs/hardware.md` |
| Agent orchestration diagram and an end-to-end walkthrough | `docs/blueprint.md` |
| Payload shapes and what is stored where | `docs/telemetry-schema.md` |
| Threat model, access control, encryption | `docs/security.md` |
| Risks, assumptions, issues, dependencies | `docs/raid.md` |
| Things the design does not yet settle | `OPEN-QUESTIONS.md` |
