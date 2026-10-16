"""Tests for repository file filtering and the batched write plan."""

import json
from pathlib import Path

import pytest

from app.ingestion.repo_scanner import FileFilter, _matches
from app.ingestion.seed_repo import build_batches, repository_id_for

FIXTURES = Path(__file__).parent / "fixtures" / "git"


class TestFileFilter:
    def test_no_filters_keeps_everything(self):
        assert FileFilter().keep("src/main.rs")
        assert FileFilter().keep("anything/at/all.txt")

    def test_exclude_by_directory_prefix(self):
        f = FileFilter(exclude_paths=["deps/"])
        assert not f.keep("deps/RediSearch/src/core.c")
        assert f.keep("src/main.rs")

    def test_exclude_by_glob(self):
        f = FileFilter(exclude_paths=["*.lock"])
        assert not f.keep("Cargo.lock")
        assert f.keep("Cargo.toml")

    def test_include_glob_matches_at_any_depth(self):
        f = FileFilter(include_globs=["*.rs"])
        assert f.keep("src/main.rs")
        assert f.keep("graph/src/graph/core.rs")
        assert not f.keep("README.md")

    def test_include_and_exclude_combine(self):
        f = FileFilter(include_globs=["*.rs"], exclude_paths=["deps/"])
        assert not f.keep("deps/RediSearch/src/core.c")
        assert f.keep("graph/src/graph/core.rs")

    def test_manifests_are_always_kept(self):
        f = FileFilter(include_globs=["*.rs"])
        assert f.keep(".gitmodules")
        assert f.keep("CODEOWNERS")

    def test_backslashes_are_normalised(self):
        assert FileFilter(exclude_paths=["deps/"]).keep("src\\main.rs")
        assert not FileFilter(exclude_paths=["deps/"]).keep("deps\\RediSearch\\x.c")

    def test_empty_path_is_rejected(self):
        assert not FileFilter().keep("")

    def test_from_config_reads_the_repo_template(self):
        config_path = Path(__file__).resolve().parents[2] / "data" / "repos.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))["repositories"][0]
        f = FileFilter.from_config(config)
        assert not f.keep("deps/RediSearch/src/core.c")
        assert f.keep("graph/src/graph/core.rs")

    def test_apply_drops_commits_with_no_relevant_files(self):
        from app.ingestion.git_history_parser import CommitRecord

        commits = [
            CommitRecord("a" * 40, "A", "a@x", "2024-01-01T00:00:00Z", "s", (), ("deps/x.c",)),
            CommitRecord("b" * 40, "B", "b@x", "2024-01-01T00:00:00Z", "s", (), ("src/main.rs",)),
        ]
        kept = FileFilter(exclude_paths=["deps/"]).apply(commits)
        assert [c.sha for c in kept] == ["b" * 40]
        assert kept[0].files == ("src/main.rs",)

    def test_apply_keeps_merge_commits_without_files(self):
        from app.ingestion.git_history_parser import CommitRecord

        commits = [CommitRecord("c" * 40, "C", "c@x", "2024-01-01T00:00:00Z", "s", ("p", "q"), ())]
        assert len(FileFilter(exclude_paths=["deps/"]).apply(commits)) == 1


class TestRepositoryId:
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/FalkorDB/FalkorDB",
            "https://github.com/FalkorDB/FalkorDB/",
            "https://github.com/FalkorDB/FalkorDB.git",
            "git@github.com:FalkorDB/FalkorDB.git",
        ],
    )
    def test_id_is_stable_across_url_forms(self, url):
        assert repository_id_for(url) == "repo_falkordb_falkordb"

    def test_id_is_slug_safe(self):
        assert repository_id_for("https://github.com/AviAvni/redismodule-rs") == (
            "repo_aviavni_redismodule_rs"
        )


class TestBatchedWritePlan:
    def test_commits_are_planned_before_files(self):
        payload = {
            "repository_url": "https://github.com/FalkorDB/FalkorDB",
            "scanned_at": "2026-01-01T00:00:00Z",
            "commits": [
                {
                    "sha": "a" * 40,
                    "subject": "s",
                    "author_name": "A",
                    "author_email": "a@x",
                    "authored_at": "2024-01-01T00:00:00Z",
                    "parents": [],
                    "is_merge": False,
                    "pr_number": 1,
                    "files": ["src/main.rs"],
                }
            ],
            "files": [
                {"path": "src/main.rs", "language": "Rust", "is_test": False, "module": "src"}
            ],
            "authors": [{"name": "A", "email": "a@x"}],
            "dependencies": [
                {
                    "slug": "FalkorDB/RediSearch",
                    "repository_id": "repo_falkordb_redisearch",
                    "url": "https://github.com/FalkorDB/RediSearch",
                    "kind": "submodule",
                    "declared_in": "deps/RediSearch",
                }
            ],
            "codeowners_paths": ["/build/"],
        }

        plan = build_batches(payload)
        labels = [query.strip().splitlines()[1].strip() for query, _ in plan]

        commit_index = next(i for i, l in enumerate(labels) if "(c:Commit" in l)
        file_index = next(i for i, l in enumerate(labels) if "(f:File" in l)
        assert commit_index < file_index

    def test_dependency_rows_are_planned(self):
        payload = {
            "repository_url": "https://github.com/FalkorDB/FalkorDB",
            "commits": [],
            "files": [],
            "authors": [],
            "dependencies": [
                {
                    "slug": "FalkorDB/RediSearch",
                    "repository_id": "repo_falkordb_redisearch",
                    "url": "https://github.com/FalkorDB/RediSearch",
                    "kind": "submodule",
                    "declared_in": "deps/RediSearch",
                }
            ],
            "codeowners_paths": [],
        }
        plan = build_batches(payload)
        assert any("Repository" in query for query, _ in plan)
        assert any("DEPENDS_ON_REPO" in query for query, _ in plan)

    def test_empty_payload_plans_nothing_beyond_the_repository(self):
        payload = {
            "repository_url": "https://github.com/FalkorDB/FalkorDB",
            "commits": [],
            "files": [],
            "authors": [],
            "dependencies": [],
            "codeowners_paths": [],
        }
        plan = build_batches(payload)
        assert len(plan) == 1


class TestGlobMatching:
    @pytest.mark.parametrize(
        ("path", "pattern", "expected"),
        [
            ("src/main.rs", "*.rs", True),
            ("graph/src/core.rs", "src", False),
            ("src/graph/core.rs", "src", True),
            ("graph/src/core.rs", "src/", False),
            ("Cargo.lock", "*.lock", True),
            ("src/main.rs", "deps", False),
        ],
    )
    def test_matches(self, path, pattern, expected):
        assert _matches(path, pattern) is expected