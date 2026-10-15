import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detector import build_analyzer


@pytest.fixture(scope="session")
def lithuanian_analyzer():
    return build_analyzer("lithuanian")


@pytest.fixture(scope="session")
def default_analyzer():
    return build_analyzer("default")
