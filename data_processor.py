"""Loads, filters and enriches the ZS / 0182 spreadsheets."""

import os
import logging

import pandas as pd

from config import Config

logger = logging.getLogger(__name__)


class DataProcessor:

    def __init__(self, folder_path: str):
        self.folder_path = folder_path
        self.zs_df = pd.DataFrame()
        self.t0182_df = pd.DataFrame()

    def load_data(self) -> bool:
        try:
            p_zs = os.path.join(self.folder_path, "zs.xlsx")
            p_0182 = os.path.join(self.folder_path, "0182.xlsx")
            logger.info("Lendo: %s", self.folder_path)
            self.zs_df = pd.read_excel(p_zs)
            self.t0182_df = pd.read_excel(p_0182)
            return True
        except FileNotFoundError as e:
            logger.critical("Arquivo nao encontrado: %s", e)
            return False
        except Exception as e:
            logger.critical("Erro ao ler Excel: %s", e)
            return False

    def process_and_enrich(self):
        logger.info("Processando dados...")

        self.zs_df["Dias da quebra"] = (
            pd.to_datetime("today") - pd.to_datetime(self.zs_df["Data da quebra"])
        ).dt.days

        self.zs_df = self.zs_df[
            (self.zs_df["Setor de atividade"] == Config.SETOR_ATIVIDADE)
            & (self.zs_df["Tipo de MRP"] == "ZS")
            & (self.zs_df["Stat.mat.todos cent."] != "Z3")
        ]

        lmr_map = self.t0182_df.groupby("Material")["No LMR"].agg(
            lambda x: ", ".join(sorted(set(x.astype(str))))
        )
        app_map = self.t0182_df.groupby("Material")["Desc. Aplicacao"].agg(
            lambda x: "\n".join(sorted(set(x.astype(str))))
        )
        self.zs_df["LMR"] = (
            self.zs_df["Material"].map(lmr_map).fillna("Sem LMR vinculada")
        )
        self.zs_df["aplicacoes"] = self.zs_df["Material"].map(app_map).fillna("")

        all_d = self.t0182_df.groupby("Material")["Local. Ativo/Desat."].agg(
            lambda x: (x == "D").all()
        )
        self.zs_df["All_Desat"] = (
            self.zs_df["Material"].map(all_d).fillna(False).astype(bool)
        )

        sem_consulta = self.zs_df["Situacao da analise"] == "N"
        dias_ok = self.zs_df["Dias da quebra"] > Config.DIAS_QUEBRA_THRESHOLD
        self.zs_df["Abrir_consulta"] = sem_consulta & dias_ok

        out1 = os.path.join(self.folder_path, "zs_para_consulta.xlsx")
        self.zs_df[self.zs_df["Abrir_consulta"]].to_excel(out1, index=False)
        logger.info("Exportado: %s", out1)

        out2 = os.path.join(self.folder_path, "zs_em_consulta.xlsx")
        self.zs_df[~sem_consulta].to_excel(out2, index=False)
        logger.info("Exportado: %s", out2)
        logger.info("Processamento concluido.")

    def get_items_to_open(self) -> pd.DataFrame:
        return self.zs_df[self.zs_df["Abrir_consulta"]].copy()

    def get_items_in_consultation(self) -> pd.DataFrame:
        return self.zs_df[self.zs_df["Situacao da analise"] == "E"].copy()
