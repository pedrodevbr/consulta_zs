"""Configuracao central — le variaveis de ambiente / .env."""

import os
import logging
from datetime import datetime

# ── .env loader ───────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())


class Config:
    # Jira
    JIRA_SERVER = "https://jira.itaipu"
    JIRA_USERNAME = os.environ.get("JIRA_USERNAME", "")
    JIRA_PASSWORD = os.environ.get("JIRA_PASSWORD", "")
    JIRA_CERT_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "ItaipuBinacionalRootCA3.pem",
    )
    JIRA_PROJECT = "GCSMIT"

    TEMPLATE_JIRA = (
        "Prezados,\n"
        "Favor informar se ha necessidade de reposicao para o "
        "CODIGO ZS {codigo_zs} - {descricao_zs}.\n"
        "LMR vinculads: {lmr_vinculados}\n"
        "Aplicacoes: {aplicacoes}\n"
        "Agradeco desde ja a atencao."
    )
    DONE_STATUSES = ["Terminado", "Concluido", "Done"]

    # SAP
    SAP_TRANSACTION = "zmm0133"
    SAP_CENTER = "CHI2"

    # Business rules
    DIAS_QUEBRA_THRESHOLD = 60
    SETOR_ATIVIDADE = 31

    # Paths
    BASE_PATH = os.environ.get("BASE_PATH", ".")

    @staticmethod
    def get_monthly_folder() -> str:
        now = datetime.now()
        return f"{now.year}-{now.month:02d}"


def setup_logging(log_to_file: bool = True):
    log_filename = f"log_processo_zs_{datetime.now():%Y-%m-%d}.log"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_to_file:
        handlers.append(logging.FileHandler(log_filename, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
