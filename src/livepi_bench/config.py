from __future__ import annotations

import os


def default_image() -> str:
    return os.getenv("LIVEPI_IMAGE", "livepi-runner:cpu")


def default_network() -> str:
    return os.getenv("LIVEPI_DOCKER_NETWORK", "host")
