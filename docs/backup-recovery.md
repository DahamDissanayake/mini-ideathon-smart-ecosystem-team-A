# Data backup and recovery

A backup is a second copy of the facility's data, and by default it is a copy
with weaker access control, weaker encryption, and longer retention than the
original. On a system holding behavioural data about children, an unconsidered
backup strategy undoes the access control matrix in
[`security.md`](security.md) more thoroughly than any attacker would.

So this file answers three questions in order. What is actually worth keeping a
second copy of. What must never be copied. And what happens when the copy has to
be used, including the case where using it conflicts with a deletion request.

The short version: **we back up what is expensive to recreate, and we do not
back up what is cheap to lose.** Most child data in this system is cheap to
lose, and that is a design property rather than an accident.

---

## 1. What each store is worth

Backup decisions follow from what it costs to lose a thing, not from how
important it sounds.

| Store | Cost of losing it | Backed up |
|---|---|---|
| Gateway configuration: anchor-to-zone map, calibration table, parameter set | **Very high.** The calibration table is a physical walk of the building by a person. Losing it means the Zone Resolver falls back to nearest-anchor comparison at low confidence until somebody re-walks the site. | **Yes**, and this is the main reason backups exist |
| Band-to-child assignment and enrolment references | **High.** Recreating it means re-assigning every band by hand before the next session. | **Yes** |
| Per-device band keys | **Very high.** Without them every band must be re-provisioned in the dock, one at a time. | **Yes**, under separate key handling. See section 5. |
| Attendance record | **High.** It is a facility record with legal and operational weight, and it cannot be reconstructed from anything else. | **Yes** |
| Audit log | **High.** An accountability record with a hole in it is not an accountability record. | **Yes**, append-only, integrity-protected |
| Consent records | **High.** The lawful basis for processing. | **Yes** |
| Daily summaries | Medium. They exist in the cloud too, so a gateway loss is not a loss of the record. | **Yes**, until acknowledged by the cloud |
| Trend baselines | Low. They rebuild from summaries over a few weeks. | **Yes**, because rebuilding costs weeks of staff-visible degradation |
| Raw feature windows | **Low, deliberately.** They exist for the agents to consume within a short retention window and have no value after it. | **No.** See section 3. |
| Activity classifications | Low. Derived from features, and already reduced into the daily summary. | **No** |
| Zone assignments, zone history, smoothing state | **Zero, deliberately.** | **Never.** See section 3. |
| Health telemetry | Zero. Operational, short-lived, aggregate. | **No** |
| Band local buffers | Zero. Transient by design, and the band re-advertises. | **No** |

Reading down the "backed up" column, the pattern is that configuration and
records are protected, and observations are not. That is the intended shape. It
keeps the backup set small, which keeps it cheap to encrypt properly, easy to
store in a second room, and quick to restore.

---

## 2. The backup register

**RPO** is the most data a failure may cost. **RTO** is how long the facility
may take to get the function back. Both are targets rather than measurements,
and neither has been validated against a real facility, which is stated again in
section 10.

| Dataset | Where it lives | Method | Frequency | Retention | Encryption | RPO target | RTO target |
|---|---|---|---|---|---|---|---|
| Gateway configuration | Gateway | Full snapshot, versioned | On change, plus daily | 90 days of versions | At rest, facility key | Last change | 1 hour |
| Band keys and assignments | Gateway secure store | Sealed export | On change | Current plus one previous | Separate key, split custody, see section 5 | Last change | 4 hours |
| Attendance record | Gateway | Incremental, daily | Daily, after close | Facility-set, aligned with the paper record | At rest, facility key | 1 day | 4 hours |
| Audit log | Gateway | Append-only replication | Continuous | Facility-set, the longest window in the system | At rest, integrity-protected | Minutes | 1 day |
| Consent records | Gateway and cloud | Included in both | On change | Enrolment plus the legal window | At rest, both tiers | Last change | 4 hours |
| Daily summaries pending upload | Gateway | Included in the daily backup | Daily | Until cloud acknowledges, plus 7 days | At rest, facility key | 1 day | 1 day |
| Trend baselines | Gateway | Weekly snapshot | Weekly | 4 weeks | At rest, facility key | 1 week | 1 week, or rebuild |
| Cloud: summaries, attendance, consent | Cloud | Managed point-in-time recovery, plus periodic export | Continuous, exports weekly | Per the retention policy, and no longer | At rest and in transit, provider-managed plus application-layer | 1 hour | 4 hours |
| Feature windows, classifications, zone data, health metrics | Gateway | **Not backed up** | — | — | — | Total loss accepted | — |

### Where the copies sit

Three copies, two media, one of them off the gateway. This is the ordinary rule
and there is no reason for this system to be an exception.

| Copy | Location | Purpose |
|---|---|---|
| Live | Gateway disk, encrypted | Operations |
| Local backup | Separate encrypted volume, in a different locked room from the gateway | Fast restore after a disk failure |
| Off-site | Encrypted export to the cloud tier, or to facility-managed off-site storage | Survives fire, flood, and theft of the gateway |

**The off-site copy is the one that needs the most care**, because it is the copy
that travels. It contains configuration, keys under separate handling, and
facility records. It does not contain feature windows or zone data, which means
even a total compromise of the off-site copy exposes no child's movement, and
that bound is the direct result of the exclusions in section 3.

---

## 3. What is never backed up, and why

Three exclusions are deliberate and are security controls in their own right.

**Zone assignments and zone history.** These never leave the gateway, which
means they never enter a backup either. A backup is an export, and an export of
zone history is exactly the artefact the facility row of the threat model says
must not exist. Section 2 of [`security.md`](security.md) does not expose zone
history to any human role, and a restorable copy of it would be an access path
that the matrix does not grant.

**Raw feature windows.** They live under `feature_retention_window` precisely so
that a gateway seizure exposes a bounded amount of a child's movement. A backup
extends that window and puts the data on a second medium, which converts a
bounded exposure into an unbounded one. Losing them costs nothing that a carer
can act on: the summary is already built, the alerts have already fired, and no
retrospective analysis of a child's raw motion is a thing this system does.

**Health telemetry.** It is aggregate and short-lived by design, described in
[`telemetry-pipeline.md`](telemetry-pipeline.md) section 7. Backing it up would
extend the life of a dataset whose safety property rests on it being short-lived.

The general rule underneath all three: **a backup inherits the sensitivity of
its contents and loses the retention window that bounded them.** So a store
whose safety property is "it does not exist for long" cannot be backed up
without destroying that property.

---

## 4. Recovery scenarios

What actually happens, per failure, including what the facility does while the
recovery runs.

| Scenario | What is lost | Recovery | Facility during recovery |
|---|---|---|---|
| Gateway disk failure | Live data since the last backup: today's features, classifications, and zone state | Restore configuration, keys, attendance, audit log and consent from the local backup onto replacement hardware | Paper register. Bands keep advertising and keep monitoring straps. |
| Gateway theft or seizure | Everything on it, plus a confidentiality incident | Restore from off-site onto new hardware. Revoke the gateway certificate. Run the incident response plan, including telling parents. | Paper register, and the incident response plan runs in parallel |
| Gateway corruption after a bad update | Depends on when it was noticed | Roll back to the previous configuration version, restore records to the last good point | Paper register for the outage |
| Anchor failure or theft | Nothing. Anchors hold no state that survives a power cycle. | Replace the unit, provision it, add it to the anchor-to-zone map, re-walk that zone for calibration | That zone reads `unknown` rather than being misassigned |
| Band lost or destroyed | That band's unsent queue | Revoke the key, assign a replacement band to the child | The child is on the roster and raised as a mismatch until reassigned |
| Cloud data loss | Parent-visible history | Point-in-time recovery, and re-upload from the gateway forward queue where it is still held | **No safety impact.** The parent portal is stale and the facility is unaffected. |
| Facility loses internet | Nothing. The gateway queues. | Queue drains when the link returns | Fully operational |
| Ransomware on the gateway | Potentially everything live | Rebuild the gateway from clean media, restore from an off-site copy that is not writable by the gateway | Paper register. This is why the off-site copy is write-once from the gateway's perspective. |

Two of these rows deserve saying out loud.

**A gateway loss is never a safety event.** Straps are monitored on the band,
bands keep advertising, and breaches keep being registered locally. What the
facility loses is the console and the automated register, and the fallback is
the register it used before this system existed. The design assumption is that a
facility can run a day on paper, which is true and is why parallel running
during the pilot is a dependency in [`raid.md`](raid.md).

**The off-site copy must not be writable by the gateway that produced it.** A
backup an attacker on the gateway can encrypt or delete is not a backup. Whether
that is object-lock storage, append-only credentials, or a pull-based backup
initiated from elsewhere, the property is the same, and it is not yet specified.

---

## 5. Backup encryption and keys

Backups are encrypted at rest with a facility key. The one interesting problem
is the band keys.

Per-device band keys are held on the gateway, and section 5.3 of
[`security.md`](security.md) wants them sealed to the platform, so that a stolen
disk is inert. Sealed to the platform means they cannot be restored onto new
hardware, and the whole point of a backup is to restore onto new hardware after
the old hardware is gone. The two requirements are in direct tension, and both
are real.

The resolution is that the key backup is a **separate artefact under different
handling** from every other backup:

- Encrypted under a key that is not on the gateway, and never has been.
- Split custody: the recovery key is held in parts, and no single person can
  reconstruct it. In practice that means the named data controller and one other
  role, per section 4 of [`security.md`](security.md).
- Used only during a rebuild, never mounted during normal operation.
- Every use logged and reported to the controller, because a key restore is
  indistinguishable from a key theft in every respect except authorisation.

**The alternative is re-provisioning.** If a facility would rather not hold an
escrowed key at all, the recovery path for band keys is to re-provision every
band in the dock, which costs an evening of staff time for a facility-sized
fleet and removes the escrow risk completely. That is a legitimate choice and
the facility makes it, not us. Which default we ship is question 6.4 in
[`../OPEN-QUESTIONS.md`](../OPEN-QUESTIONS.md).

---

## 6. Backup integrity

A backup nobody has verified is a hypothesis about a backup.

- **Checksums on write and on read.** A silently corrupted backup is worse than
  a missing one, because it is discovered at the worst moment.
- **The audit log copy is integrity-protected**, chained so that a modification
  in the middle of the copy is detectable. An audit log that can be quietly
  edited in backup form defeats the append-only property of the live one.
- **Backup completion is monitored**, and a failed or skipped backup raises a
  gateway health alert. Backup failures are almost always noticed weeks late,
  and the fix is making the failure loud on the day it happens.
- **Restores are tested**, see section 8.

---

## 7. Backups, deletion, and consent withdrawal

This is the section where a backup policy and a privacy policy collide, and
where most systems quietly choose the backup.

Consent withdrawal and a deletion request both trigger the retention policy in
section 4.3 of [`security.md`](security.md). Deleting from live storage is
straightforward. Deleting from a backup is not: backups are point-in-time
copies, and editing one to remove a child breaks its integrity guarantees and
its checksums.

Four mechanisms, in the order they do the work:

1. **Exclusion does most of it.** The bulk of a child's personal data, meaning
   raw features, classifications, and zone data, is never backed up in the first
   place. Deleting it from live storage deletes it, full stop. This is the
   strongest argument for the exclusions in section 3, and it is worth more than
   any deletion mechanism we could build.
2. **Short backup retention on the rest.** The backup set that does contain
   child data is attendance records, consent records, and daily summaries, on a
   defined retention window. A deletion request is satisfied in live storage
   immediately, and in backups by expiry, on a window the facility has recorded
   and can state to a parent.
3. **A deletion log that survives restore.** Deletions are recorded in a
   tombstone list that is itself backed up. On any restore, the tombstone list is
   replayed before the system accepts traffic, so a restored backup cannot
   resurrect a child whose data was deleted. This is the mechanism that makes
   "deletion is verifiable" survive a restore.
4. **The audit log is exempt, and we say so.** Accountability records about
   decisions the system made are retained on their own window, because deleting
   them on request would delete the evidence of how a child was treated. The
   entries hold a `child_ref` and no name. What a facility tells a parent about
   this exemption is a matter for the DPIA, not for us to decide silently.

What we do not claim is that a deletion request results in immediate erasure
from every backup copy. It does not, in this design or in most designs, and
saying otherwise would be false. What we claim is that the window is short, that
it is written down, that it applies to a small and named set of data, and that a
restore cannot bring deleted data back into service.

The verification mechanism for all of this is question 5.3 in
[`../OPEN-QUESTIONS.md`](../OPEN-QUESTIONS.md), and it remains unsolved.

---

## 8. Rehearsal

A restore that has never been performed takes longer than anyone expects and
fails in ways nobody predicted.

| Rehearsal | Cadence | Evidence |
|---|---|---|
| Restore configuration onto spare hardware | Quarterly | Timed, recorded against the RTO target |
| Restore attendance and audit records, verify integrity | Quarterly | Checksum verification and a spot check against the paper register |
| Full gateway rebuild from off-site, including keys | Annually, and after any change to the key handling in section 5 | Timed. The one rehearsal that proves the escrow works. |
| Cloud point-in-time recovery | Annually | Provider-side, evidence retained |
| Tombstone replay after restore | With every restore rehearsal | A deleted `child_ref` is confirmed absent after the restore |

The rehearsal record is an administrative control and is listed as one in the
register in [`security.md`](security.md) section 7. Its status there is
**designed**, which is accurate: none of these has been performed, because there
is no deployment.

---

## 9. What this costs

Worth stating because backup designs are often written as if storage and staff
time were free.

- The backup set is small. Excluding features and zone data means it is
  configuration, keys, and records, which is megabytes rather than gigabytes for
  a facility-sized deployment.
- The expensive part is not storage, it is the quarterly rehearsal and the split
  custody of the recovery key. Both are staff time, and both are the parts most
  likely to lapse after the first year.
- The cheapest risk reduction available here is the exclusion policy in section
  3, which costs nothing and removes most of the exposure.

---

## 10. What is not covered

- **No RPO or RTO target here has been validated.** They are targets set against
  what a daycare could plausibly tolerate, and a real facility may need
  different ones. The gateway rebuild target in particular assumes spare
  hardware exists, which is a procurement question nobody has answered.
- **The off-site write-once mechanism is not specified.** Section 4 names the
  property and not the implementation.
- **Backup key escrow versus re-provisioning is undecided.** See section 5 and
  question 6.4.
- **Deletion verification across backups is unsolved.** See section 7 and
  question 5.3.
- **Multi-gateway facilities are not addressed.** One gateway per facility is
  assumed throughout, and a second gateway raises a question about which one
  owns the configuration of record. Logged as question 5.6.
- **No backup has ever been taken or restored**, because there is no deployment.
  Everything in this file is a design intention.
