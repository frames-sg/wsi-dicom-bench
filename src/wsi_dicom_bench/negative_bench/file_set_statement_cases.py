"""Directory graph, File ID, and Icon Image defects of a copied File-set."""

from .iod_amendment_cases import _case as _spec, _op

DOCUMENT_CONTROL_ID = "V7-DOCUMENT-FILESET"
DOCUMENT_CONTROL_PATHS = tuple(f"controls-v7/iods/document-fileset/{name}"
                              for name in ("DICOMDIR", "DATA/WSI0", "DATA/WSI1", "DATA/SR", "DATA/KOS"))


def write_document_control(output):
    """Build one independent directory index of valid WSI, SR and KOS files."""
    import shutil
    import subprocess
    from pathlib import Path
    import pydicom
    from .mutations.dicom import deterministic_uid
    from .mutations.file_set import _write_directory

    source = Path(__file__).parent / "controls-v7" / "iods"
    output.mkdir(parents=True, exist_ok=False)
    (output / "DATA").mkdir()
    members = {
        "WSI0": source / "fileset/SLIDE/WSI0",
        "WSI1": source / "fileset/SLIDE/WSI1",
        "SR": source / "sr-tid1500.dcm",
        "KOS": source / "kos-rejected-quality.dcm",
    }
    for name, path in members.items():
        shutil.copyfile(path, output / "DATA" / name)
    result = subprocess.run(["dcmmkdir", "-Pgp", "+F", "DOCSET", "-I",
                             *(f"DATA/{name}" for name in members)],
                            cwd=output, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"document File-set authoring failed: {result.stderr[:1200]}")
    directory = pydicom.dcmread(output / "DICOMDIR")
    directory.file_meta.MediaStorageSOPInstanceUID = deterministic_uid(DOCUMENT_CONTROL_ID, "directory")
    _write_directory(directory, output / "DICOMDIR")


def _case(number, parameters, requirements, section, changed):
    return {
        **_spec(f"REQ-FILESET-{number:03d}", "V7-FILESET", "file_set_edits", parameters,
                ("file-set",), changed,
                {"edition": "2026d", "part": "PS3.3" if section.startswith("F") else "PS3.10",
                 "section": section,
                 "url": "https://dicom.nema.org/medical/dicom/2026d/output/chtml/part03/chapter_F.html"
                        if section.startswith("F") else
                        "https://dicom.nema.org/medical/dicom/2026d/output/chtml/part10/chapter_8.html"},
                "The source File-set is copied. Valid graph links are relocated after serialization; "
                "the named defect is retained and must fail the File-set check."),
        "requirement_ids": list(requirements),
    }


def _record(index, keyword, value):
    return _op("set", ["DirectoryRecordSequence", index, keyword], value)


CASES = [
    _case(1, {"operations": [_op("set", ["FileSetID"], "BAD-SET")]},
          ("Ps10_8_5_e938f0",), "8.5", "File-set ID contains a hyphen outside its repertoire."),
    _case(2, {"file_meta": {"TransferSyntaxUID": "1.2.840.10008.1.2"}},
          ("Ps10_8_6_0ebc18",), "8.6", "Encode the DICOMDIR using Implicit VR Little Endian."),
    _case(3, {"file_meta": {"MediaStorageSOPClassUID": "1.2.840.10008.5.1.4.1.1.77.1.6"}},
          ("Ps10_8_6_572268",), "8.6", "The DICOMDIR File Meta names the WSI class instead of Basic Directory."),
    _case(4, {"operations": [_record(3, "ReferencedFileID", ["..", "OUTSIDE"])]},
          ("Ps10_8_6_cab9e6", "Ps3_F_3_3_ReferencedFileID_a6aede"), "F.3.3 and PS3.10 8.6",
          "An IMAGE record references a path outside its File-set root."),
    _case(5, {"omit_file": "SLIDE/WSI0"},
          ("Ps3_F_2_1_9936a3",), "F.2.1", "Do not copy one referenced file into the generated File-set."),
    _case(6, {"duplicate_file": True},
          ("Ps3_F_2_1_ac61bd", "Ps3_F_3_3_ReferencedFileID_0dc388"), "F.2.1 and F.3.3",
          "Two IMAGE records consistently reference the same file and SOP Instance."),
    _case(7, {"shared_child": True},
          ("Ps3_F_2_1_7d9cf7", "Ps3_F_2_1_ea4925"), "F.2.1",
          "Two distinct SERIES records reference the same lower-level IMAGE entity."),
    _case(8, {"operations": [_record(3, "OffsetOfReferencedLowerLevelDirectoryEntity", 1)]},
          ("Ps3_F_3_3_OffsetOfReferencedLowerLevelDirectoryEntity_82f314",), "F.3.3",
          "An IMAGE record without children has a nonzero lower-level offset."),
    _case(9, {"empty_directory": True, "operations": [_op("set", ["OffsetOfTheFirstDirectoryRecordOfTheRootDirectoryEntity"], 1)]},
          ("Ps3_F_3_3_OffsetOfTheFirstDirectoryRecordOfTheRootDirectoryEntity_800e32",), "F.3.3",
          "An empty Directory has a nonzero first root-record offset."),
    _case(10, {"empty_directory": True, "operations": [_op("set", ["OffsetOfTheLastDirectoryRecordOfTheRootDirectoryEntity"], 1)]},
          ("Ps3_F_3_3_OffsetOfTheLastDirectoryRecordOfTheRootDirectoryEntity_894d9e",), "F.3.3",
          "An empty Directory has a nonzero last root-record offset."),
    _case(11, {"operations": [_record(4, "OffsetOfTheNextDirectoryRecord", 1)]},
          ("Ps3_F_3_3_OffsetOfTheNextDirectoryRecord_deaeb7",), "F.3.3",
          "The final IMAGE sibling names a nonzero, nonexistent next record."),
    _case(12, {"operations": [_record(3, "ReferencedFileID", ["SLIDE", "NINECHARS"])]},
          ("Ps3_F_3_3_ReferencedFileID_325467",), "F.3.3",
          "One File ID component has nine characters."),
    _case(13, {"duplicate_entity": "PATIENT"},
          ("Ps3_F_5_1_b0329b", "Ps3_F_5_1_e7d1bd"), "F.5.1",
          "Two distinct PATIENT records use the same Patient ID."),
    _case(14, {"duplicate_entity": "STUDY"},
          ("Ps3_F_5_2_22d39d", "Ps3_F_5_2_e0336d"), "F.5.2",
          "Two distinct STUDY records use the same Study Instance UID."),
    _case(15, {"duplicate_entity": "SERIES"},
          ("Ps3_F_5_3_2b5a27", "Ps3_F_5_3_b5858e"), "F.5.3",
          "Two distinct SERIES records use the same Series Instance UID."),
    _case(16, {"operations": [_record(8, "DirectoryRecordType", "IMAGE")]},
          ("Ps3_F_5_4_5c9817",), "F.5.4",
          "An IMAGE record references an annotation SOP Instance."),
    _case(17, {"operations": [_record(3, "DirectoryRecordType", "ANNOTATION")]},
          ("Ps3_F_5_47_1711ae",), "F.5.47",
          "An ANNOTATION record references a WSI Image SOP Instance."),
    _case(18, {"icon": {"PixelAspectRatio": [2, 1]}},
          ("Ps3_F_7_486583",), "F.7", "A correctly sized monochrome Icon has non-square pixels."),
    _case(19, {"icon": {"HighBit": 6}},
          ("Ps3_F_7_5a988c",), "F.7", "An 8-bit Icon declares High Bit 6."),
    _case(20, {"icon": {"BitsAllocated": 16, "BitsStored": 16, "HighBit": 15}},
          ("Ps3_F_7_8da9c5",), "F.7", "An otherwise consistent monochrome Icon uses 16-bit samples."),
    _case(21, {"icon": {"SamplesPerPixel": 3, "PhotometricInterpretation": "RGB", "PlanarConfiguration": 0}},
          ("Ps3_F_7_9af80c", "Ps3_F_7_f0f851"), "F.7",
          "An Icon uses native RGB with matching three-sample Pixel Data instead of monochrome or palette color."),
    _case(22, {"icon": {"PixelRepresentation": 1}},
          ("Ps3_F_7_c7d6e0",), "F.7", "An Icon declares signed samples."),
    _case(23, {"icon": {"PhotometricInterpretation": "PALETTE COLOR", "BitsAllocated": 16, "BitsStored": 16, "HighBit": 15}},
          ("Ps3_F_7_277053",), "F.7", "A palette Icon with complete LUTs uses 16-bit allocation instead of 8."),
    _case(24, {"file_meta": {"MediaStorageSOPInstanceUID": ""}},
          ("Ps10_8_6_f6c0f3", "Ps10_8_6_6f3918"), "8.6",
          "The DICOMDIR has no File-set UID Value in its File Meta Information."),
    _case(25, {"private_record": True, "unreferenced_file": True},
          ("Ps3_F_2_1_7f516a",), "F.2.1", "A File-set with a valid PRIVATE record has an unreferenced valid DICOM file."),
    _case(26, {"private_record": True, "private_bad_next": True},
          ("Ps3_F_6_1_01b3be", "Ps3_F_6_1_427b33"), "F.6.1",
          "A PRIVATE record violates the common Directory graph specification with a nonexistent next-record offset."),
]

# Consequences of the same authored defect in checks outside File-set.
# In particular a wrongly declared WSI SOP Class makes the generic validator
# attempt WSI checks on the Directory Data Set; no WSI Attributes were removed.
_CASCADES = {
    1: ("iod-value-format",),
    3: ("file-meta", "icc-profile", "identity-set", "image-metadata",
        "iod-attribute-presence", "iod-modules", "lossy-history",
        "monochrome-presentation", "source-relationship", "specimen-identity",
        "specimen-uid-set", "tile-geometry"),
    4: ("iod-value-format",),
    17: ("iod-attribute-presence",),
    19: ("pixel-attributes",),
    24: ("file-meta",),
}
for _entry in CASES:
    _number = int(_entry["case_id"].rsplit("-", 1)[1])
    _entry["expected"] = [*_entry["expected"], *_CASCADES.get(_number, ())]

CASES.extend([
    {**_case(27, {"operations": [_op("set", ["DirectoryRecordSequence", 8, "ContentSequence", 0, "RelationshipType"], "CONTAINS")]},
             ("Ps3_F_5_25_ContentSequence_65305f",), "F.5.25",
             "The SR Directory record changes a source HAS CONCEPT MOD Item to CONTAINS."),
     "control": DOCUMENT_CONTROL_ID, "expected": ("file-set", "iod-enumerated-values")},
    {**_case(28, {"operations": [_op("set", ["DirectoryRecordSequence", 6, "ContentSequence", 0, "RelationshipType"], "CONTAINS")]},
             ("Ps3_F_5_26_ContentSequence_3fb953",), "F.5.26",
             "The KOS Directory record changes a source HAS CONCEPT MOD Item to CONTAINS."),
     "control": DOCUMENT_CONTROL_ID, "expected": ("file-set", "iod-enumerated-values")},
    {**_case(29, {"operations": [_record(6, "DirectoryRecordType", "SR DOCUMENT")]},
             ("Ps3_F_5_25_c37466",), "F.5.25",
             "An SR DOCUMENT Directory record references a Key Object Selection Document."),
     "control": DOCUMENT_CONTROL_ID, "expected": ("file-set", "iod-attribute-presence")},
    {**_case(30, {"operations": [_record(8, "DirectoryRecordType", "KEY OBJECT DOC")]},
             ("Ps3_F_5_26_e9e261",), "F.5.26",
             "A KEY OBJECT DOC Directory record references a Comprehensive 3D SR Document."),
     "control": DOCUMENT_CONTROL_ID},
])
