"""Standard-library regression checks for deterministic Markdown analyzer and gate."""
import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "check.py"
SPEC = importlib.util.spec_from_file_location("minimal_test_gate", FILE)
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

HEADER = "| ID | 仕様ファイル | 仕様アンカー | 出典SHA256 | 実装ファイル | 実装アンカー | 期待値 | 承認 | 未決ID |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
QUESTIONS = "| ID | 対象 | 未決事項 | 状態 | 決定先 |\n| --- | --- | --- | --- | --- |\n| Q-001 | API | 境界 | OPEN | - |\n"


class GateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for directory in ("docs", "src", "test-gate-mvp"):
            (self.root / directory).mkdir()
        self.spec = self.root / "docs/spec.md"
        self.code = self.root / "src/app.py"
        self.spec.write_text("HTTP 400を返す\n", encoding="utf-8")
        self.code.write_text("return 400\n", encoding="utf-8")
        self.rules = self.root / "test-gate-mvp/TEST_RULES.md"
        (self.root / "test-gate-mvp/OPEN_QUESTIONS.md").write_text("# Questions\n\n" + QUESTIONS, encoding="utf-8")
        self.write_rule()

    def write_rule(self, status="approved", sha=None, question="-", code_anchor="return 400"):
        sha = gate.digest(self.spec.read_bytes()) if sha is None else sha
        self.rules.write_text("# Rules\n\n" + HEADER
            + f"| R-001 | docs/spec.md | HTTP 400 | {sha} | src/app.py | {code_anchor} | 400を返す | {status} | {question} |\n",
            encoding="utf-8")

    def execute(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = gate.main(["--root", str(self.root), *args])
        return result, out.getvalue(), err.getvalue()

    def test_approved_current_rule_allows(self):
        status, output, _ = self.execute("--strict")
        self.assertEqual(status, 0)
        self.assertIn("| R-001 | ANCHOR_FOUND | ANCHOR_FOUND | ALLOW |", output)

    def test_pending_holds(self):
        self.write_rule(status="pending")
        status, output, _ = self.execute("--strict")
        self.assertEqual(status, 1)
        self.assertIn("| HOLD |", output)

    def test_source_changes_even_if_anchor_remains(self):
        self.spec.write_text("HTTP 400を返す\n追加の条件\n", encoding="utf-8")
        status, output, _ = self.execute("--strict")
        self.assertEqual(status, 1)
        self.assertIn("仕様ファイルが変更", output)

    def test_open_question_holds(self):
        self.write_rule(question="Q-001")
        status, output, _ = self.execute("--strict")
        self.assertEqual(status, 1)
        self.assertIn("未決事項が未解決", output)

    def test_missing_question_holds(self):
        self.write_rule(question="Q-999")
        status, output, _ = self.execute("--strict")
        self.assertEqual(status, 1)
        self.assertIn("参照先がない", output)

    def test_implementation_drift_does_not_reject_valid_oracle(self):
        self.write_rule(code_anchor="return 201")
        status, output, _ = self.execute("--strict")
        self.assertEqual(status, 1)
        self.assertIn("| DRIFT | ALLOW |", output)

    def test_same_input_same_output(self):
        self.assertEqual(self.execute(), self.execute())

    def test_stamp_pending_only(self):
        self.write_rule(status="pending", sha="-")
        status, _, _ = self.execute("--stamp", "R-001")
        self.assertEqual(status, 0)
        self.assertIn(gate.digest(self.spec.read_bytes()), self.rules.read_text(encoding="utf-8"))
        self.assertIn("pending", self.rules.read_text(encoding="utf-8"))
        self.write_rule(status="approved")
        status, _, err = self.execute("--stamp", "R-001")
        self.assertEqual(status, 2)
        self.assertIn("pending", err)

    def test_duplicate_rules_are_input_error(self):
        text = self.rules.read_text(encoding="utf-8")
        self.rules.write_text(text + text.splitlines()[-1] + "\n", encoding="utf-8")
        status, _, error = self.execute()
        self.assertEqual(status, 2)
        self.assertIn("重複", error)

    def test_empty_table_is_not_strict_success(self):
        self.rules.write_text("# Rules\n\n" + HEADER, encoding="utf-8")
        self.assertEqual(self.execute("--strict")[0], 1)


if __name__ == "__main__":
    unittest.main()
