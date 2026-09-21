import asyncio
import logging
from enum import Enum

from PySide6.QtWidgets import QComboBox, QDialog, QMessageBox
from PySide6.QtCore import Qt

from services import ServiceContainer
from ...components.widgets import TabButton
from .dialog_constants import (
    DIALOG_WIDTH_TRADE_TICKET, DIALOG_HEIGHT_TRADE_TICKET,
    INTERSECTION, SPACER_XS, SPACER_SMALL, SPACER_MEDIUM, SPACER_LARGE, LABEL_WIDTH_SMALL,
    INPUT_WIDTH_LARGE, SECTION_VERTICAL_SPACING,
)
from .frameless_dialog import FramelessDialog
from .order_dialog import OrderDialog
from .dialog_components import (
    DialogSection, GridRow,
    create_label_large, create_combo_small, create_combo_large,
    create_input_small, create_input_large, create_date_input_large,
    create_value_label_small, create_value_label_large,
)

logger = logging.getLogger(__name__)
BASE_CURRENCY = "USD"
MAX_CASH_ROWS = 4


class TradeMode(Enum):
    DELTA_ONE = "DELTA_ONE"
    DERIVATIVES = "DERIVATIVES"


class TradeTicketDialog(FramelessDialog):
    """Trade ticket. Name = combo des Names actifs (verrouillé après sélection) ou saisie libre :
    un Name connu remplit CONID / Position / Currency et charge son lot actif ; un Name nouveau
    ouvre des champs de saisie Position / Currency et crée un lot 'Xxx_NN'. Un CONID inconnu
    est résolu via IB quand la Gateway est connectée. ``entry`` = écriture à modifier."""

    def __init__(self, parent=None, *, mode: TradeMode, title: str, services: ServiceContainer,
                 entry: dict | None = None):
        super().__init__(parent, size=(DIALOG_WIDTH_TRADE_TICKET, DIALOG_HEIGHT_TRADE_TICKET), title=title)
        self.setWindowTitle("Trade")
        self._mode, self._services, self._entry = mode, services, entry
        self._instruments: dict[str, dict] = {}      # name → instrument
        self._details: dict | None = None            # contrat IB (nouvel instrument)
        self._lot_id = ""
        is_deriv = mode == TradeMode.DERIVATIVES
        self.content_layout.setContentsMargins(15, 13, 0, 0)

        # --- Identifiants -------------------------------------------------
        section = DialogSection(title="", left_margin=0)
        row = GridRow(0)
        row.add_col(create_label_large()).setText("Trade Date")
        self.date_edit = row.add_col(create_date_input_large())
        row.add_spacer(INTERSECTION)
        row.add_col(create_label_large()).setText("CONID")
        self.conid_edit = row.add_col(create_input_large())
        section.add_field(row.get_widget())
        row = GridRow(0)
        row.add_col(create_label_large()).setText("Name")
        self.name_combo = row.add_col(create_combo_large([""], editable=True))
        self.name_combo.setInsertPolicy(QComboBox.NoInsert)
        row.add_spacer(INTERSECTION)
        row.add_col(create_label_large()).setText("Position")
        self.position_value = row.add_col(create_value_label_large("-", align_left=False))
        self.position_edit = row.add_col(create_input_large())
        section.add_field(row.get_widget())
        self.content_layout.addWidget(section.get_widget())
        self.content_layout.addSpacing(SECTION_VERTICAL_SPACING)

        # --- Trade Information --------------------------------------------
        section = DialogSection(title="Trade Information")
        row = GridRow(0)
        row.add_col(create_label_large()).setText("Lot ID")
        row.add_spacer(SPACER_MEDIUM)
        self.lot_value = row.add_col(create_value_label_small("-", align_left=True))
        row.add_spacer(SPACER_SMALL + SPACER_MEDIUM + INTERSECTION)
        if is_deriv:
            row.add_col(create_value_label_small("Contract", align_left=True))
        else:
            row.add_col(create_label_large(width=LABEL_WIDTH_SMALL + SPACER_LARGE)).setText("Is Margin ?")
            self.margin_buttons = [TabButton("Y", is_active=False), TabButton("N", is_active=True)]
            for btn in self.margin_buttons:
                btn.setFixedWidth(40)
                btn.clicked.connect(lambda b=btn: self._set_margin(b))
                row.add_col(btn)
                row.add_spacer(SPACER_XS)
        section.add_field(row.get_widget())

        row = GridRow(0)
        self.side_combo = row.add_col(create_combo_small(["", "Buy", "Sell"]))
        row.add_spacer(SPACER_XS + SPACER_MEDIUM + SPACER_SMALL)
        self.quantity_edit = row.add_col(create_input_large())
        if is_deriv:
            row.add_spacer(INTERSECTION)
            self.call_put_combo = row.add_col(create_combo_small(["", "Call", "Put"]))
        section.add_field(row.get_widget())

        row = GridRow(0)
        row.add_col(create_label_large()).setText("Currency")
        row.add_spacer(SPACER_MEDIUM)
        self.currency_value = row.add_col(create_value_label_large("-", align_left=True))
        self.currency_edit = row.add_col(create_input_large())
        if is_deriv:
            row.add_spacer(INTERSECTION)
            row.add_col(create_label_large()).setText("Strike")
            row.add_spacer(SPACER_MEDIUM)
            self.strike_edit = row.add_col(create_input_small())
        section.add_field(row.get_widget())

        row = GridRow(0)
        row.add_col(create_label_large()).setText("Cost Price")
        row.add_spacer(SPACER_MEDIUM)
        self.price_edit = row.add_col(create_input_large())
        if is_deriv:
            row.add_spacer(INTERSECTION)
            row.add_col(create_label_large()).setText("Expiry")
            row.add_spacer(SPACER_MEDIUM)
            self.expiry_edit = row.add_col(create_input_small())
            self.expiry_edit.setPlaceholderText("YYYY-MM-DD")
        section.add_field(row.get_widget())

        row = GridRow(0)
        row.add_col(create_label_large()).setText("Base Price")
        row.add_spacer(SPACER_MEDIUM)
        self.base_edit = row.add_col(create_input_large())
        self.base_value = row.add_col(create_value_label_large("", align_left=True))
        section.add_field(row.get_widget())
        self.content_layout.addWidget(section.get_widget())
        self.content_layout.addSpacing(SECTION_VERTICAL_SPACING)

        # --- Account Information : Cash aligné sur Trade Information (devise à gauche,
        # montant au bord droit des champs), Account calé sur "Is Margin ?" ---------------
        section = DialogSection(title="Account Information")
        self.cash_rows: list[tuple] = []
        for i in range(MAX_CASH_ROWS):
            row = GridRow(0)
            row.add_col(create_label_large()).setText("Cash" if i == 0 else "")
            row.add_spacer(SPACER_MEDIUM)
            ccy_label = row.add_col(create_label_large(width=60))
            amount = row.add_col(create_value_label_small("", align_left=False))
            amount.setFixedWidth(INPUT_WIDTH_LARGE - 60)
            self.cash_rows.append((ccy_label, amount.label))
            if i == 0:
                row.add_spacer(INTERSECTION)
                row.add_col(create_label_large()).setText("Account")
                row.add_spacer(SPACER_MEDIUM)
                self.account_combo = row.add_col(create_combo_large(["IBK_LONG", "IBK_LEV"]))
            section.add_field(row.get_widget())
        self.content_layout.addWidget(section.get_widget())

        self.save_btn = self.make_button("Save", self._on_save_clicked)
        self.add_buttons_row([self.save_btn, self.make_button("Cancel", self.reject)])

        self._set_new_mode(False)
        self.name_combo.currentTextChanged.connect(self._on_name_changed)
        self.conid_edit.editingFinished.connect(lambda: asyncio.create_task(self._on_conid_changed()))
        self.price_edit.textChanged.connect(self._sync_base_price)
        self.currency_edit.textChanged.connect(self._sync_base_price)
        self.account_combo.currentTextChanged.connect(lambda _: asyncio.create_task(self._refresh_cash()))
        asyncio.create_task(self._bootstrap())

    # ------------------------------------------------------------------ état

    def _set_new_mode(self, new: bool) -> None:
        """Name inconnu → Position et Currency deviennent des champs de saisie."""
        self.position_value.setVisible(not new)
        self.currency_value.setVisible(not new)
        self.position_edit.setVisible(new)
        self.currency_edit.setVisible(new)
        self._sync_base_price()

    def _currency(self) -> str:
        return (self.currency_edit.text() if self.currency_edit.isVisible() else self.currency_value.label.text()).strip().upper()

    def _sync_base_price(self, *_) -> None:
        """En USD le prix de base est le prix d'achat : affiché, pas saisi."""
        usd = self._currency() == BASE_CURRENCY
        self.base_edit.setVisible(not usd)
        self.base_value.setVisible(usd)
        self.base_value.label.setText(self.price_edit.text())

    def _set_margin(self, clicked: TabButton) -> None:
        for btn in self.margin_buttons:
            btn.set_active(btn is clicked)
        self.account_combo.setCurrentText("IBK_LEV" if clicked.text() == "Y" else "IBK_LONG")

    # ------------------------------------------------------------------ données

    async def _bootstrap(self) -> None:
        try:
            instruments = await self._services.ledger.list_instruments()
        except Exception as ex:
            logger.exception("Trade ticket bootstrap failed")
            QMessageBox.critical(self, "Error", f"Failed to load ledger data: {ex}")
            return
        self._instruments = {i["name"]: i for i in instruments}
        active = sorted(i["name"] for i in instruments if i["active"] and i["type"] == self._mode.value)
        self.name_combo.blockSignals(True)
        self.name_combo.clear()
        self.name_combo.addItems(["", *active])
        self.name_combo.blockSignals(False)
        await self._refresh_cash()
        if self._entry:
            self._prefill(self._entry)

    def _prefill(self, entry: dict) -> None:
        security = next(ln for ln in entry["lines"] if ln["instrument_conid"])
        inst = next((i for i in self._instruments.values() if i["conid"] == security["instrument_conid"]), None)
        self.date_edit.setDate(self.date_edit.date().fromString(entry["date"], "yyyy-MM-dd"))
        self.name_combo.setCurrentText(inst["name"] if inst else "")
        self.conid_edit.setText(security["instrument_conid"])
        qty = abs(security["quantity"])
        self.side_combo.setCurrentText("Buy" if security["quantity"] > 0 else "Sell")
        self.quantity_edit.setText(f"{qty:g}")
        mult = (inst or {}).get("multiplier") or 1.0
        self.price_edit.setText(f"{abs(security['amount']) / (qty * mult):g}" if qty else "")
        if security["quantity"] > 0:
            self.base_edit.setText(f"{security['cost_basis']:g}")
        self.account_combo.setCurrentText(security["account_id"])
        self._lot_id = security["lot_id"] or ""
        self.lot_value.label.setText(self._lot_id)

    def _on_name_changed(self, text: str) -> None:
        text = text.strip()
        self.name_combo.lineEdit().setReadOnly(self.name_combo.findText(text) > 0)   # Name de la liste : verrouillé
        inst = self._instruments.get(text)
        if inst is None:
            self._details = None
            self._set_new_mode(bool(text))
            self.currency_edit.clear()
            self.position_edit.clear()
            if not text:                                   # ligne vide : état d'ouverture
                self.conid_edit.clear()
                self.position_value.label.setText("-")
                self.currency_value.label.setText("-")
                if self._mode == TradeMode.DERIVATIVES:
                    self.strike_edit.clear(); self.expiry_edit.clear(); self.call_put_combo.setCurrentIndex(0)
            self._set_lot(None, text)
            return
        self._set_new_mode(False)
        self.conid_edit.setText(inst["conid"])
        self.currency_value.label.setText(inst["currency"])
        self._sync_base_price()
        if self._mode == TradeMode.DERIVATIVES:
            self.strike_edit.setText("" if inst["strike"] is None else f"{inst['strike']:g}")
            self.expiry_edit.setText(inst["expiry"] or "")
            self.call_put_combo.setCurrentText({"C": "Call", "P": "Put"}.get(inst["right"] or "", ""))
        asyncio.create_task(self._load_context(inst))

    async def _load_context(self, inst: dict) -> None:
        ctx = await self._services.ledger.instrument_context(inst["conid"])
        if self.conid_edit.text().strip() != inst["conid"]:
            return
        self.position_value.label.setText(f"{ctx['position']:,.4f}".rstrip("0").rstrip("."))
        self._set_lot(ctx["lot_id"], inst["name"], inst["conid"])

    def _set_lot(self, open_lot: str | None, name: str, conid: str | None = None) -> None:
        """Modification : lot de l'écriture ; sinon lot actif de la security, sinon prochain 'Xxx_NN'."""
        if self._entry:
            return
        if open_lot or not name:
            self._lot_id = open_lot or ""
            self.lot_value.label.setText(self._lot_id or "-")
            return
        async def _next():
            self._lot_id = await self._services.ledger.next_lot_id(name, conid)
            self.lot_value.label.setText(self._lot_id)
        asyncio.create_task(_next())

    async def _on_conid_changed(self) -> None:
        conid = self.conid_edit.text().strip()
        known = next((i for i in self._instruments.values() if i["conid"] == conid), None)
        if known is not None:
            self.name_combo.setCurrentText(known["name"])
            return
        if not conid or not self._services.market.connected:
            return
        details = await self._services.market.contract_details(conid)
        if details is None or details["type"] != self._mode.value:
            return
        self._details = details
        if not self.name_combo.currentText().strip():
            self.name_combo.setCurrentText(details["name"])
        self.currency_edit.setText(details["currency"])
        if self._mode == TradeMode.DERIVATIVES:
            self.strike_edit.setText("" if details["strike"] is None else f"{details['strike']:g}")
            self.expiry_edit.setText(details["expiry"] or "")
            self.call_put_combo.setCurrentText({"C": "Call", "P": "Put"}.get(details["right"] or "", ""))

    async def _refresh_cash(self) -> None:
        account = self.account_combo.currentText()
        cash = await self._services.market.ib_cash(account) or await self._services.ledger.cash_balances(account)
        ordered = sorted(((c, a) for c, a in cash.items() if abs(a) >= 0.005), key=lambda kv: (kv[0] != BASE_CURRENCY, kv[0]))
        for i, (ccy_label, value_label) in enumerate(self.cash_rows):
            ccy, amount = ordered[i] if i < len(ordered) else ("", None)
            ccy_label.setText(ccy)
            value_label.setText("" if amount is None else f"{amount:,.2f}")
            ccy_label.parentWidget().setVisible(i == 0 or amount is not None)

    # ------------------------------------------------------------------ save

    def _on_save_clicked(self) -> None:
        asyncio.create_task(self._do_save())

    async def _do_save(self) -> None:
        is_deriv = self._mode == TradeMode.DERIVATIVES
        name, conid, currency = self.name_combo.currentText().strip(), self.conid_edit.text().strip(), self._currency()
        inst = self._instruments.get(name)
        try:
            side = {"Buy": "BUY", "Sell": "SELL"}[self.side_combo.currentText()]
            quantity, price = float(self.quantity_edit.text()), float(self.price_edit.text())
            base = price if currency == BASE_CURRENCY or not self.base_edit.text().strip() else float(self.base_edit.text())
            if not name or not conid or not currency or currency == "-":
                raise ValueError("Name, CONID and Currency are required")
            if not self._lot_id:
                raise ValueError("Lot ID is not resolved yet")
            if is_deriv:
                strike = float(self.strike_edit.text())
                expiry = self.expiry_edit.text().strip()
                right = {"Call": "C", "Put": "P"}[self.call_put_combo.currentText()]
            else:
                strike = expiry = right = None
        except (KeyError, ValueError) as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        multiplier = (self._details or inst or {}).get("multiplier") or (100.0 if is_deriv else 1.0)
        msg = f"{side} {quantity:g} {name} @ {price:g} {currency}" + (f" {right} {strike:g} {expiry}" if is_deriv else "")
        self.hide()
        if OrderDialog(msg, self).exec() != QDialog.DialogCode.Accepted:
            self.show(); self.raise_(); self.activateWindow()
            return
        self.save_btn.setEnabled(False)
        try:
            await self._services.ledger.add_trade(
                date=self.date_edit.date().toString("yyyy-MM-dd"), account=self.account_combo.currentText(),
                conid=conid, name=name, type=self._mode.value, currency=currency, side=side,
                quantity=quantity, price=price, cost_basis=base, lot_id=self._lot_id,
                expiry=expiry, strike=strike, right=right, multiplier=multiplier,
                symbol=(self._details or {}).get("symbol"),
                replace_id=self._entry["id"] if self._entry else None,
            )
            self.accept()
        except Exception as ex:
            self.save_btn.setEnabled(True)
            self.show(); self.raise_(); self.activateWindow()
            QMessageBox.critical(self, "Error", str(ex))


class DeltaOneDialog(TradeTicketDialog):
    def __init__(self, parent=None, *, services: ServiceContainer, entry: dict | None = None):
        super().__init__(parent, mode=TradeMode.DELTA_ONE, title="Delta-One Trade Ticket", services=services, entry=entry)


class DerivativesDialog(TradeTicketDialog):
    def __init__(self, parent=None, *, services: ServiceContainer, entry: dict | None = None):
        super().__init__(parent, mode=TradeMode.DERIVATIVES, title="Derivatives Trade Ticket", services=services, entry=entry)
