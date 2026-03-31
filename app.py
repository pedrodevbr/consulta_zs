"""Entry point — Consultas ZS."""

from config import setup_logging
from gui.app import App

if __name__ == "__main__":
    setup_logging(log_to_file=True)
    App().mainloop()
