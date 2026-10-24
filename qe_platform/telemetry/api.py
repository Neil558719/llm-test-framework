from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from qe_platform.auth.dependencies import AuthRuntime
from qe_platform.auth.access import ApplicationAccessPolicy
from qe_platform.auth.models import AuthenticatedPrincipal
from qe_platform.ops import readiness
from qe_platform.ops.metrics import PROCESS_METRICS, install_http_metrics
from qe_platform.feedback import FeedbackInput, FeedbackKind, FeedbackQuery, ReviewAttribution, ReviewPriority, ReviewStatus, promote_review
from qe_platform.quality_loop.engine import build_quality_links, build_trends, validate_release
from qe_platform.quality_loop.models import ReleaseGatePolicy
from qe_platform.quality_loop.storage import SQLiteQualityRepository
from qe_platform.storage import TelemetryRepository, create_telemetry_repository
from qe_platform.storage.telemetry import _hydrate_trace
from qe_platform.telemetry import TelemetryQuery, TelemetryTrace
from qe_platform.telemetry.settings import TelemetrySettings


def create_telemetry_app(
    settings: TelemetrySettings,
    repository: TelemetryRepository | None = None,
    quality_repository: SQLiteQualityRepository | None = None,
    *,
    auth_runtime: AuthRuntime | None = None,
    access_policy: ApplicationAccessPolicy | None = None,
) -> FastAPI:
    repo = repository or create_telemetry_repository(
        settings.database,
        retention_days=settings.retention_days,
        hash_key=settings.hash_key,
    )
    quality_repo = quality_repository or SQLiteQualityRepository(
        settings.database,
        retention_days=settings.retention_days,
    )
    auth = auth_runtime or AuthRuntime.from_environment()
    access = access_policy if access_policy is not None else (
        ApplicationAccessPolicy({}) if auth.development_mode else ApplicationAccessPolicy.from_environment()
    )
    app = FastAPI(title="QE Telemetry API")
    app.state.metrics = PROCESS_METRICS
    install_http_metrics(app, "telemetry")

    def unauthorized() -> None:
        raise HTTPException(status_code=401, detail="unauthorized")

    def bad_request() -> None:
        raise HTTPException(status_code=400, detail="invalid telemetry request")

    def require_token(token: str | None) -> None:
        if token is None or not hmac.compare_digest(token, settings.ingest_token):
            unauthorized()

    def require_human(request: Request, role: str) -> AuthenticatedPrincipal:
        principal = auth.require(request, role)
        auth.require_csrf(request)
        return principal

    def bind_actor(payload: Mapping[str, Any], field: str, principal: AuthenticatedPrincipal) -> Mapping[str, Any]:
        if auth.development_mode:
            return payload
        if field in payload and payload[field] != principal.subject:
            bad_request()
        return {**payload, field: principal.subject}

    def principal_scope(principal: AuthenticatedPrincipal) -> frozenset[str] | None:
        if auth.development_mode:
            return None
        apps = access.allowed_applications(principal)
        if not apps:
            raise HTTPException(status_code=403, detail="forbidden")
        return apps

    def read_scope(request: Request, application: str = "") -> frozenset[str] | None:
        principal = auth.require_business_read(request)
        apps = principal_scope(principal)
        if application and apps is not None:
            access.require_application(principal, application)
        return apps

    def check_application(application: str, apps: frozenset[str] | None, *, hidden: bool = False) -> None:
        if apps is not None and not isinstance(application, str):
            bad_request()
        if apps is not None and application not in apps:
            raise HTTPException(status_code=404 if hidden else 403, detail="not found" if hidden else "forbidden")

    def scoped_record(loader, identifier: str, apps: frozenset[str]):
        try:
            record = loader(identifier)
        except ValueError:
            bad_request()
        except Exception:
            raise HTTPException(status_code=500, detail="internal error") from None
        if record is None:
            raise HTTPException(status_code=404, detail="not found")
        if hasattr(record, "application"):
            check_application(record.application, apps, hidden=True)
        else:
            scoped_record(repo.get_trace, record.trace_id, apps)
        return record

    def validation_scope(value, apps: frozenset[str]) -> None:
        if value.scope_policy_version != 1 or value.scope_application not in apps:
            raise HTTPException(status_code=404, detail="not found")
        baseline = scoped_record(quality_repo.get_run, value.baseline_run_id, apps)
        candidate = scoped_record(quality_repo.get_run, value.candidate_run_id, apps)
        if value.scope_application != candidate.application or baseline.application != candidate.application or (
            value.policy.application and value.policy.application != candidate.application
        ):
            raise HTTPException(status_code=404, detail="not found")

    def require_machine_or_human(request: Request, token: str | None, role: str) -> frozenset[str] | None:
        if token is not None and hmac.compare_digest(token, settings.ingest_token):
            if auth.development_mode:
                return None
            if not settings.allowed_applications:
                raise HTTPException(status_code=403, detail="forbidden")
            return settings.allowed_applications
        if auth.development_mode:
            require_token(token)
        return principal_scope(require_human(request, role))

    @app.get("/api/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "service": "qe-telemetry"}

    @app.get("/api/health/ready")
    def health_ready() -> Response:
        result = readiness({
            "configuration": lambda: bool(settings.database and settings.hash_key and settings.ingest_token),
            "telemetry": repo,
            "quality": quality_repo,
            **auth.readiness_bundle(),
        })
        payload = {"status": "ready" if result.ready else "not_ready", "service": "qe-telemetry", "checks": dict(result.checks)}
        return JSONResponse(payload, status_code=200 if result.ready else 503)

    @app.get("/api/metrics")
    def metrics(request: Request) -> Response:
        auth.require(request, "admin")
        return JSONResponse(app.state.metrics.snapshot())

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

    def parse_review_status(value: str) -> ReviewStatus:
        try:
            return ReviewStatus(value)
        except ValueError:
            bad_request()

    def parse_review_attribution(value: str) -> ReviewAttribution:
        try:
            return ReviewAttribution(value)
        except ValueError:
            bad_request()

    def parse_review_priority(value: str) -> ReviewPriority:
        try:
            return ReviewPriority(value)
        except ValueError:
            bad_request()

    def parse_datetime(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            bad_request()
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            bad_request()
        return parsed.astimezone(timezone.utc)

    def parse_float(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a number")
        return float(value)

    @app.get("/api/traces")
    def list_traces(
        request: Request,
        application: str = "",
        trace_id: str = "",
        limit: str = "100",
        offset: str = "0",
    ) -> Response:
        apps = read_scope(request, application)
        if trace_id and apps is not None:
            scoped_record(repo.get_trace, trace_id, apps)
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
            values = repo.list_traces(query) if apps is None else repo.list_traces(query, allowed_applications=apps)
            return JSONResponse({"traces": [trace.as_dict() for trace in values]})
        except Exception:
            return Response(status_code=500)

    @app.get("/api/traces/{trace_id}")
    def get_trace(trace_id: str, request: Request) -> Response:
        apps = read_scope(request)
        try:
            trace = repo.get_trace(trace_id)
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace not found")
        check_application(trace.application, apps, hidden=True)
        return JSONResponse(trace.as_dict())

    @app.post("/api/traces")
    async def ingest_trace(
        request: Request,
        x_qe_telemetry_token: str | None = Header(default=None, alias="X-QE-Telemetry-Token"),
    ) -> Response:
        require_token(x_qe_telemetry_token)
        apps = None if auth.development_mode else settings.allowed_applications
        if apps is not None and not apps:
            raise HTTPException(status_code=403, detail="forbidden")
        payload = await read_mapping(request)
        if apps is not None:
            check_application(payload.get("application", ""), apps)
        try:
            trace = trace_from_payload(payload)
            stored = repo.upsert_trace(trace) if apps is None else repo.upsert_trace(trace, allowed_applications=apps)
        except KeyError:
            raise HTTPException(status_code=404, detail="not found")
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        return JSONResponse(stored.as_dict(), status_code=201)

    @app.post("/api/traces/{trace_id}/feedback")
    async def add_feedback(trace_id: str, request: Request) -> Response:
        principal = require_human(request, "viewer")
        apps = principal_scope(principal)
        if apps is not None:
            scoped_record(repo.get_trace, trace_id, apps)
        payload = bind_actor(await read_mapping(request), "reporter_id", principal)
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
        request: Request,
        trace_id: str = "",
        category: str = "",
        limit: str = "100",
        offset: str = "0",
    ) -> Response:
        apps = read_scope(request)
        if trace_id and apps is not None:
            scoped_record(repo.get_trace, trace_id, apps)
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
            values = repo.list_feedback(query) if apps is None else repo.list_feedback(query, allowed_applications=apps)
            return JSONResponse({"feedback": [record.as_dict() for record in values]})
        except Exception:
            return Response(status_code=500)

    @app.post("/api/feedback/{feedback_id}/review")
    async def add_review(feedback_id: str, request: Request) -> Response:
        principal = require_human(request, "reviewer")
        apps = principal_scope(principal)
        if apps is not None:
            scoped_record(repo.get_feedback, feedback_id, apps)
        payload = bind_actor(await read_mapping(request), "reviewer_id", principal)
        if set(payload) != {"reviewer_id", "status", "attribution", "priority"}:
            bad_request()
        if not all(isinstance(payload[key], str) for key in payload):
            bad_request()
        try:
            existing = repo.list_reviews(feedback_id=feedback_id)
            review = repo.upsert_review(
                feedback_id,
                payload["reviewer_id"],
                parse_review_status(payload["status"]),
                parse_review_attribution(payload["attribution"]),
                parse_review_priority(payload["priority"]),
            )
        except HTTPException:
            raise
        except KeyError:
            raise HTTPException(status_code=404, detail="feedback not found")
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        return JSONResponse(review.as_dict(), status_code=200 if existing else 201)

    @app.get("/api/reviews")
    def list_reviews(
        request: Request,
        feedback_id: str = "",
        trace_id: str = "",
        status: str = "",
        limit: str = "100",
        offset: str = "0",
    ) -> Response:
        apps = read_scope(request)
        if apps is not None:
            if feedback_id:
                scoped_record(repo.get_feedback, feedback_id, apps)
            if trace_id:
                scoped_record(repo.get_trace, trace_id, apps)
        try:
            reviews = repo.list_reviews(
                feedback_id=feedback_id,
                trace_id=trace_id,
                status=parse_review_status(status) if status else None,
                limit=parse_int(limit, minimum=1, maximum=100),
                offset=parse_int(offset, minimum=0),
                **({"allowed_applications": apps} if apps is not None else {}),
            )
        except HTTPException:
            raise
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        return JSONResponse({"reviews": [review.as_dict() for review in reviews]})

    @app.get("/api/reviews/{review_id}")
    def get_review(review_id: str, request: Request) -> Response:
        apps = read_scope(request)
        try:
            review = repo.get_review(review_id)
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        if review is None:
            raise HTTPException(status_code=404, detail="review not found")
        if apps is not None:
            scoped_record(repo.get_trace, review.trace_id, apps)
        payload = review.as_dict()
        try:
            promotion = repo.get_promotion_for_review(review.review_id)
        except Exception:
            return Response(status_code=500)
        if promotion is not None:
            payload["promotion_id"] = promotion.promotion_id
            payload["scenario_id"] = promotion.scenario_id
        return JSONResponse(payload)

    @app.post("/api/reviews/{review_id}/promote")
    async def promote(review_id: str, request: Request) -> Response:
        apps = principal_scope(require_human(request, "releaser"))
        if apps is not None:
            scoped_record(repo.get_review, review_id, apps)
        payload = await read_mapping(request)
        if set(payload) != {"scenario"} or not isinstance(payload["scenario"], Mapping):
            bad_request()
        try:
            review = repo.get_review(review_id)
            if review is None:
                raise HTTPException(status_code=404, detail="review not found")
            feedback = repo.get_feedback(review.feedback_id)
            if feedback is None:
                raise HTTPException(status_code=404, detail="feedback not found")
            generated = promote_review(review, feedback, payload["scenario"])
            stored = repo.create_promotion(
                review.review_id,
                generated.scenario_id,
                generated.scenario_yaml,
                promotion_id=generated.promotion_id,
            )
        except HTTPException:
            raise
        except (KeyError, ValueError):
            bad_request()
        except Exception:
            return Response(status_code=500)
        return JSONResponse(stored.as_dict(), status_code=201 if stored.promotion_id == generated.promotion_id else 200)

    @app.get("/api/promotions/{promotion_id}")
    def get_promotion(promotion_id: str, request: Request) -> Response:
        apps = read_scope(request)
        try:
            promotion = repo.get_promotion(promotion_id)
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        if promotion is None:
            raise HTTPException(status_code=404, detail="promotion not found")
        if apps is not None:
            scoped_record(repo.get_trace, promotion.trace_id, apps)
        return JSONResponse(promotion.as_dict())

    @app.get("/api/quality/trends")
    def quality_trends(
        request: Request,
        application: str = "",
        version: str = "",
        from_timestamp: str = Query(default="", alias="from"),
        to_timestamp: str = Query(default="", alias="to"),
    ) -> Response:
        apps = read_scope(request, application)
        try:
            start = parse_datetime(from_timestamp) if from_timestamp else None
            end = parse_datetime(to_timestamp) if to_timestamp else None
            trend_apps = frozenset({application}) if application and apps is not None else apps
            points = build_trends(quality_repo, application=application, version=version, start=start, end=end, allowed_applications=trend_apps)
            links = build_quality_links(quality_repo, allowed_applications=trend_apps)
        except HTTPException:
            raise
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        return JSONResponse({"trends": [item.as_dict() for item in points], "links": [item.as_dict() for item in links]})

    @app.get("/api/quality/links")
    def quality_links(request: Request, offline_run_id: str = "", promotion_id: str = "") -> Response:
        apps = read_scope(request)
        if apps is not None:
            if offline_run_id:
                scoped_record(quality_repo.get_run, offline_run_id, apps)
            if promotion_id:
                scoped_record(repo.get_promotion, promotion_id, apps)
        try:
            values = build_quality_links(quality_repo, offline_run_id=offline_run_id, promotion_id=promotion_id, allowed_applications=apps)
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        return JSONResponse({"links": [item.as_dict() for item in values]})

    @app.post("/api/quality/offline-runs")
    async def import_quality_run(
        request: Request,
        x_qe_telemetry_token: str | None = Header(default=None, alias="X-QE-Telemetry-Token"),
    ) -> Response:
        apps = require_machine_or_human(request, x_qe_telemetry_token, "releaser")
        payload = dict(await read_mapping(request))
        if apps is not None:
            check_application(payload.get("application", ""), apps)
            run_id = payload.get("run_id")
            if isinstance(run_id, str) and run_id and quality_repo.get_run(run_id) is not None:
                scoped_record(quality_repo.get_run, run_id, apps)
        source_label = payload.pop("source_label", "api-report")
        if not isinstance(source_label, str):
            bad_request()
        try:
            existing = quality_repo.get_run(payload.get("run_id", "")) if isinstance(payload.get("run_id"), str) else None
            run = quality_repo.import_run(payload, source_label=source_label, allowed_applications=apps)
        except KeyError:
            raise HTTPException(status_code=404, detail="not found")
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        return JSONResponse(run.as_dict(), status_code=200 if existing is not None else 201)

    @app.post("/api/quality/links")
    async def create_quality_link(
        request: Request,
        x_qe_telemetry_token: str | None = Header(default=None, alias="X-QE-Telemetry-Token"),
    ) -> Response:
        apps = require_machine_or_human(request, x_qe_telemetry_token, "releaser")
        payload = await read_mapping(request)
        if set(payload) - {"promotion_id", "offline_run_id", "scenario_id"} or not {"promotion_id", "offline_run_id"} <= set(payload):
            bad_request()
        if not all(isinstance(payload[key], str) for key in ("promotion_id", "offline_run_id")):
            bad_request()
        if "scenario_id" in payload and not isinstance(payload["scenario_id"], str):
            bad_request()
        if apps is not None:
            promotion = scoped_record(repo.get_promotion, payload["promotion_id"], apps)
            trace = scoped_record(repo.get_trace, promotion.trace_id, apps)
            run = scoped_record(quality_repo.get_run, payload["offline_run_id"], apps)
            if trace.application != run.application:
                bad_request()
        try:
            existing = quality_repo.list_links(
                promotion_id=payload["promotion_id"],
                offline_run_id=payload["offline_run_id"],
            )
            link = quality_repo.create_link(
                payload["promotion_id"],
                payload["offline_run_id"],
                scenario_id=payload.get("scenario_id"),
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="quality link source not found")
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        return JSONResponse(link.as_dict(), status_code=200 if existing else 201)

    @app.post("/api/quality/release-validations")
    async def create_quality_validation(
        request: Request,
        x_qe_telemetry_token: str | None = Header(default=None, alias="X-QE-Telemetry-Token"),
    ) -> Response:
        apps = require_machine_or_human(request, x_qe_telemetry_token, "releaser")
        payload = await read_mapping(request)
        allowed = {
            "baseline_run_id", "candidate_run_id", "validation_id", "max_candidate_failure_rate",
            "max_pass_rate_drop", "max_low_quality_rate_increase", "require_complete",
            "application", "release_id",
        }
        if set(payload) - allowed or not {"baseline_run_id", "candidate_run_id"} <= set(payload):
            bad_request()
        if not all(isinstance(payload[key], str) and payload[key] for key in ("baseline_run_id", "candidate_run_id")):
            bad_request()
        if apps is not None:
            baseline = scoped_record(quality_repo.get_run, payload["baseline_run_id"], apps)
            candidate = scoped_record(quality_repo.get_run, payload["candidate_run_id"], apps)
            if baseline.application != candidate.application:
                bad_request()
            application = payload.get("application", "")
            if not isinstance(application, str):
                bad_request()
            if application:
                check_application(application, apps)
                if application != candidate.application:
                    bad_request()
            validation_id = payload.get("validation_id")
            if isinstance(validation_id, str) and validation_id:
                try:
                    existing_validation = quality_repo.get_validation(validation_id)
                except (ValueError, TypeError, KeyError):
                    raise HTTPException(status_code=404, detail="not found") from None
                if existing_validation is not None:
                    validation_scope(existing_validation, apps)
            apps = frozenset({candidate.application})
        try:
            policy = ReleaseGatePolicy(
                max_candidate_failure_rate=parse_float(payload.get("max_candidate_failure_rate", 0.0), "max_candidate_failure_rate"),
                max_pass_rate_drop=parse_float(payload.get("max_pass_rate_drop", 0.0), "max_pass_rate_drop"),
                max_low_quality_rate_increase=parse_float(payload.get("max_low_quality_rate_increase", 0.0), "max_low_quality_rate_increase"),
                require_complete=payload.get("require_complete", True),
                application=payload.get("application", ""),
                release_id=payload.get("release_id", ""),
            )
            result = validate_release(
                quality_repo,
                payload["baseline_run_id"],
                payload["candidate_run_id"],
                policy,
                validation_id=payload.get("validation_id"),
                allowed_applications=apps,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="quality run not found")
        except ValueError:
            bad_request()
        except Exception:
            return Response(status_code=500)
        if not result.passed:
            return JSONResponse(result.as_dict(), status_code=422)
        return JSONResponse(result.as_dict(), status_code=201)

    @app.get("/api/quality/release-validations/{validation_id}")
    def get_quality_validation(validation_id: str, request: Request) -> Response:
        apps = read_scope(request)
        try:
            value = quality_repo.get_validation(validation_id)
        except (ValueError, TypeError, KeyError) as error:
            if apps is not None:
                raise HTTPException(status_code=404, detail="not found") from None
            if isinstance(error, ValueError):
                bad_request()
            return Response(status_code=500)
        except Exception:
            return Response(status_code=500)
        if value is None:
            raise HTTPException(status_code=404, detail="quality validation not found")
        if apps is not None:
            validation_scope(value, apps)
        return JSONResponse(value.as_dict())

    return app
