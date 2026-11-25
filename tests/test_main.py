"""UI 层纯文案函数测试 + I/O 模块导入冒烟测试。"""

from unittest.mock import Mock, call

from AppKit import NSImage

from eye_guard import main
from eye_guard.monitor import MonitorSnapshot, Reminder, ReminderKind


def test_format_status_shows_all_metrics() -> None:
    snap = MonitorSnapshot(
        face_present=True,
        ear=0.3,
        blink_total=12,
        blink_rate_per_min=6.0,
        continuous_s=125.0,
        total_s=300.0,
        proximity=1.05,
    )
    text = main.format_status(snap)
    assert "12" in text
    assert "6 次/分" in text
    assert "2分05秒" in text
    assert "1.05" in text


def test_format_status_handles_missing_data() -> None:
    text = main.format_status(MonitorSnapshot())
    assert "未检测到人脸" in text
    assert "未校准" in text


def test_format_reminder_covers_all_kinds() -> None:
    for kind in ReminderKind:
        title, message = main.format_reminder(Reminder(kind, 1.0))
        assert title
        assert message


def test_camera_error_reminder_passes_message_through() -> None:
    r = Reminder(ReminderKind.CAMERA_ERROR, 0.0, message="无法打开摄像头")
    title, message = main.format_reminder(r)
    assert title == "护眼"
    assert message == "无法打开摄像头"


def test_launch_sets_menu_bar_mode_before_creating_app(monkeypatch) -> None:
    calls = Mock()
    monkeypatch.setattr(main, "NSApplication", calls.cocoa)
    monkeypatch.setattr(main, "EyeGuardApp", calls.eye_guard)
    monkeypatch.setattr(main, "load_config", calls.load_config)

    main.main()

    assert calls.mock_calls == [
        call.cocoa.sharedApplication(),
        call.cocoa.sharedApplication().setActivationPolicy_(
            main.NSApplicationActivationPolicyAccessory
        ),
        call.load_config(),
        call.eye_guard(calls.load_config.return_value),
        call.eye_guard().run(),
    ]


def test_menu_bar_template_is_a_loadable_square_asset() -> None:
    image = NSImage.alloc().initWithContentsOfFile_(str(main.MENU_BAR_ICON))
    assert image is not None
    assert tuple(image.size()) == (20, 20)


def test_io_modules_importable() -> None:
    import eye_guard.camera  # noqa: F401
    import eye_guard.reminder  # noqa: F401
    import eye_guard.vision  # noqa: F401
