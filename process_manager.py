"""Orchestrates SAP + Jira + Data pipeline."""

import os
import time
import logging

import pandas as pd

from config import Config
from sap_service import SapService
from jira_service import JiraService
from data_processor import DataProcessor

logger = logging.getLogger(__name__)


class ProcessManager:

    def __init__(self, use_com_init: bool = False):
        self.sap = SapService(use_com_init=use_com_init)
        self.jira = JiraService()
        self.folder = Config.get_monthly_folder()
        self.processor = DataProcessor(self.folder)

    def init_connections(self):
        logger.info("Conectando ao Jira...")
        try:
            _ = self.jira.client
        except Exception as e:
            logger.error("Falha Jira: %s", e)

    def run_data_pipeline(self) -> bool:
        if self.processor.load_data():
            self.processor.process_and_enrich()
            return True
        return False

    def process_single_ticket(self, row) -> bool:
        codigo = row["Material"]
        desc = row.get("Txt.brv.material", "Descricao nao disponivel")
        apps = row.get("aplicacoes", "")
        if row.get("All_Desat", False):
            lmrs = f"As posicoes nas LMR: {row['LMR']} foram desativadas"
        else:
            lmrs = row["LMR"]
        try:
            description = Config.TEMPLATE_JIRA.format(
                codigo_zs=codigo,
                descricao_zs=desc,
                lmr_vinculados=lmrs,
                aplicacoes=apps,
            )
            logger.info("Criando ticket: %s...", codigo)
            ticket = self.jira.create_ticket(
                title=f"{codigo} - {desc}",
                description=description,
                tipo="Reposicion ZS (sobre consulta)",
                pieces_in_stock=row["Utilizacao livre"],
            )
            logger.info("Ticket: %s", ticket.key)
            self.jira.transition_issue(ticket.key, "Concluir Creacion")
            self.sap.alterar_status_consulta(row["Evento"], ticket.key, "E")
            return True
        except Exception as e:
            logger.error("Erro item %s: %s", codigo, e)
            return False

    def check_open_consultations(self):
        items = self.processor.get_items_in_consultation()
        logger.info("Verificando %d itens em consulta...", len(items))
        for _, row in items.iterrows():
            mat = row["Material"]
            try:
                issues = self.jira.search_tickets(mat)
                if not issues:
                    logger.warning("Sem ticket: %s", mat)
                    continue
                status = JiraService.get_status(issues[0])
                if status in Config.DONE_STATUSES:
                    logger.info("%s fechado -> atualizando SAP", issues[0].key)
                    self.sap.alterar_status_consulta(row["Evento"], issues[0].key, "F")
                else:
                    logger.info("%s em andamento (%s)", issues[0].key, status)
            except Exception as e:
                logger.error("Erro verificacao %s: %s", mat, e)

    def extract_sap_reports(self):
        output = os.path.join(Config.BASE_PATH, self.folder)
        os.makedirs(output, exist_ok=True)
        logger.info("Extraindo ZMM0133...")
        self.sap.extract_zmm0133(output, "zs.xlsx")
        time.sleep(2)
        try:
            df = pd.read_excel(os.path.join(output, "zs.xlsx"), dtype=str)
            col = "Material" if "Material" in df.columns else df.columns[0]
            mats = df[col].dropna().unique()
            logger.info("%d materiais encontrados.", len(mats))
            pd.DataFrame(mats).to_clipboard(index=False, header=False)
            logger.info("Materiais copiados para clipboard.")
        except Exception as e:
            logger.error("Erro leitura Excel: %s", e)
            return
        logger.info("Extraindo ZMM0182...")
        self.sap.extract_zmm0182(output, "0182.xlsx")
        logger.info("Extracao SAP concluida!")
