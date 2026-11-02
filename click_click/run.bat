@echo off
:: ==========================================
:: 自动获取管理员权限
:: ==========================================
%1 mshta vbscript:CreateObject("Shell.Application").ShellExecute("cmd.exe","/c %~s0 ::","","runas",1)(window.close)&&exit
cd /d "%~dp0"
chcp 65001 >nul

:: 每次按键后的等待间隔，单位：秒（支持小数，例如 0.5）
set "INTERVAL=0.3"

:: ==========================================
:: 你的 Python 运行指令
:: ==========================================
echo 正在以管理员身份启动脚本...
python spacer_game.py --interval "%INTERVAL%"

:: 如果脚本异常停止，保留窗口查看错误信息
pause
