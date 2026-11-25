"""VisionValueBench reference evaluation package (SAE + IAE, v2.1 protocol)."""

from .dimensions import DIMENSIONS
from .runner import Runner, StageError, load_config, load_manifest

__all__ = ["DIMENSIONS", "Runner", "StageError", "load_config", "load_manifest"]