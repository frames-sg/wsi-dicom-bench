import io
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wsi_dicom_bench.workbench.encapsulated_frames import (
    FrameAssemblyError,
    frame_spans,
    read_frame,
    read_item_stream,
)
from wsi_dicom_bench.workbench.pixel_decode import (
    DecodePolicy,
    FrameExpectation,
    inspect_pnm_output,
    run_pixel_decode_checks,
)


JPEG_BASELINE = "1.2.840.10008.1.2.4.50"
HTJ2K_LOSSLESS = "1.2.840.10008.1.2.4.201"


def item(payload: bytes) -> bytes:
    return b"\xfe\xff\x00\xe0" + struct.pack("<I", len(payload)) + payload


def item_stream(fragments: list[bytes], basic_offsets: list[int] | None = None) -> bytes:
    basic_offsets = basic_offsets or []
    table = struct.pack(f"<{len(basic_offsets)}I", *basic_offsets)
    return item(table) + b"".join(item(f) for f in fragments) + b"\xfe\xff\xdd\xe0\0\0\0\0"


def spans_for(stream_bytes: bytes, frame_count: int, extended=None, lengths=None, max_bytes=1 << 20):
    stream = io.BytesIO(stream_bytes)
    basic, fragments = read_item_stream(stream, 0)
    return stream, fragments, frame_spans(fragments, frame_count, basic, extended, lengths, max_bytes)


def write_dicom(path: Path, transfer_syntax: str, frames: list[bytes], **attributes) -> None:
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.encaps import encapsulate

    meta = FileMetaDataset()
    meta.TransferSyntaxUID = transfer_syntax
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.77.1.6"
    meta.MediaStorageSOPInstanceUID = "1.2.3.4"
    dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = meta.MediaStorageSOPClassUID
    dataset.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    dataset.Rows = attributes.pop("Rows", 2)
    dataset.Columns = attributes.pop("Columns", 3)
    dataset.SamplesPerPixel = attributes.pop("SamplesPerPixel", 3)
    dataset.BitsAllocated = attributes.pop("BitsAllocated", 8)
    dataset.NumberOfFrames = attributes.pop("NumberOfFrames", len(frames))
    for keyword, value in attributes.items():
        setattr(dataset, keyword, value)
    if transfer_syntax == "1.2.840.10008.1.2.1":
        dataset.PixelData = b"".join(frames)
    else:
        dataset.PixelData = encapsulate(frames)
        dataset["PixelData"].VR = "OB"
        dataset["PixelData"].is_undefined_length = True
    dataset.save_as(path, enforce_file_format=True)


def fake_decoder(directory: Path, name: str, body: str) -> Path:
    """A decoder that reads djpeg (-outfile OUT IN) or opj/grk (-i IN -o OUT) arguments."""
    script = directory / name
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        "if '-outfile' in args:\n"
        "    output = args[args.index('-outfile') + 1]; source = args[-1]\n"
        "else:\n"
        "    source = args[args.index('-i') + 1]; output = args[args.index('-o') + 1]\n"
        "data = open(source, 'rb').read()\n"
        + body
    )
    script.chmod(0o700)
    return script


WRITE_RGB_2X3 = "open(output, 'wb').write(b'P6\\n3 2\\n255\\n' + bytes(18))\n"


class EncapsulatedFrameTests(unittest.TestCase):
    def test_basic_offset_table_maps_a_frame_split_across_fragments(self):
        fragments = [b"AA", b"BBBB", b"CC"]
        stream, located, spans = spans_for(item_stream(fragments, [0, 10]), 2)
        self.assertEqual([read_frame(stream, located, span) for span in spans], [b"AA", b"BBBBCC"])

    def test_single_frame_and_one_fragment_per_frame_need_no_offset_table(self):
        stream, located, spans = spans_for(item_stream([b"AB", b"CD"]), 1)
        self.assertEqual(read_frame(stream, located, spans[0]), b"ABCD")
        stream, located, spans = spans_for(item_stream([b"AB", b"CD"]), 2)
        self.assertEqual([read_frame(stream, located, span) for span in spans], [b"AB", b"CD"])

    def test_extended_lengths_trim_padding_but_never_exceed_the_payload(self):
        stream, located, spans = spans_for(item_stream([b"ABC\0", b"DE"]), 2, [0, 12], [3, 2])
        self.assertEqual([read_frame(stream, located, span) for span in spans], [b"ABC", b"DE"])
        with self.assertRaisesRegex(FrameAssemblyError, "includes the 8-byte Item header"):
            spans_for(item_stream([b"ABCD", b"EF"]), 2, [0, 12], [12, 2])

    def test_inconsistent_frame_tables_are_rejected(self):
        cases = {
            "not strictly increasing from zero": (item_stream([b"AA", b"BB"], [4, 10]), 2, None, None),
            "does not identify a fragment boundary": (item_stream([b"AA", b"BB"], [0, 9]), 2, None, None),
            "has 1 entries for 2 frames": (item_stream([b"AA", b"BB"], [0]), 2, None, None),
            "without an offset table": (item_stream([b"AA", b"BB", b"CC"]), 2, None, None),
            "requires an Extended Offset Table": (item_stream([b"AA"]), 1, None, [2]),
            "has no fragments": (item_stream([]), 1, None, None),
        }
        for message, (data, frames, extended, lengths) in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(FrameAssemblyError, message):
                spans_for(data, frames, extended, lengths)

    def test_frame_size_limit_is_enforced_before_reading(self):
        with self.assertRaisesRegex(FrameAssemblyError, "exceeds 3 byte validation limit"):
            spans_for(item_stream([b"ABCD"]), 1, max_bytes=3)

    def test_truncated_item_streams_are_rejected(self):
        complete = item_stream([b"ABCD"])
        for data in (complete[:-8], complete[:-12]):
            with self.subTest(length=len(data)), self.assertRaises(FrameAssemblyError):
                read_item_stream(io.BytesIO(data), 0)


class PnmInspectionTests(unittest.TestCase):
    def inspect(self, data: bytes, expected=FrameExpectation(3, 2, 3, 8)):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "frame.ppm"
            output.write_bytes(data)
            inspect_pnm_output(output, expected, 1 << 20)

    def test_matching_rgb_and_monochrome_outputs_pass(self):
        self.inspect(b"P6\n# comment\n3 2\n255\n" + bytes(18))
        self.inspect(b"P5 3 2 65535\n" + bytes(12), FrameExpectation(3, 2, 1, 16))

    def test_mismatched_outputs_fail_with_the_reason(self):
        cases = {
            "dimensions 2x2 do not match DICOM 3x2": b"P6\n2 2\n255\n" + bytes(12),
            "has 1 component": b"P5\n3 2\n255\n" + bytes(6),
            "does not match 8-bit": b"P6\n3 2\n65535\n" + bytes(36),
            "payload has 17 bytes, expected 18": b"P6\n3 2\n255\n" + bytes(17),
            "unsupported PNM magic": b"P3\n3 2\n255\n",
        }
        for message, data in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.inspect(data)


class DecodeStageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        path_patch = mock.patch.dict(os.environ, {"PATH": str(self.bin)})
        path_patch.start()
        self.addCleanup(path_patch.stop)
        self.addCleanup(self.temporary.cleanup)

    def run_stage(self, path: Path, **policy) -> dict:
        defaults = {"max_frames": 1, "strict": True, "timeout_secs": 30}
        return run_pixel_decode_checks([str(path)], DecodePolicy(**{**defaults, **policy}))

    def test_sampled_frames_reach_the_decoder_and_matching_output_passes(self):
        fake_decoder(self.bin, "djpeg", "assert data == b'FRAME0'\n" + WRITE_RGB_2X3)
        slide = self.root / "slide.dcm"
        write_dicom(slide, JPEG_BASELINE, [b"FRAME0", b"FRAME1"])

        result = self.run_stage(slide)

        self.assertEqual([check["status"] for check in result["checks"]], ["passed"])
        check = result["checks"][0]
        self.assertEqual(check["name"], "pixel-djpeg")
        self.assertEqual(check["command"][0], "djpeg")
        self.assertEqual(check["execution"]["return_code"], 0)
        self.assertEqual(result["decoders"][0]["family"], "jpeg")
        self.assertEqual(len(result["decoders"][0]["sha256"]), 64)

    def test_a_codestream_the_decoder_rejects_is_a_failed_check_not_an_execution_error(self):
        fake_decoder(self.bin, "djpeg", "sys.exit(1)\n")
        slide = self.root / "truncated.dcm"
        write_dicom(slide, JPEG_BASELINE, [b"\xff\xd8\xff"])

        check = self.run_stage(slide)["checks"][0]

        self.assertEqual(check["status"], "failed")
        self.assertEqual(check["message"], "djpeg failed")
        self.assertIsNone(check["execution"]["failure"])

    def test_decoded_geometry_must_match_the_dicom_frame(self):
        fake_decoder(self.bin, "djpeg", WRITE_RGB_2X3)
        slide = self.root / "wider.dcm"
        write_dicom(slide, JPEG_BASELINE, [b"FRAME"], Columns=4)

        check = self.run_stage(slide)["checks"][0]

        self.assertEqual(check["status"], "failed")
        self.assertIn("dimensions 3x2 do not match DICOM 4x2", check["message"])

    def test_missing_decoder_fails_strict_runs_and_is_skipped_otherwise(self):
        slide = self.root / "slide.dcm"
        write_dicom(slide, JPEG_BASELINE, [b"FRAME"])
        for strict, status in ((True, "failed"), (False, "skipped")):
            with self.subTest(strict=strict):
                check = self.run_stage(slide, strict=strict)["checks"][0]
                self.assertEqual(check["status"], status)
                self.assertEqual(check["execution"]["failure"], "unavailable")

    def test_native_pixels_need_no_decoder(self):
        slide = self.root / "native.dcm"
        write_dicom(slide, "1.2.840.10008.1.2.1", [bytes(18)])

        check = self.run_stage(slide)["checks"][0]

        self.assertEqual((check["name"], check["status"]), ("pixel-decode", "skipped"))

    def test_pixel_data_that_cannot_be_mapped_to_frames_fails_pixel_decode(self):
        fake_decoder(self.bin, "djpeg", WRITE_RGB_2X3)
        slide = self.root / "extra-frame.dcm"
        write_dicom(slide, JPEG_BASELINE, [b"A", b"B"], NumberOfFrames=3)

        check = self.run_stage(slide)["checks"][0]

        self.assertEqual((check["name"], check["status"]), ("pixel-decode", "failed"))
        self.assertEqual(check["message"], "Pixel Data offset table has 2 entries for 3 frames")

    def test_a_data_set_pydicom_cannot_read_fails_with_the_reason(self):
        slide = self.root / "undelimited.dcm"
        write_dicom(slide, JPEG_BASELINE, [b"FRAME0"])
        data = slide.read_bytes()
        delimiter = b"\xfe\xff\xdd\xe0\0\0\0\0"
        self.assertTrue(data.endswith(delimiter))
        slide.write_bytes(data[: -len(delimiter)])

        check = self.run_stage(slide)["checks"][0]

        self.assertEqual((check["name"], check["status"]), ("pixel-decode", "failed"))
        self.assertIn("cannot parse DICOM metadata: End of file reached before delimiter", check["message"])

    def test_htj2k_uses_an_absolute_template_and_rejects_relative_commands(self):
        slide = self.root / "htj2k.dcm"
        write_dicom(slide, HTJ2K_LOSSLESS, [b"CODESTREAM"])
        decoder = fake_decoder(self.bin, "custom-htj2k", WRITE_RGB_2X3)

        passed = self.run_stage(slide, htj2k_decoder=f"{decoder} -i {{input}} -o {{output}}")["checks"][0]
        relative = self.run_stage(slide, htj2k_decoder="custom-htj2k -i {input}")["checks"][0]
        unconfigured = self.run_stage(slide)["checks"][0]

        self.assertEqual((passed["name"], passed["status"]), ("pixel-htj2k", "passed"))
        self.assertEqual(relative["execution"]["failure"], "configuration")
        self.assertEqual(unconfigured["execution"]["failure"], "unavailable")
        self.assertEqual(unconfigured["status"], "failed")

    def test_htj2k_falls_back_to_grk_decompress_on_path(self):
        fake_decoder(self.bin, "grk_decompress", WRITE_RGB_2X3)
        slide = self.root / "htj2k.dcm"
        write_dicom(slide, HTJ2K_LOSSLESS, [b"CODESTREAM"])

        check = self.run_stage(slide)["checks"][0]

        self.assertEqual((check["name"], check["status"]), ("pixel-htj2k", "passed"))
        self.assertEqual(check["command"][0], str(self.bin / "grk_decompress"))


if __name__ == "__main__":
    unittest.main()
