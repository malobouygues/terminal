import asyncio
import logging

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDialog, QMessageBox

from services import LedgerService
from .frameless_dialog import FramelessDialog
from .order_dialog import OrderDialog
from .dialog_constants import DIALOG_WIDTH_FUNDING, DIALOG_HEIGHT_FUNDING, INPUT_WIDTH_SMALL, SPACER_LARGE
from .dialog_components import (
    DialogSection, GridRow, create_label_large, create_combo_small, create_input_small,
    create_date_input_small, create_value_label_small,
)

logger = logging.getLogger(__name__)
NA = "n/a"


class CashDialog(FramelessDialog):
    """Deposit : From = n/a, devises du compte To. Withdrawal : To = n/a, devises du compte
    From. Transfer : IBK_LEV ↔ IBK_LONG (choisir l'un fixe l'autre). ``entry`` = écriture à modifier."""

    def __init__(self, parent=None, *, ledger: LedgerService, entry: dict | None = None):
        super().__init__(parent, size=(DIALOG_WIDTH_FUNDING, DIALOG_HEIGHT_FUNDING))
        self.setWindowTitle("Cash")
        self._ledger, self._entry = ledger, entry
        self._accounts: list[str] = []
        self.content_layout.setContentsMargins(12, 40, 0, 0)

        section = DialogSection(title="", spacing=15)
        row = GridRow(0)
        self.type_combo = row.add_col(create_combo_small(["", "Deposit", "Withdrawal", "Transfer"]))
        section.add_field(row.get_widget())
        self.date_edit = create_date_input_small()
        self.from_combo, self.to_combo, self.currency_combo = (create_combo_small([""]) for _ in range(3))
        for combo in (self.from_combo, self.to_combo, self.currency_combo):
            combo.setFixedSize(INPUT_WIDTH_SMALL, 20)          # même largeur que les champs
        self.from_na, self.to_na = (create_value_label_small(NA, align_left=True) for _ in range(2))
        self.amount_edit = create_input_small()
        for label, widgets in (("Date", (self.date_edit,)), ("From Account", (self.from_combo, self.from_na)),
                               ("To Account", (self.to_combo, self.to_na)), ("Amount", (self.amount_edit,)),
                               ("Currency", (self.currency_combo,))):
            row = GridRow(0)
            row.add_col(create_label_large()).setText(label)
            row.add_spacer(SPACER_LARGE)
            for w in widgets:
                row.add_col(w)
            section.add_field(row.get_widget())
        self.content_layout.addWidget(section.get_widget())

        self.save_btn = self.make_button("Save", lambda: asyncio.create_task(self._do_save()))
        self.add_buttons_row([self.save_btn, self.make_button("Cancel", self.reject)])

        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self.from_combo.currentTextChanged.connect(lambda _: self._on_account_changed(self.from_combo))
        self.to_combo.currentTextChanged.connect(lambda _: self._on_account_changed(self.to_combo))
        self._on_type_changed("")
        asyncio.create_task(self._bootstrap())

    async def _bootstrap(self) -> None:
        try:
            self._accounts = await self._ledger.list_accounts()
        except Exception as ex:
            logger.exception("Failed to bootstrap CashDialog")
            QMessageBox.critical(self, "Error", f"Failed to load ledger data: {ex}")
            return
        self._on_type_changed(self.type_combo.currentText())
        if self._entry:
            await self._prefill(self._entry)

    async def _prefill(self, entry: dict) -> None:
        lines = entry["lines"]
        credit = next((ln for ln in lines if ln["amount"] > 0), None)
        debit = next((ln for ln in lines if ln["amount"] < 0), None)
        self.type_combo.setCurrentText(entry["transaction_type"].capitalize())
        self.date_edit.setDate(QDate.fromString(entry["date"], "yyyy-MM-dd"))
        if debit:
            self.from_combo.setCurrentText(debit["account_id"])
        if credit:
            self.to_combo.setCurrentText(credit["account_id"])
        await self._refresh_currencies()
        self.amount_edit.setText(f"{abs(lines[0]['amount']):g}")
        self.currency_combo.setCurrentText(lines[0]["currency"])

    @staticmethod
    def _fill(combo, items: list[str], enabled: bool = True) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)
        combo.setEnabled(enabled)
        combo.blockSignals(False)

    def _on_type_changed(self, tx_type: str) -> None:
        accounts = ["", *self._accounts]
        from_na, to_na = tx_type == "Deposit", tx_type == "Withdrawal"
        self.from_combo.setVisible(not from_na)
        self.from_na.setVisible(from_na)
        self.to_combo.setVisible(not to_na)
        self.to_na.setVisible(to_na)
        enabled = tx_type in ("Deposit", "Withdrawal", "Transfer")
        self._fill(self.from_combo, accounts if enabled else [""], enabled)
        self._fill(self.to_combo, accounts if enabled else [""], enabled)
        self._fill(self.currency_combo, [""], enabled)

    def _on_account_changed(self, combo) -> None:
        if self.type_combo.currentText() == "Transfer" and combo.currentText():
            other = self.to_combo if combo is self.from_combo else self.from_combo
            counterpart = next((a for a in self._accounts if a != combo.currentText()), "")
            other.blockSignals(True)
            other.setCurrentText(counterpart)
            other.blockSignals(False)
        asyncio.create_task(self._refresh_currencies())

    async def _refresh_currencies(self) -> None:
        account = (self.to_combo if self.type_combo.currentText() == "Deposit" else self.from_combo).currentText()
        if not account:
            self._fill(self.currency_combo, [""])
            return
        try:
            currencies = await self._ledger.list_currencies_for_account(account) or await self._ledger.list_currencies()
        except Exception:
            logger.exception("Failed to refresh currencies for %r", account)
            return
        current = self.currency_combo.currentText()
        self._fill(self.currency_combo, ["", *currencies])
        self.currency_combo.setCurrentText(current)      # conserve la devise déjà choisie (modification)

    async def _do_save(self) -> None:
        tx_type = self.type_combo.currentText()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        from_acc, to_acc = self.from_combo.currentText(), self.to_combo.currentText()
        currency = self.currency_combo.currentText()
        try:
            amount = float(self.amount_edit.text())
            if not tx_type:
                raise ValueError("Please select an operation type.")
            if not currency:
                raise ValueError("Please select a currency.")
            if tx_type != "Withdrawal" and not to_acc:
                raise ValueError("Please select the To account.")
            if tx_type != "Deposit" and not from_acc:
                raise ValueError("Please select the From account.")
        except ValueError as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        msg = {"Deposit": f"DEPOSIT {amount:g} {currency} to {to_acc}",
               "Withdrawal": f"WITHDRAWAL {amount:g} {currency} from {from_acc}",
               "Transfer": f"TRANSFER {amount:g} {currency} from {from_acc} to {to_acc}"}[tx_type]
        self.hide()
        if OrderDialog(msg, self).exec() != QDialog.DialogCode.Accepted:
            self.show(); self.raise_(); self.activateWindow()
            return
        self.save_btn.setEnabled(False)
        replace_id = self._entry["id"] if self._entry else None
        try:
            if tx_type == "Deposit":
                await self._ledger.add_deposit(date, to_acc, amount, currency, replace_id)
            elif tx_type == "Withdrawal":
                await self._ledger.add_withdrawal(date, from_acc, amount, currency, replace_id)
            else:
                await self._ledger.add_transfer(date, from_acc, to_acc, amount, currency, replace_id)
            self.accept()
        except Exception as ex:
            self.save_btn.setEnabled(True)
            self.show(); self.raise_(); self.activateWindow()
            QMessageBox.critical(self, "Error", str(ex))
