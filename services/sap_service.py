"""Wrapper for SAP GUI Scripting via COM automation."""

import os
import time
import logging
from datetime import date
from typing import Optional

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
                raise RuntimeError("Nao foi possivel conectar ao SAP GUI")
            application = sap_gui.GetScriptingEngine
            if not application:
                raise RuntimeError("Nao foi possivel obter o Scripting Engine")
            connection = application.Children(0)
            if not connection:
                raise RuntimeError("Nao ha conexoes SAP ativas")
            self._session = connection.Children(0)
            if not self._session:
                raise RuntimeError("Nao ha sessoes SAP ativas")
            logger.info("Conexao com SAP estabelecida.")
        except Exception as e:
            logger.error("Erro ao conectar com SAP: %s", e)
            self._session = None
            raise

    def reset(self):
        self._session = None

    # ── Navigation helpers ────────────────────────────────────────

    def _go_home(self):
        try:
            self.session.findById("wnd[0]/tbar[0]/btn[12]").press()
        except Exception:
            pass

    def _go_back(self, times: int = 1):
        for _ in range(times):
            try:
                self.session.findById("wnd[0]/tbar[0]/btn[3]").press()
            except Exception:
                pass

    def _run_transaction(self, tcode: str):
        self.session.findById("wnd[0]/tbar[0]/okcd").text = tcode
        self.session.findById("wnd[0]").sendVKey(0)

    def _check_status_bar(self):
        try:
            text = self.session.findById("wnd[0]/sbar").text
            if text:
                logger.info("Status SAP: %s", text)
                if any(w in text.lower() for w in ("erro", "error", "falha")):
                    return False, text
            return True, text
        except Exception:
            return True, ""

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
            base = (
                "wnd[0]/usr/tabsTAB_DADOS/tabpTAB_DADOS_FC2/"
                "ssubTAB_DADOS_SCA:ZMM_REL_MAT_CRITICO:2002"
            )
            self.session.findById(
                f"{base}/cntlTC_ANALISE/shellcont/shell"
            ).text = str(jira_ticket)
            self.session.findById(
                f"{base}/ctxtWA_EVENTO-CD_SIT_ANALISE"
            ).text = str(novo_status)
            self.session.findById("wnd[0]").sendVKey(11)
            self._go_back(3)
            logger.info("Status do evento %s atualizado no SAP.", evento)
            return True
        except Exception as e:
            logger.error("Erro SAP no evento %s: %s", evento, e)
            return False

    # ── Material level adjustment (MM02) ──────────────────────────

    def ajustar_nivel(self, material, pr, max_valor):
        try:
            self._go_home()
            self._run_transaction("mm02")
            self.session.findById("wnd[0]/usr/ctxtRMMG1-MATNR").text = material
            self.session.findById("wnd[0]").sendVKey(0)
            self.session.findById("wnd[0]/usr/tabsTABSPR1/tabpSP12").select()
            pr_path = (
                "wnd[0]/usr/tabsTABSPR1/tabpSP12/ssubTABFRA1:SAPLMGMM:2000/"
                "subSUB3:SAPLMGD1:2482/txtMARC-MINBE"
            )
            mx_path = (
                "wnd[0]/usr/tabsTABSPR1/tabpSP12/ssubTABFRA1:SAPLMGMM:2000/"
                "subSUB4:SAPLMGD1:2483/txtMARC-MABST"
            )
            self.session.findById(pr_path).text = str(pr)
            self.session.findById(mx_path).text = str(max_valor)
            self.session.findById(mx_path).setFocus()
            self.session.findById(mx_path).caretPosition = 1
            self.session.findById("wnd[0]").sendVKey(11)
            self._go_back()
            logger.info("Nivel ajustado: %s  PR=%s  MAX=%s", material, pr, max_valor)
            return True
        except Exception as e:
            logger.error("Erro ao ajustar nivel %s: %s", material, e)
            self._go_back()
            return False

    # ── MRP execution (MD03) ──────────────────────────────────────

    def rodar_mrp(self, material):
        try:
            self._go_home()
            self._run_transaction("md03")
            time.sleep(1)
            self.session.findById("wnd[0]/usr/ctxtRM61X-MATNR").text = material
            self.session.findById("wnd[0]").sendVKey(0)
            self.session.findById("wnd[0]/usr/ctxtRM61X-BANER").setFocus()
            self.session.findById("wnd[0]/usr/ctxtRM61X-BANER").text = "3"
            self.session.findById("wnd[0]").sendVKey(0)
            self.session.findById("wnd[0]").sendVKey(0)
            time.sleep(2)
            try:
                if self.session.findById("wnd[1]", False):
                    self.session.findById("wnd[1]").sendVKey(0)
                    time.sleep(1)
            except Exception:
                pass
            ok, _ = self._check_status_bar()
            if not ok:
                logger.error("MRP falhou para %s", material)
                return False
            self._go_home()
            logger.info("MRP executado: %s", material)
            return True
        except Exception as e:
            logger.error("Erro MRP %s: %s", material, e)
            self._go_home()
            return False

    # ── Emit requisition (ZMM0124 + ME5A) ─────────────────────────

    def emitir_requisicao(self, material, quantidade):
        try:
            self._run_transaction("zmm0124")
            self.session.findById("wnd[0]/usr/ctxtP_WERKS").text = Config.SAP_CENTER
            self.session.findById("wnd[0]/usr/ctxtS_MATNR-LOW").text = material
            self.session.findById("wnd[0]/usr/ctxtS_MATNR-LOW").setFocus()
            self.session.findById("wnd[0]/usr/ctxtS_MATNR-LOW").caretPosition = len(material)
            self.session.findById("wnd[0]").sendVKey(8)
            qty_field = (
                "wnd[0]/usr/tblZMM_MAT_POR_GRUPO_MRPTC_ITENS/"
                "txtWA_DADOS-QTDE_ORDEM[2,0]"
            )
            self.session.findById(qty_field).text = str(quantidade)
            self.session.findById(qty_field).setFocus()
            self.session.findById(qty_field).caretPosition = len(str(quantidade))
            self.session.findById("wnd[0]").sendVKey(0)
            self.session.findById("wnd[0]").sendVKey(8)
            self.session.findById("wnd[1]/tbar[0]/btn[0]").press()
            self.session.findById("wnd[0]/usr/btn%_S_MATNR_%_APP_%-VALU_PUSH").press()
            self.session.findById("wnd[1]/tbar[0]/btn[24]").press()
            self.session.findById("wnd[1]").sendVKey(8)
            self.session.findById("wnd[0]/usr/ctxtS_MATNR-LOW").setFocus()
            self.session.findById("wnd[0]/usr/ctxtS_MATNR-LOW").caretPosition = 6
            self.session.findById("wnd[0]").sendVKey(0)
            self.session.findById("wnd[0]").sendVKey(8)
            self.session.findById("wnd[0]/usr/btnCONT").press()
            self._go_back(2)
            logger.info("Requisicao emitida: %s", material)
            return True
        except Exception as e:
            logger.error("Erro requisicao %s: %s", material, e)
            self._go_back()
            return False

    # ── Requisition adjustment (ME53N) ────────────────────────────

    def ajustar_requisicao(self, req_num):
        try:
            self._go_home()
            self._run_transaction("ME53N")
            self.session.findById("wnd[0]/tbar[1]/btn[17]").press()
            self.session.findById(
                "wnd[1]/usr/subSUB0:SAPLMEGUI:0003/ctxtMEPO_SELECT-BANFN"
            ).text = req_num
            self.session.findById("wnd[0]").sendVKey(0)
            self.session.findById("wnd[0]").sendVKey(0)
            self.session.findById("wnd[0]/tbar[1]/btn[7]").press()
            ht = (
                "wnd[0]/usr/subSUB0:SAPLMEGUI:0010/subSUB1:SAPLMEVIEWS:1100/"
                "subSUB2:SAPLMEVIEWS:1200/subSUB1:SAPLMEGUI:3102/"
                "tabsREQ_HEADER_DETAIL/tabpTABREQHDT1/"
                "ssubTABSTRIPCONTROL3SUB:SAPLMEGUI:1230/"
                "subTEXTS:SAPLMMTE:0100/subEDITOR:SAPLMMTE:0101/"
                "cntlTEXT_EDITOR_0101/shellcont/shell"
            )
            self.session.findById(ht).text = "Reposicao de estoque\nTRIBUTADO"
            gid = (
                "wnd[0]/usr/subSUB0:SAPLMEGUI:0010/subSUB2:SAPLMEVIEWS:1100/"
                "subSUB2:SAPLMEVIEWS:1200/subSUB1:SAPLMEGUI:3212/"
                "cntlGRIDCONTROL/shellcont/shell"
            )
            self.session.findById(gid).setCurrentCell(0, "BNFPO")
            self.session.findById(gid).selectAll()
            self.session.findById(gid).pressToolbarButton("&MEREQDCMALL")
            self.session.findById("wnd[0]/tbar[1]/btn[39]").press()
            ct = (
                "wnd[0]/usr/subSUB0:SAPLMEGUI:0010/subSUB1:SAPLMEVIEWS:1100/"
                "subSUB2:SAPLMEVIEWS:1200/subSUB1:SAPLMEGUI:3102/"
                "tabsREQ_HEADER_DETAIL/tabpTABREQHDT1/"
                "ssubTABSTRIPCONTROL3SUB:SAPLMEGUI:1230/"
                "subTEXTS:SAPLMMTE:0100/subEDITOR:SAPLMMTE:0101/"
                "cntlTEXT_EDITOR_0101/shellcont/shell"
            )
            self.session.findById(ct).setSelectionIndexes(20, 20)
            self.session.findById("wnd[0]/tbar[0]/btn[11]").press()
            self._go_back()
            logger.info("Requisicao %s ajustada.", req_num)
            return True
        except Exception as e:
            logger.error("Erro ajuste req %s: %s", req_num, e)
            self._go_back()
            return False

    # ── Find requisition (ME5A) ───────────────────────────────────

    def encontrar_requisicao(self, material) -> Optional[str]:
        try:
            self._run_transaction("me5a")
            data_atual = date.today().strftime("%d%m%Y")
            self.session.findById("wnd[0]/tbar[1]/btn[16]").press()
            self.session.findById(
                "wnd[0]/usr/ssub%_SUBSCREEN_%_SUB%_CONTAINER:SAPLSSEL:2001/"
                "ssubSUBSCREEN_CONTAINER2:SAPLSSEL:2000/"
                "ssubSUBSCREEN_CONTAINER:SAPLSSEL:1106/ctxt%%DYN002-LOW"
            ).text = data_atual
            self.session.findById("wnd[0]/usr/ctxtBA_MATNR-LOW").text = material
            self.session.findById("wnd[0]/usr/ctxtBA_MATNR-LOW").setFocus()
            self.session.findById("wnd[0]/usr/ctxtBA_MATNR-LOW").caretPosition = len(material)
            self.session.findById("wnd[0]").sendVKey(8)
            req_num = None
            try:
                grid = self.session.findById("wnd[0]/usr/cntlGRID1/shellcont/shell")
                grid.currentCellRow = -1
                grid.selectColumn("BANFN")
                self.session.findById("wnd[0]/tbar[1]/btn[40]").press()
                grid.currentCellRow = 1
                req_num = grid.getCellValue(1, "BANFN")
            except Exception:
                logger.warning("Nenhuma requisicao para %s", material)
            self._go_back()
            if req_num:
                logger.info("Requisicao %s encontrada: %s", req_num, material)
            return req_num
        except Exception as e:
            logger.error("Erro busca req %s: %s", material, e)
            self._go_back()
            return None

    # ── Planned order generation (ZMM0124) ────────────────────────

    def gerar_ordem_planejada(self, material, quantidade):
        try:
            self._run_transaction("zmm0124")
            self.session.findById("wnd[0]/usr/ctxtP_WERKS").text = Config.SAP_CENTER
            self.session.findById("wnd[0]/usr/ctxtS_MATNR-LOW").text = material
            self.session.findById("wnd[0]/usr/ctxtS_MATNR-LOW").setFocus()
            self.session.findById("wnd[0]/usr/ctxtS_MATNR-LOW").caretPosition = len(material)
            self.session.findById("wnd[0]").sendVKey(8)
            qty = (
                "wnd[0]/usr/tblZMM_MAT_POR_GRUPO_MRPTC_ITENS/"
                "txtWA_DADOS-QTDE_ORDEM[2,0]"
            )
            self.session.findById(qty).text = str(quantidade)
            self.session.findById(qty).setFocus()
            self.session.findById(qty).caretPosition = len(str(quantidade))
            self.session.findById("wnd[0]").sendVKey(0)
            self.session.findById("wnd[0]").sendVKey(8)
            self.session.findById("wnd[1]/tbar[0]/btn[0]").press()
            self._go_back()
            logger.info("Ordem planejada: %s  qtd=%s", material, quantidade)
            return True
        except Exception as e:
            logger.error("Erro ordem planejada %s: %s", material, e)
            self._go_back()
            return False

    # ── Report extraction ─────────────────────────────────────────

    def extract_zmm0133(self, output_path, filename="zs.xlsx"):
        self._go_back(2)
        self.session.findById("wnd[0]").maximize()
        self._run_transaction("zmm0133")
        self.session.findById("wnd[0]/tbar[1]/btn[17]").press()
        self.session.findById("wnd[1]/tbar[0]/btn[6]").press()
        shell = "wnd[1]/usr/cntlALV_CONTAINER_1/shellcont/shell"
        self.session.findById(shell).currentCellRow = 3
        self.session.findById(shell).selectedRows = "3"
        self.session.findById(shell).doubleClickCurrentCell()
        self.session.findById("wnd[0]").sendVKey(8)
        self.session.findById("wnd[0]/mbar/menu[0]/menu[3]/menu[1]").select()
        self.session.findById("wnd[1]/tbar[0]/btn[0]").press()
        self.session.findById("wnd[1]/usr/ctxtDY_PATH").text = output_path
        self.session.findById("wnd[1]/usr/ctxtDY_FILENAME").text = filename
        self.session.findById("wnd[1]").sendVKey(11)
        self._go_back(2)
        logger.info("ZMM0133 -> %s", os.path.join(output_path, filename))

    def extract_zmm0182(self, output_path, filename="0182.xlsx"):
        self._go_back(2)
        self._run_transaction("zmm0182")
        self.session.findById("wnd[0]/usr/btn%_S_MATNR_%_APP_%-VALU_PUSH").press()
        self.session.findById("wnd[1]/tbar[0]/btn[24]").press()
        self.session.findById("wnd[1]/tbar[0]/btn[8]").press()
        self.session.findById("wnd[0]").sendVKey(8)
        self.session.findById("wnd[0]/mbar/menu[0]/menu[3]/menu[1]").select()
        self.session.findById("wnd[1]/tbar[0]/btn[0]").press()
        self.session.findById("wnd[1]/usr/ctxtDY_PATH").text = output_path
        self.session.findById("wnd[1]/usr/ctxtDY_FILENAME").text = filename
        self.session.findById("wnd[1]").sendVKey(11)
        self._go_back(2)
        logger.info("ZMM0182 -> %s", os.path.join(output_path, filename))
