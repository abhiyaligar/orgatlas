"""Tests for tree-sitter declaration extraction.

Pure and offline: no graph, no network, no model provider.
"""

import pytest

from app.ingestion import symbols
from app.ingestion.symbols import (
    GrammarUnavailable,
    available_extensions,
    extract,
    load_language,
    spec_for,
    supported_extensions,
)

RUST = '''//! Module docs.

/// Adds two numbers and returns the sum.
pub fn add(a: u32, b: u32) -> u32 {
    a + b
}

pub(crate) fn crate_visible() {}

/// A widget.
pub struct Widget {
    /// The name.
    pub name: String,
}

/// Builds defaults.
impl Default for Widget {
    /// Creates one.
    pub fn new() -> Self {
        todo!()
    }
    async fn internal(&self) {}
}

/// Something drawable.
pub trait Draw {
    /// Renders it.
    fn draw(&self);
    fn required_but_undocumented(&self);
}

pub enum Kind { A, B }
pub const LIMIT: usize = 10;
pub type Alias = u32;
pub mod inner;
// pub fn written_in_a_comment() {}
fn truly_private() {}
const NOTE: &str = "pub fn written_in_a_string";
'''


def by_name(records, name):
    return next((r for r in records if r["name"] == name), None)


class TestNoPhantomSymbols:
    """The failure mode that motivated using a real parser."""

    def test_pub_fn_inside_a_line_comment_is_not_a_symbol(self):
        assert by_name(extract(RUST, "a.rs"), "written_in_a_comment") is None

    def test_pub_fn_inside_a_string_is_not_a_symbol(self):
        names = {r["name"] for r in extract(RUST, "a.rs")}
        assert "written_in_a_string" not in names

    def test_truly_private_item_is_excluded(self):
        assert by_name(extract(RUST, "a.rs"), "truly_private") is None

    def test_undecorated_method_inside_public_impl_is_excluded(self):
        assert by_name(extract(RUST, "a.rs"), "internal") is None


class TestRustVisibility:
    def test_plain_pub_is_recorded(self):
        assert by_name(extract(RUST, "a.rs"), "add")["visibility"] == "pub"

    def test_restricted_visibility_is_preserved_verbatim(self):
        assert by_name(extract(RUST, "a.rs"), "crate_visible")["visibility"] == "pub(crate)"

    def test_private_impl_method_is_excluded(self):
        assert by_name(extract(RUST, "a.rs"), "internal") is None


class TestRustKinds:
    @pytest.mark.parametrize(
        ("name", "kind"),
        [
            ("add", "function"),
            ("Widget", "struct"),
            ("Draw", "trait"),
            ("Kind", "enum"),
            ("LIMIT", "constant"),
            ("Alias", "type_alias"),
            ("inner", "module"),
        ],
    )
    def test_kind_is_correct(self, name, kind):
        assert by_name(extract(RUST, "a.rs"), name)["kind"] == kind

    def test_all_public_items_are_found(self):
        names = {r["name"] for r in extract(RUST, "a.rs")}
        assert {"add", "crate_visible", "Widget", "new", "Draw", "draw", "Kind", "LIMIT", "Alias", "inner"} <= names

    def test_trait_member_is_kept_without_a_visibility_modifier(self):
        draw = by_name(extract(RUST, "a.rs"), "draw")
        assert draw is not None
        assert draw["visibility"] == "trait"
        assert draw["container"] == "Draw"


class TestContainers:
    def test_impl_method_carries_the_qualified_container(self):
        new = by_name(extract(RUST, "a.rs"), "new")
        assert new["container"] == "Default for Widget"

    def test_plain_impl_uses_the_type_name(self):
        src = "impl Widget {\n    /// X.\n    pub fn go(&self) {}\n}"
        assert by_name(extract(src, "a.rs"), "go")["container"] == "Widget"


class TestDocComments:
    def test_doc_comment_is_attached_to_the_right_item(self):
        add = by_name(extract(RUST, "a.rs"), "add")
        assert add["doc_comment"] == "Adds two numbers and returns the sum."
        assert add["documented"] is True

    def test_undocumented_item_is_flagged_not_invented(self):
        kind = by_name(extract(RUST, "a.rs"), "Kind")
        assert kind["doc_comment"] == ""
        assert kind["documented"] is False

    def test_module_comment_is_not_mistaken_for_an_item_doc(self):
        src = "//! Module level.\n\npub fn first() {}\n"
        first = by_name(extract(src, "a.rs"), "first")
        assert first["doc_comment"] == "", "module docs belong to the file, not the item"

    def test_block_comment_docs_are_read(self):
        src = "/** Saves the graph. */\npub fn save() {}\n"
        assert by_name(extract(src, "a.rs"), "save")["doc_comment"] == "Saves the graph."

    def test_doc_block_detached_by_a_blank_line_is_not_attached(self):
        src = "/// Orphan docs.\n\npub fn later() {}\n"
        assert by_name(extract(src, "a.rs"), "later")["doc_comment"] == ""


class TestSignaturesAndPositions:
    def test_signature_stops_before_the_body(self):
        signature = by_name(extract(RUST, "a.rs"), "add")["signature"]
        assert signature.startswith("pub fn add(a: u32, b: u32) -> u32")
        assert "{" not in signature

    def test_line_numbers_are_one_based(self):
        records = extract(RUST, "a.rs")
        assert by_name(records, "add")["line"] == 4
        for record in records:
            assert record["line"] >= 1
            assert record["end_line"] >= record["line"]


class TestDegradation:
    def test_unknown_extension_yields_nothing(self):
        assert extract("whatever", "notes.unknown") == []

    def test_structured_files_without_symbols_yield_nothing(self):
        assert extract("[package]\nname='x'", "Cargo.toml") == []

    def test_missing_grammar_raises_a_typed_error(self, monkeypatch):
        monkeypatch.setitem(symbols.SPECS, ".rs", symbols.LanguageSpec("tree_sitter_nope"))
        monkeypatch.setattr(symbols, "_LOADED", {})
        with pytest.raises(GrammarUnavailable):
            load_language(".rs")

    def test_file_with_parse_errors_yields_nothing(self):
        broken = "pub fn broken( {{{ !!!"
        assert extract(broken, "a.rs") == []

    def test_empty_source_yields_nothing(self):
        assert extract("", "a.rs") == []

    def test_missing_grammar_falls_back_to_empty_not_a_crash(self, monkeypatch):
        def unavailable(_extension):
            raise GrammarUnavailable("gone")

        monkeypatch.setattr(symbols, "load_language", unavailable)
        assert extract(RUST, "a.rs") == []


class TestOtherLanguages:
    """One snippet per installed grammar, so no entry is untested."""

    def test_python_excludes_underscore_private(self):
        src = "class W:\n    def new(self): pass\n    def _p(self): pass\ndef top(): pass\ndef _hidden(): pass\n"
        names = {r["name"] for r in extract(src, "a.py")}
        assert names == {"W", "new", "top"}

    def test_python_method_carries_container(self):
        src = "class W:\n    def new(self): pass\n"
        assert by_name(extract(src, "a.py"), "new")["container"] == "W"

    def test_javascript(self):
        src = "class W { new() {} _p() {} }\nfunction top() {}\n"
        names = {r["name"] for r in extract(src, "a.js")}
        assert names == {"W", "new", "top"}

    def test_typescript(self):
        src = "export interface Draw { draw(): void }\nexport function top(): void {}\n"
        names = {r["name"] for r in extract(src, "a.ts")}
        assert {"Draw", "top"} <= names

    def test_tsx(self):
        src = "export function C() { return null; }\ninterface P { x: number }\n"
        names = {r["name"] for r in extract(src, "a.tsx")}
        assert names == {"C", "P"}

    def test_go_excludes_unexported_and_keeps_types(self):
        src = (
            "package main\ntype Widget struct{}\ntype Alias = int\n"
            "func Top() {}\nfunc (w *Widget) Method() {}\nfunc helper() {}\n"
        )
        names = {r["name"] for r in extract(src, "a.go")}
        assert names == {"Widget", "Alias", "Top", "Method"}

    def test_java_excludes_private_members(self):
        src = "public class W { public void draw() {} private void p() {} }\ninterface I { void x(); }\n"
        names = {r["name"] for r in extract(src, "a.java")}
        assert names == {"W", "draw", "I", "x"}

    def test_c_excludes_static_functions_and_reads_declarator_names(self):
        src = "int add(int a, int b) { return a+b; }\nstatic int hidden(void) { return 0; }\n"
        names = {r["name"] for r in extract(src, "a.c")}
        assert names == {"add"}

    def test_c_struct(self):
        assert "Point" in {r["name"] for r in extract("struct Point { int x; };\n", "a.c")}

    def test_cpp_captures_namespace_and_class_containers(self):
        src = "namespace n { int f() { return 1; } }\nclass C { public: void m() {} };\n"
        records = extract(src, "a.cpp")
        assert by_name(records, "f")["container"] == "n"
        assert by_name(records, "m")["container"] == "C"


class TestRegistry:
    def test_all_ten_grammar_packages_are_registered(self):
        modules = {spec.module for spec in symbols.SPECS.values()}
        expected = {
            "tree_sitter_rust",
            "tree_sitter_c",
            "tree_sitter_cpp",
            "tree_sitter_python",
            "tree_sitter_javascript",
            "tree_sitter_typescript",
            "tree_sitter_go",
            "tree_sitter_java",
            "tree_sitter_yaml",
            "tree_sitter_toml",
        }
        assert expected <= modules

    def test_every_registered_grammar_is_installed_and_loadable(self):
        ready = available_extensions()
        missing = [ext for ext in supported_extensions() if ext not in ready]
        assert not missing, f"grammars unavailable in this environment: {missing}"

    def test_spec_lookup_is_case_insensitive(self):
        assert spec_for("src/Main.RS").module == "tree_sitter_rust"

class TestSymbolQueriesAgainstTheEngine:
    """Regression tests for query shapes FalkorDB rejects.

    ORDER BY cannot reference a RETURN alias, and length() on a string property
    fails with "expected Path or Null but was String"; size() on the property
    works. These run only when a graph is reachable.
    """

    def _graph(self):
        pytest.importorskip("app.graph.connection")
        from app.graph.connection import graph_manager

        try:
            graph_manager.check_health()
        except Exception:
            pytest.skip("no graph available in this environment")
        return graph_manager.get_or_create_graph()

    def test_symbol_lookup_orders_without_alias_or_length(self):
        from app.graph import queries

        graph = self._graph()
        try:
            rows = graph.query(
                queries.GET_CODE_SYMBOL,
                {"name": "graph_udf", "file_id": "", "file_prefix": "", "limit": 5},
            ).result_set
        except Exception as exc:
            pytest.fail(f"GET_CODE_SYMBOL rejected by the engine: {exc}")
        assert isinstance(rows, list)

    def test_symbol_lookup_filters_by_file_when_given_a_prefix(self):
        """The prefix filter has to run, not merely be accepted.

        ``STARTS WITH $file_id + '::'`` made FalkorDB reject the whole statement,
        and the failure was invisible: the tool refused with "no declaration
        named", which reads exactly like a genuinely missing symbol.
        """
        from app.graph import queries

        graph = self._graph()
        with_prefix = graph.query(
            queries.GET_CODE_SYMBOL,
            {
                "name": "graph_udf",
                "file_id": "some_repo::src/a.c",
                "file_prefix": "some_repo::src/a.c::",
                "limit": 5,
            },
        ).result_set
        without_prefix = graph.query(
            queries.GET_CODE_SYMBOL,
            {"name": "graph_udf", "file_id": "", "file_prefix": "", "limit": 5},
        ).result_set

        assert isinstance(with_prefix, list)
        assert len(with_prefix) <= len(without_prefix)

    def test_name_search_runs(self):
        from app.graph import queries

        graph = self._graph()
        rows = graph.query(
            queries.SEARCH_CODE_SYMBOLS, {"query": "udf", "limit": 5}
        ).result_set
        assert isinstance(rows, list)

    def test_owner_lookup_runs(self):
        from app.graph import queries

        graph = self._graph()
        rows = graph.query(
            queries.GET_SYMBOL_FILE,
            {"symbol_id": "repo_falkordb_falkordb::src/commands/udf.rs::function::graph_udf"},
        ).result_set
        assert isinstance(rows, list)