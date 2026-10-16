"""Offline tests for the pure git and dependency parsers.

Every fixture is captured real output, so these run with no network access and
no sandbox cost.
"""

from pathlib import Path

import pytest

from app.ingestion.dependency_scanner import (
    collect_dependencies,
    normalise_repository_url,
    parse_cargo_toml,
    parse_codeowners,
    parse_gitmodules,
)
from app.ingestion.git_history_parser import (
    collect_authors,
    collect_unique_files,
    detect_language,
    extract_pr_number,
    is_automation_author,
    is_test_path,
    module_path_for,
    parse_git_log,
)

FIXTURES = Path(__file__).parent / "fixtures" / "git"


def _read(name: str) -> str:
    return FIXTURES.joinpath(name).read_text(encoding="utf-8-sig")


@pytest.fixture(scope="module")
def click_commits():
    return parse_git_log(_read("click_log_depth40.txt"))


def test_parse_git_log_reads_every_record(click_commits):
    assert len(click_commits) == 40


def test_parse_git_log_handles_empty_input():
    assert parse_git_log("") == []
    assert parse_git_log("   \n  ") == []


def test_parse_git_log_extracts_core_metadata(click_commits):
    commit = click_commits[0]
    assert len(commit.sha) == 40
    assert commit.short_sha == commit.sha[:12]
    assert commit.author_name
    assert "@" in commit.author_email
    assert commit.authored_at.startswith("20")
    assert commit.subject


def test_parse_git_log_extracts_changed_files(click_commits):
    with_files = [c for c in click_commits if c.files]
    assert with_files
    for commit in with_files:
        assert all(path and not path.startswith(" ") for path in commit.files)


def test_merge_commits_have_no_file_list(click_commits):
    """git log --name-only suppresses the combined diff for merges."""
    merges = [c for c in click_commits if c.is_merge]
    assert merges
    assert all(not c.files for c in merges)


def test_collect_unique_files_is_ordered_and_deduplicated(click_commits):
    files = collect_unique_files(click_commits)
    assert len(files) == len(set(files))
    assert files


def test_collect_authors_deduplicates(click_commits):
    authors = collect_authors(click_commits)
    assert len(authors) == len(set(authors))


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Add Parameter.spec and deprecate human_readable_name (#3877)", 3877),
        ("Merge pull request #2459 from someone/branch", 2459),
        ("fix: one attribute dictionary per graph (#2459)", 2459),
        ("chore: bump deps", None),
        ("", None),
    ],
)
def test_extract_pr_number(subject, expected):
    assert extract_pr_number(subject) == expected


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("graph/src/graph/attribute_store.rs", "Rust"),
        ("tests/flow/test_effects_ddl.py", "Python"),
        ("src/index.ts", "TypeScript"),
        ("Cargo.toml", "TOML"),
        ("weird.unknownext", "Other"),
    ],
)
def test_detect_language(path, language):
    assert detect_language(path) == language


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tests/test_arguments.py", True),
        ("graph/src/graph/attribute_store.rs", False),
        ("src/foo_test.go", True),
        ("app/widget.test.tsx", True),
        ("bench/throughput.rs", True),
    ],
)
def test_is_test_path(path, expected):
    assert is_test_path(path) is expected


def test_module_path_for():
    assert module_path_for("graph/src/graph/core.rs") == "graph/src/graph"
    assert module_path_for("README.md") == ""


@pytest.mark.parametrize(
    ("email", "name", "expected"),
    [
        ("dependabot[bot]@users.noreply.github.com", "dependabot[bot]", True),
        ("noreply@github.com", "Renovate Bot", True),
        ("someone@example.com", "A Person", False),
    ],
)
def test_is_automation_author(email, name, expected):
    assert is_automation_author(email, name) is expected


class TestDependencyScanner:
    def test_gitmodules_yields_submodule_repositories(self):
        deps = parse_gitmodules(_read("falkordb_gitmodules.txt"))
        slugs = {d.slug for d in deps}
        assert "FalkorDB/RediSearch" in slugs
        assert all(d.kind == "submodule" for d in deps)

    def test_cargo_toml_yields_git_dependencies(self):
        deps = parse_cargo_toml(_read("falkordb_cargo_toml.txt"))
        assert any(d.slug == "AviAvni/redismodule-rs" for d in deps)

    def test_combined_scan_deduplicates_by_slug(self):
        deps = collect_dependencies(
            {
                ".gitmodules": _read("falkordb_gitmodules.txt"),
                "Cargo.toml": _read("falkordb_cargo_toml.txt"),
            }
        )
        # Two Cargo declarations point at the same repository.
        assert len(deps) == 4
        assert len({d.slug for d in deps}) == len(deps)

    def test_registry_packages_never_become_edges(self):
        cargo = '[dependencies]\nserde = "1.0"\nrand = "0.8"\n'
        assert parse_cargo_toml(cargo) == []

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://github.com/GraphBLAS/LAGraph.git", "GraphBLAS/LAGraph"),
            ("https://github.com/GraphBLAS/LAGraph/", "GraphBLAS/LAGraph"),
            ("git@github.com:DrTimothyAldenDavis/GraphBLAS.git", "DrTimothyAldenDavis/GraphBLAS"),
            ("https://example.com/some/repo.git", None),
            ("", None),
        ],
    )
    def test_normalise_repository_url(self, url, expected):
        dep = normalise_repository_url(url)
        assert (dep.slug if dep else None) == expected

    def test_repository_id_is_slug_safe(self):
        dep = normalise_repository_url("https://github.com/AviAvni/redismodule-rs")
        assert dep.repository_id == "repo_aviavni_redismodule_rs"

    def test_malformed_manifests_are_ignored(self):
        assert parse_cargo_toml("this is not toml [[[") == []
        assert parse_cargo_toml("") == []

    def test_codeowners_parses_owner_and_paths(self):
        entries = parse_codeowners(_read("falkordb_codeowners.txt"))
        assert entries
        assert all(owner.startswith("@") for owner, _ in entries)
        assert all(paths for _, paths in entries)