# Security and privacy

The threat model has four adversaries. Most systems of this kind have one, an
external attacker, and assume the operator is trustworthy. On a system that
watches children inside an institution, that assumption is the thing most worth
questioning.

---

## 1. Threat model

| Actor | Threat | Control |
|---|---|---|
| External attacker | Intercept BLE, track a child by MAC address from the street | LESC bonding, rotating private addresses, per-device keys |
| External attacker | Breach cloud, obtain child movement patterns | Summaries only in cloud. No raw motion exists there to steal. |
| Malicious or curious parent | View another child's data | Safeguard enforces scoped access. Every access logged. |
| Facility management | Use the system to monitor and discipline staff | Facility reporting is group-level and shift-level, never per-carer |
| Insider with clip tool | Remove a band without attribution | Release events logged and attributed to a staff badge, not tool possession |

### On the external attacker rows

Rotating resolvable private addresses matter more than they sound. Without them,
anyone within BLE range of the facility could passively log which child arrived
when, from the street, with a phone, and no credential or compromise would be
required. That is a real privacy attack against children and it is cheap to run.

The cloud breach row is a design property rather than a control. There is no
raw motion in the cloud, so a full compromise of the cloud database yields daily
totals and attendance times. That is not nothing, and we do not claim it is
harmless. It is a great deal less than a per-second movement record of every
child in a facility.

### On the facility row

The facility is an adversary against its own staff. This is not a hypothetical
and we do not soften it.

A system that records where every child is, second by second, also records where
every carer is, because carers are where the children are. Any facility with
access to per-child timelines can derive per-carer timelines from them without
the system offering a single staff-monitoring feature. So the control cannot be
a setting or a report that gets switched off. The control is that per-carer data
is not generated, there is no table holding it, and facility-level reporting is
group-level and shift-level only.

This row decides whether the system deploys at all. If carers believe it is
aimed at them, they will work around it, and the project fails for social
reasons well before it fails for technical ones. A carer who quietly leaves a
band in a drawer defeats every other control in this document.

### On the insider row

The clip tool is a physical object and physical objects get shared, borrowed,
and copied. Attribution therefore cannot rest on possession of the tool. Every
release event is attributed to a staff badge, so the question the audit log
answers is who released this band, rather than which tool released it.

The mechanism for badge attribution is not yet designed, and it is logged as
question 3.2 in [`../OPEN-QUESTIONS.md`](../OPEN-QUESTIONS.md). Until it is,
this control is stated rather than implemented.

---

## 2. Access control matrix

| Data | Parent | Carer | Facility admin | System |
|---|---|---|---|---|
| Raw motion features | No | No | No | Yes, gateway only |
| Activity classifications | No | Yes, own group | Aggregate only | Yes |
| Daily summary | Own child only | Own group | Aggregate only | Yes |
| Attendance record | Own child only | Own group | Yes | Yes |
| Strap and safety alerts | Own child, post-resolution | Yes, own group | Yes | Yes |
| Trend flags | **Never** | Yes, after review | No | Yes |
| Another child's data | **Never** | No | Aggregate only | No |
| Per-carer performance data | No | Own only | **Not generated** | No |

Three rows carry most of the weight.

**Raw motion features, nobody.** No human role in this matrix can read raw
features. They exist on the gateway for the agents to consume, and the access
path for a person does not exist.

**Trend flags, never to a parent.** A pattern deviation flag is an input to a
professional judgement. Sent to a parent unreviewed it becomes a claim about
their child, which the Trend Analyst contract explicitly forbids it from making.

**Per-carer performance data, not generated.** See section 1.

Scoped access is enforced by the Safeguard at the message bus rather than by the
portal UI, so a request that should not be answered is refused before the data
is assembled. Every portal access is logged with who, what, and when.

---

## 3. Link layer, band to gateway

| Property | Choice | Reason |
|---|---|---|
| Transport | BLE 5.0, connection-oriented | Low power, dense device support, mature stack |
| Pairing | LE Secure Connections with bonding | ECDH key agreement, resists passive eavesdropping |
| Key storage | ESP32-S3 secure element, per-device keys | No shared secrets. Compromising one band compromises one band. |
| Identity | Resolvable Private Addresses, rotating | A parked attacker cannot track a specific child by MAC address |
| Payload | AES-128-CCM at link layer | Standard BLE encryption, plus application-layer signing below |
| Integrity | HMAC over each packet with a per-device key | Gateway rejects any packet it cannot authenticate |
| Provisioning | Contactless dock only, never over the air | No field pairing means no pairing attack surface |

---

## 4. Gateway to cloud

| Property | Choice |
|---|---|
| Transport | HTTPS or MQTT over TLS 1.3 |
| Authentication | Mutual TLS with a per-gateway client certificate |
| Certificate lifecycle | Short-lived, automatically rotated, revocable per facility |
| Payload | Summaries only. Schema-validated and rejected if it contains disallowed fields. |
| Buffering | Store and forward on the gateway. Nothing is lost during an outage. |
| Replay protection | Monotonic sequence number and timestamp per gateway |

Per-facility certificate revocation is what makes a single compromised gateway a
bounded incident. Revoking it stops that facility's uploads and touches no other
site.

---

## 5. Guardrails

- **Least privilege.** Each agent reads only the fields its contract names.
  Enforced at the message bus, not by convention.
- **Approved output set.** The Safeguard emits from a finite vocabulary of alert
  and summary types. No free-form generated text reaches a parent or a carer.
- **Append-only audit log.** Every agent decision records inputs seen, agent,
  proposal, Safeguard verdict, and reason. Every portal access records who,
  what, and when.
- **Human override and stop rule.** Any carer can silence, dismiss, or escalate
  any alert. The action is logged and the alert is not deleted.
- **Consent as a system artefact.** Parental consent is a record with a scope
  and an expiry rather than a signature in a filing cabinet. Withdrawal revokes
  portal access and triggers the retention policy.
- **Retention and deletion.** Raw features expire on a facility-set window.
  Summaries expire on enrolment end plus a defined period. Deletion is
  verifiable.

---

## 6. What is not covered

Stated plainly, because a threat model that claims completeness is not credible.

- **Physical compromise of the gateway.** The gateway holds feature history for
  every child in the facility. Disk encryption and physical siting are assumed
  and not specified here.
- **Compromised firmware on a band.** A band running attacker firmware holds a
  valid per-device key and can sign plausible windows. Signed firmware and
  secure boot on the ESP32-S3 are assumed and not specified here.
- **The deletion mechanism.** "Deletion is verifiable" is asserted above. How it
  is verified is question 5.3 in `../OPEN-QUESTIONS.md`.
- **Badge attribution.** See section 1.
- **Denial of service on the BLE band.** Jamming the 2.4 GHz band silences every
  band at once. The system degrades to `SIGNAL_LOST` across the facility, which
  is loud and visible, and the strap circuits keep working locally. There is no
  control here beyond the escalation being obvious.
- **Formal security review.** None has been done. Everything in this document
  is a design intention.
