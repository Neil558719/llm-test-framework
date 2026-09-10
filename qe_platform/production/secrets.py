from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping


@dataclass(frozen=True, repr=False)
class SecretSource:
    """Reads secrets without retaining their values in diagnostic output."""

    _environ: Mapping[str, str] = field(repr=False)
    _environ_getter: Callable[[str], str | None] | None = field(default=None, repr=False)

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
        environ_getter: Callable[[str], str | None] | None = None,
    ) -> "SecretSource":
        return cls(environ, environ_getter)

    def __repr__(self) -> str:
        return "SecretSource(configured_names=%r)" % sorted(
            name for name in self._environ if name.endswith(("_SECRET", "_TOKEN", "_KEY"))
        )

    def get(self, name: str, default: str = "") -> str:
        """Return a direct value, or a Docker secret when the direct value is blank.

        ``<NAME>_FILE`` permits explicit local testing and deployments.  Without
        it, Docker's conventional ``/run/secrets/<lowercase-name>`` location is
        consulted only when it exists.  Error messages deliberately contain the
        variable name and never secret material or filesystem contents.
        """
        value = self._value(name)
        if isinstance(value, str) and value:
            return value
        file_name = self._value("%s_FILE" % name)
        candidate = Path(file_name) if isinstance(file_name, str) and file_name else Path("/run/secrets") / name.lower()
        try:
            if candidate.is_file():
                content = candidate.read_text(encoding="utf-8")
                if content.endswith("\r\n"):
                    return content[:-2]
                return content[:-1] if content.endswith("\n") else content
        except (OSError, UnicodeError) as exc:
            raise ValueError("%s secret file could not be read" % name) from exc
        return default

    def require(self, name: str) -> str:
        value = self.get(name)
        if not value:
            raise ValueError("%s must be configured" % name)
        return value

    def _value(self, name: str) -> str | None:
        value = self._environ.get(name)
        if value is None and self._environ_getter is not None:
            value = self._environ_getter(name)
        return value if isinstance(value, str) else None
