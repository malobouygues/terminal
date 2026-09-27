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
DES_CHOICES = ("Ordinary Shares", "Preferred Shares", "ADR", "GDR", "ADR Preferred", "GDR Preferred")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def derivative_des(right: str, strike: str, expiry: str) -> str:
    """'Call 500 Jan29' — vide tant que Call/Put, Strike et Expiry ne sont pas tous renseignés."""
    try:
        return f"{right} {float(strike):g} {_MONTHS[int(expiry[5:7]) - 1]}{expiry[2:4]}"
    except (ValueError, IndexError):
        return ""


class TradeMode(Enum):
    SECURITY = "SECURITY"
    DERIVATIVE = "DERIVATIVE"


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
        self._instruments: list[dict] = []           # instruments du mode (Security ou Derivative)
        self._details: dict | None = None            # contrat IB (nouvel instrument)
        self._lot_id = ""
        is_deriv = mode == TradeMode.DERIVATIVE
        self.content_layout.setContentsMargins(15, 13, 0, 0)

        # --- Identifiants -------------------------------------------------
        section = DialogSection(title="", left_margin=0)
        row = GridRow(0)
        row.add_col(create_label_large()).setText("Trade Date")
        self.date_edit = row.add_col(create_date_input_large())
        row.add_spacer(INTERSECTION)
        row.add_col(create_label_large()).setText("CONID")
        self.conid_value = row.add_col(create_value_label_large("-", align_left=True))
        self.conid_edit = row.add_col(create_input_large())
        section.add_field(row.get_widget())
        row = GridRow(0)
        row.add_col(create_label_large()).setText("Name")
        self.name_combo = row.add_col(create_combo_large([""], editable=True))
        self.name_combo.setInsertPolicy(QComboBox.NoInsert)
        row.add_spacer(INTERSECTION)
        row.add_col(create_label_large()).setText("Position")
        self.position_value = row.add_col(create_value_label_large("-", align_left=True))
        self.position_edit = row.add_col(create_input_large())
        section.add_field(row.get_widget())
        row = GridRow(0)
        row.add_col(create_label_large()).setText("Des")
        if is_deriv:        # composé depuis Call/Put + Strike + Expiry
            self.des_value = row.add_col(create_value_label_large("-", align_left=True))
        else:
            self.des_combo = row.add_col(create_combo_large(["", *DES_CHOICES]))
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
        self.currency_combo = row.add_col(create_combo_large([""]))
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
        if is_deriv:
            for w in (self.call_put_combo.currentTextChanged, self.strike_edit.textChanged, self.expiry_edit.textChanged):
                w.connect(self._sync_des)
        else:
            self.des_combo.currentTextChanged.connect(self._on_des_changed)
        self.currency_combo.currentTextChanged.connect(self._on_currency_changed)
        self.conid_edit.editingFinished.connect(lambda: asyncio.create_task(self._on_conid_changed()))
        self.price_edit.textChanged.connect(self._sync_base_price)
        self.account_combo.currentTextChanged.connect(lambda _: asyncio.create_task(self._refresh_cash()))
        asyncio.create_task(self._bootstrap())

    # ------------------------------------------------------------------ état

    def _set_new_mode(self, new: bool) -> None:
        """Instrument inconnu → CONID et Position deviennent des champs de saisie."""
        for value, edit in ((self.conid_value, self.conid_edit), (self.position_value, self.position_edit)):
            value.setVisible(not new)
            edit.setVisible(new)
        self._sync_base_price()

    def _conid(self) -> str:
        text = (self.conid_edit.text() if self.conid_edit.isVisible() else self.conid_value.label.text()).strip()
        return "" if text == "-" else text

    def _set_conid(self, conid: str) -> None:
        self.conid_value.label.setText(conid or "-")
        self.conid_edit.setText(conid)

    def _currency(self) -> str:
        return self.currency_combo.currentText().strip()

    def _sync_base_price(self, *_) -> None:
        """Le prix de base n'est saisi qu'en devise étrangère ; en USD il vaut le prix d'achat."""
        foreign = self._currency() not in ("", BASE_CURRENCY)
        self.base_edit.setVisible(foreign)
        self.base_value.setVisible(not foreign)
        self.base_value.label.setText(self.price_edit.text().strip() or "-")

    def _des(self) -> str:
        text = (self.des_value.label.text() if self._mode == TradeMode.DERIVATIVE
                else self.des_combo.currentText()).strip()
        return "" if text == "-" else text

    def _set_des(self, des: str) -> None:
        if self._mode == TradeMode.DERIVATIVE:
            self.des_value.label.setText(des or "-")
        else:
            self.des_combo.blockSignals(True)
            self.des_combo.setCurrentText(des)
            self.des_combo.blockSignals(False)

    def _sync_des(self, *_) -> None:
        self.des_value.label.setText(
            derivative_des(self.call_put_combo.currentText(), self.strike_edit.text(), self.expiry_edit.text()) or "-")

    def _set_margin(self, clicked: TabButton) -> None:
        for btn in self.margin_buttons:
            btn.set_active(btn is clicked)
        self.account_combo.setCurrentText("IBK_LEV" if clicked.text() == "Y" else "IBK_LONG")

    # ------------------------------------------------------------------ données

    async def _bootstrap(self) -> None:
        try:
            instruments, currencies = await asyncio.gather(
                self._services.ledger.list_instruments(), self._services.ledger.list_currencies())
        except Exception as ex:
            logger.exception("Trade ticket bootstrap failed")
            QMessageBox.critical(self, "Error", f"Failed to load ledger data: {ex}")
            return
        self._instruments = [i for i in instruments if i["type"] == self._mode.value]
        active = sorted({i["name"] for i in self._instruments if i["active"]})
        for combo, items in ((self.name_combo, active), (self.currency_combo, currencies)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(["", *items])
            combo.blockSignals(False)
        await self._refresh_cash()
        if self._entry:
            self._prefill(self._entry)

    def _prefill(self, entry: dict) -> None:
        security = next(ln for ln in entry["lines"] if ln["instrument_conid"])
        inst = self._by_conid(security["instrument_conid"])
        self.date_edit.setDate(self.date_edit.date().fromString(entry["date"], "yyyy-MM-dd"))
        self.name_combo.setCurrentText(inst["name"] if inst else "")
        self._set_des(inst["des"] if inst else "")
        self.currency_combo.setCurrentText(security["currency"])
        self._set_conid(security["instrument_conid"])
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

    def _by_conid(self, conid: str) -> dict | None:
        return next((i for i in self._instruments if i["conid"] == conid), None)

    def _on_name_changed(self, text: str) -> None:
        """Le Name ne présélectionne rien : Des, Currency et CONID restent à choisir."""
        text = text.strip()
        self.name_combo.lineEdit().setReadOnly(self.name_combo.findText(text) > 0)   # Name de la liste : verrouillé
        self._details = None
        self._set_conid("")
        self.currency_combo.setCurrentIndex(0)
        if self._mode != TradeMode.DERIVATIVE:
            self._set_des("")
        self._resolve()

    def _on_des_changed(self, _text: str) -> None:
        """Le Des ne présélectionne pas la devise : le triplet n'est résolu qu'une fois complet."""
        self._resolve()

    def _on_currency_changed(self, _text: str) -> None:
        self._sync_base_price()
        self._resolve()

    def _resolve(self) -> None:
        """Name + Des + Currency identifient l'instrument (clé unique). Tant qu'un choix manque,
        CONID et Position restent en attente ; dès qu'un choix ne correspond à rien, ils passent
        en saisie — c'est un nouvel instrument."""
        name, des, ccy = self.name_combo.currentText().strip(), self._des(), self._currency()
        candidates = [i for i in self._instruments if i["name"] == name]
        if des:
            candidates = [i for i in candidates if i["des"] == des]
        if ccy:
            candidates = [i for i in candidates if i["currency"] == ccy]
        self._set_new_mode(bool(name) and not candidates)

        inst = candidates[0] if (candidates and des and ccy) else None
        if inst is None:
            if self._by_conid(self._conid()):     # CONID hérité d'une autre déclinaison
                self._set_conid("")
            self.position_edit.clear()
            self.position_value.label.setText("-")
            same = next((i for i in self._instruments if i["name"] == name), None)
            self._set_lot(None, name, same["conid"] if same else None)
            return
        self._details = None
        self._set_conid(inst["conid"])
        if self._mode == TradeMode.DERIVATIVE:
            self.strike_edit.setText("" if inst["strike"] is None else f"{inst['strike']:g}")
            self.expiry_edit.setText(inst["expiry"] or "")
            self.call_put_combo.setCurrentText({"C": "Call", "P": "Put"}.get(inst["right"] or "", ""))
        asyncio.create_task(self._load_context(inst))

    async def _load_context(self, inst: dict) -> None:
        ctx = await self._services.ledger.instrument_context(inst["conid"])
        if self._conid() != inst["conid"]:
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
        conid = self._conid()
        known = self._by_conid(conid)
        if known is not None:
            self.name_combo.setCurrentText(known["name"])
            self._set_des(known["des"])
            self.currency_combo.setCurrentText(known["currency"])
            self._set_conid(conid)
            return
        if not conid or not self._services.market.connected:
            return
        details = await self._services.market.contract_details(conid)
        if details is None or details["type"] != self._mode.value:
            return
        self._details = details
        if not self.name_combo.currentText().strip():
            self.name_combo.setCurrentText(details["name"])
        self.currency_combo.setCurrentText(details["currency"])
        self._set_conid(conid)
        if self._mode == TradeMode.DERIVATIVE:
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
        is_deriv = self._mode == TradeMode.DERIVATIVE
        name, conid, currency = self.name_combo.currentText().strip(), self._conid(), self._currency()
        des = self._des()
        inst = self._by_conid(conid)
        try:
            side = {"Buy": "BUY", "Sell": "SELL"}[self.side_combo.currentText()]
            quantity, price = float(self.quantity_edit.text()), float(self.price_edit.text())
            base = price if currency == BASE_CURRENCY or not self.base_edit.text().strip() else float(self.base_edit.text())
            if not name or not conid or not currency or currency == "-":
                raise ValueError("Name, CONID and Currency are required")
            if not des:
                raise ValueError("Des is required")
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
        msg = f"{side} {quantity:g} {name} {des} @ {price:g} {currency}"
        self.hide()
        if OrderDialog(msg, self).exec() != QDialog.DialogCode.Accepted:
            self.show(); self.raise_(); self.activateWindow()
            return
        self.save_btn.setEnabled(False)
        try:
            await self._services.ledger.add_trade(
                date=self.date_edit.date().toString("yyyy-MM-dd"), account=self.account_combo.currentText(),
                conid=conid, name=name, des=des, type=self._mode.value, currency=currency, side=side,
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


class SecurityDialog(TradeTicketDialog):
    def __init__(self, parent=None, *, services: ServiceContainer, entry: dict | None = None):
        super().__init__(parent, mode=TradeMode.SECURITY, title="Security Trade Ticket", services=services, entry=entry)


class DerivativeDialog(TradeTicketDialog):
    def __init__(self, parent=None, *, services: ServiceContainer, entry: dict | None = None):
        super().__init__(parent, mode=TradeMode.DERIVATIVE, title="Derivative Trade Ticket", services=services, entry=entry)
