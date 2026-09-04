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
| 5.6 | Multi-gateway facilities | One gateway per facility is assumed throughout. Large facilities may need more, which raises a handover question for bands moving between coverage areas, and a question about which gateway holds the configuration of record for backup purposes. |

---

## 6. Raised by the telemetry and backup design

| # | Question | Assumption in the current files | What settles it |
|---|---|---|---|
| 6.1 | Should the advertisement telemetry bytes be encrypted, not just authenticated? | They are not. `docs/security.md` section 8 states plainly what an eavesdropper learns: a rotating identifier, a battery level, strap flags, and four motion features, belonging to a band they cannot link across rotations. | A decision on cost. Encrypting under the per-device key means the gateway must try candidate keys before it can decode, which it already does to resolve `adv_id`, so the cost may be smaller than it looks. Needs measuring against a facility-sized fleet. |
| 6.2 | How is the anchor layer simulated? | `mock/generator.py` predates the broadcast topology and emits gateway-side band windows directly, so it exercises the agents and not the ingest path. Nothing tests dedupe, tag verification, or the Zone Resolver. | Extending the generator to emit anchor observation envelopes with plausible per-anchor signal strengths. This is the prerequisite for testing zone resolution at all. |
| 6.3 | What are `adv_dedupe_window` and `anchor_ingest_rate_limit`? | Both unset. `docs/telemetry-pipeline.md` section 10 names them. | Measurement in a real facility. The first decides whether zone resolution works, the second decides whether one broken anchor takes ingest down. |
| 6.4 | Do we escrow a backup key for the per-device band keys, or re-provision after a rebuild? | `docs/backup-recovery.md` section 5 describes escrow under split custody, and names re-provisioning in the dock as the alternative that removes escrow risk entirely at the cost of an evening of staff time. | A facility decision, but we have to ship a default. The tension is real: keys sealed to the platform cannot be restored to new hardware, which is the whole purpose of a backup. |
| 6.5 | Are the RPO and RTO targets right? | The register in `docs/backup-recovery.md` section 2 sets targets against what a daycare could plausibly tolerate. None is measured, and the gateway rebuild target assumes spare hardware exists. | Agreeing them with a real facility during the pilot, and timing an actual rebuild rehearsal. |
| 6.6 | Where does the line sit on health telemetry for a multi-site operator? | Health telemetry stays in the facility by default. A fleet-health rollup for a multi-site operator is described as needing its own allow-list and does not exist. | Whether multi-site operation actually needs it. A fleet health endpoint is exactly where per-band labels would reappear, so it should not be built casually. |
