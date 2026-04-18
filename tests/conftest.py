"""Shared test fixtures."""

import pytest

from gii.models.country import CountryPair


@pytest.fixture
def sample_pair():
    return CountryPair.create("USA", "CHN")
