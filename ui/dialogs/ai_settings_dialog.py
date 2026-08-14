"""AISettingsDialog: chỉnh ngưỡng confidence của từng model AI dùng chung
(core/ai_model_manager.py) + tham số xác nhận té ngã (core/camera_pipeline.py) -
lưu qua core/ai_settings.py (config/ai_settings.json), áp dụng NGAY cho mọi
camera đang chạy, không cần khởi động lại app."""
from __future__ import annotations

from PyQt6 import QtWidgets

from core.ai_settings import AISettings
from ui.ui_menu.i18n import tr

# (field, label, tooltip) - áp dụng cho cả 5 ngưỡng confidence, chỉ khác
# label/tooltip hiển thị. Label/tooltip là KEY tiếng Anh cho tr() (khớp quy
# ước chung của app - xem ui/ui_menu/i18n/strings.py), không phải text hiển
# thị trực tiếp.
_CONF_FIELDS = [
    ("pose_conf", "Pose / Body", "Detection threshold for body/pose (used by Fall - needs keypoints)"),
    ("human_conf", "Human Detection", "Detection threshold for head detection (count in/out, occupancy, PPE zone-check)"),
    ("ppe_conf", "PPE", "Detection threshold for vest/helmet"),
    ("fire_conf", "Fire / Smoke", "Detection threshold for fire/smoke"),
    ("fall_conf", "Fall", "Detection threshold for fall pose (fall_detection_new.pt model)"),
]


class AISettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("AI Settings"))
        self.setMinimumWidth(460)

        settings = AISettings.instance()
        layout = QtWidgets.QVBoxLayout(self)

        hint = QtWidgets.QLabel(
            tr("Applies immediately to every running camera - no restart needed.")
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #7a8aaa; font-size: 11px;")
        layout.addWidget(hint)

        conf_group = QtWidgets.QGroupBox(tr("Detection Confidence"))
        conf_form = QtWidgets.QFormLayout(conf_group)
        self._conf_spins: dict[str, QtWidgets.QDoubleSpinBox] = {}
        for field, label, tooltip in _CONF_FIELDS:
            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(0.05, 0.95)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setValue(getattr(settings, field))
            spin.setToolTip(tr(tooltip))
            conf_form.addRow(tr(label), spin)
            self._conf_spins[field] = spin
        layout.addWidget(conf_group)

        fall_group = QtWidgets.QGroupBox(tr("Fall Confirmation"))
        fall_form = QtWidgets.QFormLayout(fall_group)

        self.spin_fall_window = QtWidgets.QSpinBox()
        self.spin_fall_window.setRange(1, 60)
        self.spin_fall_window.setValue(settings.fall_confirm_window)
        self.spin_fall_window.setToolTip(
            tr("Number of recent AI ticks kept to decide whether a fall is confirmed.")
        )
        self.spin_fall_window.valueChanged.connect(self._on_window_changed)
        fall_form.addRow(tr("Confirmation window (AI ticks)"), self.spin_fall_window)

        self.spin_fall_min_count = QtWidgets.QSpinBox()
        self.spin_fall_min_count.setRange(1, settings.fall_confirm_window)
        self.spin_fall_min_count.setValue(settings.fall_confirm_min_count)
        self.spin_fall_min_count.setToolTip(
            tr(
                "Minimum number of \"falling\" ticks (within the window above) required "
                "before raising the Fall alert / drawing the Fall box."
            )
        )
        fall_form.addRow(tr("Min. falling ticks to confirm"), self.spin_fall_min_count)
        layout.addWidget(fall_group)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_reset = buttons.addButton(
            tr("Reset to Defaults"), QtWidgets.QDialogButtonBox.ButtonRole.ResetRole
        )
        self.btn_reset.clicked.connect(self._on_reset_defaults)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_window_changed(self, value: int) -> None:
        # Min. falling ticks không được vượt quá window - kẹp lại ngay khi
        # window thu nhỏ hơn giá trị đang chọn, tránh trạng thái vô lý.
        self.spin_fall_min_count.setMaximum(value)

    def _on_reset_defaults(self) -> None:
        defaults = AISettings()
        for field, spin in self._conf_spins.items():
            spin.setValue(getattr(defaults, field))
        self.spin_fall_window.setValue(defaults.fall_confirm_window)
        self.spin_fall_min_count.setValue(defaults.fall_confirm_min_count)

    def _on_accept(self) -> None:
        settings = AISettings.instance()
        for field, spin in self._conf_spins.items():
            setattr(settings, field, round(spin.value(), 2))
        settings.fall_confirm_window = self.spin_fall_window.value()
        settings.fall_confirm_min_count = self.spin_fall_min_count.value()
        settings.save()
        self.accept()
