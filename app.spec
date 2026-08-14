# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec cho APP_CAMERA_AI_ATTENDANCE.

Dung --onedir (khong phai --onefile): torch+CUDA/onnxruntime-gpu/opencv rat
nang (vai GB) - --onefile se giai nen lai TOAN BO vao thu muc tam moi lan mo
app (cham, ton dia). --onedir copy 1 lan, mo app gan nhu ngay lap tuc.

Build: venv\\Scripts\\pyinstaller.exe app.spec
Ket qua: dist\\APP_CAMERA_AI_ATTENDANCE\\APP_CAMERA_AI_ATTENDANCE.exe
"""
from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = [
    # Nguyen thu muc ui/ (anh, .qss theme, .ui, resource.qrc) - Theme
    # Manager/uic.loadUi doc thang tu dia theo duong dan tuong doi BASE_DIR,
    # thieu file nao trong nay la crash ngay luc khoi dong (da gap
    # ui/themes/*.qss lan build dau). Copy ca .py cung khong sao, chi du.
    ("ui", "ui"),
    ("config", "config"),
    ("process/models", "process/models"),
    ("core/deep_sort_pytorch/configs", "core/deep_sort_pytorch/configs"),
    ("core/deep_sort_pytorch/deep_sort/deep/checkpoint", "core/deep_sort_pytorch/deep_sort/deep/checkpoint"),
]
binaries = []
hiddenimports = []

# collect_all cho cac package "kho" voi static analysis cua PyInstaller (dynamic
# import qua pkgutil/registry - ultralytics, insightface, onnx2torch - hoac
# nhieu binary/data phu nhu torch, torchvision, onnxruntime-gpu, opencv). An
# toan hon la thieu mat 1 submodule roi phai build lai nhieu lan.
for pkg in [
    "torch",
    "torchvision",
    "onnxruntime",
    "onnx",
    "onnx2torch",
    "insightface",
    "ultralytics",
    "cv2",
    "scipy",
    "skimage",
]:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

hiddenimports += [
    "PyQt6.QtPrintSupport",
    "easydict",
    "yaml",
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="APP_CAMERA_AI_ATTENDANCE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="APP_CAMERA_AI_ATTENDANCE",
)
