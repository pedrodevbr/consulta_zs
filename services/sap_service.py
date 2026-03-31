"""Wrapper for SAP GUI Scripting via COM automation."""

import logging

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
