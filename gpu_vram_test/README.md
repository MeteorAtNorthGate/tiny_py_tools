# Windows CUDA / PyTorch / 32GB 显存验机包

## 一、准备

1. 安装对应显卡可用的 NVIDIA 驱动。**N卡驱动主版本需要高于580，或者至少在525以上，525~579需要更改torch版本为126**
2. 安装 **Python 3，>= 3.12 x64**，安装时保留 Python Launcher（`py`）。
3. 关闭浏览器、游戏、录屏、视频增强、远程串流等占用 GPU 的程序。
4. 右键 `run_windows_test.ps1`，选择“使用 PowerShell 运行”。
   - 如果被执行策略拦截，在该文件夹打开 PowerShell，运行：
     `powershell -ExecutionPolicy Bypass -File .\run_windows_test.ps1`

脚本会安装独立的 PyTorch 环境，不会配置 ComfyUI，也不要求完整 CUDA Toolkit。

## 二、脚本实际测什么

- `torch.cuda.is_available()`、设备名、Compute Capability、驱动、PyTorch CUDA runtime、cuDNN。
- FP32 矩阵乘法与 CPU 参考值比对。
- FP16 Tensor Core 矩阵乘法。
- cuDNN 卷积。
- 默认覆盖最多约 **80% 显存**：
  - 以 256 MiB 为一块；
  - 所有块先写入不同数据；
  - 再把每个字节读回核对；
  - 重复两轮。
- 最后进行 10 分钟 8192×8192 FP16 矩阵乘法压力测试。
- 同时记录温度、功耗、频率、显存占用、利用率以及 Windows GPU/WHEA 事件。

32GB 卡在 Windows 下不能期待应用程序占满字面上的 32GB：
驱动、桌面显示和 CUDA 上下文都要占用一部分。正常目标通常是约 28–30GiB，
以脚本输出的 `显存读写校验 PASS：覆盖 ... GiB` 为准。

## 三、硬件供电等用3Dmark跑过了就视作没有问题（


## 四、通过标准

需要同时满足：

- `gpu-test-output.txt` 结尾出现 `ALL TESTS PASSED`。
- 显存覆盖量合理；32GB 卡建议至少约 28GiB。
- `gpu-monitor.csv` 中没有持续异常降频；温度和功耗没有明显失控。
- `windows-gpu-events.txt` 中没有测试期间的：
  - `nvlddmkm`
  - Display driver reset / 事件 4101
  - WHEA 17/18/19/20
- OCCT VRAM 与 3D Adaptive 均为 0 error。
- 无花屏、黑屏、死机、自动重启、驱动重启、程序随机退出。

出现任何一次显存错误、CUDA illegal memory access、驱动重启或 WHEA 硬件错误，
都不要按“偶发”放过；先重测，仍出现就应退换或检查显卡、主板插槽、供电和驱动。

