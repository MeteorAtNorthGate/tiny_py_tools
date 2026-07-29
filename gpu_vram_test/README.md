# Windows CUDA / PyTorch / 32GB 显存验机包

适用于 32GB 魔改 / 标准 NVIDIA 显卡的 CUDA 计算与显存完整性验收测试。

## 一、准备

1. 安装对应显卡可用的 **NVIDIA 驱动**。驱动主版本需要 **大于 580**（当前最新为 610）。
   - 驱动版本 525–579 需要降级 PyTorch 版本（脚本默认安装 2.12.1+cu130，不适用于旧驱动）。
2. 安装 **Python >= 3.12 x64**，安装时勾选 Python Launcher（`py`）。
3. 关闭浏览器、游戏、录屏、视频增强、远程串流等占用 GPU 的程序。
4. 根据网络环境选择脚本：
   - **`run_windows_test_官方源.ps1`** — 从 PyTorch 官方 CUDA 13.0 索引安装。
   - **`run_windows_test_阿里源.ps1`** — 从阿里云镜像安装（国内网络推荐，含 `--timeout 600 --retries 8`）。
   - 右键脚本文件，选择"使用 PowerShell 运行"。
   - 如果被执行策略拦截，在该文件夹打开 PowerShell，运行：
     ```powershell
     powershell -ExecutionPolicy Bypass -File .\run_windows_test_官方源.ps1
     ```

脚本会在当前目录创建 `.venv` 独立 Python 虚拟环境，自动安装 `numpy>=1.26,<3` 和 `torch==2.12.1+cu130`，不会配置 ComfyUI，也不要求完整 CUDA Toolkit。

## 二、脚本实际测什么

### 2.1 环境与设备识别
- `torch.cuda.is_available()`、设备名称、Compute Capability、驱动版本、PyTorch CUDA runtime、cuDNN 版本。
- nvidia-smi 设备列表与摘要信息。

### 2.2 基础计算正确性
- **FP32 矩阵乘法**（768×768）与 CPU 参考值比对（`torch.allclose` rtol=2e-4, atol=2e-3）。
- **FP16 Tensor Core 矩阵乘法**（2048×2048），检查无 NaN/Inf。
- **cuDNN Conv2d**（64→128 通道，3×3 卷积），检查无 NaN/Inf。

### 2.3 显存大容量读写校验（`--vram-fraction` 默认 0.92）
- 以 256 MiB 为一块（可通过 `--chunk-mib` 调整）；
- 所有块先写入基于块序号和轮次的独立 pattern（`(i*37 + rnd*101 + 13) & 0xFF`）；
- 再把每个字节读回逐块核对；
- 重复两轮（可通过 `--vram-rounds` 调整）。
- 分配门槛为 `min(总显存 × 88%, 空闲显存 − reserve − chunk)` 中的**较小值**：
  - 88% 是上限，防止在完全空闲的系统上（如 headless Linux，free ≈ total）门槛被推到不合理的高位；
  - 在 Windows 桌面上，DWM 等已占用部分显存，空闲显存一侧的值通常远小于 88%，是实际生效的门槛。因此 PS 脚本传 `--vram-fraction 0.80` 在正常桌面环境下也能轻松通过。
- 地址别名 / 虚假容量映射会被第二轮写入-读回发现。

### 2.4 持续计算压力测试
- 默认 **10 分钟** 8192×8192 FP16 矩阵乘法压力测试（可通过 `--stress-minutes` / `--matrix-size` 调整）。
- 每 30 秒输出进度（迭代次数、checksum）。

### 2.5 GPU 状态监控与系统事件采集
- nvidia-smi 每 2 秒记录：时间戳、GPU 名称、驱动版本、P-State、温度、功耗、SM/显存频率、显存占用/总量、GPU/显存利用率 → `gpu-monitor.csv`。
- 测试前后各保存一份 nvidia-smi 完整信息（`nvidia-smi-before.txt`、`nvidia-smi-after.txt`）。
- 导出测试期间 Windows 系统日志中的 GPU 相关事件（nvlddmkm、Display 驱动重置、WHEA 17/18/19/20、事件 4101）→ `windows-gpu-events.txt`。

## 三、Python 脚本命令行参数

直接调用 `gpu_acceptance_test.py` 时可覆盖以下参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--stress-minutes` | 10 | 持续计算压力测试时长（分钟） |
| `--vram-fraction` | 0.92 | 目标显存覆盖比例（0–1） |
| `--vram-rounds` | 2 | 显存写入-读回校验轮数 |
| `--chunk-mib` | 256 | 每块大小（MiB） |
| `--reserve-gib` | 1.75 | 为驱动/系统保留的显存量（GiB） |
| `--matrix-size` | 8192 | 压力测试矩阵边长 |

> **注意**：PowerShell 脚本使用 `--vram-fraction 0.80` 调用。Python 脚本自身默认 0.92。显存覆盖量以输出的 `显存读写校验 PASS：覆盖 ... GiB` 为最终结果。

## 四、硬件供电等用 3DMark 跑过了就视作没有问题

## 五、输出文件清单

| 文件 | 内容 |
|---|---|
| `gpu-test-output.txt` | Python 测试完整输出（含 PASS/FAIL 判定） |
| `gpu-monitor.csv` | nvidia-smi 每 2 秒采样（温度、功耗、频率、利用率等） |
| `gpu-monitor-error.txt` | nvidia-smi 监控的 stderr |
| `nvidia-smi-before.txt` | 测试前 nvidia-smi -q 完整信息 |
| `nvidia-smi-after.txt` | 测试后 nvidia-smi -q 完整信息 |
| `nvidia-smi-list.txt` | nvidia-smi -L 设备列表 |
| `windows-gpu-events.txt` | 测试期间 GPU 相关 Windows 系统事件 |

## 六、通过标准

需要同时满足：

- `gpu-test-output.txt` 结尾出现 `ALL TESTS PASSED`。
- 显存覆盖量合理：以输出 `显存读写校验 PASS：覆盖 ... GiB` 为准。32GB 卡通常覆盖 25–30 GiB 均为正常（Windows 桌面占用差异导致），低于 24 GiB 应排查后台占用后重测。
- `gpu-monitor.csv` 中没有持续异常降频；温度和功耗没有明显失控。
- `windows-gpu-events.txt` 中没有测试期间的：
  - `nvlddmkm`
  - Display driver reset / 事件 4101
  - WHEA 17/18/19/20
- OCCT VRAM 与 3D Adaptive 均为 0 error。
- 无花屏、黑屏、死机、自动重启、驱动重启、程序随机退出。

出现任何一次显存错误、CUDA illegal memory access、驱动重启或 WHEA 硬件错误，
都不要按"偶发"放过；先重测，仍出现就应退换或检查显卡、主板插槽、供电和驱动。
