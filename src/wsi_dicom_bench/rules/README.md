# WSI-DICOM rule catalogs

The package includes the current v6 core challenge catalog and v4 core profile, the
frozen v5 and v4 catalogs and v3 and v2 profiles that earlier evidence pins, and the v2
general catalog used by converter format-coverage runs. Catalog v5 adds the VL WSI IOD
requirement families of `wsi-dicom` rule sets `wsi-dicom-general-v2` and
`wsi-dicom-core-profile-2026c-v3`; catalog v6 adds the value set, WSI image, attribute
relation, series set, pixel attribute, codestream, and encoding families of rule sets
`wsi-dicom-general-v3` and `wsi-dicom-core-profile-2026c-v4`. Their identifiers are stable
provenance fields. The grouped profile rows do not claim exhaustive DICOM coverage.

`wsi-dicom-requirements-2026c-v1.json` is `wsi-dicom requirements --json` of the candidate
that the v6 expectations were adjudicated against: every normative statement in the VL WSI
scope of DICOM 2026c with how that build holds an object to it. Evaluation cases name the
statements they break by its identifiers.
