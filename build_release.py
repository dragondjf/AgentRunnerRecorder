#!/usr/bin/env python3
"""
本地打包脚本 — 基于 make dist 产物构建二进制发布包。

用法:
    make dist                           # 先 Cython 编译出 dist/
    python build_release.py             # 安装依赖 → PyInstaller → zip
    python build_release.py --skip-deps # 跳过依赖安装
    python build_release.py --clean     # 构建前清理旧的 PyInstaller 产物

入口: dist/recorder_app.py (make dist 的编译产物)
输出: AgentRunnerRecorder-Setup.zip

所有依赖安装在 .venv/ 虚拟环境中。
"""

import argparse
import io
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

# 强制 UTF-8 输出,避免 Windows cp1252 / PowerShell 环境打印中文报错
if sys.platform == "win32":
    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name, None)
        if _stream is not None and hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    if not sys.stdout or not getattr(sys.stdout, "encoding", "") or sys.stdout.encoding.lower().startswith("cp"):
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).parent
VENV = ROOT / ".venv"
SPEC = ROOT / "recorder.spec"
REQUIREMENTS = ROOT / "requirements.txt"
REQUIREMENTS_WIN = ROOT / "requirements-windows.txt"

_is_windows = platform.system() == "Windows"

# 阿里云镜像
_PIP_MIRROR = "https://mirrors.aliyun.com/pypi/simple/"
_PIP_TRUSTED = "mirrors.aliyun.com"

# 子进程环境（UTF-8 + 清除代理）
_SUBPROCESS_ENV = {
    k: v for k, v in os.environ.items()
    if k.upper() not in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "SOCKS_PROXY",
                          "all_proxy", "http_proxy", "https_proxy", "socks_proxy")
}
_SUBPROCESS_ENV["PYTHONUTF8"] = "1"
_SUBPROCESS_ENV["PYTHONIOENCODING"] = "utf-8"
_SUBPROCESS_ENV["PREBUILT"] = "1"


# ══════════════════════════════════════════════════════════════════
def _venv_python() -> str:
    if _is_windows:
        return str(VENV / "Scripts" / "python.exe")
    return str(VENV / "bin" / "python3")


def setup_venv() -> str:
    python = _venv_python()
    if not VENV.is_dir():
        print("\n\033[1;34m创建虚拟环境 .venv/ ...\033[0m")
        venv.create(VENV, with_pip=True)
        print(f"  \033[32m✓\033[0m {VENV}")
    return python


def run(cmd: list[str], **kwargs) -> None:
    print(f"\n  \033[36m$\033[0m {' '.join(cmd)}")
    env = kwargs.pop("env", _SUBPROCESS_ENV)
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env, **kwargs)


def _pip(python: str, *args: str) -> None:
    run([python, "-m", "pip", "install",
         "-i", _PIP_MIRROR, "--trusted-host", _PIP_TRUSTED,
         *args])


def detect_platform() -> dict:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Windows":
        return {"name": "win64", "artifact": "AgentRunnerRecorder-Setup.zip"}
    elif system == "Darwin":
        return {"name": f"mac-{machine.replace('_', '')}",
                "artifact": f"AgentRunnerRecorder-mac-{machine.replace('_', '')}.zip"}
    else:
        return {"name": f"linux-{machine.replace('_', '')}",
                "artifact": f"AgentRunnerRecorder-linux-{machine.replace('_', '')}.zip"}


# ══════════════════════════════════════════════════════════════════
def install_deps(python: str, plat: dict) -> None:
    print("\n\033[1;34m[1/3] 安装依赖 (venv)...\033[0m")
    try:
        _pip(python, "--upgrade", "pip", "--proxy", "")
    except Exception:
        pass
    _pip(python, "-r", str(REQUIREMENTS), "--proxy", "")
    _pip(python, "pyinstaller", "--proxy", "")
    if plat["name"] == "win64" and REQUIREMENTS_WIN.exists():
        _pip(python, "-r", str(REQUIREMENTS_WIN), "--proxy", "")


def build_pyinstaller(python: str) -> None:
    print("\n\033[1;34m[2/3] PyInstaller 打包 (dist/ 编译产物)...\033[0m")
    run([python, "-m", "PyInstaller", "--noconfirm", str(SPEC)])


def _ensure_win7_dll(src_dir: Path) -> None:
    """将 api-ms-win-core-path-l1-1-0.dll 复制到 _internal 目录。

    Python 3.9+ 内部依赖此 API Set DLL，Windows 7 缺少该文件。
    """
    dll_name = "api-ms-win-core-path-l1-1-0.dll"
    internal_dir = src_dir / "_internal"
    target = internal_dir / dll_name
    if target.exists():
        return
    source = ROOT / "dlls" / dll_name
    if source.exists():
        shutil.copy2(source, target)
        print(f"  \033[32m✓\033[0m {dll_name} → _internal/ (Win7 compat)")
    else:
        print(f"  \033[33m⚠ dlls/{dll_name} 不存在，Win7 可能无法启动\033[0m")


def package_output(plat: dict) -> Path:
    print("\n\033[1;34m[3/3] 封装产物...\033[0m")
    src_dir = ROOT / "dist" / "AgentRunnerRecorder"
    if not src_dir.is_dir():
        raise FileNotFoundError(f"构建产物未找到: {src_dir}")

    # 复制 requirements 到 _internal/
    internal_dir = src_dir / "_internal"
    for req_file in [REQUIREMENTS, REQUIREMENTS_WIN]:
        if req_file.exists():
            shutil.copy2(req_file, internal_dir / req_file.name)
            print(f"  \033[36m+\033[0m {req_file.name} → _internal/")

    # Win7 兼容 DLL
    if plat["name"] == "win64":
        _ensure_win7_dll(src_dir)

    artifact_path = ROOT / plat["artifact"]
    import zipfile
    with zipfile.ZipFile(artifact_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(src_dir.parent))

    print(f"  \033[32m✓\033[0m {artifact_path}  ({_fmt_size(artifact_path.stat().st_size)})")
    return artifact_path


def clean() -> None:
    for d in ["build", "dist"]:
        p = ROOT / d
        if p.exists():
            print(f"  \033[33m清理 {d}/\033[0m")
            shutil.rmtree(p)


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


# ══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="AgentRunner Recorder — 打包脚本")
    parser.add_argument("--clean", action="store_true", help="构建前清理旧的 dist/ build/")
    parser.add_argument("--skip-deps", action="store_true", help="跳过依赖安装")
    args = parser.parse_args()

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"\033[1mAgentRunner Recorder 打包构建\033[0m")
    print(f"  Python  {py_ver}  |  {platform.system()} {platform.machine()}")

    # 检查 dist/ 产物
    if not (ROOT / "dist" / "recorder_app.py").exists():
        print("\033[31m错误: dist/recorder_app.py 不存在，请先执行 make dist\033[0m")
        sys.exit(1)

    # 创建/复用 venv
    python = setup_venv()
    print(f"  venv    {VENV}")

    plat = detect_platform()
    print(f"  目标  {plat['name']}  →  {plat['artifact']}")

    if args.clean:
        clean()

    if not args.skip_deps:
        install_deps(python, plat)

    build_pyinstaller(python)

    artifact = package_output(plat)

    print(f"\n\033[1;32m══════════════════════════════════════\033[0m")
    print(f"\033[1;32m  ✓ 构建完成!\033[0m")
    print(f"\033[1;32m  {artifact}\033[0m")
    print(f"\033[1;32m══════════════════════════════════════\033[0m\n")


if __name__ == "__main__":
    main()
