# apps/worker_supervisor.py
import subprocess
import sys
import signal

N_WORKERS = 1
processes = []


def shutdown(signum, frame):
    print("Supervisor shutting down...", flush=True)
    for p in processes:
        p.terminate()
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


def main():
    print(f"Starting {N_WORKERS} worker processes", flush=True)
    for _ in range(N_WORKERS):
        p = subprocess.Popen(
            [sys.executable, "-m", "workflows.worker"],
        )
        processes.append(p)

    # Wait forever
    for p in processes:
        p.wait()


if __name__ == "__main__":
    main()
