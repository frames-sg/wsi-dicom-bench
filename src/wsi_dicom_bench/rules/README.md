# WSI-DICOM rule catalogs

The package includes the v6 core challenge catalog and v4 core profile of the negative
bench, and the v2 general catalog used by converter format-coverage runs. Catalog v6 holds
the selected WSI rule families, the VL WSI IOD requirement families, and the value set, WSI
image, attribute relation, series set, pixel attribute, codestream, and encoding families of
`wsi-dicom` rule sets `wsi-dicom-general-v3` and `wsi-dicom-core-profile-2026c-v4`. Their
identifiers are stable provenance fields. The grouped profile rows do not claim exhaustive
DICOM coverage.

`wsi-dicom-requirements-2026c-v1.json` is `wsi-dicom requirements --json` of the candidate
that the v6 expectations were adjudicated against: every normative statement in the VL WSI
scope of DICOM 2026c with how that build holds an object to it. Evaluation cases name the
statements they break by its identifiers.
