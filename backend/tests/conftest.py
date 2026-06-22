import os
import pytest

# Force offline heuristic mode so tests are deterministic and never hit the API.
os.environ["DEMO_MODE"] = "true"
os.environ["GEMINI_API_KEY"] = ""


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
