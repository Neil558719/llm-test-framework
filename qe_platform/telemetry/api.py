from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from qe_platform.feedback import FeedbackInput, FeedbackKind, FeedbackQuery
from qe_platform.storage import TelemetryRepository, create_telemetry_repository
from qe_platform.storage.telemetry import _hydrate_trace
from qe_platform.telemetry import TelemetryQuery, TelemetryTrace
from qe_platform.telemetry.settings import TelemetrySettings


def create_telemetry_app(
    settings: TelemetrySettings,
    repository: TelemetryRepository | None = None,
) -> FastAPI:
    repo = repository or create_telemetry_repository(
        settings.database,
        retention_days=settings.retention_days,
        hash_key=settings.hash_key,
    )
    app = FastAPI(title="QE Telemetry API")

    def unauthorized() -> None:
        raise HTTPException(status_code=401, detail="unauthorized")

    def bad_request() -> None:
        raise HTTPException(status_code=400, detail="invalid telemetry request")

    def require_token(token: str | None) -> None:
        if token is None or not hmac.compare_digest(token, settings.ingest_token):
            unauthorized()

    async def read_mapping(request: Request) -> Mapping[str, Any]:
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            bad_request()
        if not isinstance(payload, Mapping) or not all(isinstance(key, str) for key in payload):
            bad_request()
        return payload

    def trace_from_payload(payload: Mapping[str, Any]) -> TelemetryTrace:
        serialized = json.dumps(dict(payload), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        return _hydrate_trace(serialized)

    def parse_int(value: str, *, minimum: int, maximum: int | None = None) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            bad_request()
        if str(value).strip() != str(parsed) or parsed < minimum or (maximum is not None and parsed > maximum):
            bad_request()
        return parsed

    def parse_feedback_category(value: str) -> FeedbackKind | None:
        if not value:
            return None
        try:
            return FeedbackKind(value)
        except ValueError:
            bad_request()

    @app.get("/api/traces")
    def list_traces(
        application: str = "",
        trace_id: str = "",
        limit: str = "100",
        offset: str = "0",
    ) -> Response:
        try:
            query = TelemetryQuery(
                application=application,
                trace_id=trace_id,
                limit=parse_int(limit, minimum=1, maximum=100),
                offset=parse_int(offset, minimum=0),
            )
        except HTTPException:
            raise
        except ValueError:
            bad_request()
        try:
            return JSONResponse({"traces": [trace.as_dict() for trace in repo.list_traces(query, now=datetime.now(timezone.utc))]})
        except Exception:
            return Response(status_code=500)

    @app.get("/api/traces/{trace_id}")
    def get_trace(trace_id: str) -> Response:
        try:
            trace = repo.get_trace(trace_id, now=datetime.now(timezone.utc))
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return JSONResponse(trace.as_dict())

    @app.post("/api/traces")
    async def ingest_trace(
        request: Request,
        x_qe_telemetry_token: str | None = Header(default=None, alias="X-QE-Telemetry-Token"),
    ) -> Response:
        require_token(x_qe_telemetry_token)
        payload = await read_mapping(request)
        try:
            trace = trace_from_payload(payload)
            stored = repo.upsert_trace(trace)
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        return JSONResponse(stored.as_dict(), status_code=201)

    @app.post("/api/traces/{trace_id}/feedback")
    async def add_feedback(trace_id: str, request: Request) -> Response:
        payload = await read_mapping(request)
        if set(payload) != {"category", "reporter_id", "source"}:
            bad_request()
        if not all(isinstance(payload[key], str) for key in ("category", "reporter_id", "source")):
            bad_request()
        try:
            category = FeedbackKind(payload["category"])
            feedback = FeedbackInput(category, payload["reporter_id"], payload["source"])
            record = repo.add_feedback(feedback, trace_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="trace not found")
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        return JSONResponse(record.as_dict(), status_code=201)

    @app.get("/api/feedback")
    def list_feedback(
        trace_id: str = "",
        category: str = "",
        limit: str = "100",
        offset: str = "0",
    ) -> Response:
        try:
            query = FeedbackQuery(
                trace_id=trace_id,
                category=parse_feedback_category(category),
                limit=parse_int(limit, minimum=1, maximum=100),
                offset=parse_int(offset, minimum=0),
            )
        except HTTPException:
            raise
        except ValueError:
            bad_request()
        try:
            return JSONResponse({"feedback": [record.as_dict() for record in repo.list_feedback(query, now=datetime.now(timezone.utc))]})
        except Exception:
            return Response(status_code=500)

    return app
