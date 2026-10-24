"""Small loopback HTTP origin used by the v7 DICOMweb statement cases."""

from __future__ import annotations

import socketserver
import threading
import json
import io
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pydicom
from pydicom.encaps import generate_frames


STUDY_UID = "1.2.826.0.1.3680043.10.999.801"
SERIES_UID = "1.2.826.0.1.3680043.10.999.802"
INSTANCE_UID = "1.2.826.0.1.3680043.10.999.803"
BASE_PATH = "/dicomweb"
ABSENT_UID = "2.25.299792458299792458299792458299792458"
SERIES_UID_2 = "1.2.826.0.1.3680043.10.999.804"
INSTANCE_UID_2 = "1.2.826.0.1.3680043.10.999.805"
WSI_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.6"

# One deterministic baseline JPEG Frame from the existing PHI-free CP03
# control. This is not an HTTP-specific control and needs no image library.
_CP03 = Path(__file__).resolve().parent / "controls-v4" / "CP03-JPEG-1F.dcm"
_cp03 = pydicom.dcmread(_CP03)
JPEG = next(generate_frames(_cp03.PixelData, number_of_frames=int(_cp03.NumberOfFrames)))
_j2k = pydicom.dcmread(
    Path(__file__).resolve().parent
    / "controls-v7"
    / "wsi"
    / "W7-TS-J2K-PART1-RCT.dcm"
)
J2K = next(generate_frames(_j2k.PixelData, number_of_frames=int(_j2k.NumberOfFrames)))
_CP12 = (
    Path(__file__).resolve().parent
    / "controls-v7"
    / "mutation-sources"
    / "CP12-PYRAMID-2L"
    / "level-0.dcm"
)


def _strip_empty_json(value) -> None:
    if isinstance(value, dict):
        if value.get("Value") == []:
            value.pop("Value")
        for child in value.values():
            _strip_empty_json(child)
    elif isinstance(value, list):
        for child in value:
            _strip_empty_json(child)


STORE_PATH = _CP12
_store_dataset = pydicom.dcmread(_CP12)
STORE_STUDY_UID = str(_store_dataset.StudyInstanceUID)
STORE_SERIES_UID = str(_store_dataset.SeriesInstanceUID)
STORE_INSTANCE_UID = str(_store_dataset.SOPInstanceUID)
STORE_CLASS_UID = str(_store_dataset.SOPClassUID)
STORE_FILE = _CP12.read_bytes()
_store_metadata = _store_dataset.to_json_dict()
_strip_empty_json(_store_metadata)
STORE_METADATA_BYTES = json.dumps(
    [_store_metadata], separators=(",", ":"), sort_keys=True
).encode("utf-8")


def _metadata_document() -> dict:
    dataset = pydicom.dcmread(_CP12)
    dataset.StudyInstanceUID = STUDY_UID
    dataset.SeriesInstanceUID = SERIES_UID
    dataset.SOPInstanceUID = INSTANCE_UID
    document = dataset.to_json_dict()
    _strip_empty_json(document)
    document["7FE00010"] = {
        "vr": dataset["PixelData"].VR,
        "BulkDataURI": f"instances/{INSTANCE_UID}/bulk/pixeldata",
    }
    def externalize_icc(value):
        if isinstance(value, dict):
            if "00282000" in value:
                value["00282000"] = {"vr": "OB", "BulkDataURI": "bulk/icc"}
                return True
            return any(externalize_icc(child) for child in value.values())
        if isinstance(value, list):
            return any(externalize_icc(child) for child in value)
        return False
    if not externalize_icc(document):
        raise ValueError("CP12 has no ICC Profile to externalize")
    return document


METADATA = _metadata_document()
METADATA_BYTES = json.dumps([METADATA], separators=(",", ":"), sort_keys=True).encode("utf-8")
EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1"
ICC = bytes(next(element.value for element in _cp03.iterall() if element.tag == (0x0028, 0x2000)))


def _instance_file() -> bytes:
    dataset = pydicom.dcmread(_CP12)
    dataset.StudyInstanceUID = STUDY_UID
    dataset.SeriesInstanceUID = SERIES_UID
    dataset.SOPInstanceUID = INSTANCE_UID
    dataset.file_meta.MediaStorageSOPInstanceUID = INSTANCE_UID
    stream = io.BytesIO()
    pydicom.dcmwrite(stream, dataset, enforce_file_format=True)
    return stream.getvalue()


INSTANCE_FILE = _instance_file()


def _wadl(
    *, charset: bool = True, base: bool = True, applications: int = 1,
    thumbnail: bool = True,
) -> bytes:
    resources = "<resources" + (f' base="http://127.0.0.1{BASE_PATH}"' if base else "") + ">"
    for path in ("studies", "series", "instances", "metadata", "frames", "bulkdata", "rendered"):
        resources += f'<resource path="{path}"/>'
    if thumbnail:
        resources += '<resource path="thumbnail"/>'
    resources += "</resources>"
    application = (
        '<application xmlns="urn:ietf:params:xml:ns:wadl">'
        + resources
        + ("<doc>UTF-8</doc>" if charset else "")
        + "</application>"
    )
    return ("<?xml version=\"1.0\"?>" + application * applications).encode("utf-8")


@dataclass
class Response:
    status: int = 200
    reason: str = "OK"
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""
    unframed: bool = False
    chunked: bool = False
    silent: bool = False
    status_line: bytes | None = None
    length_without_payload: bool = False


def _attribute(vr: str, *values) -> dict:
    return {"vr": vr, **({"Value": list(values)} if values else {})}


def _study() -> dict:
    return {
        "00080020": _attribute("DA", "19700101"),
        "00080030": _attribute("TM", "120000"),
        "00080050": _attribute("SH"),
        "00080061": _attribute("CS", "SM", "CT"),
        "00080090": _attribute("PN", {"Alphabetic": "Reader^Research"}),
        "00100010": _attribute("PN", {"Alphabetic": "Research^Subject"}),
        "00100020": _attribute("LO", "RESEARCH"),
        "00100030": _attribute("DA", "19000101"),
        "00100040": _attribute("CS", "O"),
        "0020000D": _attribute("UI", STUDY_UID),
        "00200010": _attribute("SH", "HTTP"),
        "00201206": _attribute("IS", 2),
        "00201208": _attribute("IS", 2),
        "00081190": _attribute("UR", f"http://127.0.0.1{BASE_PATH}/studies/{STUDY_UID}"),
    }


def _series(uid: str, modality: str, number: int) -> dict:
    return {
        "00080060": _attribute("CS", modality),
        "0020000E": _attribute("UI", uid),
        "00200011": _attribute("IS", number),
        "00201209": _attribute("IS", 1),
        "00081190": _attribute(
            "UR", f"http://127.0.0.1{BASE_PATH}/studies/{STUDY_UID}/series/{uid}"
        ),
    }


def _instance(uid: str, number: int) -> dict:
    return {
        "00080016": _attribute("UI", WSI_CLASS),
        "00080018": _attribute("UI", uid),
        "00200013": _attribute("IS", number),
        "00280008": _attribute("IS", 4),
        "00280010": _attribute("US", 2),
        "00280011": _attribute("US", 2),
        "00280100": _attribute("US", 8),
        "00083002": _attribute("UI", "1.2.840.10008.1.2.1"),
        "00081190": _attribute(
            "UR",
            f"http://127.0.0.1{BASE_PATH}/studies/{STUDY_UID}/series/{SERIES_UID}/instances/{uid}",
        ),
    }


def _combined(*documents: dict) -> dict:
    combined = {}
    for document in documents:
        combined.update(document)
    return combined


STUDY = _study()
SERIES = [_series(SERIES_UID, "SM", 1), _series(SERIES_UID_2, "CT", 2)]
INSTANCES = [_instance(INSTANCE_UID, 1), _instance(INSTANCE_UID_2, 2)]


def _json_response(documents: list[dict], *headers: tuple[str, str]) -> Response:
    return Response(
        headers=[("Content-Type", "application/dicom+json"), *headers],
        body=json.dumps(documents, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    )


def _empty_xml() -> Response:
    boundary = "wsi-http-empty"
    xml = b"<NativeDicomModel/>"
    part = (
        f"--{boundary}\r\nContent-Type: application/dicom+xml\r\n"
        f"Content-Length: {len(xml)}\r\nContent-Location: empty\r\n\r\n"
    ).encode("ascii") + xml + (
        "\r\n"
        f"--{boundary}--\r\n"
    ).encode("ascii")
    return Response(
        headers=[
            ("Content-Type", f'multipart/related; type="application/dicom+xml"; boundary={boundary}')
        ],
        body=part,
    )


def _metadata_xml() -> Response:
    boundary = "wsi-http-metadata"
    xml = b"<NativeDicomModel/>"
    body = (
        f"--{boundary}\r\nContent-Type: application/dicom+xml\r\n"
        f"Content-Length: {len(xml)}\r\nContent-Location: metadata\r\n\r\n"
    ).encode("ascii") + xml + f"\r\n--{boundary}--\r\n".encode("ascii")
    return Response(
        headers=[
            ("Content-Type", f'multipart/related; type="application/dicom+xml"; boundary={boundary}'),
            ("Content-Location", "metadata"),
        ],
        body=body,
    )


def _metadata_xml_unquoted() -> Response:
    response = _metadata_xml()
    response.headers = [
        (name, value.replace('type="application/dicom+xml"', "type=application/dicom+xml"))
        for name, value in response.headers
    ]
    return response


def _metadata_response(scenario: str, target: str, headers: dict[str, str]) -> Response:
    query = parse_qs(urlsplit(target).query, keep_blank_values=True)
    accept = headers.get("accept", "")
    accepted_query = query.get("accept", [""])[0]
    if scenario == "accept-mixed-query-accepted" and ",text/html" in accepted_query:
        accepted_query = "application/dicom+json"
    elif ",text/html" in accepted_query:
        return Response(
            status=400,
            reason="Bad Request",
            headers=[("Content-Type", "text/plain")],
            body=b"DICOM and rendered media types cannot be mixed; this is a permanent condition",
        )
    if (
        scenario != "accept-mixed-header-accepted"
        and "application/dicom+json" in accept
        and "image/png" in accept
    ):
        return Response(
            status=400,
            reason="Bad Request",
            headers=[("Content-Type", "text/plain")],
            body=b"DICOM and rendered media types cannot be mixed; this is a permanent condition",
        )
    if accept == "application/x-wsidicom-unsupported" and scenario != "accept-unsupported-default-wrong":
        body = (
            b"not acceptable"
            if scenario == "notacceptable-unlisted"
            else b"available application/dicom+json at this Metadata resource; this is a permanent condition"
        )
        return Response(
            status=406,
            reason="Not Acceptable",
            headers=[("Content-Type", "text/plain")],
            body=body,
        )
    if scenario == "accept-unsupported-default-wrong" and accept == "application/x-wsidicom-unsupported":
        return Response(
            headers=[("Content-Type", "application/json")],
            body=METADATA_BYTES,
        )
    if scenario == "accept-invalid-rejected" and "wsidicom-invalid" in accept:
        return Response(status=406, reason="Not Acceptable")
    if scenario == "accept-wildcard-not-default" and accept == "*/*":
        return _metadata_xml()
    if scenario == "accept-qvalues-ignored" and "q=0.5" in accept:
        accept = "application/dicom+json"
    if scenario == "accept-query-ignored" and accepted_query:
        accepted_query = ""
    if scenario == "charset-query-rejected" and "charset" in query:
        return Response(status=406, reason="Not Acceptable")
    if scenario == "charset-header-rejected" and "accept-charset" in headers:
        return Response(status=406, reason="Not Acceptable")
    if scenario == "charset-media-parameters-rejected" and "charset=" in accept:
        return Response(status=406, reason="Not Acceptable")
    if "application/dicom+xml" in accept and not accepted_query:
        return _metadata_xml_unquoted() if scenario == "multipart-unquoted" else _metadata_xml()
    if scenario == "metadata-response-malformed":
        return Response(status_line=b"not an HTTP response\r\n")
    body = METADATA_BYTES
    if scenario == "metadata-omits-attribute":
        document = json.loads(METADATA_BYTES)
        document[0].pop("00080008", None)
        body = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    elif scenario in {"frames-native-j2k", "frames-syntax-before-media"}:
        document = json.loads(METADATA_BYTES)
        document[0]["00280010"] = _attribute("US", 16)
        document[0]["00280011"] = _attribute("US", 16)
        body = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    response = Response(
        headers=[
            ("Content-Type", "application/dicom+json"),
            ("Content-Location", target.split("?", 1)[0]),
        ],
        body=body,
    )
    if scenario == "metadata-no-content-location":
        response.headers = [header for header in response.headers if header[0] != "Content-Location"]
    if scenario == "metadata-no-content-type":
        response.headers = [header for header in response.headers if header[0] != "Content-Type"]
    if scenario == "metadata-unframed":
        response.unframed = True
    if scenario in ("range-valid", "range-malformed") and "range" in headers:
        response.status = 206
        response.reason = "Partial Content"
        response.headers.append(
            (
                "Content-Range",
                "bytes 0-15/{}".format(len(METADATA_BYTES))
                if scenario == "range-valid"
                else "bytes nope",
            )
        )
        response.body = METADATA_BYTES[:16]
    return response


def _multipart_response(
    root_type: str,
    parts: list[tuple[str, str | None, bytes]],
    *,
    scenario: str = "retrieve",
) -> Response:
    boundary = "wsi-http-retrieve"
    body = bytearray()
    for content_type, location, payload in parts:
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        if scenario != "frames-no-part-type":
            body.extend(f"Content-Type: {content_type}\r\n".encode("ascii"))
        if scenario != "frames-part-no-length":
            body.extend(f"Content-Length: {len(payload)}\r\n".encode("ascii"))
        if location is not None:
            body.extend(f"Content-Location: {location}\r\n".encode("ascii"))
        if scenario == "multipart-duplicate-content-id":
            body.extend(b"Content-ID: <duplicate@wsi-http>\r\n")
        body.extend(b"\r\n")
        body.extend(payload)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("ascii"))
    outer = f"multipart/related; type={root_type}; boundary={boundary}"
    if scenario == "frames-no-type-parameter":
        outer = f"multipart/related; boundary={boundary}"
    elif scenario == "frames-single-part-label":
        outer = root_type
    return Response(headers=[("Content-Type", outer)], body=bytes(body))


def _frames_response(scenario: str, target: str, headers: dict[str, str]) -> Response:
    path = target.split("?", 1)[0]
    numbers = path.rsplit("/", 1)[-1].split(",")
    accept = headers.get("accept", "")
    if scenario == "frames-syntax-rejected" and "transfer-syntax=" in accept:
        return Response(status=406, reason="Not Acceptable")
    if any(number not in {"1", "2", "3", "4"} for number in numbers):
        if scenario == "frames-missing-empty":
            return Response(status=404, reason="Not Found")
        if scenario != "frames-missing-200":
            return Response(
                status=404,
                reason="Not Found",
                headers=[("Content-Type", "text/plain")],
                body=b"requested Frame does not exist; this is a permanent condition",
            )
        numbers = ["1"]
    syntax = EXPLICIT_VR_LITTLE_ENDIAN
    if scenario == "frames-default-not-explicit":
        syntax = "1.2.840.10008.1.2.1.98"
    elif scenario == "frames-forbidden-syntax":
        syntax = "1.2.840.10008.1.2"
    native_j2k = scenario in {"frames-native-j2k", "frames-syntax-before-media"}
    mixed_j2k = "application/octet-stream" in accept and "image/jp2" in accept
    wants_j2k = "image/jp2" in accept and "application/octet-stream" not in accept
    if native_j2k and (wants_j2k or (mixed_j2k and scenario == "frames-syntax-before-media")):
        content_type = "image/jp2; transfer-syntax=1.2.840.10008.1.2.4.90"
    else:
        content_type = f"application/octet-stream; transfer-syntax={syntax}"
    if scenario == "frames-two-syntaxes":
        content_type += f"; transfer-syntax={EXPLICIT_VR_LITTLE_ENDIAN}"
    size = 768 if native_j2k else 11 if scenario == "frames-uncompressed-wrong-size" else 12
    parts = []
    for number in numbers:
        location = f"{path.rsplit('/', 1)[0]}/{number}"
        if scenario == "frames-wrong-content-location":
            location = f"{path.rsplit('/', 3)[0]}/instances/{ABSENT_UID}/frames/{number}"
        payload = J2K if content_type.startswith("image/jp2") else bytes(size)
        parts.append((content_type, location, payload))
    root_type = "image/jp2" if content_type.startswith("image/jp2") else "application/octet-stream"
    return _multipart_response(root_type, parts, scenario=scenario)


def _jpeg(width: int, height: int, *, progressive: bool = False) -> bytes:
    image = bytearray(JPEG)
    marker = b"\xff\xc0"
    at = image.find(marker)
    if at < 0:
        raise ValueError("baseline control JPEG has no SOF0")
    if progressive:
        image[at + 1] = 0xC2
    image[at + 5 : at + 7] = height.to_bytes(2, "big")
    image[at + 7 : at + 9] = width.to_bytes(2, "big")
    return bytes(image)


def _jpeg_with_icc(image: bytes, profile: bytes) -> bytes:
    chunks = [profile[index : index + 60_000] for index in range(0, len(profile), 60_000)]
    embedded = bytearray(image[:2])
    for index, chunk in enumerate(chunks, start=1):
        payload = b"ICC_PROFILE\0" + bytes((index, len(chunks))) + chunk
        embedded.extend(b"\xff\xe2")
        embedded.extend((len(payload) + 2).to_bytes(2, "big"))
        embedded.extend(payload)
    embedded.extend(image[2:])
    return bytes(embedded)


def _png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00"
    )


def _rendered_response(scenario: str, target: str, headers: dict[str, str]) -> Response:
    query = parse_qs(urlsplit(target).query, keep_blank_values=True)
    accept = headers.get("accept", "image/jpeg")
    frame_list = target.split("?", 1)[0].rsplit("/frames/", 1)[-1].split("/", 1)[0]
    if "," in frame_list and "x-wsidicom-unsupported" in accept:
        if scenario != "rendered-no-default-accepted":
            return Response(status=406, reason="Not Acceptable")
    if scenario == "rendered-utf8-rejected" and "charset" in query:
        return Response(status=406, reason="Not Acceptable")
    if scenario == "rendered-no-png" and "image/png" in accept:
        return Response(status=406, reason="Not Acceptable")
    if "image/jph" in accept:
        if scenario == "rendered-jph-no-box":
            return Response(headers=[("Content-Type", "image/jph")], body=_jpeg(2, 2))
        return Response(status=406, reason="Not Acceptable")
    annotation = query.get("annotation", [None])[0]
    quality = query.get("quality", [None])[0]
    window = query.get("window", [None])[0]
    viewport = query.get("viewport", [None])[0]
    if annotation == "" and scenario != "rendered-annotation-empty-accepted":
        return Response(status=400, reason="Bad Request")
    if scenario == "rendered-required-parameters-rejected" and (
        annotation == "patient" or quality == "90" or window == "128,256,linear"
    ):
        return Response(status=400, reason="Bad Request")
    if quality is not None:
        valid = quality.isdigit() and 1 <= int(quality) <= 100
        if valid and scenario == "rendered-quality-rejected":
            return Response(status=400, reason="Bad Request")
        if not valid and scenario != "rendered-quality-invalid-accepted":
            return Response(status=400, reason="Bad Request")
    if window is not None:
        fields = window.split(",")
        valid = len(fields) == 3 and fields[2] in {"linear", "linear-exact", "sigmoid"}
        if valid and scenario == "rendered-window-rejected":
            return Response(status=400, reason="Bad Request")
        if not valid and scenario != "rendered-window-invalid-accepted":
            return Response(status=400, reason="Bad Request")
    width, height = 2, 2
    if viewport is not None:
        fields = viewport.split(",")
        if len(fields) < 2 or not fields[0].isdigit() or not fields[1].isdigit():
            if scenario != "rendered-viewport-invalid-accepted":
                return Response(status=400, reason="Bad Request")
        else:
            into_width, into_height = int(fields[0]), int(fields[1])
            region_width, region_height = 2, 2
            if len(fields) >= 6:
                region_width = int(fields[4]) if fields[4] else 2
                region_height = int(fields[5]) if fields[5] else 2
                if scenario == "rendered-crop-ignored":
                    region_width, region_height = 2, 2
                elif scenario == "rendered-elided-wrong" and not fields[4]:
                    region_width = 1
            scale = min(
                into_width / max(region_width, 1),
                into_height / max(region_height, 1),
            )
            width = max(1, round(region_width * scale))
            height = max(1, round(region_height * scale))
            if scenario == "rendered-viewport-wrong-size":
                width, height = 2, 2
    elif scenario == "rendered-unscaled-wrong-size":
        width, height = 4, 4
    warning = None
    if annotation and "wsidicomprobe" in annotation:
        if scenario == "rendered-annotation-rejected":
            return Response(status=400, reason="Bad Request")
        if scenario != "rendered-annotation-no-warning":
            warning = (
                "299 http://127.0.0.1/dicomweb: The following annotation values "
                "are not supported: wsidicomprobe"
            )
    if "image/png" in accept:
        content_type = "image/png"
        body = _png(width, height)
    else:
        content_type = "image/jpeg"
        body = _jpeg(width, height, progressive=scenario == "rendered-progressive")
        icc_value = query.get("iccprofile", [None])[0]
        profile = None
        if scenario == "rendered-icc-no-ignored":
            profile = ICC if icc_value in {"no", "yes"} else None
        elif scenario == "rendered-icc-yes-missing":
            profile = ICC if icc_value == "srgb" else None
        elif scenario == "rendered-icc-srgb-wrong":
            profile = ICC if icc_value == "yes" else None
        elif scenario in {
            "rendered-icc-adobe-wrong",
            "rendered-icc-romm-wrong",
            "rendered-icc-p3-wrong",
        }:
            wrong_value = {
                "rendered-icc-adobe-wrong": "adobergb",
                "rendered-icc-romm-wrong": "rommrgb",
                "rendered-icc-p3-wrong": "displayp3",
            }[scenario]
            profile = ICC if icc_value in {"yes", wrong_value} else None
        elif scenario == "rendered-icc-malformed":
            profile = b"not an ICC profile" if icc_value == "yes" else None
        if profile is not None:
            body = _jpeg_with_icc(body, profile)
    if scenario == "rendered-wrong-type":
        content_type = "application/octet-stream"
    elif scenario == "rendered-with-syntax":
        content_type += "; transfer-syntax=1.2.840.10008.1.2.4.50"
    elif scenario == "rendered-multipart-label":
        content_type = "multipart/related; type=image/jpeg; boundary=wsi-rendered"
    response_headers = [("Content-Type", content_type), ("Content-Location", target.split("?", 1)[0])]
    if warning:
        response_headers.append(("Warning", warning))
    return Response(headers=response_headers, body=body)


def _bulk_response(scenario: str, target: str) -> Response:
    path = target.split("?", 1)[0]
    location = path
    if scenario == "bulk-wrong-location":
        location = path.rsplit("/", 1)[0] + "/other"
    part_type = "application/octet-stream"
    if scenario == "bulk-wrong-type":
        part_type = "application/dicom"
    payload = ICC[:-8] if scenario == "bulk-truncated" else ICC
    return _multipart_response(part_type, [(part_type, location, payload)], scenario=scenario)


def _instance_response(scenario: str, target: str, headers: dict[str, str]) -> Response:
    path = target.split("?", 1)[0]
    accept = headers.get("accept", "")
    if scenario == "instance-wildcard-rejected" and "transfer-syntax=*" in accept:
        return Response(status=406, reason="Not Acceptable")
    payload = INSTANCE_FILE
    if scenario == "instance-not-part10":
        payload = payload[132:]
    elif scenario == "instance-truncated":
        payload = payload[:-64]
    syntax = EXPLICIT_VR_LITTLE_ENDIAN
    if scenario == "instance-implicit-syntax":
        syntax = "1.2.840.10008.1.2"
    elif scenario == "instance-big-endian-syntax":
        syntax = "1.2.840.10008.1.2.2"
    elif scenario == "instance-unsupported-no-default" and "1.2.840.10008.1.2.4.100" in accept:
        syntax = "1.2.840.10008.1.2.4.100"
    part_type = f"application/dicom; transfer-syntax={syntax}"
    return _multipart_response("application/dicom", [(part_type, path, payload)], scenario=scenario)


def _store_response(scenario: str) -> Response:
    if scenario == "store-missing":
        return Response(
            status=405,
            reason="Method Not Allowed",
            headers=[("Allow", "GET, OPTIONS")],
            body=b"Store is not supported; this is a permanent condition",
        )
    if scenario == "store-reject-chunked":
        return Response(
            status=411,
            reason="Length Required",
            headers=[("Content-Type", "text/plain")],
            body=b"chunked requests are not accepted; this is a permanent condition",
        )
    if scenario == "store-conflict-empty":
        return Response(status=409, reason="Conflict")
    if scenario == "store-202-empty":
        return Response(status=202, reason="Accepted")
    study_url = f"{BASE_PATH}/studies/{STORE_STUDY_UID}"
    instance_url = (
        f"{study_url}/series/{STORE_SERIES_UID}/instances/{STORE_INSTANCE_UID}"
    )
    item = {
        "00081150": _attribute("UI", STORE_CLASS_UID),
        "00081155": _attribute("UI", STORE_INSTANCE_UID),
        "00081190": _attribute("UR", instance_url),
    }
    if scenario == "store-two-modified-items":
        modified = {"00100020": _attribute("LO", "RESEARCH")}
        item["04000561"] = {
            "vr": "SQ",
            "Value": [
                {
                    "04000550": {"vr": "SQ", "Value": [modified, modified]},
                    "04000562": _attribute("DT", "20260101120000"),
                    "04000563": _attribute("LO", "HTTP"),
                    "04000565": _attribute("CS", "COERCE"),
                }
            ],
        }
    module = {
        "00081190": _attribute("UR", study_url),
        "00081199": {"vr": "SQ", "Value": [item]},
    }
    response_headers = []
    if scenario != "store-no-location":
        response_headers.append(("Location", study_url))
    if scenario != "store-no-content-location":
        response_headers.append(("Content-Location", study_url))
    response = _json_response(
        [] if scenario == "store-no-module" else [module], *response_headers
    )
    if scenario == "store-202-clean":
        response.status = 202
        response.reason = "Accepted"
    elif scenario == "store-warning-without-status":
        response.headers.append(("Warning", "299 wsi-http: stored with changes"))
    elif scenario == "store-response-malformed":
        response.status_line = b"not an HTTP response\r\n"
    elif scenario == "store-unframed":
        response.unframed = True
    return response


def _search_response(
    scenario: str,
    target: str,
    headers: dict[str, str],
    counts: dict[str, int],
) -> Response:
    parsed = urlsplit(target)
    path = parsed.path
    query = parse_qs(parsed.query, keep_blank_values=True)
    accept = headers.get("accept")
    if scenario in ("search-too-broad-good", "search-too-broad-empty") and path == f"{BASE_PATH}/instances":
        body = (
            b"the search was too broad; narrow the query; this is a temporary condition"
            if scenario == "search-too-broad-good"
            else b""
        )
        return Response(
            status=413,
            reason="Payload Too Large",
            headers=[("Content-Type", "text/plain")] if body else [],
            body=body,
        )
    if scenario == "search-accept-charset-rejected" and "accept-charset" in headers:
        return Response(status=406, reason="Not Acceptable")
    if accept is None and scenario == "search-no-accept-status-json":
        return Response(
            status=406,
            reason="Not Acceptable",
            headers=[("Content-Type", "application/json")],
            body=b'{"error":"Accept is required"}',
        )
    if accept is None and scenario == "search-no-accept-accepted":
        accept = "application/dicom+json"
    if accept is None:
        return Response(
            status=406,
            reason="Not Acceptable",
            headers=[("Content-Type", "text/html")],
            body=b"<p>Accept is required</p>",
        )
    if query.get("limit") == ["many"] and scenario != "search-invalid-limit-accepted":
        return Response(
            status=400,
            reason="Bad Request",
            headers=[("Content-Type", "text/plain")],
            body=b"invalid limit",
        )
    if scenario == "search-unknown-parameter-rejected" and "wsidicomprobe" in query:
        return Response(
            status=400,
            reason="Bad Request",
            headers=[("Content-Type", "text/plain")],
            body=b"unknown parameter",
        )

    initial_study = (
        path == f"{BASE_PATH}/studies"
        and query.get("StudyInstanceUID") == [STUDY_UID]
        and query.get("includefield") == ["00200013"]
    )
    initial_series = (
        path == f"{BASE_PATH}/studies/{STUDY_UID}/series"
        and query.get("includefield") == ["00200013"]
        and "SeriesInstanceUID" not in query
    )
    initial_instances = (
        path == f"{BASE_PATH}/studies/{STUDY_UID}/series/{SERIES_UID}/instances"
        and query.get("includefield") == ["00083002"]
        and "SOPInstanceUID" not in query
    )
    if scenario == "search-series-resource-missing" and initial_series:
        return Response(status=404, reason="Not Found", headers=[("Content-Type", "text/plain")], body=b"missing")

    if path == f"{BASE_PATH}/studies":
        documents = [STUDY]
        unique = query.get("StudyInstanceUID", [STUDY_UID])[0]
    elif path == f"{BASE_PATH}/studies/{STUDY_UID}/series":
        documents = list(SERIES)
        unique = query.get("SeriesInstanceUID", [None])[0]
        if unique:
            documents = [SERIES[0]] if unique == SERIES_UID else []
        if query.get("Modality") == ["SM"]:
            documents = [SERIES[0]]
    elif path == f"{BASE_PATH}/studies/{STUDY_UID}/series/{SERIES_UID}/instances":
        documents = list(INSTANCES)
        unique = query.get("SOPInstanceUID", [None])[0]
        if unique:
            documents = [INSTANCES[0]] if unique == INSTANCE_UID else []
    elif path == f"{BASE_PATH}/studies/{STUDY_UID}/instances":
        documents = [_combined(SERIES[0], INSTANCES[0])]
        unique = query.get("SOPInstanceUID", [INSTANCE_UID])[0]
    elif path == f"{BASE_PATH}/series":
        documents = [_combined(STUDY, SERIES[0])]
        unique = query.get("SeriesInstanceUID", [SERIES_UID])[0]
    elif path == f"{BASE_PATH}/instances":
        documents = [_combined(STUDY, SERIES[0], INSTANCES[0])]
        unique = query.get("SOPInstanceUID", [INSTANCE_UID])[0]
    elif path.startswith(f"{BASE_PATH}/studies/{ABSENT_UID}"):
        documents = []
        unique = ABSENT_UID
    else:
        return Response(status=404, reason="Not Found", headers=[("Content-Type", "text/plain")], body=b"not found")

    documents = json.loads(json.dumps(documents))
    if scenario in {"frames-native-j2k", "frames-syntax-before-media"}:
        for document in documents:
            if "00080018" in document:
                document["00083002"] = _attribute("UI", "1.2.840.10008.1.2.4.90")
    if scenario == "search-retrieve-url-missing":
        for document in documents:
            document.pop("00081190", None)
    if (
        path == f"{BASE_PATH}/studies"
        and query.get("includefield", [""])[0] in ("00081030", "all")
        and scenario != "search-includefield-ignored"
        and documents
    ):
        documents[0]["00081030"] = _attribute("LO", "HTTP Study")
    if scenario == "search-study-no-result" and initial_study:
        documents = []
    elif scenario == "search-study-missing-key" and initial_study and documents:
        documents[0].pop("00100030", None)
    elif scenario == "search-study-instance-leak" and initial_study and documents:
        documents[0]["00200013"] = _attribute("IS", 1)
    elif scenario == "search-series-missing-key" and initial_series and documents:
        documents[0].pop("00080060", None)
    elif scenario == "search-series-instance-leak" and initial_series and documents:
        for document in documents:
            document["00200013"] = _attribute("IS", 1)
    elif scenario == "search-instance-missing-key" and initial_instances and documents:
        documents[0].pop("00200013", None)

    values = [value for found in query.values() for value in found]
    no_match = any(
        value == ABSENT_UID
        or "WSIDICOMNOMATCH" in value
        or "XQZ" in value
        or value in {"999999", "999998", "19000102", "19000103", "000001", "000002"}
        or value.endswith("\\ZZ")
        for value in values
    )
    if query.get("emptyvaluematching") == ["false"] and '""' in values:
        no_match = True
    warning = None
    for flag, text in (
        ("fuzzymatching", "The fuzzymatching parameter is not supported"),
        ("emptyvaluematching", "The emptyvaluematching parameter is not supported"),
        ("multiplevaluematching", "The multiplevaluematching parameter is not supported"),
    ):
        if query.get(flag) == ["true"]:
            warning = f'299 http://127.0.0.1{BASE_PATH}: {text}. Literal matching used'
            no_match = True
    if scenario == "search-match-ignored" and "SeriesInstanceUID" in query:
        no_match = False
        unique = None
    if scenario == "search-required-match-ignored" and no_match:
        no_match = False
    if scenario == "search-hierarchy-ignored" and path.startswith(f"{BASE_PATH}/studies/{ABSENT_UID}"):
        documents = list(SERIES)
    if scenario == "search-datetime-separate" and "StudyDate" in query and "StudyTime" in query:
        no_match = True
    if unique == ABSENT_UID or no_match:
        documents = []
    if scenario == "search-hierarchy-ignored" and path.startswith(
        f"{BASE_PATH}/studies/{ABSENT_UID}"
    ):
        documents = json.loads(json.dumps(SERIES))
    if scenario == "search-match-ignored" and "SeriesInstanceUID" in query:
        documents = json.loads(json.dumps(SERIES))
    if scenario == "search-empty-204" and not documents:
        return Response(status=204, reason="No Content")
    if scenario == "search-empty-not-array" and not documents and "application/dicom+json" in accept:
        return Response(headers=[("Content-Type", "application/dicom+json")], body=b"{}")
    if "application/dicom+xml" in accept and not documents:
        if scenario == "search-xml-not-empty":
            broken = b'<NativeDicomModel><DicomAttribute tag="00080018" vr="UI"/></NativeDicomModel>'
            boundary = "wsi-http-empty"
            body = (
                f"--{boundary}\r\nContent-Type: application/dicom+xml\r\n"
                f"Content-Length: {len(broken)}\r\nContent-Location: empty\r\n\r\n"
            ).encode("ascii") + broken + f"\r\n--{boundary}--\r\n".encode("ascii")
            return Response(
                headers=[("Content-Type", f'multipart/related; type="application/dicom+xml"; boundary={boundary}')],
                body=body,
            )
        return _empty_xml()

    offset = int(query.get("offset", ["0"])[0])
    limit = query.get("limit")
    if scenario == "search-invalid-limit-accepted" and limit == ["many"]:
        limit = None
    all_count = len(documents)
    if limit:
        chosen_offset = 0 if scenario == "search-paging-ignore-offset" else offset
        chosen_limit = all_count if scenario == "search-paging-ignore-limit" else int(limit[0])
        documents = documents[chosen_offset : chosen_offset + chosen_limit]
        remaining = max(0, all_count - offset - len(documents))
        if remaining:
            if scenario != "search-paging-no-warning":
                agent = "not-a-url" if scenario == "search-paging-warning-no-url" else f"http://127.0.0.1{BASE_PATH}"
                warning = (
                    f"299 {agent}: There are {remaining} additional results that can be requested"
                )
    counts[target] = counts.get(target, 0) + 1
    if scenario == "search-non-idempotent" and counts[target] > 1 and not limit:
        documents.reverse()
    if scenario == "search-flags-rejected" and all(
        name in query
        for name in ("fuzzymatching", "emptyvaluematching", "multiplevaluematching")
    ):
        return Response(status=400, reason="Bad Request", headers=[("Content-Type", "text/plain")], body=b"flags rejected")
    fuzzy = query.get("fuzzymatching")
    if scenario == "search-fuzzy-despite-false" and fuzzy == ["false"]:
        documents = [json.loads(json.dumps(STUDY))]
    elif scenario == "search-fuzzy-warning-missing" and fuzzy == ["true"]:
        warning = None
    elif scenario == "search-fuzzy-supported-undocumented" and fuzzy == ["true"]:
        warning = None
        documents = [json.loads(json.dumps(STUDY))]
    elif scenario == "search-fuzzy-unsupported-applied" and fuzzy == ["true"]:
        documents = [json.loads(json.dumps(STUDY))]
    empty = query.get("emptyvaluematching")
    if scenario == "search-empty-despite-false" and empty == ["false"]:
        documents = [json.loads(json.dumps(STUDY))]
    elif scenario == "search-empty-warning-missing" and empty == ["true"]:
        warning = None
    elif scenario == "search-empty-unsupported-applied" and empty == ["true"]:
        documents = [json.loads(json.dumps(STUDY))]
    elif scenario == "search-empty-supported-undocumented" and empty == ["true"]:
        warning = None
        documents = [json.loads(json.dumps(STUDY))]
    multiple = query.get("multiplevaluematching")
    if scenario == "search-multiple-warning-missing" and multiple == ["true"]:
        warning = None
    elif scenario == "search-multiple-supported-undocumented" and multiple == ["true"]:
        warning = None
        documents = [] if any(value.endswith("\\ZZ") for value in values) else [json.loads(json.dumps(STUDY))]
    if scenario == "search-matched-attribute-omitted" and documents and any(
        key in query for key in ("StudyDate", "Modality", "SOPClassUID")
    ):
        for tag in ("00080020", "00080060", "00080016"):
            documents[0].pop(tag, None)
    if scenario == "search-all-series-no-study" and path == f"{BASE_PATH}/series":
        documents = [json.loads(json.dumps(SERIES[0]))]
    if scenario == "search-all-instances-no-series" and path == f"{BASE_PATH}/instances":
        documents = [json.loads(json.dumps(INSTANCES[0]))]
    if scenario == "search-ie-level-ignored" and path in (
        f"{BASE_PATH}/series", f"{BASE_PATH}/instances", f"{BASE_PATH}/studies/{STUDY_UID}/instances"
    ):
        documents = []
    if scenario == "search-study-wrong-media" and initial_study:
        return Response(headers=[("Content-Type", "application/json")], body=json.dumps(documents, sort_keys=True).encode())
    extra = (("Warning", warning),) if warning else ()
    response = _json_response(documents, *extra)
    if scenario == "search-response-malformed" and initial_study:
        response.status_line = b"not an HTTP response\r\n"
    elif scenario == "search-no-content-type" and initial_study:
        response.headers = [header for header in response.headers if header[0] != "Content-Type"]
    elif scenario == "search-unframed" and initial_study:
        response.unframed = True
    return response


def _capabilities(scenario: str) -> Response:
    response = Response(
        headers=[("Content-Type", "application/vnd.sun.wadl+xml")],
        body=_wadl(),
    )
    if scenario == "capabilities-missing":
        return Response(status=405, reason="Method Not Allowed", headers=[("Allow", "GET")])
    if scenario == "capabilities-304":
        return Response(status=304, reason="Not Modified")
    if scenario == "capabilities-wrong-media":
        response.headers = [("Content-Type", "text/plain")]
    elif scenario == "capabilities-empty":
        response.headers = [("Content-Type", "application/json")]
        response.body = b""
    elif scenario == "capabilities-two-applications":
        response.body = _wadl(applications=2)
    elif scenario == "capabilities-no-base":
        response.body = _wadl(base=False)
    elif scenario == "capabilities-no-charset":
        response.body = _wadl(charset=False)
    elif scenario == "capabilities-omit-thumbnail":
        response.body = _wadl(thumbnail=False)
    elif scenario == "response-silent":
        response.silent = True
    elif scenario == "response-status-invalid":
        response.status = 600
        response.reason = "Invalid"
    elif scenario == "payload-no-content-type":
        response.headers = []
    elif scenario == "payload-unframed":
        response.unframed = True
    elif scenario == "payload-length-with-chunked":
        response.chunked = True
    elif scenario == "payload-empty-unframed":
        response.headers = [("Content-Type", "application/json")]
        response.body = b""
        response.unframed = True
    elif scenario == "payload-204-length":
        response = Response(status=204, reason="No Content", length_without_payload=True)
    elif scenario == "payload-204-type":
        response = Response(
            status=204,
            reason="No Content",
            headers=[("Content-Type", "application/json")],
        )
    elif scenario == "payload-unquoted-charset":
        response.headers = [("Content-Type", "application/json; charset=ISO IR 192")]
        response.body = b'{"charset":"UTF-8"}'
    elif scenario == "payload-dicom-outside-instance":
        response.headers = [("Content-Type", "application/dicom")]
    return response


def response_for(
    scenario: str, method: str, target: str, headers: dict[str, str], counts: dict[str, int]
) -> Response:
    path = target.split("?", 1)[0]
    if headers.get("authorization") == "Bearer wsi-dicom-invalid-credential":
        response_headers = [("Content-Type", "text/plain")]
        if scenario != "unauthorized-no-challenge":
            response_headers.append(("WWW-Authenticate", 'Bearer realm="wsi-http"'))
        return Response(
            status=401,
            reason="Unauthorized",
            headers=response_headers,
            body=b"invalid credential; authentication is required; this is a permanent condition",
        )
    if method == "TRACE":
        response_headers = [("Content-Type", "text/plain")]
        if scenario != "not-allowed-no-allow":
            response_headers.append(("Allow", "GET, POST, OPTIONS"))
        return Response(
            status=405,
            reason="Method Not Allowed",
            headers=response_headers,
            body=b"TRACE is not supported; this is a permanent condition",
        )
    if method == "OPTIONS" and path.rstrip("/") == BASE_PATH:
        return _capabilities(scenario)
    if method == "POST" and path == f"{BASE_PATH}/studies":
        return _store_response(scenario)
    if method == "GET" and STORE_INSTANCE_UID in path and path.endswith("/metadata"):
        body = STORE_METADATA_BYTES
        if scenario == "store-coerced-silently":
            document = json.loads(STORE_METADATA_BYTES)
            document[0]["00100020"] = _attribute("LO", "COERCED")
            body = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return Response(
            headers=[
                ("Content-Type", "application/dicom+json"),
                ("Content-Location", target.split("?", 1)[0]),
            ],
            body=body,
        )
    if method == "GET" and path.endswith(f"/instances/{STORE_INSTANCE_UID}"):
        part_type = f"application/dicom; transfer-syntax={EXPLICIT_VR_LITTLE_ENDIAN}"
        payload = STORE_FILE[:-64] if scenario == "store-readback-truncated" else STORE_FILE
        return _multipart_response(
            "application/dicom", [(part_type, path, payload)], scenario=scenario
        )
    if method == "GET" and path.endswith("/metadata"):
        return _metadata_response(scenario, target, headers)
    if method == "GET" and path.endswith("/rendered"):
        return _rendered_response(scenario, target, headers)
    if method == "GET" and path.endswith("/bulk/icc"):
        return _bulk_response(scenario, target)
    if method == "GET" and path.endswith(f"/instances/{INSTANCE_UID}"):
        return _instance_response(scenario, target, headers)
    if method == "GET" and "/frames/" in path and not path.endswith(("/rendered", "/thumbnail")):
        return _frames_response(scenario, target, headers)
    if method == "GET" and (
        path in (f"{BASE_PATH}/studies", f"{BASE_PATH}/series", f"{BASE_PATH}/instances")
        or path.startswith(f"{BASE_PATH}/studies/")
    ) and not path.endswith("/thumbnail"):
        return _search_response(scenario, target, headers, counts)
    if method == "GET" and path.endswith("/thumbnail"):
        if scenario == "thumbnail-partial" and f"/series/{SERIES_UID}/thumbnail" in path:
            return Response(status=404, reason="Not Found")
        if scenario == "thumbnail-multipart":
            return _multipart_response(
                "image/jpeg", [("image/jpeg", target, JPEG)], scenario=scenario
            )
        return Response(
            headers=[("Content-Type", "image/jpeg"), ("Content-Location", target)],
            body=JPEG,
        )
    return Response(
        status=404,
        reason="Not Found",
        headers=[("Content-Type", "text/plain")],
        body=b"not found",
    )


def _read_request(stream) -> tuple[str, str, dict[str, str]] | None:
    line = stream.readline(64 * 1024)
    if not line:
        return None
    parts = line.decode("latin-1", "replace").strip().split()
    if len(parts) < 2:
        return None
    headers = {}
    while True:
        header = stream.readline(64 * 1024)
        if not header or header in (b"\r\n", b"\n"):
            break
        name, separator, value = header.decode("latin-1", "replace").partition(":")
        if separator:
            headers[name.strip().lower()] = value.strip()
    if "chunked" in headers.get("transfer-encoding", "").lower():
        while True:
            size_line = stream.readline(64 * 1024).split(b";", 1)[0].strip()
            try:
                size = int(size_line, 16)
            except ValueError:
                break
            if size == 0:
                while stream.readline(64 * 1024) not in (b"\r\n", b"\n", b""):
                    pass
                break
            stream.read(size)
            stream.read(2)
    elif headers.get("content-length", "").isdigit():
        stream.read(int(headers["content-length"]))
    return parts[0], parts[1], headers


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        request = _read_request(self.rfile)
        if request is None:
            return
        method, target, headers = request
        response = response_for(
            self.server.scenario, method, target, headers, self.server.counts
        )
        self.server.requests.append((method, target))
        if response.silent:
            return
        status = response.status_line or (
            f"HTTP/1.1 {response.status} {response.reason}\r\n".encode("ascii")
        )
        self.wfile.write(status)
        for name, value in response.headers:
            self.wfile.write(f"{name}: {value}\r\n".encode("latin-1"))
        no_payload = 100 <= response.status < 200 or response.status in (204, 304)
        if response.chunked:
            self.wfile.write(b"Transfer-Encoding: chunked\r\n")
            self.wfile.write(f"Content-Length: {len(response.body)}\r\n".encode("ascii"))
        elif not response.unframed and (not no_payload or response.length_without_payload):
            self.wfile.write(f"Content-Length: {len(response.body)}\r\n".encode("ascii"))
        self.wfile.write(b"Connection: close\r\n\r\n")
        if response.chunked:
            self.wfile.write(f"{len(response.body):X}\r\n".encode("ascii"))
            self.wfile.write(response.body + b"\r\n0\r\n\r\n")
        elif not no_payload:
            self.wfile.write(response.body)


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, scenario: str):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.scenario = scenario
        self.requests: list[tuple[str, str]] = []
        self.counts: dict[str, int] = {}


class HttpOrigin:
    """A running case origin; shuts down without leaving a listener or thread."""

    def __init__(self, scenario: str):
        self._server = _Server(scenario)
        self._thread = threading.Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.05),
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}{BASE_PATH}"

    @property
    def requests(self) -> list[tuple[str, str]]:
        return list(self._server.requests)

    def __enter__(self) -> "HttpOrigin":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
