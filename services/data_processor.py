"""Loads, filters and enriches the ZS / 0182 spreadsheets."""

import os
import logging

import pandas as pd

from config import Config

logger = logging.getLogger(__name__)

# Shorthand aliases for column names
_ZS = Config
_T = Config


def _safe_col(df: pd.DataFrame, name: str, fallback: str = "") -> pd.Series:
    """Return the column if it exists, otherwise a Series filled with *fallback*."""
    if name in df.columns:
        return df[name]
    logger.warning("Coluna '%s' não encontrada. Usando valor padrão '%s'.", name, fallback)
    return pd.Series(fallback, index=df.index)


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first column name that exists in *df*, or None."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


class DataProcessor:

    def __init__(self, folder_path: str):
        self.folder_path = folder_path
        self.zs_df = pd.DataFrame()
        self.t0182_df = pd.DataFrame()

    # ── Load ──────────────────────────────────────────────────────

    def load_data(self) -> bool:
        p_zs = os.path.join(self.folder_path, "zs.xlsx")
        p_0182 = os.path.join(self.folder_path, "0182.xlsx")

        for path, label in [(p_zs, "ZS"), (p_0182, "0182")]:
            if not os.path.isfile(path):
                logger.critical("Arquivo %s não encontrado: %s", label, path)
                return False

        try:
            logger.info("Lendo planilhas em: %s", self.folder_path)
            self.zs_df = pd.read_excel(p_zs)
            self.t0182_df = pd.read_excel(p_0182)
            logger.info(
                "ZS: %d linhas, %d colunas | 0182: %d linhas, %d colunas",
                *self.zs_df.shape, *self.t0182_df.shape,
            )
            return True
        except Exception as e:
            logger.critical("Erro ao ler planilhas: %s", e)
            return False

    # ── Validate ──────────────────────────────────────────────────

    def _validate_columns(self) -> bool:
        """Check that essential columns exist; log warnings for missing ones."""
        ok = True
        zs_required = [
            _ZS.ZS_MATERIAL, _ZS.ZS_DATA_QUEBRA, _ZS.ZS_SETOR_ATIVIDADE,
            _ZS.ZS_TIPO_MRP, _ZS.ZS_STAT_MAT, _ZS.ZS_SITUACAO_ANALISE,
        ]
        for col in zs_required:
            if col not in self.zs_df.columns:
                logger.error("Coluna obrigatória ausente na planilha ZS: '%s'", col)
                ok = False

        t_required = [_T.T0182_MATERIAL, _T.T0182_LOCAL_ATIVO_DESAT]
        for col in t_required:
            if col not in self.t0182_df.columns:
                logger.error("Coluna obrigatória ausente na planilha 0182: '%s'", col)
                ok = False

        if not ok:
            logger.error(
                "Colunas disponíveis ZS: %s", list(self.zs_df.columns),
            )
            logger.error(
                "Colunas disponíveis 0182: %s", list(self.t0182_df.columns),
            )
        return ok

    # ── Process ───────────────────────────────────────────────────

    def process_and_enrich(self):
        logger.info("Processando dados…")

        if not self._validate_columns():
            logger.error("Processamento abortado — colunas obrigatórias ausentes.")
            return

        # Dias da quebra
        self.zs_df["Dias da quebra"] = (
            pd.to_datetime("today")
            - pd.to_datetime(self.zs_df[_ZS.ZS_DATA_QUEBRA], errors="coerce")
        ).dt.days

        # Filter
        self.zs_df = self.zs_df[
            (self.zs_df[_ZS.ZS_SETOR_ATIVIDADE] == Config.SETOR_ATIVIDADE)
            & (self.zs_df[_ZS.ZS_TIPO_MRP] == "ZS")
            & (self.zs_df[_ZS.ZS_STAT_MAT] != "Z3")
        ].copy()

        if self.zs_df.empty:
            logger.warning("Nenhum item ZS após filtragem.")
            return

        # ── LMR / SMR mapping ─────────────────────────────────────
        # The 0182 report may have "Cód. SMR" instead of "Nº LMR".
        smr_col = _find_column(self.t0182_df, ["Nº LMR", _T.T0182_COD_SMR])
        if smr_col:
            lmr_map = self.t0182_df.groupby(_T.T0182_MATERIAL)[smr_col].agg(
                lambda x: ", ".join(sorted(set(x.dropna().astype(str))))
            )
            self.zs_df["LMR"] = (
                self.zs_df[_ZS.ZS_MATERIAL].map(lmr_map).fillna("Sem LMR vinculada")
            )
        else:
            logger.warning("Coluna de LMR/SMR não encontrada na planilha 0182.")
            self.zs_df["LMR"] = "Sem LMR vinculada"

        # ── Aplicações mapping ────────────────────────────────────
        app_col = _find_column(self.t0182_df, [_T.T0182_DESC_APLICACAO, "Desc. Aplicacao"])
        if app_col:
            app_map = self.t0182_df.groupby(_T.T0182_MATERIAL)[app_col].agg(
                lambda x: "\n".join(sorted(set(x.dropna().astype(str))))
            )
            self.zs_df["aplicacoes"] = (
                self.zs_df[_ZS.ZS_MATERIAL].map(app_map).fillna("")
            )
        else:
            logger.warning("Coluna de aplicações não encontrada na planilha 0182.")
            self.zs_df["aplicacoes"] = ""

        # ── All deactivated? ──────────────────────────────────────
        all_d = self.t0182_df.groupby(_T.T0182_MATERIAL)[_T.T0182_LOCAL_ATIVO_DESAT].agg(
            lambda x: (x == "D").all()
        )
        self.zs_df["All_Desat"] = (
            self.zs_df[_ZS.ZS_MATERIAL].map(all_d).fillna(False).astype(bool)
        )

        # ── Flag items to open ────────────────────────────────────
        sem_consulta = _safe_col(self.zs_df, _ZS.ZS_SITUACAO_ANALISE) == "N"
        dias_ok = self.zs_df["Dias da quebra"] > Config.DIAS_QUEBRA_THRESHOLD
        self.zs_df["Abrir_consulta"] = sem_consulta & dias_ok

        # ── Export ────────────────────────────────────────────────
        try:
            out1 = os.path.join(self.folder_path, "zs_para_consulta.xlsx")
            self.zs_df[self.zs_df["Abrir_consulta"]].to_excel(out1, index=False)
            logger.info("Exportado: %s", out1)

            out2 = os.path.join(self.folder_path, "zs_em_consulta.xlsx")
            self.zs_df[~sem_consulta].to_excel(out2, index=False)
            logger.info("Exportado: %s", out2)
        except Exception as e:
            logger.error("Erro ao exportar planilhas: %s", e)

        logger.info(
            "Processamento concluído — %d para abrir, %d em consulta.",
            self.zs_df["Abrir_consulta"].sum(),
            (~sem_consulta).sum(),
        )

    # ── Accessors ─────────────────────────────────────────────────

    def get_items_to_open(self) -> pd.DataFrame:
        if "Abrir_consulta" not in self.zs_df.columns:
            return pd.DataFrame()
        return self.zs_df[self.zs_df["Abrir_consulta"]].copy()

    def get_items_in_consultation(self) -> pd.DataFrame:
        col = _ZS.ZS_SITUACAO_ANALISE
        if col not in self.zs_df.columns:
            return pd.DataFrame()
        return self.zs_df[self.zs_df[col] == "E"].copy()
