"""企业资产目录 Mock 服务。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .common import FailureConfig, MockServiceBase


class AssetService(MockServiceBase):
    def __init__(
        self,
        records: dict[str, dict[str, Any]] | None = None,
        failure: FailureConfig | None = None,
    ) -> None:
        super().__init__(failure)
        self._records = deepcopy(records or {})

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        self._before_call()
        record = self._records.get(asset_id)
        return deepcopy(record) if record is not None else None
