"""Tests for file description extraction from authored source text.

Pure functions only: no graph, no network, no model provider.
"""

import pytest

from app.ingestion.file_docs import (
    MAX_SUMMARY_CHARS,
    describe_source,
    first_item_summary,
    llm_fallback_available,
    markdown_summary,
    markdown_symbols,
    rust_module_summary,
    rust_public_symbols,
)

RUST_WITH_MODULE_DOCS = '''
//! Graph traversal over a time-filtered property graph.
//!
//! Entry points are [`Graph::query`] and [`Graph::ro_query`]. Callers that only
//! read should prefer the read-only handle.

use std::collections::HashMap;

pub struct Graph {
    pub name: String,
}

impl Graph {
    pub fn query(&self, statement: &str) -> Vec<String> {
        Vec::new()
    }

    pub async fn ro_query(&self, statement: &str) -> Vec<String> {
        Vec::new()
    }

    fn internal_helper(&self) {}
}

pub enum QueryKind { Read, Write }

pub trait Store { fn get(&self) -> Option<String>; }
'''

RUST_ITEM_DOCS_ONLY = '''
use std::sync::Arc;

/// Builds a connection pool sized for the configured worker count.
///
/// Returns `None` when `max_size` is zero.
pub fn build_pool(max_size: usize) -> Option<Arc<Pool>> {
    None
}

pub fn other_public_function() {}
'''

RUST_NO_DOCS = """
pub fn alpha() {}
pub struct Beta { x: u8 }
pub enum Gamma { One }
fn private_thing() {}
"""

MARKDOWN = """---
title: FalkorDB
---

# FalkorDB

[![ci](https://img.shields.io/badge/ci-passing-green)](https://example.com)

FalkorDB is a graph database built on Redis. It stores nodes and edges and
answers traversal queries.

## Installation

Run the build.

## Usage

```python
from falkordb import Graph
```

## License

BSD
"""


class TestRustModuleDocs:
    def test_prefers_inner_module_docs(self):
        summary = rust_module_summary(RUST_WITH_MODULE_DOCS)
        assert summary.startswith("Graph traversal over a time-filtered property graph.")
        assert "read-only handle" in summary

    def test_inner_block_docs_are_supported(self):
        text = "/*! Handles socket teardown.\n\n    Used by the server loop.\n*/\npub fn a() {}"
        assert "Handles socket teardown" in rust_module_summary(text)

    def test_module_summary_is_empty_when_absent(self):
        assert rust_module_summary(RUST_ITEM_DOCS_ONLY) == ""

    def test_attribute_before_docs_does_not_break_extraction(self):
        text = "#![allow(dead_code)]\n//! Docs after the crate attribute.\npub fn a() {}"
        assert "Docs after the crate attribute" in rust_module_summary(text)

    def test_first_code_line_terminates_the_module_docs(self):
        text = "use std::fmt;\n//! Not really module docs.\npub fn a() {}"
        assert rust_module_summary(text) == ""


class TestRustSymbols:
    def test_collects_public_items_in_order(self):
        assert rust_public_symbols(RUST_WITH_MODULE_DOCS)[:4] == [
            "Graph",
            "query",
            "ro_query",
            "QueryKind",
        ]

    def test_includes_impl_methods_and_traits(self):
        symbols = rust_public_symbols(RUST_WITH_MODULE_DOCS)
        assert "Store" in symbols
        assert "ro_query" in symbols

    def test_skips_private_items(self):
        assert "private_thing" not in rust_public_symbols(RUST_NO_DOCS)
        assert "internal_helper" not in rust_public_symbols(RUST_WITH_MODULE_DOCS)

    def test_handles_visibility_restrictions_and_qualifiers(self):
        text = "pub(crate) fn helper() {}\npub(super) struct Inner;\npub async unsafe fn risky() {}"
        assert rust_public_symbols(text) == ["helper", "Inner", "risky"]

    def test_deduplicates_repeated_names(self):
        text = "pub fn same() {}\npub fn same() {}"
        assert rust_public_symbols(text) == ["same"]


class TestRustItemDocs:
    def test_falls_back_to_item_docs(self):
        summary = first_item_summary(RUST_ITEM_DOCS_ONLY)
        assert summary.startswith("Builds a connection pool sized for the configured worker count.")
        assert "Returns `None`" in summary

    def test_falls_back_to_block_docs(self):
        text = "/** Saves the graph to disk. */\npub fn save() {}"
        assert "Saves the graph to disk." in first_item_summary(text)

    def test_doc_block_without_following_item_is_ignored(self):
        text = "/// Orphan docs at end of file.\n"
        assert first_item_summary(text) == ""


class TestDescribeSource:
    def test_rust_file_reports_module_docs_and_symbols(self):
        result = describe_source(RUST_WITH_MODULE_DOCS, "src/graph.rs", "Rust")
        assert result["docs_source"] == "module"
        assert result["symbols"]
        assert result["summary"]

    def test_rust_file_without_docs_reports_declarations(self):
        result = describe_source(RUST_NO_DOCS, "src/plain.rs", "Rust")
        assert result["docs_source"] == "declaration"
        assert result["symbols"] == ["alpha", "Beta", "Gamma"]
        assert "public Rust item" in result["summary"]

    def test_never_invents_a_summary_for_empty_text(self):
        result = describe_source("   \n\n", "src/empty.rs", "Rust")
        assert result == {"summary": "", "symbols": [], "docs_source": "none", "path": "src/empty.rs"}

    def test_unknown_language_is_handled_without_raising(self):
        assert describe_source("whatever", "notes.unknown")["docs_source"] == "none"

    def test_toml_lists_tables(self):
        result = describe_source('[package]\nname = "x"\n\n[dependencies]\nserde = "1"', "Cargo.toml")
        assert result["symbols"] == ["package", "dependencies"]
        assert result["docs_source"] == "key"

    def test_yaml_lists_top_level_keys_only(self):
        text = "name: ci\non:\n  push:\n    branches: [main]\njobs:\n  build:\n    runs-on: ubuntu\n"
        result = describe_source(text, ".github/workflows/ci.yml")
        assert result["symbols"] == ["name", "on", "jobs"]

    def test_summary_runs_to_a_paragraph_and_is_bounded(self):
        """A description is context, not a teaser.

        It used to be cut at 400 characters, which left readers holding half a
        claim with the evidence for the rest of it removed. It now runs to a
        full paragraph, and is bounded only where it has to be.
        """
        result = describe_source("//! " + ("word " * 500), "src/long.rs", "Rust")

        assert len(result["summary"]) <= MAX_SUMMARY_CHARS
        assert MAX_SUMMARY_CHARS == 5000

    def test_an_ordinary_description_is_not_cut(self):
        source = (
            "//! Core graph data structure and operations.\n"
            "//!\n"
            "//! The graph supports nodes, relationships, properties and indexes.\n"
        )
        summary = describe_source(source, "src/graph.rs", "Rust")["summary"]

        assert "[truncated]" not in summary
        assert "indexes" in summary


class TestMarkdown:
    def test_summary_skips_front_matter_badges_and_headings(self):
        summary = markdown_summary(MARKDOWN)
        assert summary.startswith("FalkorDB is a graph database built on Redis.")
        assert "img.shields.io" not in summary
        assert "title: FalkorDB" not in summary

    def test_symbols_are_headings_without_hash_markers(self):
        assert markdown_symbols(MARKDOWN) == [
            "FalkorDB",
            "Installation",
            "Usage",
            "License",
        ]

    def test_code_fence_content_is_not_treated_as_prose(self):
        text = "# Title\n\nIntro paragraph here.\n\n```\nfenced prose that is not real\n```\n"
        assert "fenced" not in markdown_summary(text)

    def test_describe_reports_heading_source(self):
        result = describe_source(MARKDOWN, "README.md", "Markdown")
        assert result["docs_source"] == "heading"
        assert result["symbols"]


class TestModelFallbackStaysInert:
    @pytest.mark.parametrize(
        "key",
        [None, "", "   ", "your_nebius_api_key", "YOUR_API_KEY", "placeholder", "none"],
    )
    def test_placeholder_keys_disable_the_fallback(self, key):
        assert llm_fallback_available(key) is False

    @pytest.mark.parametrize("key", ["abc123", "sk-live-key"])
    def test_real_keys_enable_the_fallback(self, key):
        assert llm_fallback_available(key) is True

    def test_configured_placeholder_keeps_fallback_off(self):
        from app.core.config import settings

        if llm_fallback_available(settings.NEBIUS_API_KEY):
            pytest.skip("a real provider key is configured in this environment")

class TestDescribeFilesInAClone:
    """Exercise the scanner-side wiring against a real checkout on disk."""

    def _make_repo(self, tmp_path):
        import subprocess

        def git(*args):
            subprocess.run(
                ["git", *args],
                cwd=tmp_path,
                check=True,
                capture_output=True,
            )

        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "Test")
        return git

    def _write(self, tmp_path, name, text, *, binary=False):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            target.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff\xfe\x00")
        else:
            target.write_text(text, encoding="utf-8")
        return target

    def test_annotates_kept_files_with_head_sha(self, tmp_path):
        from app.ingestion.repo_scanner import describe_files

        git = self._make_repo(tmp_path)
        self._write(tmp_path, "src/graph.rs", RUST_WITH_MODULE_DOCS)
        self._write(tmp_path, "README.md", MARKDOWN)
        git("add", "-A")
        git("commit", "-q", "-m", "initial")

        records = [
            {"path": "src/graph.rs", "language": "Rust"},
            {"path": "README.md", "language": "Markdown"},
        ]
        sha, described, needing, decls = describe_files(str(tmp_path), records)

        assert len(sha) == 40, "should record the full commit sha"
        assert described == 2
        assert records[0]["docs_source"] == "module"
        assert records[0]["symbols"]
        assert records[0]["docs_at_sha"] == sha
        assert records[1]["docs_source"] == "heading"

    def test_marks_binary_files_unreadable_instead_of_guessing(self, tmp_path):
        from app.ingestion.repo_scanner import describe_files

        self._make_repo(tmp_path)
        self._write(tmp_path, "assets/logo.png", "", binary=True)

        records = [{"path": "assets/logo.png", "language": "Other"}]
        _sha, described, needing, decls = describe_files(str(tmp_path), records)

        assert described == 0
        assert records[0]["docs_source"] == "skipped_unreadable"
        assert "summary" not in records[0]

    def test_skips_files_over_the_size_cap(self, tmp_path):
        from app.ingestion.repo_scanner import MAX_DESCRIBE_BYTES, describe_files

        self._make_repo(tmp_path)
        self._write(tmp_path, "big.md", "// filler\n" * (MAX_DESCRIBE_BYTES // 5))

        records = [{"path": "big.md", "language": "Markdown"}]
        _sha, described, needing, decls = describe_files(str(tmp_path), records)

        assert described == 0
        assert records[0]["docs_source"] == "skipped_large"

    def test_missing_file_is_left_undescribed(self, tmp_path):
        from app.ingestion.repo_scanner import describe_files

        self._make_repo(tmp_path)
        records = [{"path": "not/there.rs", "language": "Rust"}]
        _sha, described, needing, decls = describe_files(str(tmp_path), records)

        assert described == 0
        assert "summary" not in records[0]

    def test_file_without_usable_docs_gets_no_summary(self, tmp_path):
        from app.ingestion.repo_scanner import describe_files

        self._make_repo(tmp_path)
        self._write(tmp_path, "src/plain.rs", RUST_NO_DOCS)

        records = [{"path": "src/plain.rs", "language": "Rust"}]
        _sha, described, needing, decls = describe_files(str(tmp_path), records)

        # Public declarations still count as usable description.
        assert described == 1
        assert records[0]["docs_source"] == "declaration"
        assert records[0]["symbols"] == ["alpha", "Beta", "Gamma"]
    def test_gap_files_get_a_bounded_excerpt_for_the_fallback(self, tmp_path):
        from app.ingestion.repo_scanner import (
            MAX_EXCERPT_CHARS,
            build_excerpt,
            describe_files,
        )

        self._make_repo(tmp_path)
        # No module docs and no public declarations: nothing to extract.
        self._write(tmp_path, "src/plain.rs", "fn only_private() {}\nmod helpers;\n")

        records = [{"path": "src/plain.rs", "language": "Rust"}]
        sha, described, needing, decls = describe_files(str(tmp_path), records)

        assert described == 0
        assert needing == 1
        assert records[0]["docs_source"] == "none"
        assert records[0]["docs_at_sha"] == sha, "gap files must still pin a sha"
        assert "only_private" in records[0]["excerpt"]
        assert "summary" not in records[0], "no summary is invented in the sandbox"

    def test_described_files_carry_no_excerpt(self, tmp_path):
        from app.ingestion.repo_scanner import describe_files

        self._make_repo(tmp_path)
        self._write(tmp_path, "src/graph.rs", RUST_WITH_MODULE_DOCS)

        records = [{"path": "src/graph.rs", "language": "Rust"}]
        _sha, described, needing, decls = describe_files(str(tmp_path), records)

        assert described == 1
        assert needing == 0
        assert "excerpt" not in records[0], "wasteful payload for already-described files"

    def test_skipped_files_do_not_join_the_gap_set(self, tmp_path):
        from app.ingestion.repo_scanner import MAX_DESCRIBE_BYTES, describe_files

        self._make_repo(tmp_path)
        self._write(tmp_path, "assets/logo.png", "", binary=True)
        self._write(tmp_path, "big.md", "plain text\n" * (MAX_DESCRIBE_BYTES // 6))

        records = [
            {"path": "assets/logo.png", "language": "Other"},
            {"path": "big.md", "language": "Markdown"},
        ]
        _sha, described, needing, decls = describe_files(str(tmp_path), records)

        assert described == 0
        assert needing == 0, "binary and oversized files must not trigger model calls"

    def test_excerpt_is_bounded(self):
        from app.ingestion.repo_scanner import MAX_EXCERPT_CHARS, build_excerpt

        built = build_excerpt("x" * (MAX_EXCERPT_CHARS * 2))
        assert len(built) < MAX_EXCERPT_CHARS * 2
        assert "truncated for length" in built

    def test_declarations_are_attached_and_counted(self, tmp_path):
        from app.ingestion.repo_scanner import describe_files

        git = self._make_repo(tmp_path)
        self._write(tmp_path, "src/graph.rs", RUST_WITH_MODULE_DOCS)
        git("add", "-A")
        git("commit", "-q", "-m", "initial")

        records = [{"path": "src/graph.rs", "language": "Rust"}]
        _sha, _described, _needing, decls = describe_files(str(tmp_path), records)

        assert decls > 0
        assert decls == len(records[0]["declarations"])
        names = {d["name"] for d in records[0]["declarations"]}
        assert "Graph" in names and "query" in names

    def test_missing_grammar_reports_negative_count_rather_than_guessing(self, tmp_path, monkeypatch):
        import app.ingestion.repo_scanner as scanner

        monkeypatch.setattr(scanner, "available_extensions", list)
        git = self._make_repo(tmp_path)
        self._write(tmp_path, "src/graph.rs", RUST_WITH_MODULE_DOCS)
        git("add", "-A")
        git("commit", "-q", "-m", "initial")

        records = [{"path": "src/graph.rs", "language": "Rust"}]
        _sha, _described, _needing, decls = scanner.describe_files(str(tmp_path), records)

        assert decls == -1, "a negative count means the parser was unavailable"
        assert "declarations" not in records[0]
        assert records[0]["summary"], "file-level documentation still works"
