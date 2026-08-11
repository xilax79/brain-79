import logging
import os
from typing import Generator

import pytest


@pytest.fixture(autouse=True)
def clean_env() -> Generator[None, None, None]:
    """Purge environment variables related to FastMCP and Brain79 before each test."""
    to_delete = [
        k
        for k in os.environ
        if k.startswith("BRAIN79_") or k.startswith("FASTMCP_")
    ]
    saved = {k: os.environ[k] for k in to_delete}
    for k in to_delete:
        del os.environ[k]

    # Re-apply default FASTMCP banner suppression
    os.environ["FASTMCP_SHOW_SERVER_BANNER"] = "false"

    yield

    current = [
        k
        for k in os.environ
        if k.startswith("BRAIN79_") or k.startswith("FASTMCP_")
    ]
    for k in current:
        if k not in saved:
            del os.environ[k]
    for k, v in saved.items():
        os.environ[k] = v



@pytest.fixture(autouse=True)
def restore_logging() -> Generator[None, None, None]:
    """Restore logger levels for test independence."""
    fastmcp_logger = logging.getLogger("fastmcp")
    mcp_logger = logging.getLogger("mcp")

    orig_fastmcp_level = fastmcp_logger.level
    orig_mcp_level = mcp_logger.level

    yield

    fastmcp_logger.setLevel(orig_fastmcp_level)
    mcp_logger.setLevel(orig_mcp_level)
