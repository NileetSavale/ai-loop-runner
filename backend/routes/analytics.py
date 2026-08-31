import json
from collections import Counter
from functools import wraps
from fastapi import APIRouter
from sqlmodel import select

from fastapi import Depends
from models import Session, UsageEvent
from database import get_session as db_session
from cache import redis
from auth import get_current_user, user_id

router = APIRouter()

CACHE_TTL = 60  # seconds


def cached(key: str, ttl: int = CACHE_TTL):
    """Cache the return value of an async or sync endpoint in Redis."""
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            hit = await redis.get(key)
            if hit:
                return json.loads(hit)
            result = fn(*args, **kwargs)
            await redis.setex(key, ttl, json.dumps(result))
            return result
        return wrapper
    return decorator


async def invalidate_analytics():
    """Call this when new session data arrives."""
    keys = ["analytics:summary", "analytics:cost", "analytics:distribution",
            "analytics:success", "analytics:top"]
    await redis.delete(*keys)


@router.get("/analytics/summary")
@cached("analytics:summary")
def summary():
    with db_session() as db:
        sessions = db.exec(select(Session)).all()
        if not sessions:
            return {
                "total_sessions": 0, "total_passed": 0, "success_rate": 0,
                "avg_iterations_to_pass": 0, "total_cost_usd": 0,
                "total_tokens": 0, "avg_cost_per_session": 0,
                "correction_tax_avg_iterations": 0,
            }
        total = len(sessions)
        passed = [s for s in sessions if s.status == "passed"]
        total_cost = sum(s.total_cost_usd for s in sessions)
        passed_iters = [s.total_iterations for s in passed]
        avg_iters = sum(passed_iters) / len(passed_iters) if passed_iters else 0
        return {
            "total_sessions": total,
            "total_passed": len(passed),
            "success_rate": round(len(passed) / total, 4),
            "avg_iterations_to_pass": round(avg_iters, 2),
            "total_cost_usd": round(total_cost, 4),
            "total_tokens": sum(s.total_tokens for s in sessions),
            "avg_cost_per_session": round(total_cost / total, 4),
            "correction_tax_avg_iterations": round(max(0, avg_iters - 1), 2),
        }


@router.get("/analytics/cost-over-time")
@cached("analytics:cost")
def cost_over_time():
    with db_session() as db:
        sessions = db.exec(select(Session)).all()
    by_date: dict[str, float] = {}
    for s in sessions:
        day = s.created_at.strftime("%Y-%m-%d")
        by_date[day] = round(by_date.get(day, 0) + s.total_cost_usd, 4)
    return [{"date": k, "cost_usd": v} for k, v in sorted(by_date.items())]


@router.get("/analytics/iteration-distribution")
@cached("analytics:distribution")
def iteration_distribution():
    with db_session() as db:
        sessions = db.exec(select(Session)).all()
    counts = Counter(s.total_iterations for s in sessions)
    return [{"iterations": k, "count": v} for k, v in sorted(counts.items())]


@router.get("/analytics/success-rate")
@cached("analytics:success")
def success_rate():
    with db_session() as db:
        sessions = db.exec(select(Session)).all()
    counts = Counter(s.status for s in sessions)
    return {"passed": counts.get("passed", 0), "failed": counts.get("failed", 0), "stopped": counts.get("stopped", 0)}


@router.get("/analytics/top-tasks")
@cached("analytics:top")
def top_tasks():
    with db_session() as db:
        sessions = db.exec(select(Session).order_by(Session.total_cost_usd.desc()).limit(10)).all()
    return [{"name": s.name, "total_cost_usd": s.total_cost_usd, "total_tokens": s.total_tokens, "id": s.id} for s in sessions]


@router.get("/analytics/usage")
def usage_events(limit: int = 100, user: dict = Depends(get_current_user)):
    """Per-user usage ledger — for billing display and audit trail."""
    uid = user_id(user)
    with db_session() as db:
        events = db.exec(
            select(UsageEvent)
            .where(UsageEvent.user_id == uid)
            .order_by(UsageEvent.created_at.desc())
            .limit(min(limit, 1000))
        ).all()
    return [
        {
            "id": e.id,
            "session_id": e.session_id,
            "provider": e.provider,
            "model": e.model,
            "input_tokens": e.input_tokens,
            "output_tokens": e.output_tokens,
            "cost_usd": e.cost_usd,
            "byok": e.byok,
            "created_at": e.created_at,
        }
        for e in events
    ]
