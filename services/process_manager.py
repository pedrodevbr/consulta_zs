"""Orchestrates SAP + Jira + Data pipeline."""

import os
import time
import logging

import pandas as pd

from config import Config
from services.sap_service import SapService
from services.jira_service import JiraService, JiraAuthError
from services.data_processor import DataProcessor

logger = logging.getLogger(__name__)


class ProcessManager:

    def __init__(self, use_com_init: bool = False):
        self.sap = SapService(use_com_init=use_com_init)
        self.jira = JiraService()
        self.folder = os.path.join(Config.BASE_PATH, Config.get_monthly_folder())
        self.processor = DataProcessor(self.folder)

    # ── Connections ───────────────────────────────────────────────

    def init_connections(self):
        # Validate config first
        problems = Config.validate()
        for p in problems:
            logger.warning("Config: %s", p)

        logger.info("Conectando ao Jira…")
        try:
            _ = self.jira.client
            # Log available options for customfield_17633 to help debug
            self.jira.get_field_options("customfield_17633")
        except JiraAuthError as e:
            logger.error("Falha de autenticação JIRA: %s", e)
        except ConnectionError as e:
            logger.error("Falha conexão JIRA: %s", e)
        except Exception as e:
            logger.error("Falha Jira inesperada: %s", e)

    # ── Data pipeline ─────────────────────────────────────────────

    def run_data_pipeline(self) -> bool:
        if not os.path.isdir(self.folder):
            logger.error("Pasta não encontrada: %s", self.folder)
            return False
        if self.processor.load_data():
            self.processor.process_and_enrich()
            return True
        return False

    # ── Process single ticket ─────────────────────────────────────

    def process_single_ticket(self, row) -> bool:
        codigo = row[Config.ZS_MATERIAL]
        desc = row.get(Config.ZS_TXT_BREVE, "Descrição não disponível")
        apps = row.get("aplicacoes", "")

        if row.get("All_Desat", False):
            lmrs = f"As posições nas LMR: {row['LMR']} foram desativadas"
        else:
            lmrs = row.get("LMR", "Sem LMR vinculada")

        try:
            description = Config.TEMPLATE_JIRA.format(
                codigo_zs=codigo,
                descricao_zs=desc,
                lmr_vinculados=lmrs,
                aplicacoes=apps,
            )
            logger.info("Criando ticket: %s…", codigo)
            ticket = self.jira.create_ticket(
                title=f"{codigo} - {desc}",
                description=description,
                tipo="Reposição ZS (sobre consulta)",
                pieces_in_stock=row.get(Config.ZS_UTILIZACAO_LIVRE, "0"),
            )
            logger.info("Ticket: %s", ticket.key)
            self.jira.transition_issue(ticket.key, "Concluir Creación")
            self.sap.alterar_status_consulta(
                row[Config.ZS_EVENTO], ticket.key, "E",
            )
            return True
        except Exception as e:
            logger.error("Erro item %s: %s", codigo, e)
            return False

    # ── Check open consultations ──────────────────────────────────

    def check_open_consultations(self):
        items = self.processor.get_items_in_consultation()
        if items.empty:
            logger.info("Nenhum item em consulta para verificar.")
            return

        logger.info("Verificando %d itens em consulta…", len(items))
        for _, row in items.iterrows():
            mat = row[Config.ZS_MATERIAL]
            try:
                issues = self.jira.search_tickets(mat)
                if not issues:
                    logger.warning("Sem ticket JIRA para: %s", mat)
                    continue
                status = JiraService.get_status(issues[0])
                if status in Config.DONE_STATUSES:
                    logger.info("%s fechado → atualizando SAP", issues[0].key)
                    self.sap.alterar_status_consulta(
                        row[Config.ZS_EVENTO], issues[0].key, "F",
                    )
                else:
                    logger.info("%s em andamento (%s)", issues[0].key, status)
            except Exception as e:
                logger.error("Erro verificação %s: %s", mat, e)

    # ── SAP actions dispatcher ────────────────────────────────────

    def run_sap_action(self, action: str, material: str, **kwargs) -> tuple[bool, str]:
        """Execute a SAP action. Returns (success, message)."""
        try:
            if action == "ajustar_nivel":
                pr = kwargs.get("pr", "")
                max_valor = kwargs.get("max_valor", "")
                if not pr or not max_valor:
                    return False, "PR e MAX são obrigatórios"
                ok = self.sap.ajustar_nivel(material, pr, max_valor)
                return ok, "Nível ajustado" if ok else "Falha ao ajustar nível"

            if action == "rodar_mrp":
                ok = self.sap.rodar_mrp(material)
                return ok, "MRP executado" if ok else "Falha no MRP"

            if action == "emitir_requisicao":
                qtd = kwargs.get("quantidade", "")
                if not qtd:
                    return False, "Quantidade é obrigatória"
                ok = self.sap.emitir_requisicao(material, qtd)
                return ok, "Requisição emitida" if ok else "Falha na requisição"

            if action == "gerar_ordem":
                qtd = kwargs.get("quantidade", "")
                if not qtd:
                    return False, "Quantidade é obrigatória"
                ok = self.sap.gerar_ordem_planejada(material, qtd)
                return ok, "Ordem planejada gerada" if ok else "Falha na ordem"

            if action == "encontrar_requisicao":
                req = self.sap.encontrar_requisicao(material)
                if req:
                    return True, f"Requisição encontrada: {req}"
                return False, "Nenhuma requisição encontrada"

            return False, f"Ação desconhecida: {action}"
        except Exception as e:
            logger.error("Erro SAP '%s' para %s: %s", action, material, e)
            return False, str(e)

    # ── SAP report extraction ─────────────────────────────────────

    def extract_sap_reports(self):
        os.makedirs(self.folder, exist_ok=True)
        logger.info("Extraindo ZMM0133…")
        self.sap.extract_zmm0133(self.folder, "zs.xlsx")
        time.sleep(2)

        zs_path = os.path.join(self.folder, "zs.xlsx")
        if not os.path.isfile(zs_path):
            logger.error("Arquivo ZS não foi gerado: %s", zs_path)
            return

        try:
            df = pd.read_excel(zs_path, dtype=str)
            col = Config.ZS_MATERIAL if Config.ZS_MATERIAL in df.columns else df.columns[0]
            mats = df[col].dropna().unique()
            logger.info("%d materiais encontrados.", len(mats))
            pd.DataFrame(mats).to_clipboard(index=False, header=False)
            logger.info("Materiais copiados para clipboard.")
        except Exception as e:
            logger.error("Erro leitura Excel: %s", e)
            return

        logger.info("Extraindo ZMM0182…")
        self.sap.extract_zmm0182(self.folder, "0182.xlsx")
        logger.info("Extração SAP concluída!")
