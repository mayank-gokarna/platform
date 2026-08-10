"""Gunicorn config enabling Prometheus multiprocess metric aggregation.

With multiple workers, prometheus_client must run in multiprocess mode so that
counters/gauges are aggregated across workers instead of each worker reporting
its own isolated values. This hook cleans up a worker's metric files when it
exits so dead workers don't leave stale samples behind.
"""

from prometheus_client import multiprocess


def child_exit(server, worker):  # noqa: ARG001 (gunicorn hook signature)
    multiprocess.mark_process_dead(worker.pid)
