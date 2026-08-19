"""Bảng dịch VI/EN/JA - key là chuỗi tiếng Anh gốc đang hard-code trong
.ui/.py (xem ui/ui_menu/i18n/manager.py::tr). Tổ chức theo từng
trang/dialog để dễ đối chiếu khi 1 trang nào đó đổi text - KHÔNG có key
nào dùng chung giữa 2 trang khác nhau dù trùng chữ (tránh 1 bản dịch chung
vô tình sai ngữ cảnh cho trang kia); nếu 2 nơi thực sự cùng nghĩa/cùng
ngữ cảnh thì trùng key cũng không sao (dict tự dedupe).

Chuỗi có phần ĐỘNG (số/tên...) dùng placeholder kiểu {name} - nơi gọi
tr() phải .format(...) lại sau, xem ví dụ trong từng page.py."""
from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ #
    # menu_window.ui / menu_window.py - shell (top-bar + sidebar), luôn
    # hiển thị bất kể đang ở trang nào.
    # ------------------------------------------------------------------ #
    "Multi AI Camera Management System": {
        "vi": "Hệ Thống Quản Lý Camera AI Đa Luồng",
        "en": "Multi AI Camera Management System",
        "ja": "マルチAIカメラ管理システム",
    },
    "⬡ MULTI AI CAMERA SYSTEM": {
        "vi": "⬡ HỆ THỐNG CAMERA AI ĐA LUỒNG",
        "en": "⬡ MULTI AI CAMERA SYSTEM",
        "ja": "⬡ マルチAIカメラシステム",
    },
    "● SYSTEM ONLINE": {
        "vi": "● HỆ THỐNG HOẠT ĐỘNG",
        "en": "● SYSTEM ONLINE",
        "ja": "● システム稼働中",
    },
    "GPU: {value}%": {
        "vi": "GPU: {value}%",
        "en": "GPU: {value}%",
        "ja": "GPU: {value}%",
    },
    "CPU: {value}%": {
        "vi": "CPU: {value}%",
        "en": "CPU: {value}%",
        "ja": "CPU: {value}%",
    },
    "RAM: {value} GB": {
        "vi": "RAM: {value} GB",
        "en": "RAM: {value} GB",
        "ja": "RAM: {value} GB",
    },
    "GPU: N/A": {
        "vi": "GPU: Không có",
        "en": "GPU: N/A",
        "ja": "GPU: なし",
    },
    "Account": {
        "vi": "Tài khoản",
        "en": "Account",
        "ja": "アカウント",
    },
    "Change Language": {
        "vi": "Đổi ngôn ngữ",
        "en": "Change Language",
        "ja": "言語を変更",
    },
    "Toggle Dark / Light Mode": {
        "vi": "Chuyển chế độ Sáng / Tối",
        "en": "Toggle Dark / Light Mode",
        "ja": "ダーク/ライトモード切替",
    },
    "🚪 Logout": {
        "vi": "🚪 Đăng xuất",
        "en": "🚪 Logout",
        "ja": "🚪 ログアウト",
    },
    "MAIN": {
        "vi": "TRANG CHÍNH",
        "en": "MAIN",
        "ja": "メイン",
    },
    "⊞  Dashboard": {
        "vi": "⊞  Tổng quan",
        "en": "⊞  Dashboard",
        "ja": "⊞  ダッシュボード",
    },
    "◉  Live View": {
        "vi": "◉  Xem trực tiếp",
        "en": "◉  Live View",
        "ja": "◉  ライブビュー",
    },
    "⌬  Device Management": {
        "vi": "⌬  Quản lý thiết bị",
        "en": "⌬  Device Management",
        "ja": "⌬  デバイス管理",
    },
    "⚙  Camera Config": {
        "vi": "⚙  Cấu hình camera",
        "en": "⚙  Camera Config",
        "ja": "⚙  カメラ設定",
    },
    "🎚️  AI Setting": {
        "vi": "🎚️  Cài đặt AI",
        "en": "🎚️  AI Setting",
        "ja": "🎚️  AI設定",
    },
    "LOG": {
        "vi": "NHẬT KÝ",
        "en": "LOG",
        "ja": "ログ",
    },
    "≡  Event Log": {
        "vi": "≡  Nhật ký sự kiện",
        "en": "≡  Event Log",
        "ja": "≡  イベントログ",
    },
    "ATTENDANCE": {
        "vi": "CHẤM CÔNG",
        "en": "ATTENDANCE",
        "ja": "勤怠管理",
    },
    "🪪  Face App": {
        "vi": "🪪  Ứng dụng khuôn mặt",
        "en": "🪪  Face App",
        "ja": "🪪  顔認証アプリ",
    },
    "🟢  Check In": {
        "vi": "🟢  Chấm công vào",
        "en": "🟢  Check In",
        "ja": "🟢  出勤",
    },
    "🔴  Check Out": {
        "vi": "🔴  Chấm công ra",
        "en": "🔴  Check Out",
        "ja": "🔴  退勤",
    },
    "  ⚙  Settings": {
        "vi": "  ⚙  Cài đặt",
        "en": "  ⚙  Settings",
        "ja": "  ⚙  設定",
    },

    # ------------------------------------------------------------------ #
    # login.ui / login.py
    # ------------------------------------------------------------------ #
    "Welcome": {
        "vi": "Chào mừng",
        "en": "Welcome",
        "ja": "ようこそ",
    },
    "User Name": {
        "vi": "Tên đăng nhập",
        "en": "User Name",
        "ja": "ユーザー名",
    },
    "Password": {
        "vi": "Mật khẩu",
        "en": "Password",
        "ja": "パスワード",
    },
    "Login": {
        "vi": "Đăng nhập",
        "en": "Login",
        "ja": "ログイン",
    },
    "Missing Information": {
        "vi": "Thiếu thông tin",
        "en": "Missing Information",
        "ja": "情報が不足しています",
    },
    "Please enter both your account and password.": {
        "vi": "Vui lòng nhập đầy đủ tài khoản và mật khẩu.",
        "en": "Please enter both your account and password.",
        "ja": "アカウントとパスワードを両方入力してください。",
    },
    "Login Failed": {
        "vi": "Đăng nhập thất bại",
        "en": "Login Failed",
        "ja": "ログインに失敗しました",
    },
    "Incorrect account or password!\nPlease check your connection or credentials.": {
        "vi": "Sai tài khoản hoặc mật khẩu!\nKiểm tra lại kết nối hoặc thông tin.",
        "en": "Incorrect account or password!\nPlease check your connection or credentials.",
        "ja": "アカウントまたはパスワードが正しくありません！\n接続状況または入力内容をご確認ください。",
    },

    # ------------------------------------------------------------------ #
    # dashboard_page.ui / dashboard_page.py
    # ------------------------------------------------------------------ #
    "Total Cameras": {"vi": "Tổng số camera", "en": "Total Cameras", "ja": "カメラ総数"},
    "Online": {"vi": "Trực tuyến", "en": "Online", "ja": "オンライン"},
    "Offline": {"vi": "Ngoại tuyến", "en": "Offline", "ja": "オフライン"},
    "Error": {"vi": "Lỗi", "en": "Error", "ja": "エラー"},
    "Unknown": {"vi": "Không rõ", "en": "Unknown", "ja": "不明"},
    "AI Active": {"vi": "AI đang chạy", "en": "AI Active", "ja": "AI稼働中"},
    "Streams": {"vi": "Luồng hình", "en": "Streams", "ja": "ストリーム"},
    "Recording": {"vi": "Đang ghi hình", "en": "Recording", "ja": "録画"},
    "Alarms": {"vi": "Cảnh báo", "en": "Alarms", "ja": "アラーム"},
    "GPU": {"vi": "GPU", "en": "GPU", "ja": "GPU"},
    "CPU": {"vi": "CPU", "en": "CPU", "ja": "CPU"},
    "RAM": {"vi": "RAM", "en": "RAM", "ja": "RAM"},
    "Network": {"vi": "Mạng", "en": "Network", "ja": "ネットワーク"},
    "Camera Health": {"vi": "Tình trạng camera", "en": "Camera Health", "ja": "カメラ状態"},
    "AI Engine": {"vi": "Engine AI", "en": "AI Engine", "ja": "AIエンジン"},
    "Event Feed": {"vi": "Dòng sự kiện", "en": "Event Feed", "ja": "イベントフィード"},
    "All →": {"vi": "Tất cả →", "en": "All →", "ja": "すべて →"},
    "Clear": {"vi": "Xoá", "en": "Clear", "ja": "クリア"},
    "System": {"vi": "Hệ thống", "en": "System", "ja": "システム"},
    "VRAM": {"vi": "VRAM", "en": "VRAM", "ja": "VRAM"},
    "Disk": {"vi": "Ổ đĩa", "en": "Disk", "ja": "ディスク"},
    "Temp": {"vi": "Nhiệt độ", "en": "Temp", "ja": "温度"},
    "Net": {"vi": "Mạng", "en": "Net", "ja": "ネット"},
    "Storage": {"vi": "Lưu trữ", "en": "Storage", "ja": "ストレージ"},
    "Used": {"vi": "Đã dùng", "en": "Used", "ja": "使用済み"},
    "Total": {"vi": "Tổng", "en": "Total", "ja": "合計"},
    "Free": {"vi": "Còn trống", "en": "Free", "ja": "空き容量"},
    "Est. Days": {"vi": "Số ngày ước tính", "en": "Est. Days", "ja": "推定日数"},
    "Refresh all dashboard data": {
        "vi": "Làm mới toàn bộ dữ liệu dashboard",
        "en": "Refresh all dashboard data",
        "ja": "ダッシュボードのデータを更新",
    },
    "Restart all camera streams": {
        "vi": "Khởi động lại tất cả luồng camera",
        "en": "Restart all camera streams",
        "ja": "すべてのカメラストリームを再起動",
    },
    "Stop all AI pipelines immediately": {
        "vi": "Dừng ngay toàn bộ pipeline AI",
        "en": "Stop all AI pipelines immediately",
        "ja": "すべてのAIパイプラインを即時停止",
    },
    "↻  Refresh": {"vi": "↻  Làm mới", "en": "↻  Refresh", "ja": "↻  更新"},
    "⟳  Restart Cameras": {"vi": "⟳  Khởi động lại camera", "en": "⟳  Restart Cameras", "ja": "⟳  カメラ再起動"},
    "⛔  Emergency Stop": {"vi": "⛔  Dừng khẩn cấp", "en": "⛔  Emergency Stop", "ja": "⛔  緊急停止"},
    "Camera": {"vi": "Camera", "en": "Camera", "ja": "カメラ"},
    "Status": {"vi": "Trạng thái", "en": "Status", "ja": "ステータス"},
    "Stream": {"vi": "Luồng", "en": "Stream", "ja": "ストリーム"},
    "AI": {"vi": "AI", "en": "AI", "ja": "AI"},
    "REC": {"vi": "GHI", "en": "REC", "ja": "REC"},
    "FPS": {"vi": "FPS", "en": "FPS", "ja": "FPS"},
    "Heartbeat": {"vi": "Nhịp tín hiệu", "en": "Heartbeat", "ja": "ハートビート"},
    "Model": {"vi": "Mô hình", "en": "Model", "ja": "モデル"},
    "Active Cameras": {"vi": "Camera đang dùng", "en": "Active Cameras", "ja": "使用中のカメラ"},
    "GPU %": {"vi": "GPU %", "en": "GPU %", "ja": "GPU使用率"},
    "Last ms": {"vi": "Thời gian gần nhất (ms)", "en": "Last ms", "ja": "直近の処理時間(ms)"},
    "All Events": {"vi": "Tất cả sự kiện", "en": "All Events", "ja": "すべてのイベント"},
    "AI Events": {"vi": "Sự kiện AI", "en": "AI Events", "ja": "AIイベント"},
    "Human Detection": {"vi": "Phát hiện người", "en": "Human Detection", "ja": "人物検知"},
    "Body / Pose (Fall)": {"vi": "Dáng người / Té ngã", "en": "Body / Pose (Fall)", "ja": "姿勢推定（転倒検知）"},
    "PPE Detection": {"vi": "Phát hiện đồ bảo hộ", "en": "PPE Detection", "ja": "PPE検知"},
    "Fire Detection": {"vi": "Phát hiện cháy", "en": "Fire Detection", "ja": "火災検知"},
    "Fall Detection": {"vi": "Phát hiện té ngã", "en": "Fall Detection", "ja": "転倒検知"},
    "Face Recognition": {"vi": "Nhận diện khuôn mặt", "en": "Face Recognition", "ja": "顔認識"},
    "No alarms": {"vi": "Không có cảnh báo", "en": "No alarms", "ja": "アラームなし"},
    "🔴 Active alarm": {"vi": "🔴 Đang có cảnh báo", "en": "🔴 Active alarm", "ja": "🔴 アラーム発生中"},
    "{name}: → {status}": {"vi": "{name}: → {status}", "en": "{name}: → {status}", "ja": "{name}: → {status}"},
    "Started": {"vi": "Đã khởi động", "en": "Started", "ja": "開始"},
    "Stopped": {"vi": "Đã dừng", "en": "Stopped", "ja": "停止"},
    "{name}: {state}": {"vi": "{name}: {state}", "en": "{name}: {state}", "ja": "{name}: {state}"},
    "{name}: New camera added": {
        "vi": "{name}: Đã thêm camera mới",
        "en": "{name}: New camera added",
        "ja": "{name}: 新しいカメラが追加されました",
    },
    "{device_id}: Camera removed": {
        "vi": "{device_id}: Đã xoá camera",
        "en": "{device_id}: Camera removed",
        "ja": "{device_id}: カメラが削除されました",
    },
    "{name}: {label}": {"vi": "{name}: {label}", "en": "{name}: {label}", "ja": "{name}: {label}"},
    "{name}: Recognized {known_name}": {
        "vi": "{name}: Nhận diện {known_name}",
        "en": "{name}: Recognized {known_name}",
        "ja": "{name}: {known_name}を認識しました",
    },
    "Events Today: {count}": {
        "vi": "Sự kiện hôm nay: {count}",
        "en": "Events Today: {count}",
        "ja": "本日のイベント数: {count}",
    },
    "{ip} IP · {usb} USB": {"vi": "{ip} IP · {usb} USB", "en": "{ip} IP · {usb} USB", "ja": "{ip} IP・{usb} USB"},
    "{n} offline": {"vi": "{n} ngoại tuyến", "en": "{n} offline", "ja": "{n} 台オフライン"},
    "of {n} running": {"vi": "trong {n} đang chạy", "en": "of {n} running", "ja": "実行中 {n} 台中"},
    "cameras streaming": {"vi": "camera đang phát hình", "en": "cameras streaming", "ja": "台がストリーミング中"},
    "{n} cameras configured to record": {
        "vi": "{n} camera đã cấu hình ghi hình",
        "en": "{n} cameras configured to record",
        "ja": "{n} 台が録画設定済み",
    },
    "None": {"vi": "Không có", "en": "None", "ja": "なし"},
    "AI Engine: {state}": {"vi": "AI Engine: {state}", "en": "AI Engine: {state}", "ja": "AIエンジン: {state}"},
    "Running": {"vi": "Đang chạy", "en": "Running", "ja": "実行中"},
    "Idle": {"vi": "Đang chờ", "en": "Idle", "ja": "待機中"},
    "● {state}": {"vi": "● {state}", "en": "● {state}", "ja": "● {state}"},
    "Threads: {n}": {"vi": "Luồng xử lý: {n}", "en": "Threads: {n}", "ja": "スレッド数: {n}"},
    "Streams: {n}": {"vi": "Luồng hình: {n}", "en": "Streams: {n}", "ja": "ストリーム数: {n}"},
    "ON": {"vi": "BẬT", "en": "ON", "ja": "ON"},
    "OFF": {"vi": "TẮT", "en": "OFF", "ja": "OFF"},
    "just now": {"vi": "vừa xong", "en": "just now", "ja": "たった今"},
    "{n}s ago": {"vi": "{n} giây trước", "en": "{n}s ago", "ja": "{n}秒前"},
    "{n}m ago": {"vi": "{n} phút trước", "en": "{n}m ago", "ja": "{n}分前"},
    "Loaded": {"vi": "Đã tải", "en": "Loaded", "ja": "読込済み"},
    "Not loaded": {"vi": "Chưa tải", "en": "Not loaded", "ja": "未読込"},
    "High": {"vi": "Cao", "en": "High", "ja": "高い"},
    "Normal": {"vi": "Bình thường", "en": "Normal", "ja": "通常"},
    "No GPU": {"vi": "Không có GPU", "en": "No GPU", "ja": "GPUなし"},
    "N/A": {"vi": "Không có", "en": "N/A", "ja": "該当なし"},
    "{n} cameras recording": {
        "vi": "{n} camera đang ghi hình",
        "en": "{n} cameras recording",
        "ja": "{n} 台が録画中",
    },
    "No cameras recording": {
        "vi": "Không có camera nào đang ghi hình",
        "en": "No cameras recording",
        "ja": "録画中のカメラはありません",
    },
    "No cameras are currently running.": {
        "vi": "Không có camera nào đang chạy.",
        "en": "No cameras are currently running.",
        "ja": "現在実行中のカメラはありません。",
    },
    "Restart Cameras": {"vi": "Khởi động lại camera", "en": "Restart Cameras", "ja": "カメラを再起動"},
    "Restart {n} running camera(s)?": {
        "vi": "Khởi động lại {n} camera đang chạy?",
        "en": "Restart {n} running camera(s)?",
        "ja": "実行中の{n}台のカメラを再起動しますか？",
    },
    "Emergency Stop": {"vi": "Dừng khẩn cấp", "en": "Emergency Stop", "ja": "緊急停止"},
    "No cameras currently have AI enabled.": {
        "vi": "Không có camera nào đang bật AI.",
        "en": "No cameras currently have AI enabled.",
        "ja": "AIが有効なカメラはありません。",
    },
    "Emergency Stop AI": {"vi": "Dừng khẩn cấp AI", "en": "Emergency Stop AI", "ja": "AI緊急停止"},
    "Turn off AI on {n} running camera(s)?\n(Cameras will keep streaming, only AI processing stops - cameras won't stop entirely.)": {
        "vi": "Tắt AI trên {n} camera đang chạy?\n(Camera vẫn tiếp tục phát hình, chỉ tắt xử lý AI - không dừng hẳn camera.)",
        "en": "Turn off AI on {n} running camera(s)?\n(Cameras will keep streaming, only AI processing stops - cameras won't stop entirely.)",
        "ja": "実行中の{n}台のカメラでAIをオフにしますか？\n（カメラの映像配信は継続し、AI処理のみ停止します。カメラ自体は停止しません。）",
    },

    # ------------------------------------------------------------------ #
    # Nhãn cảnh báo AI - dùng chung bởi dashboard_page.py, liveview_page.py,
    # camera_card.py (badge trên card) - cùng 1 nghĩa, cố tình dùng chung key.
    # ------------------------------------------------------------------ #
    "⚠ PPE violation": {"vi": "⚠ Vi phạm PPE", "en": "⚠ PPE violation", "ja": "⚠ PPE違反"},
    "🔥 Fire": {"vi": "🔥 Cháy", "en": "🔥 Fire", "ja": "🔥 火災"},
    "🚨 Fall": {"vi": "🚨 Té ngã", "en": "🚨 Fall", "ja": "🚨 転倒"},
    "🧑‍❓ Stranger": {"vi": "🧑‍❓ Người lạ", "en": "🧑‍❓ Stranger", "ja": "🧑‍❓ 不審者"},
    "⚠ PPE": {"vi": "⚠ PPE", "en": "⚠ PPE", "ja": "⚠ PPE"},
    "Online: {online} / {total}": {
        "vi": "Trực tuyến: {online} / {total}",
        "en": "Online: {online} / {total}",
        "ja": "オンライン: {online} / {total}",
    },

    # ------------------------------------------------------------------ #
    # liveview_page.ui / liveview_page.py
    # ------------------------------------------------------------------ #
    "Live View": {"vi": "Xem trực tiếp", "en": "Live View", "ja": "ライブビュー"},
    "1 column × 1 row  (view 1 camera)": {
        "vi": "1 cột × 1 hàng  (xem 1 camera)",
        "en": "1 column × 1 row  (view 1 camera)",
        "ja": "1列×1行（カメラ1台を表示）",
    },
    "2 columns × 3 rows  (6 cameras)": {
        "vi": "2 cột × 3 hàng  (6 camera)",
        "en": "2 columns × 3 rows  (6 cameras)",
        "ja": "2列×3行（カメラ6台）",
    },
    "2 columns × 4 rows  (8 cameras)": {
        "vi": "2 cột × 4 hàng  (8 camera)",
        "en": "2 columns × 4 rows  (8 cameras)",
        "ja": "2列×4行（カメラ8台）",
    },
    "4 columns × 4 rows  (16 cameras)": {
        "vi": "4 cột × 4 hàng  (16 camera)",
        "en": "4 columns × 4 rows  (16 cameras)",
        "ja": "4列×4行（カメラ16台）",
    },
    "DISPLAY CAMERAS": {"vi": "HIỂN THỊ CAMERA", "en": "DISPLAY CAMERAS", "ja": "表示するカメラ"},
    "REAL-TIME DETECTION": {"vi": "PHÁT HIỆN THỜI GIAN THỰC", "en": "REAL-TIME DETECTION", "ja": "リアルタイム検知"},
    "SYSTEM ALARMS": {"vi": "CẢNH BÁO HỆ THỐNG", "en": "SYSTEM ALARMS", "ja": "システムアラーム"},
    "{name}   ·  {status}": {"vi": "{name}   ·  {status}", "en": "{name}   ·  {status}", "ja": "{name}   ·  {status}"},
    "👤 Recognized {name}": {
        "vi": "👤 Nhận diện {name}",
        "en": "👤 Recognized {name}",
        "ja": "👤 {name}を認識",
    },

    # ------------------------------------------------------------------ #
    # device_management_page.ui / device_page.py
    # ------------------------------------------------------------------ #
    "+ Add": {"vi": "+ Thêm", "en": "+ Add", "ja": "+ 追加"},
    "🔍 Online Device": {"vi": "🔍 Quét camera", "en": "🔍 Online Device", "ja": "🔍 オンライン検索"},
    "🗑  Delete": {"vi": "🗑  Xoá", "en": "🗑  Delete", "ja": "🗑  削除"},
    "▶  Start": {"vi": "▶  Chạy", "en": "▶  Start", "ja": "▶  開始"},
    "■  Stop": {"vi": "■  Dừng", "en": "■  Stop", "ja": "■  停止"},
    "filter": {"vi": "lọc", "en": "filter", "ja": "フィルター"},
    "Name": {"vi": "Tên", "en": "Name", "ja": "名前"},
    "IP": {"vi": "IP", "en": "IP", "ja": "IP"},
    "MAC Address": {"vi": "Địa chỉ MAC", "en": "MAC Address", "ja": "MACアドレス"},
    "Serial No.": {"vi": "Số Serial", "en": "Serial No.", "ja": "シリアル番号"},
    "Operation": {"vi": "Thao tác", "en": "Operation", "ja": "操作"},
    "Total({n})": {"vi": "Tổng({n})", "en": "Total({n})", "ja": "合計({n})"},
    "Configure camera": {"vi": "Cấu hình camera", "en": "Configure camera", "ja": "カメラ設定"},
    "Start": {"vi": "Chạy", "en": "Start", "ja": "開始"},
    "Stop": {"vi": "Dừng", "en": "Stop", "ja": "停止"},
    "{status} · Running": {"vi": "{status} · Đang chạy", "en": "{status} · Running", "ja": "{status}・実行中"},
    "Scanning...": {"vi": "Đang quét...", "en": "Scanning...", "ja": "スキャン中..."},
    "Camera Scan": {"vi": "Quét camera", "en": "Camera Scan", "ja": "カメラスキャン"},
    "Found {n} camera(s).": {
        "vi": "Tìm thấy {n} camera.",
        "en": "Found {n} camera(s).",
        "ja": "{n}台のカメラが見つかりました。",
    },
    "Delete Camera": {"vi": "Xoá camera", "en": "Delete Camera", "ja": "カメラを削除"},
    "Please select at least 1 camera.": {
        "vi": "Vui lòng chọn ít nhất 1 camera.",
        "en": "Please select at least 1 camera.",
        "ja": "カメラを1台以上選択してください。",
    },
    "Confirm Delete": {"vi": "Xác nhận xoá", "en": "Confirm Delete", "ja": "削除の確認"},
    "Delete {n} selected camera(s)?": {
        "vi": "Xoá {n} camera đã chọn?",
        "en": "Delete {n} selected camera(s)?",
        "ja": "選択した{n}台のカメラを削除しますか？",
    },
    "Start camera": {"vi": "Chạy camera", "en": "Start camera", "ja": "カメラを開始"},
    "Stop camera": {"vi": "Dừng camera", "en": "Stop camera", "ja": "カメラを停止"},

    # ------------------------------------------------------------------ #
    # camera_config_page.ui / camera_config_page.py
    # ------------------------------------------------------------------ #
    "Search camera…": {"vi": "Tìm camera…", "en": "Search camera…", "ja": "カメラを検索…"},
    "Camera Identity": {"vi": "Thông tin camera", "en": "Camera Identity", "ja": "カメラ情報"},
    "Camera Name": {"vi": "Tên camera", "en": "Camera Name", "ja": "カメラ名"},
    "Camera ID": {"vi": "ID camera", "en": "Camera ID", "ja": "カメラID"},
    "App-generated internal ID used as the lookup key for this camera in DeviceManager - not editable, and NOT the camera_id sent to the web server (see the \"MAC Address\" field below for that).": {
        "vi": "ID nội bộ do app tự sinh, dùng làm khoá tra cứu camera trong DeviceManager - không sửa được, và KHÔNG phải camera_id gửi lên web server (xem field \"MAC Address\" bên dưới cho việc đó).",
        "en": "App-generated internal ID used as the lookup key for this camera in DeviceManager - not editable, and NOT the camera_id sent to the web server (see the \"MAC Address\" field below for that).",
        "ja": "DeviceManager内でこのカメラを識別するためアプリが自動生成した内部ID - 編集不可、Webサーバーに送信されるcamera_idではありません（そちらは下記の「MACアドレス」欄を参照）。",
    },
    "Vendor": {"vi": "Hãng sản xuất", "en": "Vendor", "ja": "メーカー"},
    "Unknown": {"vi": "Không rõ", "en": "Unknown", "ja": "不明"},
    "Other": {"vi": "Khác", "en": "Other", "ja": "その他"},
    "Connection": {"vi": "Kết nối", "en": "Connection", "ja": "接続"},
    "IP Address": {"vi": "Địa chỉ IP", "en": "IP Address", "ja": "IPアドレス"},
    "Stream URL": {"vi": "Đường dẫn Stream", "en": "Stream URL", "ja": "ストリームURL"},
    "Substream URL": {"vi": "Đường dẫn Substream", "en": "Substream URL", "ja": "サブストリームURL"},
    "Low-resolution substream used for AI + live preview instead of the Stream URL - reduces bandwidth/decode CPU, doesn't affect AI accuracy since frames are auto-resized to <=640px anyway. Leave empty to use the Stream URL (mainstream) as before.": {
        "vi": "Luồng phụ (độ phân giải thấp) dùng cho AI + xem trực tiếp thay vì Stream URL - giảm băng thông/CPU decode, không ảnh hưởng độ chính xác AI vì đã tự resize xuống <=640px. Để trống để dùng Stream URL (mainstream) như trước.",
        "en": "Low-resolution substream used for AI + live preview instead of the Stream URL - reduces bandwidth/decode CPU, doesn't affect AI accuracy since frames are auto-resized to <=640px anyway. Leave empty to use the Stream URL (mainstream) as before.",
        "ja": "AI処理とライブプレビューにStream URLの代わりに使う低解像度サブストリーム - 帯域幅/デコードCPUを削減。フレームはどのみち640px以下に自動リサイズされるためAI精度への影響なし。空欄の場合は従来通りStream URL（メインストリーム）を使用。",
    },
    "Uncheck to temporarily fall back to the Stream URL (mainstream) without deleting the saved Substream URL.": {
        "vi": "Bỏ tick để tạm dùng lại Stream URL (mainstream) mà không cần xoá Substream URL đã lưu.",
        "en": "Uncheck to temporarily fall back to the Stream URL (mainstream) without deleting the saved Substream URL.",
        "ja": "チェックを外すと、保存済みのSubstream URLを削除せずに一時的にStream URL（メインストリーム）へ戻します。",
    },
    "Prefer the substream": {"vi": "Ưu tiên dùng substream", "en": "Prefer the substream", "ja": "サブストリームを優先"},
    "MAC Address": {"vi": "Địa chỉ MAC", "en": "MAC Address", "ja": "MACアドレス"},
    "This is the actual camera_id sent to the web server (matches the camera already registered there by MAC, DIFFERENT from the internal \"Camera ID\" above) - auto-filled when scanning ARP (IP camera), or entered manually if scanning isn't possible / USB camera. Leave empty = events/attendance from this camera won't be sent to the web.": {
        "vi": "Đây mới là camera_id thật sự gửi lên web server (khớp với camera đã đăng ký sẵn bên đó theo MAC, KHÁC \"Camera ID\" nội bộ ở trên) - tự điền khi quét ARP (camera IP), hoặc nhập tay nếu không quét được/camera USB. Để trống = không gửi sự kiện/chấm công của camera này lên web.",
        "en": "This is the actual camera_id sent to the web server (matches the camera already registered there by MAC, DIFFERENT from the internal \"Camera ID\" above) - auto-filled when scanning ARP (IP camera), or entered manually if scanning isn't possible / USB camera. Leave empty = events/attendance from this camera won't be sent to the web.",
        "ja": "こちらがWebサーバーに送信される実際のcamera_idです（MACアドレスで既に登録済みのカメラと一致、上記の内部「カメラID」とは別物）- ARPスキャン時に自動入力（IPカメラ）、またはスキャンできない場合/USBカメラは手動入力。空欄の場合はこのカメラのイベント/勤怠情報がWebに送信されません。",
    },
    "Stream Settings": {"vi": "Cài đặt luồng hình", "en": "Stream Settings", "ja": "ストリーム設定"},
    "Resolution": {"vi": "Độ phân giải", "en": "Resolution", "ja": "解像度"},
    "Limits the maximum DISPLAY resolution (does not change the resolution AI uses for detection). If the source camera's resolution is higher than the selected value, it will be downscaled before display to reduce lag - choose 4K = no limit. For USB cameras, this also requests that the camera capture at this exact resolution (requires Stop/Start to take effect); for IP/RTSP, the camera server decides this and it can't be set here.": {
        "vi": "Giới hạn độ phân giải HIỂN THỊ tối đa (không đổi độ phân giải AI dùng để nhận diện). Nếu camera nguồn có độ phân giải cao hơn mức chọn, hình sẽ được downscale trước khi hiển thị để đỡ giật - chọn 4K = không giới hạn. Với camera USB, còn yêu cầu camera capture đúng độ phân giải này (cần Stop/Start lại mới áp dụng); IP/RTSP thì do camera server quyết định, không set được ở đây.",
        "en": "Limits the maximum DISPLAY resolution (does not change the resolution AI uses for detection). If the source camera's resolution is higher than the selected value, it will be downscaled before display to reduce lag - choose 4K = no limit. For USB cameras, this also requests that the camera capture at this exact resolution (requires Stop/Start to take effect); for IP/RTSP, the camera server decides this and it can't be set here.",
        "ja": "表示の最大解像度を制限します（AI検知に使う解像度は変わりません）。元のカメラの解像度が選択値より高い場合、表示前にダウンスケールして遅延を軽減します - 4Kを選ぶと無制限。USBカメラの場合、この解像度でキャプチャするよう要求します（反映にはStop/Startが必要）。IP/RTSPの場合はカメラサーバー側が決定するためここでは設定できません。",
    },
    "FPS": {"vi": "FPS", "en": "FPS", "ja": "FPS"},
    "Limits the DISPLAY frame rate (frames per second sent for viewing) - does not limit the AI processing rate (see \"AI FPS Limit\" in the AI tab). Takes effect immediately, no need to Stop/Start.": {
        "vi": "Giới hạn tốc độ HIỂN THỊ (số khung hình/giây gửi lên xem) - không giới hạn tốc độ AI xử lý (xem \"AI FPS Limit\" ở tab AI). Có hiệu lực ngay, không cần Stop/Start lại.",
        "en": "Limits the DISPLAY frame rate (frames per second sent for viewing) - does not limit the AI processing rate (see \"AI FPS Limit\" in the AI tab). Takes effect immediately, no need to Stop/Start.",
        "ja": "表示のフレームレート（表示用に送信するフレーム数/秒）を制限します - AI処理速度は制限しません（AIタブの「AI FPS Limit」参照）。即座に反映され、Stop/Startは不要です。",
    },
    "Camera Preview": {"vi": "Xem trước camera", "en": "Camera Preview", "ja": "カメラプレビュー"},
    "▶  Open Preview": {"vi": "▶  Mở xem trước", "en": "▶  Open Preview", "ja": "▶  プレビューを開く"},
    "■  Close Preview": {"vi": "■  Đóng xem trước", "en": "■  Close Preview", "ja": "■  プレビューを閉じる"},
    "No Preview": {"vi": "Không có hình xem trước", "en": "No Preview", "ja": "プレビューなし"},
    "Connecting...": {"vi": "Đang kết nối...", "en": "Connecting...", "ja": "接続中..."},
    "Test Connection": {"vi": "Kiểm tra kết nối", "en": "Test Connection", "ja": "接続テスト"},
    "Please enter an IP Address first.": {
        "vi": "Vui lòng nhập địa chỉ IP trước.",
        "en": "Please enter an IP Address first.",
        "ja": "先にIPアドレスを入力してください。",
    },
    "Successfully connected to {ip}.": {
        "vi": "Kết nối tới {ip} thành công.",
        "en": "Successfully connected to {ip}.",
        "ja": "{ip}への接続に成功しました。",
    },
    "Could not connect to {ip}.": {
        "vi": "Không thể kết nối tới {ip}.",
        "en": "Could not connect to {ip}.",
        "ja": "{ip}に接続できませんでした。",
    },
    "AI Processing": {"vi": "Xử lý AI", "en": "AI Processing", "ja": "AI処理"},
    "Enable AI": {"vi": "Bật AI", "en": "Enable AI", "ja": "AIを有効化"},
    "AI FPS Limit": {"vi": "Giới hạn FPS xử lý AI", "en": "AI FPS Limit", "ja": "AI処理FPS上限"},
    "Detection Quality": {"vi": "Chất lượng nhận diện", "en": "Detection Quality", "ja": "検知品質"},
    "Image size fed into the AI model (pose/PPE/fire/fall) - does not affect the display resolution. Fast/Balanced run much smoother when AI runs on multiple cameras at once, at the cost of slightly lower accuracy for small or distant people/objects.": {
        "vi": "Kích thước ảnh đưa vào model AI (pose/PPE/fire/fall) - không ảnh hưởng độ phân giải hiển thị. Fast/Balanced chạy mượt hơn nhiều khi AI xử lý nhiều camera cùng lúc, đổi lại độ chính xác giảm nhẹ với người/vật nhỏ hoặc ở xa.",
        "en": "Image size fed into the AI model (pose/PPE/fire/fall) - does not affect the display resolution. Fast/Balanced run much smoother when AI runs on multiple cameras at once, at the cost of slightly lower accuracy for small or distant people/objects.",
        "ja": "AIモデル（姿勢/PPE/火災/転倒）に入力する画像サイズ - 表示解像度には影響しません。Fast/Balancedは複数カメラで同時にAIを実行する際により滑らかに動作しますが、小さい/遠い人物・物体の精度がわずかに低下します。",
    },
    "Fast (320px)": {"vi": "Nhanh (320px)", "en": "Fast (320px)", "ja": "高速 (320px)"},
    "Balanced (480px)": {"vi": "Cân bằng (480px)", "en": "Balanced (480px)", "ja": "バランス (480px)"},
    "Accurate (640px)": {"vi": "Chính xác (640px)", "en": "Accurate (640px)", "ja": "高精度 (640px)"},
    "AI Features": {"vi": "Tính năng AI", "en": "AI Features", "ja": "AI機能"},
    "Count people in/out  (requires drawing a Counting Line)": {
        "vi": "Đếm người vào/ra  (cần vẽ Counting Line)",
        "en": "Count people in/out  (requires drawing a Counting Line)",
        "ja": "入退室カウント（Counting Lineの作成が必要）",
    },
    "Monitor current occupancy  (ROI recommended)": {
        "vi": "Giám sát số người hiện tại  (nên có ROI)",
        "en": "Monitor current occupancy  (ROI recommended)",
        "ja": "現在の在室人数を監視（ROI推奨）",
    },
    "Alert if occupancy exceeds": {
        "vi": "Cảnh báo nếu số người vượt quá",
        "en": "Alert if occupancy exceeds",
        "ja": "在室人数がこれを超えたら警告",
    },
    "0 = no alert (unlimited). When the number of people currently in view goes above this number, an "
    "alert is raised (SYSTEM ALARMS + Event Log) - it will not repeat while the count stays above the "
    "threshold continuously, only again after it drops back down and exceeds it again.": {
        "vi": "0 = không cảnh báo (không giới hạn). Khi số người hiện có trong khung hình vượt quá số này, "
        "hệ thống sẽ tạo cảnh báo (SYSTEM ALARMS + Event Log) - không lặp lại liên tục khi vẫn còn vượt "
        "ngưỡng, chỉ báo lại khi tụt xuống dưới ngưỡng rồi vượt lại lần nữa.",
        "en": "0 = no alert (unlimited). When the number of people currently in view goes above this number, an "
        "alert is raised (SYSTEM ALARMS + Event Log) - it will not repeat while the count stays above the "
        "threshold continuously, only again after it drops back down and exceeds it again.",
        "ja": "0 = 警告なし（無制限）。現在画面内の人数がこの数を超えると警告が発生します（SYSTEM ALARMS + "
        "Event Log）- 閾値を超え続けている間は繰り返さず、一度下回ってから再度超えた時のみ再通知します。",
    },
    "Off": {"vi": "Tắt", "en": "Off", "ja": "オフ"},
    "👥 OVER LIMIT": {"vi": "👥 VƯỢT NGƯỠNG", "en": "👥 OVER LIMIT", "ja": "👥 上限超過"},
    "👥 Overcrowding": {"vi": "👥 Quá đông người", "en": "👥 Overcrowding", "ja": "👥 過密"},
    "Overcrowding": {"vi": "Quá đông người", "en": "Overcrowding", "ja": "過密"},
    "Recognized": {"vi": "Nhận diện", "en": "Recognized", "ja": "認識"},
    "Alert on localized crowd density": {
        "vi": "Cảnh báo đám đông cục bộ",
        "en": "Alert on localized crowd density",
        "ja": "局所的な混雑を警告",
    },
    "0 = off. Unlike \"Alert if occupancy exceeds\" (total headcount), this tracks LOCALIZED density - "
    "people clustering in the same small area of the ROI, even if the total count is still under the "
    "occupancy limit. Builds up the longer people linger in one spot, cools down a few seconds after "
    "they leave. When set above 0, a heatmap overlay is also shown on the live view.": {
        "vi": "0 = tắt. Khác với \"Cảnh báo nếu số người vượt quá\" (đếm tổng), cái này theo dõi mật độ "
        "CỤC BỘ - người tụ tập cùng 1 vùng nhỏ trong ROI, dù tổng số người vẫn dưới ngưỡng occupancy. "
        "Tăng dần khi người đứng lâu 1 chỗ, giảm dần vài giây sau khi họ rời đi. Khi đặt lớn hơn 0, còn "
        "hiện thêm lớp phủ heatmap trên Live View.",
        "en": "0 = off. Unlike \"Alert if occupancy exceeds\" (total headcount), this tracks LOCALIZED "
        "density - people clustering in the same small area of the ROI, even if the total count is still "
        "under the occupancy limit. Builds up the longer people linger in one spot, cools down a few "
        "seconds after they leave. When set above 0, a heatmap overlay is also shown on the live view.",
        "ja": "0 = オフ。「在室人数がこれを超えたら警告」（総人数）とは異なり、これはROI内の同じ小さな範囲"
        "に人が集まる「局所的な」密度を追跡します（総人数が在室人数の上限を下回っていても対象）。1箇所に"
        "長くとどまるほど蓄積し、離れてから数秒で冷めます。0より大きい値を設定すると、ライブビューにヒー"
        "トマップのオーバーレイも表示されます。",
    },
    "Crowd Density": {"vi": "Mật độ đông cục bộ", "en": "Crowd Density", "ja": "局所的な混雑"},
    "🌡️ Crowd Density": {"vi": "🌡️ Mật độ đông cục bộ", "en": "🌡️ Crowd Density", "ja": "🌡️ 局所的な混雑"},
    "PPE monitoring  (requires drawing an ROI)": {
        "vi": "Giám sát đồ bảo hộ PPE  (cần vẽ ROI)",
        "en": "PPE monitoring  (requires drawing an ROI)",
        "ja": "PPE監視（ROIの作成が必要）",
    },
    "Fire Detection": {"vi": "Phát hiện cháy", "en": "Fire Detection", "ja": "火災検知"},
    "Fall Detection": {"vi": "Phát hiện té ngã", "en": "Fall Detection", "ja": "転倒検知"},
    "Face recognition - alert on strangers / recognize known people": {
        "vi": "Nhận diện khuôn mặt - cảnh báo người lạ / nhận diện người quen",
        "en": "Face recognition - alert on strangers / recognize known people",
        "ja": "顔認識 - 不審者を警告 / 既知の人物を認識",
    },
    "Repeat notifications": {
        "vi": "Lặp lại thông báo",
        "en": "Repeat notifications",
        "ja": "通知の再送",
    },
    "Notify once per visit": {
        "vi": "Chỉ báo 1 lần mỗi lượt xuất hiện",
        "en": "Notify once per visit",
        "ja": "来訪ごとに1回だけ通知",
    },
    "Repeat after grace period": {
        "vi": "Báo lại sau thời gian chờ",
        "en": "Repeat after grace period",
        "ja": "猶予期間後に再通知",
    },
    "How to handle the SAME person (known or stranger) being seen again after briefly turning away/being "
    "partly hidden. \"Notify once\" only alerts/logs the first time until they leave the frame entirely. "
    "\"Repeat after grace period\" alerts/logs again if they go quiet for a while and get reconfirmed - "
    "same behavior as PPE/Fire/Fall/Overcrowding.": {
        "vi": "Cách xử lý khi vẫn ĐÚNG 1 người (quen hoặc lạ) bị nhìn thấy lại sau khi vừa quay đầu/bị che "
        "khuất một phần. \"Chỉ báo 1 lần\" chỉ cảnh báo/ghi log lần đầu tiên, tới khi họ ra khỏi khung hình "
        "hẳn. \"Báo lại sau thời gian chờ\" cảnh báo/ghi log lại nếu họ \"im lặng\" một lúc rồi được xác "
        "nhận lại - giống hành vi PPE/Fire/Fall/Overcrowding.",
        "en": "How to handle the SAME person (known or stranger) being seen again after briefly turning "
        "away/being partly hidden. \"Notify once\" only alerts/logs the first time until they leave the "
        "frame entirely. \"Repeat after grace period\" alerts/logs again if they go quiet for a while and "
        "get reconfirmed - same behavior as PPE/Fire/Fall/Overcrowding.",
        "ja": "同じ人物（既知または不審者）が、少し目を離した/一部隠れた後に再び見られた場合の扱い方。「1回"
        "だけ通知」は画面から完全に消えるまで最初の1回だけ警告/記録します。「猶予期間後に再通知」は、しばら"
        "く静かになって再確認された場合に再度警告/記録します - PPE/Fire/Fall/Overcrowdingと同じ挙動です。",
    },
    "Face match sensitivity": {
        "vi": "Độ nhạy nhận diện khuôn mặt",
        "en": "Face match sensitivity",
        "ja": "顔認識の感度",
    },
    "How closely a detected face must match a known person to be recognized. Higher = stricter (fewer "
    "false matches, but may miss known people at bad angles/lighting). Lower = looser (recognizes known "
    "people more easily, but raises the risk of confusing 2 similar-looking people).": {
        "vi": "Mức độ tương đồng tối thiểu để coi 1 khuôn mặt phát hiện được là khớp với người quen. Cao "
        "hơn = chặt hơn (ít nhận nhầm 2 người giống nhau, nhưng dễ bỏ sót người quen ở góc/ánh sáng xấu). "
        "Thấp hơn = lỏng hơn (nhận ra người quen dễ hơn, nhưng dễ nhầm giữa 2 người trông giống nhau hơn).",
        "en": "How closely a detected face must match a known person to be recognized. Higher = stricter "
        "(fewer false matches, but may miss known people at bad angles/lighting). Lower = looser "
        "(recognizes known people more easily, but raises the risk of confusing 2 similar-looking people).",
        "ja": "検出した顔が既知の人物とどれだけ一致すれば認識するか。高いほど厳格（誤認識は減るが、角度や照"
        "明が悪いと既知の人物を見逃しやすい）。低いほど緩やか（既知の人物を認識しやすいが、似た顔の2人を混"
        "同するリスクが上がる）。",
    },
    "Face memory match strictness": {
        "vi": "Độ chặt của bộ nhớ khuôn mặt",
        "en": "Face memory match strictness",
        "ja": "顔メモリの一致厳密度",
    },
    "How closely 2 sightings must match to be treated as the SAME person when tracking briefly loses "
    "them (they turned away/looked down for a moment). Higher = stricter (safer, but may fail to "
    "reconnect after a bad angle - shows up as a fresh Stranger notification or a moment of \"Unknown\" "
    "for a known person). Lower = looser (reconnects more easily, but raises the risk of confusing 2 "
    "different people who look alike).": {
        "vi": "2 lần nhìn thấy phải giống nhau tới mức nào mới được coi là ĐÚNG 1 người khi việc theo dõi bị "
        "mất dấu thoáng qua (họ quay đầu/cúi xuống 1 lúc). Cao hơn = chặt hơn (an toàn hơn, nhưng dễ không "
        "bắc cầu được sau 1 góc xấu - hiện ra như 1 thông báo Người lạ mới hoặc 1 lúc \"Unknown\" cho người "
        "quen). Thấp hơn = lỏng hơn (bắc cầu dễ hơn, nhưng dễ nhầm 2 người khác nhau trông giống nhau).",
        "en": "How closely 2 sightings must match to be treated as the SAME person when tracking briefly "
        "loses them (they turned away/looked down for a moment). Higher = stricter (safer, but may fail "
        "to reconnect after a bad angle - shows up as a fresh Stranger notification or a moment of "
        "\"Unknown\" for a known person). Lower = looser (reconnects more easily, but raises the risk of "
        "confusing 2 different people who look alike).",
        "ja": "追跡が一時的に途切れた（少し目を離した/下を向いた）後、2回の目撃を同一人物として扱うにはどれ"
        "だけ一致する必要があるか。高いほど厳格（安全だが、悪い角度の後に再接続できず、新しい不審者通知や既"
        "知の人物の一時的な「不明」として表示される場合がある）。低いほど緩やか（再接続しやすいが、似た外見"
        "の別人を混同するリスクが上がる）。",
    },
    "🔄  Refresh Known Faces": {"vi": "🔄  Làm mới danh sách khuôn mặt", "en": "🔄  Refresh Known Faces", "ja": "🔄  既知の顔を更新"},
    "Known faces: not loaded": {"vi": "Khuôn mặt đã biết: chưa tải", "en": "Known faces: not loaded", "ja": "既知の顔: 未読込"},
    "Known faces: load error ({error})": {
        "vi": "Khuôn mặt đã biết: lỗi tải ({error})",
        "en": "Known faces: load error ({error})",
        "ja": "既知の顔: 読込エラー ({error})",
    },
    "Known faces: {n} people": {
        "vi": "Khuôn mặt đã biết: {n} người",
        "en": "Known faces: {n} people",
        "ja": "既知の顔: {n}人",
    },
    "⚙  Open Pipeline Config": {"vi": "⚙  Mở cấu hình Pipeline", "en": "⚙  Open Pipeline Config", "ja": "⚙  パイプライン設定を開く"},
    "Pipeline Config": {"vi": "Cấu hình Pipeline", "en": "Pipeline Config", "ja": "パイプライン設定"},
    "TODO: open detailed AI pipeline configuration dialog.": {
        "vi": "TODO: mở dialog cấu hình pipeline AI chi tiết.",
        "en": "TODO: open detailed AI pipeline configuration dialog.",
        "ja": "TODO: 詳細なAIパイプライン設定ダイアログを開く。",
    },
    "Click \"Open ROI Editor…\" to draw ROI/Counting Line directly on the camera feed": {
        "vi": "Bấm \"Open ROI Editor…\" để vẽ trực tiếp ROI/Counting Line lên hình camera",
        "en": "Click \"Open ROI Editor…\" to draw ROI/Counting Line directly on the camera feed",
        "ja": "「Open ROI Editor…」をクリックしてカメラ映像上に直接ROI/Counting Lineを描画",
    },
    "Regions of Interest": {"vi": "Vùng quan tâm (ROI)", "en": "Regions of Interest", "ja": "関心領域（ROI）"},
    "✏  Open ROI Editor…": {"vi": "✏  Mở ROI Editor…", "en": "✏  Open ROI Editor…", "ja": "✏  ROIエディタを開く…"},
    "View-only list - draw/edit/delete via the ROI Editor": {
        "vi": "Danh sách chỉ để xem - vẽ/sửa/xoá qua ROI Editor",
        "en": "View-only list - draw/edit/delete via the ROI Editor",
        "ja": "閲覧専用リスト - 作成/編集/削除はROIエディタで行ってください",
    },
    "Counting Line (count people in/out)": {
        "vi": "Counting Line (đếm người vào/ra)",
        "en": "Counting Line (count people in/out)",
        "ja": "Counting Line（入退室カウント）",
    },
    "Not set": {"vi": "Chưa đặt", "en": "Not set", "ja": "未設定"},
    "Set: {value}": {"vi": "Đã đặt: {value}", "en": "Set: {value}", "ja": "設定済み: {value}"},
    "Enable Trigger": {"vi": "Bật Trigger", "en": "Enable Trigger", "ja": "トリガーを有効化"},
    "Trigger Rules": {"vi": "Quy tắc Trigger", "en": "Trigger Rules", "ja": "トリガールール"},
    "＋  Add Rule": {"vi": "＋  Thêm quy tắc", "en": "＋  Add Rule", "ja": "＋  ルールを追加"},
    "✏  Edit Rule": {"vi": "✏  Sửa quy tắc", "en": "✏  Edit Rule", "ja": "✏  ルールを編集"},
    "🗑  Delete Rule": {"vi": "🗑  Xoá quy tắc", "en": "🗑  Delete Rule", "ja": "🗑  ルールを削除"},
    "Double-click a rule to edit it in the Rule Editor dialog.": {
        "vi": "Double-click 1 quy tắc để sửa trong dialog Rule Editor.",
        "en": "Double-click a rule to edit it in the Rule Editor dialog.",
        "ja": "ルールをダブルクリックするとRule Editorダイアログで編集できます。",
    },
    "Trigger Rule": {"vi": "Quy tắc Trigger", "en": "Trigger Rule", "ja": "トリガールール"},
    "Please select a camera first.": {
        "vi": "Vui lòng chọn 1 camera trước.",
        "en": "Please select a camera first.",
        "ja": "先にカメラを選択してください。",
    },
    "Please select a rule from the list to delete.": {
        "vi": "Vui lòng chọn 1 quy tắc trong danh sách để xoá.",
        "en": "Please select a rule from the list to delete.",
        "ja": "削除するルールをリストから選択してください。",
    },
    "Recording Settings": {"vi": "Cài đặt ghi hình", "en": "Recording Settings", "ja": "録画設定"},
    "Enable Recording": {"vi": "Bật ghi hình", "en": "Enable Recording", "ja": "録画を有効化"},
    "Recording Mode": {"vi": "Chế độ ghi hình", "en": "Recording Mode", "ja": "録画モード"},
    "Continuous": {"vi": "Liên tục", "en": "Continuous", "ja": "常時録画"},
    "On Motion": {"vi": "Khi có chuyển động", "en": "On Motion", "ja": "動体検知時"},
    "On Trigger": {"vi": "Khi có Trigger", "en": "On Trigger", "ja": "トリガー時"},
    "Scheduled": {"vi": "Theo lịch", "en": "Scheduled", "ja": "スケジュール"},
    "Save Path": {"vi": "Nơi lưu", "en": "Save Path", "ja": "保存先"},
    "Browse…": {"vi": "Duyệt…", "en": "Browse…", "ja": "参照…"},
    "Select video save folder": {
        "vi": "Chọn thư mục lưu video",
        "en": "Select video save folder",
        "ja": "動画の保存フォルダを選択",
    },
    "Retention (days)": {"vi": "Thời gian lưu (ngày)", "en": "Retention (days)", "ja": "保持期間（日）"},
    "📅  Schedule Config…": {"vi": "📅  Cấu hình lịch…", "en": "📅  Schedule Config…", "ja": "📅  スケジュール設定…"},
    "Schedule Config": {"vi": "Cấu hình lịch ghi hình", "en": "Schedule Config", "ja": "スケジュール設定"},
    "TODO: open detailed recording schedule configuration dialog.": {
        "vi": "TODO: mở dialog cấu hình lịch ghi hình chi tiết.",
        "en": "TODO: open detailed recording schedule configuration dialog.",
        "ja": "TODO: 詳細な録画スケジュール設定ダイアログを開く。",
    },
    "Overlay Visibility": {"vi": "Hiển thị Overlay", "en": "Overlay Visibility", "ja": "オーバーレイ表示"},
    "Show Bounding Box": {"vi": "Hiện khung bao", "en": "Show Bounding Box", "ja": "バウンディングボックスを表示"},
    "Show Label": {"vi": "Hiện nhãn", "en": "Show Label", "ja": "ラベルを表示"},
    "Show Confidence": {"vi": "Hiện độ tin cậy", "en": "Show Confidence", "ja": "信頼度を表示"},
    "Show ROI": {"vi": "Hiện ROI", "en": "Show ROI", "ja": "ROIを表示"},
    "Show Tracking ID": {"vi": "Hiện ID theo dõi", "en": "Show Tracking ID", "ja": "追跡IDを表示"},
    "🎨  Overlay Settings…": {"vi": "🎨  Cài đặt Overlay…", "en": "🎨  Overlay Settings…", "ja": "🎨  オーバーレイ設定…"},
    "Overlay Settings": {"vi": "Cài đặt Overlay", "en": "Overlay Settings", "ja": "オーバーレイ設定"},
    "TODO: open detailed overlay color/style configuration dialog.": {
        "vi": "TODO: mở dialog cấu hình chi tiết màu sắc/kiểu overlay.",
        "en": "TODO: open detailed overlay color/style configuration dialog.",
        "ja": "TODO: 詳細なオーバーレイの色/スタイル設定ダイアログを開く。",
    },
    "Pipeline": {"vi": "Pipeline", "en": "Pipeline", "ja": "パイプライン"},
    "Frame Queue Size": {"vi": "Kích thước hàng đợi khung hình", "en": "Frame Queue Size", "ja": "フレームキューサイズ"},
    "Reconnect Timeout (s)": {"vi": "Thời gian chờ kết nối lại (giây)", "en": "Reconnect Timeout (s)", "ja": "再接続タイムアウト（秒）"},
    "Hardware & Decoder": {"vi": "Phần cứng & Bộ giải mã", "en": "Hardware & Decoder", "ja": "ハードウェア＆デコーダー"},
    "Decoder Backend": {"vi": "Bộ giải mã", "en": "Decoder Backend", "ja": "デコーダーバックエンド"},
    "Hardware Acceleration": {"vi": "Tăng tốc phần cứng", "en": "Hardware Acceleration", "ja": "ハードウェアアクセラレーション"},
    "GPU Device": {"vi": "Thiết bị GPU", "en": "GPU Device", "ja": "GPUデバイス"},
    "GPU 0 (default)": {"vi": "GPU 0 (mặc định)", "en": "GPU 0 (default)", "ja": "GPU 0（デフォルト）"},
    "GPU 1": {"vi": "GPU 1", "en": "GPU 1", "ja": "GPU 1"},
    "CPU Fallback": {"vi": "Dự phòng CPU", "en": "CPU Fallback", "ja": "CPUフォールバック"},
    "💾  Save": {"vi": "💾  Lưu", "en": "💾  Save", "ja": "💾  保存"},
    "✔  Apply": {"vi": "✔  Áp dụng", "en": "✔  Apply", "ja": "✔  適用"},
    "↺  Reset": {"vi": "↺  Đặt lại", "en": "↺  Reset", "ja": "↺  リセット"},
    "↑  Export Config": {"vi": "↑  Xuất cấu hình", "en": "↑  Export Config", "ja": "↑  設定をエクスポート"},
    "↓  Import Config": {"vi": "↓  Nhập cấu hình", "en": "↓  Import Config", "ja": "↓  設定をインポート"},
    "Basic": {"vi": "Cơ bản", "en": "Basic", "ja": "基本"},
    "ROI": {"vi": "ROI", "en": "ROI", "ja": "ROI"},
    "Trigger": {"vi": "Trigger", "en": "Trigger", "ja": "トリガー"},
    "Recording": {"vi": "Ghi hình", "en": "Recording", "ja": "録画"},
    "Overlay": {"vi": "Overlay", "en": "Overlay", "ja": "オーバーレイ"},
    "Advanced": {"vi": "Nâng cao", "en": "Advanced", "ja": "詳細設定"},
    "Saved": {"vi": "Đã lưu", "en": "Saved", "ja": "保存しました"},
    "Camera configuration saved.": {
        "vi": "Đã lưu cấu hình camera.",
        "en": "Camera configuration saved.",
        "ja": "カメラ設定を保存しました。",
    },
    "No camera selected": {"vi": "Chưa chọn camera", "en": "No camera selected", "ja": "カメラが選択されていません"},
    "Please select a camera from the list on the left.": {
        "vi": "Vui lòng chọn 1 camera ở danh sách bên trái.",
        "en": "Please select a camera from the list on the left.",
        "ja": "左側のリストからカメラを選択してください。",
    },
    "Missing information": {"vi": "Thiếu thông tin", "en": "Missing information", "ja": "情報が不足しています"},
    "Camera Name cannot be empty.": {
        "vi": "Tên camera không được để trống.",
        "en": "Camera Name cannot be empty.",
        "ja": "カメラ名を空にすることはできません。",
    },
    "Count In/Out requires drawing a Counting Line (ROI tab).": {
        "vi": "Đếm vào/ra cần vẽ Counting Line (tab ROI).",
        "en": "Count In/Out requires drawing a Counting Line (ROI tab).",
        "ja": "入退室カウントにはCounting Lineの作成が必要です（ROIタブ）。",
    },
    "Occupancy requires at least 1 ROI (ROI tab).": {
        "vi": "Occupancy cần vẽ ít nhất 1 ROI (tab ROI).",
        "en": "Occupancy requires at least 1 ROI (ROI tab).",
        "ja": "在室人数監視には少なくとも1つのROIが必要です（ROIタブ）。",
    },
    "PPE requires at least 1 ROI (ROI tab).": {
        "vi": "PPE cần vẽ ít nhất 1 ROI (tab ROI).",
        "en": "PPE requires at least 1 ROI (ROI tab).",
        "ja": "PPE監視には少なくとも1つのROIが必要です（ROIタブ）。",
    },
    "Face Recognition has no known faces yet - every face will be treated as 'Stranger' until 'Refresh Known Faces' succeeds.": {
        "vi": "Face Recognition chưa có khuôn mặt đã biết - mọi khuôn mặt sẽ bị coi là 'Người lạ' cho tới khi 'Làm mới danh sách khuôn mặt' thành công.",
        "en": "Face Recognition has no known faces yet - every face will be treated as 'Stranger' until 'Refresh Known Faces' succeeds.",
        "ja": "顔認識にはまだ既知の顔が登録されていません - 「既知の顔を更新」が成功するまで、すべての顔は「不審者」として扱われます。",
    },
    "Missing ROI/Line configuration": {
        "vi": "Thiếu cấu hình ROI/Line",
        "en": "Missing ROI/Line configuration",
        "ja": "ROI/Lineの設定が不足しています",
    },
    "Saved, but the following features will NOT run until fully configured:\n\n": {
        "vi": "Đã lưu, nhưng các tính năng sau sẽ CHƯA chạy cho tới khi cấu hình đủ:\n\n",
        "en": "Saved, but the following features will NOT run until fully configured:\n\n",
        "ja": "保存しましたが、以下の機能は設定が完了するまで動作しません：\n\n",
    },
    "Export Config": {"vi": "Xuất cấu hình", "en": "Export Config", "ja": "設定をエクスポート"},
    "Configuration exported to:\n{path}": {
        "vi": "Đã xuất cấu hình ra:\n{path}",
        "en": "Configuration exported to:\n{path}",
        "ja": "設定をエクスポートしました:\n{path}",
    },
    "Import Config": {"vi": "Nhập cấu hình", "en": "Import Config", "ja": "設定をインポート"},
    "Invalid configuration file:\n{exc}": {
        "vi": "File cấu hình không hợp lệ:\n{exc}",
        "en": "Invalid configuration file:\n{exc}",
        "ja": "無効な設定ファイルです:\n{exc}",
    },
    "Configuration applied to the selected camera.": {
        "vi": "Đã áp cấu hình vào camera đang chọn.",
        "en": "Configuration applied to the selected camera.",
        "ja": "選択したカメラに設定を適用しました。",
    },
    "New camera created from the configuration file.": {
        "vi": "Đã tạo camera mới từ file cấu hình.",
        "en": "New camera created from the configuration file.",
        "ja": "設定ファイルから新しいカメラを作成しました。",
    },
    "Please click Start on the camera before viewing the preview.": {
        "vi": "Vui lòng bấm Start camera trước khi xem preview.",
        "en": "Please click Start on the camera before viewing the preview.",
        "ja": "プレビューを表示する前にカメラのStartをクリックしてください。",
    },
    "Preview error:\n{message}": {
        "vi": "Lỗi xem trước:\n{message}",
        "en": "Preview error:\n{message}",
        "ja": "プレビューエラー:\n{message}",
    },
    "People: {n}": {"vi": "Người: {n}", "en": "People: {n}", "ja": "人数: {n}"},
    "In: {n}": {"vi": "Vào: {n}", "en": "In: {n}", "ja": "入: {n}"},
    "Out: {n}": {"vi": "Ra: {n}", "en": "Out: {n}", "ja": "出: {n}"},
    "Recognized: {names}": {"vi": "Nhận diện: {names}", "en": "Recognized: {names}", "ja": "認識: {names}"},
    "⚠ PPE VIOLATION": {"vi": "⚠ VI PHẠM PPE", "en": "⚠ PPE VIOLATION", "ja": "⚠ PPE違反"},
    "🔥 FIRE": {"vi": "🔥 CHÁY", "en": "🔥 FIRE", "ja": "🔥 火災"},
    "🚨 FALL": {"vi": "🚨 TÉ NGÃ", "en": "🚨 FALL", "ja": "🚨 転倒"},
    "🧑‍❓ STRANGER": {"vi": "🧑‍❓ NGƯỜI LẠ", "en": "🧑‍❓ STRANGER", "ja": "🧑‍❓ 不審者"},
    "ROI Editor": {"vi": "ROI Editor", "en": "ROI Editor", "ja": "ROIエディタ"},

    # ------------------------------------------------------------------ #
    # event_log_page.ui / event_log_page.py
    # ------------------------------------------------------------------ #
    "All cameras": {"vi": "Tất cả camera", "en": "All cameras", "ja": "すべてのカメラ"},
    "All types": {"vi": "Tất cả loại", "en": "All types", "ja": "すべての種類"},
    "PPE Violation": {"vi": "Vi phạm PPE", "en": "PPE Violation", "ja": "PPE違反"},
    "Fire / Smoke": {"vi": "Cháy / Khói", "en": "Fire / Smoke", "ja": "火災・煙"},
    "Fall": {"vi": "Té ngã", "en": "Fall", "ja": "転倒"},
    "Stranger": {"vi": "Người lạ", "en": "Stranger", "ja": "不審者"},
    "Check-in": {"vi": "Điểm danh", "en": "Check-in", "ja": "チェックイン"},
    "Check-out": {"vi": "Điểm danh ra", "en": "Check-out", "ja": "チェックアウト"},
    "All time": {"vi": "Toàn bộ thời gian", "en": "All time", "ja": "全期間"},
    "Today": {"vi": "Hôm nay", "en": "Today", "ja": "今日"},
    "Last 7 days": {"vi": "7 ngày gần đây", "en": "Last 7 days", "ja": "過去7日間"},
    "Last 30 days": {"vi": "30 ngày gần đây", "en": "Last 30 days", "ja": "過去30日間"},
    "{n} events": {"vi": "{n} sự kiện", "en": "{n} events", "ja": "{n}件のイベント"},
    "◀ Prev": {"vi": "◀ Trước", "en": "◀ Prev", "ja": "◀ 前へ"},
    "Next ▶": {"vi": "Tiếp ▶", "en": "Next ▶", "ja": "次へ ▶"},
    "Page {page} / {total}": {
        "vi": "Trang {page} / {total}",
        "en": "Page {page} / {total}",
        "ja": "{page} / {total} ページ",
    },
    "Image": {"vi": "Ảnh", "en": "Image", "ja": "画像"},
    "Time": {"vi": "Thời gian", "en": "Time", "ja": "時刻"},
    "Event Type": {"vi": "Loại sự kiện", "en": "Event Type", "ja": "イベント種別"},
    "Detail": {"vi": "Chi tiết", "en": "Detail", "ja": "詳細"},
    "Evidence Image": {"vi": "Ảnh bằng chứng", "en": "Evidence Image", "ja": "証拠画像"},
    "Event Log": {"vi": "Nhật ký sự kiện", "en": "Event Log", "ja": "イベントログ"},

    # ------------------------------------------------------------------ #
    # ui/dialogs/roi_editor_dialog.py
    # ------------------------------------------------------------------ #
    "No image": {"vi": "Không có hình", "en": "No image", "ja": "画像なし"},
    "At least 3 points are required to create an ROI.": {
        "vi": "Cần ít nhất 3 điểm để tạo vùng ROI.",
        "en": "At least 3 points are required to create an ROI.",
        "ja": "ROIを作成するには少なくとも3つの点が必要です。",
    },
    "ROI Name": {"vi": "Tên vùng ROI", "en": "ROI Name", "ja": "ROI名"},
    "Name:": {"vi": "Tên:", "en": "Name:", "ja": "名前:"},
    "＋  Draw New ROI": {"vi": "＋  Vẽ ROI mới", "en": "＋  Draw New ROI", "ja": "＋  新規ROIを描画"},
    "🗑  Delete Selected ROI": {"vi": "🗑  Xoá ROI đã chọn", "en": "🗑  Delete Selected ROI", "ja": "🗑  選択したROIを削除"},
    "📏  Redraw Counting Line": {"vi": "📏  Vẽ lại Counting Line", "en": "📏  Redraw Counting Line", "ja": "📏  Counting Lineを再描画"},
    "🔄  Flip IN/OUT Direction": {"vi": "🔄  Đổi chiều IN/OUT", "en": "🔄  Flip IN/OUT Direction", "ja": "🔄  IN/OUT方向を反転"},
    "🗑  Delete Line": {"vi": "🗑  Xoá Line", "en": "🗑  Delete Line", "ja": "🗑  ラインを削除"},
    "Click to add a point.\nDouble-click or Enter to close an ROI (≥ 3 points).\nCounting Line closes automatically after the 2nd point.\nEsc: cancel current drawing.   Backspace: remove last point.\nIN/OUT direction doesn't depend on draw order - use the\n\"Flip IN/OUT Direction\" button to reverse it if needed.": {
        "vi": "Click để thêm điểm.\nDouble-click hoặc Enter để đóng vùng ROI (≥ 3 điểm).\nCounting Line tự đóng sau điểm thứ 2.\nEsc: huỷ vẽ dở.   Backspace: xoá điểm cuối.\nChiều IN/OUT không phụ thuộc hướng vẽ - dùng nút\n\"Đổi chiều IN/OUT\" để đảo lại nếu vẽ ngược ý.",
        "en": "Click to add a point.\nDouble-click or Enter to close an ROI (≥ 3 points).\nCounting Line closes automatically after the 2nd point.\nEsc: cancel current drawing.   Backspace: remove last point.\nIN/OUT direction doesn't depend on draw order - use the\n\"Flip IN/OUT Direction\" button to reverse it if needed.",
        "ja": "クリックして点を追加します。\nダブルクリックまたはEnterでROIを閉じます（3点以上）。\nCounting Lineは2点目の後、自動的に閉じます。\nEsc: 描画をキャンセル　Backspace: 最後の点を削除\nIN/OUT方向は描画順に依存しません - 必要に応じて\n「IN/OUT方向を反転」ボタンで反転してください。",
    },
    "ROI Regions (Occupancy)": {"vi": "Vùng ROI (Occupancy)", "en": "ROI Regions (Occupancy)", "ja": "ROI領域（在室検知）"},
    "Counting Line (In/Out)": {"vi": "Counting Line (Vào/Ra)", "en": "Counting Line (In/Out)", "ja": "Counting Line（入/出）"},
    "Select an ROI from the list to delete.": {
        "vi": "Chọn 1 ROI trong danh sách để xoá.",
        "en": "Select an ROI from the list to delete.",
        "ja": "削除するROIをリストから選択してください。",
    },
    "Could not get a frame from the camera (not started and could not connect).\nYou can still draw ROI/Line on a blank background using estimated coordinates.": {
        "vi": "Không lấy được hình từ camera (chưa Start và không kết nối được).\nVẫn có thể vẽ ROI/Line trên nền trống theo toạ độ ước lượng.",
        "en": "Could not get a frame from the camera (not started and could not connect).\nYou can still draw ROI/Line on a blank background using estimated coordinates.",
        "ja": "カメラから映像を取得できませんでした（未起動または接続不可）。\n推定座標で空白の背景にROI/Lineを描画することは可能です。",
    },
    "IN": {"vi": "VÀO", "en": "IN", "ja": "IN"},
    "OUT": {"vi": "RA", "en": "OUT", "ja": "OUT"},

    # ------------------------------------------------------------------ #
    # ui/dialogs/trigger_rule_dialog.py
    # ------------------------------------------------------------------ #
    "Rule Name": {"vi": "Tên quy tắc", "en": "Rule Name", "ja": "ルール名"},
    "Condition (IF)": {"vi": "Điều kiện (IF)", "en": "Condition (IF)", "ja": "条件（IF）"},
    "Action (THEN)": {"vi": "Hành động (THEN)", "en": "Action (THEN)", "ja": "アクション（THEN）"},

    # ------------------------------------------------------------------ #
    # ui/dialogs/add_device_dialog.py
    # ------------------------------------------------------------------ #
    "Add Camera": {"vi": "Thêm camera", "en": "Add Camera", "ja": "カメラを追加"},
    "Device Type": {"vi": "Loại thiết bị", "en": "Device Type", "ja": "デバイスタイプ"},
    "Identifies this camera on the web server - leave empty if unknown, you can enter/edit it later in Camera Config.": {
        "vi": "Định danh camera này bên web server - để trống nếu chưa biết, có thể nhập/sửa sau ở Camera Config.",
        "en": "Identifies this camera on the web server - leave empty if unknown, you can enter/edit it later in Camera Config.",
        "ja": "このカメラをWebサーバー上で識別します - 不明な場合は空欄のままにし、後でCamera Configで入力/編集できます。",
    },
    "USB Index": {"vi": "Chỉ số USB", "en": "USB Index", "ja": "USBインデックス"},

    # ------------------------------------------------------------------ #
    # pages/face_attendance_page.py (Face App kiosk)
    # ------------------------------------------------------------------ #
    "Face App - Attendance": {"vi": "Face App - Chấm công", "en": "Face App - Attendance", "ja": "顔認証アプリ - 勤怠"},
    "Select camera for Face App": {
        "vi": "Chọn camera cho Face App",
        "en": "Select camera for Face App",
        "ja": "顔認証アプリ用のカメラを選択",
    },
    "🪪  FACE ATTENDANCE": {"vi": "🪪  CHẤM CÔNG KHUÔN MẶT", "en": "🪪  FACE ATTENDANCE", "ja": "🪪  顔認証勤怠"},
    "Searching for face...": {"vi": "Đang tìm khuôn mặt...", "en": "Searching for face...", "ja": "顔を検索中..."},
    "Stand facing the camera, keep your face within the frame": {
        "vi": "Đứng thẳng trước camera, giữ khuôn mặt trong khung hình",
        "en": "Stand facing the camera, keep your face within the frame",
        "ja": "カメラの正面に立ち、顔を枠内に収めてください",
    },
    "➕  Register": {"vi": "➕  Đăng ký", "en": "➕  Register", "ja": "➕  登録"},
    "⚙  Change Camera": {"vi": "⚙  Đổi camera", "en": "⚙  Change Camera", "ja": "⚙  カメラを変更"},
    "Move a bit closer to the camera": {
        "vi": "Lại gần camera hơn một chút",
        "en": "Move a bit closer to the camera",
        "ja": "もう少しカメラに近づいてください",
    },
    "Hello, {name}": {"vi": "Xin chào, {name}", "en": "Hello, {name}", "ja": "こんにちは、{name}さん"},
    "✎  Edit Info": {"vi": "✎  Sửa thông tin", "en": "✎  Edit Info", "ja": "✎  情報を編集"},
    "Not recognized - new person": {
        "vi": "Chưa nhận diện được - người mới",
        "en": "Not recognized - new person",
        "ja": "未認識 - 新しい人物",
    },
    "⏳ Saving information...": {"vi": "⏳ Đang lưu thông tin...", "en": "⏳ Saving information...", "ja": "⏳ 情報を保存中..."},
    "Success": {"vi": "Thành công", "en": "Success", "ja": "成功"},
    "Error": {"vi": "Lỗi", "en": "Error", "ja": "エラー"},
    "⚠ {message}": {"vi": "⚠ {message}", "en": "⚠ {message}", "ja": "⚠ {message}"},
    "Could not open camera: {source}": {
        "vi": "Không thể mở camera: {source}",
        "en": "Could not open camera: {source}",
        "ja": "カメラを開けませんでした: {source}",
    },
    "Failed to save information to server: {exc}": {
        "vi": "Lỗi lưu thông tin lên server: {exc}",
        "en": "Failed to save information to server: {exc}",
        "ja": "サーバーへの情報保存に失敗しました: {exc}",
    },
    "Employee information saved successfully.": {
        "vi": "Đã lưu thông tin nhân viên thành công.",
        "en": "Employee information saved successfully.",
        "ja": "従業員情報を正常に保存しました。",
    },

    # ------------------------------------------------------------------ #
    # pages/gate_kiosk_page.py (Check In/Out kiosk)
    # ------------------------------------------------------------------ #
    "CHECK IN": {"vi": "CHẤM CÔNG VÀO", "en": "CHECK IN", "ja": "出勤"},
    "CHECK OUT": {"vi": "CHẤM CÔNG RA", "en": "CHECK OUT", "ja": "退勤"},
    "Stranger detected at gate {gate}": {
        "vi": "Phát hiện người lạ - cổng {gate}",
        "en": "Stranger detected at gate {gate}",
        "ja": "不審者を検知 - ゲート{gate}",
    },
    "Waiting for camera feed...": {
        "vi": "Đang chờ hình từ camera...",
        "en": "Waiting for camera feed...",
        "ja": "カメラ映像を待機中...",
    },
    "Gate Kiosk - {label}": {"vi": "Kiosk Cổng - {label}", "en": "Gate Kiosk - {label}", "ja": "ゲートキオスク - {label}"},
    "Total: {n}": {"vi": "Tổng: {n}", "en": "Total: {n}", "ja": "合計: {n}"},
    "Set Up Gate {label}": {"vi": "Thiết lập cổng {label}", "en": "Set Up Gate {label}", "ja": "ゲート{label}を設定"},
    "⚠ Camera \"{name}\" has no Counting Line - go to Camera Config > ROI tab to draw one.": {
        "vi": "⚠ Camera \"{name}\" chưa vẽ Counting Line - vào Camera Config > tab ROI để vẽ vạch.",
        "en": "⚠ Camera \"{name}\" has no Counting Line - go to Camera Config > ROI tab to draw one.",
        "ja": "⚠ カメラ「{name}」にCounting Lineがありません - Camera Config > ROIタブで作成してください。",
    },
    "⚠ Camera \"{name}\" has no gate ROI - go to Camera Config > ROI tab to draw the gate zone.": {
        "vi": "⚠ Camera \"{name}\" chưa vẽ vùng ROI cổng - vào Camera Config > tab ROI để vẽ vùng cổng.",
        "en": "⚠ Camera \"{name}\" has no gate ROI - go to Camera Config > ROI tab to draw the gate zone.",
        "ja": "⚠ カメラ「{name}」にゲートROIがありません - Camera Config > ROIタブでゲート範囲を作成してください。",
    },
    "⚠ Camera \"{name}\" is not started - go to Camera Config or Device Management to start it.": {
        "vi": "⚠ Camera \"{name}\" chưa được Start - vào Camera Config hoặc Device Management để bật chạy.",
        "en": "⚠ Camera \"{name}\" is not started - go to Camera Config or Device Management to start it.",
        "ja": "⚠ カメラ「{name}」が起動していません - Camera ConfigまたはDevice Managementで起動してください。",
    },
    "⚠ Camera \"{name}\" has stopped - go to Camera Config to start it again.": {
        "vi": "⚠ Camera \"{name}\" đã dừng - vào Camera Config để Start lại.",
        "en": "⚠ Camera \"{name}\" has stopped - go to Camera Config to start it again.",
        "ja": "⚠ カメラ「{name}」が停止しました - Camera Configで再起動してください。",
    },

    # ------------------------------------------------------------------ #
    # ui/dialogs/gate_setup_dialog.py
    # ------------------------------------------------------------------ #
    "Select camera": {"vi": "Chọn camera", "en": "Select camera", "ja": "カメラを選択"},
    " (with Counting Line configured in Camera Config > ROI)": {
        "vi": " (đã cấu hình Counting Line ở Camera Config > ROI)",
        "en": " (with Counting Line configured in Camera Config > ROI)",
        "ja": "（Camera Config > ROIでCounting Lineを設定済み）",
    },
    "⚠ No camera has been registered yet - go to Device Management to add one first.": {
        "vi": "⚠ Chưa có camera nào được đăng ký - vào Device Management để thêm camera trước.",
        "en": "⚠ No camera has been registered yet - go to Device Management to add one first.",
        "ja": "⚠ まだカメラが登録されていません - Device Managementで先に追加してください。",
    },
    "⚠ Camera \"{name}\" is not started - go to Camera Config or Device Management to start it first.": {
        "vi": "⚠ Camera \"{name}\" chưa được Start - vào Camera Config hoặc Device Management để bật chạy trước.",
        "en": "⚠ Camera \"{name}\" is not started - go to Camera Config or Device Management to start it first.",
        "ja": "⚠ カメラ「{name}」が起動していません - 先にCamera ConfigまたはDevice Managementで起動してください。",
    },
    "⚠ Camera \"{name}\" has no Counting Line - go to Camera Config > ROI tab to draw one first.": {
        "vi": "⚠ Camera \"{name}\" chưa vẽ Counting Line - vào Camera Config > tab ROI để vẽ vạch trước.",
        "en": "⚠ Camera \"{name}\" has no Counting Line - go to Camera Config > ROI tab to draw one first.",
        "ja": "⚠ カメラ「{name}」にCounting Lineがありません - 先にCamera Config > ROIタブで作成してください。",
    },
    "✓ Camera \"{name}\" is ready.": {
        "vi": "✓ Camera \"{name}\" đã sẵn sàng.",
        "en": "✓ Camera \"{name}\" is ready.",
        "ja": "✓ カメラ「{name}」の準備ができました。",
    },
    "No Camera Selected": {"vi": "Chưa chọn camera", "en": "No Camera Selected", "ja": "カメラが選択されていません"},
    "Camera Not Running": {"vi": "Camera chưa chạy", "en": "Camera Not Running", "ja": "カメラが実行されていません"},
    "Camera \"{name}\" is not started.\nGo to Camera Config or Device Management to start it first.": {
        "vi": "Camera \"{name}\" chưa được Start.\nVào Camera Config hoặc Device Management để bật chạy trước.",
        "en": "Camera \"{name}\" is not started.\nGo to Camera Config or Device Management to start it first.",
        "ja": "カメラ「{name}」が起動していません。\n先にCamera ConfigまたはDevice Managementで起動してください。",
    },
    "No Counting Line": {"vi": "Chưa có vạch đếm", "en": "No Counting Line", "ja": "Counting Lineがありません"},
    "Camera \"{name}\" has no Counting Line.\nGo to Camera Config > ROI tab to draw one first.": {
        "vi": "Camera \"{name}\" chưa vẽ Counting Line.\nVào Camera Config > tab ROI để vẽ vạch trước.",
        "en": "Camera \"{name}\" has no Counting Line.\nGo to Camera Config > ROI tab to draw one first.",
        "ja": "カメラ「{name}」にCounting Lineがありません。\n先にCamera Config > ROIタブで作成してください。",
    },

    # ------------------------------------------------------------------ #
    # ui/dialogs/employee_form_dialog.py
    # ------------------------------------------------------------------ #
    "Edit Employee Information": {"vi": "Sửa thông tin nhân viên", "en": "Edit Employee Information", "ja": "従業員情報を編集"},
    "Register New Employee": {"vi": "Đăng ký nhân viên mới", "en": "Register New Employee", "ja": "新規従業員登録"},
    "💳 Scan an ID card at any time to auto-fill Employee Code/First Name/Last Name/DOB/Gender/Address, or enter manually below.": {
        "vi": "💳 Quét thẻ CCCD bất kỳ lúc nào để tự điền Mã NV/Tên/Họ/Ngày sinh/Giới tính/Địa chỉ, hoặc tự nhập tay bên dưới.",
        "en": "💳 Scan an ID card at any time to auto-fill Employee Code/First Name/Last Name/DOB/Gender/Address, or enter manually below.",
        "ja": "💳 いつでもIDカードをスキャンして、社員コード/名/姓/生年月日/性別/住所を自動入力できます。または下に手動で入力してください。",
    },
    "Employee Code *": {"vi": "Mã nhân viên *", "en": "Employee Code *", "ja": "社員コード *"},
    "First Name *": {"vi": "Tên *", "en": "First Name *", "ja": "名 *"},
    "Last Name *": {"vi": "Họ *", "en": "Last Name *", "ja": "姓 *"},
    "Gender": {"vi": "Giới tính", "en": "Gender", "ja": "性別"},
    "Male": {"vi": "Nam", "en": "Male", "ja": "男性"},
    "Female": {"vi": "Nữ", "en": "Female", "ja": "女性"},
    "Date of Birth": {"vi": "Ngày sinh", "en": "Date of Birth", "ja": "生年月日"},
    "Address": {"vi": "Địa chỉ", "en": "Address", "ja": "住所"},
    "Phone Number": {"vi": "Số điện thoại", "en": "Phone Number", "ja": "電話番号"},
    "Email": {"vi": "Email", "en": "Email", "ja": "メールアドレス"},
    "✓ Information filled from the scanned card.": {
        "vi": "✓ Đã điền thông tin từ thẻ vừa quét.",
        "en": "✓ Information filled from the scanned card.",
        "ja": "✓ スキャンしたカードから情報を入力しました。",
    },
    "🗑  Clear Scanned Info": {
        "vi": "🗑  Xoá thông tin đã quét",
        "en": "🗑  Clear Scanned Info",
        "ja": "🗑  スキャン情報を消去",
    },
    "🔒 Information locked from the scanned card. Use \"Clear Scanned Info\" to edit manually.": {
        "vi": "🔒 Thông tin đã khoá theo thẻ vừa quét. Bấm \"Xoá thông tin đã quét\" để tự sửa tay.",
        "en": "🔒 Information locked from the scanned card. Use \"Clear Scanned Info\" to edit manually.",
        "ja": "🔒 スキャンしたカードの情報はロックされています。手動で編集するには「スキャン情報を消去」を使用してください。",
    },
    "🔒 Name, date of birth and gender cannot be changed after registration. Only address, phone and email can be updated.": {
        "vi": "🔒 Họ, Tên, Ngày sinh và Giới tính không thể sửa sau khi đã đăng ký. Chỉ Địa chỉ, SĐT và Email có thể cập nhật.",
        "en": "🔒 Name, date of birth and gender cannot be changed after registration. Only address, phone and email can be updated.",
        "ja": "🔒 登録後は氏名・生年月日・性別を変更できません。住所・電話番号・メールアドレスのみ更新可能です。",
    },
    "Missing Information": {"vi": "Thiếu thông tin", "en": "Missing Information", "ja": "情報が不足しています"},
    "Please fill in Employee Code, First Name and Last Name.": {
        "vi": "Vui lòng điền Mã nhân viên, Tên và Họ.",
        "en": "Please fill in Employee Code, First Name and Last Name.",
        "ja": "社員コード、名、姓を入力してください。",
    },

    # ------------------------------------------------------------------ #
    # ui/dialogs/face_capture_wizard_dialog.py
    # ------------------------------------------------------------------ #
    "Face Registration": {"vi": "Đăng ký khuôn mặt", "en": "Face Registration", "ja": "顔登録"},
    "Look straight at the camera": {"vi": "Nhìn thẳng vào camera", "en": "Look straight at the camera", "ja": "カメラをまっすぐ見てください"},
    "Turn your head LEFT": {"vi": "Xoay đầu sang TRÁI", "en": "Turn your head LEFT", "ja": "顔を左に向けてください"},
    "Turn your head RIGHT": {"vi": "Xoay đầu sang PHẢI", "en": "Turn your head RIGHT", "ja": "顔を右に向けてください"},
    "📸  Manual Capture": {"vi": "📸  Chụp thủ công", "en": "📸  Manual Capture", "ja": "📸  手動撮影"},
    "Cancel": {"vi": "Huỷ", "en": "Cancel", "ja": "キャンセル"},
    "Step {n}/{total}: {text}": {"vi": "Bước {n}/{total}: {text}", "en": "Step {n}/{total}: {text}", "ja": "ステップ {n}/{total}: {text}"},
    "Position your face in the frame": {
        "vi": "Đưa khuôn mặt vào khung hình",
        "en": "Position your face in the frame",
        "ja": "顔を枠内に合わせてください",
    },
    "Move closer to the camera": {"vi": "Lại gần camera hơn", "en": "Move closer to the camera", "ja": "カメラに近づいてください"},
    "Step back a little": {"vi": "Lùi lại một chút", "en": "Step back a little", "ja": "少し下がってください"},
    "Hold still...": {"vi": "Giữ yên...", "en": "Hold still...", "ja": "そのまま静止してください..."},
    "Hold still... ({n}/{total})": {
        "vi": "Giữ yên... ({n}/{total})",
        "en": "Hold still... ({n}/{total})",
        "ja": "そのまま静止してください... ({n}/{total})",
    },
    "Adjust your pose according to the instructions above": {
        "vi": "Chỉnh đúng tư thế theo hướng dẫn phía trên",
        "en": "Adjust your pose according to the instructions above",
        "ja": "上の指示に従って姿勢を調整してください",
    },
    "No face detected, try again.": {
        "vi": "Chưa phát hiện khuôn mặt, thử lại.",
        "en": "No face detected, try again.",
        "ja": "顔が検出されませんでした。もう一度お試しください。",
    },

    # ------------------------------------------------------------------ #
    # ui/ui_menu/widgets/camera_card.py + face_card.py
    # ------------------------------------------------------------------ #
    "Fullscreen": {"vi": "Phóng to", "en": "Fullscreen", "ja": "全画面表示"},
    "Exit Fullscreen": {"vi": "Thu nhỏ", "en": "Exit Fullscreen", "ja": "全画面表示を終了"},
    "✓ Match": {"vi": "✓ Khớp", "en": "✓ Match", "ja": "✓ 一致"},
    "?  Stranger": {"vi": "?  Người lạ", "en": "?  Stranger", "ja": "?  不審者"},

    # ------------------------------------------------------------------ #
    # core/camera_pipeline.py, core/device_manager.py, core/device_discovery.py
    # ------------------------------------------------------------------ #
    "Could not open video source: {source}": {
        "vi": "Không thể mở nguồn video: {source}",
        "en": "Could not open video source: {source}",
        "ja": "映像ソースを開けませんでした: {source}",
    },
    "Camera has no video source configured (IP/Stream URL/USB index).": {
        "vi": "Camera chưa cấu hình nguồn video (IP/Stream URL/USB index).",
        "en": "Camera has no video source configured (IP/Stream URL/USB index).",
        "ja": "カメラに映像ソースが設定されていません（IP/Stream URL/USBインデックス）。",
    },
    "Scanning USB cameras...": {"vi": "Đang quét camera USB...", "en": "Scanning USB cameras...", "ja": "USBカメラをスキャン中..."},
    "Scanning IP cameras on the LAN...": {
        "vi": "Đang quét camera IP trong mạng LAN...",
        "en": "Scanning IP cameras on the LAN...",
        "ja": "LAN内のIPカメラをスキャン中...",
    },
    "Could not determine the LAN subnet.": {
        "vi": "Không xác định được subnet mạng LAN.",
        "en": "Could not determine the LAN subnet.",
        "ja": "LANのサブネットを特定できませんでした。",
    },

    # ------------------------------------------------------------------ #
    # ui/dialogs/ai_settings_dialog.py
    # ------------------------------------------------------------------ #
    "AI Settings": {"vi": "Cài đặt AI", "en": "AI Settings", "ja": "AI設定"},
    "Applies immediately to every running camera - no restart needed.": {
        "vi": "Áp dụng ngay cho mọi camera đang chạy - không cần khởi động lại.",
        "en": "Applies immediately to every running camera - no restart needed.",
        "ja": "実行中のすべてのカメラに即座に適用されます - 再起動不要。",
    },
    "Detection Confidence": {"vi": "Ngưỡng nhận diện", "en": "Detection Confidence", "ja": "検出信頼度"},
    "Pose / Body": {"vi": "Dáng người / Body", "en": "Pose / Body", "ja": "姿勢推定 / Body"},
    "Detection threshold for body/pose (used by Fall - needs keypoints)": {
        "vi": "Ngưỡng nhận diện dáng người (dùng cho Té ngã - cần keypoints)",
        "en": "Detection threshold for body/pose (used by Fall - needs keypoints)",
        "ja": "姿勢検出の閾値（転倒検知で使用 - キーポイントが必要）",
    },
    "Detection threshold for head detection (count in/out, occupancy, PPE zone-check)": {
        "vi": "Ngưỡng nhận diện đầu người (đếm vào/ra, occupancy, kiểm tra vùng PPE)",
        "en": "Detection threshold for head detection (count in/out, occupancy, PPE zone-check)",
        "ja": "頭部検出の閾値（入退室カウント、occupancy、PPEゾーンチェック）",
    },
    "Detection threshold for vest/helmet": {
        "vi": "Ngưỡng nhận diện áo vest/mũ bảo hộ",
        "en": "Detection threshold for vest/helmet",
        "ja": "ベスト/ヘルメット検出の閾値",
    },
    "Detection threshold for fire/smoke (fire_detection_new.pt model)": {
        "vi": "Ngưỡng nhận diện cháy/khói (model fire_detection_new.pt)",
        "en": "Detection threshold for fire/smoke (fire_detection_new.pt model)",
        "ja": "火災/煙検出の閾値（fire_detection_new.ptモデル）",
    },
    "Detection threshold for fall pose (fall_detection_new.pt model)": {
        "vi": "Ngưỡng nhận diện tư thế té ngã (model fall_detection_new.pt)",
        "en": "Detection threshold for fall pose (fall_detection_new.pt model)",
        "ja": "転倒姿勢検出の閾値（fall_detection_new.ptモデル）",
    },
    "Fall Confirmation": {"vi": "Xác nhận té ngã", "en": "Fall Confirmation", "ja": "転倒の確認"},
    "Confirmation window (AI ticks)": {
        "vi": "Cửa sổ xác nhận (số lượt AI)",
        "en": "Confirmation window (AI ticks)",
        "ja": "確認ウィンドウ（AI回数）",
    },
    "Number of recent AI ticks kept to decide whether a fall is confirmed.": {
        "vi": "Số lượt AI gần nhất được giữ lại để quyết định có xác nhận té ngã hay không.",
        "en": "Number of recent AI ticks kept to decide whether a fall is confirmed.",
        "ja": "転倒を確定するかどうかを判断するために保持する直近のAI回数。",
    },
    "Min. falling ticks to confirm": {
        "vi": "Số lượt ngã tối thiểu để xác nhận",
        "en": "Min. falling ticks to confirm",
        "ja": "確定に必要な最小検知回数",
    },
    "Minimum number of \"falling\" ticks (within the window above) required before raising the Fall alert / drawing the Fall box.": {
        "vi": "Số lượt \"đang ngã\" tối thiểu (trong cửa sổ ở trên) cần có trước khi báo động Té ngã / vẽ khung Fall.",
        "en": "Minimum number of \"falling\" ticks (within the window above) required before raising the Fall alert / drawing the Fall box.",
        "ja": "転倒アラートを発報/転倒枠を描画する前に必要な、上記ウィンドウ内での最小「転倒中」検知回数。",
    },
    "Stranger Anti-Spam": {"vi": "Chống spam người lạ", "en": "Stranger Anti-Spam", "ja": "不審者スパム防止"},
    "Min. face quality to judge": {
        "vi": "Chất lượng mặt tối thiểu để đánh giá",
        "en": "Min. face quality to judge",
        "ja": "判定に必要な最小顔品質",
    },
    "Minimum face detection quality required before a face is even considered for the Stranger alert - "
    "blurry/far/low-confidence faces below this are ignored instead of being judged.": {
        "vi": "Chất lượng nhận diện khuôn mặt tối thiểu trước khi được xét vào cảnh báo Người lạ - mặt mờ/"
        "xa/độ tin cậy thấp dưới mức này sẽ được bỏ qua thay vì bị đánh giá.",
        "en": "Minimum face detection quality required before a face is even considered for the Stranger "
        "alert - blurry/far/low-confidence faces below this are ignored instead of being judged.",
        "ja": "不審者アラートの判定対象とする前に必要な最小顔検出品質 - これを下回るぼやけた/遠い/低信頼度の"
        "顔は判定されずに無視されます。",
    },
    "Max. similarity to confirm Stranger": {
        "vi": "Độ tương đồng tối đa để xác nhận Người lạ",
        "en": "Max. similarity to confirm Stranger",
        "ja": "不審者確定の最大類似度",
    },
    "Similarity must be at or below this value to confirm \"Stranger\". A face with some resemblance to a "
    "known person (above this, but below the match threshold) is treated as uncertain instead of Stranger - "
    "avoids false alerts for known people partly hidden by a mask/hair/bad angle. Lower this to reduce "
    "missed real strangers, raise it to reduce false Stranger alerts.": {
        "vi": "Similarity phải bằng hoặc thấp hơn giá trị này mới xác nhận \"Người lạ\". Mặt có nét giống 1 "
        "người quen (cao hơn mức này nhưng vẫn thấp hơn ngưỡng khớp) được coi là chưa chắc chắn thay vì "
        "Người lạ - tránh báo nhầm người quen bị khẩu trang/tóc/góc xấu che 1 phần. Hạ thấp giá trị này để "
        "giảm bỏ sót người lạ thật, tăng lên để giảm báo nhầm Người lạ.",
        "en": "Similarity must be at or below this value to confirm \"Stranger\". A face with some "
        "resemblance to a known person (above this, but below the match threshold) is treated as uncertain "
        "instead of Stranger - avoids false alerts for known people partly hidden by a mask/hair/bad angle. "
        "Lower this to reduce missed real strangers, raise it to reduce false Stranger alerts.",
        "ja": "「不審者」と確定するにはこの値以下である必要があります。既知の人物にある程度似ている顔（この"
        "値より高いが、一致閾値未満）は不審者ではなく不確実として扱われます - マスクや髪、悪い角度で一部隠"
        "れた既知の人物の誤警告を防ぎます。この値を下げると本物の不審者の見逃しが減り、上げると不審者の誤警"
        "告が減ります。",
    },
    "Min. face angle (straight-on)": {
        "vi": "Góc mặt tối thiểu (nhìn thẳng)",
        "en": "Min. face angle (straight-on)",
        "ja": "最小顔角度（正面向き）",
    },
    "How straight-on a face must be facing the camera before it can be judged Stranger. A turned/angled "
    "face - even if detected clearly - produces a less reliable face match, so it is treated as uncertain "
    "instead of Stranger until it turns to face the camera more directly. Lower this to accept more angled "
    "faces, raise it to require a more direct look.": {
        "vi": "Mặt phải nhìn thẳng vào camera ở mức nào mới được xét là Người lạ. Mặt quay nghiêng/xoay - dù "
        "vẫn được phát hiện rõ - cho ra kết quả khớp kém tin cậy hơn, nên được coi là chưa chắc chắn thay vì "
        "Người lạ cho tới khi họ quay lại nhìn thẳng camera hơn. Hạ thấp giá trị này để chấp nhận góc nghiêng "
        "nhiều hơn, tăng lên để yêu cầu nhìn thẳng hơn.",
        "en": "How straight-on a face must be facing the camera before it can be judged Stranger. A turned/"
        "angled face - even if detected clearly - produces a less reliable face match, so it is treated as "
        "uncertain instead of Stranger until it turns to face the camera more directly. Lower this to "
        "accept more angled faces, raise it to require a more direct look.",
        "ja": "不審者と判定する前に、顔がどれだけ正面を向いている必要があるか。顔を背けた/斜めの顔は、はっき"
        "り検出されていても顔の一致信頼度が下がるため、カメラの方をもっと直接向くまで不審者ではなく不確実と"
        "して扱われます。この値を下げるとより斜めの顔を許容し、上げるとより正面を向いた顔を必要とします。",
    },
    "Reset to Defaults": {"vi": "Khôi phục mặc định", "en": "Reset to Defaults", "ja": "デフォルトに戻す"},
}
