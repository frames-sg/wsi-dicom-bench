"""PS3.15 declaration and confidentiality defects of a synthetic WSI control.

The control authoring function applies the Basic Profile actions to the known
CP10 fixture only; it is not a de-identifier for arbitrary clinical inputs.
UIDs are retained by the explicit Retain UIDs Option. All names and dates in
this corpus are synthetic. The original control is never overwritten.
"""

from pathlib import Path
import subprocess
import tempfile

import pydicom
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from .iod_amendment_cases import _case as _spec, _code, _op

CONTROL_ID = "V7-DEID-BASIC"
CONTROL_PATH = "controls-v7/iods/deid-basic.dcm"
ENCRYPTED_CONTROL_ID = "V7-DEID-ENCRYPTED"
ENCRYPTED_CONTROL_PATH = "controls-v7/iods/deid-encrypted.dcm"
FILESET_CONTROL_ID = "V7-DEID-FILESET"
FILESET_CONTROL_PATHS = ("controls-v7/iods/deid-fileset/DICOMDIR", "controls-v7/iods/deid-fileset/DATA/WSI")


def write_control(source: Path, output: Path) -> None:
    if output.exists():
        raise ValueError(f"control output already exists: {output}")
    dataset = pydicom.dcmread(source)
    # PS3.15 2026d Table E.1-1: every listed Attribute occurring in CP10.
    remove = {"StudyDescription", "PyramidLabel", "SpecimenShortDescription",
              "SpecimenDetailedDescription", "AcquisitionDate", "AcquisitionTime"}
    empty = {"StudyDate", "StudyTime", "AccessionNumber", "ReferringPhysicianName",
             "PatientName", "PatientBirthDate", "PatientSex", "StudyID"}
    empty_sequences = {"IssuerOfTheContainerIdentifierSequence",
                       "IssuerOfTheSpecimenIdentifierSequence", "SpecimenPreparationSequence",
                       "AcquisitionContextSequence"}
    dummy = {"PatientID": "DUMMY-PATIENT", "ContainerIdentifier": "DUMMY-SLIDE",
             "SpecimenIdentifier": "DUMMY-SPECIMEN", "DeviceSerialNumber": "DUMMY-DEVICE",
             "AcquisitionDateTime": "19000101000000", "ContentDate": "19000101",
             "ContentTime": "000000"}

    def protect(item):
        for element in list(item):
            if element.keyword in remove:
                del item[element.tag]
            elif element.keyword in empty:
                element.value = None
            elif element.keyword in empty_sequences:
                element.value = Sequence([])
            elif element.keyword in dummy:
                element.value = dummy[element.keyword]
            elif element.VR == "SQ":
                for child in element.value:
                    protect(child)

    protect(dataset)
    dataset.PatientIdentityRemoved = "YES"
    dataset.LongitudinalTemporalInformationModified = "REMOVED"
    methods = []
    for value, meaning in [("113100", "Basic Application Confidentiality Profile"),
                           ("113110", "Retain UIDs Option")]:
        code = Dataset()
        code.CodeValue, code.CodingSchemeDesignator, code.CodeMeaning = value, "DCM", meaning
        methods.append(code)
    dataset.DeidentificationMethodCodeSequence = Sequence(methods)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset.save_as(output, enforce_file_format=True)


def write_encrypted_control(source: Path, output: Path) -> None:
    """Author real RSA/AES-CBC encrypted original Attributes; discard the test key."""
    if output.exists():
        raise ValueError(f"control output already exists: {output}")
    from pydicom.filebase import DicomBytesIO
    from pydicom.filewriter import write_dataset

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        key, certificate = root / "key.pem", root / "certificate.pem"
        original = Dataset()
        original.PatientName = "RESEARCH^ORIGINAL"
        stream = DicomBytesIO()
        stream.is_little_endian, stream.is_implicit_VR = True, False
        write_dataset(stream, original)
        (root / "attributes.bin").write_bytes(stream.getvalue())
        commands = [
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
             "-subj", "/CN=WSI benchmark synthetic encryption", "-keyout", str(key), "-out", str(certificate)],
            ["openssl", "cms", "-encrypt", "-binary", "-aes-256-cbc", "-in", str(root / "attributes.bin"),
             "-outform", "DER", "-out", str(root / "enveloped.der"), str(certificate)],
        ]
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError(f"synthetic encryption authoring failed: {result.stderr[:1200]}")
        dataset = pydicom.dcmread(source)
        encrypted = Dataset()
        encrypted.EncryptedContentTransferSyntaxUID = "1.2.840.10008.1.2.1"
        encrypted.EncryptedContent = (root / "enveloped.der").read_bytes()
        dataset.EncryptedAttributesSequence = Sequence([encrypted])
        dataset.save_as(output, enforce_file_format=True)


def write_fileset_control(source: Path, output: Path) -> None:
    """Build a Directory from the protected synthetic file, with matching keys."""
    from .mutations.dicom import deterministic_uid
    from .mutations.file_set import _write_directory

    output.mkdir(parents=True, exist_ok=False)
    (output / "DATA").mkdir()
    dataset = pydicom.dcmread(source)
    # Directory Type 1 keys may be nonempty dummy Values under action Z.
    dataset.StudyDate, dataset.StudyTime, dataset.StudyID = "19000101", "000000", "DEIDSTUDY"
    dataset.save_as(output / "DATA" / "WSI", enforce_file_format=True)
    result = subprocess.run(["dcmmkdir", "-Pgp", "+F", "DEIDBASIC", "-I", "DATA/WSI"],
                            cwd=output, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"synthetic File-set authoring failed: {result.stderr[:1200]}")
    directory = pydicom.dcmread(output / "DICOMDIR")
    directory.file_meta.MediaStorageSOPInstanceUID = deterministic_uid(FILESET_CONTROL_ID, "directory")
    _write_directory(directory, output / "DICOMDIR")


def _methods(*options):
    return [_code("DCM", value, meaning) for value, meaning in [
        ("113100", "Basic Application Confidentiality Profile"),
        ("113110", "Retain UIDs Option"), *options,
    ]]


def _case(number, operations, identifiers, section, changed):
    return {
        **_spec(f"REQ-DEID-{number:03d}", CONTROL_ID, "iod_edits", {"operations": operations},
                ("deidentification",), changed,
                {"edition": "2026d", "part": "PS3.15", "section": section,
                 "url": "https://dicom.nema.org/medical/dicom/2026d/output/chtml/part15/chapter_E.html"},
                "The control declares and satisfies the Basic Profile with Retain UIDs; "
                "the case violates the named declaration or Attribute action."),
        "requirement_ids": list(identifiers),
    }


CASES = [
    _case(1, [_op("delete", ["PatientIdentityRemoved"])],
          ("Ps15_E_1_1_a9ad8b",), "E.1.1", "A named de-identification method has no Patient Identity Removed flag."),
    _case(2, [_op("delete", ["DeidentificationMethodCodeSequence"])],
          ("Ps15_E_1_1_9278e7",), "E.1.1", "Patient Identity Removed is YES but neither a coded nor textual method is given."),
    _case(3, [_op("set", ["PatientIdentityRemoved"], "NO")],
          ("Ps15_E_1_2_3efb4e",), "E.1.2", "The re-identified declaration NO retains the de-identification method."),
    _case(4, [_op("delete", ["LongitudinalTemporalInformationModified"])],
          ("Ps15_E_2_8ecf99",), "E.2", "No longitudinal-retention option is selected but the required REMOVED indicator is absent."),
    _case(5, [_op("insert", ["(0004,1130)"], "FILESET", vr="CS")],
          ("Ps15_E_1_1_3a437a",), "E.1.1", "The protected image retains a group 0004 Attribute although it is not a DICOMDIR."),
    _case(6, [_op("insert", ["StudyDescription"], "Research placeholder WSI export")],
          ("Ps15_E_1_1_130cad", "Ps15_E_1_1_3479d4"), "E.1.1",
          "The original Study Description is retained unchanged despite its Basic Profile X action."),
    _case(7, [_op("insert", ["(0029,0010)"], "BENCH", vr="LO"),
              _op("insert", ["(0029,1001)"], "RESEARCH", vr="LO")],
          ("Ps15_E_3_10_c41c02",), "E.3.10", "A private block is retained without the Retain Safe Private Option."),
    _case(8, [_op("set", ["DeidentificationMethodCodeSequence"],
                  _methods(("113111", "Retain Safe Private Option"))),
              _op("insert", ["(0029,0010)"], "BENCH", vr="LO"),
              _op("insert", ["(0029,1001)"], [{"PatientComments": "RESEARCH"}], vr="SQ")],
          ("Ps15_E_3_10_813a17",), "E.3.10",
          "A retained private Sequence holds standard Patient Comments that still require the Basic Profile X action."),
    _case(9, [_op("set", ["DeidentificationMethodCodeSequence"],
                  _methods(("113101", "Clean Pixel Data Option"))),
              _op("set", ["BurnedInAnnotation"], "YES")],
          ("Ps15_E_3_1_3a4bfe",), "E.3.1", "Clean Pixel Data is claimed but Burned In Annotation is YES."),
    _case(10, [_op("set", ["DeidentificationMethodCodeSequence"],
                   _methods(("113102", "Clean Recognizable Visual Features Option"))),
               _op("insert", ["RecognizableVisualFeatures"], "YES")],
          ("Ps15_E_3_2_4931da",), "E.3.2", "Clean Recognizable Visual Features is claimed but its indicator is YES."),
    _case(11, [_op("set", ["DeidentificationMethodCodeSequence"],
                   _methods(("113106", "Retain Longitudinal Temporal Information Full Dates Option")))],
          ("Ps15_E_3_6_cce630",), "E.3.6", "Full Dates retention is selected but the temporal indicator remains REMOVED."),
    _case(12, [_op("set", ["DeidentificationMethodCodeSequence"],
                   _methods(("113107", "Retain Longitudinal Temporal Information Modified Dates Option"))),
               _op("set", ["ContentDate"], "19000102"),
               _op("set", ["AcquisitionDateTime"], "19000102000000")],
          ("Ps15_E_3_6_6c1923",), "E.3.6", "Dates are shifted by a day under Modified Dates retention but the temporal indicator remains REMOVED."),
    _case(13, [_op("set", ["DeidentificationMethodCodeSequence"],
                   _methods(("113111", "Retain Safe Private Option"))),
               _op("insert", ["(0029,1001)"], "SAFE-SYNTHETIC", vr="LO")],
          ("Ps15_E_3_10_d4f53a",), "E.3.10", "A retained safe private Attribute has no defining Private Creator."),
    _case(14, [_op("set", ["DeidentificationMethodCodeSequence"],
                   _methods(("113104", "Clean Structured Content Option"))),
               _op("set", ["AcquisitionContextSequence"], [{
                   "ValueType": "CODE",
                   "ConceptNameCodeSequence": [_code("DCM", "121032", "Subject Sex")],
                   "ConceptCodeSequence": [_code("SCT", "248153007", "Male")],
               }])],
          ("Ps15_E_3_4_4c3e71",), "E.3.4", "Clean Structured Content retains a Subject Sex Content Item that Table E.3.4-1 removes."),
]

CASES.extend([
    {**_case(15, [], ("Ps15_E_1_1_d220db", "Ps15_E_1_1_097048"), "E.1.1",
             "Encrypted Attributes declare RSAES-OAEP key transport instead of the required RFC 2313 RSA transport."),
     "control": ENCRYPTED_CONTROL_ID, "mutation_name": "encrypted_attribute_edit",
     "mutation_parameters": {"wrong_key_transport": True}},
    {**_case(16, [], ("Ps15_E_1_1_9e2599",), "E.1.1",
             "The encrypted Data Set's Transfer Syntax is declared with an allocated SOP Class UID instead of a Transfer Syntax UID."),
     "control": ENCRYPTED_CONTROL_ID, "mutation_name": "encrypted_attribute_edit",
     "mutation_parameters": {"transfer_syntax": "1.2.840.10008.5.1.4.1.1.7"}},
    {**_case(17, [], ("Ps15_E_1_1_0dc920", "Ps15_E_1_1_610bd1"), "E.1.1",
             "A protected File-set retains a Study Description in the Directory although the Basic Profile removes it from the referenced file."),
     "control": FILESET_CONTROL_ID, "mutation_name": "file_set_edits",
     "mutation_parameters": {"operations": [_op("set", ["DirectoryRecordSequence", 1, "StudyDescription"], "RESEARCH")]}} ,
])

for _case_spec in CASES:
    _cascade = {
        "REQ-DEID-002": "iod-attribute-presence",
        "REQ-DEID-013": "encoding",
    }.get(_case_spec["case_id"])
    if _cascade:
        _case_spec["expected"] = [*_case_spec["expected"], _cascade]
