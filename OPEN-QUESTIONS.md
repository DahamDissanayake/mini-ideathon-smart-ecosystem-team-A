# Open questions

Things the design does not settle. Each entry says what is missing, what we
assumed in order to keep writing, and what would settle it. Where a file already
states an assumption, it is marked as such so the two do not drift.

Nothing here is blocking the simulation. Several entries are blocking a
deployment.

---

## 1. Values we cannot set yet

| # | Question | Assumption in the current files | What settles it |
|---|---|---|---|
| 1.1 | What is the confidence floor? | `spec.md` lists `confidence_floor` as unset. The mock generator emits confidence values without applying a floor. | A staff-labelled validation set, plus a decision on the false-positive rate a facility will tolerate on the console. |
| 1.2 | What is the signal loss threshold? | `spec.md` lists `signal_loss_threshold` as unset. The generator uses a placeholder gap length for the `--signal-loss` scenario. | Measuring normal BLE dropout duration in a real facility, including dead spots and outdoor areas. |
| 1.3 | What is the exact breakaway force? | "Typically 20 to 30 N", taken from the plan. Set mechanically at manufacture, not configurable. | Physical testing against child anthropometric data and playground snag scenarios. Must release before injury and must not release during normal play. |
| 1.4 | What is the battery critical threshold? | Not stated anywhere. The failure path says "escalates before depletion, not after" without a percentage. | Battery characterisation on the prototype, expressed as remaining hours rather than percent. |
| 1.5 | How long is a Trend Analyst baseline? | "Multi-day" only. No number of days is given. | Pilot data. Too short and normal week-to-week variation flags, too long and a real change is missed. |
| 1.6 | What are the retention windows? | "Facility-set" for features, "enrolment end plus a defined period" for summaries. No defaults. | Local data protection law, which varies by deployment country. |

---

## 2. Definitions the plan uses but does not define

| # | Question | Assumption in the current files | Notes |
|---|---|---|---|
| 2.1 | What is "wear-consistent motion"? | Treated as a boolean the band or classifier can assert. The attendance state machine depends on it entirely. | This is the second of the two attendance conditions, so it carries as much weight as the strap circuit. It needs a real definition before `CLIP_FAILED` means anything. |
| 2.2 | How is `movement_variety_index` computed? | Emitted as a 0 to 1 float. The example payload in the plan shows 0.68. No formula given. | Probably a distribution measure over activity classes within a session. Needs specifying before a parent sees the number. |
| 2.3 | Which activity classes count towards `active_minutes`? | The generator counts windows classified as active classes, with the class list as a constant in the file. | A parent-facing number needs a definition a carer can explain out loud. |
| 2.4 | What is a "fitness session" and how is participation decided? | Emitted as a boolean. The generator sets it from a scheduled window in the day. | Needs a source for the schedule, and a rule for partial participation. |
| 2.5 | What are the grades in "graded anomaly events"? | `spec.md` orders anomalies by precedence but does not name grade levels. | The console needs a ranked worklist, so the grades need naming and mapping to console behaviour. |
| 2.6 | What is the full activity class list? | The generator uses a small placeholder set. | Comes with the labelled dataset, so this is downstream of 1.1. |

---

## 3. Mechanisms named but not described

| # | Question | Assumption in the current files | Notes |
|---|---|---|---|
| 3.1 | How does the clip tool signal the band? | Treated as a second input available at the moment the circuit opens. `spec.md` states that if the signal is absent or ambiguous, the event is classified `CUT` and escalates. | The whole `RELEASED_BY_TOOL` vs `CUT` distinction rests on this. It needs a physical mechanism (magnetic, contact, NFC) that a child cannot reproduce. |
| 3.2 | How is a release attributed to a staff badge? | The plan says release events are attributed to a staff badge rather than to tool possession. No mechanism given. | If the tool is shared, badge attribution needs its own channel. This is the control for the insider row of the threat model, so it matters. |
| 3.3 | How is a band assigned to a child? | Assumed to happen in the dock or on the staff console before clipping. `CLIP_PENDING` requires "band clipped, child assigned". | Also determines what happens when the assignment is wrong. |
| 3.4 | Where does the daily roster come from? | Assumed to be provided to the gateway. `spec.md` defines a degraded mode where a missing roster raises every child as a mismatch rather than failing the day. | Integration with whatever the facility already uses. |
| 3.5 | How does `child_ref` map to a real child, and where is that map held? | `child_ref` is treated as a pseudonymous identifier (`enr-8891`). The cloud payload carries it. | If the map lives in the cloud, the pseudonymisation is weaker than it looks. Our assumption is that it lives on the gateway and in the facility's own enrolment system. |
| 3.6 | Do bands go home with children, or stay at the facility? | Assumed to stay, charged overnight in the dock. | Changes the threat model, the battery requirement, and what an out-of-hours strap event means. |

---

## 4. Inconsistencies in the source plan

| # | Question | How the current files handle it |
|---|---|---|
| 4.1 | Does raw IMU reach the gateway? The storage table says the gateway retains raw IMU samples for a short window, while the pipeline description has the band extracting features and sending only feature windows. | `docs/telemetry-schema.md` reproduces the storage table as written and flags the conflict in place. `spec.md` takes the stricter reading: the band sends features only. This needs deciding, because it changes what a gateway seizure exposes. |
| 4.2 | The precedence order is stated as "safety outranks summary, always" without enumerating the levels below that. | `CLAUDE.md` section 5 enumerates five levels. Levels 1 and 2 follow from the plan directly. The ordering of attendance, summary, and trend below them is ours. |
| 4.3 | Agent types (deterministic vs model-backed) are not stated in the plan. | `CLAUDE.md` assigns them: Movement Classifier and Trend Analyst model-backed, the other three deterministic. The Anomaly Monitor is the arguable one, since prolonged stillness detection could be learned rather than thresholded. We chose deterministic so that no safety event depends on a model. |
| 4.4 | `STRAP_BREACH` returns to `PRESENT` on re-clip, but the strap state machine sends every breach state to `UNCLIPPED` first. | Read as consistent: the strap machine and the attendance machine are separate, and attendance re-enters `PRESENT` only after the two-condition rule is satisfied again. Worth confirming. |

---

## 5. Not yet designed

| # | Item | Note |
|---|---|---|
| 5.1 | Staff console interaction design | The ranked worklist is specified as an output. Its behaviour, acknowledgement flow, and escalation UI are not designed. |
| 5.2 | Consent record schema | Described as a record with scope and expiry. Not modelled. |
| 5.3 | Deletion verification | "Deletion is verifiable" is asserted. The mechanism is not specified. |
| 5.4 | Gateway capacity | Bands per gateway is not stated, and it bounds facility size. |
| 5.5 | Implementation stack | Nothing in the plan fixes a language or runtime for the gateway. |
| 5.6 | Multi-gateway facilities | One gateway per facility is assumed throughout. Large facilities may need more, which raises a handover question for bands moving between coverage areas. |
