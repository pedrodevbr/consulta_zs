"""Configuração central — lê variáveis de ambiente / .env."""

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
    JIRA_MAX_RETRIES = 3
    JIRA_RETRY_DELAY = 2  # seconds

    TEMPLATE_JIRA = (
        "Prezados,\n"
        "Favor informar se há necessidade de reposição para o "
        "CODIGO ZS {codigo_zs} - {descricao_zs}.\n"
        "LMR vinculadas: {lmr_vinculados}\n"
        "Aplicações: {aplicacoes}\n"
        "Agradeço desde já a atenção."
    )
    DONE_STATUSES = ["Terminado", "Concluído", "Done"]

    # SAP
    SAP_TRANSACTION = "zmm0133"
    SAP_CENTER = "CHI2"

    # Business rules
    DIAS_QUEBRA_THRESHOLD = 60
    SETOR_ATIVIDADE = 31

    # Paths
    BASE_PATH = os.environ.get(
        "BASE_PATH",
        r"C:\Users\pedrohvb\OneDrive - ITAIPU Binacional\Projetos\consulta_zs",
    )

    # ── Column names — ZS spreadsheet ─────────────────────────────
    # Keeps column names in one place; if SAP changes a header, fix here only.
    ZS_EVENTO = "Evento"
    ZS_MATERIAL = "Material"
    ZS_TXT_BREVE = "Txt.brv.material"
    ZS_DATA_QUEBRA = "Data da quebra"
    ZS_SITUACAO_ANALISE = "Situação da análise"
    ZS_UTILIZACAO_LIVRE = "Utilização livre"
    ZS_SETOR_ATIVIDADE = "Setor de atividade"
    ZS_TIPO_MRP = "Tipo de MRP"
    ZS_STAT_MAT = "Stat.mat.todos cent."
    ZS_PLANEJADOR_MRP = "Planejador MRP"

    # ── Column names — 0182 spreadsheet ───────────────────────────
    T0182_MATERIAL = "Material"
    T0182_DESC_SAP = "Desc. SAP"
    T0182_COD_SMR = "Cód. SMR"
    T0182_COD_APLICACAO = "Cód Aplicação"
    T0182_DESC_APLICACAO = "Desc. Aplicação"
    T0182_LOCAL_ATIVO_DESAT = "Local. Ativo/Desat."

    # ── OpenRouter / LLM ──────────────────────────────────────────
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    @staticmethod
    def get_monthly_folder() -> str:
        now = datetime.now()
        return f"{now.year}-{now.month:02d}"

    @classmethod
    def validate(cls) -> list[str]:
        """Return a list of configuration problems (empty = OK)."""
        problems = []
        if not cls.JIRA_USERNAME:
            problems.append("JIRA_USERNAME não configurado (defina no .env)")
        if not cls.JIRA_PASSWORD:
            problems.append("JIRA_PASSWORD não configurado (defina no .env)")
        if not os.path.isfile(cls.JIRA_CERT_PATH):
            problems.append(f"Certificado não encontrado: {cls.JIRA_CERT_PATH}")
        if not os.path.isdir(cls.BASE_PATH):
            problems.append(f"BASE_PATH não existe: {cls.BASE_PATH}")
        if not cls.OPENROUTER_API_KEY:
            problems.append("OPENROUTER_API_KEY não configurado (defina no .env)")
        return problems


def setup_logging(log_to_file: bool = True):
    log_filename = f"log_processo_zs_{datetime.now():%Y-%m-%d}.log"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_to_file:
        try:
            handlers.append(logging.FileHandler(log_filename, encoding="utf-8"))
        except OSError:
            pass  # can't write log file — continue with console only
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s — %(levelname)s — %(message)s",
        handlers=handlers,
    )
