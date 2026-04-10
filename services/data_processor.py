import os
import logging

import pandas as pd

from config import Config

logger = logging.getLogger(__name__)


class DataProcessor:
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.zs_df = pd.DataFrame()
        self.t0182_df = pd.DataFrame()

    def load_data(self):
        try:
            path_zs = os.path.join(self.folder_path, "zs.xlsx")
            path_0182 = os.path.join(self.folder_path, "0182.xlsx")

            logger.info("Lendo arquivos de: %s", self.folder_path)
            self.zs_df = pd.read_excel(path_zs)
            self.t0182_df = pd.read_excel(path_0182)
            return True
        except FileNotFoundError as e:
            logger.critical("Arquivo não encontrado: %s", e)
            return False
        except Exception as e:
            logger.critical("Erro ao ler Excel: %s", e)
            return False

    def process_and_enrich(self):
        logger.info("Iniciando processamento de dados...")

        # Calcular dias da quebra
        self.zs_df['Dias da quebra'] = (
            pd.to_datetime('today') - pd.to_datetime(self.zs_df['Data da quebra'])
        ).dt.days

        # Filtros
        self.zs_df = self.zs_df[
            (self.zs_df['Setor de atividade'] == Config.SETOR_ATIVIDADE)
            & (self.zs_df['Tipo de MRP'] == "ZS")
            & (self.zs_df['Stat.mat.todos cent.'] != "Z3")
        ]

        # Mapeamento de LMRs
        logger.info("Mapeando LMRs...")
        lmr_map = (
            self.t0182_df.groupby('Material')['Nº LMR']
            .agg(lambda x: ', '.join(sorted(set(x.astype(str)))))
        )
        aplicacoes_map = (
            self.t0182_df.groupby('Material')['Desc. Aplicação']
            .agg(lambda x: '\n'.join(sorted(set(x.astype(str)))))
        )
        self.zs_df['LMR'] = self.zs_df['Material'].map(lmr_map).fillna('Sem LMR vinculada')
        self.zs_df['aplicacoes'] = self.zs_df['Material'].map(aplicacoes_map).fillna('')

        # Verificar se todos os locais estão desativados
        logger.info("Verificando status dos locais...")
        all_d_map = (
            self.t0182_df.groupby('Material')['Local. Ativo/Desat.']
            .agg(lambda x: (x == 'D').all())
        )
        self.zs_df['All_Desat'] = self.zs_df['Material'].map(all_d_map).fillna(False).astype(bool)

        # Flag para abrir consulta
        sem_consulta = self.zs_df['Situação da análise'] == 'N'
        dias_quebra = self.zs_df['Dias da quebra'] > Config.DIAS_QUEBRA_THRESHOLD
        self.zs_df['Abrir_consulta'] = sem_consulta & dias_quebra

        # Exportar relatórios de auditoria
        output_abrir = os.path.join(self.folder_path, "zs_para_consulta.xlsx")
        self.zs_df[self.zs_df['Abrir_consulta']].to_excel(output_abrir, index=False)
        logger.info("Relatório de consultas a abrir exportado: %s", output_abrir)

        output_em = os.path.join(self.folder_path, "zs_em_consulta.xlsx")
        self.zs_df[~sem_consulta].to_excel(output_em, index=False)
        logger.info("Relatório de consultas em andamento exportado: %s", output_em)

        logger.info("Processamento concluído.")

    def get_items_to_open(self):
        return self.zs_df[self.zs_df['Abrir_consulta']].copy()

    def get_items_in_consultation(self):
        return self.zs_df[self.zs_df['Situação da análise'] == 'E'].copy()
