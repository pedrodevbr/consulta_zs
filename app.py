"""Entry point — Consultas ZS."""

from config import setup_logging
from cli import run

if __name__ == "__main__":
    setup_logging(log_to_file=True)
    run()
