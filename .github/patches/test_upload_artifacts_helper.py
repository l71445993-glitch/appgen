import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from upload_artifacts_to_rdgen import upload_direct, upload_via_object_storage  # noqa: E402


class UploadHelperTests(unittest.TestCase):
    def test_script_exists(self):
        self.assertTrue((SCRIPTS / "upload_artifacts_to_rdgen.py").is_file())

    @mock.patch("upload_artifacts_to_rdgen._curl")
    @mock.patch("upload_artifacts_to_rdgen._req")
    def test_object_storage_path(self, req, curl):
        req.side_effect = [
            {
                "mode": "object_storage",
                "provider": "cos",
                "uploads": [
                    {
                        "filename": "a.exe",
                        "object_key": "rdgen/u/a.exe",
                        "put_url": "https://cos.example/put",
                        "headers": {"Content-Type": "application/octet-stream"},
                    }
                ],
            },
            {"status": "ok"},
        ]
        with mock.patch("upload_artifacts_to_rdgen._sha256_file", return_value="abc"):
            with mock.patch("os.path.getsize", return_value=12):
                ok = upload_via_object_storage(
                    "https://app.example",
                    "tok",
                    "uuid-1",
                    ["/tmp/a.exe"],
                    defer=True,
                )
        self.assertTrue(ok)
        self.assertEqual(req.call_count, 2)
        self.assertEqual(curl.call_count, 1)

    @mock.patch("upload_artifacts_to_rdgen._curl")
    def test_direct_uses_long_timeout(self, curl):
        with mock.patch("os.path.getsize", return_value=12):
            upload_direct("https://app.example", "tok", "uuid-1", ["/tmp/a.exe"], False)
        args = curl.call_args[0][0]
        self.assertIn("--http1.1", args)
        self.assertIn("1800", args)
        self.assertIn("https://app.example/save_custom_client", args)


if __name__ == "__main__":
    unittest.main()
