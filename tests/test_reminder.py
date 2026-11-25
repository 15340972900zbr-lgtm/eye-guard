"""提醒脚本构造测试：osascript 通知文案的转义。"""

from eye_guard.reminder import notification_script


def test_script_embeds_title_and_message() -> None:
    script = notification_script("护眼提示", "该休息了")
    assert script.startswith('display notification "该休息了"')
    assert 'with title "护眼提示"' in script


def test_script_escapes_quotes_and_backslashes() -> None:
    script = notification_script('说"你好"', '包含"引号"和\\反斜杠')
    assert '\\"' in script
    assert "\\\\" in script
    assert '"引号"' not in script  # 原始引号必须被转义


def test_script_can_add_sound() -> None:
    script = notification_script("护眼提示", "该休息了", sound=True)
    assert "sound name" in script
