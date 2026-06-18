from __future__ import annotations

import unittest

from autodev.real_env_check import EnvironmentCheck, decode_output, redact


class RealEnvironmentCheckTests(unittest.TestCase):
    def test_redacts_token_lines(self) -> None:
        text = "github.com\n  - Token: gho_secret\n  - Token scopes: repo\n"

        redacted = redact(text)

        self.assertIn("Token: [redacted]", redacted)
        self.assertNotIn("gho_secret", redacted)

    def test_environment_check_payload(self) -> None:
        check = EnvironmentCheck("codex", "failed", "Access denied")

        self.assertEqual(
            check.to_dict(),
            {
                "name": "codex",
                "status": "failed",
                "summary": "Access denied",
                "required": True,
            },
        )

    def test_decode_output_replaces_invalid_bytes(self) -> None:
        self.assertIn("�", decode_output(b"\xff"))


if __name__ == "__main__":
    unittest.main()
