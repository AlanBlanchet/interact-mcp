import os

import pytest


def pytest_collection_modifyitems(config, items):
    if not os.environ.get("OPENAI_API_KEY"):
        skip = pytest.mark.skip(reason="No OPENAI_API_KEY set")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
