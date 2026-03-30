import sys
import logging

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jira_service import JiraService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Stylesheet ────────────────────────────────────────────────────────
STYLESHEET = """
QMainWindow {
    background-color: #f5f6fa;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #dcdde1;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #2f3640;
}
QTableWidget {
    border: 1px solid #dcdde1;
    border-radius: 4px;
    background-color: #ffffff;
    gridline-color: #ecf0f1;
    selection-background-color: #3498db;
    selection-color: #ffffff;
    alternate-background-color: #f8f9fa;
}
QTableWidget::item {
    padding: 4px 8px;
}
QHeaderView::section {
    background-color: #2c3e50;
    color: #ffffff;
    padding: 6px 8px;
    border: none;
    font-weight: bold;
}
QLineEdit {
    border: 1px solid #bdc3c7;
    border-radius: 4px;
    padding: 6px 10px;
    background-color: #ffffff;
}
QLineEdit:focus {
    border-color: #3498db;
}
QPushButton {
    background-color: #3498db;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 18px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #2980b9;
}
QPushButton:pressed {
    background-color: #1c6ea4;
}
QPushButton#btnCreateZS {
    background-color: #27ae60;
}
QPushButton#btnCreateZS:hover {
    background-color: #219a52;
}
QPushButton#btnCreateFRAC {
    background-color: #e67e22;
}
QPushButton#btnCreateFRAC:hover {
    background-color: #cf6d17;
}
QTextEdit {
    border: 1px solid #dcdde1;
    border-radius: 4px;
    background-color: #ffffff;
}
QLabel#commentAuthor {
    color: #2c3e50;
    font-weight: bold;
}
QLabel#commentDate {
    color: #7f8c8d;
    font-size: 11px;
}
QLabel#fieldLabel {
    color: #7f8c8d;
    font-size: 11px;
}
QLabel#fieldValue {
    color: #2c3e50;
    font-size: 13px;
}
QLabel#sectionTitle {
    color: #2c3e50;
    font-size: 15px;
    font-weight: bold;
    padding: 4px 0;
}
QStatusBar {
    background-color: #2c3e50;
    color: #ecf0f1;
}
"""


# ── Worker threads ────────────────────────────────────────────────────
class SearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, jira_service, code):
        super().__init__()
        self.jira_service = jira_service
        self.code = code

    def run(self):
        try:
            issues = self.jira_service.search_tickets(self.code, max_results=50)
            results = []
            for issue in issues:
                details = self.jira_service.get_ticket_details(issue)
                results.append(details)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class CreateTicketWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, jira_service, ticket_type, code, short_text, reference, saldo):
        super().__init__()
        self.jira_service = jira_service
        self.ticket_type = ticket_type
        self.code = code
        self.short_text = short_text
        self.reference = reference
        self.saldo = saldo

    def run(self):
        try:
            if self.ticket_type == "ZS":
                ticket = self.jira_service.create_zs_ticket(
                    self.code, self.short_text, self.reference, self.saldo
                )
            else:
                ticket = self.jira_service.create_frac_ticket(
                    self.code, self.short_text, self.reference, self.saldo
                )
            self.finished.emit(ticket.key)
        except Exception as e:
            self.error.emit(str(e))


# ── Create ticket dialog ─────────────────────────────────────────────
class CreateTicketDialog(QDialog):
    def __init__(self, ticket_type, parent=None):
        super().__init__(parent)
        self.ticket_type = ticket_type
        self.setWindowTitle(f"Criar Ticket {ticket_type}")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Ex: 12345678")
        layout.addRow("Código do material:", self.code_input)

        self.short_text_input = QLineEdit()
        self.short_text_input.setPlaceholderText("Descrição curta do material")
        layout.addRow("Texto breve:", self.short_text_input)

        self.reference_input = QLineEdit()
        self.reference_input.setPlaceholderText("Referência atual")
        layout.addRow("Referência:", self.reference_input)

        self.saldo_input = QLineEdit("0")
        layout.addRow("Saldo virtual:", self.saldo_input)

        btn_layout = QHBoxLayout()
        self.btn_create = QPushButton("Criar")
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setStyleSheet("background-color: #95a5a6;")
        btn_layout.addWidget(self.btn_create)
        btn_layout.addWidget(self.btn_cancel)
        layout.addRow(btn_layout)

        self.btn_create.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def get_values(self):
        return {
            'code': self.code_input.text().strip(),
            'short_text': self.short_text_input.text().strip(),
            'reference': self.reference_input.text().strip(),
            'saldo': self.saldo_input.text().strip() or "0",
        }


# ── Main window ──────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.jira = JiraService()
        self.tickets_data = []
        self._worker = None

        self.setWindowTitle("Consulta ZS — Gerenciador de Tickets Jira")
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(STYLESHEET)

        self._build_ui()
        self.statusBar().showMessage("Pronto")

    # ── UI construction ───────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(8)

        # Search bar
        search_layout = QHBoxLayout()
        search_label = QLabel("Código do material:")
        search_label.setFont(QFont("Segoe UI", 10))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Digite o código e pressione Enter ou clique em Buscar")
        self.search_input.setMinimumWidth(300)
        self.search_input.returnPressed.connect(self._on_search)
        self.btn_search = QPushButton("Buscar")
        self.btn_search.clicked.connect(self._on_search)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.btn_search)
        root_layout.addLayout(search_layout)

        # Splitter: tickets table | detail panel
        splitter = QSplitter(Qt.Horizontal)

        # Left — tickets table
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        table_label = QLabel("Tickets encontrados")
        table_label.setObjectName("sectionTitle")
        left_layout.addWidget(table_label)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Chave", "Resumo", "Status", "Responsável", "Atualizado"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.currentCellChanged.connect(self._on_ticket_selected)
        left_layout.addWidget(self.table)

        # Create buttons under the table
        btn_row = QHBoxLayout()
        self.btn_create_zs = QPushButton("Criar Ticket ZS")
        self.btn_create_zs.setObjectName("btnCreateZS")
        self.btn_create_zs.clicked.connect(lambda: self._on_create_ticket("ZS"))
        self.btn_create_frac = QPushButton("Criar Ticket FRAC")
        self.btn_create_frac.setObjectName("btnCreateFRAC")
        self.btn_create_frac.clicked.connect(lambda: self._on_create_ticket("FRAC"))
        btn_row.addWidget(self.btn_create_zs)
        btn_row.addWidget(self.btn_create_frac)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left_widget)

        # Right — detail + comments panel (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(400)

        self.detail_container = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setAlignment(Qt.AlignTop)
        self.detail_layout.setSpacing(6)

        self._add_placeholder_detail()

        scroll.setWidget(self.detail_container)
        splitter.addWidget(scroll)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        root_layout.addWidget(splitter, 1)

    def _add_placeholder_detail(self):
        lbl = QLabel("Selecione um ticket para ver os detalhes e comentários.")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #95a5a6; font-size: 13px; padding: 40px;")
        self.detail_layout.addWidget(lbl)

    # ── Search ────────────────────────────────────────────────────────
    def _on_search(self):
        code = self.search_input.text().strip()
        if not code:
            return
        self.btn_search.setEnabled(False)
        self.statusBar().showMessage(f"Buscando tickets para '{code}'...")
        self._worker = SearchWorker(self.jira, code)
        self._worker.finished.connect(self._on_search_finished)
        self._worker.error.connect(self._on_search_error)
        self._worker.start()

    def _on_search_finished(self, results):
        self.btn_search.setEnabled(True)
        self.tickets_data = results
        self._populate_table()
        count = len(results)
        self.statusBar().showMessage(f"{count} ticket(s) encontrado(s)." if count else "Nenhum ticket encontrado.")

    def _on_search_error(self, msg):
        self.btn_search.setEnabled(True)
        self.statusBar().showMessage(f"Erro: {msg}")
        QMessageBox.warning(self, "Erro na busca", msg)

    def _populate_table(self):
        self.table.setRowCount(0)
        for row_idx, ticket in enumerate(self.tickets_data):
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(ticket['key']))
            self.table.setItem(row_idx, 1, QTableWidgetItem(ticket['summary']))
            self.table.setItem(row_idx, 2, QTableWidgetItem(ticket['status']))
            self.table.setItem(row_idx, 3, QTableWidgetItem(ticket['assignee']))
            self.table.setItem(row_idx, 4, QTableWidgetItem(ticket['updated'][:10]))

    # ── Detail panel ──────────────────────────────────────────────────
    def _on_ticket_selected(self, row, _col, _prev_row, _prev_col):
        if row < 0 or row >= len(self.tickets_data):
            return
        ticket = self.tickets_data[row]
        self._render_detail(ticket)

    def _clear_detail(self):
        while self.detail_layout.count():
            child = self.detail_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

    def _render_detail(self, ticket):
        self._clear_detail()

        # ── Ticket info group ──
        info_group = QGroupBox("Informações do Ticket")
        info_layout = QFormLayout()
        info_layout.setSpacing(6)

        fields = [
            ("Chave", ticket['key']),
            ("Resumo", ticket['summary']),
            ("Status", ticket['status']),
            ("Responsável", ticket['assignee']),
            ("Relator", ticket['reporter']),
            ("Prioridade", ticket['priority']),
            ("Criado em", ticket['created'][:19].replace('T', ' ')),
            ("Atualizado em", ticket['updated'][:19].replace('T', ' ')),
            ("Tipo", ticket['tipo']),
            ("Peças em estoque", ticket['pieces_in_stock']),
        ]
        for label_text, value in fields:
            label = QLabel(label_text)
            label.setObjectName("fieldLabel")
            val_label = QLabel(value or "—")
            val_label.setObjectName("fieldValue")
            val_label.setWordWrap(True)
            info_layout.addRow(label, val_label)

        info_group.setLayout(info_layout)
        self.detail_layout.addWidget(info_group)

        # ── Description group ──
        if ticket['description']:
            desc_group = QGroupBox("Descrição")
            desc_layout = QVBoxLayout()
            desc_text = QTextEdit()
            desc_text.setReadOnly(True)
            desc_text.setPlainText(ticket['description'])
            desc_text.setMaximumHeight(150)
            desc_layout.addWidget(desc_text)
            desc_group.setLayout(desc_layout)
            self.detail_layout.addWidget(desc_group)

        # ── Comments group ──
        comments = ticket.get('comments', [])
        comments_group = QGroupBox(f"Comentários ({len(comments)})")
        comments_layout = QVBoxLayout()
        comments_layout.setSpacing(10)

        if not comments:
            no_comments = QLabel("Nenhum comentário.")
            no_comments.setStyleSheet("color: #95a5a6; padding: 12px;")
            no_comments.setAlignment(Qt.AlignCenter)
            comments_layout.addWidget(no_comments)
        else:
            for comment in comments:
                card = self._build_comment_card(comment)
                comments_layout.addWidget(card)

        comments_group.setLayout(comments_layout)
        self.detail_layout.addWidget(comments_group)

        # Spacer
        self.detail_layout.addStretch()

    @staticmethod
    def _build_comment_card(comment):
        card = QWidget()
        card.setStyleSheet(
            "QWidget { background-color: #f8f9fa; border: 1px solid #ecf0f1; "
            "border-radius: 6px; padding: 10px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Header: author + date
        header = QHBoxLayout()
        author_lbl = QLabel(comment.get('author', 'Desconhecido'))
        author_lbl.setObjectName("commentAuthor")
        date_str = comment.get('created', '')[:19].replace('T', ' ')
        date_lbl = QLabel(date_str)
        date_lbl.setObjectName("commentDate")
        header.addWidget(author_lbl)
        header.addStretch()
        header.addWidget(date_lbl)
        layout.addLayout(header)

        # Body
        body_lbl = QLabel(comment.get('body', ''))
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet("color: #2c3e50; font-size: 12px; border: none; padding: 0;")
        layout.addWidget(body_lbl)

        return card

    # ── Create ticket ─────────────────────────────────────────────────
    def _on_create_ticket(self, ticket_type):
        dialog = CreateTicketDialog(ticket_type, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        values = dialog.get_values()
        if not values['code'] or not values['short_text']:
            QMessageBox.warning(self, "Campos obrigatórios", "Código e texto breve são obrigatórios.")
            return

        self.statusBar().showMessage(f"Criando ticket {ticket_type}...")
        self._worker = CreateTicketWorker(
            self.jira, ticket_type,
            values['code'], values['short_text'], values['reference'], values['saldo'],
        )
        self._worker.finished.connect(self._on_create_finished)
        self._worker.error.connect(self._on_create_error)
        self._worker.start()

    def _on_create_finished(self, key):
        self.statusBar().showMessage(f"Ticket {key} criado com sucesso!")
        QMessageBox.information(self, "Ticket Criado", f"Ticket {key} criado com sucesso!")

    def _on_create_error(self, msg):
        self.statusBar().showMessage("Erro ao criar ticket.")
        QMessageBox.critical(self, "Erro", f"Falha ao criar ticket:\n{msg}")


# ── Entry point ───────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
