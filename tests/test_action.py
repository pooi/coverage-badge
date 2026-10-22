import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text())
PREPARE = next(step for step in ACTION["runs"]["steps"] if step.get("id") == "site")
REPORT = '<report><counter type="INSTRUCTION" missed="25" covered="75"/></report>'


class SitePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.runner_temp = self.root / "runner temp"
        self.runner_temp.mkdir()
        # These names must remain literal rather than becoming shell commands.
        self.reports = self.workspace / "reports $(touch INJECTED); ' quoted"
        self.reports.mkdir()
        self.xml = self.reports / "report.xml"
        self.xml.write_text(REPORT)
        self.html = self.reports / "html report"
        self.html.mkdir()
        (self.html / "index.html").write_text("<html>coverage report</html>")
        (self.html / "assets").mkdir()
        (self.html / "assets" / "report.css").write_text("body {}")
        self.output = self.root / "output"

    def prepare(self, xml=None, html=None):
        environment = os.environ.copy()
        environment.update(
            PATH=str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", ""),
            GITHUB_WORKSPACE=str(self.workspace),
            GITHUB_ACTION_PATH=str(ROOT),
            RUNNER_TEMP=str(self.runner_temp),
            GITHUB_OUTPUT=str(self.output),
            XML_TEST_REPORT_PATH=str(self.xml if xml is None else xml),
            HTML_TEST_REPORT_PATH=str(self.html if html is None else html),
        )
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", PREPARE["run"]],
            cwd=self.root,
            env=environment,
            text=True,
            capture_output=True,
        )

    def test_absolute_and_relative_paths(self):
        for absolute in (True, False):
            with self.subTest(absolute=absolute):
                xml = self.xml if absolute else self.xml.relative_to(self.workspace)
                # A trailing slash must not introduce another report directory level.
                html = str(self.html if absolute else self.html.relative_to(self.workspace)) + "/"
                self.output.write_text("")
                result = self.prepare(xml, html)
                self.assertEqual(result.returncode, 0, result.stderr)
                site = Path(self.output.read_text().strip().removeprefix("path="))
                self.assertEqual(site.parent, self.runner_temp)
                self.assertEqual({p.name for p in site.iterdir()}, {"coverage.svg", "coverage"})
                self.assertIn("75.00%", (site / "coverage.svg").read_text())
                self.assertEqual((site / "coverage" / "index.html").read_text(), "<html>coverage report</html>")
                self.assertTrue((site / "coverage" / "assets" / "report.css").is_file())
                self.assertFalse((self.root / "INJECTED").exists())
                self.assertFalse((self.workspace / "coverage.svg").exists())

    def test_missing_reports_fail_without_output(self):
        for xml, html in (
            ("missing.xml", self.html), (self.xml, "missing-html"),
            ("", self.html), (self.xml, ""),
            (self.html, self.html), (self.xml, self.xml),
        ):
            with self.subTest(xml=xml, html=html):
                result = self.prepare(xml, html)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())

    def test_invalid_xml_fails_without_output(self):
        self.xml.write_text("<report>")
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_missing_instruction_counter_fails_without_output(self):
        self.xml.write_text("<report/>")
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not produce a coverage badge", result.stderr)
        self.assertFalse(self.output.exists())


class ActionWiringTests(unittest.TestCase):
    def test_example_has_required_pages_configuration(self):
        readme = (ROOT / "README.md").read_text()
        workflow = yaml.load(readme.split("```yaml\n", 1)[1].split("```", 1)[0], Loader=yaml.BaseLoader)
        job = workflow["jobs"]["coverage"]
        self.assertEqual(set(workflow["on"]), {"push", "workflow_dispatch"})
        self.assertEqual(workflow["on"]["push"]["branches"], ["main"])
        self.assertEqual(job["permissions"], {"contents": "read", "pages": "write", "id-token": "write"})
        self.assertEqual(job["environment"]["name"], "github-pages")
        self.assertEqual(job["environment"]["url"], "${{ steps.coverage.outputs.page-url }}")
        self.assertIn("concurrency", workflow)
        coverage = next(step for step in job["steps"] if step.get("id") == "coverage")
        self.assertNotIn("token", coverage["with"])

    def test_token_is_limited_to_deployment_steps(self):
        self.assertFalse(ACTION["inputs"]["token"]["required"])
        self.assertEqual(ACTION["inputs"]["token"]["default"], "${{ github.token }}")
        steps = ACTION["runs"]["steps"]
        deployment = next(step for step in steps if step.get("id") == "deployment")
        self.assertEqual(deployment["with"]["token"], "${{ inputs.token }}")
        branch = next(step for step in steps if step["name"] == "Publish coverage branch")
        self.assertEqual(branch["env"]["COVERAGE_TOKEN"], "${{ inputs.token }}")
        for step in steps:
            if step not in (deployment, branch):
                self.assertNotIn("inputs.token", str(step))
        self.assertEqual(ACTION["inputs"]["github-page-ref"]["default"], "gh-pages")
        self.assertNotIn("github-page-path", ACTION["inputs"])
        self.assertFalse((ROOT / "clone-url.py").exists())

    def test_upload_and_deploy_are_ordered_and_gated_by_success(self):
        steps = ACTION["runs"]["steps"]
        upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload-pages-artifact@"))
        deployment = next(step for step in steps if step.get("id") == "deployment")
        self.assertEqual(upload["uses"], "actions/upload-pages-artifact@v4")
        self.assertEqual(deployment["uses"], "actions/deploy-pages@v4")
        self.assertLess(steps.index(PREPARE), steps.index(upload))
        self.assertLess(steps.index(upload), steps.index(deployment))
        self.assertEqual(upload["with"]["path"], "${{ steps.site.outputs.path }}")
        self.assertEqual(ACTION["outputs"]["page-url"]["value"], "${{ steps.deployment.outputs.page_url }}")
        self.assertEqual(upload["if"], "steps.mode.outputs.value == 'pages'")
        self.assertEqual(deployment["if"], upload["if"])
        branch = next(step for step in steps if step["name"] == "Publish coverage branch")
        self.assertEqual(branch["if"], "steps.mode.outputs.value == 'branch'")
        for step in steps:
            self.assertNotIn("continue-on-error", step)
            self.assertNotIn("${{", step.get("run", ""))

    def test_deployment_selection(self):
        mode = next(step for step in ACTION["runs"]["steps"] if step.get("id") == "mode")
        cases = (
            ("auto", "https://github.com", "pages"),
            ("auto", "https://github.example.test", "branch"),
            ("branch", "https://github.com", "branch"),
            ("pages", "https://github.example.test", None),
            ("invalid", "https://github.com", None),
        )
        for requested, server, expected in cases:
            with self.subTest(requested=requested, server=server), tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "output"
                environment = dict(os.environ, DEPLOYMENT_MODE=requested,
                                   GITHUB_SERVER_URL=server, GITHUB_OUTPUT=str(output))
                result = subprocess.run(["bash", "-c", mode["run"]], env=environment, capture_output=True)
                if expected:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output.read_text().strip(), f"value={expected}")
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
