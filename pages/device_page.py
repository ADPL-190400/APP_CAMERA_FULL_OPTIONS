"""
Controller cho device_management_page.ui.

Trang này KHÔNG tự giữ danh sách camera. Mọi dữ liệu đọc/ghi qua
DeviceManager.instance() -> khi camera_config_page (hoặc trang khác) sửa
1 camera, trang này tự cập nhật lại nhờ signal, không cần gọi qua lại.
"""
from __future__ import annotations

import os

from PyQt6 import uic, QtWidgets
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QMessageBox, QTableWidgetItem, QHeaderView

from core.path_manager import BASE_DIR
from core.device_manager import DeviceManager
from core.device_discovery import DeviceDiscoveryWorker
from core.models.camera_device import CameraDevice, DeviceStatus
from ui.dialogs.add_device_dialog import AddDeviceDialog
from ui.ui_menu.i18n import LanguageManager, tr

# Vị trí cột trong tableWidget (đúng thứ tự cột định nghĩa trong .ui)
COL_CHECK = 0
COL_NAME = 1
COL_IP = 2
COL_MAC = 3
COL_SERIAL = 4
COL_STATUS = 5
COL_OPERATION = 6

# DeviceStatus -> giá trị property "statusKind" cho QSS (ui/themes/theme_*.qss,
# khối QLabel[cardRole="statusBadge"]) - trước đây tô màu bằng
# QTableWidgetItem.setBackground()/setForeground() trực tiếp trong code, bị
# theme light ghi đè mất màu (QSS đặt color/background-color trên
# QTableWidget nuốt mất brush đặt theo item - lỗi Qt đã biết), nên đổi sang
# cell widget (QLabel + dynamic property) như mọi badge khác trong app
# (camera_card.py, face_card.py) - không bị việc đó nữa.
_STATUS_KIND = {
    DeviceStatus.ONLINE: "online",
    DeviceStatus.OFFLINE: "offline",
    DeviceStatus.ERROR: "error",
    DeviceStatus.UNKNOWN: "unknown",
}

_TR_TEXT_MAP = {
    "btn_add_device": "+ Add",
    "btn_find_online_devices": "🔍 Online Device",
    "btn_delete_device": "🗑  Delete",
    "btn_refresh_device": "↻  Refresh",
    "btn_start_device": "▶  Start",
    "btn_stop_device": "■  Stop",
}
_TR_TABLE_HEADERS = ["", "Name", "IP", "MAC Address", "Serial No.", "Status", "Operation"]


class DeviceManagementPage(QtWidgets.QWidget):
    # Phát ra khi người dùng bấm "Config" trên 1 dòng -> MainWindow / PageManager
    # lắng nghe signal này để chuyển qua camera_config_page và load đúng camera.
    open_camera_config = pyqtSignal(str)  # device_id

    def __init__(self):
        super().__init__()
        ui_path = os.path.join(BASE_DIR, "ui", "device_management_page.ui")
        uic.loadUi(ui_path, self)

        self.device_manager = DeviceManager.instance()
        self._discovery_worker: DeviceDiscoveryWorker | None = None

        self._setup_table()
        self._connect_buttons()
        self._connect_device_manager_signals()

        self.reload_table()

        self.retranslate_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    # ------------------------------------------------------------------ #
    # i18n
    # ------------------------------------------------------------------ #
    def retranslate_ui(self, _lang: str = "") -> None:
        for attr, key in _TR_TEXT_MAP.items():
            getattr(self, attr).setText(tr(key))
        self.lineEdit.setPlaceholderText(tr("filter"))
        for col, key in enumerate(_TR_TABLE_HEADERS):
            if not key:
                continue
            item = self.tableWidget.horizontalHeaderItem(col)
            if item is not None:
                item.setText(tr(key))
        self.reload_table()

    # ------------------------------------------------------------------ #
    # Khởi tạo
    # ------------------------------------------------------------------ #
    def _setup_table(self) -> None:
        header = self.tableWidget.horizontalHeader()
        # Chỉ Name (thông tin đáng xem đầy đủ nhất) chiếm phần dư ra
        # (Stretch) - các cột còn lại tự co theo đúng nội dung/tiêu đề
        # (ResizeToContents) thay vì để Qt tự đặt độ rộng mặc định tuỳ tiện,
        # tránh tình trạng Name phình quá to và các cột sau bị dồn/lấn nhau
        # (bug đã gặp).
        # COL_CHECK chứa cell WIDGET (container bọc QCheckBox, không phải
        # QTableWidgetItem) - cùng vấn đề với COL_STATUS bên dưới:
        # ResizeToContents đo sizeHint widget không đáng tin cậy -> cột bị co
        # hẹp hơn checkbox thật, checkbox hiển thị không đủ (bug đã gặp). Đặt
        # cố định đủ rộng thay vì auto-measure; vẫn Interactive để kéo giãn
        # được nếu cần.
        header.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(COL_CHECK, 40)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_IP, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_MAC, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_SERIAL, QHeaderView.ResizeMode.ResizeToContents)
        # COL_STATUS chứa cell WIDGET (badge, không phải QTableWidgetItem) -
        # ResizeToContents đo sizeHint widget KHÔNG đáng tin cậy (đo trước khi
        # QSS polish xong, ra kích thước hụt) -> chữ "Online"/"Offline · Running"
        # bị cắt (bug đã gặp). Đặt cố định đủ rộng cho text dài nhất thay vì
        # auto-measure; vẫn Interactive để người dùng tự kéo giãn được nếu cần.
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(COL_STATUS, 130)
        header.setSectionResizeMode(COL_OPERATION, QHeaderView.ResizeMode.ResizeToContents)
        self.tableWidget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableWidget.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._setup_header_check_all()

    def _setup_header_check_all(self) -> None:
        """Checkbox "Check All" nhúng ngay trong header cột checkbox (đầu
        bảng, hàng tiêu đề) - tích vào thì tick hết các dòng bên dưới, bỏ
        tích thì bỏ tick hết. Qt không hỗ trợ đặt widget vào header sẵn (chỉ
        QTableWidget.setCellWidget cho các dòng dữ liệu), nên overlay 1
        QCheckBox làm con của header rồi tự định vị theo đúng vị trí/độ rộng
        cột COL_CHECK - phải tự cập nhật lại vị trí khi cột đó bị resize."""
        header = self.tableWidget.horizontalHeader()
        self._header_check_all = QCheckBox(header)
        self._header_check_all.toggled.connect(self._on_header_check_all_toggled)
        header.sectionResized.connect(lambda *_: self._position_header_check_all())
        self._position_header_check_all()
        # Lúc này header có thể chưa layout xong (height/width = 0) -> định
        # vị lại 1 lần nữa ngay sau khi event loop xử lý xong show ban đầu.
        QTimer.singleShot(0, self._position_header_check_all)

    def _position_header_check_all(self) -> None:
        header = self.tableWidget.horizontalHeader()
        x = header.sectionViewportPosition(COL_CHECK)
        w = header.sectionSize(COL_CHECK)
        size = self._header_check_all.sizeHint()
        self._header_check_all.move(
            x + max(0, (w - size.width()) // 2),
            max(0, (header.height() - size.height()) // 2),
        )

    def _on_header_check_all_toggled(self, checked: bool) -> None:
        for row in range(self.tableWidget.rowCount()):
            checkbox = self._row_checkbox(row)
            if checkbox is not None:
                checkbox.setChecked(checked)

    def _row_checkbox(self, row: int) -> QCheckBox | None:
        """setCellWidget(row, COL_CHECK) trả về container bọc ngoài (xem
        _add_row - cần bọc để canh giữa checkbox trong ô), không phải chính
        QCheckBox - hàm này tìm đúng checkbox bên trong container đó."""
        container = self.tableWidget.cellWidget(row, COL_CHECK)
        return container.findChild(QCheckBox) if container is not None else None

    def _connect_buttons(self) -> None:
        self.btn_add_device.clicked.connect(self._on_add_device)
        self.btn_find_online_devices.clicked.connect(self._on_find_online_devices)
        self.btn_delete_device.clicked.connect(self._on_delete_device)
        self.btn_refresh_device.clicked.connect(self.reload_table)
        self.btn_start_device.clicked.connect(self._on_start_device)
        self.btn_stop_device.clicked.connect(self._on_stop_device)
        self.lineEdit.textChanged.connect(self._on_filter_changed)

    def _connect_device_manager_signals(self) -> None:
        # Bất kể danh sách bị thay đổi từ đâu (trang này, camera_config_page,
        # hay 1 worker nền), tableWidget đều tự vẽ lại.
        self.device_manager.devices_changed.connect(self.reload_table)
        self.device_manager.device_status_changed.connect(lambda *_: self.reload_table())
        self.device_manager.device_running_changed.connect(lambda *_: self.reload_table())

    # ------------------------------------------------------------------ #
    # Render bảng
    # ------------------------------------------------------------------ #
    def reload_table(self) -> None:
        keyword = self.lineEdit.text().strip().lower()
        devices = self.device_manager.all_devices()
        if keyword:
            devices = [
                d for d in devices
                if keyword in d.name.lower() or keyword in d.ip_address.lower()
            ]

        self.tableWidget.setRowCount(0)
        for device in devices:
            self._add_row(device)
        # setCellWidget() không tự kích hoạt tính lại chiều cao dòng như
        # QTableWidgetItem - gọi tường minh để dòng luôn đủ cao chứa widget
        # (checkbox/status badge/nút Operation), tránh bị cắt/tràn ra ngoài.
        self.tableWidget.resizeRowsToContents()

        self.lbl_total_find.setText(tr("Total({n})").format(n=len(devices)))

    def _add_row(self, device: CameraDevice) -> None:
        row = self.tableWidget.rowCount()
        self.tableWidget.insertRow(row)

        # Cột checkbox để chọn nhiều dòng cho Start/Stop/Delete - bọc trong 1
        # container có layout AlignCenter vì setCellWidget() kéo dãn widget
        # theo đúng kích thước ô, còn bản thân QCheckBox (không có text) lại
        # tự căn trái bên trong đó nếu đặt thẳng - phải bọc thêm mới canh
        # giữa được (khớp với checkbox "Check All" ở header, xem _row_checkbox).
        checkbox_container = QtWidgets.QWidget()
        checkbox_layout = QtWidgets.QHBoxLayout(checkbox_container)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        checkbox_layout.addWidget(QtWidgets.QCheckBox())
        self.tableWidget.setCellWidget(row, COL_CHECK, checkbox_container)

        name_item = QTableWidgetItem(device.name)
        name_item.setData(Qt.ItemDataRole.UserRole, device.id)
        self.tableWidget.setItem(row, COL_NAME, name_item)

        ip_text = device.ip_address if device.device_type.value == "IP" else "USB"
        self.tableWidget.setItem(row, COL_IP, QTableWidgetItem(ip_text))
        self.tableWidget.setItem(row, COL_MAC, QTableWidgetItem(device.mac_address or "—"))
        self.tableWidget.setItem(row, COL_SERIAL, QTableWidgetItem(device.serial_no))

        self.tableWidget.setCellWidget(row, COL_STATUS, self._build_status_badge(device))
        self.tableWidget.setCellWidget(row, COL_OPERATION, self._build_operation_widget(device))

    @staticmethod
    def _build_status_badge(device: CameraDevice) -> QtWidgets.QWidget:
        text = (
            tr("{status} · Running").format(status=tr(device.status.value))
            if device.is_running
            else tr(device.status.value)
        )
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        badge = QtWidgets.QLabel(text)
        badge.setProperty("cardRole", "statusBadge")
        badge.setProperty("statusKind", _STATUS_KIND.get(device.status, "unknown"))
        layout.addWidget(badge)
        return container

    def _build_operation_widget(self, device: CameraDevice) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        btn_config = QtWidgets.QToolButton()
        btn_config.setText("⚙")
        btn_config.setToolTip(tr("Configure camera"))
        # cardRole="tableActionBtn": QSS thu gọn riêng cho nút trong bảng
        # (ui/themes/theme_*.qss) - rule QToolButton chung (min-height 26px +
        # padding) làm nút cao hơn dòng bảng (bug đã gặp: "nút Operation to
        # hơn chiều cao của hàng"), cần nhỏ gọn hơn ở đây.
        btn_config.setProperty("cardRole", "tableActionBtn")
        btn_config.clicked.connect(lambda: self.open_camera_config.emit(device.id))
        layout.addWidget(btn_config)

        if device.is_running:
            btn_toggle = QtWidgets.QToolButton()
            btn_toggle.setText("■")
            btn_toggle.setToolTip(tr("Stop"))
            btn_toggle.clicked.connect(lambda: self.device_manager.stop_device(device.id))
        else:
            btn_toggle = QtWidgets.QToolButton()
            btn_toggle.setText("▶")
            btn_toggle.setToolTip(tr("Start"))
            btn_toggle.clicked.connect(lambda: self.device_manager.start_device(device.id))
        btn_toggle.setProperty("cardRole", "tableActionBtn")
        layout.addWidget(btn_toggle)

        return container

    # ------------------------------------------------------------------ #
    # Helpers lấy dòng đang chọn (checkbox HOẶC dòng đang bôi đen)
    # ------------------------------------------------------------------ #
    def _checked_device_ids(self) -> list[str]:
        ids = []
        for row in range(self.tableWidget.rowCount()):
            checkbox = self._row_checkbox(row)
            if checkbox is not None and checkbox.isChecked():
                ids.append(self.tableWidget.item(row, COL_NAME).data(Qt.ItemDataRole.UserRole))
        if ids:
            return ids

        # Không tick checkbox nào -> dùng dòng đang được chọn (bôi đen) làm fallback
        selected_rows = {index.row() for index in self.tableWidget.selectedIndexes()}
        return [
            self.tableWidget.item(row, COL_NAME).data(Qt.ItemDataRole.UserRole)
            for row in selected_rows
        ]

    # ------------------------------------------------------------------ #
    # Slot xử lý nút bấm
    # ------------------------------------------------------------------ #
    def _on_add_device(self) -> None:
        dialog = AddDeviceDialog(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.device_manager.add_device(dialog.get_device())

    def _on_find_online_devices(self) -> None:
        if self._discovery_worker is not None and self._discovery_worker.isRunning():
            return

        self.btn_find_online_devices.setEnabled(False)
        self.btn_find_online_devices.setText(tr("Scanning..."))

        self._discovery_worker = DeviceDiscoveryWorker(scan_usb=True, scan_network=True)
        self._discovery_worker.finished_scan.connect(self._on_discovery_finished)
        self._discovery_worker.start()

    def _on_discovery_finished(self, found: list[CameraDevice]) -> None:
        self.device_manager.merge_discovered_devices(found)
        self.btn_find_online_devices.setEnabled(True)
        self.btn_find_online_devices.setText(tr("🔍 Online Device"))
        QMessageBox.information(self, tr("Camera Scan"), tr("Found {n} camera(s).").format(n=len(found)))

    def _on_delete_device(self) -> None:
        ids = self._checked_device_ids()
        if not ids:
            QMessageBox.warning(self, tr("Delete Camera"), tr("Please select at least 1 camera."))
            return

        confirm = QMessageBox.question(
            self,
            tr("Confirm Delete"),
            tr("Delete {n} selected camera(s)?").format(n=len(ids)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.device_manager.remove_devices(ids)

    def _on_start_device(self) -> None:
        ids = self._checked_device_ids()
        if not ids:
            QMessageBox.warning(self, tr("Start camera"), tr("Please select at least 1 camera."))
            return
        self.device_manager.start_devices(ids)

    def _on_stop_device(self) -> None:
        ids = self._checked_device_ids()
        if not ids:
            QMessageBox.warning(self, tr("Stop camera"), tr("Please select at least 1 camera."))
            return
        self.device_manager.stop_devices(ids)

    def _on_filter_changed(self, _text: str) -> None:
        self.reload_table()