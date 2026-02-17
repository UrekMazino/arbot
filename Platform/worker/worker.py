from __future__ import annotations

import os
from redis import Redis
from rq import Worker


def main() -> None:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    queues = os.getenv("RQ_QUEUES", "reports,analytics").split(",")
    conn = Redis.from_url(redis_url)
    worker = Worker([q.strip() for q in queues if q.strip()], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
