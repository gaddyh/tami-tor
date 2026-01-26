# scripts/redis_smoke.py
from runtime.redis_client import enqueue_outbox, dequeue_outbox


def main() -> None:
    test_value = "hello"
    enqueue_outbox(test_value)
    got = dequeue_outbox(block_seconds=3)
    print(f"Dequeued: {got!r}")


if __name__ == "__main__":
    main()
