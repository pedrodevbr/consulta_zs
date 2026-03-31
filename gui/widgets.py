"""Reusable UI widgets: material card, ticket card, LLM result, navigation."""

import webbrowser
import customtkinter as ctk

from config import Config
from gui.theme import P, severity_color, confidence_color, status_color

JIRA_BROWSE = f"{Config.JIRA_SERVER}/browse/"


def open_jira(key: str):
    webbrowser.open(f"{JIRA_BROWSE}{key}")


def render_nav(parent, idx: int, total: int, prev_cmd, next_cmd):
    """< 3/47 > navigation bar."""
    nav = ctk.CTkFrame(parent, fg_color="transparent")
    nav.pack(fill="x", pady=(0, 6))

    ctk.CTkButton(nav, text="<", width=36, height=24, corner_radius=4,
                  fg_color=P["surface_alt"], hover_color=P["border"],
                  text_color=P["text"], font=ctk.CTkFont(size=11),
                  command=prev_cmd,
                  state="normal" if idx > 0 else "disabled").pack(side="left")

    ctk.CTkLabel(nav, text=f" {idx + 1}/{total} ",
                 font=ctk.CTkFont(size=11, weight="bold"),
                 text_color=P["text"]).pack(side="left", padx=4)

    ctk.CTkButton(nav, text=">", width=36, height=24, corner_radius=4,
                  fg_color=P["surface_alt"], hover_color=P["border"],
                  text_color=P["text"], font=ctk.CTkFont(size=11),
                  command=next_cmd,
                  state="normal" if idx < total - 1 else "disabled").pack(side="left")
    return nav


def render_material_info(parent, row):
    """Material header card with evento, pills, and SAP data."""
    mat = str(row[Config.ZS_MATERIAL])
    desc = row.get(Config.ZS_TXT_BREVE, "")
    evento = row.get(Config.ZS_EVENTO, "")
    dias = row.get("Dias da quebra", "?")
    estoque = row.get(Config.ZS_UTILIZACAO_LIVRE, "?")
    ordem = row.get(Config.ZS_ORDEM_PLANEJADA, "")
    req = row.get(Config.ZS_REQ_COMPRA, "")
    pedido = row.get(Config.ZS_PEDIDO, "")

    f = ctk.CTkFrame(parent, fg_color=P["card_bg"], corner_radius=8)
    f.pack(fill="x", pady=(0, 4))

    # Title
    ctk.CTkLabel(f, text=f"{mat}  —  {desc}",
                 font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
                 text_color=P["accent"]).pack(anchor="w", padx=12, pady=(8, 0))

    # Evento
    if evento:
        ctk.CTkLabel(f, text=f"Evento: {evento}",
                     font=ctk.CTkFont(family="Consolas", size=11),
                     text_color=P["text_dim"]).pack(anchor="w", padx=12, pady=(0, 4))

    # Pills
    pills = ctk.CTkFrame(f, fg_color="transparent")
    pills.pack(fill="x", padx=12, pady=(0, 6))

    pill_data = [
        ("Dias", dias, severity_color(dias)),
        ("Estoque", estoque, P["text"]),
    ]
    if ordem:
        pill_data.append(("Ord.Plan.", ordem, P["warn"]))
    if req:
        pill_data.append(("Req.Compra", req, P["text_dim"]))
    if pedido:
        pill_data.append(("Pedido", pedido, P["text_dim"]))

    for label, val, color in pill_data:
        p = ctk.CTkFrame(pills, fg_color=P["surface_alt"], corner_radius=4)
        p.pack(side="left", padx=(0, 4))
        ctk.CTkLabel(p, text=f" {label}: {val} ", font=ctk.CTkFont(size=10),
                     text_color=color).pack(padx=3, pady=1)
    return f


def render_llm(frame, analysis: dict):
    """Render LLM analysis result."""
    for w in frame.winfo_children():
        w.destroy()

    acao = analysis.get("acao", "—")
    conf = analysis.get("confianca", "baixa")
    resolvido = analysis.get("resolvido")
    abrir = analysis.get("abrir_nova")
    justificativa = analysis.get("justificativa", "")

    row = ctk.CTkFrame(frame, fg_color="transparent")
    row.pack(fill="x", padx=10, pady=(6, 2))
    ctk.CTkLabel(row, text="IA:", font=ctk.CTkFont(size=10),
                 text_color=P["text_dim"]).pack(side="left")
    ctk.CTkLabel(row, text=f" {acao}", font=ctk.CTkFont(size=11, weight="bold"),
                 text_color=P["text"]).pack(side="left")

    pills = ctk.CTkFrame(frame, fg_color="transparent")
    pills.pack(fill="x", padx=10, pady=(0, 2))

    def _pill(text, color):
        p = ctk.CTkFrame(pills, fg_color=P["bg"], corner_radius=3)
        p.pack(side="left", padx=(0, 4))
        ctk.CTkLabel(p, text=f" {text} ", font=ctk.CTkFont(size=9),
                     text_color=color).pack(padx=3, pady=1)

    if resolvido is not None:
        _pill("Resolvido" if resolvido else "Pendente",
              P["accent"] if resolvido else P["warn"])
    if abrir is not None:
        _pill("Abrir: Sim" if abrir else "Abrir: Não",
              P["accent"] if abrir else P["danger"])
    _pill(f"Conf: {conf}", confidence_color(conf))

    if justificativa:
        ctk.CTkLabel(frame, text=justificativa, font=ctk.CTkFont(size=9),
                     text_color=P["text_dim"], wraplength=550, anchor="w",
                     justify="left").pack(fill="x", padx=10, pady=(0, 6))


def render_tickets(frame, tickets: list[dict], evento: str = ""):
    """Render list of Jira ticket cards with comments."""
    for w in frame.winfo_children():
        w.destroy()
    if not tickets:
        ctk.CTkLabel(frame, text="Nenhum ticket JIRA.",
                     font=ctk.CTkFont(size=10), text_color=P["text_dim"]
                     ).pack(anchor="w", pady=4)
        return
    for t in tickets:
        _render_ticket(frame, t, evento)


def _render_ticket(parent, t: dict, evento: str = ""):
    card = ctk.CTkFrame(parent, fg_color=P["card_bg"], corner_radius=6,
                        border_width=1, border_color=P["border"])
    card.pack(fill="x", pady=2)

    hdr = ctk.CTkFrame(card, fg_color="transparent")
    hdr.pack(fill="x", padx=8, pady=(4, 2))

    # Clickable ticket key
    ctk.CTkButton(hdr, text=t["key"], width=0, height=20,
                  fg_color="transparent", hover_color=P["surface_alt"],
                  text_color=P["accent"], cursor="hand2",
                  font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                  command=lambda k=t["key"]: open_jira(k)).pack(side="left")

    # Status
    ctk.CTkLabel(hdr, text=f"[{t['status']}]",
                 font=ctk.CTkFont(size=9, weight="bold"),
                 text_color=status_color(t["status"])).pack(side="left", padx=(4, 0))

    # Evento correlation
    if evento:
        ctk.CTkLabel(hdr, text=f"Ev.{evento}",
                     font=ctk.CTkFont(family="Consolas", size=8),
                     text_color=P["text_dim"]).pack(side="left", padx=(6, 0))

    ctk.CTkLabel(hdr, text=t["updated"][:10],
                 font=ctk.CTkFont(size=9),
                 text_color=P["text_dim"]).pack(side="right")

    ctk.CTkLabel(hdr, text=t["assignee"],
                 font=ctk.CTkFont(size=9),
                 text_color=P["text_dim"]).pack(side="right", padx=(0, 8))

    # Comments — most recent first
    comments = t.get("comments", [])
    if comments:
        for c in list(reversed(comments))[:3]:
            cf = ctk.CTkFrame(card, fg_color=P["surface_alt"], corner_radius=3)
            cf.pack(fill="x", padx=8, pady=1)

            top = ctk.CTkFrame(cf, fg_color="transparent")
            top.pack(fill="x", padx=6, pady=(3, 0))
            ctk.CTkLabel(top, text=c.get("author", "?"),
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=P["accent"]).pack(side="left")
            ctk.CTkLabel(top, text=c.get("created", "")[:10],
                         font=ctk.CTkFont(size=8),
                         text_color=P["text_dim"]).pack(side="right")

            body = c.get("body", "")
            if len(body) > 250:
                body = body[:247] + "…"
            ctk.CTkLabel(cf, text=body, font=ctk.CTkFont(size=9),
                         text_color=P["text"], wraplength=500,
                         anchor="w", justify="left").pack(fill="x", padx=6, pady=(0, 3))

        if len(comments) > 3:
            ctk.CTkLabel(card, text=f"+ {len(comments) - 3} anteriores",
                         font=ctk.CTkFont(size=8),
                         text_color=P["text_dim"]).pack(padx=8, pady=(0, 3))
    else:
        ctk.CTkLabel(card, text="Sem comentários", font=ctk.CTkFont(size=9),
                     text_color=P["text_dim"]).pack(padx=8, pady=(0, 4))
