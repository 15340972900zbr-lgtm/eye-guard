import os
import shutil
import subprocess
from ctypes import WinDLL, c_int, c_void_p, c_wchar_p, get_last_error
from pathlib import Path
from threading import Event

from .config import Config, load_config
from .monitor import Monitor


def message(title: str, text: str) -> None:
    user32 = WinDLL("user32")
    user32.MessageBoxW.argtypes = [c_void_p, c_wchar_p, c_wchar_p, c_int]
    user32.MessageBoxW(None, text, title, 0)


def summary(mode, reading, window: float) -> str:
    if reading.blink_rate is None:
        rate = f"采样 {int(reading.sample_seconds)}/{window:g} 秒" if reading.present else "等待人脸"
    else:
        rate = f"{reading.blink_rate:.0f} 次/分"
    seconds = int(reading.active_seconds)
    scale = f"{reading.face_scale:.2f}" if reading.face_scale is not None else "未校准"
    if reading.calibrating:
        scale = "校准中"
    return (
        f"护眼工具 · {mode}\n"
        f"眨眼 {reading.blink_total} 次 · {rate}\n"
        f"连续用眼 {seconds // 60}分{seconds % 60:02d}秒 · 距离指数 {scale}"
    )


def run(assets: Path) -> None:
    import pystray
    from PIL import Image

    kernel = WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [c_void_p, c_int, c_wchar_p]
    kernel.CreateMutexW.restype = c_void_p
    kernel.CloseHandle.argtypes = [c_void_p]
    instance = kernel.CreateMutexW(None, False, "Local\\EyeGuardWindows")
    already_running = get_last_error() == 183
    if not instance:
        raise OSError("无法创建应用实例")
    if already_running:
        kernel.CloseHandle(instance)
        message("护眼工具", "护眼工具已在运行。请在任务栏右下角查找眼睛图标。")
        return

    monitor = None
    stopping = Event()
    try:
        config_path = Path(os.environ["LOCALAPPDATA"]) / "EyeGuard" / "config.toml"
        try:
            config = load_config(config_path)
        except (ValueError, OSError) as exc:
            message("护眼工具 · 配置", f"配置有误，本次使用默认设置。\n{exc}")
            config = Config()
        monitor = Monitor(config, assets / "face_landmarker.task")

        def edit_config(_icon, _item):
            config_path.parent.mkdir(parents=True, exist_ok=True)
            if not config_path.exists():
                shutil.copyfile(assets / "config.example.toml", config_path)
            notepad = Path(os.environ["SystemRoot"]) / "System32" / "notepad.exe"
            subprocess.Popen([str(notepad), str(config_path)])

        def show(_icon, _item):
            message("护眼工具 · 状态", _icon.title)

        def quit_app(icon, _item):
            stopping.set()
            icon.stop()

        def setup(icon):
            icon.visible = True
            while not stopping.is_set():
                mode, reading, notices = monitor.snapshot()
                text = summary(mode, reading, config.blink_window_s)
                if icon.title != text:
                    icon.title = text
                for kind, detail in notices:
                    title = "护眼工具" if kind in {"calibrated", "calibration", "error"} else "护眼提醒"
                    if icon.HAS_NOTIFICATION:
                        icon.notify(detail, title)
                stopping.wait(0.4)

        menu = pystray.Menu(
            pystray.MenuItem("查看当前统计", show, default=True),
            pystray.MenuItem("启动 / 恢复监控", lambda _icon, _item: monitor.start()),
            pystray.MenuItem("暂停监控", lambda _icon, _item: monitor.pause()),
            pystray.MenuItem("校准距离", lambda _icon, _item: monitor.calibrate()),
            pystray.MenuItem("重置统计", lambda _icon, _item: monitor.reset()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("编辑配置（重启后应用）", edit_config),
            pystray.MenuItem("退出", quit_app),
        )
        with Image.open(assets / "eye.ico") as source:
            icon = pystray.Icon("EyeGuard", source.convert("RGBA"), "护眼工具", menu)
        icon.run(setup=setup)
    finally:
        stopping.set()
        if monitor is not None:
            monitor.close()
        kernel.CloseHandle(instance)
