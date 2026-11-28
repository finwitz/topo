"""The readme check: a pull request that changes what Topo does updates README.md, or says why not."""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location(
    "readme_check", os.path.join(HERE, "..", ".github", "scripts", "readme_check.py"))
readme_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readme_check)
verdict = readme_check.verdict


class ReadmeCheck(unittest.TestCase):
    def test_changes_that_do_not_touch_what_topo_does_pass(self):
        self.assertTrue(verdict({"test/test_tools.py", "docs/features-view.md", "maps/saleor/flows.json"}, "")[0])
        self.assertTrue(verdict(set(), "")[0])

    def test_a_watched_change_needs_the_readme(self):
        for f in ("pipeline/routes.py", "viewer/topo.template.html", "hooks/pre-commit",
                  ".claude/skills/map/SKILL.md", ".claude-plugin/plugin.json", "MAPPING_PLAYBOOK.md"):
            ok, message = verdict({f, "test/test_tools.py"}, "Fixes a bug.")
            self.assertFalse(ok, f)
            self.assertIn(f, message)
        self.assertTrue(verdict({"pipeline/routes.py", "README.md"}, "")[0])

    def test_a_reason_waives_it(self):
        for body in ("Fixes it.\n\nREADME: no change, a refactor with the same output",
                     "README: no change needed - tests only",
                     "- **README: no change** (internal rename)",
                     "readme: No change: the docstring only"):
            ok, message = verdict({"pipeline/build.py"}, body)
            self.assertTrue(ok, body)
            self.assertIn("because", message)

    def test_a_waiver_without_a_reason_or_mid_sentence_does_not_count(self):
        for body in ("README: no change", "README: no change needed", "README: no change.",
                     "Write README: no change and why, as the template asks.", None):
            self.assertFalse(verdict({"pipeline/build.py"}, body)[0], body)

    def test_the_untouched_pull_request_template_does_not_count(self):
        with open(os.path.join(HERE, "..", ".github", "pull_request_template.md")) as f:
            self.assertFalse(verdict({"pipeline/build.py"}, f.read())[0])


if __name__ == "__main__":
    unittest.main()
