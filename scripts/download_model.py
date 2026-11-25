"""安装时一次性下载 MediaPipe 人脸和坐姿模型到 assets/。

注意：这是唯一的网络请求，仅在安装模型时手动执行；
工具运行期不发起任何网络请求，也不将任何图像帧写入磁盘。

用法: uv run python scripts/download_model.py
"""

import hashlib
import sys
import urllib.request
from pathlib import Path
from tempfile import NamedTemporaryFile

MODEL_HOST = "https://storage.googleapis.com/mediapipe-models/"
MODELS = (
    (
        "face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
    ),
    (
        "pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a",
    ),
)


def download_model(relative_url: str, expected_hash: str) -> None:
    destination = Path("assets", relative_url.rsplit("/", 1)[-1])
    if destination.is_file():
        print(f"模型已存在：{destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"下载模型到 {destination}…")
    with urllib.request.urlopen(MODEL_HOST + relative_url, timeout=30) as response:
        model = response.read()
    if hashlib.sha256(model).hexdigest() != expected_hash:
        raise OSError(f"{destination.name} 的 SHA-256 校验失败")
    with NamedTemporaryFile(dir=destination.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(model)
            output.close()
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def main() -> int:
    try:
        for relative_url, digest in MODELS:
            download_model(relative_url, digest)
    except OSError as exc:
        print(f"模型准备失败：{exc}")
        return 1
    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
