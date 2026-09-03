# LetGo Band, system scope and agent contracts

This file defines what the system is and who each part answers to. It is the
authority for scope, agent responsibilities, and the safety contract. The HOW
(interfaces, state machines, parameters, failure handling) lives in `spec.md`.

Project context: IEEE Computer Society R10 Summer School 2026 Mini Ideathon,
SDG 3 track (Good Health and Well-being).

---

## 1. What the system is

LetGo Band is a child-worn activity band with a tamper-evident strap, connected
to a facility edge gateway that runs the entire agent workflow locally. The
system automates daycare attendance, detects safety anomalies in seconds, and
produces a daily activity record for parents.

The scope is one facility per gateway, with a cloud tier that serves parents and
multi-site administration only.

### In scope

- Attendance state, derived from strap circuit state, wear-consistent motion, and the daily roster.
- Safety anomaly detection: strap breach, signal loss after check-in, early device power-off, prolonged stillness inconsistent with wear.
- Activity classification and a per-day activity summary.
- Multi-day activity pattern deviation flags, for staff review only.
- Local staff console, and a parent portal fed by minimised daily summaries.

### Out of scope, permanently

- Diagnosis of any kind. The system produces flags for a human to review, and never a conclusion about a child.
- Calorie, weight, body composition, or fitness-scoring output.
- Any restriction of a child's movement. The band observes, it does not confine.
- Comparison of one child against another.
- Per-carer performance measurement. This data is not generated at all.
- Location tracking, audio, or video.

---

## 2. Who each tier answers to

Three tiers, each existing for a reason the other two cannot satisfy.

### Tier 0, the band

Runs sampling, filtering, strap circuit monitoring, step and motion
segmentation, feature extraction, and a local buffer.

It exists because the band has to keep working with the gateway out of range,
and because strap events have to be registered in the instant they happen. A
band that depends on radio contact to notice its own strap opening is not a
safety device.

### Tier 1, the edge gateway

Runs the movement classification model, all five agents, the deterministic
Safeguard, attendance reconciliation, the staff console, and local storage of
raw features.

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
| **Consumes** | Strap events, link state, and motion. |
| **Produces** | Graded anomaly events: signal loss after check-in, early device power-off, prolonged stillness inconsistent with wear, strap breach. |
| **Type** | Deterministic. Rules over strap state, link state, and elapsed time. It reads classifier output as context, and no safety event depends on the classifier being right. |

*May not:* suppress a strap breach event under any circumstance. Breaches always
escalate.

---

### 3. Day Summariser

| | |
|---|---|
| **Purpose** | Reduce a session's classifications to the record a parent sees. |
| **Consumes** | Activity classifications across a session. |
| **Produces** | Active minutes, movement variety, fitness session participation. |
| **Type** | Deterministic. Aggregation over classifier output, with no model of its own. |

*May not:* produce calorie, weight, body composition, or fitness-scoring output.
Never compares one child to another.

---

### 4. Trend Analyst

| | |
|---|---|
| **Purpose** | Notice that a child's activity pattern has moved away from that child's own baseline across days. |
| **Consumes** | Multi-day summaries. |
| **Produces** | Activity pattern deviation flags. |
| **Type** | Model-backed. Deviation detection against a per-child baseline. |

*May not:* produce a conclusion, diagnosis, or characterisation of a child.
Output is a flag for staff review only, never surfaced to parents unreviewed.

---

### 5. Attendance Manager

| | |
|---|---|
| **Purpose** | Reconcile three independent sources of truth about who is present. |
| **Consumes** | Clip events, motion confirmation, and the daily roster. |
| **Produces** | Attendance state transitions, and the set of mismatches between the three sources. |
| **Type** | Deterministic. A state machine plus a reconciliation rule set. |

*May not:* mark a child present on clip state alone.

---

## 4. The Safeguard

The Safeguard is a deterministic policy engine. It is not an agent, it holds no
model, and it does not reason. It applies rules to every agent proposal before
that proposal reaches a human.

It holds:

- Who may see which child's data.
- What escalates to staff, and what goes to parents.
- The confidence floor below which nothing is surfaced.
- The contraindication list for the Trend Analyst.

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

## 5. Precedence when agents conflict

Safety outranks summary, always. When two agent outputs disagree, or when
several want the same carer's attention at once, the Safeguard applies this
order, highest first:

1. **Strap breach** (breakaway, cut, or fault) from the Anomaly Monitor. Bypasses batching, escalates immediately, and no other agent state can delay or suppress it.
2. **Other safety anomalies**: signal loss after check-in, early device power-off, prolonged stillness inconsistent with wear, battery critical.
3. **Attendance state and reconciliation mismatches** from the Attendance Manager.
4. **Day summary** output.
5. **Trend flags**, which are queued for staff review and never escalated as alerts.

Two rules cut across that order:

- **Attendance never wins over safety.** A clean attendance state does not
  suppress an anomaly. A child recorded as `CHECKED_OUT` whose band reports a
  strap breach still generates the breach.
- **The classifier never gates a safety event.** Anomaly Monitor conclusions
  that rest on strap state or link state stand on their own, whatever the
  Movement Classifier says or fails to say.

Below the confidence floor, the Safeguard suppresses and logs. It does not guess
and it does not surface a hedged result.

---

## 6. Where to look next

| Question | File |
|---|---|
| Interfaces, state machines, parameters, failure paths | `spec.md` |
| Agent orchestration diagram and an end-to-end walkthrough | `docs/blueprint.md` |
| Payload shapes and what is stored where | `docs/telemetry-schema.md` |
| Threat model, access control, encryption | `docs/security.md` |
| Risks, assumptions, issues, dependencies | `docs/raid.md` |
| Things the design does not yet settle | `OPEN-QUESTIONS.md` |
