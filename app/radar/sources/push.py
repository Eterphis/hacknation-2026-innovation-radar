"""Push transports. All of them decode bytes with `PushAdapter` and call `ingest()`; only the receive loop differs.

* webhook      — HTTP POST to /api/ingest/webhook/{source_id} (handled in radar.api), optional HMAC-SHA256.
* amqp         — RabbitMQ/AMQP queue (kombu). options: url, queue, exchange, routing_key, prefetch
* gcp_pubsub   — Google Cloud Pub/Sub pull subscription. options: subscription (projects/x/subscriptions/y)
* kafka        — Kafka topic. options: bootstrap_servers, topic, group_id

Consumers run as `radar consume <source_id>`; Helm creates one Deployment per enabled push source.
A message is acked only after ingest() committed it, so a crash means redelivery, and redelivery is a no-op
thanks to the (source_id, external_id, content_hash) key.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

from radar.sources.base import PushAdapter, SourceSpec

log = logging.getLogger(__name__)


def webhook_secret(source_id: str) -> str | None:
    return os.environ.get("RADAR_WEBHOOK_SECRET_" + source_id.upper().replace("-", "_"))


def verify_signature(source_id: str, body: bytes, signature: str | None) -> bool:
    """GitHub-style `X-Radar-Signature: sha256=<hex>`. No secret configured = open endpoint (dev only)."""
    secret = webhook_secret(source_id)
    if not secret:
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


def _handle(spec: SourceSpec, body: bytes, via: str, headers: dict | None = None) -> int:
    from radar.ingest import ingest_many

    envelopes = PushAdapter(spec, via).parse(body, headers)
    return ingest_many(envelopes)["accepted"]


def consume_amqp(spec: SourceSpec) -> None:
    from kombu import Connection, Exchange, Queue

    url = spec.opt("url") or os.environ.get("RADAR_BROKER_URL")
    exchange = Exchange(spec.opt("exchange", spec.id), type=spec.opt("exchange_type", "topic"), durable=True)
    dlx = Exchange(f"{spec.id}.dlx", type="fanout", durable=True)
    queue = Queue(
        spec.opt("queue", f"ingest.{spec.id}"),
        exchange,
        routing_key=spec.opt("routing_key", "#"),
        durable=True,
        queue_arguments={"x-dead-letter-exchange": f"{spec.id}.dlx"},
    )
    dlq = Queue(f"ingest.{spec.id}.dlq", dlx, durable=True)

    def on_message(body, message):
        if isinstance(body, bytes):
            raw = body
        elif isinstance(body, str):
            raw = body.encode()
        else:  # kombu already decoded JSON
            raw = json.dumps(body).encode()
        try:
            n = _handle(spec, raw, "pubsub", dict(message.headers or {}))
            message.ack()
            log.info("amqp %s: ingested %d", spec.id, n)
        except Exception:
            log.exception("amqp %s: rejecting message to DLQ", spec.id)
            message.reject(requeue=False)

    with Connection(url) as conn:
        dlq(conn.default_channel).declare()
        with conn.Consumer(queue, callbacks=[on_message], accept=["json", "text/plain", "application/data"],
                           prefetch_count=int(spec.opt("prefetch", 10))):
            log.info("amqp %s: consuming %s", spec.id, queue.name)
            while True:
                conn.drain_events()


def consume_gcp_pubsub(spec: SourceSpec) -> None:
    from google.cloud import pubsub_v1  # optional dependency: pip install .[gcp]

    sub = pubsub_v1.SubscriberClient()

    def cb(message):
        try:
            _handle(spec, message.data, "pubsub", dict(message.attributes))
            message.ack()
        except Exception:
            log.exception("pubsub %s: nack", spec.id)
            message.nack()  # dead-lettering is configured on the subscription itself

    future = sub.subscribe(spec.opt("subscription"), callback=cb,
                           flow_control=pubsub_v1.types.FlowControl(max_messages=int(spec.opt("prefetch", 10))))
    log.info("pubsub %s: listening on %s", spec.id, spec.opt("subscription"))
    future.result()


def consume_kafka(spec: SourceSpec) -> None:
    from kafka import KafkaConsumer  # optional dependency: pip install .[kafka]

    consumer = KafkaConsumer(
        spec.opt("topic"),
        bootstrap_servers=spec.opt("bootstrap_servers"),
        group_id=spec.opt("group_id", f"radar-{spec.id}"),
        enable_auto_commit=False,
        auto_offset_reset=spec.opt("auto_offset_reset", "earliest"),
    )
    for msg in consumer:
        try:
            _handle(spec, msg.value, "pubsub", {k: v.decode() for k, v in (msg.headers or [])})
        except Exception:
            log.exception("kafka %s: offset %s failed; parking and continuing", spec.id, msg.offset)
            # TODO(T034): publish to <topic>.dlq instead of only logging.
        consumer.commit()


CONSUMERS = {"amqp": consume_amqp, "gcp_pubsub": consume_gcp_pubsub, "kafka": consume_kafka}
