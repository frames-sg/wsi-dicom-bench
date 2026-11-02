# WSI-DICOM Negative Bench v6

This protocol governs manifest-v6.json, expected-results-lock-v6.json, catalog v6
(`rules/wsi-dicom-bench-rules-2026c-v6.json`), core profile v4
(`rules/wsi-dicom-core-profile-2026c-v4.json`), the controls in controls-v4 and controls-v6, and
`rules/wsi-dicom-requirements-2026c-v1.json`. The suite evaluates a `wsi-dicom` candidate
against DICOM 2026c VL Whole Slide Microscopy Image Storage. It is not an independent blinded
replication: cases and expected failures are authored with knowledge of the rules.

The suite has 14 controls (15 objects), 10 development entries, and 352 evaluation cases. The
controls are repository-generated synthetic objects with no patient data: fresh deterministic
derivatives of the sealed PHI-free 4x4 research fixtures, built from controls-v2 by
`build_core_profile_controls.py`. They cover Explicit VR Little Endian, JPEG Baseline, lossless
and lossy JPEG 2000, and lossless, RPCL, and lossy HTJ2K; implicit frame positions; MONOCHROME2
at 8 and 16 bits in Explicit VR Little Endian; and a two-level pyramid whose derived level is a
deterministic nearest-neighbor reduction of its referenced source, with the required coded
Derivation Image functional group. The 16-bit control does not cover every compressed syntax and
bit-depth pair. Twelve controls are the files in controls-v4. The lossy JPEG 2000 controls
CP05-J2K-LOSSY-4F and CP08-HTJ2K-LOSSY-4F are the files in controls-v6: their Frames code their
components with the irreversible multiple component transformation, which PS3.5 8.2.4 and 8.2.14
require to be declared YBR_ICT, while the controls-v4 files declare YBR_RCT, which the
`codestream` rule reports. `build_core_profile_controls.py --correct-lossy-photometric` derives
the controls-v6 files from controls-v4 with Photometric Interpretation YBR_ICT and a new SOP
Instance UID; their Frames, Study, Series, Frame of Reference, and specimen identities are
unchanged. The 17 core-profile and IOD structure cases built on these two controls were authored
on the controls-v4 files and are rebased onto the corrected files with their mutations and seeds
unchanged. The development entries name the candidate unit tests that exercise rules during
development; they are not evaluation cases.

Each evaluation case is a deterministic single-defect mutation of one control with its own seed,
and records the exact attributes or bytes changed, its DICOM 2026c citation, and its expected
rules. The cases form three cohorts. `core-profile-evaluation-v2` has 69 cases in five reporting
domains (19 conformance, 17 identity, 14 geometry, 12 color, 7 pixel) that exercise 18 selected
rule families. `iod-structure-evaluation-v1` has 80 cases. Each changes one Data Element (one
case changes a shared UID consistently at its three references), one Sequence Item, or one File
Meta element, at the top level, in nested Sequence Items, or in Shared and Per-Frame Functional
Group Items: 9 Module and Functional Group cases (an absent mandatory Module; unlisted, misplaced,
and missing mandatory Macros; Per-Frame Item count above and below Number of Frames), 17 presence
cases (Type 1 deleted and emptied, Type 2 deleted, required 1C deleted and emptied, forbidden 1C
present), 8 Enumerated Value, 12 VR and VM (explicit VR controls), 17 Value format (UID leading
zero, DA, TM, DT, lowercase CS, CR and LF in LO, DS over 16 bytes, IS over 12 bytes, PN
components), 8 Sequence Item count, and 9 File Meta cases. `requirement-statement-evaluation-v1`
has 203 cases: 40 attribute relation, 13 WSI image, 7 series set, 3 value set, 25 pixel
attribute, 38 codestream, and 77 encoding cases. Codestream cases edit the marker segments,
fragments, or donor Frames of one encapsulated Frame; encoding cases write into the encoded bytes
the defects that a DICOM writer would normalize away (`encoding_rewrite`), and use ordinary
Attribute edits for the rest. Every Attribute a case adds around its defect (a Sequence's required
members, the Common Instance Reference listing of a reference, the ICC Profile an Optical Path
palette requires) is otherwise conformant. Each case also records `requirement_ids`: the
identifiers, in the candidate's `wsi-dicom requirements --json` (pinned as
`rules/wsi-dicom-requirements-2026c-v1.json`), of the normative statements it breaks. The value
set cases name none, because Context Group and Template bindings are table rows rather than
statements. manifest-v6.json is the frozen record of the controls, the development entries, and
the core-profile cohort. `build_requirement_manifest.py` regenerates the IOD structure cohort from
`iod_amendment_cases.STRUCTURE_CASES` and the requirement-statement cohort from
`requirement_cases.REQUIREMENT_CASES`, and fails when the result differs from the committed
manifest, lock, or profile.

Generation has three further properties. A handler that derives two Instances from one control
gives the second the next Instance Number, because within a Series only the members of one
Concatenation may share an Instance Number (PS3.3 C.7.6.16.1); the eight instance-pair handlers
of the core-profile cohort were first authored with Instance Number 1 on both Instances, and no
expectation depends on the Instance Number. The derived instance of NB-ID-006 lists its source in
the Common Instance Reference Module (PS3.3 C.12.2), which the VL WSI IOD makes Mandatory, with
the source's true SOP Class, so the CT class in Source Image Sequence is the case's only defect.
Generation admits a control or generated object only when it is VL Whole Slide Microscopy and its
Patient ID and every component of its Patient's Name are empty or a placeholder word (RESEARCH,
PLACEHOLDER, ANONYMOUS, ANON).

Catalog v6 has 32 intrinsic, decoder, and set rules and four independent-validator observers.
The rules are the 18 core-profile rule families; seven VL WSI IOD requirement families generated
from the pinned DICOM 2026c DocBook tables (PS3.3 A.32.8 and the Module and Macro tables it
includes, PS3.6 Tables 6-1 and 7-1, PS3.10 Table 7.1-1): `iod-modules`, `iod-attribute-presence`,
`iod-enumerated-values`, `iod-vr-vm`, `iod-value-format`, `iod-sequence-items`, and `file-meta`;
and seven requirement-statement families: `iod-value-sets` (Defined Context Groups and Templates
of PS3.16, with Baseline and extensible departures reported as advisories), `wsi-image` (VL WSI
Image and Frame Type, Tiles Overlap, Imaged Volume Depth, Position Reference Indicator, optical
path resolution, derivation, pixel spacing, and the regular tiling), `attribute-relations`
(constraints between Attributes in the Data Set and every Item), `series-set` (Frames of
Reference, UID roles, Instance Numbers, Specimen Identifiers, Frame Extraction history, and
patient groups across the evaluated set), `pixel-attributes` (Pixel Padding, Pixel Aspect Ratio,
Icon Images, and palette tables), `codestream` (each encapsulated Frame is one complete codestream
of the coding process its Transfer Syntax identifies and agrees with the Image Pixel Attributes),
and `encoding` (the Data Set as encoded in the file's bytes: element order, VR and reserved bytes,
delimiters, Group Lengths, private blocks, and character sets). Each family is prefixed
`intrinsic-wsi-dicom-2026c-`. The requirement "the Per-Frame Functional Groups Sequence has one
Item per Frame" (PS3.3 Table C.7.6.16-1) belongs to `iod-sequence-items`, with the other Sequence
Item counts generated from the DocBook tables. Catalog v6 requires the binary to declare rule set
`wsi-dicom-general-v3` or `wsi-dicom-core-profile-2026c-v4`, and the workbench defaults to it.
Core profile v4 has 71 grouped rows, including one per requirement-statement family; its row
CP-IOD-FG-002, the Per-Frame Item count, is enforced by `iod-sequence-items`.

Expectations were set by running the frozen candidate recorded in the manifest's
`expectation_provenance` (`wsi-dicom 0.9.0`, SHA-256
e9efedc70aec4d4d15f91e799ea96c9b3fa3e76b21a929f2a3cee65ce4c9b774) and adjudicating each result
against the cited DICOM 2026c text. They are not blinded. The core-profile expectations list five
pixel-assembly cascades of the independent decoder rule (NB-PX-001 through NB-PX-005) by exact
rule ID. The IOD structure expectations, and the IOD-rule failures on core-profile cases recorded
in each case's `iod_rule_adjudications` (35 expected failing rules and 5 adjudicated cascades),
were first adjudicated on an earlier build of the same version (SHA-256
e4c5561ae73cf5a79c8186f8b78dd9ef1753b074495c8f7fec16bf50092e2b25). The cascades are on NB-CF-002
and NB-CF-005 (Type 1C Attributes left present after their condition stopped holding) and
CP-CF-002 (LABEL-conditional Module, Type 2, and Number of Frames requirements). An IOD structure
or requirement-statement case expects the targeted rule and, where another catalog rule
independently reports the same defect, that rule as well (25 requirement-statement cases); no
case of either cohort has an adjudicated cascade. Framing that only the encoded bytes show
(trailing bytes, the encapsulated Pixel Data VR, Fragment Item lengths, and delimiters) is
reported by `encoding` alone; `pixel-structure` checks the parsed Pixel Data.

On the 149 core-profile and IOD structure cases, a failure of a requirement-statement rule is an
expected failing rule when it reports the mutated Attribute or the inconsistency the case defines,
and an adjudicated cascade when it reports an unchanged Attribute whose requirement the mutation
changed; an authored expected rule whose requirement a requirement-statement rule now enforces is
recorded as superseded, with its replacement. Every decision, with the observed message,
citation, and rationale, is in the case's `requirement_rule_adjudications`; an IOD structure case
holds its decisions in its definition. There are 15 expected failing rules (`codestream` on
NB-PX-001 through NB-PX-006, whose offset tables, fragments, or codestream the case breaks;
`wsi-image` on CP-CF-004, CP-CL-006, and IOD-PRS-009; `series-set` on CP-ID-002 and CP-ID-003;
`dimension-order` on IOD-PRS-012; `iod-sequence-items` on NB-PX-001, IOD-MOD-006, and
IOD-MOD-007), 4 adjudicated cascades (`pixel-structure` on NB-CF-005, whose unchanged Pixel Data
no longer has the length one sample per pixel requires; `wsi-image` on CP-CF-002, CP-CL-002, and
CP-CL-003, where the unchanged Specimen Label in Image or Frame Optical Path Identifier no longer
meets the requirement the mutation changed), and 3 superseded `iod-modules` expectations
(NB-PX-001, IOD-MOD-006, IOD-MOD-007), each replaced by `iod-sequence-items`. Each case's
`expected_unaffected_rules` is every intrinsic rule that is neither expected nor an adjudicated
cascade.

expected-results-lock-v6.json binds the SHA-256 of this protocol, manifest v6, catalog v6, and
core profile v4, the profile identity and version, and the expected counts. Generation verifies
the lock before it writes a package, and runs the core-profile coverage gate: every one of the 71
profile rows is required, maps to catalog rules or required external validators, and has positive
controls and negative cases that exercise a mapped rule, and every one of the 32 intrinsic,
decoder, and set rules is expected by a case. Link completeness measures only the declared rows;
it does not establish exhaustive coverage of the DICOM standard, all attributes in a module, or
every conditional branch.

The requirement snapshot lists 919 statements, 553 of them checked by an intrinsic rule. The
requirement-statement cohort names 208 of those. The 31 checked statements of the
requirement-statement rules that no case names are listed with the reason in
`requirement_cases.UNCOVERED`. Thirty need a control the suite does not have (concatenations,
LABEL or OVERVIEW images, two optical paths, a LOCALIZER, JPEG-LS, RLE, JPEG XL, JPEG 2000 Part 2,
Encapsulated Uncompressed, large-frame HTJ2K RPCL, or JPIP Referenced Pixel Data). One, a Value
Length that overstates its Value, leaves the file unreadable to the parser, so the other rules
give no verdict and no single-defect case can hold it. The remaining unnamed statements belong to
the core-profile and IOD rules, whose cases exercise them without naming statements. The test
suite fails if a named statement is not checked by one of its case's expected rules, and holds
the count of unnamed checked statements, 345, to a limit that may only fall.

Scope is VOLUME, TILED_FULL, one optical path, one focal plane, no extended depth of field, and no
concatenations. LABEL, OVERVIEW, THUMBNAIL, sparse tiling, source fidelity, calibrated color,
DICOMweb behavior, digital signature verification, and compound defects are outside this
evaluation. Conditions that cannot be determined from the object are counted and never failed.
Files with an absent or unrecognized Transfer Syntax UID are excluded: the candidate cannot open
them, reports only a Pixel Data read failure, and emits no `file-meta` check, which the contract
treats as an incomplete check set.

Run the suite with `wsi-dicom-bench challenge run`, which selects `core-2026c` explicitly,
requires the external validators dciodvfy, dcentvfy, and validate_iods (edition 2026c), and runs
the bounded independent decoder checks in the bench. Preserve tool stdout and stderr, return
codes, elapsed time, executable digests, Python validator runtime provenance, IOD definition
hashes, and input digests. Controls must pass every required validator. Every negative case must
fail all expected rules and its declared domain. Any intrinsic failure that is neither expected
nor an adjudicated cascade blocks release until its cause is understood and an adjudication is
recorded in a new version of the suite; expected failures are not changed merely to obtain a
passing gate. A timeout, launch error, unavailable required tool, output truncation, unmapped
check, or incomplete check set is an execution error and cannot count as detection.
External-validator verdicts are observations, not expectations. Finalization runs the complete
evidence gate before it creates an exclusive checksum seal. Sealed packages are read-only:
reanalysis uses summarize_challenge, and a corrected execution requires a separate package.
Object and static-input bytes are deterministic; runtime measurements and environment evidence
are execution-specific and are sealed separately, not claimed byte-identical between runs.

Report observed counts and fractions on the authored challenge. They are not clinical
sensitivity, prevalence, certification, exhaustive normative coverage, or estimates of error
rates in deployed converters. Severity labels are expert assessments, not measured patient
outcomes.

Normative sources: DICOM PS3.3 2026c [VL WSI IOD](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part03/sect_A.32.8.html),
[WSI functional groups](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part03/sect_A.32.8.4.html),
[WSI Image Module](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part03/sect_C.8.12.4.html),
and [implicit frame order](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part03/sect_C.7.6.17.3.html);
PS3.5 2026c [Value Representations](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part05/sect_6.2.html),
[character sets](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part05/chapter_6.html),
[Data Set encoding](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part05/chapter_7.html),
[Data Element Types](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part05/sect_7.4.html),
and [Encapsulation](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part05/sect_A.4.html);
PS3.6 2026c [Registry of Data Elements](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part06/chapter_6.html);
PS3.10 2026c [File Format](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part10/chapter_7.html);
and PS3.16 2026c [Context Groups](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part16/chapter_B.html)
and [Templates](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part16/chapter_A.html).
