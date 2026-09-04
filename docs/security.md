# Security and privacy

The threat model has four adversaries. Most systems of this kind have one, an
external attacker, and assume the operator is trustworthy. On a system that
watches children inside an institution, that assumption is the thing most worth
questioning.

Sections 1 and 2 say what we are defending against and who may see what.
Sections 3 to 7 are the controls, organised as administrative, technical, and
physical, because a control set that is only technical is not a control set. A
rotating identifier is worthless if the gateway sits unlocked in a corridor, and
disk encryption is worthless if nobody ever reviews who still has a portal
account. Sections 8 and 9 cover the links, and section 10 states plainly what is
not covered.

---

## 1. Threat model

| Actor | Threat | Control |
|---|---|---|
| External attacker | Passively log which child arrived when, from the street, with a phone | Rotating BLE address and rotating `adv_id` inside the payload. Both rotate, or neither is worth having. |
| External attacker | Forge or replay a band advertisement | Truncated per-device HMAC tag over the advertisement, sequence number inside the authenticated bytes, verification failures rate-limited and logged |
| External attacker | Breach cloud, obtain child movement patterns | Summaries only in cloud. No raw motion and no zone data exists there to steal. |
| Compromised anchor | Claim a zone, forge a band, or identify a child | Anchors hold no keys and no zone map. They forward bytes and a signal strength. Resolution, authentication and zone assignment all happen on the gateway. |
| Malicious or curious parent | View another child's data | Safeguard enforces scoped access at the message bus. Every access logged. |
| Facility management | Use the system to monitor and discipline staff | Facility reporting is group-level and shift-level, never per-carer |
| Insider with clip tool | Remove a band without attribution | Release events logged and attributed to a staff badge, not tool possession |

### On the external attacker rows

Rotating identifiers matter more than they sound. Without them, anyone within
BLE range of the facility could passively log which child arrived when, from the
street, with a phone, and no credential or compromise would be required. That is
a real privacy attack against children and it is cheap to run.

Under a broadcast topology this is the dominant privacy control, because there
is no link-layer encryption on an advertisement nobody is connected to. Section
8 states what an eavesdropper can and cannot learn.

The cloud breach row is a design property rather than a control. There is no raw
motion and no zone data in the cloud, so a full compromise of the cloud database
yields daily totals and attendance times. That is not nothing, and we do not
claim it is harmless. It is a great deal less than a per-second movement record
of every child in a facility.

### On the compromised anchor row

Anchors are mains-powered devices screwed to a wall in a room full of people.
Physically they are the most reachable part of the system, so the design assumes
one will eventually be compromised and makes that cheap. An anchor that lies can
report a signal strength that is not true, which degrades zone confidence for
the zone it covers. It cannot forge a band, because it holds no key. It cannot
identify a child, because `adv_id` rotates and only the gateway resolves it. It
cannot assign a zone, because the anchor-to-zone map is gateway-side.

Zone data never stands alone, so the worst a lying anchor achieves is a wrong
room in an alert a carer is already walking towards.

### On the facility row

The facility is an adversary against its own staff. This is not a hypothetical
and we do not soften it.

A system that records which room every child is in also records where every
carer is, because carers are where the children are. Any facility with access to
per-child zone timelines can derive per-carer timelines from them without the
system offering a single staff-monitoring feature. So the control cannot be a
setting or a report that gets switched off. The control is that per-carer data
is not generated, there is no table holding it, zone history is not exposed to
an administrator, and facility-level reporting is group-level and shift-level
only.

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
| Zone assignment, current | No | Yes, own group | No | Yes, gateway only |
| Zone history across a day | **Never** | No | **Not exposed** | Yes, gateway only |
| Daily summary | Own child only | Own group | Aggregate only | Yes |
| Attendance record | Own child only | Own group | Yes | Yes |
| Strap and safety alerts | Own child, post-resolution | Yes, own group | Yes | Yes |
| Trend flags | **Never** | Yes, after review | No | Yes |
| Another child's data | **Never** | No | Aggregate only | No |
| Per-carer performance data | No | Own only | **Not generated** | No |
| Audit log | No | No | Read-only, no delete | Append only |
| Backup media and restore | No | No | Request a restore, no direct read | Yes, see [`backup-recovery.md`](backup-recovery.md) |

Five rows carry most of the weight.

**Raw motion features, nobody.** No human role in this matrix can read raw
features. They exist on the gateway for the agents to consume, and the access
path for a person does not exist.

**Zone history, nobody, including the facility admin.** A carer sees where to
look for a child now. Nobody gets a queryable record of which room a child was
in through the day, because that record is also a record of which room each
carer was in. The Day Summariser reduces zone occupancy to a single variety
figure and the assignments underneath it stay on the gateway.

**Trend flags, never to a parent.** A pattern deviation flag is an input to a
professional judgement. Sent to a parent unreviewed it becomes a claim about
their child, which the Trend Analyst contract explicitly forbids it from making.

**Per-carer performance data, not generated.** See section 1.

**Backups, no direct read.** A backup is a copy of production data with weaker
access control unless somebody deliberately gives it the same access control. An
admin can request a restore, which is approved and logged. An admin cannot mount
a backup and read it.

Scoped access is enforced by the Safeguard at the message bus rather than by the
portal UI, so a request that should not be answered is refused before the data
is assembled. Every portal access is logged with who, what, and when.

---

## 3. How the controls are organised

Every control in this document is one of three kinds, and the three answer
different failure modes. A control set weighted entirely towards one kind fails
in the ways the other two would have caught.

| Class | What it is | What it cannot do |
|---|---|---|
| **Administrative** | Policy, process, roles, training, review, and consent. What people are required to do, and what the organisation is required to check. | Stop anything by itself. An administrative control nobody audits is a sentence in a document. |
| **Technical** | What the system enforces in code or in silicon. Cryptography, schema validation, least privilege at the message bus, the Safeguard veto. | Cover what happens away from the keyboard. No amount of encryption addresses a gateway carried out of the building. |
| **Physical** | Control over objects and places. Locks, mounting, custody of the clip tool and the dock, siting of the gateway, disposal of hardware. | Constrain what an authorised person does once they are legitimately inside. |

Section 7 maps every control to its class, its tier, the threat it answers, and
whether it is implemented, designed, or assumed. The status column is the honest
one. A great deal of this is designed and not built, and a register that hides
that is worse than no register.

---

## 4. Administrative controls

Process, policy, and the reviews that make the technical controls mean
something. These bind the operator, not the code.

### 4.1 Governance and accountability

- **A named data controller per facility.** The facility, not the project, is
  the controller for child data. The project supplies the gateway and the
  contract saying what it may do. Without a named accountable person there is
  nobody to set a retention window or approve a restore.
- **A data protection impact assessment before deployment.** This system
  processes behavioural data about children inside an institution. A DPIA is a
  legal requirement in most deployment countries, and it is the right document
  to force the questions in `../OPEN-QUESTIONS.md` to be answered by someone
  other than the engineers.
- **Change control on the Safeguard.** The Safeguard has no run-time override
  path, which means its rules change only by a code change. That change is
  reviewed by someone who did not write it, and the review is recorded. This is
  the administrative half of the "no override path" guarantee, and without it
  the technical half is only a habit.
- **Change control on the agent contracts.** The *May not* clauses in
  `../CLAUDE.md` change by the same route. An agent that quietly gains a field
  it is not contracted to read is a contract change, not a bug fix.
- **A deployment sign-off gate.** No facility goes live until the register in
  section 7 has no **assumed** rows in the physical column. That gate is the
  practical purpose of the register.

### 4.2 People

- **Role definitions that match the access matrix.** Parent, carer, facility
  admin. A person holds one role per facility, and the role is granted by the
  named controller rather than by whoever is at the console.
- **Joiners, movers, leavers.** A carer who leaves loses console access the same
  day. This is the control that fails most often in real deployments, and it
  fails silently, which is why it is paired with the review below.
- **Quarterly access review.** The controller reviews who holds which role and
  which parent accounts exist. Accounts with no matching enrolment are disabled.
  The review is recorded with a date and a name.
- **Training on what the system does not do.** Carers are told, in the session
  that teaches them the console, that the band cannot restrain a child, cannot
  diagnose anything, and produces flags rather than conclusions. A carer who
  believes a trend flag is a finding will act on it as one.
- **Training on the alert vocabulary.** Which alerts escalate immediately, what
  `SIGNAL_LOST` actually means, and why an `unknown` zone is a correct answer
  rather than a fault. This is the half of the alert-fatigue countermeasure that
  a confidence floor cannot supply.
- **Custody policy for the clip tool and the dock**, naming which roles may hold
  each. The insider row of the threat model rests on it.

### 4.3 Consent and transparency

- **Consent as a system artefact.** Parental consent is a record with a scope
  and an expiry rather than a signature in a filing cabinet. Withdrawal revokes
  portal access and triggers the retention policy, including the backup handling
  in [`backup-recovery.md`](backup-recovery.md) section 7.
- **Plain-language disclosure.** Parents are told that the band comes off under
  load by design, that no audio or video exists, that no location of any kind
  leaves the building, and what a daily summary contains. Consent obtained
  without this is not consent to this system.
- **An opt-out path that does not disadvantage a child.** A child without a band
  is on the paper roster, and the Attendance Manager raises them as a known and
  suppressed mismatch rather than a daily alert.
- **Staff consultation before deployment.** The facility row of the threat model
  is a social risk, and the mitigation is that carers see the
  group-level-reporting guarantee in writing before the first band is clipped.

### 4.4 Operations

- **Retention windows set per facility, in writing.** Features, classifications,
  zone state, audit log, and backups each get a number, set against local law by
  the named controller. "Facility-set" with no recorded value is not a policy.
- **Audit log review cadence.** An append-only log that nobody reads is the
  normal outcome. The controller reviews Safeguard rejections and portal access
  anomalies monthly, and the review is itself logged.
- **Incident response plan.** Who is called for a suspected gateway compromise,
  a lost band, a lost clip tool, or a certificate compromise; what gets revoked;
  and who tells the parents. Certificate revocation is a technical control.
  Deciding to use it at three in the morning is an administrative one.
- **Firmware release policy.** Signed builds only, versioned, provisioned in the
  dock, recorded against the band. `fw_version` and `model_version` travel with
  the telemetry so a bad release is traceable through the audit log.
- **Model release policy.** A classifier version is released against a recorded
  validation set and a recorded confidence floor. A model change that moves the
  false-positive rate on the staff console is a change that needs approving.
- **Restore authorisation.** A restore from backup is requested, approved by the
  controller, and logged. See [`backup-recovery.md`](backup-recovery.md).
- **Backup restore rehearsal.** A backup that has never been restored is a
  hypothesis. Rehearsal cadence and evidence are in
  [`backup-recovery.md`](backup-recovery.md) section 8.
- **Supplier and dependency review.** The gateway runs third-party code. Which
  packages, which versions, and who watches their advisories is an operator
  responsibility and is not specified here.

---

## 5. Technical controls

What the system enforces itself, in code or in silicon. These are the controls
that hold when nobody is watching.

### 5.1 Identity and cryptography

- **Per-device keys in ESP32C3 eFuse**, not readable by application firmware.
  Compromising one band compromises one band.
- **Truncated HMAC-SHA256 tag on every advertisement.** The gateway rejects
  anything it cannot authenticate, and no anchor is trusted to do that check.
- **Rotating `adv_id` in the payload, and rotating resolvable private addresses
  at the link layer.** Each rotates on its own period. Rotating one alone
  achieves nothing, because an attacker tracks whichever one stayed still.
- **Sequence number inside the authenticated bytes.** A captured advertisement
  cannot be replayed, because the gateway rejects a sequence number it has
  already seen for that band.
- **Rate limiting and logging on tag verification failure**, per anchor and per
  `adv_id`. Truncation to eight bytes is a real weakening, and this is what
  makes brute force against it visible rather than silent.
- **Mutual TLS with a short-lived per-gateway certificate** on the cloud link,
  automatically rotated and revocable per facility.
- **Provisioning in the contactless dock only.** No field pairing means no
  pairing attack surface.

### 5.2 Data flow and minimisation

- **Least privilege at the message bus.** Each agent reads only the fields its
  contract names. Enforced at the bus, not by convention.
- **`additionalProperties: false` at cloud ingest.** A payload carrying a field
  outside the allowed set is rejected by the validator rather than by review.
  Minimisation is a property of the code path.
- **Zone data has no cloud representation.** There is no field that could carry
  a zone, so there is no misconfiguration that leaks one.
- **Approved output set.** The Safeguard emits from a finite vocabulary of alert
  and summary types. No free-form generated text reaches a parent or a carer.
- **Confidence floor and fail-to-`unknown`.** Below the floor the Safeguard
  suppresses and logs. The system does not surface a hedged result.
- **Health telemetry is aggregate-only.** Operational metrics about anchors and
  the gateway carry no `child_ref` and no per-band series, so monitoring cannot
  become a second, unregulated location log. See
  [`telemetry-pipeline.md`](telemetry-pipeline.md) section 7.

### 5.3 Platform and storage

- **Full-disk encryption on the gateway**, with the key sealed to the platform
  so a removed disk is inert. Assumed and not yet specified. See section 10.
- **Secure boot and signed firmware on bands and anchors.** Assumed and not yet
  specified.
- **Network segmentation for anchors.** Anchors sit on their own VLAN or SSID,
  with a route to the gateway ingest port and to nothing else. A compromised
  anchor reaches the gateway and no other facility system.
- **The band holds no network credentials.** A lost or stolen band is not a
  route into the facility network, because there is nothing on it to use.
- **Append-only audit log.** Every agent decision records inputs seen, agent,
  proposal, Safeguard verdict, and reason. Every portal access records who,
  what, and when. No role in the access matrix can delete from it.
- **Encrypted backups with independently held keys.** A backup restorable by
  whoever finds it is a second copy of the facility's data with no access
  control on it. See [`backup-recovery.md`](backup-recovery.md) section 5.
- **Retention enforced by a scheduled job, not by intention.** Expiry runs on
  the gateway, is logged, and covers backups as well as live data.

### 5.4 Availability

- **UPS on the gateway**, so a common power blip does not become a paper-register
  day.
- **Store and forward at every hop.** The band buffers when unheard, anchors
  buffer briefly, the gateway buffers for the cloud. No hop drops data because
  the next one is unavailable.
- **ESP-NOW fallback for anchors** when facility WiFi is down, so zone detection
  survives a network failure.
- **No safety function depends on the WAN link.** Losing the internet loses the
  parent portal and nothing else.

---

## 6. Physical controls

Every part of this system is an object in a building full of children. Physical
controls are not an afterthought here. They decide what the technical controls
are worth.

### 6.1 The gateway

- **Locked, ventilated cabinet in a staff-only room.** The gateway holds feature
  history and zone state for every child in the facility, and it is the only
  tier holding band keys. It is the highest-value object in the building.
- **No accessible ports on the enclosure.** USB and console access sits behind
  the same lock, because a gateway with an exposed USB port is a gateway with an
  exposed disk.
- **Tamper-evident seal**, checked on the same cadence as the access review.
  Detection rather than prevention, which is the same philosophy as the strap.
- **Sited away from public areas and away from the perimeter.** A gateway in a
  reception area is a gateway that leaves in a bag.
- **Mains plus UPS, on a circuit that is not the one the kettle is on.**

### 6.2 The anchors

- **Mounted high and out of reach**, one per zone, on a fixed bracket rather
  than a shelf. An anchor that gets moved silently redraws a zone boundary,
  which is a correctness problem before it is a security one.
- **Positions recorded in the anchor-to-zone map at deployment.** Moving an
  anchor requires a map change and a re-run of the calibration walk.
- **Assumed compromisable, therefore holding nothing.** See section 1.
- **Anchor coverage checked against the perimeter at deployment.** Coverage that
  extends well past the building line makes passive observation from outside
  easier, and it is a siting decision rather than a software one.

### 6.3 Bands, dock, and clip tool

- **Bands stay at the facility and charge overnight in the dock.** This is an
  assumption in [`raid.md`](raid.md) and it is also a physical control: a band
  that goes home is a band outside every control in this document.
- **The dock is in a staff-only area.** Provisioning and firmware update happen
  only there, one device at a time, so physical custody of the dock gates both.
- **The clip tool is signed in and out**, with custody recorded against a
  person. The tool is not the attribution mechanism, the badge is, but a tool
  nobody can account for is a tool used at the wrong time.
- **Decommissioning wipes and destroys.** A retired band holds a per-device key
  in eFuse and a rolling sample buffer. Decommissioning revokes the key at the
  gateway and physically destroys the module rather than putting it in a drawer.
- **Lost band procedure.** Reported, key revoked at the gateway, band marked
  unassignable. A found band whose key is revoked authenticates as nothing.

### 6.4 Media and paper

- **Backup media held to the same standard as the gateway**, and in a different
  room from it. A backup in the same cabinet fails to the same fire.
- **The paper register fallback is a personal data record.** It is stored locked
  and destroyed on the same retention window as the electronic attendance
  record, because a degraded-mode day still produced a list of which children
  were present.
- **Visitors and contractors escorted in the room holding the gateway.** Stated
  because network segmentation does not survive somebody unplugging a thing.

---

## 7. The control register

Every control, its class, and its honest status. **Implemented** means it exists
in this repository, or in the design at a level someone could build from without
inventing the mechanism. **Designed** means the mechanism is specified and
nothing is built. **Assumed** means we are relying on it and have not specified
it at all.

| Control | Class | Tier | Threat answered | Status |
|---|---|---|---|---|
| Per-device keys in eFuse | Technical | Band | One compromised band compromising others | Designed |
| Truncated HMAC tag on every advertisement | Technical | Band, gateway | Forged bands | Designed |
| Sequence number inside authenticated bytes | Technical | Band, gateway | Replay | Designed |
| Rotating `adv_id` | Technical | Band | Passive tracking of a child | Designed |
| Rotating resolvable private address | Technical | Band | Passive tracking of a child | Designed |
| Rate limit and log tag verification failures | Technical | Gateway | Brute force against a truncated tag | Designed |
| Anchors hold no keys and no zone map | Technical | Anchor | A compromised anchor forging or identifying | Designed |
| Anchor VLAN routed only to the gateway | Technical | Anchor, network | A compromised anchor pivoting | Assumed |
| Least privilege at the message bus | Technical | Gateway | Agent scope creep | Designed |
| Safeguard veto, no override path | Technical | Gateway | Unreviewed output reaching a human | Designed |
| Confidence floor, fail to `unknown` | Technical | Gateway | A guess presented as a finding | Designed, floor unset |
| `additionalProperties: false` at ingest | Technical | Cloud | Minimisation drifting over time | **Implemented**, `schema/telemetry.schema.json` |
| Zone data has no cloud representation | Technical | Cloud | Location leaving the building | **Implemented**, by omission from the schema |
| Aggregate-only health telemetry | Technical | Gateway | Monitoring becoming a shadow location log | Designed |
| Mutual TLS, short-lived per-gateway certificate | Technical | Gateway, cloud | Gateway impersonation | Designed |
| Per-facility certificate revocation | Technical | Cloud | Bounding a gateway compromise | Designed |
| Append-only audit log | Technical | Gateway | Undetected misuse | Designed |
| Full-disk encryption on the gateway | Technical | Gateway | Gateway theft or seizure | Assumed |
| Secure boot and signed firmware | Technical | Band, anchor | Attacker firmware signing plausible windows | Assumed |
| Encrypted backups, keys held separately | Technical | Gateway, cloud | Backup media as an uncontrolled second copy | Designed |
| Scheduled retention and expiry job | Technical | Gateway, cloud | Data outliving its purpose | Designed |
| UPS and store-and-forward at every hop | Technical | All | Availability loss becoming data loss | Designed |
| Named data controller per facility | Administrative | Facility | Nobody accountable for a decision | Assumed |
| DPIA before deployment | Administrative | Facility | Processing children's data unassessed | Assumed |
| Change control on Safeguard and agent contracts | Administrative | Project | Silent erosion of the *May not* clauses | Assumed |
| Deployment sign-off against this register | Administrative | Project | Going live on assumptions | Assumed |
| Joiners, movers, leavers | Administrative | Facility | Stale accounts | Assumed |
| Quarterly access review | Administrative | Facility | Stale accounts, silently | Assumed |
| Carer training on what the system does not do | Administrative | Facility | A flag read as a finding | Assumed |
| Consent record with scope and expiry | Administrative | Facility, cloud | Processing with no lawful basis | Designed |
| Retention windows recorded per facility | Administrative | Facility | "Facility-set" meaning unset | Assumed |
| Monthly audit log review | Administrative | Facility | An append-only log nobody reads | Assumed |
| Incident response plan | Administrative | Facility | Slow revocation | Assumed |
| Firmware and model release policy | Administrative | Project | An untraceable bad release | Partly. Versions travel in the payload. |
| Restore authorisation and logging | Administrative | Facility | Restore used as an unlogged read path | Designed |
| Backup restore rehearsal | Administrative | Facility | A backup nobody has ever restored | Designed |
| Locked cabinet in a staff-only room | Physical | Gateway | Theft and physical compromise | Assumed |
| Tamper-evident seal on the gateway | Physical | Gateway | Undetected physical access | Assumed |
| Anchors mounted high, on fixed brackets | Physical | Anchor | Tampering, and silent zone redefinition | Assumed |
| Anchor moves require map change and recalibration | Physical | Anchor | The zone map drifting from the building | Designed |
| Dock in a staff-only area | Physical | Band | Unauthorised provisioning or firmware load | Assumed |
| Bands stay on site, charged in the dock | Physical | Band | Bands outside every other control | Assumed |
| Clip tool signed in and out | Physical | Facility | Unattributed release | Assumed |
| Decommission revokes the key and destroys the module | Physical | Band | Live keys in a drawer | Assumed |
| Lost band reported and key revoked | Physical, technical | Band, gateway | A found band still authenticating | Designed |
| Backup media in a different room from the gateway | Physical | Facility | One fire taking both copies | Designed |
| Paper register held and destroyed as a record | Physical | Facility | Degraded-mode data escaping the policy | Assumed |

Counting the statuses is the point of the table. Most of what protects a child
in this design is currently **assumed**, and the assumptions concentrate in the
administrative and physical columns, which is exactly where a project run by
engineers under-invests. The register exists so that this is visible rather than
implied.

### The three classes working together

A control class on its own leaves a gap the other two close. Three threats,
traced across all three columns:

| Threat | Administrative | Technical | Physical |
|---|---|---|---|
| The gateway is stolen | Incident response names who revokes the certificate and who tells the parents | Full-disk encryption, per-facility revocation, short feature retention bounding the exposure | Locked cabinet, staff-only room, tamper seal, sited away from public areas |
| A child is tracked from the street | The DPIA identifies the attack, disclosure tells parents it was considered | `adv_id` and BLE address both rotate, the payload carries no stable identity | Anchor and gateway siting does not extend usable coverage past the perimeter |
| A carer is disciplined using the system | Group-level reporting agreed with staff in writing, a controller accountable for it | Per-carer data not generated, zone history not exposed to an admin, access enforced at the bus | The console is sited in the staff area, not in a manager's office |

---

## 8. Link layer, band to anchors

The band broadcasts and never connects, so the controls here are not the ones a
connection-oriented BLE design would use. There is no bonding, no session key,
and no link-layer encryption, because there is no link.

| Property | Choice | Reason |
|---|---|---|
| Transport | BLE 5.0, connectionless advertising | No association means no credentials on the band and no connection state to attack |
| Identity | Rotating `adv_id` in the payload, plus rotating resolvable private addresses | Rotating one and not the other achieves nothing |
| Key storage | ESP32C3 eFuse, per-device keys, not readable by application firmware | Compromising one band compromises one band |
| Integrity | HMAC-SHA256 over bytes 0 to 17, truncated to eight bytes | Budget-limited. Makes forgery expensive, and the gateway rate-limits and logs failures. |
| Replay | Sequence number inside the authenticated bytes | The gateway rejects a sequence number it has already seen for that band |
| Confidentiality | **None over the air.** See below. | There is no session to encrypt under, and the 26-byte budget is already spent |
| Provisioning | Contactless dock only, one device at a time, never in the field | No field pairing means no pairing attack surface |

**The advertisement is authenticated and not encrypted, and we state that
plainly.** An eavesdropper in range reads a rotating identifier, a battery
percentage, strap flags, and four motion features, belonging to an unnamed band,
until the identifier rotates again. What they cannot do is link two rotation
epochs to the same band, attach a band to a child, forge a window, or replay one.

What they can do is observe that some band in range had its breach flag set,
which reveals that a strap somewhere in the building opened. Whether the
telemetry bytes should be encrypted under the per-device key, at the cost of the
gateway trying candidate keys before it can decode, is an open design question
and is logged as question 6.1 in
[`../OPEN-QUESTIONS.md`](../OPEN-QUESTIONS.md).

---

## 9. Anchor to gateway, and gateway to cloud

### Anchor to gateway

| Property | Choice |
|---|---|
| Transport | WiFi to the gateway, ESP-NOW as fallback |
| Network position | Dedicated VLAN or SSID, routed only to the gateway ingest port |
| Anchor authentication | Per-anchor credential, so the gateway knows which anchor is claiming a signal strength |
| What an anchor may assert | Its own identifier, a received signal strength, a receive timestamp, and the bytes it heard, unmodified |
| What an anchor may not assert | A zone, a band identity, or the validity of an advertisement |
| Trust level | Low by design. The gateway re-verifies everything and treats signal strength as a claim, not a measurement it owns. |

The envelope, the deduplication rule, and what the gateway does when anchors
disagree are in [`telemetry-pipeline.md`](telemetry-pipeline.md).

### Gateway to cloud

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

## 10. What is not covered

Stated plainly, because a threat model that claims completeness is not credible.

- **Physical compromise of the gateway.** The gateway holds feature history and
  zone state for every child in the facility. Disk encryption and physical
  siting are named as controls in sections 5 and 6, and neither is specified.
- **Compromised firmware on a band.** A band running attacker firmware holds a
  valid per-device key and can sign plausible windows. Signed firmware and
  secure boot on the ESP32C3 are assumed and not specified here.
- **Confidentiality of the advertisement.** It is authenticated and not
  encrypted. See section 8 and question 6.1.
- **The deletion mechanism.** "Deletion is verifiable" is asserted here and in
  [`backup-recovery.md`](backup-recovery.md). How it is verified across backups
  is question 5.3 in `../OPEN-QUESTIONS.md`.
- **Badge attribution.** See section 1.
- **Denial of service on the BLE band.** Jamming 2.4 GHz silences every band at
  once. The system degrades to `SIGNAL_LOST` across the facility, which is loud
  and visible, and the strap circuits keep working locally. There is no control
  here beyond the escalation being obvious.
- **A hostile anchor flooding the gateway.** Per-anchor ingest rate limiting is
  named in `telemetry-pipeline.md` and is not sized. An anchor forwarding
  garbage at line rate is an availability problem we have not measured.
- **Supply chain for third-party gateway dependencies.** Named as an
  administrative responsibility in section 4.4 and not specified.
- **Formal security review.** None has been done. Everything in this document
  is a design intention.
