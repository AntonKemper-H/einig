"""Project-wide test setup: tests never reach the network (specs/c2b-place-cards.md).

This file is in the project root, not in tests/, because the files in tests/
are frozen after review. pytest loads it for every test.
"""

import pytest
import requests


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Make every real HTTP request fail as if there were no network.

    Tests that fake Google replace requests.get / requests.post directly, so their
    fakes still work. Any other request (e.g. a page that loads place details in a
    test that only faked the search) gets a ConnectionError, which the app already
    handles like "Google is unreachable".
    """

    def refuse(*args, **kwargs):
        raise requests.ConnectionError("Tests never call the network (see conftest.py).")

    monkeypatch.setattr(requests.Session, "request", refuse)
