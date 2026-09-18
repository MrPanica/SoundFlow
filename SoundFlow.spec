# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [('assets', 'assets')]
datas += collect_data_files('imageio_ffmpeg')

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
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy', 'pedalboard', 'tkinter', 'matplotlib', 'pydoc', 'unittest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

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
)
