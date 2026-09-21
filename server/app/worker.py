"""RQ worker entrypoint.

RQ is intentionally opt-in. Configure QUEUE_BACKEND=rq and REDIS_URL, install
the ``rq`` extra, then run ``python -m app.worker`` in a separate process.
"""

import os


def main() -> None:
    try:
        from redis import Redis
        from rq import Worker
    except ImportError as exc:
        raise SystemExit("Install the rq extra to run the worker") from exc
    url = os.getenv("REDIS_URL")
    if not url:
        raise SystemExit("REDIS_URL is required when QUEUE_ADAPTER=rq")
    Worker(["clipper"], connection=Redis.from_url(url)).work()


if __name__ == "__main__":
    main()
