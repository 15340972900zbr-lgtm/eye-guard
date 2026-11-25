# 护眼工具 · EyeGuard

在本机用摄像头统计眨眼、相对距离和连续用眼时间。macOS 版支持校准头前倾界线，并在超过界线时提醒坐直、放松肩膀。

**[查看中文使用手册](docs/使用手册.md)** · **[Windows 试用版安装包](https://github.com/15340972900zbr-lgtm/eye-guard/releases/tag/windows-v0.1.0)**

## macOS 快速开始

适用于 Apple Silicon Mac。安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，克隆本仓库，在项目目录执行：

```sh
uv sync
uv run python scripts/download_model.py
uv run eye-guard
```

点击顶部菜单栏的单色眼睛图标，选择「启动监控」。休息、眨眼和距离提醒在 `config.toml` 中启用。头前倾提醒在「坐姿提醒」菜单中完成两步校准即可开启。

## Windows 试用版

适用于 Windows 10 或 11 的 Intel / AMD x64 电脑。到发布页下载安装程序，安装后从「开始」菜单打开「护眼工具」，再用任务栏右下角的托盘图标开始监控。安装包内含运行环境和模型。

Windows 试用版包含眨眼、连续用眼和相对距离。构建源码在 [`windows` 分支](https://github.com/15340972900zbr-lgtm/eye-guard/tree/windows)。

## 本地运行与开发

摄像头画面和关键点只在内存里处理，推理在本机完成。安装 Python 依赖和下载模型时需要联网。Mac 版模型由安装脚本从 MediaPipe 下载并校验。

| 目录 | 内容 |
| --- | --- |
| `src/eye_guard/` | 摄像头采集、本地推理、指标与提醒、菜单栏界面 |
| `tests/` | 无需相机硬件的自动测试 |
| `docs/` | 中文使用手册 |

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
