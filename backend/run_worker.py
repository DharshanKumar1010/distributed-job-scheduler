import os
import subprocess
import sys

# Helper to launch a worker: python run_worker.py <queue_id>


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python run_worker.py <queue_id>", file=sys.stderr)
        sys.exit(1)

    queue_id = sys.argv[1]
    env = os.environ.copy()
    env["QUEUE_ID"] = queue_id

    subprocess.run([sys.executable, "-m", "app.worker.entrypoint"], env=env, check=True)


if __name__ == "__main__":
    main()
