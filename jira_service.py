"""Wrapper around the python-jira client with enhanced comment/detail methods."""

import logging

from config import Config

logger = logging.getLogger(__name__)


class JiraService:

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._connect()
        return self._client

    def _connect(self):
        try:
            from jira import JIRA

            self._client = JIRA(
                server=Config.JIRA_SERVER,
                basic_auth=(Config.JIRA_USERNAME, Config.JIRA_PASSWORD),
                options={"verify": Config.JIRA_CERT_PATH},
            )
            logger.info("Conectado ao JIRA: %s", self._client.current_user())
        except Exception as e:
            raise ConnectionError(f"Erro ao conectar ao JIRA: {e}")

    # ── Search ────────────────────────────────────────────────────

    def search_tickets(self, code, max_results=5):
        try:
            q = (
                f'project = {Config.JIRA_PROJECT} '
                f'AND summary ~ "{code}" ORDER BY updated DESC'
            )
            issues = self.client.search_issues(q, maxResults=max_results)
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
            ticket = self.client.create_issue(
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
            f"Favor verificar a necessidade de reposicao do material: "
            f"{code} - {short_text}\n"
            f"Aplicacao: []\n"
            f"Caso seja necessaria reposicao favor indicar reference atualizada.\n"
            f"Referencia atual: {reference}"
        )
        return self.create_ticket(
            title=f"{code} - {short_text}",
            tipo="Reposicao ZS (sobre consulta)",
            description=desc,
            pieces_in_stock=saldo_virtual,
        )

    def create_frac_ticket(self, code, short_text, reference, saldo_virtual="0"):
        desc = (
            f"Prezados\n"
            f"A licitacao do codigo {code} - {short_text} resultou deserta.\n"
            f"Aplicacao: []\n"
            f"Referencia atual: {reference}"
        )
        return self.create_ticket(
            title=f"{code} - {short_text}",
            tipo=f"Referencia: {reference}",
            description=desc,
            pieces_in_stock=saldo_virtual,
        )

    # ── Transitions ───────────────────────────────────────────────

    def transition_issue(self, issue_key, transition_name):
        try:
            issue = self.client.issue(issue_key)
            for t in self.client.transitions(issue):
                if t["name"].lower() == transition_name.lower():
                    self.client.transition_issue(issue, t["id"])
                    logger.info("%s -> '%s'", issue_key, transition_name)
                    return True
            avail = [t["name"] for t in self.client.transitions(issue)]
            logger.warning(
                "Transicao '%s' indisponivel em %s. Disponiveis: %s",
                transition_name, issue_key, avail,
            )
            return False
        except Exception as e:
            logger.error("Erro transicao %s: %s", issue_key, e)
            return False

    # ── Comments ──────────────────────────────────────────────────

    def read_comments(self, ticket_key):
        try:
            issue = self.client.issue(ticket_key)
            return [
                {
                    "author": c.author.displayName,
                    "body": c.body,
                    "created": c.created,
                    "updated": c.updated,
                }
                for c in issue.fields.comment.comments
            ]
        except Exception as e:
            logger.error("Erro leitura comentarios %s: %s", ticket_key, e)
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
            self.client.add_comment(ticket_key, body)
            logger.info("Comentario adicionado: %s", ticket_key)
            return True
        except Exception as e:
            logger.error("Erro comentario %s: %s", ticket_key, e)
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
            getattr(fields.assignee, "displayName", "Nao atribuido")
            if fields.assignee
            else "Nao atribuido"
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
