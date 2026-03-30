import logging
from jira import JIRA
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
            self._client = JIRA(
                server=Config.JIRA_SERVER,
                basic_auth=(Config.JIRA_USERNAME, Config.JIRA_PASSWORD),
                options={'verify': Config.JIRA_CERT_PATH},
            )
            logger.info("Conectado ao JIRA: %s", self._client.current_user())
        except Exception as e:
            raise ConnectionError(f"Erro ao conectar ao JIRA: {e}")

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search_tickets(self, code, max_results=5):
        try:
            query = f'project = {Config.JIRA_PROJECT} AND summary ~ "{code}" ORDER BY updated DESC'
            issues = self.client.search_issues(query, maxResults=max_results)
            if not issues:
                logger.info("Nenhum ticket encontrado para o material %s", code)
                return []
            logger.info("Encontrados %d tickets para o material %s", len(issues), code)
            return issues
        except Exception as e:
            logger.error("Erro ao buscar tickets para o material %s: %s", code, e)
            return []

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def create_ticket(self, title, description, tipo, pieces_in_stock):
        try:
            ticket = self.client.create_issue(
                project=Config.JIRA_PROJECT,
                summary=title,
                description=description,
                issuetype={"name": "Task"},
                customfield_17633={'value': tipo},
                customfield_17601=str(pieces_in_stock),
            )
            logger.info("Ticket criado: %s", ticket.key)
            return ticket
        except Exception as e:
            logger.error("Erro ao criar ticket '%s': %s", title, e)
            raise

    def create_zs_ticket(self, code, short_text, reference, saldo_virtual="0"):
        description = (
            f"Prezados\n"
            f"Favor verificar a necessidade de reposição do material: {code} - {short_text}\n"
            f"Aplicação: []\n"
            f"Caso seja necessaria reposição favor indicar reference atualizada.\n"
            f"Referencia atual: {reference}"
        )
        return self.create_ticket(
            title=f"{code} - {short_text}",
            tipo='Reposição ZS (sobre consulta)',
            description=description,
            pieces_in_stock=saldo_virtual,
        )

    def create_frac_ticket(self, code, short_text, reference, saldo_virtual="0"):
        description = (
            f"Prezados\n"
            f"A licitação do codigo {code} - {short_text} resultou deserta.\n"
            f"Aplicação: []\n"
            f"Referencia atual: {reference}"
        )
        return self.create_ticket(
            title=f"{code} - {short_text}",
            tipo=f'Referencia: {reference}',
            description=description,
            pieces_in_stock=saldo_virtual,
        )

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    def transition_issue(self, issue_key, transition_name):
        try:
            issue = self.client.issue(issue_key)
            transitions = self.client.transitions(issue)
            for t in transitions:
                if t['name'].lower() == transition_name.lower():
                    self.client.transition_issue(issue, t['id'])
                    logger.info("Ticket %s movido para '%s'", issue_key, transition_name)
                    return True
            available = [t['name'] for t in transitions]
            logger.warning(
                "Transição '%s' indisponível para %s. Disponíveis: %s",
                transition_name, issue_key, available,
            )
            return False
        except Exception as e:
            logger.error("Erro ao mudar status de %s: %s", issue_key, e)
            return False

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------
    def read_comments(self, ticket_key):
        try:
            issue = self.client.issue(ticket_key)
            return [
                {
                    'author': c.author.displayName,
                    'body': c.body,
                    'created': c.created,
                    'updated': c.updated,
                }
                for c in issue.fields.comment.comments
            ]
        except Exception as e:
            logger.error("Erro ao ler comentários do ticket %s: %s", ticket_key, e)
            return []

    def read_all_comments(self, code, max_results=50):
        """Fetch all comments from every ticket matching the material code."""
        tickets = self.search_tickets(code, max_results=max_results)
        all_comments = []
        for ticket in tickets:
            comments = self.read_comments(ticket.key)
            for comment in comments:
                comment['ticket_key'] = ticket.key
                all_comments.append(comment)
        return all_comments

    def add_comment(self, ticket_key, body):
        try:
            self.client.add_comment(ticket_key, body)
            logger.info("Comentário adicionado ao ticket %s", ticket_key)
            return True
        except Exception as e:
            logger.error("Erro ao adicionar comentário ao ticket %s: %s", ticket_key, e)
            return False

    def find_last_comment(self, code):
        tickets = self.search_tickets(code)
        if not tickets:
            return None, None
        last_ticket = tickets[-1]
        comments = self.read_comments(last_ticket.key)
        return comments, last_ticket

    # ------------------------------------------------------------------
    # Ticket details
    # ------------------------------------------------------------------
    def get_ticket_details(self, issue):
        """Return a structured dict with full ticket information and comments."""
        fields = issue.fields
        assignee = getattr(fields.assignee, 'displayName', 'Não atribuído') if fields.assignee else 'Não atribuído'
        reporter = getattr(fields.reporter, 'displayName', '') if fields.reporter else ''
        priority = getattr(fields.priority, 'name', '') if fields.priority else ''

        # Custom fields (safe access)
        tipo_field = getattr(fields, 'customfield_17633', None)
        tipo = ''
        if tipo_field:
            tipo = tipo_field.get('value', '') if isinstance(tipo_field, dict) else str(tipo_field)
        pieces_in_stock = getattr(fields, 'customfield_17601', '') or ''

        comments = self.read_comments(issue.key)

        return {
            'key': issue.key,
            'summary': fields.summary or '',
            'status': self.get_status(issue),
            'assignee': assignee,
            'reporter': reporter,
            'priority': priority,
            'created': str(fields.created or ''),
            'updated': str(fields.updated or ''),
            'description': fields.description or '',
            'tipo': tipo,
            'pieces_in_stock': str(pieces_in_stock),
            'comments': comments,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def get_status(issue):
        return getattr(issue.fields.status, 'name', str(issue.fields.status))
