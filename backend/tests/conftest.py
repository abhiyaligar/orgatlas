"""Shared test configuration.

Answer synthesis is disabled for the whole suite so no test depends on the
model provider being reachable, deterministic, or free. The synthesis paths
themselves are covered in test_answer_synthesis.py with a stubbed provider,
and a live check is available through the opt-in evaluation suite.
"""

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def disable_synthesis():
    """Keep every test offline and cost-free."""
    previous = settings.ASK_SYNTHESIS_ENABLED
    settings.ASK_SYNTHESIS_ENABLED = False
    yield
    settings.ASK_SYNTHESIS_ENABLED = previous
