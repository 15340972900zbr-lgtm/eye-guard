from pathlib import Path

from eye_guard.windows import message, run

if __name__ == "__main__":
    try:
        run(Path(__file__).resolve().parent.parent / "assets")
    except Exception as error:
        message("护眼工具无法启动", f"{type(error).__name__}: {error}")
