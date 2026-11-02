"""Digital Signature witnesses authored independently with DCMTK and OpenSSL.

The negative signatures are genuine RSA signatures over deliberately incorrect
MAC byte streams. Their authoring code identifies exactly which required field
was omitted or misencoded. Test private keys are temporary and are not shipped.
The frozen public fixture and its precomputed mutations are consumed together.
"""

from __future__ import annotations

import json
import struct
import subprocess
import tempfile
from pathlib import Path

import pydicom

from .iod_amendment_cases import _case as _spec

CONTROL_ID = "V7-SIGNED-WSI"
CONTROL_PATH = "controls-v7/signatures/signed.dcm"
TIMESTAMP_CONTROL_ID = "V7-TIMESTAMPED-WSI"
TIMESTAMP_CONTROL_PATH = "controls-v7/signatures/timestamped.dcm"
MUTATIONS_PATH = "controls-v7/signatures/mac-signatures.json"
ITEM = bytes.fromhex("feff00e0")
DELIMITER = bytes.fromhex("feffdde0")


def _run(command):
    result = subprocess.run([str(value) for value in command], capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"{command[0]} fixture authoring failed: {result.stderr.decode(errors='replace')[:1400]}")


def _key(root, name, timestamp=False):
    key, certificate = root / f"{name}.key", root / f"{name}.pem"
    command = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
               "-subj", f"/CN=WSI benchmark {name} synthetic only", "-keyout", key, "-out", certificate]
    if timestamp:
        command += ["-addext", "extendedKeyUsage=critical,timeStamping"]
    _run(command)
    return key, certificate


def _one(haystack: bytes, needle: bytes) -> int:
    if haystack.count(needle) != 1:
        raise ValueError(f"MAC authoring marker must be unique: {needle.hex()}")
    return haystack.index(needle)


def _primitive_span(stream, group, element, vr):
    start = _one(stream, struct.pack("<HH", group, element) + vr)
    # The chosen UI, LO and DT elements use the short explicit-VR header.
    length = int.from_bytes(stream[start + 6:start + 8], "little")
    return start, start + 8 + length


def malformed_streams(stream: bytes, dataset, file_bytes: bytes) -> dict[str, bytes]:
    sequence = struct.pack("<HH", 0x0040, 0x0560) + b"SQ\0\0"
    sequence_at = _one(stream, sequence)
    first_item = sequence_at + len(sequence)
    if stream[first_item:first_item + 4] != ITEM:
        raise ValueError("Specimen Description MAC must start with an Item Tag")
    pixel = struct.pack("<HH", 0x7FE0, 0x0010) + b"OB\0\0"
    pixel_at = _one(stream, pixel)
    bot_length = int.from_bytes(dataset.PixelData[4:8], "little")
    fragment = pixel_at + len(pixel) + len(ITEM) + bot_length
    if stream[fragment:fragment + 4] != ITEM:
        raise ValueError("encapsulated MAC must include a Fragment Item Tag")
    specimen_start, specimen_end = _primitive_span(stream, 0x0040, 0x0551, b"LO")
    uid_start, _ = _primitive_span(stream, 0x0008, 0x0018, b"UI")
    datetime_start, datetime_end = _primitive_span(stream, 0x0400, 0x0105, b"DT")
    delimiter = stream.index(DELIMITER, first_item, pixel_at)
    raw_sequence = _one(file_bytes, sequence)
    value_length = file_bytes[raw_sequence + 8:raw_sequence + 12]
    wrong_endian = bytearray(stream)
    wrong_endian[uid_start:uid_start + 4] = struct.pack(">HH", 0x0008, 0x0018)
    return {
        "omit-sequence-item-tag": stream[:first_item] + stream[first_item + 4:],
        "omit-fragment-item-tag": stream[:fragment] + stream[fragment + 4:],
        "omit-nested-attribute": stream[:specimen_start] + stream[specimen_end:],
        "omit-sequence-delimiter": stream[:delimiter] + stream[delimiter + 4:],
        "wrong-tag-byte-order": bytes(wrong_endian),
        "include-sequence-value-length": stream[:first_item] + value_length + stream[first_item:],
        "omit-signature-datetime": stream[:datetime_start] + stream[datetime_end:],
        "omit-primitive-vr": stream[:uid_start + 4] + stream[uid_start + 6:],
    }


def write_controls(source: Path, output: Path) -> None:
    """Author controls and their mutation signatures into a new directory."""
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        key, certificate = _key(root, "signer")
        signed, dump = root / "signed.dcm", root / "stream.bin"
        _run(["dcmsign", "--sign", key, certificate, "--null-passwd", "--profile-none",
              "--mac-sha256", "--tag", "0008,0018", "--tag", "0040,0560",
              "--tag", "7fe0,0010", "--dump", dump, source, signed])
        dataset = pydicom.dcmread(signed)
        # Rewriting preserves the canonical MAC despite physical Sequence lengths.
        dataset.save_as(output / "signed.dcm", enforce_file_format=True)
        stream = dump.read_bytes()
        signatures = {}
        streams = malformed_streams(stream, dataset, signed.read_bytes())
        streams["wrong-mac-algorithm"] = stream
        for name, data in streams.items():
            (root / "wrong-stream.bin").write_bytes(data)
            algorithm = "-sha512" if name == "wrong-mac-algorithm" else "-sha256"
            _run(["openssl", "dgst", algorithm, "-sign", key, "-out", root / "wrong-signature.bin",
                  root / "wrong-stream.bin"])
            signatures[name] = (root / "wrong-signature.bin").read_bytes().hex()
        signature = bytes(dataset.DigitalSignaturesSequence[0].Signature)
        (output / "mac-signatures.json").write_text(json.dumps({
            "schema_version": "wsi-dicom-signature-mutations-v1",
            "original_signature": signature.hex(), "signatures": signatures,
        }, indent=2, sort_keys=True) + "\n")

        tsa_key, tsa_certificate = _key(root, "timestamp-authority", timestamp=True)
        (root / "signature.bin").write_bytes(signature)
        (root / "serial").write_text("01\n")
        configuration = root / "tsa.cnf"
        configuration.write_text(
            "[ tsa ]\ndefault_tsa = fixture\n[ fixture ]\n"
            f"serial = {root / 'serial'}\nsigner_cert = {tsa_certificate}\nsigner_key = {tsa_key}\n"
            "signer_digest = sha256\ndefault_policy = 1.2.826.0.1.3680043.10.999.2\n"
            "digests = sha256, sha384, sha512\naccuracy = secs:1\ness_cert_id_alg = sha256\n"
        )
        _run(["openssl", "ts", "-query", "-data", root / "signature.bin", "-sha256", "-cert",
              "-out", root / "query.tsq"])
        _run(["openssl", "ts", "-reply", "-config", configuration, "-queryfile", root / "query.tsq",
              "-out", root / "reply.tsr"])
        _run(["openssl", "ts", "-reply", "-in", root / "reply.tsr", "-token_out", "-out", root / "token.der"])
        item = dataset.DigitalSignaturesSequence[0]
        item.CertifiedTimestampType = "CMS_TSP"
        item.CertifiedTimestamp = (root / "token.der").read_bytes()
        dataset.save_as(output / "timestamped.dcm", enforce_file_format=True)


def _case(number, variant, requirement, changed, timestamp=False):
    return {
        **_spec(f"REQ-SIGNATURE-{number:03d}", TIMESTAMP_CONTROL_ID if timestamp else CONTROL_ID,
                "signature_mac_defect", {"variant": variant}, ("digital-signatures",), changed,
                {"edition": "2026d", "part": "PS3.3", "section": "C.12.1.1.3.1 and C.12-6",
                 "url": "https://dicom.nema.org/medical/dicom/2026d/output/chtml/part03/sect_C.12.html"},
                "DCMTK authors the conformant MAC stream. The named defect changes only its signing "
                "encoding or declaration; the source Data Set and pixel values remain unchanged."),
        "requirement_ids": [requirement],
    }


CASES = [
    _case(1, "omit-sequence-item-tag", "Ps3_C_12_1_1_3_1_1_5a8e43", "The signed stream omits a Sequence Item Tag."),
    _case(2, "omit-fragment-item-tag", "Ps3_C_12_1_1_3_1_1_88f6d4", "The signed stream omits the first Pixel Data Fragment Item Tag."),
    _case(3, "omit-nested-attribute", "Ps3_C_12_1_1_3_1_1_9cd4e0", "A signed Sequence's Specimen Identifier is omitted from its MAC stream."),
    _case(4, "omit-declared-tag", "Ps3_C_12_1_1_3_1_1_b3d0ca", "Data Elements Signed omits the SOP Instance UID that the actual MAC includes."),
    _case(5, "omit-sequence-delimiter", "Ps3_C_12_1_1_3_1_2_725031", "The MAC stream omits the required Sequence Delimitation Item Tag."),
    _case(6, "wrong-tag-byte-order", "Ps3_C_12_1_1_3_1_2_793fd1", "A signed Tag uses Big Endian byte order despite the declared Explicit VR Little Endian encoding."),
    _case(7, "include-sequence-value-length", "Ps3_C_12_1_1_3_1_2_974e7a", "The MAC stream incorrectly includes the Sequence Value Length."),
    _case(8, "omit-signature-datetime", "Ps3_C_12_1_1_3_1_2_e3cab5", "The Digital Signature DateTime is omitted from its implicit signed Attributes."),
    _case(9, "wrong-mac-algorithm", "Ps3_C_12_1_1_3_1_2_e64d07", "The Signature uses SHA512 over the correct stream while MAC Algorithm declares SHA256."),
    _case(10, "omit-primitive-vr", "Ps3_C_12_1_1_3_1_2_f55b08", "The MAC stream omits a primitive Data Element's VR field."),
    _case(11, "wrong-timestamp-imprint", "Ps3_C_12_6_CertifiedTimestamp_bedcdd", "The Certified Timestamp's message imprint differs from the Signature Value.", timestamp=True),
]
