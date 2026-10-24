# WSI-DICOM Negative Bench v7 draft

This is an unfrozen Phase C work product for DICOM 2026d. It is not a runnable release suite and
has no expected-results lock or frozen candidate digest. The runnable bundled suite remains v6.
The development-only `negative_bench.draft_diagnostic` module can materialize the current general,
core-profile, advisory, File-set and DICOM JSON inputs and compare them with a candidate; its compact
summary is diagnostic output, not locked benchmark evidence.

The draft uses edition-neutral validation check, rule, catalog and candidate rule-set identifiers.
Its positive corpus covers every supported VL WSI configuration and transfer syntax represented by
`controls_v7_wsi`, the Segmentation, Parametric Map, Microscopy Bulk Simple Annotations, Key Object
Selection, Comprehensive SR and Comprehensive 3D SR objects represented by `controls_v7_iods`, and
one Basic Directory File-set. The former v6 controls remain mutation sources only. Cases must be
rebased before v7 is frozen; they are not v7 positive controls.

`statement-coverage-v7.json` is the coverage authority. A statement counts as directly named only
when a case names its stable requirement ID and expects the rule to which the candidate assigns the
statement. Exact duplicate standard text assigned to the same rule is listed separately. Missing
file-object statements and DICOMweb statements remain explicit work. DICOM JSON statements are
covered by the separate `json_evaluation_cases` corpus rather than file mutations. An
authored case blocked before its target rule runs is not credited as localized evidence.

Mappings onto carried cases are bound by `existing-statement-mapping-observations-v7.json`. The
builder generates the mapped case and its source control separately and credits the mapping only
when the assigned rule is a newly failing rule on the mutation. A rule already failing on a source
is not evidence for the mutation; affected legacy sources are rebased before observation.
Recommendations (`should`) need advisory evidence and are counted apart from mandatory failures.

The carry corpus is rebound by `carried-case-observations-v7.json`. CP01, CP11, CP12 and CP14 use
derived v7 mutation-source copies whose only Data Set changes are corrected per-Frame X offsets;
the v4 source files remain unchanged. Every rebased source passes the general profile. Carried
general cases record exactly the current observed target and adjudicated cascade rules. Former
profile-family expectations remain visible as profile-specific or superseded expectations. Cases
that still require the core profile are listed separately, and candidate detection gaps are not
counted as detected evaluation cases.

The DICOMweb statements need an HTTP-origin challenge corpus. The DICOM JSON statement cases use
JSON inputs derived from a valid WSI control and are kept separate from encoded-file mutations.

The current dciodvfy Concatenation observation is a tool limit: with `-new`, dicom3tools exits zero
on both members of `W7-CONCATENATION-2X4F` but warns that the legal Plane Position (Slide) Functional
Group Macro and its position attributes are absent from the IOD model. The same warnings occur on
other controls with explicit slide positions, so they are not a Concatenation defect.

Before freezing v7: finish every ledger item or retain an evidence-based blocker; rebase and run all
cases; adjudicate expected failures and cascades; record the exact candidate version and digest;
create the v7 profile and expected-results lock; run the complete challenge in a new evidence
directory; and only then update the bundled-suite default, README command and downstream CI pin.
