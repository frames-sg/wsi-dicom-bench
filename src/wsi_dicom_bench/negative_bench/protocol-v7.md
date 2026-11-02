# WSI-DICOM Negative Bench v7

This locked DICOM 2026d challenge evaluates every normative statement that the candidate catalog
classifies as checked. It deliberately does not claim complete standards coverage: seven
requirements remain `Unchecked` in 16 IOD scope-pairs and are frozen as known acceptance-policy
failures, not reclassified or hidden.

`statement-coverage-v7.json` is the coverage authority. A checked statement counts only when a
case names its stable requirement ID and expects the assigned rule, or when the ledger records an
exact duplicate statement assigned to that rule. The locked corpus contains separate file/object,
DICOM JSON, DICOMweb, core-profile and advisory cohorts. Recommendations are witnessed by advisory
evidence and never converted into mandatory failures.

Carried v6 cases use corrected, derived mutation sources; the original controls remain unchanged.
New controls cover supported pathology IODs, File-sets, motion transfer syntaxes, codec boundary
conditions, digital signatures and lossy Segmentation/Parametric Map objects. Each positive control
passes before its mutation is credited. Observed cascades are locked explicitly.

The DICOMweb cohort runs against bounded local origin scenarios. JSON cases carry an explicit
Transfer Syntax hint. File/object cases are materialized deterministically and stored in the
generated package. The retained benchmark wheel and pinned pydicom dependency are part of the
reproduction payload.

The dciodvfy warnings about legal Plane Position (Slide) Functional Groups in Concatenation members
are recorded as a dicom3tools model limitation. OpenJPEG and Grok rejecting the standards-authored
JPEG 2000 Part 2 multiple-component-transform control is likewise recorded as an independent-tool
limitation, not used to adjudicate the candidate.

Acceptance requires a complete, internally consistent execution of every locked cohort. Candidate
execution or integrity failures exit as infrastructure errors. A complete run exits as a policy
failure while any frozen `Unchecked` scope-pair remains; v7 therefore produces concrete failed
evidence for the current seven requirements rather than presenting an incomplete candidate as
standards-complete.
