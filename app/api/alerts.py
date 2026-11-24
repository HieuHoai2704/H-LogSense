"""Scoped incidents with append-only application audit history and role checks."""

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from app.domain import Alert, AlertAudit, AlertRule, User, UserDataset
from app.extensions import db
from app.i18n import translate
from app.models import Detector
from app.security import require_dataset, roles
from app.services.investigation import QueryError, integer
from app.services.redaction import redact

alerts_api = Blueprint("alerts", __name__)


@alerts_api.errorhandler(QueryError)
def invalid(error):
    return jsonify(error={"code": "invalid_query", "message": translate(str(error))}), 400


@alerts_api.post("/api/v1/alert-rules")
@roles("staff", "admin")
def create_rule():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise QueryError("JSON object required.")
    dataset = integer(data.get("dataset_id"), 1, 2**63 - 1, "Dataset")
    require_dataset(dataset)
    name = data.get("name")
    priority = data.get("min_priority", "High")
    host = data.get("host")
    detector = data.get("detector_id")
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 100
        or not isinstance(priority, str)
        or priority not in {"Low", "Medium", "High", "Critical"}
    ):
        raise QueryError("Valid name and priority required.")
    if host is not None and (not isinstance(host, str) or len(host) > 128):
        raise QueryError("Invalid host.")
    if detector is not None:
        detector = integer(detector, 1, 2**63 - 1, "Detector")
        if db.session.get(Detector, detector) is None:
            raise QueryError("Detector not found.")
    rule = AlertRule(
        dataset_id=dataset,
        name=name,
        min_priority=priority,
        host=host,
        detector_id=detector,
        cooldown_seconds=integer(data.get("cooldown_seconds", 300), 0, 86400, "Cooldown"),
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify(rule_id=rule.id), 201


@alerts_api.get("/api/v1/alerts")
@roles("staff", "admin")
def list_alerts():
    dataset = integer(request.args.get("dataset_id"), 1, 2**63 - 1, "Dataset")
    require_dataset(dataset)
    before = integer(request.args.get("before_id", 2**63 - 1), 1, 2**63 - 1, "Cursor")
    limit = integer(request.args.get("limit", 50), 1, 100, "Page size")
    rows = list(
        db.session.scalars(
            select(Alert)
            .where(Alert.dataset_id == dataset, Alert.id < before)
            .order_by(Alert.id.desc())
            .limit(limit + 1)
        )
    )
    return jsonify(
        items=[
            dict(
                id=a.id,
                anomaly_id=a.anomaly_id,
                run_id=a.run_id,
                status=a.status,
                assigned_to=a.assigned_to,
                evidence_url=f"/api/v1/database/anomalies/{a.anomaly_id}/evidence?dataset_id={dataset}",
            )
            for a in rows[:limit]
        ],
        next_before_id=rows[limit - 1].id if len(rows) > limit else None,
    )


@alerts_api.route("/api/v1/alerts/<int:alert_id>", methods=["GET", "PATCH"])
@roles("staff", "admin")
def alert_detail(alert_id):
    alert = db.session.scalar(select(Alert).where(Alert.id == alert_id).with_for_update())
    if alert is None:
        return jsonify(error={"code": "not_found"}), 404
    require_dataset(alert.dataset_id)
    if request.method == "PATCH":
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            raise QueryError("JSON object required.")
        if set(data) - {"status", "assigned_to", "note"}:
            raise QueryError("Unknown incident change.")
        changes = {}
        if "status" in data:
            target = data["status"]
            if not isinstance(target, str):
                raise QueryError("Unknown incident change.")
            allowed = {
                "open": {"acknowledged"},
                "acknowledged": {"investigating", "resolved"},
                "investigating": {"acknowledged", "resolved"},
                "resolved": {"open"},
            }
            if target != alert.status and (target not in allowed[alert.status]):
                return jsonify(error={"code": "invalid_transition"}), 409
            changes["status"] = {"old": alert.status, "new": target}
            alert.status = target
            if target == "acknowledged":
                alert.acknowledged_by = g.user.id
        if "assigned_to" in data:
            user_id = integer(data["assigned_to"], 1, 2**63 - 1, "Assignee")
            user = db.session.get(User, user_id)
            granted = db.session.scalar(
                select(UserDataset.id).where(
                    UserDataset.user_id == user_id,
                    UserDataset.dataset_id == alert.dataset_id,
                )
            )
            if not user or not user.active or not granted:
                raise QueryError("Assignee must have dataset permission and an investigation role.")
            changes["assigned_to"] = {"old": alert.assigned_to, "new": user_id}
            alert.assigned_to = user_id
        if "note" in data:
            if not isinstance(data["note"], str) or not 1 <= len(data["note"]) <= 2000:
                raise QueryError("Note must be 1..2000 characters.")
            changes["note"] = redact(data["note"])
        if changes:
            db.session.add(
                AlertAudit(
                    dataset_id=alert.dataset_id,
                    alert_id=alert.id,
                    actor_id=g.user.id,
                    action="updated",
                    details=changes,
                )
            )
        db.session.commit()
    history = list(
        db.session.scalars(
            select(AlertAudit)
            .where(
                AlertAudit.dataset_id == alert.dataset_id,
                AlertAudit.alert_id == alert.id,
            )
            .order_by(AlertAudit.id.desc())
            .limit(100)
        )
    )
    return jsonify(
        id=alert.id,
        status=alert.status,
        assigned_to=alert.assigned_to,
        acknowledged_by=alert.acknowledged_by,
        anomaly_id=alert.anomaly_id,
        run_id=alert.run_id,
        history=[
            dict(
                id=h.id,
                actor_id=h.actor_id,
                action=h.action,
                details=h.details,
                timestamp=h.timestamp.isoformat(),
            )
            for h in history
        ],
        history_limit=100,
        evidence_url=f"/api/v1/database/anomalies/{alert.anomaly_id}/evidence?dataset_id={alert.dataset_id}",
    )
