import hashlib
import base64
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


class FakeDistribution:
    def __init__(self, root: Path, direct_url: dict | None):
        self.root = root
        self.metadata = {"Name": "wsi-dicom-bench"}
        self.version = "0.1.0"
        self.requires = ["pydicom==3.0.2"]
        self.files = [Path("wsi_dicom_bench/__init__.py"), Path("wsi_dicom_bench-0.1.0.dist-info/RECORD")]
        self.direct_url = direct_url

    def read_text(self, name: str) -> str | None:
        if name != "direct_url.json" or self.direct_url is None:
            return None
        return json.dumps(self.direct_url)

    def locate_file(self, path: Path) -> Path:
        return self.root / path


class DistributionPayloadTests(unittest.TestCase):
    def test_retains_exact_verified_wheel_with_portable_metadata(self):
        from wsi_dicom_bench import distribution_payload

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wheel = root / "wsi_dicom_bench-0.1.0-py3-none-any.whl"
            package = root / "wsi_dicom_bench/__init__.py"
            package.parent.mkdir()
            package.write_bytes(b"runtime")
            encoded = base64.urlsafe_b64encode(hashlib.sha256(package.read_bytes()).digest()).decode().rstrip("=")
            record = root / "wsi_dicom_bench-0.1.0.dist-info/RECORD"
            record.parent.mkdir()
            record.write_text(f"wsi_dicom_bench/__init__.py,sha256={encoded},7\nwsi_dicom_bench-0.1.0.dist-info/RECORD,,\n", encoding="utf-8")
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.write(package, "wsi_dicom_bench/__init__.py")
                archive.write(record, "wsi_dicom_bench-0.1.0.dist-info/RECORD")
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            installed = FakeDistribution(
                root,
                {
                    "url": wheel.as_uri(),
                    "archive_info": {"hashes": {"sha256": digest}},
                },
            )
            output = root / "payload"

            with mock.patch.object(
                distribution_payload, "distribution", return_value=installed
            ):
                metadata = distribution_payload.retain_installed_distribution(output)

            self.assertEqual((output / wheel.name).read_bytes(), wheel.read_bytes())
            self.assertEqual(metadata["wheel"], {"path": wheel.name, "sha256": digest})
            self.assertNotIn(str(root), json.dumps(metadata))
            self.assertEqual(metadata["requires"], ["pydicom==3.0.2"])

    def test_missing_nonlocal_and_tampered_wheels_fail_without_output(self):
        from wsi_dicom_bench import distribution_payload

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = root / "wsi_dicom_bench-0.1.0.dist-info/RECORD"
            record.parent.mkdir()
            record.write_text("record\n", encoding="utf-8")
            wheel = root / "package.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("wsi_dicom_bench-0.1.0.dist-info/RECORD", "record\n")
            package = root / "wsi_dicom_bench/__init__.py"
            package.parent.mkdir()
            package.write_text("runtime")
            cases = {
                "missing metadata": None,
                "nonlocal wheel": {
                    "url": "https://example.invalid/package.whl",
                    "archive_info": {"hashes": {"sha256": "0" * 64}},
                },
                "tampered wheel": {
                    "url": wheel.as_uri(),
                    "archive_info": {"hashes": {"sha256": "0" * 64}},
                },
            }
            for name, direct_url in cases.items():
                with self.subTest(name=name):
                    output = root / name.replace(" ", "-")
                    installed = FakeDistribution(root, direct_url)
                    with mock.patch.object(
                        distribution_payload, "distribution", return_value=installed
                    ), self.assertRaises(distribution_payload.DistributionPayloadError):
                        distribution_payload.retain_installed_distribution(output)
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
