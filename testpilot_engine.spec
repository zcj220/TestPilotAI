# -*- mode: python ; coding: utf-8 -*-
"""
TestPilot AI 引擎打包配置
用法: poetry run pyinstaller testpilot_engine.spec
"""

import os
import sys
from pathlib import Path

# ── 基本路径 ──────────────────────────────────────────────────
project_dir = Path(SPECPATH)

# 跨平台查找 site-packages：
#   Windows: .venv/lib/site-packages
#   macOS/Linux: .venv/lib/python3.x/site-packages
import sysconfig
venv_site_packages = Path(sysconfig.get_path('purelib'))

# ── 需要随二进制一起携带的数据目录 ────────────────────────────
datas = [
    # playwright driver（含 node.exe 和 package/）
    (str(venv_site_packages / 'playwright' / 'driver'), 'playwright/driver'),
    # alembic 迁移脚本（数据库升级用）
    (str(project_dir / 'alembic'), 'alembic'),
    # alembic.ini
    (str(project_dir / 'alembic.ini'), '.'),
    # 小程序 JS 脚本（BUNDLE_DIR/controller/ 下可找到）
    (str(project_dir / 'src' / 'controller' / 'miniprogram_runner.js'), 'controller'),
    (str(project_dir / 'src' / 'controller' / 'miniprogram_bridge_server.js'), 'controller'),
]

# ── 隐式导入（动态加载的模块，分析器找不到）────────────────────
hiddenimports = [
    # FastAPI / Starlette
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.loops.uvloop',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.websockets_impl',
    'uvicorn.protocols.websockets.wsproto_impl',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'starlette.routing',
    'starlette.middleware',
    'starlette.middleware.cors',
    # Playwright
    'playwright',
    'playwright.sync_api',
    'playwright.async_api',
    # SQLAlchemy
    'sqlalchemy.dialects.sqlite',
    # jose
    'jose',
    'jose.jwt',
    # multipart
    'multipart',
    # email_validator (fastapi opt-dep)
    'email_validator',
    # passlib
    'passlib.handlers.bcrypt',
    'passlib.handlers.sha2_crypt',
    # websockets
    'websockets',
    'websockets.legacy',
    'websockets.legacy.server',
]

a = Analysis(
    ['main.py'],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除用不到的大型包，减小体积
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'IPython',
        'notebook',
        'pytest',
        'sphinx',
    ],
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
    name='testpilot-engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,         # UPX 压缩在某些杀毒软件中会误报，关闭
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,      # 保留控制台，方便用户看启动日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 图标（可选，后续替换为实际 .ico 文件）
    # icon='resources/icon.ico',
)
