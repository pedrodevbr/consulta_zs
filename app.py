"""
Consultas ZS — Itaipu Binacional
CustomTkinter GUI: one material at a time, LLM-powered analysis.
"""

import logging
import threading
from datetime import datetime

import customtkinter as ctk

from config import Config, setup_logging
from process_manager import ProcessManager
from llm_service import analyze_material

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")

# ── Palette ───────────────────────────────────────────────────────
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


# ── Main App ──────────────────────────────────────────────────────
class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Consultas ZS — Itaipu Binacional")
        self.geometry("1000x680")
        self.minsize(800, 550)
        self.configure(fg_color=_P["bg"])

        self.manager = ProcessManager(use_com_init=True)

        # Data lists — populated after loading
        self._new_items = []       # rows for "Novas Consultas"
        self._open_items = []      # rows for "Em Consulta"
        self._new_idx = 0
        self._open_idx = 0

        # Current LLM analysis cache {material_code: dict}
        self._analysis_cache = {}

        self._build_layout()
        self._attach_logger()
        logger.info("Sistema iniciado.")

    # ── Layout ────────────────────────────────────────────────────

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ── Sidebar ───────────────────────────────────────────────
        sidebar = ctk.CTkFrame(self, width=240, corner_radius=0,
                               fg_color=_P["surface"])
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(7, weight=1)
        sidebar.grid_propagate(False)

        ctk.CTkLabel(
            sidebar, text="CONSULTAS ZS",
            font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
            text_color=_P["accent"],
        ).grid(row=0, column=0, padx=20, pady=(24, 2), sticky="w")
        ctk.CTkLabel(
            sidebar, text="Gestão de Materiais Críticos",
            font=ctk.CTkFont(size=10), text_color=_P["text_dim"],
        ).grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        ctk.CTkFrame(sidebar, height=1, fg_color=_P["border"]
                      ).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))

        btn = dict(height=38, corner_radius=8, border_width=0,
                   font=ctk.CTkFont(size=12, weight="bold"))

        self.btn_extract = ctk.CTkButton(
            sidebar, text="Extrair SAP", fg_color=_P["surface_alt"],
            hover_color=_P["border"], text_color=_P["text"],
            command=self._on_extract, **btn)
        self.btn_extract.grid(row=3, column=0, padx=16, pady=(0, 6), sticky="ew")

        self.btn_load = ctk.CTkButton(
            sidebar, text="Carregar Dados", fg_color=_P["accent"],
            hover_color=_P["accent_hover"], text_color=_P["bg"],
            command=self._on_load, **btn)
        self.btn_load.grid(row=4, column=0, padx=16, pady=(0, 6), sticky="ew")

        self.btn_check = ctk.CTkButton(
            sidebar, text="Verificar Abertas", fg_color=_P["surface_alt"],
            hover_color=_P["border"], text_color=_P["text"],
            command=self._on_check, state="disabled", **btn)
        self.btn_check.grid(row=5, column=0, padx=16, pady=(0, 6), sticky="ew")

        ctk.CTkFrame(sidebar, height=1, fg_color=_P["border"]
                      ).grid(row=6, column=0, sticky="ew", padx=16, pady=8)

        # Stats
        sf = ctk.CTkFrame(sidebar, fg_color="transparent")
        sf.grid(row=7, column=0, padx=20, sticky="new")
        self.lbl_total = self._stat(sf, "Total ZS", 0)
        self.lbl_new = self._stat(sf, "Novas", 1)
        self.lbl_open = self._stat(sf, "Em consulta", 2)

        ctk.CTkLabel(
            sidebar, text=f"v3.0 — {datetime.now():%Y}",
            font=ctk.CTkFont(size=9), text_color=_P["text_dim"],
        ).grid(row=8, column=0, padx=20, pady=(0, 12), sticky="s")

        # ── Main area ─────────────────────────────────────────────
        main = ctk.CTkFrame(self, fg_color=_P["bg"], corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(
            main, fg_color=_P["surface"],
            segmented_button_fg_color=_P["surface_alt"],
            segmented_button_selected_color=_P["accent"],
            segmented_button_selected_hover_color=_P["accent_hover"],
            segmented_button_unselected_color=_P["surface_alt"],
            segmented_button_unselected_hover_color=_P["border"],
            text_color=_P["bg"], corner_radius=10,
            border_width=1, border_color=_P["border"])
        self.tabview.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")

        self.tab_new = self.tabview.add("Novas Consultas")
        self.tab_open = self.tabview.add("Em Consulta")
        self.tab_log = self.tabview.add("Console")

        for tab in (self.tab_new, self.tab_open, self.tab_log):
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

        # ── Novas Consultas — single-item view ────────────────────
        self.new_frame = ctk.CTkFrame(self.tab_new, fg_color="transparent")
        self.new_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.new_frame.grid_rowconfigure(0, weight=1)
        self.new_frame.grid_columnconfigure(0, weight=1)
        self._new_placeholder("Carregue os dados para começar.")

        # ── Em Consulta — single-item view ────────────────────────
        self.open_frame = ctk.CTkFrame(self.tab_open, fg_color="transparent")
        self.open_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.open_frame.grid_rowconfigure(0, weight=1)
        self.open_frame.grid_columnconfigure(0, weight=1)
        self._open_placeholder("Carregue os dados para começar.")

        # ── Console ───────────────────────────────────────────────
        self.log_box = ctk.CTkTextbox(
            self.tab_log, font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=_P["bg"], text_color=_P["accent"],
            border_width=1, border_color=_P["border"],
            corner_radius=6, state="disabled")
        self.log_box.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

    # ── Helpers ───────────────────────────────────────────────────

    def _stat(self, parent, title, row):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", pady=2)
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=10),
                     text_color=_P["text_dim"]).pack(side="left")
        lbl = ctk.CTkLabel(f, text="—", font=ctk.CTkFont(size=12, weight="bold"),
                           text_color=_P["accent"])
        lbl.pack(side="right")
        return lbl

    def _attach_logger(self):
        h = TextboxLogHandler(self.log_box)
        h.setFormatter(logging.Formatter("%(asctime)s — %(levelname)s — %(message)s"))
        logging.getLogger().addHandler(h)

    def _clear(self, frame):
        for w in frame.winfo_children():
            w.destroy()

    def _new_placeholder(self, text):
        self._clear(self.new_frame)
        ctk.CTkLabel(self.new_frame, text=text, font=ctk.CTkFont(size=12),
                     text_color=_P["text_dim"]).place(relx=0.5, rely=0.5, anchor="center")

    def _open_placeholder(self, text):
        self._clear(self.open_frame)
        ctk.CTkLabel(self.open_frame, text=text, font=ctk.CTkFont(size=12),
                     text_color=_P["text_dim"]).place(relx=0.5, rely=0.5, anchor="center")

    def _update_stats(self):
        total = len(self.manager.processor.zs_df)
        self.lbl_total.configure(text=str(total))
        self.lbl_new.configure(text=str(len(self._new_items)))
        self.lbl_open.configure(text=str(len(self._open_items)))

    @staticmethod
    def _severity_color(dias):
        try:
            d = int(dias)
        except (ValueError, TypeError):
            return _P["text_dim"]
        if d > 120:
            return _P["danger"]
        if d > 90:
            return _P["warn"]
        return _P["accent"]

    @staticmethod
    def _conf_color(conf):
        if conf == "alta":
            return _P["accent"]
        if conf == "media":
            return _P["warn"]
        return _P["danger"]

    # ── Thread wrappers ───────────────────────────────────────────

    def _on_extract(self):
        self.btn_extract.configure(state="disabled", text="Extraindo…")
        self.tabview.set("Console")
        def _w():
            try:
                self.manager.extract_sap_reports()
            except Exception as e:
                logger.error("Erro extração: %s", e)
            self.btn_extract.after(0, lambda: self.btn_extract.configure(
                state="normal", text="Extrair SAP"))
        threading.Thread(target=_w, daemon=True).start()

    def _on_load(self):
        self.btn_load.configure(state="disabled", text="Processando…")
        def _w():
            self.manager.init_connections()
            if self.manager.run_data_pipeline():
                new = self.manager.processor.get_items_to_open()
                opn = self.manager.processor.get_items_in_consultation()
                self._new_items = [row for _, row in new.iterrows()]
                self._open_items = [row for _, row in opn.iterrows()]
                self._new_idx = 0
                self._open_idx = 0
                self._analysis_cache.clear()
                self.after(0, self._update_stats)
                self.after(0, self._show_new_item)
                self.after(0, self._show_open_item)
                self.btn_check.after(0, lambda: self.btn_check.configure(state="normal"))
                logger.info("Dados carregados — %d novas, %d em consulta.",
                            len(self._new_items), len(self._open_items))
            else:
                logger.error("Falha ao carregar planilhas.")
            self.btn_load.after(0, lambda: self.btn_load.configure(
                state="normal", text="Carregar Dados"))
        threading.Thread(target=_w, daemon=True).start()

    def _on_check(self):
        self.btn_check.configure(state="disabled", text="Verificando…")
        self.tabview.set("Console")
        def _w():
            self.manager.check_open_consultations()
            logger.info("Verificação concluída.")
            self.btn_check.after(0, lambda: self.btn_check.configure(
                state="normal", text="Verificar Abertas"))
        threading.Thread(target=_w, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    # NOVAS CONSULTAS — one at a time
    # ══════════════════════════════════════════════════════════════

    def _show_new_item(self):
        self._clear(self.new_frame)
        if not self._new_items:
            self._new_placeholder("Nenhum item pendente.")
            return
        if self._new_idx >= len(self._new_items):
            self._new_placeholder("Todos os itens foram processados.")
            return

        row = self._new_items[self._new_idx]
        mat = str(row[Config.ZS_MATERIAL])
        desc = row.get(Config.ZS_TXT_BREVE, "")
        dias = row.get("Dias da quebra", "?")
        estoque = row.get(Config.ZS_UTILIZACAO_LIVRE, "?")
        lmr = row.get("LMR", "—")
        apps = row.get("aplicacoes", "")

        # Scrollable container
        scroll = ctk.CTkScrollableFrame(self.new_frame, fg_color="transparent",
                                         scrollbar_button_color=_P["border"])
        scroll.grid(row=0, column=0, sticky="nsew")

        # ── Navigation bar ────────────────────────────────────────
        nav = ctk.CTkFrame(scroll, fg_color="transparent")
        nav.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            nav, text="< Anterior", width=90, height=28, corner_radius=6,
            fg_color=_P["surface_alt"], hover_color=_P["border"],
            text_color=_P["text"], font=ctk.CTkFont(size=11),
            command=self._new_prev,
            state="normal" if self._new_idx > 0 else "disabled",
        ).pack(side="left")

        ctk.CTkLabel(
            nav, text=f"{self._new_idx + 1} / {len(self._new_items)}",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=_P["text"],
        ).pack(side="left", padx=12)

        ctk.CTkButton(
            nav, text="Próximo >", width=90, height=28, corner_radius=6,
            fg_color=_P["surface_alt"], hover_color=_P["border"],
            text_color=_P["text"], font=ctk.CTkFont(size=11),
            command=self._new_next,
            state="normal" if self._new_idx < len(self._new_items) - 1 else "disabled",
        ).pack(side="left")

        # ── Material info ─────────────────────────────────────────
        info = ctk.CTkFrame(scroll, fg_color=_P["card_bg"], corner_radius=8)
        info.pack(fill="x", pady=(0, 6))

        # Title
        ctk.CTkLabel(
            info, text=f"{mat}  —  {desc}",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            text_color=_P["accent"],
        ).pack(anchor="w", padx=12, pady=(10, 4))

        # Pills
        pills = ctk.CTkFrame(info, fg_color="transparent")
        pills.pack(fill="x", padx=12, pady=(0, 4))
        for label, val, color in [
            ("Dias quebra", dias, self._severity_color(dias)),
            ("Estoque", estoque, _P["text"]),
        ]:
            p = ctk.CTkFrame(pills, fg_color=_P["surface_alt"], corner_radius=4)
            p.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(p, text=f" {label}: {val} ", font=ctk.CTkFont(size=10),
                         text_color=color).pack(padx=4, pady=2)

        # LMR + Apps
        if lmr:
            ctk.CTkLabel(info, text=f"LMR: {lmr}", font=ctk.CTkFont(size=10),
                         text_color=_P["text_dim"], wraplength=600,
                         anchor="w").pack(fill="x", padx=12, pady=(0, 2))
        if apps:
            ctk.CTkLabel(info, text=f"Aplicações: {apps[:200]}", font=ctk.CTkFont(size=10),
                         text_color=_P["text_dim"], wraplength=600, anchor="w",
                         justify="left").pack(fill="x", padx=12, pady=(0, 8))
        else:
            # padding
            ctk.CTkFrame(info, height=4, fg_color="transparent").pack()

        # ── Action buttons ────────────────────────────────────────
        btns = ctk.CTkFrame(scroll, fg_color="transparent")
        btns.pack(fill="x", pady=(0, 8))

        self._btn_approve = ctk.CTkButton(
            btns, text="Criar Chamado", height=34, corner_radius=6,
            fg_color=_P["accent"], hover_color=_P["accent_hover"],
            text_color=_P["bg"], font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._approve_new(row))
        self._btn_approve.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btns, text="Pular", height=34, corner_radius=6, width=80,
            fg_color=_P["surface_alt"], hover_color=_P["danger_hover"],
            text_color=_P["danger"], font=ctk.CTkFont(size=11),
            command=self._skip_new).pack(side="left")

        # ── LLM analysis area ─────────────────────────────────────
        self._llm_frame_new = ctk.CTkFrame(scroll, fg_color=_P["surface_alt"],
                                           corner_radius=8)
        self._llm_frame_new.pack(fill="x", pady=(0, 6))

        # ── Tickets area ──────────────────────────────────────────
        self._tickets_frame_new = ctk.CTkFrame(scroll, fg_color="transparent")
        self._tickets_frame_new.pack(fill="x")

        # Kick off async loading
        self._load_new_analysis(mat, row)

    def _load_new_analysis(self, material, row):
        """Load tickets + LLM analysis for a new-consultation item."""
        ctk.CTkLabel(
            self._llm_frame_new, text="Analisando com IA…",
            font=ctk.CTkFont(size=11), text_color=_P["warn"],
        ).pack(padx=12, pady=8)

        def _work():
            # Fetch tickets
            tickets = []
            try:
                issues = self.manager.jira.search_tickets(material, max_results=10)
                for iss in issues:
                    tickets.append(self.manager.jira.get_ticket_details(iss))
            except Exception as e:
                logger.error("Erro buscando tickets %s: %s", material, e)

            # LLM analysis
            mat_info = {
                "codigo": material,
                "descricao": row.get(Config.ZS_TXT_BREVE, ""),
                "dias_quebra": row.get("Dias da quebra", "?"),
                "estoque": row.get(Config.ZS_UTILIZACAO_LIVRE, "?"),
                "lmr": row.get("LMR", ""),
                "aplicacoes": row.get("aplicacoes", ""),
                "all_desat": row.get("All_Desat", False),
            }

            if material in self._analysis_cache:
                analysis = self._analysis_cache[material]
            else:
                analysis = analyze_material(mat_info, tickets)
                self._analysis_cache[material] = analysis

            def _update():
                self._render_llm_result(self._llm_frame_new, analysis)
                self._render_tickets(self._tickets_frame_new, tickets)
            self.after(0, _update)

        threading.Thread(target=_work, daemon=True).start()

    def _render_llm_result(self, frame, analysis):
        """Render LLM analysis result inside frame."""
        self._clear(frame)

        # Header
        ctk.CTkLabel(
            frame, text="Análise IA",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=_P["text"],
        ).pack(anchor="w", padx=12, pady=(8, 4))

        # Recommendation
        acao = analysis.get("acao", "—")
        conf = analysis.get("confianca", "baixa")
        resolvido = analysis.get("resolvido")
        abrir = analysis.get("abrir_nova")
        justificativa = analysis.get("justificativa", "")

        # Action line
        action_frame = ctk.CTkFrame(frame, fg_color="transparent")
        action_frame.pack(fill="x", padx=12, pady=(0, 2))

        ctk.CTkLabel(
            action_frame, text="Recomendação:",
            font=ctk.CTkFont(size=10), text_color=_P["text_dim"],
        ).pack(side="left")
        ctk.CTkLabel(
            action_frame, text=f" {acao}",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=_P["text"],
        ).pack(side="left")

        # Status pills
        pills = ctk.CTkFrame(frame, fg_color="transparent")
        pills.pack(fill="x", padx=12, pady=(0, 2))

        if resolvido is not None:
            color = _P["accent"] if resolvido else _P["warn"]
            text = "Resolvido" if resolvido else "Não resolvido"
            p = ctk.CTkFrame(pills, fg_color=_P["bg"], corner_radius=4)
            p.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(p, text=f" {text} ", font=ctk.CTkFont(size=10),
                         text_color=color).pack(padx=4, pady=2)

        if abrir is not None:
            color = _P["accent"] if abrir else _P["danger"]
            text = "Abrir nova: Sim" if abrir else "Abrir nova: Não"
            p = ctk.CTkFrame(pills, fg_color=_P["bg"], corner_radius=4)
            p.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(p, text=f" {text} ", font=ctk.CTkFont(size=10),
                         text_color=color).pack(padx=4, pady=2)

        # Confidence
        p = ctk.CTkFrame(pills, fg_color=_P["bg"], corner_radius=4)
        p.pack(side="left")
        ctk.CTkLabel(p, text=f" Confiança: {conf} ", font=ctk.CTkFont(size=10),
                     text_color=self._conf_color(conf)).pack(padx=4, pady=2)

        # Justification
        if justificativa:
            ctk.CTkLabel(
                frame, text=justificativa, font=ctk.CTkFont(size=10),
                text_color=_P["text_dim"], wraplength=600, anchor="w", justify="left",
            ).pack(fill="x", padx=12, pady=(2, 8))
        else:
            ctk.CTkFrame(frame, height=6, fg_color="transparent").pack()

    def _render_tickets(self, frame, tickets):
        """Render ticket list with comments."""
        self._clear(frame)
        if not tickets:
            ctk.CTkLabel(frame, text="Nenhum ticket JIRA existente.",
                         font=ctk.CTkFont(size=11), text_color=_P["text_dim"],
                         ).pack(anchor="w", pady=4)
            return

        ctk.CTkLabel(frame, text=f"Tickets existentes ({len(tickets)})",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=_P["text"]).pack(anchor="w", pady=(0, 4))

        for t in tickets:
            self._render_single_ticket(frame, t)

    def _render_single_ticket(self, parent, t):
        """Render a single ticket card with comments."""
        card = ctk.CTkFrame(parent, fg_color=_P["card_bg"], corner_radius=6,
                            border_width=1, border_color=_P["border"])
        card.pack(fill="x", pady=3)

        # Header
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(6, 2))

        ctk.CTkLabel(hdr, text=t["key"],
                     font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                     text_color=_P["accent"]).pack(side="left")

        s_color = _P["accent"] if "done" in t["status"].lower() or "termin" in t["status"].lower() else _P["warn"]
        ctk.CTkLabel(hdr, text=f"  [{t['status']}]",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=s_color).pack(side="left")

        ctk.CTkLabel(hdr, text=f"  {t['assignee']}",
                     font=ctk.CTkFont(size=10),
                     text_color=_P["text_dim"]).pack(side="left")

        ctk.CTkLabel(hdr, text=t["updated"][:10],
                     font=ctk.CTkFont(size=10),
                     text_color=_P["text_dim"]).pack(side="right")

        # Comments
        comments = t.get("comments", [])
        if comments:
            for c in comments[-3:]:  # show last 3 comments
                cf = ctk.CTkFrame(card, fg_color=_P["surface_alt"], corner_radius=4)
                cf.pack(fill="x", padx=10, pady=2)

                top = ctk.CTkFrame(cf, fg_color="transparent")
                top.pack(fill="x", padx=8, pady=(4, 0))
                ctk.CTkLabel(top, text=c.get("author", "?"),
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=_P["accent"]).pack(side="left")
                ctk.CTkLabel(top, text=c.get("created", "")[:10],
                             font=ctk.CTkFont(size=9),
                             text_color=_P["text_dim"]).pack(side="right")

                body = c.get("body", "")
                if len(body) > 300:
                    body = body[:297] + "…"
                ctk.CTkLabel(cf, text=body, font=ctk.CTkFont(size=10),
                             text_color=_P["text"], wraplength=550,
                             anchor="w", justify="left",
                             ).pack(fill="x", padx=8, pady=(0, 4))

            if len(comments) > 3:
                ctk.CTkLabel(card, text=f"+ {len(comments) - 3} comentário(s) anteriores",
                             font=ctk.CTkFont(size=9), text_color=_P["text_dim"],
                             ).pack(padx=10, pady=(0, 4))
        else:
            ctk.CTkLabel(card, text="Sem comentários", font=ctk.CTkFont(size=10),
                         text_color=_P["text_dim"]).pack(padx=10, pady=(0, 6))

    # ── New-item navigation ───────────────────────────────────────

    def _new_prev(self):
        if self._new_idx > 0:
            self._new_idx -= 1
            self._show_new_item()

    def _new_next(self):
        if self._new_idx < len(self._new_items) - 1:
            self._new_idx += 1
            self._show_new_item()

    def _skip_new(self):
        self._new_items.pop(self._new_idx)
        if self._new_idx >= len(self._new_items):
            self._new_idx = max(0, len(self._new_items) - 1)
        self._update_stats()
        self._show_new_item()

    def _approve_new(self, row):
        self._btn_approve.configure(state="disabled", text="Criando…")
        def _w():
            ok = self.manager.process_single_ticket(row)
            def _done():
                if ok:
                    self._new_items.pop(self._new_idx)
                    if self._new_idx >= len(self._new_items):
                        self._new_idx = max(0, len(self._new_items) - 1)
                    self._update_stats()
                    self._show_new_item()
                else:
                    self._btn_approve.configure(state="normal", text="Criar Chamado")
                    logger.warning("Falha ao criar chamado.")
            self.after(0, _done)
        threading.Thread(target=_w, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    # EM CONSULTA — one at a time
    # ══════════════════════════════════════════════════════════════

    def _show_open_item(self):
        self._clear(self.open_frame)
        if not self._open_items:
            self._open_placeholder("Nenhum item em consulta.")
            return
        if self._open_idx >= len(self._open_items):
            self._open_idx = 0

        row = self._open_items[self._open_idx]
        mat = str(row[Config.ZS_MATERIAL])
        desc = row.get(Config.ZS_TXT_BREVE, "")
        dias = row.get("Dias da quebra", "?")
        estoque = row.get(Config.ZS_UTILIZACAO_LIVRE, "?")

        scroll = ctk.CTkScrollableFrame(self.open_frame, fg_color="transparent",
                                         scrollbar_button_color=_P["border"])
        scroll.grid(row=0, column=0, sticky="nsew")

        # Nav
        nav = ctk.CTkFrame(scroll, fg_color="transparent")
        nav.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            nav, text="< Anterior", width=90, height=28, corner_radius=6,
            fg_color=_P["surface_alt"], hover_color=_P["border"],
            text_color=_P["text"], font=ctk.CTkFont(size=11),
            command=self._open_prev,
            state="normal" if self._open_idx > 0 else "disabled",
        ).pack(side="left")

        ctk.CTkLabel(
            nav, text=f"{self._open_idx + 1} / {len(self._open_items)}",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=_P["text"],
        ).pack(side="left", padx=12)

        ctk.CTkButton(
            nav, text="Próximo >", width=90, height=28, corner_radius=6,
            fg_color=_P["surface_alt"], hover_color=_P["border"],
            text_color=_P["text"], font=ctk.CTkFont(size=11),
            command=self._open_next,
            state="normal" if self._open_idx < len(self._open_items) - 1 else "disabled",
        ).pack(side="left")

        # Material info
        info = ctk.CTkFrame(scroll, fg_color=_P["card_bg"], corner_radius=8)
        info.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            info, text=f"{mat}  —  {desc}",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            text_color=_P["accent"],
        ).pack(anchor="w", padx=12, pady=(10, 4))

        pills = ctk.CTkFrame(info, fg_color="transparent")
        pills.pack(fill="x", padx=12, pady=(0, 8))
        for label, val, color in [
            ("Dias quebra", dias, self._severity_color(dias)),
            ("Estoque", estoque, _P["text"]),
        ]:
            p = ctk.CTkFrame(pills, fg_color=_P["surface_alt"], corner_radius=4)
            p.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(p, text=f" {label}: {val} ", font=ctk.CTkFont(size=10),
                         text_color=color).pack(padx=4, pady=2)

        # LLM + tickets
        self._llm_frame_open = ctk.CTkFrame(scroll, fg_color=_P["surface_alt"],
                                            corner_radius=8)
        self._llm_frame_open.pack(fill="x", pady=(0, 6))

        self._tickets_frame_open = ctk.CTkFrame(scroll, fg_color="transparent")
        self._tickets_frame_open.pack(fill="x")

        # Load async
        self._load_open_analysis(mat, row)

    def _load_open_analysis(self, material, row):
        ctk.CTkLabel(
            self._llm_frame_open, text="Analisando com IA…",
            font=ctk.CTkFont(size=11), text_color=_P["warn"],
        ).pack(padx=12, pady=8)

        def _work():
            tickets = []
            try:
                issues = self.manager.jira.search_tickets(material, max_results=10)
                for iss in issues:
                    tickets.append(self.manager.jira.get_ticket_details(iss))
            except Exception as e:
                logger.error("Erro buscando tickets %s: %s", material, e)

            mat_info = {
                "codigo": material,
                "descricao": row.get(Config.ZS_TXT_BREVE, ""),
                "dias_quebra": row.get("Dias da quebra", "?"),
                "estoque": row.get(Config.ZS_UTILIZACAO_LIVRE, "?"),
                "lmr": row.get("LMR", ""),
                "aplicacoes": row.get("aplicacoes", ""),
                "all_desat": row.get("All_Desat", False),
            }

            if material in self._analysis_cache:
                analysis = self._analysis_cache[material]
            else:
                analysis = analyze_material(mat_info, tickets)
                self._analysis_cache[material] = analysis

            def _update():
                self._render_llm_result(self._llm_frame_open, analysis)
                self._render_tickets(self._tickets_frame_open, tickets)
            self.after(0, _update)

        threading.Thread(target=_work, daemon=True).start()

    def _open_prev(self):
        if self._open_idx > 0:
            self._open_idx -= 1
            self._show_open_item()

    def _open_next(self):
        if self._open_idx < len(self._open_items) - 1:
            self._open_idx += 1
            self._show_open_item()


# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    setup_logging(log_to_file=True)
    app = App()
    app.mainloop()
