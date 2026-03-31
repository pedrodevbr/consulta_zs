"""
Consultas ZS - Itaipu Binacional
CustomTkinter GUI with enhanced ticket details and comments view.
"""

import logging
import threading
from datetime import datetime

import customtkinter as ctk

from config import setup_logging
from jira_service import JiraService
from process_manager import ProcessManager

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")


# ── Colour palette ────────────────────────────────────────────────
_P = {
    "bg":           "#0F1923",
    "surface":      "#172A3A",
    "surface_alt":  "#1E3448",
    "accent":       "#00D4AA",
    "accent_hover": "#00B894",
    "danger":       "#FF6B6B",
    "danger_hover": "#EE5A5A",
    "warn":         "#FDCB6E",
    "text":         "#E8EDF2",
    "text_dim":     "#8899AA",
    "border":       "#2A4054",
    "success":      "#00D4AA",
    "card_bg":      "#1B3244",
}


# ── Log handler ───────────────────────────────────────────────────
class TextboxLogHandler(logging.Handler):
    def __init__(self, textbox):
        super().__init__()
        self.textbox = textbox

    def emit(self, record):
        msg = self.format(record)
        def _append():
            self.textbox.configure(state="normal")
            self.textbox.insert("end", msg + "\n")
            self.textbox.see("end")
            self.textbox.configure(state="disabled")
        try:
            self.textbox.after(0, _append)
        except Exception:
            pass


# ── Ticket Detail Dialog ─────────────────────────────────────────
class TicketDetailDialog(ctk.CTkToplevel):
    """Shows full ticket details and comments in a modal window."""

    def __init__(self, parent, ticket_details: dict):
        super().__init__(parent)
        self.title(f"Ticket {ticket_details['key']}")
        self.geometry("700x600")
        self.minsize(500, 400)
        self.configure(fg_color=_P["bg"])
        self.transient(parent)
        self.grab_set()

        self._build(ticket_details)

    def _build(self, t):
        scroll = ctk.CTkScrollableFrame(
            self, fg_color=_P["bg"],
            scrollbar_button_color=_P["border"],
            scrollbar_button_hover_color=_P["accent"],
        )
        scroll.pack(fill="both", expand=True, padx=12, pady=12)

        # ── Header ──
        header = ctk.CTkFrame(scroll, fg_color=_P["surface"], corner_radius=10)
        header.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header, text=t["key"],
            font=ctk.CTkFont(family="Consolas", size=20, weight="bold"),
            text_color=_P["accent"],
        ).pack(anchor="w", padx=16, pady=(12, 2))

        ctk.CTkLabel(
            header, text=t["summary"],
            font=ctk.CTkFont(size=14),
            text_color=_P["text"], wraplength=600,
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # ── Info grid ──
        info_frame = ctk.CTkFrame(scroll, fg_color=_P["surface"], corner_radius=10)
        info_frame.pack(fill="x", pady=(0, 10))

        fields = [
            ("Status", t["status"]),
            ("Responsavel", t["assignee"]),
            ("Relator", t["reporter"]),
            ("Prioridade", t["priority"]),
            ("Criado", t["created"][:19].replace("T", " ")),
            ("Atualizado", t["updated"][:19].replace("T", " ")),
            ("Tipo", t["tipo"]),
            ("Pecas em estoque", t["pieces_in_stock"]),
        ]
        for i, (label, value) in enumerate(fields):
            row_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            row_frame.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(
                row_frame, text=f"{label}:", width=140,
                font=ctk.CTkFont(size=11), text_color=_P["text_dim"], anchor="w",
            ).pack(side="left")
            status_color = _P["text"]
            if label == "Status":
                status_color = self._status_color(value)
            ctk.CTkLabel(
                row_frame, text=value or "-",
                font=ctk.CTkFont(size=12, weight="bold" if label == "Status" else "normal"),
                text_color=status_color, anchor="w",
            ).pack(side="left", padx=(4, 0))

        # ── Description ──
        if t.get("description"):
            desc_frame = ctk.CTkFrame(scroll, fg_color=_P["surface"], corner_radius=10)
            desc_frame.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(
                desc_frame, text="Descricao",
                font=ctk.CTkFont(size=13, weight="bold"), text_color=_P["text"],
            ).pack(anchor="w", padx=16, pady=(10, 4))
            desc_text = ctk.CTkTextbox(
                desc_frame, height=100,
                font=ctk.CTkFont(size=12), fg_color=_P["bg"],
                text_color=_P["text"], border_width=0, corner_radius=6,
            )
            desc_text.pack(fill="x", padx=16, pady=(0, 10))
            desc_text.insert("1.0", t["description"])
            desc_text.configure(state="disabled")

        # ── Comments ──
        comments = t.get("comments", [])
        comments_header = ctk.CTkFrame(scroll, fg_color=_P["surface"], corner_radius=10)
        comments_header.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            comments_header,
            text=f"Comentarios ({len(comments)})",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=_P["text"],
        ).pack(anchor="w", padx=16, pady=10)

        if not comments:
            ctk.CTkLabel(
                scroll, text="Nenhum comentario.",
                font=ctk.CTkFont(size=12), text_color=_P["text_dim"],
            ).pack(pady=10)
        else:
            for c in comments:
                self._build_comment_card(scroll, c)

    def _build_comment_card(self, parent, comment):
        card = ctk.CTkFrame(parent, fg_color=_P["card_bg"], corner_radius=8,
                            border_width=1, border_color=_P["border"])
        card.pack(fill="x", pady=3)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(8, 2))

        ctk.CTkLabel(
            top, text=comment.get("author", "?"),
            font=ctk.CTkFont(size=12, weight="bold"), text_color=_P["accent"],
        ).pack(side="left")

        date_str = comment.get("created", "")[:16].replace("T", " ")
        ctk.CTkLabel(
            top, text=date_str,
            font=ctk.CTkFont(size=10), text_color=_P["text_dim"],
        ).pack(side="right")

        ctk.CTkLabel(
            card, text=comment.get("body", ""),
            font=ctk.CTkFont(size=11), text_color=_P["text"],
            wraplength=600, justify="left", anchor="w",
        ).pack(fill="x", padx=12, pady=(2, 10))

    @staticmethod
    def _status_color(status):
        s = status.lower()
        if any(w in s for w in ("done", "terminado", "concluido", "fechado")):
            return _P["success"]
        if any(w in s for w in ("progress", "andamento", "aberto")):
            return _P["warn"]
        return _P["text"]


# ── Main App ─────────────────────────────────────────────────────
class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Consultas ZS  -  Itaipu Binacional")
        self.geometry("1120x720")
        self.minsize(900, 600)
        self.configure(fg_color=_P["bg"])

        self.manager = ProcessManager(use_com_init=True)
        self._card_widgets: list = []

        self._build_layout()
        self._attach_logger()

        logger.info("Sistema iniciado. Clique em Carregar Dados para comecar.")

    # ── Layout ────────────────────────────────────────────────────

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ── Sidebar ───────────────────────────────────────────────
        sidebar = ctk.CTkFrame(
            self, width=260, corner_radius=0,
            fg_color=_P["surface"], border_width=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(8, weight=1)
        sidebar.grid_propagate(False)

        # Logo area
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=20, pady=(28, 4), sticky="ew")
        ctk.CTkLabel(
            logo_frame, text=">>",
            font=ctk.CTkFont(size=28), text_color=_P["accent"],
        ).pack(side="left")
        ctk.CTkLabel(
            logo_frame, text=" CONSULTAS ZS",
            font=ctk.CTkFont(family="Consolas", size=18, weight="bold"),
            text_color=_P["text"],
        ).pack(side="left", padx=(4, 0))

        ctk.CTkLabel(
            sidebar, text="Gestao de Materiais Criticos",
            font=ctk.CTkFont(size=11), text_color=_P["text_dim"],
        ).grid(row=1, column=0, padx=24, pady=(0, 20), sticky="w")

        ctk.CTkFrame(
            sidebar, height=1, fg_color=_P["border"]
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))

        # Buttons
        btn_style = dict(
            height=42, corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"), border_width=0,
        )

        self.btn_extract = ctk.CTkButton(
            sidebar, text="  Extrair Relatorios SAP",
            fg_color=_P["surface_alt"], hover_color=_P["border"],
            text_color=_P["text"], command=self._on_extract, **btn_style,
        )
        self.btn_extract.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="ew")

        self.btn_load = ctk.CTkButton(
            sidebar, text="  Carregar & Processar Dados",
            fg_color=_P["accent"], hover_color=_P["accent_hover"],
            text_color=_P["bg"], command=self._on_load, **btn_style,
        )
        self.btn_load.grid(row=4, column=0, padx=16, pady=(0, 8), sticky="ew")

        self.btn_check = ctk.CTkButton(
            sidebar, text="  Verificar Consultas Abertas",
            fg_color=_P["surface_alt"], hover_color=_P["border"],
            text_color=_P["text"], command=self._on_check,
            state="disabled", **btn_style,
        )
        self.btn_check.grid(row=5, column=0, padx=16, pady=(0, 8), sticky="ew")

        ctk.CTkFrame(
            sidebar, height=1, fg_color=_P["border"]
        ).grid(row=6, column=0, sticky="ew", padx=16, pady=12)

        # Stats panel
        self.stats_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        self.stats_frame.grid(row=7, column=0, padx=20, sticky="ew")

        self.lbl_stat_total = self._stat_label(self.stats_frame, "Total ZS", "-", 0)
        self.lbl_stat_open = self._stat_label(self.stats_frame, "Para abrir", "-", 1)
        self.lbl_stat_progress = self._stat_label(self.stats_frame, "Em consulta", "-", 2)

        ctk.CTkLabel(
            sidebar, text=f"v2.0 - {datetime.now():%Y}",
            font=ctk.CTkFont(size=10), text_color=_P["text_dim"],
        ).grid(row=9, column=0, padx=20, pady=(0, 16), sticky="s")

        # ── Main content ──────────────────────────────────────────
        main = ctk.CTkFrame(self, fg_color=_P["bg"], corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(
            main,
            fg_color=_P["surface"],
            segmented_button_fg_color=_P["surface_alt"],
            segmented_button_selected_color=_P["accent"],
            segmented_button_selected_hover_color=_P["accent_hover"],
            segmented_button_unselected_color=_P["surface_alt"],
            segmented_button_unselected_hover_color=_P["border"],
            text_color=_P["bg"],
            corner_radius=12, border_width=1, border_color=_P["border"],
        )
        self.tabview.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")

        tab_cards = self.tabview.add("  Novas Consultas  ")
        tab_em_consulta = self.tabview.add("  Em Consulta  ")
        tab_logs = self.tabview.add("  Console  ")

        # ── Tab: Novas Consultas ──
        tab_cards.grid_rowconfigure(0, weight=1)
        tab_cards.grid_columnconfigure(0, weight=1)

        self.scroll_cards = ctk.CTkScrollableFrame(
            tab_cards, fg_color="transparent",
            scrollbar_button_color=_P["border"],
            scrollbar_button_hover_color=_P["accent"],
        )
        self.scroll_cards.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        self.lbl_empty = ctk.CTkLabel(
            self.scroll_cards,
            text='Nenhum dado carregado.\nClique em "Carregar & Processar Dados" para iniciar.',
            font=ctk.CTkFont(size=13), text_color=_P["text_dim"], justify="center",
        )
        self.lbl_empty.pack(pady=80)

        # ── Tab: Em Consulta ──
        tab_em_consulta.grid_rowconfigure(0, weight=1)
        tab_em_consulta.grid_columnconfigure(0, weight=1)

        self.scroll_em_consulta = ctk.CTkScrollableFrame(
            tab_em_consulta, fg_color="transparent",
            scrollbar_button_color=_P["border"],
            scrollbar_button_hover_color=_P["accent"],
        )
        self.scroll_em_consulta.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        self.lbl_empty_consulta = ctk.CTkLabel(
            self.scroll_em_consulta,
            text="Nenhum item em consulta.\nCarregue os dados primeiro.",
            font=ctk.CTkFont(size=13), text_color=_P["text_dim"], justify="center",
        )
        self.lbl_empty_consulta.pack(pady=80)

        # ── Tab: Console ──
        tab_logs.grid_rowconfigure(0, weight=1)
        tab_logs.grid_columnconfigure(0, weight=1)

        self.log_textbox = ctk.CTkTextbox(
            tab_logs,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=_P["bg"], text_color=_P["accent"],
            border_width=1, border_color=_P["border"],
            corner_radius=8, state="disabled",
        )
        self.log_textbox.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    # ── Helpers ───────────────────────────────────────────────────

    def _stat_label(self, parent, title, value, row):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", pady=3)
        ctk.CTkLabel(
            frame, text=title,
            font=ctk.CTkFont(size=11), text_color=_P["text_dim"],
        ).pack(side="left")
        lbl = ctk.CTkLabel(
            frame, text=value,
            font=ctk.CTkFont(size=13, weight="bold"), text_color=_P["accent"],
        )
        lbl.pack(side="right")
        return lbl

    def _update_stats(self):
        total = len(self.manager.processor.zs_df)
        to_open = len(self.manager.processor.get_items_to_open())
        in_prog = len(self.manager.processor.get_items_in_consultation())
        self.lbl_stat_total.configure(text=str(total))
        self.lbl_stat_open.configure(text=str(to_open))
        self.lbl_stat_progress.configure(text=str(in_prog))

    def _attach_logger(self):
        handler = TextboxLogHandler(self.log_textbox)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logging.getLogger().addHandler(handler)

    @staticmethod
    def _severity_color(dias):
        try:
            dias = int(dias)
        except (ValueError, TypeError):
            return _P["text_dim"]
        if dias > 120:
            return _P["danger"]
        if dias > 90:
            return _P["warn"]
        return _P["accent"]

    # ── Thread wrappers ───────────────────────────────────────────

    def _on_extract(self):
        self.btn_extract.configure(state="disabled", text="  Extraindo...")
        self.tabview.set("  Console  ")

        def _work():
            try:
                self.manager.extract_sap_reports()
            except Exception as e:
                logger.error("Erro extracao: %s", e)
            self.btn_extract.after(
                0, lambda: self.btn_extract.configure(
                    state="normal", text="  Extrair Relatorios SAP"),
            )

        threading.Thread(target=_work, daemon=True).start()

    def _on_load(self):
        self.btn_load.configure(state="disabled", text="  Processando...")

        def _work():
            self.manager.init_connections()
            if self.manager.run_data_pipeline():
                self.after(0, self._build_cards)
                self.after(0, self._build_em_consulta_cards)
                self.after(0, self._update_stats)
                self.btn_check.after(
                    0, lambda: self.btn_check.configure(state="normal"),
                )
                logger.info('Dados prontos! Veja as abas "Novas Consultas" e "Em Consulta".')
            else:
                logger.error("Falha ao carregar planilhas.")
            self.btn_load.after(
                0, lambda: self.btn_load.configure(
                    state="normal", text="  Atualizar Dados"),
            )

        threading.Thread(target=_work, daemon=True).start()

    def _on_check(self):
        self.btn_check.configure(state="disabled", text="  Verificando...")
        self.tabview.set("  Console  ")

        def _work():
            self.manager.check_open_consultations()
            logger.info("Verificacao concluida.")
            self.after(0, self._build_em_consulta_cards)
            self.btn_check.after(
                0, lambda: self.btn_check.configure(
                    state="normal", text="  Verificar Consultas Abertas"),
            )

        threading.Thread(target=_work, daemon=True).start()

    # ── Card builder — Novas Consultas ────────────────────────────

    def _build_cards(self):
        for w in self.scroll_cards.winfo_children():
            w.destroy()
        self._card_widgets.clear()

        items = self.manager.processor.get_items_to_open()
        if items.empty:
            ctk.CTkLabel(
                self.scroll_cards,
                text="Nenhum item pendente para abrir consulta.",
                font=ctk.CTkFont(size=13), text_color=_P["text_dim"],
            ).pack(pady=60)
            return

        for idx, (_, row) in enumerate(items.iterrows()):
            self._create_card(row, idx)

    def _create_card(self, row, idx: int):
        card = ctk.CTkFrame(
            self.scroll_cards, fg_color=_P["card_bg"],
            corner_radius=10, border_width=1, border_color=_P["border"],
        )
        card.pack(fill="x", padx=8, pady=5)
        card.grid_columnconfigure(1, weight=1)

        material = str(row["Material"])
        desc = row.get("Txt.brv.material", "")
        lmr = row.get("LMR", "-")
        dias = row.get("Dias da quebra", "?")
        estoque = row.get("Utilizacao livre", "?")
        apps = row.get("aplicacoes", "")

        # Left accent bar
        dias_color = self._severity_color(dias)
        ctk.CTkFrame(
            card, width=4, corner_radius=2, fg_color=dias_color,
        ).grid(row=0, column=0, rowspan=3, sticky="ns", padx=(8, 0), pady=10)

        # Info block
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=12, pady=(10, 2))
        info.grid_columnconfigure(0, weight=1)

        # Title row
        title_frame = ctk.CTkFrame(info, fg_color="transparent")
        title_frame.pack(fill="x")
        ctk.CTkLabel(
            title_frame, text=material,
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            text_color=_P["accent"],
        ).pack(side="left")
        ctk.CTkLabel(
            title_frame, text=f"  -  {desc}",
            font=ctk.CTkFont(size=13), text_color=_P["text"],
        ).pack(side="left", padx=(4, 0))

        # Meta row
        meta_frame = ctk.CTkFrame(info, fg_color="transparent")
        meta_frame.pack(fill="x", pady=(4, 0))
        for label, val in [("Dias quebra", dias), ("Estoque", estoque)]:
            pill = ctk.CTkFrame(meta_frame, fg_color=_P["surface_alt"], corner_radius=6)
            pill.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                pill, text=f" {label}: {val} ",
                font=ctk.CTkFont(size=11), text_color=_P["text_dim"],
            ).pack(padx=6, pady=2)

        # LMR + Aplicacoes
        detail_frame = ctk.CTkFrame(card, fg_color="transparent")
        detail_frame.grid(row=1, column=1, sticky="ew", padx=12, pady=(4, 2))

        lmr_display = str(lmr) if len(str(lmr)) < 80 else str(lmr)[:77] + "..."
        ctk.CTkLabel(
            detail_frame, text=f"LMR: {lmr_display}",
            font=ctk.CTkFont(size=11), text_color=_P["text_dim"], anchor="w",
        ).pack(fill="x")

        if apps:
            apps_short = apps if len(apps) < 100 else apps[:97] + "..."
            ctk.CTkLabel(
                detail_frame, text=f"Aplicacoes: {apps_short}",
                font=ctk.CTkFont(size=11), text_color=_P["text_dim"], anchor="w",
            ).pack(fill="x")

        # Existing ticket info (loaded async)
        ticket_info_frame = ctk.CTkFrame(card, fg_color="transparent")
        ticket_info_frame.grid(row=2, column=1, sticky="ew", padx=12, pady=(0, 6))

        # Buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.grid(row=0, column=2, rowspan=3, padx=(0, 12), pady=10)

        btn_approve = ctk.CTkButton(
            btn_frame, text="Criar Chamado", width=140, height=36,
            corner_radius=8, fg_color=_P["accent"], hover_color=_P["accent_hover"],
            text_color=_P["bg"], font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda r=row, c=card: self._approve(r, c),
        )
        btn_approve.pack(pady=(0, 6))

        btn_detail = ctk.CTkButton(
            btn_frame, text="Ver Tickets", width=140, height=30,
            corner_radius=8, fg_color=_P["surface_alt"], hover_color=_P["border"],
            text_color=_P["accent"], font=ctk.CTkFont(size=11),
            command=lambda m=material, f=ticket_info_frame: self._show_existing_tickets(m, f),
        )
        btn_detail.pack(pady=(0, 6))

        btn_skip = ctk.CTkButton(
            btn_frame, text="Pular", width=140, height=30,
            corner_radius=8, fg_color=_P["surface_alt"], hover_color=_P["danger_hover"],
            text_color=_P["danger"], font=ctk.CTkFont(size=11),
            command=lambda c=card: c.destroy(),
        )
        btn_skip.pack()

        self._card_widgets.append(card)

    def _show_existing_tickets(self, material, frame):
        """Search for existing tickets for a material and show inline."""
        for w in frame.winfo_children():
            w.destroy()

        loading = ctk.CTkLabel(
            frame, text="Buscando tickets...",
            font=ctk.CTkFont(size=11), text_color=_P["warn"],
        )
        loading.pack(anchor="w")

        def _work():
            try:
                issues = self.manager.jira.search_tickets(material, max_results=10)
                details_list = []
                for issue in issues:
                    details_list.append(self.manager.jira.get_ticket_details(issue))
            except Exception as e:
                logger.error("Erro buscando tickets para %s: %s", material, e)
                details_list = []

            def _update():
                loading.destroy()
                if not details_list:
                    ctk.CTkLabel(
                        frame, text="Nenhum ticket existente.",
                        font=ctk.CTkFont(size=11), text_color=_P["text_dim"],
                    ).pack(anchor="w")
                    return

                for t in details_list:
                    row_frame = ctk.CTkFrame(frame, fg_color=_P["surface_alt"], corner_radius=6)
                    row_frame.pack(fill="x", pady=2)

                    status_color = TicketDetailDialog._status_color(t["status"])
                    ctk.CTkLabel(
                        row_frame, text=t["key"],
                        font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                        text_color=_P["accent"],
                    ).pack(side="left", padx=(8, 4), pady=4)
                    ctk.CTkLabel(
                        row_frame, text=t["status"],
                        font=ctk.CTkFont(size=11, weight="bold"),
                        text_color=status_color,
                    ).pack(side="left", padx=(0, 8))

                    n_comments = len(t.get("comments", []))
                    ctk.CTkLabel(
                        row_frame, text=f"{n_comments} comentario(s)",
                        font=ctk.CTkFont(size=10), text_color=_P["text_dim"],
                    ).pack(side="left")

                    ctk.CTkButton(
                        row_frame, text="Detalhes", width=70, height=24,
                        corner_radius=4, fg_color=_P["border"],
                        hover_color=_P["accent"], text_color=_P["text"],
                        font=ctk.CTkFont(size=10),
                        command=lambda details=t: TicketDetailDialog(self, details),
                    ).pack(side="right", padx=8, pady=4)

            frame.after(0, _update)

        threading.Thread(target=_work, daemon=True).start()

    # ── Card builder — Em Consulta ────────────────────────────────

    def _build_em_consulta_cards(self):
        for w in self.scroll_em_consulta.winfo_children():
            w.destroy()

        items = self.manager.processor.get_items_in_consultation()
        if items.empty:
            ctk.CTkLabel(
                self.scroll_em_consulta,
                text="Nenhum item em consulta no momento.",
                font=ctk.CTkFont(size=13), text_color=_P["text_dim"],
            ).pack(pady=60)
            return

        for _, row in items.iterrows():
            self._create_em_consulta_card(row)

    def _create_em_consulta_card(self, row):
        card = ctk.CTkFrame(
            self.scroll_em_consulta, fg_color=_P["card_bg"],
            corner_radius=10, border_width=1, border_color=_P["border"],
        )
        card.pack(fill="x", padx=8, pady=5)
        card.grid_columnconfigure(1, weight=1)

        material = str(row["Material"])
        desc = row.get("Txt.brv.material", "")
        lmr = row.get("LMR", "-")
        dias = row.get("Dias da quebra", "?")
        estoque = row.get("Utilizacao livre", "?")

        # Left accent bar
        ctk.CTkFrame(
            card, width=4, corner_radius=2, fg_color=_P["warn"],
        ).grid(row=0, column=0, rowspan=2, sticky="ns", padx=(8, 0), pady=10)

        # Info
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=12, pady=(10, 2))

        title_frame = ctk.CTkFrame(info, fg_color="transparent")
        title_frame.pack(fill="x")
        ctk.CTkLabel(
            title_frame, text=material,
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            text_color=_P["accent"],
        ).pack(side="left")
        ctk.CTkLabel(
            title_frame, text=f"  -  {desc}",
            font=ctk.CTkFont(size=13), text_color=_P["text"],
        ).pack(side="left", padx=(4, 0))

        meta_frame = ctk.CTkFrame(info, fg_color="transparent")
        meta_frame.pack(fill="x", pady=(4, 0))
        for label, val in [("Dias quebra", dias), ("Estoque", estoque)]:
            pill = ctk.CTkFrame(meta_frame, fg_color=_P["surface_alt"], corner_radius=6)
            pill.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                pill, text=f" {label}: {val} ",
                font=ctk.CTkFont(size=11), text_color=_P["text_dim"],
            ).pack(padx=6, pady=2)

        lmr_display = str(lmr) if len(str(lmr)) < 80 else str(lmr)[:77] + "..."
        lmr_frame = ctk.CTkFrame(card, fg_color="transparent")
        lmr_frame.grid(row=1, column=1, sticky="ew", padx=12, pady=(0, 10))
        ctk.CTkLabel(
            lmr_frame, text=f"LMR: {lmr_display}",
            font=ctk.CTkFont(size=11), text_color=_P["text_dim"], anchor="w",
        ).pack(fill="x")

        # Ticket + comments area (loaded async)
        ticket_area = ctk.CTkFrame(card, fg_color="transparent")
        ticket_area.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=(0, 12), pady=10)

        loading = ctk.CTkLabel(
            ticket_area, text="Carregando ticket...",
            font=ctk.CTkFont(size=11), text_color=_P["text_dim"],
        )
        loading.pack(anchor="w")

        def _load_ticket():
            try:
                issues = self.manager.jira.search_tickets(material, max_results=1)
                if issues:
                    details = self.manager.jira.get_ticket_details(issues[0])
                else:
                    details = None
            except Exception:
                details = None

            def _update():
                loading.destroy()
                if not details:
                    ctk.CTkLabel(
                        ticket_area, text="Sem ticket vinculado",
                        font=ctk.CTkFont(size=11), text_color=_P["danger"],
                    ).pack(anchor="w")
                    return

                # Ticket key + status
                header = ctk.CTkFrame(ticket_area, fg_color="transparent")
                header.pack(fill="x")
                ctk.CTkLabel(
                    header, text=details["key"],
                    font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                    text_color=_P["accent"],
                ).pack(side="left")
                status_color = TicketDetailDialog._status_color(details["status"])
                ctk.CTkLabel(
                    header, text=f"  [{details['status']}]",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=status_color,
                ).pack(side="left")

                # Last comment preview
                comments = details.get("comments", [])
                if comments:
                    last = comments[-1]
                    preview = last["body"][:120] + "..." if len(last["body"]) > 120 else last["body"]
                    ctk.CTkLabel(
                        ticket_area,
                        text=f'{last["author"]}: {preview}',
                        font=ctk.CTkFont(size=10), text_color=_P["text_dim"],
                        wraplength=300, anchor="w", justify="left",
                    ).pack(fill="x", pady=(4, 0))

                ctk.CTkButton(
                    ticket_area, text="Ver Detalhes", width=100, height=26,
                    corner_radius=4, fg_color=_P["border"],
                    hover_color=_P["accent"], text_color=_P["text"],
                    font=ctk.CTkFont(size=10),
                    command=lambda d=details: TicketDetailDialog(self, d),
                ).pack(anchor="w", pady=(6, 0))

            ticket_area.after(0, _update)

        threading.Thread(target=_load_ticket, daemon=True).start()

    # ── Approve / Process ─────────────────────────────────────────

    def _approve(self, row, card):
        for w in card.winfo_children():
            if isinstance(w, ctk.CTkFrame):
                for child in w.winfo_children():
                    if isinstance(child, ctk.CTkButton):
                        child.configure(state="disabled")

        def _work():
            ok = self.manager.process_single_ticket(row)
            if ok:
                card.after(0, card.destroy)
                self.after(0, self._update_stats)
            else:
                def _re():
                    for w in card.winfo_children():
                        if isinstance(w, ctk.CTkFrame):
                            for child in w.winfo_children():
                                if isinstance(child, ctk.CTkButton):
                                    child.configure(state="normal")
                card.after(0, _re)
                logger.warning("Falha ao processar %s.", row["Material"])

        threading.Thread(target=_work, daemon=True).start()


# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    setup_logging(log_to_file=True)
    app = App()
    app.mainloop()
