"""radar <command>

  initdb                    create tables (TODO T030: Alembic)
  sources                   validate and list sources.yaml
  harvest <source_id>       pull one source now (inline when RADAR_EAGER=1, else via the broker)
  consume <source_id>       run the consumer of a push source (amqp | gcp_pubsub | kafka)
  reconcile                 re-enqueue records whose pipeline stopped mid-way
  reassess                  re-index the graph and re-score all ready cards (also daily via beat)
  demo                      eager run of all demo sources into the local DB (no broker, no keys)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.environ.get("RADAR_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="radar")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("initdb")
    sub.add_parser("sources")
    h = sub.add_parser("harvest"); h.add_argument("source_id")
    c = sub.add_parser("consume"); c.add_argument("source_id")
    sub.add_parser("reconcile")
    sub.add_parser("demo")
    sub.add_parser("reassess")
    a = p.parse_args(argv)

    if a.cmd == "demo":
        os.environ["RADAR_EAGER"] = "1"
        os.environ["RADAR_DEMO_MODE"] = "1"
        from radar.config import get_settings
        get_settings.cache_clear()

    from radar.db import create_all

    if a.cmd == "initdb":
        create_all()
        print("ok")
    elif a.cmd == "sources":
        from radar.sources.registry import active_sources, load_sources

        active = active_sources()
        for s in load_sources().values():
            print(f"{'*' if s.id in active else ' '} {s.id:28} {s.type:10} {s.mode:5} {s.description}")
    elif a.cmd == "harvest":
        create_all()
        from radar.pipeline.tasks import harvest

        r = harvest.apply_async((a.source_id,), queue="harvest", routing_key="harvest")
        print(json.dumps(r.get() if r.ready() else {"task_id": r.id}, default=str))
    elif a.cmd == "consume":
        create_all()
        from radar.sources.push import CONSUMERS
        from radar.sources.registry import get_source

        spec = get_source(a.source_id)
        if spec.type not in CONSUMERS:
            print(f"{a.source_id} is {spec.type!r}; consumers exist for {sorted(CONSUMERS)}", file=sys.stderr)
            return 2
        CONSUMERS[spec.type](spec)
    elif a.cmd == "reconcile":
        from radar.pipeline.tasks import reconcile_all

        print(f"re-enqueued {reconcile_all()}")
    elif a.cmd == "demo":
        create_all()
        from radar.pipeline.tasks import harvest
        from radar.sources.registry import active_sources

        for s in active_sources().values():
            if s.mode == "pull":
                print(s.id, harvest.apply((s.id,)).get())
        from radar.pipeline.tasks import reassess

        print("reassessed", reassess.apply().get())
    elif a.cmd == "reassess":
        create_all()
        from radar.pipeline.tasks import reassess

        print("reassessed", reassess.apply().get())
    return 0


if __name__ == "__main__":
    sys.exit(main())
