# -*- coding: utf-8 -*-
"""
Kakao Local Program Launcher v24
- Real desktop program UI, not web
- Always asks access code on every program start
- Windows/Mac selector included
- Control endpoint is hidden from UI and not stored as a plain URL string
- Checks access code with control server
- Server only controls code/enabled state
- KakaoTalk launches on the user's local PC
- Windows handle-unlock launcher included
- Standard library only
"""

import os
import sys
import json
import time
import ctypes
import subprocess
import threading
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import tkinter as tk
from tkinter import ttk, messagebox


def _control_endpoint():
    # Not shown in the UI. Built at runtime so the plain address is not stored in the source.
    scheme = "".join(chr(x) for x in (104, 116, 116, 112))
    host = ".".join(str(x) for x in (167, 172, 95, 226))
    port = str(1000 + 70)
    return scheme + "://" + host + ":" + port


def _api_url(path):
    return _control_endpoint().rstrip("/") + path

APP_ICON_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAbElEQVR42u2XOw4AIAhDuf/5vA/uGo3C8zN06EbLU0iMZmb+WJ8BeDnXbJDdF52AmORuFdPNxztAQSzkpMwO+JGQjA8Ni9SzoYEb404WHBcz28TCxhes1dW3AGouAAEIQAACEIAAPvyaCeC2Kq8dufXUe6lPAAAAAElFTkSuQmCC"
CONFIG_FILE = Path.home() / ".kakao_local_launcher_config.json"

RUN_META = {}
RUN_SEQ = 0


def is_windows():
    return sys.platform == "win32"


def is_mac():
    return sys.platform == "darwin"


def current_os_label():
    if is_windows():
        return "windows"
    if is_mac():
        return "mac"
    return "other"


def now_time():
    return time.strftime("%H:%M:%S")


def load_config():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_config(data):
    try:
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def remote_check_code(code):
    code = str(code or "").strip()
    if not code:
        return False, "user", False, "invalid"

    try:
        payload = json.dumps({"code": code}).encode("utf-8")
        req = Request(
            _api_url("/api/check"),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        ok = bool(data.get("ok"))
        role = str(data.get("role") or "user")
        enabled = bool(data.get("enabled", False))

        if not ok:
            return False, role, enabled, "invalid"
        if not enabled:
            return False, role, enabled, "disabled"
        return True, role, enabled, ""
    except Exception as e:
        return False, "user", False, "server_error"


def normalize_proxy(proxy: str) -> str:
    proxy = (proxy or "").strip()
    if not proxy:
        return ""
    if proxy.startswith(("http://", "https://", "socks5://")):
        return proxy
    return "http://" + proxy


def run_quiet(args, shell=False):
    try:
        if is_windows():
            return subprocess.run(
                args,
                shell=shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="mbcs",
                errors="ignore",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        return subprocess.run(
            args,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            errors="ignore",
        )
    except Exception as e:
        class Result:
            stdout = ""
            stderr = str(e)
            returncode = 1
        return Result()


def register_pid(pid, mode, proxy=""):
    global RUN_SEQ
    try:
        pid = int(pid)
    except Exception:
        return
    if pid not in RUN_META:
        RUN_SEQ += 1
        RUN_META[pid] = {
            "seq": RUN_SEQ,
            "mode": mode,
            "proxy": proxy or "",
            "started_at": now_time(),
        }


def cleanup_meta(active_pids):
    active = set(int(x) for x in active_pids)
    for pid in list(RUN_META.keys()):
        if int(pid) not in active:
            RUN_META.pop(pid, None)


# ======================================================
# Windows handle unlock
# ======================================================
WIN_READY = False

if is_windows():
    from ctypes import wintypes

    ntdll = ctypes.WinDLL("ntdll")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    PROCESS_DUP_HANDLE = 0x0040
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    DUPLICATE_CLOSE_SOURCE = 0x00000001
    DUPLICATE_SAME_ACCESS = 0x00000002
    SystemExtendedHandleInformation = 64
    ObjectNameInformation = 1
    STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
    STATUS_SUCCESS = 0
    ULONG_PTR = wintypes.WPARAM

    class UNICODE_STRING(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", wintypes.LPWSTR),
        ]

    class SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX(ctypes.Structure):
        _fields_ = [
            ("Object", wintypes.LPVOID),
            ("UniqueProcessId", ULONG_PTR),
            ("HandleValue", ULONG_PTR),
            ("GrantedAccess", wintypes.ULONG),
            ("CreatorBackTraceIndex", wintypes.USHORT),
            ("ObjectTypeIndex", wintypes.USHORT),
            ("HandleAttributes", wintypes.ULONG),
            ("Reserved", wintypes.ULONG),
        ]

    class SYSTEM_HANDLE_INFORMATION_EX(ctypes.Structure):
        _fields_ = [
            ("NumberOfHandles", ULONG_PTR),
            ("Reserved", ULONG_PTR),
            ("Handles", SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX * 1),
        ]

    NtQuerySystemInformation = ntdll.NtQuerySystemInformation
    NtQuerySystemInformation.argtypes = [
        wintypes.ULONG,
        wintypes.LPVOID,
        wintypes.ULONG,
        ctypes.POINTER(wintypes.ULONG),
    ]
    NtQuerySystemInformation.restype = wintypes.LONG

    NtQueryObject = ntdll.NtQueryObject
    NtQueryObject.argtypes = [
        wintypes.HANDLE,
        wintypes.ULONG,
        wintypes.LPVOID,
        wintypes.ULONG,
        ctypes.POINTER(wintypes.ULONG),
    ]
    NtQueryObject.restype = wintypes.LONG

    OpenProcess = kernel32.OpenProcess
    OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    OpenProcess.restype = wintypes.HANDLE

    DuplicateHandle = kernel32.DuplicateHandle
    DuplicateHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    DuplicateHandle.restype = wintypes.BOOL

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    GetCurrentProcess = kernel32.GetCurrentProcess
    GetCurrentProcess.restype = wintypes.HANDLE

    WIN_READY = True


def windows_find_kakao_path():
    paths = [
        r"C:\Program Files\Kakao\KakaoTalk\KakaoTalk.exe",
        r"C:\Program Files (x86)\Kakao\KakaoTalk\KakaoTalk.exe",
        os.path.expanduser(r"~\AppData\Local\Kakao\KakaoTalk\KakaoTalk.exe"),
    ]

    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                key = winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\KakaoTalk.exe")
                p = winreg.QueryValue(key, None)
                if p and os.path.exists(p):
                    return p
            except Exception:
                pass
    except Exception:
        pass

    for p in paths:
        if os.path.exists(p):
            return p
    return None


def windows_list_pids():
    if not is_windows():
        return []
    pids = []
    r = run_quiet(["tasklist", "/FI", "IMAGENAME eq KakaoTalk.exe", "/FO", "CSV", "/NH"])
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line or "정보:" in line or "INFO:" in line or "No tasks" in line:
            continue
        parts = [x.strip('"') for x in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == "kakaotalk.exe":
            try:
                pids.append(int(parts[1]))
            except Exception:
                pass
    return sorted(set(pids))


def windows_query_all_handles():
    size = 0x10000
    while True:
        buf = ctypes.create_string_buffer(size)
        ret_len = wintypes.ULONG(0)
        status = NtQuerySystemInformation(
            SystemExtendedHandleInformation,
            buf,
            size,
            ctypes.byref(ret_len),
        )
        if status == STATUS_SUCCESS:
            break

        if status == ctypes.c_long(STATUS_INFO_LENGTH_MISMATCH).value or status == STATUS_INFO_LENGTH_MISMATCH:
            size = max(size * 2, ret_len.value + 0x10000)
            if size > 128 * 1024 * 1024:
                raise RuntimeError("핸들 목록 버퍼가 너무 커졌습니다.")
            continue

        raise RuntimeError(f"NtQuerySystemInformation 실패: 0x{status & 0xFFFFFFFF:08X}")

    info = ctypes.cast(buf, ctypes.POINTER(SYSTEM_HANDLE_INFORMATION_EX)).contents
    count = int(info.NumberOfHandles)
    base = ctypes.addressof(info.Handles)
    entry_size = ctypes.sizeof(SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX)

    for i in range(count):
        yield SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX.from_address(base + i * entry_size)


def windows_duplicate_for_query(process_handle, handle_value):
    dup = wintypes.HANDLE(0)
    ok = DuplicateHandle(
        process_handle,
        wintypes.HANDLE(int(handle_value)),
        GetCurrentProcess(),
        ctypes.byref(dup),
        0,
        False,
        DUPLICATE_SAME_ACCESS,
    )
    if not ok or not dup.value:
        return None
    return dup


def windows_query_object_name(handle):
    size = 0x2000
    for _ in range(3):
        buf = ctypes.create_string_buffer(size)
        ret_len = wintypes.ULONG(0)
        status = NtQueryObject(handle, ObjectNameInformation, buf, size, ctypes.byref(ret_len))

        if status == STATUS_SUCCESS:
            uni = ctypes.cast(buf, ctypes.POINTER(UNICODE_STRING)).contents
            if uni.Length and uni.Buffer:
                try:
                    return ctypes.wstring_at(uni.Buffer, uni.Length // 2)
                except Exception:
                    return ""
            return ""

        if ret_len.value and ret_len.value > size:
            size = ret_len.value + 2
            continue

        return ""

    return ""


def windows_close_source_handle(process_handle, handle_value):
    dup = wintypes.HANDLE(0)
    ok = DuplicateHandle(
        process_handle,
        wintypes.HANDLE(int(handle_value)),
        GetCurrentProcess(),
        ctypes.byref(dup),
        0,
        False,
        DUPLICATE_CLOSE_SOURCE | DUPLICATE_SAME_ACCESS,
    )
    if ok:
        if dup.value:
            CloseHandle(dup)
        return True
    return False


def windows_unlock_handles():
    if not WIN_READY:
        return ["Windows 핸들 API 초기화 실패"], 0

    pids = windows_list_pids()
    if not pids:
        return ["실행 중인 KakaoTalk.exe 없음"], 0

    logs = ["감지된 PID: " + ", ".join(map(str, pids))]
    lock_keywords = [
        "97C4DDD9-D36D-48b5-BB47-2C8299BA7D1E".lower(),
        "kakaotalk".lower(),
    ]

    pid_set = set(pids)
    process_handles = {}
    closed = 0
    names = []

    try:
        for h in windows_query_all_handles():
            pid = int(h.UniqueProcessId)
            if pid not in pid_set:
                continue

            if pid not in process_handles:
                ph = OpenProcess(PROCESS_DUP_HANDLE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not ph:
                    continue
                process_handles[pid] = ph

            ph = process_handles[pid]
            dup = windows_duplicate_for_query(ph, h.HandleValue)
            if not dup:
                continue

            try:
                name = windows_query_object_name(dup) or ""
            finally:
                CloseHandle(dup)

            if any(key in name.lower() for key in lock_keywords):
                if windows_close_source_handle(ph, h.HandleValue):
                    closed += 1
                    if len(names) < 5:
                        names.append(name)

    except Exception as e:
        logs.append("핸들 해제 오류: " + str(e))
    finally:
        for ph in process_handles.values():
            try:
                CloseHandle(ph)
            except Exception:
                pass

    logs.append(f"핸들 해제 완료: {closed}개")
    return logs, closed


def windows_launch(proxy=""):
    path = windows_find_kakao_path()
    if not path:
        return False, ["KakaoTalk.exe를 찾지 못했습니다."]

    before = set(windows_list_pids())
    logs = [f"{len(before) + 1}개 실행 시도", "중복 실행 방지 핸들 검색중"]

    unlock_logs, _ = windows_unlock_handles()
    logs.extend(unlock_logs)

    env = os.environ.copy()
    proxy_url = normalize_proxy(proxy)
    if proxy_url:
        env["HTTP_PROXY"] = proxy_url
        env["HTTPS_PROXY"] = proxy_url
        env["http_proxy"] = proxy_url
        env["https_proxy"] = proxy_url
    logs.append("실행 환경 적용 완료")

    try:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
        proc = subprocess.Popen([path], cwd=os.path.dirname(path) or None, env=env, creationflags=flags)
        logs.append(f"실행 요청 완료 / PID {proc.pid}")

        time.sleep(1.2)

        extra_logs, extra_closed = windows_unlock_handles()
        if extra_closed:
            logs.append(f"다음 실행 준비 핸들 해제: {extra_closed}개")

        after = set(windows_list_pids())
        new_pids = sorted(after - before)
        if new_pids:
            for pid in new_pids:
                register_pid(pid, "windows", proxy)
        else:
            register_pid(proc.pid, "windows", proxy)

        count = len(windows_list_pids())
        logs.append(f"{count}개 정상실행중")
        return True, logs

    except Exception as e:
        logs.append("실행 오류: " + str(e))
        return False, logs


def windows_kill_pid(pid):
    try:
        pid = int(pid)
    except Exception:
        return False, ["PID가 올바르지 않습니다."]

    logs = [f"PID {pid} 종료 시도"]
    run_quiet(["taskkill", "/F", "/T", "/PID", str(pid)])
    time.sleep(0.5)

    RUN_META.pop(pid, None)
    alive = pid in windows_list_pids()
    logs.append("종료 완료" if not alive else "종료 실패 또는 잔여 프로세스 존재")
    return not alive, logs


def windows_kill_all():
    before = len(windows_list_pids())
    logs = ["카카오톡 전체 종료 시작"]

    for img in ("KakaoTalk.exe", "KakaoTalkUpdate.exe", "KakaoAdPlus.exe"):
        run_quiet(["taskkill", "/F", "/T", "/IM", img])

    time.sleep(0.8)
    after = len(windows_list_pids())

    if after == 0:
        for pid in list(RUN_META.keys()):
            if RUN_META[pid].get("mode") == "windows":
                RUN_META.pop(pid, None)

    logs.append(f"카카오톡 종료 완료: 종료 전 {before}개 / 남은 {after}개")
    return after == 0, logs


# ======================================================
# macOS fallback
# ======================================================
def mac_find_app():
    candidates = [
        "/Applications/KakaoTalk.app",
        str(Path.home() / "Applications/KakaoTalk.app"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def mac_list_pids():
    if not is_mac():
        return []
    pids = []
    r = run_quiet(["pgrep", "-f", "KakaoTalk"])
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            pid = int(line)
            if pid != os.getpid():
                pids.append(pid)
    return sorted(set(pids))


def mac_launch(proxy=""):
    app = mac_find_app()
    before = set(mac_list_pids())
    logs = [f"{len(before) + 1}개 실행 시도", "macOS 버전으로 실행 준비"]

    if not app:
        logs.append("KakaoTalk.app을 찾지 못했습니다. /Applications에 설치되어 있어야 합니다.")
        return False, logs

    try:
        subprocess.Popen(
            ["open", "-n", app],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logs.append("open -n 방식 실행 요청 완료")

        time.sleep(2.0)
        after = set(mac_list_pids())
        new_pids = sorted(after - before)

        for pid in new_pids:
            register_pid(pid, "mac", proxy)

        count = len(mac_list_pids())
        if new_pids:
            logs.append(f"{count}개 정상실행중")
            return True, logs

        logs.append("새 카톡 프로세스 증가 확인 안 됨")
        return False, logs

    except Exception as e:
        logs.append("실행 오류: " + str(e))
        return False, logs


def mac_kill_pid(pid):
    try:
        pid = int(pid)
    except Exception:
        return False, ["PID가 올바르지 않습니다."]

    logs = [f"PID {pid} 종료 시도"]
    run_quiet(["kill", "-TERM", str(pid)])
    time.sleep(0.7)

    if pid in mac_list_pids():
        run_quiet(["kill", "-9", str(pid)])
        time.sleep(0.5)

    RUN_META.pop(pid, None)
    alive = pid in mac_list_pids()
    logs.append("종료 완료" if not alive else "종료 실패 또는 잔여 프로세스 존재")
    return not alive, logs


def mac_kill_all():
    before = len(mac_list_pids())
    logs = ["카카오톡 전체 종료 시작"]
    run_quiet(["osascript", "-e", 'tell application "KakaoTalk" to quit'])
    time.sleep(1.0)
    run_quiet(["pkill", "-f", "KakaoTalk"])
    time.sleep(0.8)
    after = len(mac_list_pids())
    logs.append(f"카카오톡 종료 완료: 종료 전 {before}개 / 남은 {after}개")
    return after == 0, logs


def get_pids_by_mode(mode):
    mode = (mode or "windows").lower()
    if mode == "windows":
        return windows_list_pids() if is_windows() else []
    if mode == "mac":
        return mac_list_pids() if is_mac() else []
    return []


def launch_by_mode(mode):
    mode = (mode or "windows").lower()
    if mode == "windows":
        if not is_windows():
            return False, ["Windows 버전은 Windows에서만 실행할 수 있습니다."]
        return windows_launch("")
    if mode == "mac":
        if not is_mac():
            return False, ["Mac 버전은 macOS에서만 실행할 수 있습니다."]
        return mac_launch("")
    return False, ["지원하지 않는 실행 버전입니다."]


def kill_pid_by_mode(mode, pid):
    mode = (mode or "windows").lower()
    if mode == "windows":
        if not is_windows():
            return False, ["Windows 버전은 Windows에서만 종료할 수 있습니다."]
        return windows_kill_pid(pid)
    if mode == "mac":
        if not is_mac():
            return False, ["Mac 버전은 macOS에서만 종료할 수 있습니다."]
        return mac_kill_pid(pid)
    return False, ["지원하지 않는 실행 버전입니다."]


def kill_all_by_mode(mode):
    mode = (mode or "windows").lower()
    if mode == "windows":
        if not is_windows():
            return False, ["Windows 버전은 Windows에서만 종료할 수 있습니다."]
        return windows_kill_all()
    if mode == "mac":
        if not is_mac():
            return False, ["Mac 버전은 macOS에서만 종료할 수 있습니다."]
        return mac_kill_all()
    return False, ["지원하지 않는 실행 버전입니다."]


def kill_all_local_for_exit():
    """Kill all KakaoTalk processes for the current OS when the launcher closes."""
    logs = []
    ok = True

    if is_windows():
        result_ok, result_logs = windows_kill_all()
        ok = ok and result_ok
        logs.extend(result_logs)
    elif is_mac():
        result_ok, result_logs = mac_kill_all()
        ok = ok and result_ok
        logs.extend(result_logs)
    else:
        logs.append("지원하지 않는 운영체제입니다.")

    RUN_META.clear()
    return ok, logs


# ======================================================
# GUI
# ======================================================
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("카카오톡 독립실행기")
        self.root.geometry("920x680")
        self.root.minsize(820, 620)
        self.root.configure(bg="#0f1117")
        try:
            self._app_icon = tk.PhotoImage(data=APP_ICON_BASE64)
            self.root.iconphoto(True, self._app_icon)
        except Exception:
            pass

        self._closing = False
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.lang = "ko"
        self.config = {}
        self.access_code = ""
        self.selected_mode = "windows" if is_windows() else ("mac" if is_mac() else "windows")

        self.texts = {
            "ko": {
                "title": "카카오톡 독립실행기",
                "code_title": "접속 코드 입력",
                "login": "입장",
                "logout": "로그아웃",
                "translate": "翻译成中文",
                "mode": "실행 버전 선택",
                "windows": "Windows 버전",
                "mac": "Mac 버전",
                "launch": "독립 실행",
                "kill_all": "전체 종료",
                "refresh": "새로고침",
                "profiles": "현재 실행중 프로필",
                "profile": "프로필",
                "env_done": "실행환경 적용완료",
                "run_time": "실행시간",
                "close": "종료",
                "no_profiles": "현재 실행중인 프로필 없음",
                "logs": "로그",
                "clear": "로그 지우기",
                "status_ready": "인증 완료",
                "need_code": "코드를 입력하세요.",
                "bad_code": "코드가 올바르지 않습니다.",
                "disabled": "현재 사용이 중지되었습니다.",
                "server_fail": "서버 연결 실패",
                "footer": "프로그램 제작의뢰 Telegram @oh_Yandex",
            },
            "zh": {
                "title": "KakaoTalk 独立启动器",
                "code_title": "输入访问代码",
                "login": "进入",
                "logout": "退出登录",
                "translate": "한국어로 번역",
                "mode": "选择启动版本",
                "windows": "Windows 版本",
                "mac": "Mac 版本",
                "launch": "独立启动",
                "kill_all": "全部关闭",
                "refresh": "刷新",
                "profiles": "当前运行中的配置",
                "profile": "配置",
                "env_done": "运行环境已应用",
                "run_time": "运行时间",
                "close": "关闭",
                "no_profiles": "当前没有运行中的配置",
                "logs": "日志",
                "clear": "清空日志",
                "status_ready": "认证完成",
                "need_code": "请输入代码。",
                "bad_code": "代码不正确。",
                "disabled": "当前已停用。",
                "server_fail": "服务器连接失败",
                "footer": "程序定制委托 Telegram @oh_Yandex",
            },
        }

        self.build_login()
        self.build_main()
        self.show_login()

        self.root.after(2000, self.periodic_refresh)

    def t(self, key):
        return self.texts[self.lang][key]

    def style_btn(self, btn, bg="#2b3445", fg="#f6f7fb"):
        btn.configure(
            bg=bg,
            fg=fg,
            activebackground=bg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            font=("Malgun Gothic", 10, "bold"),
            cursor="hand2",
            padx=10,
            pady=8,
        )

    def build_login(self):
        self.login_frame = tk.Frame(self.root, bg="#000000")

        box = tk.Frame(self.login_frame, bg="#161a23", highlightbackground="#303747", highlightthickness=1)
        box.place(relx=0.5, rely=0.5, anchor="center", width=360, height=230)

        self.login_title = tk.Label(box, text="", bg="#161a23", fg="#f6f7fb", font=("Malgun Gothic", 18, "bold"))
        self.login_title.pack(pady=(28, 14))

        self.code_entry = tk.Entry(box, bg="#0b0f17", fg="#f6f7fb", insertbackground="#f6f7fb", relief="flat", font=("Malgun Gothic", 14), justify="center")
        self.code_entry.pack(fill="x", padx=28, ipady=8)
        self.code_entry.bind("<Return>", lambda e: self.login())

        self.login_btn = tk.Button(box, text="", command=self.login)
        self.style_btn(self.login_btn, "#ffd400", "#111111")
        self.login_btn.pack(fill="x", padx=28, pady=(12, 6))

        self.login_msg = tk.Label(box, text="", bg="#161a23", fg="#99a2b4", font=("Malgun Gothic", 9))
        self.login_msg.pack()

    def build_main(self):
        self.main_frame = tk.Frame(self.root, bg="#0f1117")

        top = tk.Frame(self.main_frame, bg="#161a23", height=74)
        top.pack(fill="x")
        top.pack_propagate(False)

        logo = tk.Label(top, text="Y", bg="#000000", fg="#ffffff", font=("Arial", 22, "bold"), width=3)
        logo.pack(side="left", padx=(16, 10), pady=14)

        title_box = tk.Frame(top, bg="#161a23")
        title_box.pack(side="left", fill="both", expand=True)
        self.title_label = tk.Label(title_box, text="", bg="#161a23", fg="#f6f7fb", font=("Malgun Gothic", 17, "bold"), anchor="w")
        self.title_label.pack(fill="both", expand=True, pady=(0, 0))
        self.status_label = tk.Label(title_box, text="", bg="#161a23", fg="#99a2b4", font=("Malgun Gothic", 9), anchor="w")

        self.logout_btn = tk.Button(top, text="", command=self.logout)
        self.style_btn(self.logout_btn, "#3a1f27", "#ffb3b3")
        self.logout_btn.pack(side="right", padx=(4, 14), pady=18)

        self.lang_btn = tk.Button(top, text="", command=self.toggle_lang)
        self.style_btn(self.lang_btn, "#2b3445", "#f6f7fb")
        self.lang_btn.pack(side="right", padx=4, pady=18)

        body = tk.Frame(self.main_frame, bg="#0f1117")
        body.pack(fill="both", expand=True, padx=16, pady=16)

        mode_box = tk.Frame(body, bg="#1f2531", highlightbackground="#303747", highlightthickness=1)
        mode_box.pack(fill="x", pady=(0, 12))

        self.mode_label = tk.Label(mode_box, text="", bg="#1f2531", fg="#f6f7fb", font=("Malgun Gothic", 11, "bold"), anchor="w")
        self.mode_label.pack(fill="x", padx=12, pady=(10, 4))

        mode_buttons = tk.Frame(mode_box, bg="#1f2531")
        mode_buttons.pack(fill="x", padx=12, pady=(0, 10))

        self.win_btn = tk.Button(mode_buttons, text="", command=lambda: self.set_mode("windows"))
        self.style_btn(self.win_btn, "#2b3445", "#f6f7fb")
        self.win_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.mac_btn = tk.Button(mode_buttons, text="", command=lambda: self.set_mode("mac"))
        self.style_btn(self.mac_btn, "#2b3445", "#f6f7fb")
        self.mac_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))

        actions = tk.Frame(body, bg="#0f1117")
        actions.pack(fill="x", pady=(0, 12))

        self.launch_btn = tk.Button(actions, text="", command=self.launch_clicked)
        self.style_btn(self.launch_btn, "#ffd400", "#111111")
        self.launch_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.kill_all_btn = tk.Button(actions, text="", command=self.kill_all_clicked)
        self.style_btn(self.kill_all_btn, "#2b3445", "#f6f7fb")
        self.kill_all_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        split = tk.Frame(body, bg="#0f1117")
        split.pack(fill="both", expand=True, pady=(0, 8))

        left_panel = tk.Frame(split, bg="#0f1117")
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 8))

        right_panel = tk.Frame(split, bg="#0f1117", width=430)
        right_panel.pack(side="right", fill="y", padx=(8, 0))
        right_panel.pack_propagate(False)

        log_head = tk.Frame(left_panel, bg="#0f1117")
        log_head.pack(fill="x")
        self.log_label = tk.Label(log_head, text="", bg="#0f1117", fg="#f6f7fb", font=("Malgun Gothic", 12, "bold"), anchor="w")
        self.log_label.pack(side="left")
        self.clear_btn = tk.Button(log_head, text="", command=self.clear_log)
        self.style_btn(self.clear_btn, "#2b3445", "#f6f7fb")
        self.clear_btn.pack(side="right")

        self.log_text = tk.Text(left_panel, height=18, bg="#080b10", fg="#d9e2f1", insertbackground="#f6f7fb", relief="flat", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, pady=(6, 0))

        prof_head = tk.Frame(right_panel, bg="#0f1117")
        prof_head.pack(fill="x")
        self.profile_label = tk.Label(prof_head, text="", bg="#0f1117", fg="#f6f7fb", font=("Malgun Gothic", 12, "bold"), anchor="w")
        self.profile_label.pack(side="left")
        self.refresh_btn = tk.Button(prof_head, text="", command=self.refresh_profiles)
        self.style_btn(self.refresh_btn, "#2b3445", "#f6f7fb")
        self.refresh_btn.pack(side="right")

        self.profile_container = tk.Frame(right_panel, bg="#1f2531", highlightbackground="#303747", highlightthickness=1)
        self.profile_container.pack(fill="both", expand=True, pady=(6, 0))

        self.profile_canvas = tk.Canvas(
            self.profile_container,
            bg="#1f2531",
            highlightthickness=0,
            bd=0,
        )
        self.profile_scrollbar = tk.Scrollbar(
            self.profile_container,
            orient="vertical",
            command=self.profile_canvas.yview,
        )
        self.profile_inner = tk.Frame(self.profile_canvas, bg="#1f2531")

        self.profile_inner.bind(
            "<Configure>",
            lambda e: self.profile_canvas.configure(scrollregion=self.profile_canvas.bbox("all")),
        )
        self.profile_window = self.profile_canvas.create_window(
            (0, 0),
            window=self.profile_inner,
            anchor="nw",
        )
        self.profile_canvas.configure(yscrollcommand=self.profile_scrollbar.set)

        self.profile_canvas.pack(side="left", fill="both", expand=True)
        self.profile_scrollbar.pack(side="right", fill="y")
        self.profile_canvas.bind(
            "<Configure>",
            lambda e: self.profile_canvas.itemconfigure(self.profile_window, width=e.width),
        )
        self.profile_canvas.bind("<MouseWheel>", self._on_profile_mousewheel)
        self.profile_inner.bind("<MouseWheel>", self._on_profile_mousewheel)

        self.footer_label = tk.Label(body, text="", bg="#0f1117", fg="#687084", font=("Malgun Gothic", 8))
        self.footer_label.pack(fill="x")

    def apply_text(self):
        self.login_title.configure(text=self.t("code_title") + "\n输入访问代码" if self.lang == "ko" else "输入访问代码\n접속 코드 입력")
        self.login_btn.configure(text=self.t("login"))
        self.title_label.configure(text=self.t("title"))
        self.status_label.configure(text="")
        self.logout_btn.configure(text=self.t("logout"))
        self.lang_btn.configure(text=self.t("translate"))
        self.mode_label.configure(text=self.t("mode"))
        self.win_btn.configure(text=self.t("windows"))
        self.mac_btn.configure(text=self.t("mac"))
        self.update_mode_buttons()
        self.launch_btn.configure(text=self.t("launch"))
        self.kill_all_btn.configure(text=self.t("kill_all"))
        self.refresh_btn.configure(text=self.t("refresh"))
        self.profile_label.configure(text=self.t("profiles"))
        self.log_label.configure(text=self.t("logs"))
        self.clear_btn.configure(text=self.t("clear"))
        self.footer_label.configure(text=self.t("footer"))

    def set_mode(self, mode):
        self.selected_mode = mode
        self.update_mode_buttons()
        self.refresh_profiles()

    def update_mode_buttons(self):
        if not hasattr(self, "win_btn"):
            return
        if self.selected_mode == "windows":
            self.win_btn.configure(bg="#ffd400", fg="#111111", activebackground="#ffd400", activeforeground="#111111")
            self.mac_btn.configure(bg="#2b3445", fg="#f6f7fb", activebackground="#2b3445", activeforeground="#f6f7fb")
        else:
            self.mac_btn.configure(bg="#ffd400", fg="#111111", activebackground="#ffd400", activeforeground="#111111")
            self.win_btn.configure(bg="#2b3445", fg="#f6f7fb", activebackground="#2b3445", activeforeground="#f6f7fb")


    def show_login(self):
        self.apply_text()
        self.main_frame.pack_forget()
        self.login_frame.pack(fill="both", expand=True)
        self.code_entry.focus_set()

    def show_main(self):
        self.apply_text()
        self.login_frame.pack_forget()
        self.main_frame.pack(fill="both", expand=True)
        self.refresh_profiles()

    def login(self):
        code = self.code_entry.get().strip()
        if not code:
            self.login_msg.configure(text=self.t("need_code"))
            return

        self.login_btn.configure(state="disabled")
        self.login_msg.configure(text="확인중... / 正在确认...")
        threading.Thread(target=self._login_worker, args=(code,), daemon=True).start()

    def _login_worker(self, code):
        ok, role, enabled, reason = remote_check_code(code)
        def done():
            self.login_btn.configure(state="normal")
            if not ok:
                if reason == "disabled":
                    self.login_msg.configure(text=self.t("disabled"))
                elif reason == "server_error":
                    self.login_msg.configure(text=self.t("server_fail"))
                else:
                    self.login_msg.configure(text=self.t("bad_code"))
                return

            self.access_code = code
            self.add_log("접속 인증 완료")
            self.show_main()
        self.root.after(0, done)

    def try_saved_login(self):
        threading.Thread(target=self._saved_worker, daemon=True).start()

    def _saved_worker(self):
        ok, role, enabled, reason = remote_check_code(self.access_code)
        self.root.after(0, self.show_main if ok else self.show_login)

    def logout(self):
        self.access_code = ""
        self.code_entry.delete(0, "end")
        self.login_msg.configure(text="")
        self.show_login()

    def toggle_lang(self):
        self.lang = "zh" if self.lang == "ko" else "ko"
        self.apply_text()
        self.refresh_profiles()

    def add_log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")

    def clear_log(self):
        self.log_text.delete("1.0", "end")

    def check_before_action(self):
        ok, role, enabled, reason = remote_check_code(self.access_code)
        if ok:
            return True
        if reason == "disabled":
            self.add_log("현재 사용이 중지되었습니다.")
            messagebox.showwarning("Stopped", self.t("disabled"))
        elif reason == "server_error":
            self.add_log("서버 연결 실패")
            messagebox.showwarning("Server", self.t("server_fail"))
        else:
            self.add_log("코드 확인 실패")
            self.logout()
        return False

    def launch_clicked(self):
        self.launch_btn.configure(state="disabled")
        self.add_log("요청 처리중...")
        threading.Thread(target=self._launch_worker, daemon=True).start()

    def _launch_worker(self):
        if not self.check_before_action():
            self.root.after(0, lambda: self.launch_btn.configure(state="normal"))
            return
        ok, logs = launch_by_mode(self.selected_mode)
        def done():
            for line in logs:
                self.add_log(line)
            self.refresh_profiles()
            self.launch_btn.configure(state="normal")
        self.root.after(0, done)

    def kill_all_clicked(self):
        self.add_log("전체 종료 요청")
        threading.Thread(target=self._kill_all_worker, daemon=True).start()

    def _kill_all_worker(self):
        ok, logs = kill_all_by_mode(self.selected_mode)
        if ok:
            RUN_META.clear()
        self.root.after(0, lambda: [self.add_log(x) for x in logs] or self.refresh_profiles())

    def _on_profile_mousewheel(self, event):
        try:
            if not hasattr(self, "profile_canvas") or not self.main_frame.winfo_ismapped():
                return
            bbox = self.profile_canvas.bbox("all")
            if not bbox:
                return
            content_height = bbox[3] - bbox[1]
            visible_height = self.profile_canvas.winfo_height()
            if content_height <= visible_height:
                self.profile_canvas.yview_moveto(0)
                return
            self.profile_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _bind_profile_wheel(self, widget):
        try:
            widget.bind("<MouseWheel>", self._on_profile_mousewheel)
        except Exception:
            pass

    def refresh_profiles(self):
        target = getattr(self, "profile_inner", None)
        if target is None:
            return

        for w in target.winfo_children():
            w.destroy()

        pids = get_pids_by_mode(self.selected_mode)
        if not pids:
            RUN_META.clear()
        else:
            cleanup_meta(pids)

        try:
            self.profile_canvas.yview_moveto(0)
        except Exception:
            pass

        if not pids:
            empty = tk.Label(
                target,
                text=self.t("no_profiles"),
                bg="#1f2531",
                fg="#99a2b4",
                font=("Malgun Gothic", 10, "bold"),
                anchor="n",
                pady=12,
            )
            empty.pack(fill="x", anchor="n")
            self._bind_profile_wheel(empty)
            try:
                self.profile_canvas.configure(scrollregion=self.profile_canvas.bbox("all"))
            except Exception:
                pass
            return

        for i, pid in enumerate(pids, 1):
            meta = RUN_META.get(pid, {})
            row = tk.Frame(target, bg="#10151f", highlightbackground="#303747", highlightthickness=1)
            row.pack(fill="x", padx=6, pady=3, anchor="n")
            self._bind_profile_wheel(row)

            profile = tk.Label(
                row,
                text=f"{self.t('profile')} {i}",
                bg="#10151f",
                fg="#ffd400",
                font=("Malgun Gothic", 8, "bold"),
                width=8,
                anchor="w",
            )
            profile.pack(side="left", padx=(8, 3), pady=7)
            self._bind_profile_wheel(profile)

            pid_line = tk.Label(
                row,
                text=f"PID {pid}",
                bg="#10151f",
                fg="#f6f7fb",
                font=("Consolas", 8, "bold"),
                width=9,
                anchor="w",
            )
            pid_line.pack(side="left", padx=(0, 3), pady=7)
            self._bind_profile_wheel(pid_line)

            env_line = tk.Label(
                row,
                text=self.t("env_done"),
                bg="#10151f",
                fg="#33c481",
                font=("Malgun Gothic", 8, "bold"),
                width=14 if self.lang == "ko" else 15,
                anchor="w",
            )
            env_line.pack(side="left", padx=(0, 3), pady=7)
            self._bind_profile_wheel(env_line)

            time_line = tk.Label(
                row,
                text=f"{self.t('run_time')} {meta.get('started_at', '-')}",
                bg="#10151f",
                fg="#99a2b4",
                font=("Malgun Gothic", 7),
                width=12 if self.lang == "ko" else 13,
                anchor="w",
            )
            time_line.pack(side="left", padx=(0, 3), pady=7)
            self._bind_profile_wheel(time_line)

            btn = tk.Button(row, text=self.t("close"), command=lambda p=pid: self.kill_one_clicked(p))
            self.style_btn(btn, "#3a1f27", "#ffb3b3")
            btn.configure(font=("Malgun Gothic", 8, "bold"), padx=7, pady=4)
            btn.pack(side="right", padx=(3, 7), pady=4)
            self._bind_profile_wheel(btn)

        try:
            self.profile_inner.update_idletasks()
            self.profile_canvas.configure(scrollregion=self.profile_canvas.bbox("all"))
        except Exception:
            pass

    def kill_one_clicked(self, pid):
        self.add_log(f"PID {pid} 종료 요청")
        threading.Thread(target=self._kill_one_worker, args=(pid,), daemon=True).start()

    def _kill_one_worker(self, pid):
        ok, logs = kill_pid_by_mode(self.selected_mode, pid)
        self.root.after(0, lambda: [self.add_log(x) for x in logs] or self.refresh_profiles())

    def periodic_refresh(self):
        if self.main_frame.winfo_ismapped():
            self.refresh_profiles()
        self.root.after(3000, self.periodic_refresh)

    def on_close(self):
        if getattr(self, "_closing", False):
            return
        self._closing = True

        try:
            self.add_log("프로그램 종료중: 카카오톡 전체 종료")
        except Exception:
            pass

        def worker():
            try:
                ok, logs = kill_all_local_for_exit()
            except Exception as e:
                logs = ["종료 처리 오류: " + str(e)]

            def finish():
                try:
                    for line in logs:
                        self.add_log(line)
                    RUN_META.clear()
                    if hasattr(self, "profile_inner"):
                        for w in self.profile_inner.winfo_children():
                            w.destroy()
                except Exception:
                    pass

                try:
                    self.root.destroy()
                except Exception:
                    os._exit(0)

            try:
                self.root.after(0, finish)
            except Exception:
                os._exit(0)

        threading.Thread(target=worker, daemon=True).start()


    def run(self):
        self.apply_text()
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
