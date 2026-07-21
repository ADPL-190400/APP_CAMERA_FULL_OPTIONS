"""Dialog thêm / sửa 1 Trigger Rule (IF condition THEN action)."""
from __future__ import annotations

from PyQt6 import QtWidgets

from core.models.camera_device import TriggerRule


class TriggerRuleDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, rule: TriggerRule | None = None):
        super().__init__(parent)
        self.setWindowTitle("Trigger Rule")
        self.setMinimumWidth(420)

        layout = QtWidgets.QFormLayout(self)

        self.edit_name = QtWidgets.QLineEdit(rule.name if rule else "Rule")
        layout.addRow("Tên rule", self.edit_name)

        self.edit_condition = QtWidgets.QLineEdit(rule.condition if rule else "")
        self.edit_condition.setPlaceholderText("e.g. person count > 0 in ROI-1")
        layout.addRow("Điều kiện (IF)", self.edit_condition)

        self.edit_action = QtWidgets.QLineEdit(rule.action if rule else "")
        self.edit_action.setPlaceholderText("e.g. send notification + record 10s")
        layout.addRow("Hành động (THEN)", self.edit_action)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_rule(self) -> TriggerRule:
        return TriggerRule(
            name=self.edit_name.text().strip() or "Rule",
            condition=self.edit_condition.text().strip(),
            action=self.edit_action.text().strip(),
        )