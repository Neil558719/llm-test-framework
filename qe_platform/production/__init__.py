"""Production configuration primitives shared by platform components."""

from .secrets import SecretSource
from .settings import ProductionSettings

__all__ = ["ProductionSettings", "SecretSource"]
