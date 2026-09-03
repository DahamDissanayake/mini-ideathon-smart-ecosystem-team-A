# RAID log

Risks, assumptions, issues, and dependencies. An issue is something already
true. A risk is something that might become true. An assumption is something we
have taken as given without evidence. A dependency is something outside our
control that the system needs.

| Type | Item | Mitigation |
|---|---|---|
| Risk | Band becomes an entrapment or ligature hazard | Calibrated breakaway, force specified in the design, detection replaces retention |
| Risk | Mass evacuation with bands attached | Breakaway covers it, no bulk unclip required, documented in facility emergency procedure |
| Risk | Band clipped to an object registers as attendance | Two-condition attendance rule, `CLIP_PENDING` state, motion confirmation window |
| Risk | Trend Analyst produces a behavioural inference about a child | May-not clause in contract, staff review before surfacing, never sent to parents unreviewed |
| Risk | Passive BLE tracking of a specific child from outside the building | Rotating resolvable private addresses |
| Risk | Carers perceive the system as staff surveillance | Group-level reporting only, per-carer metrics not generated at all |
| Risk | Parents perceive the band as restraining their child | Breakaway design disclosed in plain-language consent material |
| Risk | Classifier trained on adult motion misreads child activity | Confidence floor, fail to unknown rather than to a class, staff-labelled bootstrap |
| Risk | Clip tool lost or duplicated | Release events attributed to a staff badge, not to tool possession |
| Risk | Physical compromise of the gateway exposes feature history for the whole facility | Disk encryption and physical siting, both assumed and not yet specified. Facility-set feature retention window bounds the exposure. |
| Risk | Compromised band firmware signs plausible windows with a valid per-device key | Secure boot and signed firmware on the ESP32-S3, provisioning in the dock only. Assumed, not yet specified. |
| Risk | 2.4 GHz jamming silences every band at once | Degrades to facility-wide `SIGNAL_LOST`, which is loud and visible. Strap circuits keep working locally. No further control. |
| Risk | Alert volume trains carers to dismiss alerts | Confidence floor, graded escalation, and a ranked worklist rather than an alarm per event. Not yet validated against a real facility's alert rate. |
| Assumption | Parents will accept a worn device on their child | Consent record, opt-out path, plain-language disclosure |
| Assumption | Facilities have a power source and local network for the gateway | Gateway is a Raspberry Pi 5 with UPS, band buffers through gateway outages |
| Assumption | One gateway covers a facility | Holds for a single-building site. Larger facilities need multiple gateways and a handover rule, which is not designed. |
| Assumption | Bands stay at the facility and charge overnight in the dock | Not stated in the design. Changes the threat model and the battery requirement if wrong. |
| Assumption | `child_ref` to child identity mapping stays inside the facility | If that map ever reaches the cloud, the pseudonymisation is weaker than it looks. |
| Issue | No labelled child activity dataset exists | Bootstrap from staff-labelled sessions during pilot, state as a known limitation |
| Issue | Breakaway force threshold needs empirical validation | Named as a parameter in the spec, not a constant. Pilot-calibrated. |
| Issue | Confidence floor cannot be set until labelled data exists | Downstream of the dataset issue. Until then the Safeguard has no floor to apply. |
| Issue | Signal loss threshold has no measured basis | Needs BLE dropout measurement in a real facility, including dead spots and outdoor areas. |
| Issue | "Wear-consistent motion" is undefined | It is half the attendance rule. Defining it is a prerequisite for `CLIP_FAILED` meaning anything. Logged as question 2.1 in `../OPEN-QUESTIONS.md`. |
| Issue | Clip tool signalling mechanism is not designed | The `RELEASED_BY_TOOL` and `CUT` distinction rests on it. Until it exists, ambiguous releases classify as `CUT` and escalate. |
| Issue | Storage table and pipeline disagree on whether raw IMU reaches the gateway | Stricter reading taken in `spec.md`. Logged as question 4.1 in `../OPEN-QUESTIONS.md`. |
| Issue | No safety certification work has been done on the hardware | The band is a prototype. Certification is a prerequisite for any deployment involving children. |
| Dependency | Gateway uptime and power | Local buffering on band, defined degraded mode, UPS |
| Dependency | Facility willingness to change attendance workflow | Parallel running with the paper register during pilot |
| Dependency | A roster source the gateway can read | Degraded mode runs attendance on clip plus motion alone and raises every child as a mismatch. |
| Dependency | Local data protection law for retention and consent | Retention windows are facility-set for this reason. Deployment country determines the defaults. |
