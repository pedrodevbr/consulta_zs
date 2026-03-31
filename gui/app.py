"""Main application window — simplified single-pane layout."""

import json
import logging
import os
import threading
from datetime import datetime

import customtkinter as ctk

from config import Config
from services.process_manager import ProcessManager
from services.llm_service import analyze_material
from gui.theme import P
from gui.widgets import render_nav, render_material_info, render_llm, render_tickets
from gui.sap_actions import SapActionsPanel

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")


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
        self.geometry("960x640")
        self.minsize(760, 480)
        self.configure(fg_color=P["bg"])

        self.manager = ProcessManager(use_com_init=True)
        self._items = {"novas": [], "consulta": []}
        self._idx = {"novas": 0, "consulta": 0}
        self._mode = "novas"
        self._cache = {}

        self._build()
        self._attach_logger()
        logger.info("Sistema iniciado.")

    # ── Build ─────────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ── Sidebar ───────────────────────────────────────────────
        sb = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=P["surface"])
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_rowconfigure(8, weight=1)
        sb.grid_propagate(False)

        ctk.CTkLabel(sb, text="CONSULTAS ZS",
                     font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
                     text_color=P["accent"]).grid(row=0, column=0, padx=14, pady=(16, 10), sticky="w")

        btn = dict(height=32, corner_radius=6, border_width=0,
                   font=ctk.CTkFont(size=11, weight="bold"))

        self.btn_extract = ctk.CTkButton(sb, text="Extrair SAP",
            fg_color=P["surface_alt"], hover_color=P["border"],
            text_color=P["text"], command=self._on_extract, **btn)
        self.btn_extract.grid(row=1, column=0, padx=10, pady=(0, 3), sticky="ew")

        self.btn_load = ctk.CTkButton(sb, text="Carregar Dados",
            fg_color=P["accent"], hover_color=P["accent_hover"],
            text_color=P["bg"], command=self._on_load, **btn)
        self.btn_load.grid(row=2, column=0, padx=10, pady=(0, 3), sticky="ew")

        self.btn_check = ctk.CTkButton(sb, text="Verificar Abertas",
            fg_color=P["surface_alt"], hover_color=P["border"],
            text_color=P["text"], command=self._on_check, state="disabled", **btn)
        self.btn_check.grid(row=3, column=0, padx=10, pady=(0, 3), sticky="ew")

        ctk.CTkFrame(sb, height=1, fg_color=P["border"]).grid(
            row=4, column=0, sticky="ew", padx=10, pady=6)

        # Stats
        sf = ctk.CTkFrame(sb, fg_color="transparent")
        sf.grid(row=5, column=0, padx=14, sticky="new")
        self.lbl_total = self._stat(sf, "Total", 0)
        self.lbl_new = self._stat(sf, "Novas", 1)
        self.lbl_open = self._stat(sf, "Em consulta", 2)

        # Console toggle
        ctk.CTkFrame(sb, height=1, fg_color=P["border"]).grid(
            row=6, column=0, sticky="ew", padx=10, pady=6)

        self.btn_console = ctk.CTkButton(sb, text="Console ▸", height=24,
            corner_radius=4, fg_color="transparent", hover_color=P["surface_alt"],
            text_color=P["text_dim"], font=ctk.CTkFont(size=10),
            anchor="w", command=self._toggle_console)
        self.btn_console.grid(row=7, column=0, padx=10, sticky="ew")

        self.log_frame = ctk.CTkFrame(sb, fg_color="transparent")
        self.log_box = ctk.CTkTextbox(self.log_frame, height=150,
            font=ctk.CTkFont(family="Consolas", size=9),
            fg_color=P["bg"], text_color=P["accent"],
            border_width=1, border_color=P["border"],
            corner_radius=4, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)
        self._console_visible = False

        # ── Main area ─────────────────────────────────────────────
        main = ctk.CTkFrame(self, fg_color=P["bg"], corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # Mode switcher
        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

        self.mode_btn = ctk.CTkSegmentedButton(
            top, values=["Novas", "Em Consulta"],
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=P["surface_alt"],
            selected_color=P["accent"],
            selected_hover_color=P["accent_hover"],
            unselected_color=P["surface_alt"],
            unselected_hover_color=P["border"],
            text_color=P["bg"],
            command=self._on_mode_change)
        self.mode_btn.set("Novas")
        self.mode_btn.pack(side="left")

        # Content
        self.content = ctk.CTkFrame(main, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self._placeholder("Carregue os dados para começar.")

    # ── Helpers ───────────────────────────────────────────────────

    def _stat(self, parent, title, row):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", pady=1)
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=10),
                     text_color=P["text_dim"]).pack(side="left")
        lbl = ctk.CTkLabel(f, text="—", font=ctk.CTkFont(size=11, weight="bold"),
                           text_color=P["accent"])
        lbl.pack(side="right")
        return lbl

    def _attach_logger(self):
        h = TextboxLogHandler(self.log_box)
        h.setFormatter(logging.Formatter("%(asctime)s — %(message)s"))
        logging.getLogger().addHandler(h)

    def _clear(self):
        for w in self.content.winfo_children():
            w.destroy()

    def _placeholder(self, text):
        self._clear()
        ctk.CTkLabel(self.content, text=text, font=ctk.CTkFont(size=12),
                     text_color=P["text_dim"]).place(relx=0.5, rely=0.5, anchor="center")

    def _update_stats(self):
        total = len(self.manager.processor.zs_df)
        self.lbl_total.configure(text=str(total))
        self.lbl_new.configure(text=str(len(self._items["novas"])))
        self.lbl_open.configure(text=str(len(self._items["consulta"])))

    def _toggle_console(self):
        self._console_visible = not self._console_visible
        if self._console_visible:
            self.btn_console.configure(text="Console ▾")
            self.log_frame.grid(row=8, column=0, sticky="nsew", padx=4, pady=(0, 4))
        else:
            self.btn_console.configure(text="Console ▸")
            self.log_frame.grid_forget()

    # ── Mode switching ────────────────────────────────────────────

    def _on_mode_change(self, value):
        self._mode = "novas" if value == "Novas" else "consulta"
        self._show_item()

    @property
    def _current_items(self):
        return self._items[self._mode]

    @property
    def _current_idx(self):
        return self._idx[self._mode]

    @_current_idx.setter
    def _current_idx(self, val):
        self._idx[self._mode] = val

    # ── Thread wrappers ───────────────────────────────────────────

    def _on_extract(self):
        self.btn_extract.configure(state="disabled", text="Extraindo…")
        self._toggle_console() if not self._console_visible else None
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
                self._items["novas"] = [row for _, row in new.iterrows()]
                self._items["consulta"] = [row for _, row in opn.iterrows()]
                self._idx = {"novas": 0, "consulta": 0}
                self._cache.clear()
                self._load_cache_from_disk()
                self.after(0, self._update_stats)
                self.after(0, self._show_item)
                self.btn_check.after(0, lambda: self.btn_check.configure(state="normal"))
                logger.info("%d novas, %d em consulta.",
                            len(self._items["novas"]), len(self._items["consulta"]))
            else:
                logger.error("Falha ao carregar planilhas.")
            self.btn_load.after(0, lambda: self.btn_load.configure(
                state="normal", text="Carregar Dados"))
        threading.Thread(target=_w, daemon=True).start()

    def _on_check(self):
        self.btn_check.configure(state="disabled", text="Verificando…")
        def _w():
            self.manager.check_open_consultations()
            logger.info("Verificação concluída.")
            self.btn_check.after(0, lambda: self.btn_check.configure(
                state="normal", text="Verificar Abertas"))
        threading.Thread(target=_w, daemon=True).start()

    # ── Display current item ──────────────────────────────────────

    def _show_item(self):
        self._clear()
        items = self._current_items
        idx = self._current_idx

        if not items:
            self._placeholder("Nenhum item." if self._mode == "consulta"
                              else "Nenhum item pendente.")
            return
        if idx >= len(items):
            self._current_idx = 0
            idx = 0

        row = items[idx]
        mat = str(row[Config.ZS_MATERIAL])
        evento = row.get(Config.ZS_EVENTO, "")

        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent",
                                         scrollbar_button_color=P["border"])
        scroll.grid(row=0, column=0, sticky="nsew")

        # Navigation
        render_nav(scroll, idx, len(items), self._prev, self._next)

        # Material info
        render_material_info(scroll, row)

        # SAP actions (collapsible)
        SapActionsPanel(scroll, self.manager, mat, self)

        # Action buttons (only for "novas" mode)
        if self._mode == "novas":
            btns = ctk.CTkFrame(scroll, fg_color="transparent")
            btns.pack(fill="x", pady=(0, 4))
            self._btn_approve = ctk.CTkButton(btns, text="Criar Chamado",
                height=28, corner_radius=6, fg_color=P["accent"],
                hover_color=P["accent_hover"], text_color=P["bg"],
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda: self._approve(row))
            self._btn_approve.pack(side="left", padx=(0, 6))
            ctk.CTkButton(btns, text="Pular", height=28, corner_radius=6, width=60,
                          fg_color=P["surface_alt"], hover_color=P["danger_hover"],
                          text_color=P["danger"], font=ctk.CTkFont(size=10),
                          command=self._skip).pack(side="left")

        # LLM analysis
        llm_frame = ctk.CTkFrame(scroll, fg_color=P["surface_alt"], corner_radius=6)
        llm_frame.pack(fill="x", pady=(0, 4))

        # Tickets
        tkt_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        tkt_frame.pack(fill="x")

        # Load data (cached or async)
        self._load_data(mat, row, evento, llm_frame, tkt_frame)

    # ── Navigation ────────────────────────────────────────────────

    def _prev(self):
        if self._current_idx > 0:
            self._current_idx -= 1
            self._show_item()

    def _next(self):
        if self._current_idx < len(self._current_items) - 1:
            self._current_idx += 1
            self._show_item()

    def _skip(self):
        items = self._current_items
        items.pop(self._current_idx)
        if self._current_idx >= len(items):
            self._current_idx = max(0, len(items) - 1)
        self._update_stats()
        self._show_item()

    def _approve(self, row):
        self._btn_approve.configure(state="disabled", text="Criando…")
        def _w():
            ok = self.manager.process_single_ticket(row)
            def _done():
                if ok:
                    items = self._current_items
                    items.pop(self._current_idx)
                    if self._current_idx >= len(items):
                        self._current_idx = max(0, len(items) - 1)
                    self._update_stats()
                    self._show_item()
                else:
                    self._btn_approve.configure(state="normal", text="Criar Chamado")
            self.after(0, _done)
        threading.Thread(target=_w, daemon=True).start()

    # ── Data loader with cache ────────────────────────────────────

    def _load_data(self, material, row, evento, llm_frame, tkt_frame):
        cached = self._cache.get(material)
        if cached and "tickets" in cached and "analysis" in cached:
            render_llm(llm_frame, cached["analysis"])
            render_tickets(tkt_frame, cached["tickets"], evento)
            return

        ctk.CTkLabel(llm_frame, text="Analisando…", font=ctk.CTkFont(size=10),
                     text_color=P["warn"]).pack(padx=10, pady=6)

        def _work():
            entry = self._cache.setdefault(material, {})

            if "tickets" not in entry:
                tickets = []
                try:
                    issues = self.manager.jira.search_tickets(material, max_results=10)
                    for iss in issues:
                        tickets.append(self.manager.jira.get_ticket_details(iss))
                except Exception as e:
                    logger.error("Erro tickets %s: %s", material, e)
                entry["tickets"] = tickets

            if "analysis" not in entry:
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
                entry["analysis"] = analyze_material(mat_info, entry["tickets"])
                self._save_cache_to_disk()

            def _update():
                render_llm(llm_frame, entry["analysis"])
                render_tickets(tkt_frame, entry["tickets"], evento)
            self.after(0, _update)

        threading.Thread(target=_work, daemon=True).start()

    # ── Disk cache ────────────────────────────────────────────────

    def _cache_path(self):
        return os.path.join(self.manager.folder, "analysis_cache.json")

    def _save_cache_to_disk(self):
        try:
            data = {m: {"tickets": e.get("tickets", []), "analysis": e.get("analysis", {})}
                    for m, e in self._cache.items()}
            with open(self._cache_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Erro salvar cache: %s", e)

    def _load_cache_from_disk(self):
        path = self._cache_path()
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._cache.update(json.load(f))
            logger.info("Cache carregado: %d materiais", len(self._cache))
        except Exception as e:
            logger.error("Erro carregar cache: %s", e)
