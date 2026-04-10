"""Wrapper for SAP GUI Scripting via COM automation."""

import logging
import os
import time

from config import Config

logger = logging.getLogger(__name__)


class SapService:

    def __init__(self, use_com_init: bool = False):
        self._session = None
        self._use_com_init = use_com_init

    # ── Connection ────────────────────────────────────────────────

    @property
    def session(self):
        if self._session is None:
            self._connect()
        return self._session

    def _connect(self):
        try:
            if self._use_com_init:
                import pythoncom
                pythoncom.CoInitialize()

            import win32com.client
            sap_gui = win32com.client.GetObject("SAPGUI")
            if not sap_gui:
                raise RuntimeError("Não foi possível conectar ao SAP GUI")
            application = sap_gui.GetScriptingEngine
            if not application:
                raise RuntimeError("Não foi possível obter o Scripting Engine")
            connection = application.Children(0)
            if not connection:
                raise RuntimeError("Não há conexões SAP ativas")
            self._session = connection.Children(0)
            if not self._session:
                raise RuntimeError("Não há sessões SAP ativas")
            logger.info("Conexão com SAP estabelecida.")
        except Exception as e:
            logger.error("Erro ao conectar com SAP: %s", e)
            self._session = None
            raise

    def reset(self):
        self._session = None

    # ── Navigation helpers ────────────────────────────────────────

    def _go_back(self, times: int = 1):
        for _ in range(times):
            try:
                self.session.findById("wnd[0]/tbar[0]/btn[3]").press()
            except Exception:
                pass

    def _run_transaction(self, tcode: str):
        self.session.findById("wnd[0]/tbar[0]/okcd").text = tcode
        self.session.findById("wnd[0]").sendVKey(0)

    # ── Report extraction ────────────────────────────────────────

    def extract_zmm0133(self, output_path: str, filename: str = "zs.xlsx"):
        """Run ZMM0133 transaction and export the ALV grid to Excel."""
        dest = os.path.join(output_path, filename)
        try:
            self._go_back(2)
            self._run_transaction(Config.SAP_TRANSACTION)

            # Selection screen
            self.session.findById(
                "wnd[0]/usr/ctxtS_CENTRO-LOW"
            ).text = Config.SAP_CENTER
            self.session.findById(
                "wnd[0]/usr/ctxtS_SETOR-LOW"
            ).text = str(Config.SETOR_ATIVIDADE)
            self.session.findById("wnd[0]").sendVKey(8)  # Execute

            time.sleep(2)

            # Export ALV grid → spreadsheet
            grid = self.session.findById(
                "wnd[0]/usr/cntlGRID1/shellcont/shell"
            )
            grid.pressToolbarContextButton("&MB_EXPORT")
            grid.selectContextMenuItem("&XXL")

            time.sleep(1)
            # Fill save dialog
            self.session.findById(
                "wnd[1]/usr/ctxtDY_PATH"
            ).text = output_path
            self.session.findById(
                "wnd[1]/usr/ctxtDY_FILENAME"
            ).text = filename
            self.session.findById(
                "wnd[1]/tbar[0]/btn[11]"
            ).press()  # Replace if exists

            time.sleep(3)
            self._go_back(1)

            logger.info("ZMM0133 exportada: %s", dest)
            return True
        except Exception as e:
            logger.error("Erro ao extrair ZMM0133: %s", e)
            return False

    def extract_zmm0182(self, output_path: str, filename: str = "0182.xlsx"):
        """Run ZMM0182 transaction and export the ALV grid to Excel."""
        dest = os.path.join(output_path, filename)
        try:
            self._go_back(2)
            self._run_transaction("zmm0182")

            # Selection screen
            self.session.findById(
                "wnd[0]/usr/ctxtS_CENTRO-LOW"
            ).text = Config.SAP_CENTER

            # Paste materials from clipboard
            self.session.findById(
                "wnd[0]/usr/btn%_S_MATNR_%_APP_%-VALU_PUSH"
            ).press()
            time.sleep(1)

            # Paste (Ctrl+V into multiple selection)
            self.session.findById("wnd[1]/tbar[0]/btn[24]").press()
            time.sleep(1)
            self.session.findById("wnd[1]/tbar[0]/btn[8]").press()
            time.sleep(1)

            self.session.findById("wnd[0]").sendVKey(8)  # Execute
            time.sleep(2)

            # Export ALV grid → spreadsheet
            grid = self.session.findById(
                "wnd[0]/usr/cntlGRID1/shellcont/shell"
            )
            grid.pressToolbarContextButton("&MB_EXPORT")
            grid.selectContextMenuItem("&XXL")

            time.sleep(1)
            self.session.findById(
                "wnd[1]/usr/ctxtDY_PATH"
            ).text = output_path
            self.session.findById(
                "wnd[1]/usr/ctxtDY_FILENAME"
            ).text = filename
            self.session.findById(
                "wnd[1]/tbar[0]/btn[11]"
            ).press()

            time.sleep(3)
            self._go_back(1)

            logger.info("ZMM0182 exportada: %s", dest)
            return True
        except Exception as e:
            logger.error("Erro ao extrair ZMM0182: %s", e)
            return False

    # ── Consultation status ───────────────────────────────────────

    def alterar_status_consulta(self, evento, jira_ticket, novo_status):
        try:
            self._go_back(2)
            self._run_transaction(Config.SAP_TRANSACTION)

            self.session.findById("wnd[0]/usr/ctxtS_EVENTO-LOW").text = str(evento)
            self.session.findById("wnd[0]").sendVKey(8)

            grid = self.session.findById("wnd[0]/usr/cntlGRID1/shellcont/shell")
            grid.selectedRows = "0"
            grid.doubleClickCurrentCell()

            self.session.findById(
                "wnd[0]/usr/tabsTAB_DADOS/tabpTAB_DADOS_FC2"
            ).select()

            field_ticket = self.session.findById(
                "wnd[0]/usr/tabsTAB_DADOS/tabpTAB_DADOS_FC2/"
                "ssubTAB_DADOS_SCA:ZMM_REL_MAT_CRITICO:2002/"
                "cntlTC_ANALISE/shellcont/shell"
            )
            field_ticket.text = str(jira_ticket)

            field_status = self.session.findById(
                "wnd[0]/usr/tabsTAB_DADOS/tabpTAB_DADOS_FC2/"
                "ssubTAB_DADOS_SCA:ZMM_REL_MAT_CRITICO:2002/"
                "ctxtWA_EVENTO-CD_SIT_ANALISE"
            )
            field_status.text = str(novo_status)

            self.session.findById("wnd[0]").sendVKey(11)
            self._go_back(3)

            logger.info("Status do evento %s atualizado no SAP.", evento)
            return True
        except Exception as e:
            logger.error("Erro SAP no evento %s: %s", evento, e)
            return False
