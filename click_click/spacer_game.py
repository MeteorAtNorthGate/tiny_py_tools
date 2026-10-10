import argparse
import random
import time

import keyboard


def main():
    parser = argparse.ArgumentParser(description="简易连点器")
    parser.add_argument("--interval", type=float, default=1, help="每次按键后的等待间隔（秒）")
    args = parser.parse_args()
    if not 0 < args.interval < float("inf"):
        parser.error("等待间隔必须是大于 0 的有限数字")

    try:
        while True:
            key = input("请输入要连按的按键（如 space、enter、a，直接回车默认 space）：").strip() or "space"
            try:
                keyboard.parse_hotkey(key)
                break
            except ValueError:
                print("无法识别该按键，请重新输入。")

        print(f"连按按键：{key}，等待间隔：{args.interval} 秒。")
        print("脚本启动，请在 5 秒内切换到目标窗口...")
        time.sleep(5)
        end_time = time.monotonic() + 600  # 运行 10 分钟

        while time.monotonic() < end_time:
            keyboard.press(key)
            try:
                # 模拟真人按住按键的时间（0.05 秒到 0.1 秒）
                time.sleep(random.uniform(0.05, 0.1))
            finally:
                keyboard.release(key)
            time.sleep(args.interval)
        print("时间到，任务结束。")
    except (KeyboardInterrupt, EOFError):
        print("已手动停止。")


if __name__ == "__main__":
    main()
