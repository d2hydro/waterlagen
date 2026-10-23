"""Exercise the CLI against real, isolated Git indexes without creating commits."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_dev_workdocs.py"


class WorkdocsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="dev-workdocs-")
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name) / "repository with spaces"
        self.repository.mkdir()
        self.git("init", "--quiet")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repository), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.stdout

    def write(self, name: str, tracked: bool = True) -> Path:
        path = self.repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("example\n", encoding="utf-8")
        if tracked:
            self.git("add", "--", name)
        return path

    def check(
        self, repository: Path | None = None, summary: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                "--repo",
                str(repository or self.repository),
                *(["--summary", str(summary)] if summary is not None else []),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_empty_index_passes(self) -> None:
        self.assertEqual(self.check().returncode, 0)

    def test_untracked_and_ignored_workdocs_do_not_block(self) -> None:
        ignore = self.repository / ".gitignore"
        ignore.write_text("reviewcases/ignored/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.write("reviewcases/local.md", tracked=False)
        self.write("reviewcases/ignored/output.png", tracked=False)
        self.write("docs/bijdragen/implementatieplannen/local.md", tracked=False)
        self.assertEqual(self.check().returncode, 0)

    def test_all_tracked_files_in_both_directories_block(self) -> None:
        paths = [
            "docs/bijdragen/implementatieplannen/index.md",
            "docs/bijdragen/implementatieplannen/nested/plan with spaces.md",
            "reviewcases/review-abc.md",
            "reviewcases/nested/reproduce.py",
            "reviewcases/.gitkeep",
            "reviewcases/output/data.gpkg",
        ]
        for path in paths:
            self.write(path)
        # Nothing in the unstaged diff: the check must inspect the entire index.
        self.assertEqual(self.git("diff", "--name-only"), "")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Merge geblokkeerd: 6", result.stdout)
        for path in paths:
            self.assertIn(path, result.stdout)
        self.assertIn("tijdelijke implementatieplannen", result.stdout)
        self.assertIn("tijdelijke reviewrapporten", result.stdout)

    def test_each_directory_blocks_independently(self) -> None:
        for directory in ("reviewcases", "docs/bijdragen/implementatieplannen"):
            with self.subTest(directory=directory):
                path = f"{directory}/work.md"
                self.write(path)
                self.assertEqual(self.check().returncode, 1)
                self.git("rm", "--cached", "--", path)

    def test_other_locations_and_similar_names_are_allowed(self) -> None:
        for path in (
            "src/module.py",
            "docs/bijdragen/conventions.md",
            "tests/test_example.py",
            "reviewcases-archive/example.md",
            "docs/bijdragen/implementatieplannen-extra/plan.md",
            "examples/reviewcases/example.md",
        ):
            self.write(path)
        self.assertEqual(self.check().returncode, 0)

    def test_unstaged_deletion_still_blocks(self) -> None:
        self.write("reviewcases/missing.md").unlink()
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("reviewcases/missing.md", result.stdout)

    def test_removing_from_index_passes_but_local_file_remains(self) -> None:
        path = self.write("reviewcases/local.md")
        self.assertEqual(self.check().returncode, 1)
        self.git("rm", "--cached", "--", "reviewcases/local.md")
        self.assertTrue(path.exists())
        self.assertEqual(self.check().returncode, 0)

    def test_tracked_ignored_file_still_blocks(self) -> None:
        (self.repository / ".gitignore").write_text("reviewcases/\n", encoding="utf-8")
        self.write("reviewcases/forced.md", tracked=False)
        self.git("add", "-f", "--", "reviewcases/forced.md")
        self.assertEqual(self.check().returncode, 1)

    def test_subdirectory_argument_still_checks_whole_repository(self) -> None:
        self.write("reviewcases/block.md")
        subdirectory = self.repository / "src"
        subdirectory.mkdir()
        result = self.check(subdirectory)
        self.assertEqual(result.returncode, 1)
        self.assertIn("reviewcases/block.md", result.stdout)

    def test_tracked_entry_at_directory_root_also_blocks(self) -> None:
        # A tracked symlink/submodule at this path must not bypass the policy.
        self.write("reviewcases")
        self.assertEqual(self.check().returncode, 1)

    def test_non_repository_is_an_error_not_a_success(self) -> None:
        result = self.check(Path(self.temporary.name))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Controle niet uitgevoerd", result.stderr)

    def test_success_summary(self) -> None:
        summary = Path(self.temporary.name) / "summary.md"
        result = self.check(summary=summary)
        self.assertEqual(result.returncode, 0)
        self.assertIn("**Geslaagd**", summary.read_text(encoding="utf-8"))

    def test_failure_summary_lists_files_and_preserves_existing_content(self) -> None:
        self.write("reviewcases/work & notes.md")
        summary = Path(self.temporary.name) / "summary.md"
        summary.write_text("Eerdere stap\n", encoding="utf-8")
        result = self.check(summary=summary)
        self.assertEqual(result.returncode, 1)
        content = summary.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("Eerdere stap\n"))
        self.assertIn("**Merge geblokkeerd**", content)
        self.assertIn("reviewcases/work &amp; notes.md", content)
        self.assertIn("tijdelijke reviewrapporten", content)
        self.assertIn("stage die verwijdering", content)

    def test_inspection_error_is_reported_in_summary(self) -> None:
        summary = Path(self.temporary.name) / "summary.md"
        result = self.check(Path(self.temporary.name), summary=summary)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Controle niet uitgevoerd", summary.read_text(encoding="utf-8"))

    def test_unwritable_summary_fails_explicitly(self) -> None:
        result = self.check(summary=Path(self.temporary.name))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Samenvatting kon niet worden opgeslagen", result.stderr)

    def test_script_is_standalone_in_an_isolated_copy(self) -> None:
        standalone = Path(self.temporary.name) / "standalone"
        standalone.mkdir()
        copied_script = standalone / SCRIPT.name
        copied_script.write_bytes(SCRIPT.read_bytes())
        self.write("reviewcases/block.md")
        result = subprocess.run(
            [sys.executable, "-I", str(copied_script), "--repo", str(self.repository)],
            cwd=standalone,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("reviewcases/block.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
