"""A repository is answerable from the files it contains.

"What is the tech stack" routes to the file intent on a Repository, which had no
retrieval behind it: the branch looked for a File id that a Repository can never
have, so the answer was a bare "insufficient evidence" while the graph held 215
files with their languages.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.ask_service import AskService
from app.services.question_resolution import ResolvedEntity


def _gateway(mix, files):
    gateway = MagicMock()
    gateway.get_repository_language_mix.return_value = mix
    gateway.get_repository_files.return_value = files
    return gateway


MIX = [
    {"language": "Python", "files": 91},
    {"language": "JavaScript", "files": 89},
]

FILES = [
    {
        "language": "Python",
        "files": 91,
        "samples": [{"path": "backend/app/services/auth_service.py", "summary": "Auth.", "docs_source": "authored"}],
    },
    {
        "language": "JavaScript",
        "files": 89,
        "samples": [{"path": "frontend/src/components/Navbar.jsx", "summary": "Nav.", "docs_source": "model"}],
    },
]

REPOSITORY = ResolvedEntity(
    term="EstateX",
    entity_id="repo_estatex",
    label="Repository",
    name="EstateX",
    quality=0,
)


def _service(gateway):
    return AskService(gateway=gateway)


def test_a_repository_question_returns_the_language_mix():
    svc = _service(_gateway(MIX, FILES))

    package = svc.retrieve_repository("repo_estatex", "EstateX")

    assert package is not None
    assert "Python (91 files)" in package["answer"]
    assert "JavaScript (89 files)" in package["answer"]


def test_a_repository_question_is_supported_and_cites_its_files():
    svc = _service(_gateway(MIX, FILES))

    package = svc.retrieve_repository("repo_estatex", "EstateX")

    assert package["confidence"] == "supported"
    assert {c.source_id for c in package["citations"]} == {
        "repo_estatex::backend/app/services/auth_service.py",
        "repo_estatex::frontend/src/components/Navbar.jsx",
    }


def test_the_subgraph_carries_the_repository_and_its_sampled_files():
    svc = _service(_gateway(MIX, FILES))

    graph = svc.retrieve_repository("repo_estatex", "EstateX")["graph"]

    labels = {node.label for node in graph.nodes}
    assert "Repository" in labels and "File" in labels
    assert all(edge.type == "PART_OF" for edge in graph.edges)
    assert graph.edges[0].target == "repo_estatex"


def test_a_repository_with_no_files_yields_nothing_rather_than_an_empty_answer():
    svc = _service(_gateway([], []))

    assert svc.retrieve_repository("repo_empty", "Empty") is None


def test_an_unknown_language_is_not_reported_as_a_technology():
    mix = [{"language": "Unknown", "files": 4}, {"language": "Go", "files": 12}]
    gateway = _gateway(mix, [{"language": "Go", "files": 12, "samples": []}])
    gateway.get_repository_language_mix.return_value = [
        {"language": "Go", "files": 12}
    ]

    package = _service(gateway).retrieve_repository("repo_x", "X")

    assert "Unknown" not in package["answer"]


def test_the_retrieve_dispatch_sends_a_repository_to_the_repository_branch():
    """The dispatch is what was missing; the helper alone would not be reached."""
    gateway = _gateway(MIX, FILES)
    gateway.search_entities_by_terms.return_value = [
        {
            "term": "EstateX",
            "id": "repo_estatex",
            "label": "Repository",
            "name": "EstateX",
            "quality": 0,
        }
    ]
    svc = _service(gateway)

    package = svc.retrieve("What is the tech stack of EstateX", None)

    assert package is not None, "a repository must not fall through to a file id"
    assert package["intent"] == "file"


def test_a_file_question_still_goes_to_the_file_branch():
    gateway = MagicMock()
    gateway.get_file_description.return_value = {
        "path": "backend/app/main.py",
        "name": "main.py",
        "language": "Python",
        "summary": "Entry point.",
        "docs_source": "authored",
        "docs_at_sha": "abc123",
        "repository_id": "repo_estatex",
    }

    package = _service(gateway).retrieve_file("repo_estatex::backend/app/main.py")

    assert package is not None
    assert package["intent"] == "file"