"""Extract function- and type-level structure from source files.

The scanner already reads every kept file inside the sandbox, so this runs in
the same pass and adds no cost.

Why tree-sitter rather than a regex: comments and string literals are nodes,
so a ``pub fn`` written inside either can never be mistaken for a declaration.
The previous regex approach could not make that distinction, which is why a
handful of phantom symbols were possible.

Only items that are part of a file's externally reachable surface are emitted.
An item qualifies when it carries an explicit ``pub``-style visibility, or
when it is a member declaration inside a public trait, which has no
visibility modifier of its own but is part of that trait's contract.

If a grammar is unavailable, the language is not mapped, or the parse
contains errors, this returns an empty list. Missing symbols are recoverable;
wrong symbols are not.
"""

from __future__ import annotations

import importlib
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_SYMBOLS_PER_FILE = 400
MAX_SIGNATURE_CHARS = 300
MAX_DOC_CHARS = 1200

RUST_VISIBILITY_NODE = "visibility_modifier"
RUST_CONTAINER_TYPES = ("impl_item", "trait_item")


class GrammarUnavailable(RuntimeError):
    """A tree-sitter grammar could not be imported or loaded."""


class LanguageSpec:
    """How to read declarations out of one grammar."""

    def __init__(
        self,
        module: str,
        loader: str = "language",
        item_types: Optional[Dict[str, str]] = None,
        name_field: str = "name",
        container_types: tuple[str, ...] = (),
        visibility_node: Optional[str] = None,
        exclude_visibility: Optional[str] = None,
        private_name: Optional[str] = None,
        declarator_field: Optional[str] = None,
        treat_trait_members_as_public: bool = False,
    ) -> None:
        self.module = module
        self.loader = loader
        self.item_types = item_types or {}
        self.name_field = name_field
        self.container_types = container_types
        self.visibility_node = visibility_node
        self.exclude_visibility = (
            re.compile(exclude_visibility) if exclude_visibility else None
        )
        self.private_name = re.compile(private_name) if private_name else None
        self.declarator_field = declarator_field
        self.treat_trait_members_as_public = treat_trait_members_as_public


_C_LIKE = {
    "function_definition": "function",
    "struct_specifier": "struct",
    "union_specifier": "struct",
    "enum_specifier": "enum",
    "type_definition": "type_alias",
    "declaration": "constant",
}

SPECS: Dict[str, LanguageSpec] = {
    ".rs": LanguageSpec(
        "tree_sitter_rust",
        item_types={
            "function_item": "function",
            "function_signature_item": "function",
            "struct_item": "struct",
            "enum_item": "enum",
            "union_item": "struct",
            "trait_item": "trait",
            "mod_item": "module",
            "const_item": "constant",
            "static_item": "constant",
            "type_item": "type_alias",
        },
        container_types=RUST_CONTAINER_TYPES,
        visibility_node=RUST_VISIBILITY_NODE,
        treat_trait_members_as_public=True,
    ),
    ".c": LanguageSpec(
        "tree_sitter_c",
        item_types=_C_LIKE,
        declarator_field="declarator",
        visibility_node="storage_class_specifier",
        exclude_visibility=r"\bstatic\b",
    ),
    ".h": LanguageSpec(
        "tree_sitter_c",
        item_types=_C_LIKE,
        declarator_field="declarator",
        visibility_node="storage_class_specifier",
        exclude_visibility=r"\bstatic\b",
    ),
    ".cpp": LanguageSpec(
        "tree_sitter_cpp",
        item_types={**_C_LIKE, "field_definition": "method"},
        declarator_field="declarator",
        visibility_node="storage_class_specifier",
        exclude_visibility=r"\bstatic\b",
        container_types=("class_specifier", "namespace_definition"),
    ),
    ".cc": LanguageSpec(
        "tree_sitter_cpp",
        item_types={**_C_LIKE, "field_definition": "method"},
        declarator_field="declarator",
        visibility_node="storage_class_specifier",
        exclude_visibility=r"\bstatic\b",
        container_types=("class_specifier", "namespace_definition"),
    ),
    ".hpp": LanguageSpec(
        "tree_sitter_cpp",
        item_types={**_C_LIKE, "field_definition": "method"},
        declarator_field="declarator",
        visibility_node="storage_class_specifier",
        exclude_visibility=r"\bstatic\b",
        container_types=("class_specifier", "namespace_definition"),
    ),
    ".py": LanguageSpec(
        "tree_sitter_python",
        item_types={
            "function_definition": "function",
            "class_definition": "class",
        },
        container_types=("class_definition",),
        private_name=r"^_(?!_)",
    ),
    ".js": LanguageSpec(
        "tree_sitter_javascript",
        item_types={
            "function_declaration": "function",
            "generator_function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
        },
        container_types=("class_declaration", "class"),
        private_name=r"^_",
    ),
    ".jsx": LanguageSpec("tree_sitter_javascript", item_types={"function_declaration": "function", "class_declaration": "class"}),
    ".ts": LanguageSpec(
        "tree_sitter_typescript",
        "language_typescript",
        item_types={
            "function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
            "interface_declaration": "interface",
            "type_alias_declaration": "type_alias",
            "enum_declaration": "enum",
        },
        container_types=("class_declaration", "interface_declaration"),
        private_name=r"^_",
    ),
    ".tsx": LanguageSpec(
        "tree_sitter_typescript",
        "language_tsx",
        item_types={
            "function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
            "interface_declaration": "interface",
        },
        container_types=("class_declaration", "interface_declaration"),
        private_name=r"^_",
    ),
    ".go": LanguageSpec(
        "tree_sitter_go",
        item_types={
            "function_declaration": "function",
            "method_declaration": "method",
            "type_spec": "type",
            "type_alias": "type_alias",
        },
        container_types=(),
        # Go marks unexported identifiers with a lowercase first letter, not an
        # underscore, so the usual underscore rule would let them through.
        private_name=r"^[a-z_]",
    ),
    ".java": LanguageSpec(
        "tree_sitter_java",
        item_types={
            "class_declaration": "class",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "method_declaration": "method",
            "constructor_declaration": "constructor",
        },
        container_types=("class_declaration", "interface_declaration", "enum_declaration"),
        visibility_node="modifiers",
        exclude_visibility=r"\bprivate\b",
        private_name=r"^_",
    ),
    ".yml": LanguageSpec("tree_sitter_yaml", item_types={}),
    ".yaml": LanguageSpec("tree_sitter_yaml", item_types={}),
    ".toml": LanguageSpec("tree_sitter_toml", item_types={}),
}

_LOADED: Dict[str, Any] = {}


def supported_extensions() -> List[str]:
    return sorted(SPECS)


def spec_for(path: str) -> Optional[LanguageSpec]:
    lowered = path.lower()
    for extension, spec in SPECS.items():
        if lowered.endswith(extension):
            return spec
    return None


def load_language(extension: str) -> Any:
    """Load and cache one grammar. Raises :class:`GrammarUnavailable`."""
    if extension in _LOADED:
        return _LOADED[extension]

    spec = SPECS.get(extension)
    if spec is None:
        raise GrammarUnavailable(f"no grammar registered for {extension!r}")

    try:
        from tree_sitter import Language, Parser

        module = importlib.import_module(spec.module)
        raw = getattr(module, spec.loader)()
        language = Language(raw)
        # Constructing a parser and parsing proves the grammar is usable, not
        # merely importable.
        Parser(language).parse(b"")
    except Exception as exc:
        raise GrammarUnavailable(f"{spec.module}: {exc}") from exc

    _LOADED[extension] = language
    return language


def available_extensions() -> List[str]:
    """Extensions whose grammar is actually installed right now."""
    ready: List[str] = []
    for extension in SPECS:
        try:
            load_language(extension)
        except GrammarUnavailable:
            continue
        ready.append(extension)
    return ready


def _trim(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


def _is_doc_comment(node) -> bool:
    """Only outer documentation attaches to a declaration.

    ``//!`` and ``/*! */`` are inner documentation and belong to the module,
    so they must never be attributed to the first item in the file.
    """
    text = node.text.decode("utf-8", errors="replace").lstrip()
    if node.type == "line_comment":
        return text.startswith("///") and not text.startswith("////")
    if node.type == "block_comment":
        return text.startswith("/**") and not text.startswith("/***")
    return False


def _doc_body(node) -> str:
    text = node.text.decode("utf-8", errors="replace")
    if node.type == "line_comment":
        return text.strip().lstrip("/").strip()
    body = text.strip()
    if body.startswith("/**"):
        body = body[3:]
    elif body.startswith("/*"):
        body = body[2:]
    if body.endswith("*/"):
        body = body[:-2]
    lines = [line.strip().strip("*").strip() for line in body.splitlines()]
    return "\n".join(lines)


def _is_attached(comment, item) -> bool:
    """True when the declaration follows the comment with no blank line.

    A line comment consumes its own trailing newline, so its end row already
    points at the item's row. A block comment does not, so the item starts one
    row later. Comparing rows therefore distinguishes a blank line from a plain
    newline, which neither the byte gap nor a newline count can do on its own.
    """
    expected = comment.end_point[0]
    if comment.type != "line_comment":
        expected += 1
    return item.start_point[0] == expected


def _collect_doc_comment(node, source: bytes) -> str:
    """Read the doc block attached immediately above a declaration.

    Comments are ``extra`` nodes in the tree, so they are walked as real
    siblings rather than matched as text.
    """
    lines: List[str] = []
    sibling = node.prev_sibling

    while sibling is not None and sibling.type in ("line_comment", "block_comment"):
        if not _is_doc_comment(sibling) or not _is_attached(sibling, node):
            break

        body = _doc_body(sibling).strip()
        if lines and not body:
            break
        lines.insert(0, body)
        sibling = sibling.prev_sibling

    return _trim(" ".join(part for part in lines if part).strip(), MAX_DOC_CHARS)


def _visibility_of(node, spec: LanguageSpec) -> Optional[str]:
    if not spec.visibility_node:
        return None
    for child in node.children:
        if child.type == spec.visibility_node:
            return child.text.decode("utf-8", errors="replace").strip()
    return None


def _name_of(node, spec: LanguageSpec) -> str:
    if spec.declarator_field:
        declarator = node.child_by_field_name(spec.declarator_field)
        if declarator is not None:
            # C declarators nest (pointers, arrays), so walk to the identifier.
            cursor = declarator
            while cursor is not None:
                if cursor.type in ("identifier", "field_identifier", "type_identifier"):
                    return cursor.text.decode("utf-8", errors="replace")
                cursor = cursor.child_by_field_name("declarator")
            text = declarator.text.decode("utf-8", errors="replace")
            match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", text.strip())
            return match.group(1) if match else ""

    named = node.child_by_field_name(spec.name_field)
    return named.text.decode("utf-8", errors="replace") if named is not None else ""


def _container_of(node, spec: LanguageSpec) -> str:
    """Return the enclosing type, qualified by any trait for the impl block."""
    parent = node.parent
    while parent is not None:
        if parent.type in spec.container_types:
            if parent.type == "impl_item":
                trait = parent.child_by_field_name("trait")
                type_node = parent.child_by_field_name("type")
                type_text = (
                    type_node.text.decode("utf-8", errors="replace") if type_node else "?"
                )
                if trait is not None:
                    trait_text = trait.text.decode("utf-8", errors="replace")
                    return f"{trait_text} for {type_text}"
                return type_text
            named = parent.child_by_field_name("name")
            return named.text.decode("utf-8", errors="replace") if named else ""
        parent = parent.parent
    return ""


def _signature_of(node, source: bytes, spec: LanguageSpec) -> str:
    """Slice the declaration up to its body, so the signature reads cleanly."""
    body = node.child_by_field_name("body")
    end = body.start_byte if body is not None else node.end_byte
    text = source[node.start_byte:min(end, node.start_byte + MAX_SIGNATURE_CHARS)]
    return _trim(text.decode("utf-8", errors="replace"), MAX_SIGNATURE_CHARS)


def _parent_kind(node, spec: LanguageSpec) -> Optional[str]:
    """For Rust trait members, detect an enclosing trait declaration."""
    if not spec.treat_trait_members_as_public:
        return None
    parent = node.parent
    while parent is not None:
        if parent.type in spec.container_types:
            return parent.type
        parent = parent.parent
    return None


def extract(text: str, path: str, max_symbols: int = MAX_SYMBOLS_PER_FILE) -> List[Dict[str, Any]]:
    """Return the public declarations found in one file.

    Returns an empty list whenever an answer cannot be trusted.
    """
    spec = spec_for(path)
    if spec is None or not spec.item_types:
        return []

    source = text.encode("utf-8")
    extension = next(ext for ext in SPECS if path.lower().endswith(ext))

    try:
        from tree_sitter import Parser

        language = load_language(extension)
    except GrammarUnavailable as exc:
        logger.debug("symbol extraction skipped for %s: %s", path, exc)
        return []

    try:
        tree = Parser(language).parse(source)
    except Exception as exc:
        logger.debug("parse failed for %s: %s", path, exc)
        return []

    if tree is None or tree.root_node.has_error:
        # A partial tree would produce a partial symbol list. Report nothing
        # rather than something incomplete presented as complete.
        logger.debug("parse has errors for %s; skipping symbols", path)
        return []

    symbols: List[Dict[str, Any]] = []
    stack = [tree.root_node]

    while stack and len(symbols) < max_symbols:
        node = stack.pop()
        if node.child_count:
            stack.extend(reversed(node.children))

        kind = spec.item_types.get(node.type)
        if kind is None:
            continue

        name = _name_of(node, spec)
        if not name:
            continue

        if spec.private_name and spec.private_name.match(name):
            continue

        visibility = _visibility_of(node, spec)

        if spec.exclude_visibility and visibility and spec.exclude_visibility.search(visibility):
            # e.g. a Java private member or a C file-local function.
            continue

        if spec.visibility_node and spec.visibility_node == RUST_VISIBILITY_NODE:
            if not visibility:
                # No modifier: keep it only when it is a member of a public
                # trait, where the declaration is the trait's contract.
                parent_kind = _parent_kind(node, spec)
                if parent_kind != "trait_item":
                    continue
                visibility = "trait"
            elif node.type == "trait_item" and visibility in ("trait",):
                continue

        doc = _collect_doc_comment(node, source)
        container = _container_of(node, spec)

        symbols.append(
            {
                "name": name,
                "kind": kind,
                "signature": _signature_of(node, source, spec),
                "doc_comment": doc,
                "documented": bool(doc),
                "line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "visibility": visibility or "",
                "container": container,
            }
        )

    return symbols