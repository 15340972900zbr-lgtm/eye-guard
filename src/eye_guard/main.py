"""菜单栏应用入口：启动/暂停/退出、距离校准、状态刷新与提醒派发。

提醒通过系统通知（osascript）发出，不抢占前台焦点。
"""

from pathlib import Path

import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

from eye_guard.camera import OpenCVCamera
from eye_guard.config import EyeGuardConfig, load_config
from eye_guard.monitor import Monitor, MonitorSnapshot, Reminder, ReminderKind
from eye_guard.posture import PostureCalibration, PostureState
from eye_guard.reminder import notify
from eye_guard.vision import FaceLandmarkerEngine

MENU_BAR_ICON = Path(__file__).with_name("menu-bar-eye.pdf")


def format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}分{secs:02d}秒"


def format_status(snap: MonitorSnapshot) -> str:
    face = "检测中" if snap.face_present else "未检测到人脸"
    prox = f"{snap.proximity:.2f}" if snap.proximity is not None else "未校准"
    return (
        f"{face}｜眨眼 {snap.blink_total} 次（{snap.blink_rate_per_min:.0f} 次/分）"
        f"｜连续 {format_duration(snap.continuous_s)}"
        f"｜累计 {format_duration(snap.total_s)}｜距离 {prox}"
    )


def format_reminder(r: Reminder) -> tuple[str, str]:
    if r.message:
        return ("坐姿提醒" if r.kind is ReminderKind.POSTURE else "护眼", r.message)
    match r.kind:
        case ReminderKind.CONTINUOUS_LIMIT:
            return ("护眼提醒", f"已连续用眼 {r.value:.0f} 分钟，建议起身远眺休息。")
        case ReminderKind.TOO_CLOSE:
            return ("护眼提醒", f"距离屏幕过近（相对值 {r.value:.2f}），请适当后移。")
        case ReminderKind.TOO_FAR:
            return ("护眼提醒", f"距离屏幕过远（相对值 {r.value:.2f}），请适当靠近。")
        case ReminderKind.BLINK_RATE_LOW:
            return ("护眼提醒", f"眨眼频率偏低（{r.value:.0f} 次/分），请有意识多眨眼、适当休息。")
        case ReminderKind.CALIBRATED:
            return ("护眼", f"距离校准完成，基准人脸占比 {r.value:.3f}。")
        case ReminderKind.CAMERA_ERROR:
            return ("护眼", "监控出现问题，已自动暂停，可点击「恢复监控」重试。")
        case ReminderKind.POSTURE:
            return ("坐姿提醒", "坐直一点，放松肩膀。")


def format_posture_status(state: PostureState) -> str:
    if state.calibration is not None:
        phase = "坐直" if state.calibration is PostureCalibration.UPRIGHT else "前倾界线"
        progress = "请让双耳、双肩入镜" if state.since is None else "保持当前姿势"
        return f"正在校准{phase} · {progress}"
    if state.limit is None:
        return "待校准前倾界线" if state.upright_max is not None else "未开启"
    if state.leaning is None:
        return "请让双耳、双肩入镜"
    return "头部前伸" if state.leaning else "在校准范围内"


class EyeGuardApp(rumps.App):
    def __init__(self, config: EyeGuardConfig) -> None:
        super().__init__("护眼", icon=str(MENU_BAR_ICON), template=True, quit_button=None)
        self._config = config
        try:
            engine = FaceLandmarkerEngine(config.model_path)
        except FileNotFoundError:
            engine = None
        self._monitor = Monitor(OpenCVCamera(), engine, config)

        self._toggle = rumps.MenuItem("启动监控", callback=self._on_toggle)
        self._calibrate = rumps.MenuItem(
            "校准距离（保持当前坐姿约 3 秒）", callback=self._on_calibrate
        )
        self._reset = rumps.MenuItem("重置统计", callback=self._on_reset)
        self._status = rumps.MenuItem("状态：未启动", callback=lambda _sender: None)
        self._posture_status = rumps.MenuItem("当前：未开启")
        posture_menu = rumps.MenuItem("坐姿提醒")
        posture_menu.update(
            [
                self._posture_status,
                None,
                rumps.MenuItem("① 校准坐直姿势", callback=self._on_posture_upright),
                rumps.MenuItem("② 校准前倾提醒界线", callback=self._on_posture_limit),
                rumps.MenuItem("关闭并清除坐姿校准", callback=self._on_posture_disable),
            ]
        )
        quit_item = rumps.MenuItem("退出", callback=self._on_quit)
        self.menu = [
            self._toggle,
            self._calibrate,
            posture_menu,
            self._reset,
            None,
            self._status,
            None,
            quit_item,
        ]

        self._timer = rumps.Timer(self._on_tick, 1)
        self._timer.start()

    def _on_toggle(self, _sender: rumps.MenuItem) -> None:
        if not self._monitor.is_started():
            try:
                self._monitor.start()
            except RuntimeError as exc:
                notify("护眼", str(exc))
                return
            self._toggle.title = "暂停监控"
        elif self._monitor.is_paused():
            self._monitor.resume()
            self._toggle.title = "暂停监控"
        else:
            self._monitor.pause()
            self._toggle.title = "恢复监控"

    def _on_calibrate(self, _sender: rumps.MenuItem) -> None:
        if not self._monitor.is_started() or self._monitor.is_paused():
            notify("护眼", "请先启动监控，再进行距离校准。")
            return
        self._monitor.calibrate()

    def _on_reset(self, _sender: rumps.MenuItem) -> None:
        self._monitor.reset_stats()
        self._status.title = "状态：已重置"

    def _calibrate_posture(self, phase: PostureCalibration) -> None:
        try:
            self._monitor.calibrate_posture(phase)
        except ValueError as exc:
            notify("坐姿提醒", str(exc))

    def _on_posture_upright(self, _sender: rumps.MenuItem) -> None:
        self._calibrate_posture(PostureCalibration.UPRIGHT)

    def _on_posture_limit(self, _sender: rumps.MenuItem) -> None:
        self._calibrate_posture(PostureCalibration.LIMIT)

    def _on_posture_disable(self, _sender: rumps.MenuItem) -> None:
        self._monitor.disable_posture()

    def _on_quit(self, _sender: rumps.MenuItem) -> None:
        self._monitor.stop()
        rumps.quit_application()

    def _on_tick(self, _sender: rumps.Timer) -> None:
        snap = self._monitor.snapshot()
        posture = self._monitor.posture_snapshot()
        status = format_posture_status(posture)
        if posture.sampling and self._monitor.is_paused():
            status = "已暂停"
        self._posture_status.title = f"当前：{status}"
        if self._monitor.is_started():
            self._status.title = f"状态：{format_status(snap)}"
            # 出错自动暂停等状态变化由线程发起，菜单标题以实际状态为准
            self._toggle.title = "恢复监控" if self._monitor.is_paused() else "暂停监控"
        for reminder in self._monitor.drain_reminders():
            title, message = format_reminder(reminder)
            notify(title, message)


def main() -> None:
    if not NSApplication.sharedApplication().setActivationPolicy_(
        NSApplicationActivationPolicyAccessory
    ):
        raise RuntimeError("无法将护眼工具设为菜单栏应用")
    EyeGuardApp(load_config()).run()


if __name__ == "__main__":
    main()
