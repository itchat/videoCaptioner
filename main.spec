# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs

def get_ffmpeg_path():
    possible_paths = [
        '/opt/homebrew/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        '/usr/bin/ffmpeg',
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

ffmpeg_path = get_ffmpeg_path()
if not ffmpeg_path:
    raise FileNotFoundError("Could not find ffmpeg. Please install it first.")

# First create the Analysis object
a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[
        (ffmpeg_path, 'Contents/MacOS'),
    ],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='videoCaptioner'
)

app = BUNDLE(
    coll,
    name='videoCaptioner.app',
    bundle_identifier=None,
    icon='icons/translate.icns',
    info_plist={
        'NSHighResolutionCapable': 'True',
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'Video',
                'CFBundleTypeRole': 'Viewer',
                'LSHandlerRank': 'Owner',
                'LSItemContentTypes': [
                    'public.movie',
                    'public.video',
                ],
            }
        ],
        'LSEnvironment': {
            'PATH': '@executable_path:@executable_path/../Resources:@executable_path/Contents/MacOS:/usr/local/bin:/usr/bin:/bin'
        },
    },
)