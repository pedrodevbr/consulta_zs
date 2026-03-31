"""Wrapper around the python-jira client with retry, 401 handling, and
enhanced comment/detail methods."""

import time
import logging

from config import Config

logger = logging.getLogger(__name__)


class JiraAuthError(ConnectionError):
    """Raised when JIRA returns 401 Unauthorized."""


class JiraService:

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._connect()
        return self._client

    # ── Connection with retry ─────────────────────────────────────

    def _connect(self):
        from jira import JIRA
        from jira.exceptions import JIRAError

        if not Config.JIRA_USERNAME or not Config.JIRA_PASSWORD:
            raise JiraAuthError(
                "JIRA_USERNAME ou JIRA_PASSWORD não configurados. "
                "Defina as variáveis no arquivo .env."
            )

        last_error = None
        for attempt in range(1, Config.JIRA_MAX_RETRIES + 1):
            try:
                self._client = JIRA(
                    server=Config.JIRA_SERVER,
                    basic_auth=(Config.JIRA_USERNAME, Config.JIRA_PASSWORD),
                    options={"verify": Config.JIRA_CERT_PATH},
                )
                user = self._client.current_user()
                logger.info("Conectado ao JIRA como: %s", user)
                return
            except JIRAError as e:
                last_error = e
                status = getattr(e, "status_code", None)
                if status == 401:
                    raise JiraAuthError(
                        "Autenticação JIRA falhou (401 Unauthorized). "
                        "Verifique JIRA_USERNAME e JIRA_PASSWORD no .env."
                    ) from e
                if status == 403:
                    raise JiraAuthError(
                        "Acesso JIRA negado (403 Forbidden). "
                        "Sua conta pode estar bloqueada — faça login no navegador "
                        "e complete o CAPTCHA, depois tente novamente."
                    ) from e
                logger.warning(
                    "Tentativa %d/%d falhou (HTTP %s): %s",
                    attempt, Config.JIRA_MAX_RETRIES, status, e,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "Tentativa %d/%d falhou: %s",
                    attempt, Config.JIRA_MAX_RETRIES, e,
                )

            if attempt < Config.JIRA_MAX_RETRIES:
                delay = Config.JIRA_RETRY_DELAY * attempt
                logger.info("Aguardando %ds antes de tentar novamente…", delay)
                time.sleep(delay)

        raise ConnectionError(
            f"Não foi possível conectar ao JIRA após {Config.JIRA_MAX_RETRIES} "
            f"tentativas. Último erro: {last_error}"
        )

    def reconnect(self):
        """Force a fresh connection (e.g. after password change)."""
        self._client = None
        self._connect()

    # ── Safe API wrapper ──────────────────────────────────────────

    def _call(self, fn, *args, **kwargs):
        """Execute a JIRA API call; on 401 try reconnecting once."""
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            status = getattr(e, "status_code", None)
            if status == 401:
                logger.warning("Sessão expirada (401). Reconectando…")
                try:
                    self.reconnect()
                    return fn(*args, **kwargs)
                except Exception:
                    pass
            raise

    # ── Search ────────────────────────────────────────────────────

    def get_field_options(self, field_id="customfield_17633"):
        """List allowed values for a custom select field."""
        try:
            meta = self._call(
                self.client.createmeta,
                projectKeys=Config.JIRA_PROJECT,
                issuetypeNames="Task",
                expand="projects.issuetypes.fields",
            )
            for proj in meta.get("projects", []):
                for itype in proj.get("issuetypes", []):
                    field = itype.get("fields", {}).get(field_id, {})
                    options = field.get("allowedValues", [])
                    values = [o.get("value", o.get("name", "?")) for o in options]
                    logger.info(
                        "Opções disponíveis para %s: %s", field_id, values,
                    )
                    return values
            logger.warning("Campo %s não encontrado nos metadados.", field_id)
            return []
        except Exception as e:
            logger.error("Erro ao buscar opções de %s: %s", field_id, e)
            return []

    def search_tickets(self, code, max_results=5):
        try:
            q = (
                f'project = {Config.JIRA_PROJECT} '
                f'AND summary ~ "{code}" ORDER BY updated DESC'
            )
            issues = self._call(
                self.client.search_issues, q, maxResults=max_results,
            )
            if not issues:
                logger.info("Nenhum ticket para %s", code)
                return []
            logger.info("%d tickets para %s", len(issues), code)
            return issues
        except Exception as e:
            logger.error("Erro busca tickets %s: %s", code, e)
            return []

    # ── Create ────────────────────────────────────────────────────

    def create_ticket(self, title, description, tipo, pieces_in_stock):
        try:
            ticket = self._call(
                self.client.create_issue,
                project=Config.JIRA_PROJECT,
                summary=title,
                description=description,
                issuetype={"name": "Task"},
                customfield_17633={"value": tipo},
                customfield_17601=str(pieces_in_stock),
            )
            logger.info("Ticket criado: %s", ticket.key)
            return ticket
        except Exception as e:
            logger.error("Erro criar ticket '%s': %s", title, e)
            raise

    def create_zs_ticket(self, code, short_text, reference, saldo_virtual="0"):
        desc = (
            f"Prezados\n"
            f"Favor verificar a necessidade de reposição do material: "
            f"{code} - {short_text}\n"
            f"Aplicação: []\n"
            f"Caso seja necessária reposição favor indicar referência atualizada.\n"
            f"Referência atual: {reference}"
        )
        return self.create_ticket(
            title=f"{code} - {short_text}",
            tipo="Reposição ZS (sobre consulta)",
            description=desc,
            pieces_in_stock=saldo_virtual,
        )

    def create_frac_ticket(self, code, short_text, reference, saldo_virtual="0"):
        desc = (
            f"Prezados\n"
            f"A licitação do código {code} - {short_text} resultou deserta.\n"
            f"Aplicação: []\n"
            f"Referência atual: {reference}"
        )
        return self.create_ticket(
            title=f"{code} - {short_text}",
            tipo=f"Referência: {reference}",
            description=desc,
            pieces_in_stock=saldo_virtual,
        )

    # ── Transitions ───────────────────────────────────────────────

    def transition_issue(self, issue_key, transition_name):
        try:
            issue = self._call(self.client.issue, issue_key)
            transitions = self._call(self.client.transitions, issue)
            for t in transitions:
                if t["name"].lower() == transition_name.lower():
                    self._call(self.client.transition_issue, issue, t["id"])
                    logger.info("%s → '%s'", issue_key, transition_name)
                    return True
            avail = [t["name"] for t in transitions]
            logger.warning(
                "Transição '%s' indisponível em %s. Disponíveis: %s",
                transition_name, issue_key, avail,
            )
            return False
        except Exception as e:
            logger.error("Erro transição %s: %s", issue_key, e)
            return False

    # ── Comments ──────────────────────────────────────────────────

    def read_comments(self, ticket_key):
        try:
            issue = self._call(self.client.issue, ticket_key)
            return [
                {
                    "author": getattr(c.author, "displayName", "?"),
                    "body": c.body,
                    "created": c.created,
                    "updated": c.updated,
                }
                for c in issue.fields.comment.comments
            ]
        except Exception as e:
            logger.error("Erro leitura comentários %s: %s", ticket_key, e)
            return []

    def read_all_comments(self, code, max_results=50):
        """Fetch all comments from every ticket matching the material code."""
        tickets = self.search_tickets(code, max_results=max_results)
        all_comments = []
        for ticket in tickets:
            comments = self.read_comments(ticket.key)
            for comment in comments:
                comment["ticket_key"] = ticket.key
                all_comments.append(comment)
        return all_comments

    def add_comment(self, ticket_key, body):
        try:
            self._call(self.client.add_comment, ticket_key, body)
            logger.info("Comentário adicionado: %s", ticket_key)
            return True
        except Exception as e:
            logger.error("Erro comentário %s: %s", ticket_key, e)
            return False

    def find_last_comment(self, code):
        tickets = self.search_tickets(code)
        if not tickets:
            return None, None
        last = tickets[-1]
        return self.read_comments(last.key), last

    # ── Ticket details ────────────────────────────────────────────

    def get_ticket_details(self, issue):
        """Return a structured dict with full ticket information and comments."""
        fields = issue.fields
        assignee = (
            getattr(fields.assignee, "displayName", "Não atribuído")
            if fields.assignee
            else "Não atribuído"
        )
        reporter = (
            getattr(fields.reporter, "displayName", "")
            if fields.reporter
            else ""
        )
        priority = (
            getattr(fields.priority, "name", "")
            if fields.priority
            else ""
        )

        tipo_field = getattr(fields, "customfield_17633", None)
        tipo = ""
        if tipo_field:
            tipo = (
                tipo_field.get("value", "")
                if isinstance(tipo_field, dict)
                else str(tipo_field)
            )
        pieces_in_stock = getattr(fields, "customfield_17601", "") or ""

        comments = self.read_comments(issue.key)

        return {
            "key": issue.key,
            "summary": fields.summary or "",
            "status": self.get_status(issue),
            "assignee": assignee,
            "reporter": reporter,
            "priority": priority,
            "created": str(fields.created or ""),
            "updated": str(fields.updated or ""),
            "description": fields.description or "",
            "tipo": tipo,
            "pieces_in_stock": str(pieces_in_stock),
            "comments": comments,
        }

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def get_status(issue):
        return getattr(issue.fields.status, "name", str(issue.fields.status))
