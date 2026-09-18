# -*- mode: python ; coding: utf-8 -*-

import os
import glob
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [('assets', 'assets')]
datas += collect_data_files('imageio_ffmpeg')

# Explicitly collect numpy, OpenBLAS, and MSVC runtime DLLs to root '.' and subdirectories
binaries = []
try:
    import numpy
    numpy_dir = os.path.dirname(numpy.__file__)
    for d in [
        os.path.join(numpy_dir, os.pardir, 'numpy.libs'),
        os.path.join(numpy_dir, '.libs'),
        os.path.join(numpy_dir, 'libs'),
    ]:
        if os.path.isdir(d):
            for dll in glob.glob(os.path.join(d, '*.dll')):
                binaries.append((dll, '.'))
                binaries.append((dll, 'numpy.libs'))
except Exception as e:
    print(f"[Spec] Note collecting numpy libs: {e}")

try:
    import PyQt6
    pyqt_dir = os.path.dirname(PyQt6.__file__)
    qt_bin = os.path.join(pyqt_dir, 'Qt6', 'bin')
    if os.path.isdir(qt_bin):
        for dll_name in ['MSVCP140.dll', 'MSVCP140_1.dll', 'MSVCP140_2.dll', 'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll']:
            p = os.path.join(qt_bin, dll_name)
            if os.path.isfile(p):
                binaries.append((p, '.'))
except Exception as e:
    print(f"[Spec] Note collecting PyQt MSVC libs: {e}")

hiddenimports = [
    'core.i18n',
    'core.mic_repeater',
    'core.ptt_controller',
    'core.app_router',
    'core.app_capture',
    'imageio_ffmpeg',
    'yt_dlp',
    'edge_tts',
    'qfluentwidgets',
    'qframelesswindow',
    'miniaudio',
    'sounddevice',
    'numpy',
    'pycaw',
    'comtypes',
    'psutil'
]

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hooks/rthook_dll_search.py'],
    excludes=['scipy', 'pedalboard', 'tkinter', 'matplotlib', 'pydoc', 'unittest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

version_file = 'assets/version_info.txt' if os.path.exists('assets/version_info.txt') else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SoundFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\app_icon.ico'],
    version=version_file,
)
