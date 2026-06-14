"""Pluggable step runner registry.

A step is a dict with at least `id`, `name`, `type`. Built-in types:
- http: make an HTTP request
- email: send an email via SMTP integration
- slack: post a message to Slack
- ai: call the LLM provider
- transform: apply a JSON path / template transform
- condition: branch on a JSON path expression
- delay: wait N seconds (max 30)
- log: append a log line
- webhook: alias for http (POST)
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx
import jmespath  # type: ignore

from flowforge.core.config import get_settings
from flowforge.models.integration import Integration, IntegrationKind
from flowforge.services import llm

StepHandler = Callable[[Dict[str, Any], Dict[str, Any], "StepContext"], Awaitable[Dict[str, Any]]]


class StepContext:
    """Carries run-time data into step handlers."""

    def __init__(
        self,
        *,
        session: Any,
        run_id: str,
        workflow_id: str,
        owner_id: str,
        trigger_payload: Dict[str, Any],
    ) -> None:
        self.session = session
        self.run_id = run_id
        self.workflow_id = workflow_id
        self.owner_id = owner_id
        self.trigger_payload = trigger_payload or {}

    def find_integration(self, name: str) -> Optional[Integration]:
        if not name:
            return None
        return (
            self.session.query(Integration)
            .filter(Integration.owner_id == self.owner_id, Integration.name == name)
            .one_or_none()
        )


def _safe_eval(expr: str, context: Dict[str, Any]) -> Any:
    """Very small expression evaluator. Supports dotted paths, defaults,
    and simple ``${{ path }}`` interpolation. Not a full template
    language — but enough to thread state between steps.
    """
    pattern = re.compile(r"\$\{\{\s*([\w\.\-\[\]]+)\s*(?:\|\s*default\(([^)]+)\))?\s*\}\}")
    if expr is None:
        return None

    def _resolve(path: str) -> Any:
        # JMESPath supports dotted/bracket access; works for our nested dicts.
        try:
            return jmespath.search(path, context)
        except Exception:
            return None

    if isinstance(expr, str) and pattern.search(expr):
        def _sub(match: "re.Match[str]") -> str:
            path = match.group(1)
            default = match.group(2)
            value = _resolve(path)
            if value is None:
                if default is None:
                    return ""
                return default.strip().strip("'").strip('"')
            if isinstance(value, (dict, list)):
                return json.dumps(value, default=str)
            return str(value)

        return pattern.sub(_sub, expr)

    if isinstance(expr, str) and expr.strip().startswith("${{"):
        return _resolve(expr.strip().strip("${{}}").strip())

    return expr


# -----------------------------
# Step handlers
# -----------------------------


async def run_http(step: Dict[str, Any], state: Dict[str, Any], ctx: StepContext) -> Dict[str, Any]:
    cfg = step.get("config") or {}
    method = (cfg.get("method") or "GET").upper()
    url = _safe_eval(cfg.get("url", ""), state)
    headers = _safe_eval(cfg.get("headers") or {}, state) or {}
    body = _safe_eval(cfg.get("body"), state)
    params = _safe_eval(cfg.get("params") or {}, state) or {}
    timeout = float(cfg.get("timeout") or 30)

    integration_name = cfg.get("integration")
    if integration_name:
        integ = ctx.find_integration(integration_name)
        if integ and integ.kind == IntegrationKind.HTTP:
            base = (integ.config or {}).get("base_url")
            if base and not str(url).startswith("http"):
                url = base.rstrip("/") + "/" + str(url).lstrip("/")
            secret_headers = (integ.secret or {}).get("headers") or {}
            headers = {**secret_headers, **headers}

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, url, headers=headers, params=params, json=body if body is not None else None)
    text = resp.text[:4096] if resp.text else ""
    return {
        "status": resp.status_code,
        "headers": dict(resp.headers),
        "body_text": text,
        "json": _safe_json(resp),
    }


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None


async def run_email(step: Dict[str, Any], state: Dict[str, Any], ctx: StepContext) -> Dict[str, Any]:
    cfg = step.get("config") or {}
    integration_name = cfg.get("integration", "default")
    integ = ctx.find_integration(integration_name) or ctx.find_integration("default")
    to = _safe_eval(cfg.get("to", ""), state)
    subject = _safe_eval(cfg.get("subject", ""), state)
    body = _safe_eval(cfg.get("body", ""), state)
    if not to or not subject:
        return {"skipped": True, "reason": "missing to or subject"}
    settings = get_settings()
    if not settings.smtp_host and not (integ and (integ.config or {}).get("host")):
        # In dev without SMTP, log and return preview.
        return {
            "delivered": False,
            "preview": True,
            "to": to,
            "subject": subject,
            "body": body,
            "note": "SMTP not configured — message captured as preview.",
        }
    # Real delivery: aiosmtplib
    try:
        import aiosmtplib  # type: ignore

        smtp_host = (integ.config or {}).get("host") or settings.smtp_host
        smtp_port = (integ.config or {}).get("port") or settings.smtp_port
        smtp_user = (integ.secret or {}).get("user") or settings.smtp_user
        smtp_password = (integ.secret or {}).get("password") or settings.smtp_password
        smtp_from = (integ.config or {}).get("from") or settings.smtp_from
        message = f"From: {smtp_from}\nTo: {to}\nSubject: {subject}\n\n{body}"
        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=int(smtp_port),
            username=smtp_user or None,
            password=smtp_password or None,
        )
        return {"delivered": True, "to": to, "subject": subject}
    except Exception as exc:  # pragma: no cover
        return {"delivered": False, "error": str(exc)}


async def run_slack(step: Dict[str, Any], state: Dict[str, Any], ctx: StepContext) -> Dict[str, Any]:
    cfg = step.get("config") or {}
    text = _safe_eval(cfg.get("text", ""), state)
    if not text:
        return {"skipped": True, "reason": "missing text"}
    integration_name = cfg.get("integration", "default")
    integ = ctx.find_integration(integration_name)
    webhook = (integ.secret or {}).get("webhook_url") if integ else None
    if not webhook:
        settings = get_settings()
        webhook = settings.slack_webhook_url
    if not webhook:
        return {"delivered": False, "preview": True, "text": text, "note": "no slack webhook configured"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(webhook, json={"text": text})
    return {"delivered": resp.is_success, "status": resp.status_code}


async def run_ai(step: Dict[str, Any], state: Dict[str, Any], ctx: StepContext) -> Dict[str, Any]:
    cfg = step.get("config") or {}
    prompt = _safe_eval(cfg.get("prompt", ""), state)
    system = _safe_eval(cfg.get("system") or "", state) or ""
    temperature = float(cfg.get("temperature") or 0.2)
    model = cfg.get("model")
    provider = cfg.get("provider")
    if not prompt:
        return {"skipped": True, "reason": "empty prompt"}
    response = await asyncio.to_thread(
        llm.complete,
        str(prompt),
        system=str(system) if system else "",
        temperature=temperature,
        model=model,
        provider=provider,
    )
    return {
        "text": response.text,
        "model": response.model,
        "provider": response.provider,
        "usage": response.usage,
    }


async def run_transform(step: Dict[str, Any], state: Dict[str, Any], ctx: StepContext) -> Dict[str, Any]:
    cfg = step.get("config") or {}
    expr = cfg.get("expression")
    path = cfg.get("path")
    value = _safe_eval(expr, state) if expr is not None else None
    if path:
        # store under dotted path in state
        parts = path.split(".")
        cursor: Dict[str, Any] = state
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
    return {"value": value, "stored_at": path}


async def run_condition(step: Dict[str, Any], state: Dict[str, Any], ctx: StepContext) -> Dict[str, Any]:
    cfg = step.get("config") or {}
    left = _safe_eval(cfg.get("left"), state)
    op = (cfg.get("op") or "==").lower()
    right = _safe_eval(cfg.get("right"), state)
    result = _compare(left, op, right)
    if cfg.get("branch") and not result:
        return {"result": result, "skipped": True, "reason": f"condition {left!r} {op} {right!r} false"}
    return {"result": result, "left": left, "op": op, "right": right}


def _compare(left: Any, op: str, right: Any) -> bool:
    try:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == ">":
            return float(left) > float(right)
        if op == "<":
            return float(left) < float(right)
        if op == ">=":
            return float(left) >= float(right)
        if op == "<=":
            return float(left) <= float(right)
        if op == "contains":
            return str(right) in str(left)
        if op == "in":
            return left in (right or [])
    except (TypeError, ValueError):
        return False
    return False


async def run_delay(step: Dict[str, Any], state: Dict[str, Any], ctx: StepContext) -> Dict[str, Any]:
    cfg = step.get("config") or {}
    seconds = max(0, min(int(cfg.get("seconds") or 0), 30))
    await asyncio.sleep(seconds)
    return {"waited": seconds}


async def run_log(step: Dict[str, Any], state: Dict[str, Any], ctx: StepContext) -> Dict[str, Any]:
    cfg = step.get("config") or {}
    message = _safe_eval(cfg.get("message", ""), state)
    level = (cfg.get("level") or "info").lower()
    return {"message": message, "level": level}


HANDLERS: Dict[str, StepHandler] = {
    "http": run_http,
    "webhook": run_http,
    "email": run_email,
    "slack": run_slack,
    "ai": run_ai,
    "llm": run_ai,
    "transform": run_transform,
    "condition": run_condition,
    "delay": run_delay,
    "log": run_log,
}


def list_step_types() -> Dict[str, Any]:
    """Catalog of supported step types with config schema hints."""
    return {
        "types": [
            {
                "type": "http",
                "description": "Make an HTTP request. Supports template interpolation in url/headers/body.",
                "config": {
                    "method": "GET|POST|PUT|DELETE|PATCH",
                    "url": "string (supports ${{ ... }} interpolation)",
                    "headers": "object",
                    "params": "object",
                    "body": "object | string",
                    "timeout": "number (seconds)",
                    "integration": "optional name of an http integration",
                },
            },
            {
                "type": "ai",
                "description": "Call the LLM provider. Prompts support ${{ ... }} interpolation.",
                "config": {
                    "prompt": "string",
                    "system": "string (optional)",
                    "temperature": "0.0-1.0",
                    "model": "optional override",
                    "provider": "stub|openai|anthropic",
                },
            },
            {
                "type": "email",
                "description": "Send an email via SMTP. Falls back to preview if SMTP not configured.",
                "config": {"to": "string", "subject": "string", "body": "string", "integration": "optional"},
            },
            {
                "type": "slack",
                "description": "Post a message to Slack via incoming webhook.",
                "config": {"text": "string", "integration": "optional"},
            },
            {
                "type": "transform",
                "description": "Extract a value via JMESPath and optionally store at a path.",
                "config": {"expression": "string (jmespath)", "path": "optional dotted path to write into state"},
            },
            {
                "type": "condition",
                "description": "Compare two values; skip rest of workflow if false and branch=true.",
                "config": {
                    "left": "string (jmespath or literal)",
                    "op": "==|!=|>|<|>=|<=|contains|in",
                    "right": "string (jmespath or literal)",
                    "branch": "true|false",
                },
            },
            {
                "type": "delay",
                "description": "Pause for up to 30 seconds.",
                "config": {"seconds": "integer"},
            },
            {
                "type": "log",
                "description": "Record a log line in run output.",
                "config": {"message": "string", "level": "info|warn|error"},
            },
        ]
    }
