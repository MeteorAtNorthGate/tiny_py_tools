# tiny_py_tools

一些互不相关的简易 Python 小脚本合集。每个工具独立放在自己的目录里，各自维护 `requirements.txt`，共享一份 `.gitignore`。

## 工具列表

| 目录 | 用途 |
|---|---|
| [`gpu_vram_test`](./gpu_vram_test/) | Windows 下 NVIDIA 显卡 CUDA / PyTorch / 显存完整性验收测试（搭配 PowerShell 脚本一键运行） |
| [`llm_api_check`](./llm_api_check/) | 查询 DeepSeek / Gemini API 可用模型列表 |
| [`pandoc-studio`](./pandoc-studio/) | 基于 Pandoc + PySide6 的 Windows 文档格式转换 GUI |
| [`sign_to_png`](./sign_to_png/) | 将手写签名照片转为透明背景的 PNG 电子签名（带羽化效果） |

## 使用方式

进入对应目录，创建虚拟环境并安装依赖：

```bash
cd <tool-dir>
python -m venv .venv
source .venv/bin/activate  # Linux / macOS
# 或 .venv\Scripts\activate  # Windows
pip install -r requirements.txt
python <entry-script>.py
```

部分工具（如 `gpu_vram_test`）有独立的 PowerShell 脚本或更详细的 README，详见各目录。
