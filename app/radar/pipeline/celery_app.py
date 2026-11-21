"""Celery app: one queue per stage, so each stage scales separately (one worker Deployment per queue group in Helm).

No-loss settings (D-003, D-005):
* task_acks_late + task_reject_on_worker_lost: a message is acked only after the task finished; a killed worker
  means redelivery, never loss.
* every queue has a dead-letter exchange; a task that exhausted retries is rejected into `<queue>.dlq`
  (visible on the operator screen as a counter, re-playable with `radar replay-dlq`).
* tasks are idempotent by (raw_id, stage, content_hash), so redelivery is a no-op.
"""

from celery import Celery, signals
from kombu import Exchange, Queue

from radar.config import get_settings

STAGES = ["harvest", "normalize", "resolve_org", "dedup", "gate", "link", "extract", "maturity", "score"]
# Queues after Basal carry its priority (0-9); RabbitMQ serves higher first.
PRIORITY_QUEUES = {"link", "extract", "maturity", "score"}

settings = get_settings()
app = Celery("radar", broker=settings.broker_url, include=["radar.pipeline.tasks"])

dlx = Exchange("radar.dlx", type="direct", durable=True)
queues = []
for q in STAGES:
    queues.append(Queue(q, Exchange("radar", type="direct", durable=True), routing_key=q, durable=True,
                        queue_arguments={"x-dead-letter-exchange": "radar.dlx", "x-dead-letter-routing-key": q,
                                         **({"x-max-priority": 9} if q in PRIORITY_QUEUES else {})}))
    queues.append(Queue(f"{q}.dlq", dlx, routing_key=q, durable=True))

app.conf.update(
    task_queues=queues,
    task_default_exchange="radar",
    task_default_routing_key="normalize",
    task_default_queue="normalize",
    task_routes={f"radar.pipeline.tasks.{s}": {"queue": s, "routing_key": s} for s in STAGES},
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=False,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    task_always_eager=settings.eager,
    task_eager_propagates=True,
    broker_connection_retry_on_startup=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    timezone="Europe/Warsaw",
)


def beat_schedule() -> dict:
    """Scheduled pulls from sources.yaml (`schedule_s`). Evaluated when beat starts."""
    from radar.sources.registry import active_sources

    sched = {
        f"harvest-{s.id}": {"task": "radar.pipeline.tasks.harvest", "schedule": float(s.schedule_s), "args": (s.id,)}
        for s in active_sources().values()
        if s.mode == "pull" and s.schedule_s
    }
    # novelty, recipients and regional gaps depend on the whole collection: refresh all scores daily
    sched["reassess-daily"] = {"task": "radar.pipeline.tasks.reassess", "schedule": 86400.0,
                               "options": {"queue": "score", "routing_key": "score"}}
    sched["notify-watchlists-daily"] = {"task": "radar.pipeline.tasks.notify_watchlists", "schedule": 86400.0,
                                        "options": {"queue": "score", "routing_key": "score"}}
    return sched


@app.on_after_configure.connect
def _setup_beat(sender, **_):
    try:
        sender.conf.beat_schedule = beat_schedule()
    except Exception:  # a broken sources.yaml must not stop workers from starting
        import logging

        logging.getLogger(__name__).exception("could not build beat schedule")


@signals.setup_logging.connect
def _json_logs(**_):
    """Workers log JSON like the API (RADAR_LOG_FORMAT=json, default)."""
    from radar.observability import setup_logging

    setup_logging()
