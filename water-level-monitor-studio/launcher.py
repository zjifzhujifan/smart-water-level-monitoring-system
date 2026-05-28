from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"


def run_check(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
    except Exception as exc:
        return False, str(exc)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def main() -> int:
    if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve())])

    ok, output = run_check([sys.executable, "-m", "compileall", "app", "run.py"])
    if not ok:
        print("启动前检查失败：代码无法编译")
        print(output)
        return 1

    ok, output = run_check([sys.executable, "-m", "pip", "check"])
    if not ok:
        print("依赖检查存在问题：")
        print(output)
        return 1

    from app.main import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
