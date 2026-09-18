import os
import sys

if sys.platform == 'win32':
    if hasattr(sys, '_MEIPASS'):
        meipass = sys._MEIPASS
        candidates = [
            meipass,
            os.path.join(meipass, 'numpy.libs'),
            os.path.join(meipass, 'PyQt6', 'Qt6', 'bin'),
        ]
        for c in candidates:
            if os.path.isdir(c):
                try:
                    os.add_dll_directory(c)
                except Exception:
                    pass
        os.environ['PATH'] = ';'.join(candidates) + ';' + os.environ.get('PATH', '')
