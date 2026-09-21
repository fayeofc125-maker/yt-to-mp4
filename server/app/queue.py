"""Selectable execution adapters.

ThreadPoolExecutor is the default and is intentionally local. RQ is supported
as an explicit configuration choice, but must be installed and configured
before startup rather than silently falling back to an in-process queue.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from importlib.util import find_spec


class ThreadQueue:
    def __init__(self, workers: int, prefix: str):
        self.pool = ThreadPoolExecutor(workers, thread_name_prefix=prefix)

    def submit(self, fn, *args):
        return self.pool.submit(fn, *args)


def make_queue(name: str, workers: int, prefix: str, redis_url: str | None = None):
    if name in {"thread", "threadpool", "ThreadPoolExecutor"}:
        return ThreadQueue(workers, prefix)
    if name == "rq":
        if find_spec("rq") is None:
            raise RuntimeError(
                "QUEUE_ADAPTER=rq requires the optional 'rq' dependency and Redis configuration"
            )
        if not redis_url and not os.getenv("REDIS_URL"):
            raise RuntimeError("QUEUE_BACKEND=rq requires REDIS_URL")
        raise RuntimeError(
            "QUEUE_ADAPTER=rq is configured but no Redis URL/worker integration is available; "
            "start the documented worker entrypoint"
        )
    raise ValueError(f"Unknown queue adapter: {name}")
