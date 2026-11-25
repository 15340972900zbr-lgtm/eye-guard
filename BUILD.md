# 护眼工具 Windows x64 构建

Windows 版根据项目规约及 Mac 版已经验证的功能重新实现。视觉与状态计算独立于 Windows 托盘界面。安装包为 NSIS 安装程序，内含官方 Python 嵌入式运行时、Windows 依赖和本地模型。

在 Linux x86-64 构建机上准备 uv、curl、unzip 和 NSIS 3.11，然后运行：

    uv run pytest
    uv run ruff check . source/start.pyw
    uv run ruff format --check . source/start.pyw
    ./build-windows.sh

自定义安装的 NSIS 可以通过环境变量 MAKENSIS 指定编译器路径，并用 NSISDIR 指定组件目录。构建会下载并校验固定版本的 Python 和模型，Python 依赖版本固定在 requirements-windows.txt。安装和运行不需要联网。Windows x64 真机验收包括首次摄像头权限、托盘状态、暂停和退出释放设备、休息提醒不抢走正在输入的焦点。
