# Pandoc Studio

一个基于 [Pandoc](https://pandoc.org/) 和 PySide6 的 Windows 文档转换 GUI。程序不内置 Pandoc，而是直接调用已注册到系统 `PATH` 的 `pandoc` 命令。

## 功能

- 将文件拖放到窗口，或点击拖放区域选择文件
- 输入格式下拉菜单默认留空；留空时由 Pandoc 根据文件后缀判断
- 可选择 Word、PDF、HTML、Markdown、EPUB、PowerPoint、ODT、RTF 等输出格式
- 默认把输出文件放在源文件旁，也可使用“另存为…”指定位置
- 转换过程不会阻塞界面，并展示成功、失败和 Pandoc 错误信息
- 启动时自动运行 `pandoc --version` 检查系统环境

## 环境要求

- Windows 10/11
- Python 3.10 或更高版本
- Pandoc 已安装并加入系统 `PATH`

先在命令提示符中确认：

```powershell
pandoc --version
```

然后安装并运行：

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

> PDF 转换还需要 Pandoc 可用的 PDF 引擎，例如 MiKTeX。是否需要额外依赖取决于所选输入和输出格式。

## 开发检查

```powershell
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Pandoc 由 `QProcess` 通过参数列表直接执行，没有经过 shell；文件名中包含空格时也不需要额外处理。
