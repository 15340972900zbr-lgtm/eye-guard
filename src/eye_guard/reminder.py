"""提醒交互：macOS 系统通知（osascript），不抢占前台焦点。

通知通过单工作线程异步派发：osascript 最长可阻塞数秒，绝不能卡住
菜单栏主线程。仅使用本地通知，不涉及任何网络请求。
"""

import contextlib
import subprocess
from concurrent.futures import ThreadPoolExecutor

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="eye-guard-notify")


def notification_script(title: str, message: str, sound: bool = False) -> str:
    """构造 osascript 的 display notification 脚本（纯函数，可测试）。"""

    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')

    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    if sound:
        script += ' sound name "Submarine"'
    return script


def _send(script: str) -> None:
    """在工作线程中执行 osascript；失败静默（提醒通道不可用不影响监控）。"""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            timeout=5,
            capture_output=True,
        )


def notify(title: str, message: str, sound: bool = True) -> None:
    """异步发送系统通知，立即返回，不阻塞调用线程。"""
    _EXECUTOR.submit(_send, notification_script(title, message, sound=sound))
