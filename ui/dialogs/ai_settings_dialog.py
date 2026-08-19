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
    ("fire_conf", "Fire / Smoke", "Detection threshold for fire/smoke (fire_detection_new.pt model)"),
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

        face_group = QtWidgets.QGroupBox(tr("Face Recognition"))
        face_form = QtWidgets.QFormLayout(face_group)

        self.spin_face_similarity_threshold = QtWidgets.QDoubleSpinBox()
        self.spin_face_similarity_threshold.setRange(0.05, 0.95)
        self.spin_face_similarity_threshold.setSingleStep(0.05)
        self.spin_face_similarity_threshold.setDecimals(2)
        self.spin_face_similarity_threshold.setValue(settings.face_similarity_threshold)
        self.spin_face_similarity_threshold.setToolTip(
            tr(
                "How closely a detected face must match a known person to be recognized. Higher = stricter "
                "(fewer false matches, but may miss known people at bad angles/lighting). Lower = looser "
                "(recognizes known people more easily, but raises the risk of confusing 2 similar-looking "
                "people)."
            )
        )
        face_form.addRow(tr("Face match sensitivity"), self.spin_face_similarity_threshold)

        self.spin_face_memory_match_threshold = QtWidgets.QDoubleSpinBox()
        self.spin_face_memory_match_threshold.setRange(0.05, 0.95)
        self.spin_face_memory_match_threshold.setSingleStep(0.05)
        self.spin_face_memory_match_threshold.setDecimals(2)
        self.spin_face_memory_match_threshold.setValue(settings.face_memory_match_threshold)
        self.spin_face_memory_match_threshold.setToolTip(
            tr(
                "How closely 2 sightings must match to be treated as the SAME person when tracking briefly "
                "loses them (they turned away/looked down for a moment). Higher = stricter (safer, but may "
                "fail to reconnect after a bad angle - shows up as a fresh Stranger notification or a "
                "moment of \"Unknown\" for a known person). Lower = looser (reconnects more easily, but "
                "raises the risk of confusing 2 different people who look alike)."
            )
        )
        face_form.addRow(tr("Face memory match strictness"), self.spin_face_memory_match_threshold)
        layout.addWidget(face_group)

        stranger_group = QtWidgets.QGroupBox(tr("Stranger Anti-Spam"))
        stranger_form = QtWidgets.QFormLayout(stranger_group)

        self.spin_stranger_confirm_min_score = QtWidgets.QDoubleSpinBox()
        self.spin_stranger_confirm_min_score.setRange(0.05, 0.95)
        self.spin_stranger_confirm_min_score.setSingleStep(0.05)
        self.spin_stranger_confirm_min_score.setDecimals(2)
        self.spin_stranger_confirm_min_score.setValue(settings.stranger_confirm_min_score)
        self.spin_stranger_confirm_min_score.setToolTip(
            tr(
                "Minimum face detection quality required before a face is even considered for the "
                "Stranger alert - blurry/far/low-confidence faces below this are ignored instead of being "
                "judged."
            )
        )
        stranger_form.addRow(tr("Min. face quality to judge"), self.spin_stranger_confirm_min_score)

        self.spin_stranger_ambiguous_max_sim = QtWidgets.QDoubleSpinBox()
        self.spin_stranger_ambiguous_max_sim.setRange(0.05, 0.95)
        self.spin_stranger_ambiguous_max_sim.setSingleStep(0.05)
        self.spin_stranger_ambiguous_max_sim.setDecimals(2)
        self.spin_stranger_ambiguous_max_sim.setValue(settings.stranger_ambiguous_max_sim)
        self.spin_stranger_ambiguous_max_sim.setToolTip(
            tr(
                "Similarity must be at or below this value to confirm \"Stranger\". A face with some "
                "resemblance to a known person (above this, but below the match threshold) is treated as "
                "uncertain instead of Stranger - avoids false alerts for known people partly hidden by a "
                "mask/hair/bad angle. Lower this to reduce missed real strangers, raise it to reduce false "
                "Stranger alerts."
            )
        )
        stranger_form.addRow(tr("Max. similarity to confirm Stranger"), self.spin_stranger_ambiguous_max_sim)

        self.spin_stranger_min_frontal_ratio = QtWidgets.QDoubleSpinBox()
        self.spin_stranger_min_frontal_ratio.setRange(0.10, 1.00)
        self.spin_stranger_min_frontal_ratio.setSingleStep(0.05)
        self.spin_stranger_min_frontal_ratio.setDecimals(2)
        self.spin_stranger_min_frontal_ratio.setValue(settings.stranger_min_frontal_ratio)
        self.spin_stranger_min_frontal_ratio.setToolTip(
            tr(
                "How straight-on a face must be facing the camera before it can be judged Stranger. A "
                "turned/angled face - even if detected clearly - produces a less reliable face match, so it "
                "is treated as uncertain instead of Stranger until it turns to face the camera more "
                "directly. Lower this to accept more angled faces, raise it to require a more direct look."
            )
        )
        stranger_form.addRow(tr("Min. face angle (straight-on)"), self.spin_stranger_min_frontal_ratio)
        layout.addWidget(stranger_group)

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
        self.spin_face_similarity_threshold.setValue(defaults.face_similarity_threshold)
        self.spin_face_memory_match_threshold.setValue(defaults.face_memory_match_threshold)
        self.spin_stranger_confirm_min_score.setValue(defaults.stranger_confirm_min_score)
        self.spin_stranger_ambiguous_max_sim.setValue(defaults.stranger_ambiguous_max_sim)
        self.spin_stranger_min_frontal_ratio.setValue(defaults.stranger_min_frontal_ratio)

    def _on_accept(self) -> None:
        settings = AISettings.instance()
        for field, spin in self._conf_spins.items():
            setattr(settings, field, round(spin.value(), 2))
        settings.fall_confirm_window = self.spin_fall_window.value()
        settings.fall_confirm_min_count = self.spin_fall_min_count.value()
        settings.face_similarity_threshold = round(self.spin_face_similarity_threshold.value(), 2)
        settings.face_memory_match_threshold = round(self.spin_face_memory_match_threshold.value(), 2)
        settings.stranger_confirm_min_score = round(self.spin_stranger_confirm_min_score.value(), 2)
        settings.stranger_ambiguous_max_sim = round(self.spin_stranger_ambiguous_max_sim.value(), 2)
        settings.stranger_min_frontal_ratio = round(self.spin_stranger_min_frontal_ratio.value(), 2)
        settings.save()
        self.accept()
