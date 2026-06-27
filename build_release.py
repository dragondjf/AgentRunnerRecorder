#!/usr/bin/env python3
"""
本地打包脚本 — 构建当前平台的二进制发布包。

用法:
    python build_release.py              # 自动创建 .venv，一键构建
    python build_release.py --cython     # 先 Cython 编译再 PyInstaller 打包
    python build_release.py --clean      # 构建前清理旧的 build/dist
    python build_release.py --skip-deps  # 跳过依赖安装（已装好时）
    python build_release.py -h           # 显示帮助

所有依赖安装在 .venv/ 虚拟环境中，不污染系统 Python。

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
import venv
from pathlib import Path

ROOT = Path(__file__).parent
VENV = ROOT / ".venv"
DIST = ROOT / "dist"
SPEC = ROOT / "recorder.spec"
REQUIREMENTS = ROOT / "requirements.txt"
REQUIREMENTS_WIN = ROOT / "requirements-windows.txt"

_is_windows = platform.system() == "Windows"

# 阿里云镜像 + trusted-host（解决 venv 内 SSL 证书问题）
_PIP_MIRROR = "https://mirrors.aliyun.com/pypi/simple/"
_PIP_TRUSTED = "mirrors.aliyun.com"

# 子进程环境变量（修复 Windows GBK 无法解码 UTF-8 中文问题 + 清除 SOCKS 代理）
_SUBPROCESS_ENV = {
    k: v for k, v in os.environ.items()
    if k.upper() not in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "SOCKS_PROXY",
                          "all_proxy", "http_proxy", "https_proxy", "socks_proxy")
}
_SUBPROCESS_ENV["PYTHONUTF8"] = "1"
_SUBPROCESS_ENV["PYTHONIOENCODING"] = "utf-8"


def _venv_python() -> str:
    """返回 .venv 中的 python 路径。"""
    if _is_windows:
        return str(VENV / "Scripts" / "python.exe")
    return str(VENV / "bin" / "python3")


def setup_venv() -> str:
    """创建虚拟环境（首次），返回 python 路径。"""
    python = _venv_python()
    if not VENV.is_dir():
        print("\n\033[1;34m创建虚拟环境 .venv/ ...\033[0m")
        venv.create(VENV, with_pip=True)
        print(f"  \033[32m✓\033[0m {VENV}")
    return python


def run(cmd: list[str], **kwargs) -> None:
    """打印并执行命令（使用 venv python + UTF-8 环境）。"""
    print(f"\n  \033[36m$\033[0m {' '.join(cmd)}")
    env = kwargs.pop("env", None) or _SUBPROCESS_ENV
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env, **kwargs)


def _pip(python: str, *args: str) -> None:
    """在 venv 中执行 pip install，自动加阿里源 + trusted-host。"""
    run([python, "-m", "pip", "install",
         "-i", _PIP_MIRROR, "--trusted-host", _PIP_TRUSTED,
         *args])


def detect_platform() -> dict:
    """检测当前平台并返回构建参数。"""
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        return {
            "name": "win64",
            "artifact": "AgentRunnerRecorder-Setup.zip",
            "pack": "zip",
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


def install_deps(python: str, plat: dict) -> None:
    """在 venv 中安装构建依赖（阿里源）。"""
    print("\n\033[1;34m[1/5] 安装依赖 (venv)...\033[0m")
    # pip --upgrade 可能因 SOCKS 代理失败，非关键操作加 try
    try:
        _pip(python, "--upgrade", "pip", "--proxy", "")
    except Exception:
        pass
    _pip(python, "-r", str(REQUIREMENTS), "--proxy", "")
    _pip(python, "pyinstaller", "--proxy", "")

    if plat["name"] == "win64" and REQUIREMENTS_WIN.exists():
        _pip(python, "-r", str(REQUIREMENTS_WIN), "--proxy", "")


def check_linux_gui() -> None:
    """检查 Linux GUI 依赖（非 root 时仅警告）。"""
    if platform.system() != "Linux":
        return
    print("  \033[33m提示: Linux 请确保已安装 libgtk-3-0 libxkbcommon-x11-0 等 GUI 库\033[0m")


def build_cython(python: str) -> None:
    """Cython 编译 Python 源码（可选，加固反编译）。"""
    print("\n\033[1;34m[2/5] Cython 编译...\033[0m")
    _pip(python, "Cython", "--proxy", "")
    run([python, "release.py", "build_ext"])


def build_pyinstaller(python: str) -> None:
    """PyInstaller 打包。"""
    print("\n\033[1;34m[3/5] PyInstaller 打包...\033[0m")
    run([python, "-m", "PyInstaller", "--noconfirm", str(SPEC)])


def package_output(plat: dict) -> Path:
    """封装产物 — onedir 模式打包整个 dist/AgentRunnerRecorder/ 为 zip。"""
    print("\n\033[1;34m[4/5] 封装产物...\033[0m")

    src_dir = DIST / "AgentRunnerRecorder"  # onedir 输出目录
    if not src_dir.is_dir():
        raise FileNotFoundError(f"构建产物未找到: {src_dir}")

    artifact_path = ROOT / plat["artifact"].replace(".exe", ".zip")

    if plat["pack"] == "copy_exe":
        # Windows: 仍保留单体 .exe 命名习惯，实际打包为 zip
        import zipfile
        with zipfile.ZipFile(artifact_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in src_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(src_dir.parent))
    else:
        # macOS / Linux: 同上
        import zipfile
        with zipfile.ZipFile(artifact_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in src_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(src_dir.parent))

    print(f"  \033[32m✓\033[0m {artifact_path}  ({_fmt_size(artifact_path.stat().st_size)})")
    return artifact_path


def clean() -> None:
    """清理旧的构建产物（保留 .venv）。"""
    for d in ["build", "dist"]:
        p = ROOT / d
        if p.exists():
            print(f"  \033[33m清理 {d}/\033[0m")
            shutil.rmtree(p)
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
  python build_release.py                    # 自动创建 .venv 并一键构建
  python build_release.py --cython --clean   # 清理 + Cython + 打包
  python build_release.py --skip-deps        # 跳过依赖安装
        """,
    )
    parser.add_argument("--cython", action="store_true", help="先 Cython 编译再打包")
    parser.add_argument("--clean", action="store_true", help="构建前清理旧的 build/dist")
    parser.add_argument("--skip-deps", action="store_true", help="跳过依赖安装（已装好时）")
    args = parser.parse_args()

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"\033[1mAgentRunner Recorder 打包构建\033[0m")
    print(f"  Python  {py_ver}  |  {platform.system()} {platform.machine()}")

    # 创建/复用虚拟环境
    python = setup_venv()
    print(f"  venv    {VENV}")

    plat = detect_platform()
    print(f"  目标平台  {plat['name']}")
    print(f"  输出产物  {plat['artifact']}")

    if args.clean:
        clean()

    if not args.skip_deps:
        install_deps(python, plat)

    check_linux_gui()

    if args.cython:
        build_cython(python)

    build_pyinstaller(python)

    artifact = package_output(plat)

    print(f"\n\033[1;32m══════════════════════════════════════\033[0m")
    print(f"\033[1;32m  ✓ 构建完成!\033[0m")
    print(f"\033[1;32m  {artifact}\033[0m")
    print(f"\033[1;32m══════════════════════════════════════\033[0m\n")


if __name__ == "__main__":
    main()
