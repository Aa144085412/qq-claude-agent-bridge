"""Small, deterministic Windows tool registry for owner's QQ Agent.

No generic shell, dynamic code execution, files mutation, or remote endpoint exposure.
Write actions (launching preapproved desktop apps) require explicit owner confirmation.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
import urllib.request

APPLICATIONS = {
    "notepad": ("记事本", Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "notepad.exe"),
    "calculator": ("计算器", Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "calc.exe"),
    "explorer": ("文件资源管理器", Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe"),
}
APP_ALIASES = {
    "记事本": "notepad",
    "notepad": "notepad",
    "计算器": "calculator",
    "calc": "calculator",
    "calculator": "calculator",
    "文件资源管理器": "explorer",
    "资源管理器": "explorer",
    "explorer": "explorer",
}


class ToolDenied(Exception):
    pass


class MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def parse_action_name(text: str):
    value = text.strip()
    for prefix in ("/打开 ", "打开", "帮我打开", "请打开", "启动", "帮我启动", "请启动"):
        if value.startswith(prefix):
            name = value[len(prefix):].strip(" 。！! ")
            return APP_ALIASES.get(name)
    return None


def may_be_machine_request(text: str) -> bool:
    value = text.strip()
    return value.startswith(("/电脑", "/打开 ", "/确认操作 ", "/取消操作", "/工具", "/系统状态", "打开", "启动", "请打开", "帮我打开", "请启动", "帮我启动")) or any(
        marker in value
        for marker in ("控制电脑", "操控电脑", "操作电脑", "本地电脑", "电脑状态",
                       "电脑运行", "系统状态", "磁盘空间", "内存使用", "CPU使用", "CPU 状态",
                       "显卡状态", "模型状态", "打开记事本", "打开计算器", "打开资源管理器",
                       "启动记事本", "启动计算器", "启动资源管理器",
                       "切换Agent模式", "切换聊天模式", "模式切换", "切换其他模式", "切换模式")
    )


def model_health() -> str:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open("http://127.0.0.1:18081/health", timeout=3) as resp:
            return "HTTP " + str(resp.status)
    except (OSError, TimeoutError):
        return "不可连接"


def computer_status() -> str:
    if os.name != "nt":
        raise ToolDenied("此工具仅支持本机 Windows")
    mem = MemoryStatus()
    mem.dwLength = ctypes.sizeof(mem)
    try:
        mem_ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
    except Exception:
        mem_ok = 0
    memory_info = (
        f"内存：{(mem.ullTotalPhys - mem.ullAvailPhys)/2**30:.1f}/"
        f"{mem.ullTotalPhys/2**30:.1f} GB 已用"
        if mem_ok and mem.ullTotalPhys else "内存：获取失败"
    )
    drive = os.environ.get("SystemDrive", "C:") + "\\"
    try:
        disk = shutil.disk_usage(drive)
        disk_info = f"{drive} 空间：剩余 {disk.free/2**30:.1f} GB / 总 {disk.total/2**30:.1f} GB"
    except OSError:
        disk_info = "磁盘：获取失败"
    return (
        "本机 Windows 电脑状态（真实只读检查）：\n"
        f"系统：{platform.system()} {platform.release()}\n"
        f"CPU：{os.cpu_count() or '未知'} 个逻辑处理器\n"
        f"{memory_info}\n{disk_info}\n"
        f"本地 IQ3_S：{model_health()}\n"
        "此次仅查看状态，未修改电脑。"
    )


def allowlisted_application(action: str):
    item = APPLICATIONS.get(action)
    if item is None:
        raise ToolDenied("未授权的应用操作")
    name, exe = item
    if not exe.is_file():
        raise ToolDenied(f"{name} 程序不存在")
    return name, exe


def launch_application(action: str) -> str:
    name, executable = allowlisted_application(action)
    # Never use shell=True; program/arguments are fixed in trusted code.
    if os.name != "nt":
        raise ToolDenied("应用启动只允许 Windows 本机")
    proc = subprocess.Popen(
        [str(executable)], cwd=str(executable.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        shell=False, close_fds=True,
    )
    return f"已向 Windows 发出启动 {name} 的请求（PID {proc.pid}）。如窗口未显示，请在桌面检查。"


TOOL_GUIDE = (
    "电脑任务模式已接入本机工具：\n"
    "· /电脑状态 或“帮我检查电脑状态”——读取 Windows、内存、磁盘和本地模型状态\n"
    "· 打开记事本／计算器／资源管理器——先生成操作申请\n"
    "· /确认操作 8位操作码——主人确认后才启动预设程序\n"
    "· /取消操作——取消未执行的操作\n"
    "· /模式 Agent、/模式 聊天、/模式 自动——切换消息路由模式\n"
    "目前不支持任意 Shell、删除文件、安装软件或无人值守电脑操作。"
)
