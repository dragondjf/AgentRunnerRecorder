#!/usr/bin/env python3
"""
本地打包脚本 — 构建当前平台的二进制发布包。

用法:
    python build_release.py              # 自动检测平台，一键构建
    python build_release.py --cython     # 先 Cython 编译再 PyInstaller 打包
    python build_release.py --clean      # 构建前清理旧的 build/dist
    python build_release.py --skip-deps  # 跳过依赖安装（已装好时）
    python build_release.py -h           # 显示帮助

平台自动检测，输出产物:
    Windows  → AgentRunnerRecorder-Setup.exe
    macOS    → AgentRunnerRecorder-mac-arm64.zip
    Linux    → AgentRunnerRecorder-linux-x64.zip

等价于 GitHub Actions build.yml 的本地版本。
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
SPEC = ROOT / "recorder.spec"
REQUIREMENTS = ROOT / "requirements.txt"
REQUIREMENTS_WIN = ROOT / "requirements-windows.txt"


def run(cmd: list[str], **kwargs) -> None:
    """打印并执行命令。"""
    print(f"\n  \033[36m$\033[0m {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(ROOT), **kwargs)


def detect_platform() -> dict:
    """检测当前平台并返回构建参数。"""
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        return {
            "name": "win64",
            "artifact": "AgentRunnerRecorder-Setup.exe",
            "source_exe": "AgentRunnerRecorder.exe",
            "pack": "copy_exe",
        }
    elif system == "Darwin":
        return {
            "name": f"mac-{machine.replace('_', '')}",
            "artifact": f"AgentRunnerRecorder-mac-{machine.replace('_', '')}.zip",
            "source_exe": "AgentRunnerRecorder",
            "pack": "zip",
        }
    else:  # Linux
        return {
            "name": f"linux-{machine.replace('_', '')}",
            "artifact": f"AgentRunnerRecorder-linux-{machine.replace('_', '')}.zip",
            "source_exe": "AgentRunnerRecorder",
            "pack": "zip",
        }


def install_deps(plat: dict) -> None:
    """安装构建依赖。"""
    print("\n\033[1;34m[1/5] 安装依赖...\033[0m")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    if plat["name"] == "win64" and REQUIREMENTS_WIN.exists():
        run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_WIN)])


def check_linux_gui() -> None:
    """检查 Linux GUI 依赖（非 root 时仅警告）。"""
    if platform.system() != "Linux":
        return
    missing = []
    for lib in ["libgtk-3-0", "libxkbcommon-x11-0"]:
        try:
            subprocess.run(["ldconfig", "-p"], capture_output=True, timeout=5)
        except Exception:
            pass
    print("  \033[33m提示: Linux 请确保已安装 libgtk-3-0 libxkbcommon-x11-0 等 GUI 库\033[0m")


def build_cython() -> None:
    """Cython 编译 Python 源码（可选，加固反编译）。"""
    print("\n\033[1;34m[2/5] Cython 编译...\033[0m")

    # 确保 Cython 已安装
    try:
        import Cython
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "Cython"])

    run([sys.executable, "release.py", "build_ext"])


def build_pyinstaller() -> None:
    """PyInstaller 打包。"""
    print("\n\033[1;34m[3/5] PyInstaller 打包...\033[0m")
    run(["pyinstaller", "--noconfirm", str(SPEC)])


def package_output(plat: dict) -> Path:
    """封装产物。"""
    print("\n\033[1;34m[4/5] 封装产物...\033[0m")

    src = DIST / plat["source_exe"]
    if not src.exists():
        # macOS .app bundle
        src = DIST / f"{plat['source_exe']}.app"
    if not src.exists():
        raise FileNotFoundError(f"构建产物未找到: {src}")

    artifact_path = ROOT / plat["artifact"]

    if plat["pack"] == "copy_exe":
        # Windows: 直接复制
        shutil.copy2(src, artifact_path)
    else:
        # macOS / Linux: zip
        import zipfile
        with zipfile.ZipFile(artifact_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if src.is_dir():
                for f in src.rglob("*"):
                    zf.write(f, f.relative_to(DIST))
            else:
                zf.write(src, src.name)

    print(f"  \033[32m✓\033[0m {artifact_path}  ({_fmt_size(artifact_path.stat().st_size)})")
    return artifact_path


def clean() -> None:
    """清理旧的构建产物。"""
    for d in ["build", "dist"]:
        p = ROOT / d
        if p.exists():
            print(f"  \033[33m清理 {d}/\033[0m")
            shutil.rmtree(p)
    # 清理 Cython 生成的 .c 文件
    pattern_count = 0
    for ext in [".c", ".so", ".pyd"]:
        for f in ROOT.rglob(f"*{ext}"):
            if "site-packages" not in str(f) and ".venv" not in str(f):
                f.unlink()
                pattern_count += 1
    if pattern_count:
        print(f"  \033[33m已清理 {pattern_count} 个 Cython 产物\033[0m")


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


# ══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="AgentRunner Recorder — 本地跨平台打包脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python build_release.py                    # 一键构建
  python build_release.py --cython --clean   # 清理 + Cython + 打包
  python build_release.py --skip-deps        # 跳过依赖安装
        """,
    )
    parser.add_argument("--cython", action="store_true", help="先进行 Cython 编译再打包")
    parser.add_argument("--clean", action="store_true", help="构建前清理旧的 build/dist")
    parser.add_argument("--skip-deps", action="store_true", help="跳过依赖安装（已安装时）")
    args = parser.parse_args()

    # 检查 Python 版本
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"\033[1mAgentRunner Recorder 打包构建\033[0m")
    print(f"  Python  {py_ver}  |  {platform.system()} {platform.machine()}")

    plat = detect_platform()
    print(f"  目标平台  {plat['name']}")
    print(f"  输出产物  {plat['artifact']}")

    if args.clean:
        clean()

    if not args.skip_deps:
        install_deps(plat)

    check_linux_gui()

    if args.cython:
        build_cython()

    build_pyinstaller()

    artifact = package_output(plat)

    print(f"\n\033[1;32m══════════════════════════════════════\033[0m")
    print(f"\033[1;32m  ✓ 构建完成!\033[0m")
    print(f"\033[1;32m  {artifact}\033[0m")
    print(f"\033[1;32m══════════════════════════════════════\033[0m\n")


if __name__ == "__main__":
    main()
