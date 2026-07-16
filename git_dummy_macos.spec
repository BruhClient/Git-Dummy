# -*- mode: python ; coding: utf-8 -*-
import os
import qtawesome

# PyInstaller exec()s this spec without the repo root on sys.path, so a plain
# `import version` fails in CI — read it directly relative to the spec file.
_version_ns = {}
with open(os.path.join(SPECPATH, 'version.py')) as _f:
    exec(_f.read(), _version_ns)
__version__ = _version_ns['__version__']

block_cipher = None

qta_dir = os.path.dirname(qtawesome.__file__)
qta_fonts = os.path.join(qta_dir, 'fonts')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('fonts', 'fonts'),
        ('logo', 'logo'),
        (qta_fonts, os.path.join('qtawesome', 'fonts')),
    ],
    hiddenimports=[
        'git',
        'git.cmd',
        'git.repo',
        'git.repo.base',
        'git.exc',
        'qtawesome',
        'PyQt5.sip',
        'PyQt5.QtSvg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt5.QtWebEngine',
        'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebEngineCore',
        'PyQt5.QtQml',
        'PyQt5.QtQuick',
        'PyQt5.QtQuickWidgets',
        'PyQt5.QtBluetooth',
        'PyQt5.QtNfc',
        'PyQt5.QtLocation',
        'PyQt5.QtMultimedia',
        'PyQt5.QtMultimediaWidgets',
        'PyQt5.QtSensors',
        'PyQt5.QtSerialPort',
        'PyQt5.QtSql',
        'PyQt5.QtTest',
        'PyQt5.QtXml',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GitDummy',
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
    icon='logo/logo.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='GitDummy',
)

app = BUNDLE(
    coll,
    name='GitDummy.app',
    icon='logo/logo.icns',
    bundle_identifier='com.gitdummy.app',
    info_plist={
        'CFBundleDisplayName': 'Git Dummy',
        'CFBundleShortVersionString': __version__,
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
    },
)
