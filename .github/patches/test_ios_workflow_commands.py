import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "generator-ios.yml"


class IOSWorkflowTests(unittest.TestCase):
    def test_unsigned_ipa_workflow_basics(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("flutter build ipa --release --no-codesign", text)
        self.assertIn("iosBundleId", text)
        self.assertIn("PRODUCT_BUNDLE_IDENTIFIER", text)
        self.assertIn("arm64-ios", text)
        self.assertIn("aarch64-apple-ios", text)
        self.assertIn("${{ env.filename }}.ipa", text)
        self.assertIn("save_custom_client", text)
        self.assertNotIn("codesign --sign", text)
        self.assertIn("allowCustom.py", text)


if __name__ == "__main__":
    unittest.main()
