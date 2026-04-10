"""Interface de terminal para Consultas ZS."""

import json
import logging
import os

from config import Config
from services.process_manager import ProcessManager
from services.llm_service import analyze_material

logger = logging.getLogger(__name__)

JIRA_BROWSE = f"{Config.JIRA_SERVER}/browse/"

# ── ANSI helpers ─────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"


def _severity(dias) -> str:
    try:
        d = int(dias)
    except (ValueError, TypeError):
        return DIM
    return RED if d > 120 else YELLOW if d > 90 else GREEN


def _confidence_color(conf: str) -> str:
    return {"alta": GREEN, "media": YELLOW}.get(conf, RED)


def _status_color(status: str) -> str:
    s = status.lower()
    if any(w in s for w in ("done", "termin", "conclu", "fechad")):
        return GREEN
    return YELLOW


def _hr():
    print(f"{DIM}{'─' * 60}{RESET}")


# ── Display helpers ──────────────────────────────────────────────

def show_material(row, idx: int, total: int):
    mat = str(row[Config.ZS_MATERIAL])
    desc = row.get(Config.ZS_TXT_BREVE, "")
    evento = row.get(Config.ZS_EVENTO, "")
    dias = row.get("Dias da quebra", "?")
    estoque = row.get(Config.ZS_UTILIZACAO_LIVRE, "?")
    ordem = row.get(Config.ZS_ORDEM_PLANEJADA, "")
    req = row.get(Config.ZS_REQ_COMPRA, "")
    pedido = row.get(Config.ZS_PEDIDO, "")

    print()
    _hr()
    print(f"  {BOLD}{CYAN}{mat}{RESET}  —  {BOLD}{desc}{RESET}   "
          f"{DIM}[{idx + 1}/{total}]{RESET}")
    if evento:
        print(f"  {DIM}Evento: {evento}{RESET}")

    pills = []
    cor_dias = _severity(dias)
    pills.append(f"{cor_dias}Dias: {dias}{RESET}")
    pills.append(f"Estoque: {estoque}")
    if ordem:
        pills.append(f"{YELLOW}Ord.Plan.: {ordem}{RESET}")
    if req:
        pills.append(f"Req.Compra: {req}")
    if pedido:
        pills.append(f"Pedido: {pedido}")
    print(f"  {' | '.join(pills)}")
    _hr()


def show_llm(analysis: dict):
    acao = analysis.get("acao", "—")
    conf = analysis.get("confianca", "baixa")
    resolvido = analysis.get("resolvido")
    abrir = analysis.get("abrir_nova")
    justificativa = analysis.get("justificativa", "")

    print(f"\n  {BOLD}IA:{RESET} {acao}")

    pills = []
    if resolvido is not None:
        if resolvido:
            pills.append(f"{GREEN}Resolvido{RESET}")
        else:
            pills.append(f"{YELLOW}Pendente{RESET}")
    if abrir is not None:
        if abrir:
            pills.append(f"{GREEN}Abrir: Sim{RESET}")
        else:
            pills.append(f"{RED}Abrir: Nao{RESET}")
    cor_conf = _confidence_color(conf)
    pills.append(f"{cor_conf}Conf: {conf}{RESET}")
    print(f"  {' | '.join(pills)}")

    if justificativa:
        print(f"  {DIM}{justificativa}{RESET}")


def show_tickets(tickets: list[dict], evento: str = ""):
    if not tickets:
        print(f"\n  {DIM}Nenhum ticket JIRA.{RESET}")
        return
    print(f"\n  {BOLD}Tickets JIRA ({len(tickets)}):{RESET}")
    for t in tickets:
        cor = _status_color(t["status"])
        ev_str = f"  {DIM}Ev.{evento}{RESET}" if evento else ""
        print(f"\n  {CYAN}{BOLD}{t['key']}{RESET} {cor}[{t['status']}]{RESET}"
              f"  {DIM}{t['assignee']}{RESET}  {DIM}{t['updated'][:10]}{RESET}{ev_str}")
        comments = t.get("comments", [])
        if comments:
            for c in list(reversed(comments))[:3]:
                author = c.get("author", "?")
                date = c.get("created", "")[:10]
                body = c.get("body", "")
                if len(body) > 200:
                    body = body[:197] + "..."
                print(f"    {GREEN}{author}{RESET} {DIM}{date}{RESET}")
                print(f"    {body}")
            if len(comments) > 3:
                print(f"    {DIM}+ {len(comments) - 3} anteriores{RESET}")
        else:
            print(f"    {DIM}Sem comentarios{RESET}")


# ── Cache ────────────────────────────────────────────────────────

def _cache_path(folder: str) -> str:
    return os.path.join(folder, "analysis_cache.json")


def load_cache(folder: str) -> dict:
    path = _cache_path(folder)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        logger.info("Cache carregado: %d materiais", len(cache))
        return cache
    except Exception as e:
        logger.error("Erro carregar cache: %s", e)
        return {}


def save_cache(folder: str, cache: dict):
    try:
        data = {m: {"tickets": e.get("tickets", []), "analysis": e.get("analysis", {})}
                for m, e in cache.items()}
        with open(_cache_path(folder), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erro salvar cache: %s", e)


# ── Data loader ──────────────────────────────────────────────────

def load_item_data(manager: ProcessManager, cache: dict, row) -> dict:
    """Load tickets + LLM analysis for a material (cached or fresh)."""
    mat = str(row[Config.ZS_MATERIAL])
    cached = cache.get(mat)
    if cached and "tickets" in cached and "analysis" in cached:
        return cached

    entry = cache.setdefault(mat, {})

    if "tickets" not in entry:
        print(f"  {DIM}Buscando tickets...{RESET}", end="", flush=True)
        tickets = []
        try:
            issues = manager.jira.search_tickets(mat, max_results=10)
            for iss in issues:
                tickets.append(manager.jira.get_ticket_details(iss))
        except Exception as e:
            logger.error("Erro tickets %s: %s", mat, e)
        entry["tickets"] = tickets
        print(f"\r  {DIM}Tickets: {len(tickets)} encontrados.{' ' * 20}{RESET}")

    if "analysis" not in entry:
        print(f"  {DIM}Analisando com IA...{RESET}", end="", flush=True)
        mat_info = {
            "codigo": mat,
            "descricao": row.get(Config.ZS_TXT_BREVE, ""),
            "dias_quebra": row.get("Dias da quebra", "?"),
            "estoque": row.get(Config.ZS_UTILIZACAO_LIVRE, "?"),
            "lmr": row.get("LMR", ""),
            "aplicacoes": row.get("aplicacoes", ""),
            "all_desat": row.get("All_Desat", False),
            "ordem_planejada": row.get(Config.ZS_ORDEM_PLANEJADA, ""),
        }
        entry["analysis"] = analyze_material(mat_info, entry["tickets"])
        save_cache(manager.folder, cache)
        print(f"\r  {DIM}Analise concluida.{' ' * 30}{RESET}")

    return entry


# ── Item viewer ──────────────────────────────────────────────────

def view_items(manager: ProcessManager, cache: dict, items: list, mode: str):
    """Interactive navigation through items."""
    if not items:
        print(f"\n  {DIM}Nenhum item {'pendente' if mode == 'novas' else 'em consulta'}.{RESET}")
        input(f"\n  {DIM}Enter para voltar...{RESET}")
        return

    idx = 0
    while True:
        if not items:
            print(f"\n  {DIM}Nenhum item restante.{RESET}")
            input(f"\n  {DIM}Enter para voltar...{RESET}")
            return

        if idx >= len(items):
            idx = 0

        row = items[idx]
        evento = row.get(Config.ZS_EVENTO, "")

        show_material(row, idx, len(items))

        data = load_item_data(manager, cache, row)
        show_llm(data.get("analysis", {}))
        show_tickets(data.get("tickets", []), str(evento))

        # Actions
        print()
        _hr()
        opts = []
        if idx > 0:
            opts.append("[p] Anterior")
        if idx < len(items) - 1:
            opts.append("[n] Proximo")
        if mode == "novas":
            opts.append(f"[c] Criar Chamado")
            opts.append("[s] Pular")
        opts.append("[m] Menu")
        print(f"  {' | '.join(opts)}")

        choice = input(f"\n  > ").strip().lower()

        if choice == "n" and idx < len(items) - 1:
            idx += 1
        elif choice == "p" and idx > 0:
            idx -= 1
        elif choice == "c" and mode == "novas":
            print(f"\n  {YELLOW}Criando chamado...{RESET}")
            ok = manager.process_single_ticket(row)
            if ok:
                print(f"  {GREEN}Chamado criado com sucesso!{RESET}")
                items.pop(idx)
                if idx >= len(items):
                    idx = max(0, len(items) - 1)
            else:
                print(f"  {RED}Erro ao criar chamado.{RESET}")
            input(f"  {DIM}Enter para continuar...{RESET}")
        elif choice == "s" and mode == "novas":
            items.pop(idx)
            if idx >= len(items):
                idx = max(0, len(items) - 1)
        elif choice == "m":
            return
        elif choice == "":
            # Enter = next if possible
            if idx < len(items) - 1:
                idx += 1


# ── Main loop ────────────────────────────────────────────────────

def run():
    print(f"\n{BOLD}{CYAN}  CONSULTAS ZS{RESET} — Itaipu Binacional\n")

    manager = ProcessManager(use_com_init=True)
    items = {"novas": [], "consulta": []}
    cache: dict = {}
    loaded = False

    while True:
        _hr()
        if loaded:
            n_novas = len(items["novas"])
            n_consulta = len(items["consulta"])
            n_total = len(manager.processor.zs_df)
            print(f"  {DIM}Total: {n_total} | "
                  f"Novas: {n_novas} | "
                  f"Em consulta: {n_consulta}{RESET}")
            _hr()
            print(f"\n  [1] Ver Novas ({n_novas})")
            print(f"  [2] Ver Em Consulta ({n_consulta})")
            print(f"  [3] Verificar Abertas")
            print(f"  [4] Recarregar Dados")
            print(f"  [5] Sair")
        else:
            print(f"\n  [1] Carregar Dados")
            print(f"  [2] Sair")

        choice = input(f"\n  > ").strip()

        if not loaded:
            if choice == "1":
                print(f"\n  {YELLOW}Inicializando conexoes...{RESET}")
                manager.init_connections()
                print(f"  {YELLOW}Carregando dados...{RESET}")
                if manager.run_data_pipeline():
                    new = manager.processor.get_items_to_open()
                    opn = manager.processor.get_items_in_consultation()
                    items["novas"] = [row for _, row in new.iterrows()]
                    items["consulta"] = [row for _, row in opn.iterrows()]
                    cache = load_cache(manager.folder)
                    loaded = True
                    print(f"  {GREEN}Dados carregados! "
                          f"{len(items['novas'])} novas, "
                          f"{len(items['consulta'])} em consulta.{RESET}")
                else:
                    print(f"  {RED}Falha ao carregar planilhas.{RESET}")
            elif choice == "2":
                print(f"\n  {DIM}Saindo...{RESET}")
                break
        else:
            if choice == "1":
                view_items(manager, cache, items["novas"], "novas")
            elif choice == "2":
                view_items(manager, cache, items["consulta"], "consulta")
            elif choice == "3":
                print(f"\n  {YELLOW}Verificando consultas abertas...{RESET}")
                manager.check_open_consultations()
                print(f"  {GREEN}Verificacao concluida.{RESET}")
                input(f"  {DIM}Enter para continuar...{RESET}")
            elif choice == "4":
                print(f"\n  {YELLOW}Recarregando dados...{RESET}")
                manager.init_connections()
                if manager.run_data_pipeline():
                    new = manager.processor.get_items_to_open()
                    opn = manager.processor.get_items_in_consultation()
                    items["novas"] = [row for _, row in new.iterrows()]
                    items["consulta"] = [row for _, row in opn.iterrows()]
                    cache = load_cache(manager.folder)
                    print(f"  {GREEN}Dados recarregados!{RESET}")
                else:
                    print(f"  {RED}Falha ao carregar planilhas.{RESET}")
            elif choice == "5":
                print(f"\n  {DIM}Saindo...{RESET}")
                break
