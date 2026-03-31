"""
Consultas ZS — Itaipu Binacional
CustomTkinter GUI: one material at a time, LLM-powered analysis.
"""

import logging
import threading
import webbrowser
from datetime import datetime

import customtkinter as ctk

from config import Config, setup_logging
from process_manager import ProcessManager
from llm_service import analyze_material

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")

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

JIRA_BROWSE = f"{Config.JIRA_SERVER}/browse/"


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


class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Consultas ZS — Itaipu Binacional")
        self.geometry("960x650")
        self.minsize(760, 500)
        self.configure(fg_color=_P["bg"])

        self.manager = ProcessManager(use_com_init=True)
        self._new_items = []
        self._open_items = []
        self._new_idx = 0
        self._open_idx = 0
        self._analysis_cache = {}

        self._build_layout()
        self._attach_logger()
        logger.info("Sistema iniciado.")

    # ── Layout ────────────────────────────────────────────────────

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Sidebar
        sb = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=_P["surface"])
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_rowconfigure(7, weight=1)
        sb.grid_propagate(False)

        ctk.CTkLabel(sb, text="CONSULTAS ZS",
                     font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
                     text_color=_P["accent"]).grid(row=0, column=0, padx=16, pady=(20, 12), sticky="w")

        btn = dict(height=34, corner_radius=6, border_width=0,
                   font=ctk.CTkFont(size=11, weight="bold"))

        self.btn_extract = ctk.CTkButton(sb, text="Extrair SAP",
            fg_color=_P["surface_alt"], hover_color=_P["border"],
            text_color=_P["text"], command=self._on_extract, **btn)
        self.btn_extract.grid(row=1, column=0, padx=12, pady=(0, 4), sticky="ew")

        self.btn_load = ctk.CTkButton(sb, text="Carregar Dados",
            fg_color=_P["accent"], hover_color=_P["accent_hover"],
            text_color=_P["bg"], command=self._on_load, **btn)
        self.btn_load.grid(row=2, column=0, padx=12, pady=(0, 4), sticky="ew")

        self.btn_check = ctk.CTkButton(sb, text="Verificar Abertas",
            fg_color=_P["surface_alt"], hover_color=_P["border"],
            text_color=_P["text"], command=self._on_check, state="disabled", **btn)
        self.btn_check.grid(row=3, column=0, padx=12, pady=(0, 4), sticky="ew")

        ctk.CTkFrame(sb, height=1, fg_color=_P["border"]).grid(
            row=4, column=0, sticky="ew", padx=12, pady=8)

        sf = ctk.CTkFrame(sb, fg_color="transparent")
        sf.grid(row=5, column=0, padx=16, sticky="new")
        self.lbl_total = self._stat(sf, "Total ZS", 0)
        self.lbl_new = self._stat(sf, "Novas", 1)
        self.lbl_open = self._stat(sf, "Em consulta", 2)

        # Main
        main = ctk.CTkFrame(self, fg_color=_P["bg"], corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(main, fg_color=_P["surface"],
            segmented_button_fg_color=_P["surface_alt"],
            segmented_button_selected_color=_P["accent"],
            segmented_button_selected_hover_color=_P["accent_hover"],
            segmented_button_unselected_color=_P["surface_alt"],
            segmented_button_unselected_hover_color=_P["border"],
            text_color=_P["bg"], corner_radius=8,
            border_width=1, border_color=_P["border"])
        self.tabview.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.tab_new = self.tabview.add("Novas")
        self.tab_open = self.tabview.add("Em Consulta")
        self.tab_log = self.tabview.add("Console")

        for tab in (self.tab_new, self.tab_open, self.tab_log):
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

        self.new_frame = ctk.CTkFrame(self.tab_new, fg_color="transparent")
        self.new_frame.grid(row=0, column=0, sticky="nsew")
        self.new_frame.grid_rowconfigure(0, weight=1)
        self.new_frame.grid_columnconfigure(0, weight=1)
        self._placeholder(self.new_frame, "Carregue os dados para começar.")

        self.open_frame = ctk.CTkFrame(self.tab_open, fg_color="transparent")
        self.open_frame.grid(row=0, column=0, sticky="nsew")
        self.open_frame.grid_rowconfigure(0, weight=1)
        self.open_frame.grid_columnconfigure(0, weight=1)
        self._placeholder(self.open_frame, "Carregue os dados para começar.")

        self.log_box = ctk.CTkTextbox(self.tab_log,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=_P["bg"], text_color=_P["accent"],
            border_width=1, border_color=_P["border"],
            corner_radius=6, state="disabled")
        self.log_box.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

    # ── Helpers ───────────────────────────────────────────────────

    def _stat(self, parent, title, row):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", pady=1)
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=10),
                     text_color=_P["text_dim"]).pack(side="left")
        lbl = ctk.CTkLabel(f, text="—", font=ctk.CTkFont(size=11, weight="bold"),
                           text_color=_P["accent"])
        lbl.pack(side="right")
        return lbl

    def _attach_logger(self):
        h = TextboxLogHandler(self.log_box)
        h.setFormatter(logging.Formatter("%(asctime)s — %(message)s"))
        logging.getLogger().addHandler(h)

    def _clear(self, frame):
        for w in frame.winfo_children():
            w.destroy()

    def _placeholder(self, frame, text):
        self._clear(frame)
        ctk.CTkLabel(frame, text=text, font=ctk.CTkFont(size=12),
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
        return _P["danger"] if d > 120 else _P["warn"] if d > 90 else _P["accent"]

    @staticmethod
    def _conf_color(conf):
        return {"alta": _P["accent"], "media": _P["warn"]}.get(conf, _P["danger"])

    @staticmethod
    def _open_jira(key):
        webbrowser.open(f"{JIRA_BROWSE}{key}")

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
                logger.info("%d novas, %d em consulta.", len(self._new_items), len(self._open_items))
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

    # ── Shared: material info block ───────────────────────────────

    def _render_material_info(self, parent, row):
        """Render the material header + pills. Returns the frame."""
        mat = str(row[Config.ZS_MATERIAL])
        desc = row.get(Config.ZS_TXT_BREVE, "")
        dias = row.get("Dias da quebra", "?")
        estoque = row.get(Config.ZS_UTILIZACAO_LIVRE, "?")
        ordem = row.get(Config.ZS_ORDEM_PLANEJADA, "")
        req = row.get(Config.ZS_REQ_COMPRA, "")
        pedido = row.get(Config.ZS_PEDIDO, "")

        f = ctk.CTkFrame(parent, fg_color=_P["card_bg"], corner_radius=8)
        f.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(f, text=f"{mat}  —  {desc}",
                     font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
                     text_color=_P["accent"]).pack(anchor="w", padx=12, pady=(8, 4))

        pills = ctk.CTkFrame(f, fg_color="transparent")
        pills.pack(fill="x", padx=12, pady=(0, 6))

        pill_data = [
            ("Dias", dias, self._severity_color(dias)),
            ("Estoque", estoque, _P["text"]),
        ]
        if ordem:
            pill_data.append(("Ord.Plan.", ordem, _P["warn"]))
        if req:
            pill_data.append(("Req.Compra", req, _P["text_dim"]))
        if pedido:
            pill_data.append(("Pedido", pedido, _P["text_dim"]))

        for label, val, color in pill_data:
            p = ctk.CTkFrame(pills, fg_color=_P["surface_alt"], corner_radius=4)
            p.pack(side="left", padx=(0, 4))
            ctk.CTkLabel(p, text=f" {label}: {val} ", font=ctk.CTkFont(size=10),
                         text_color=color).pack(padx=3, pady=1)

        return f

    # ── Shared: navigation bar ────────────────────────────────────

    def _render_nav(self, parent, idx, total, prev_cmd, next_cmd):
        nav = ctk.CTkFrame(parent, fg_color="transparent")
        nav.pack(fill="x", pady=(0, 6))

        ctk.CTkButton(nav, text="<", width=40, height=26, corner_radius=4,
                      fg_color=_P["surface_alt"], hover_color=_P["border"],
                      text_color=_P["text"], font=ctk.CTkFont(size=11),
                      command=prev_cmd,
                      state="normal" if idx > 0 else "disabled").pack(side="left")

        ctk.CTkLabel(nav, text=f" {idx + 1}/{total} ",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=_P["text"]).pack(side="left", padx=4)

        ctk.CTkButton(nav, text=">", width=40, height=26, corner_radius=4,
                      fg_color=_P["surface_alt"], hover_color=_P["border"],
                      text_color=_P["text"], font=ctk.CTkFont(size=11),
                      command=next_cmd,
                      state="normal" if idx < total - 1 else "disabled").pack(side="left")

    # ── Shared: LLM result ────────────────────────────────────────

    def _render_llm(self, frame, analysis):
        self._clear(frame)

        acao = analysis.get("acao", "—")
        conf = analysis.get("confianca", "baixa")
        resolvido = analysis.get("resolvido")
        abrir = analysis.get("abrir_nova")
        justificativa = analysis.get("justificativa", "")

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(6, 2))

        ctk.CTkLabel(row, text="IA:", font=ctk.CTkFont(size=10),
                     text_color=_P["text_dim"]).pack(side="left")
        ctk.CTkLabel(row, text=f" {acao}", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=_P["text"]).pack(side="left")

        pills = ctk.CTkFrame(frame, fg_color="transparent")
        pills.pack(fill="x", padx=10, pady=(0, 2))

        def _pill(text, color):
            p = ctk.CTkFrame(pills, fg_color=_P["bg"], corner_radius=3)
            p.pack(side="left", padx=(0, 4))
            ctk.CTkLabel(p, text=f" {text} ", font=ctk.CTkFont(size=9),
                         text_color=color).pack(padx=3, pady=1)

        if resolvido is not None:
            _pill("Resolvido" if resolvido else "Pendente",
                  _P["accent"] if resolvido else _P["warn"])
        if abrir is not None:
            _pill("Abrir: Sim" if abrir else "Abrir: Não",
                  _P["accent"] if abrir else _P["danger"])
        _pill(f"Conf: {conf}", self._conf_color(conf))

        if justificativa:
            ctk.CTkLabel(frame, text=justificativa, font=ctk.CTkFont(size=9),
                         text_color=_P["text_dim"], wraplength=550, anchor="w",
                         justify="left").pack(fill="x", padx=10, pady=(0, 6))

    # ── Shared: ticket + comments ─────────────────────────────────

    def _render_tickets(self, frame, tickets):
        self._clear(frame)
        if not tickets:
            ctk.CTkLabel(frame, text="Nenhum ticket JIRA.",
                         font=ctk.CTkFont(size=10), text_color=_P["text_dim"]
                         ).pack(anchor="w", pady=4)
            return

        for t in tickets:
            self._render_ticket(frame, t)

    def _render_ticket(self, parent, t):
        card = ctk.CTkFrame(parent, fg_color=_P["card_bg"], corner_radius=6,
                            border_width=1, border_color=_P["border"])
        card.pack(fill="x", pady=2)

        # Header with clickable link
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=8, pady=(4, 2))

        link = ctk.CTkButton(hdr, text=t["key"], width=0, height=20,
                             fg_color="transparent", hover_color=_P["surface_alt"],
                             text_color=_P["accent"], cursor="hand2",
                             font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                             command=lambda k=t["key"]: self._open_jira(k))
        link.pack(side="left")

        s = t["status"].lower()
        s_color = _P["accent"] if any(w in s for w in ("done", "termin", "conclu")) else _P["warn"]
        ctk.CTkLabel(hdr, text=f"[{t['status']}]",
                     font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=s_color).pack(side="left", padx=(4, 0))

        ctk.CTkLabel(hdr, text=t["updated"][:10],
                     font=ctk.CTkFont(size=9),
                     text_color=_P["text_dim"]).pack(side="right")

        ctk.CTkLabel(hdr, text=t["assignee"],
                     font=ctk.CTkFont(size=9),
                     text_color=_P["text_dim"]).pack(side="right", padx=(0, 8))

        # Comments — most recent first
        comments = t.get("comments", [])
        if comments:
            recent = list(reversed(comments))[:3]
            for c in recent:
                cf = ctk.CTkFrame(card, fg_color=_P["surface_alt"], corner_radius=3)
                cf.pack(fill="x", padx=8, pady=1)

                top = ctk.CTkFrame(cf, fg_color="transparent")
                top.pack(fill="x", padx=6, pady=(3, 0))
                ctk.CTkLabel(top, text=c.get("author", "?"),
                             font=ctk.CTkFont(size=9, weight="bold"),
                             text_color=_P["accent"]).pack(side="left")
                ctk.CTkLabel(top, text=c.get("created", "")[:10],
                             font=ctk.CTkFont(size=8),
                             text_color=_P["text_dim"]).pack(side="right")

                body = c.get("body", "")
                if len(body) > 250:
                    body = body[:247] + "…"
                ctk.CTkLabel(cf, text=body, font=ctk.CTkFont(size=9),
                             text_color=_P["text"], wraplength=500,
                             anchor="w", justify="left").pack(fill="x", padx=6, pady=(0, 3))

            if len(comments) > 3:
                ctk.CTkLabel(card, text=f"+ {len(comments) - 3} anteriores",
                             font=ctk.CTkFont(size=8),
                             text_color=_P["text_dim"]).pack(padx=8, pady=(0, 3))
        else:
            ctk.CTkLabel(card, text="Sem comentários", font=ctk.CTkFont(size=9),
                         text_color=_P["text_dim"]).pack(padx=8, pady=(0, 4))

    # ══════════════════════════════════════════════════════════════
    # NOVAS CONSULTAS
    # ══════════════════════════════════════════════════════════════

    def _show_new_item(self):
        self._clear(self.new_frame)
        if not self._new_items:
            self._placeholder(self.new_frame, "Nenhum item pendente.")
            return
        if self._new_idx >= len(self._new_items):
            self._placeholder(self.new_frame, "Todos processados.")
            return

        row = self._new_items[self._new_idx]
        mat = str(row[Config.ZS_MATERIAL])

        scroll = ctk.CTkScrollableFrame(self.new_frame, fg_color="transparent",
                                         scrollbar_button_color=_P["border"])
        scroll.grid(row=0, column=0, sticky="nsew")

        self._render_nav(scroll, self._new_idx, len(self._new_items),
                         self._new_prev, self._new_next)
        self._render_material_info(scroll, row)

        # Actions
        btns = ctk.CTkFrame(scroll, fg_color="transparent")
        btns.pack(fill="x", pady=(0, 6))
        self._btn_approve = ctk.CTkButton(btns, text="Criar Chamado",
            height=30, corner_radius=6, fg_color=_P["accent"],
            hover_color=_P["accent_hover"], text_color=_P["bg"],
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._approve_new(row))
        self._btn_approve.pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Pular", height=30, corner_radius=6, width=60,
                      fg_color=_P["surface_alt"], hover_color=_P["danger_hover"],
                      text_color=_P["danger"], font=ctk.CTkFont(size=10),
                      command=self._skip_new).pack(side="left")

        # LLM
        self._llm_new = ctk.CTkFrame(scroll, fg_color=_P["surface_alt"], corner_radius=6)
        self._llm_new.pack(fill="x", pady=(0, 4))

        # Tickets
        self._tkt_new = ctk.CTkFrame(scroll, fg_color="transparent")
        self._tkt_new.pack(fill="x")

        self._load_analysis(mat, row, self._llm_new, self._tkt_new)

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
            self.after(0, _done)
        threading.Thread(target=_w, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    # EM CONSULTA
    # ══════════════════════════════════════════════════════════════

    def _show_open_item(self):
        self._clear(self.open_frame)
        if not self._open_items:
            self._placeholder(self.open_frame, "Nenhum item em consulta.")
            return
        if self._open_idx >= len(self._open_items):
            self._open_idx = 0

        row = self._open_items[self._open_idx]
        mat = str(row[Config.ZS_MATERIAL])

        scroll = ctk.CTkScrollableFrame(self.open_frame, fg_color="transparent",
                                         scrollbar_button_color=_P["border"])
        scroll.grid(row=0, column=0, sticky="nsew")

        self._render_nav(scroll, self._open_idx, len(self._open_items),
                         self._open_prev, self._open_next)
        self._render_material_info(scroll, row)

        self._llm_open = ctk.CTkFrame(scroll, fg_color=_P["surface_alt"], corner_radius=6)
        self._llm_open.pack(fill="x", pady=(0, 4))

        self._tkt_open = ctk.CTkFrame(scroll, fg_color="transparent")
        self._tkt_open.pack(fill="x")

        self._load_analysis(mat, row, self._llm_open, self._tkt_open)

    def _open_prev(self):
        if self._open_idx > 0:
            self._open_idx -= 1
            self._show_open_item()

    def _open_next(self):
        if self._open_idx < len(self._open_items) - 1:
            self._open_idx += 1
            self._show_open_item()

    # ── Shared async loader ───────────────────────────────────────

    def _load_analysis(self, material, row, llm_frame, tkt_frame):
        ctk.CTkLabel(llm_frame, text="Analisando…",
                     font=ctk.CTkFont(size=10), text_color=_P["warn"]
                     ).pack(padx=10, pady=6)

        def _work():
            tickets = []
            try:
                issues = self.manager.jira.search_tickets(material, max_results=10)
                for iss in issues:
                    tickets.append(self.manager.jira.get_ticket_details(iss))
            except Exception as e:
                logger.error("Erro tickets %s: %s", material, e)

            mat_info = {
                "codigo": material,
                "descricao": row.get(Config.ZS_TXT_BREVE, ""),
                "dias_quebra": row.get("Dias da quebra", "?"),
                "estoque": row.get(Config.ZS_UTILIZACAO_LIVRE, "?"),
                "lmr": row.get("LMR", ""),
                "aplicacoes": row.get("aplicacoes", ""),
                "all_desat": row.get("All_Desat", False),
                "ordem_planejada": row.get(Config.ZS_ORDEM_PLANEJADA, ""),
            }

            if material in self._analysis_cache:
                analysis = self._analysis_cache[material]
            else:
                analysis = analyze_material(mat_info, tickets)
                self._analysis_cache[material] = analysis

            def _update():
                self._render_llm(llm_frame, analysis)
                self._render_tickets(tkt_frame, tickets)
            self.after(0, _update)

        threading.Thread(target=_work, daemon=True).start()


if __name__ == "__main__":
    setup_logging(log_to_file=True)
    app = App()
    app.mainloop()
