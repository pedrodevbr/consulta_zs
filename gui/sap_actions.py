"""SAP action panel — collapsible section with SAP operation buttons."""

import logging
import threading

import customtkinter as ctk

from gui.theme import P

logger = logging.getLogger(__name__)


class SapInputDialog(ctk.CTkToplevel):
    """Small dialog for SAP action parameters."""

    def __init__(self, parent, title: str, fields: list[tuple[str, str]]):
        super().__init__(parent)
        self.title(title)
        self.geometry("320x" + str(60 + len(fields) * 50))
        self.configure(fg_color=P["bg"])
        self.transient(parent)
        self.grab_set()

        self.result = None
        self._entries = {}

        for label, placeholder in fields:
            ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=11),
                         text_color=P["text"]).pack(anchor="w", padx=16, pady=(8, 0))
            entry = ctk.CTkEntry(self, placeholder_text=placeholder,
                                 fg_color=P["surface"], border_color=P["border"],
                                 text_color=P["text"])
            entry.pack(fill="x", padx=16, pady=(2, 0))
            self._entries[label] = entry

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(btns, text="Executar", height=28, corner_radius=4,
                      fg_color=P["accent"], hover_color=P["accent_hover"],
                      text_color=P["bg"], font=ctk.CTkFont(size=11, weight="bold"),
                      command=self._ok).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Cancelar", height=28, corner_radius=4,
                      fg_color=P["surface_alt"], hover_color=P["border"],
                      text_color=P["text_dim"], font=ctk.CTkFont(size=11),
                      command=self.destroy).pack(side="left")

    def _ok(self):
        self.result = {k: e.get().strip() for k, e in self._entries.items()}
        self.destroy()


class SapActionsPanel:
    """Collapsible SAP actions panel. Embeds into a parent frame."""

    def __init__(self, parent, manager, material_code: str, app_root):
        self.manager = manager
        self.material = material_code
        self.app_root = app_root
        self._expanded = False

        self.container = ctk.CTkFrame(parent, fg_color="transparent")
        self.container.pack(fill="x", pady=(0, 4))

        # Toggle header
        self.toggle_btn = ctk.CTkButton(
            self.container, text="Ações SAP  ▸", height=26, corner_radius=4,
            fg_color=P["surface_alt"], hover_color=P["border"],
            text_color=P["text_dim"], font=ctk.CTkFont(size=10),
            anchor="w", command=self._toggle)
        self.toggle_btn.pack(fill="x")

        # Action buttons (initially hidden)
        self.body = ctk.CTkFrame(self.container, fg_color=P["surface_alt"],
                                 corner_radius=6)

        self._status_label = None
        self._build_buttons()

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.toggle_btn.configure(text="Ações SAP  ▾")
            self.body.pack(fill="x", pady=(2, 0))
        else:
            self.toggle_btn.configure(text="Ações SAP  ▸")
            self.body.pack_forget()

    def _build_buttons(self):
        grid = ctk.CTkFrame(self.body, fg_color="transparent")
        grid.pack(fill="x", padx=8, pady=6)

        btn = dict(height=26, corner_radius=4, font=ctk.CTkFont(size=10),
                   fg_color=P["bg"], hover_color=P["border"], text_color=P["text"])

        actions = [
            ("Rodar MRP", self._run_mrp),
            ("Ajustar Nível", self._ajustar_nivel),
            ("Emitir Req.", self._emitir_req),
            ("Gerar Ord.Plan.", self._gerar_ordem),
            ("Encontrar Req.", self._encontrar_req),
        ]

        for i, (text, cmd) in enumerate(actions):
            r, c = divmod(i, 3)
            ctk.CTkButton(grid, text=text, command=cmd, width=120,
                          **btn).grid(row=r, column=c, padx=2, pady=2)

        grid.grid_columnconfigure((0, 1, 2), weight=1)

        # Status feedback
        self._status_label = ctk.CTkLabel(
            self.body, text="", font=ctk.CTkFont(size=9),
            text_color=P["text_dim"])
        self._status_label.pack(padx=8, pady=(0, 6))

    def _run_action(self, action: str, **kwargs):
        self._status_label.configure(text="Executando…", text_color=P["warn"])

        def _work():
            ok, msg = self.manager.run_sap_action(action, self.material, **kwargs)
            color = P["accent"] if ok else P["danger"]
            self._status_label.after(
                0, lambda: self._status_label.configure(text=msg, text_color=color))

        threading.Thread(target=_work, daemon=True).start()

    def _run_mrp(self):
        self._run_action("rodar_mrp")

    def _encontrar_req(self):
        self._run_action("encontrar_requisicao")

    def _ajustar_nivel(self):
        dlg = SapInputDialog(self.app_root, "Ajustar Nível (MM02)", [
            ("Ponto de Reposição (PR)", "Ex: 5"),
            ("Estoque Máximo (MAX)", "Ex: 10"),
        ])
        self.app_root.wait_window(dlg)
        if dlg.result:
            self._run_action("ajustar_nivel",
                             pr=dlg.result.get("Ponto de Reposição (PR)", ""),
                             max_valor=dlg.result.get("Estoque Máximo (MAX)", ""))

    def _emitir_req(self):
        dlg = SapInputDialog(self.app_root, "Emitir Requisição (ZMM0124)", [
            ("Quantidade", "Ex: 10"),
        ])
        self.app_root.wait_window(dlg)
        if dlg.result:
            self._run_action("emitir_requisicao",
                             quantidade=dlg.result.get("Quantidade", ""))

    def _gerar_ordem(self):
        dlg = SapInputDialog(self.app_root, "Gerar Ordem Planejada", [
            ("Quantidade", "Ex: 5"),
        ])
        self.app_root.wait_window(dlg)
        if dlg.result:
            self._run_action("gerar_ordem",
                             quantidade=dlg.result.get("Quantidade", ""))
