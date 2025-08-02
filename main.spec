# -*- mode: python ; coding: utf-8 -*-

import os
import sys

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

# Get user home directory and construct conda environment path
user_home = os.path.expanduser("~")
conda_env_path = os.path.join(user_home, "anaconda3/envs/video")

print(f"Bundling ffmpeg from: {ffmpeg_path}")
print(f"Using conda environment: {conda_env_path}")

# First create the Analysis object
a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[
        (ffmpeg_path, '.'),  # 将 ffmpeg 放在 Contents/Frameworks 目录
        (f'{conda_env_path}/lib/python3.13/site-packages/mlx/lib/mlx.metallib', 'mlx'),
    ],
    datas=[
        (f'{conda_env_path}/lib/python3.13/site-packages/mlx', './mlx'),
    ],
    hiddenimports=["mlx", "mlx._reprlib_fix","mlx._os_warning"],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
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
    bundle_identifier='com.videocaptioner.app',
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
            'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:@executable_path:@executable_path/../Resources:@executable_path/Contents/MacOS'
        },
        'NSAppleEventsUsageDescription': 'This app needs access to keyboard events for shortcuts like Command+Q',
        'NSHumanReadableCopyright': 'Copyright © 2023',
        'NSPrincipalClass': 'NSApplication',
        'NSRequiresAquaSystemAppearance': 'No',
        'NSSupportsAutomaticGraphicsSwitching': True,
        'LSUIElement': False,
        'LSBackgroundOnly': False,
    },
)