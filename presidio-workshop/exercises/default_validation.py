"""Intentionally failing workshop test; its filename avoids automatic collection."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detector import build_analyzer
from validation import assert_case, load_examples


@pytest.fixture(scope="module")
def default_analyzer():
    return build_analyzer("default")


@pytest.mark.parametrize("case", load_examples(), ids=lambda case: case["id"])
def test_default_detection_and_redaction(default_analyzer, case):
    assert_case(default_analyzer, case)
