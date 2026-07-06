# -*- coding: utf-8 -*-
"""
Kakao Local Program Launcher v26 - macOS only
- Real desktop program UI, not web
- Always asks access code on every program start
- macOS-only launcher for GitHub Actions Mac build
- Control endpoint is hidden from UI and not stored as a plain URL string
- Checks access code with control server
- Server only controls code/enabled state
- KakaoTalk launches on the user's local Mac
- Bilingual UI/logs: Korean <-> Chinese
- Stored log events re-render when language changes
- Failure diagnostics are logged and can be copied from the UI
- Standard library only
"""

import os
import sys
import json
import time
import subprocess
import threading
import plistlib
from pathlib import Path
from urllib.request import Request, urlopen
import tkinter as tk
from tkinter import messagebox


# ======================================================
# Control server endpoint
# ======================================================
def _control_endpoint():
    # Built at runtime so the plain address is not shown in the UI.
    scheme = "".join(chr(x) for x in (104, 116, 116, 112))
    host = ".".join(str(x) for x in (167, 172, 95, 226))
    port = str(1000 + 70)
    return scheme + "://" + host + ":" + port


def _api_url(path):
    return _control_endpoint().rstrip("/") + path


APP_ICON_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAbElEQVR42u2XOw4AIAhDuf/5vA/uGo3C8zN06EbLU0iMZmb+WJ8BeDnXbJDdF52AmORuFdPNxztAQSzkpMwO+JGQjA8Ni9SzoYEb404WHBcz28TCxhes1dW3AGouAAEIQAACEIAAPvyaCeC2Kq8dufXUe6lPAAAAAElFTkSuQmCC"
MAC_PROFILE_ROOT = Path.home() / "Library" / "Application Support" / "KakaoLocalLauncher" / "Profiles"
RUN_META = {}
RUN_SEQ = 0


# ======================================================
# Text resources
# ======================================================
UI_TEXTS = {
    "ko": {
        "title": "카카오톡 독립실행기",
        "subtitle": "macOS 전용 실행기",
        "code_title": "접속 코드 입력",
        "code_title_alt": "输入访问代码",
        "login": "입장",
        "logout": "로그아웃",
        "translate": "翻译成中文",
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
        "copy_logs": "로그 복사",
        "need_code": "코드를 입력하세요.",
        "bad_code": "코드가 올바르지 않습니다.",
        "disabled": "현재 사용이 중지되었습니다.",
        "server_fail": "서버 연결 실패",
        "copied": "로그가 클립보드에 복사되었습니다.",
        "mac_only_title": "macOS 전용",
        "mac_only_body": "이 실행기는 macOS에서만 실행할 수 있습니다.",
        "footer": "프로그램 제작의뢰 Telegram @oh_Yandex",
    },
    "zh": {
        "title": "KakaoTalk 独立启动器",
        "subtitle": "macOS 专用启动器",
        "code_title": "输入访问代码",
        "code_title_alt": "접속 코드 입력",
        "login": "进入",
        "logout": "退出登录",
        "translate": "한국어로 번역",
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
        "copy_logs": "复制日志",
        "need_code": "请输入代码。",
        "bad_code": "代码不正确。",
        "disabled": "当前已停用。",
        "server_fail": "服务器连接失败",
        "copied": "日志已复制到剪贴板。",
        "mac_only_title": "macOS 专用",
        "mac_only_body": "此启动器只能在 macOS 上运行。",
        "footer": "程序定制委托 Telegram @oh_Yandex",
    },
}


LOG_TEXTS = {
    "ko": {
        "app_started": "실행기 시작",
        "not_macos": "차단: 현재 운영체제는 macOS가 아님 / platform={platform}",
        "auth_checking": "접속 코드 확인중",
        "auth_ok": "접속 인증 완료 / role={role}",
        "auth_failed_invalid": "접속 인증 실패: 코드 불일치",
        "auth_failed_disabled": "접속 인증 실패: 사용 중지 상태",
        "auth_failed_server": "접속 인증 실패: 서버 연결 실패",
        "precheck_start": "실행 전 서버 상태 확인",
        "precheck_ok": "실행 전 서버 상태 정상",
        "precheck_disabled": "실행 차단: 서버 사용 중지 상태",
        "precheck_invalid": "실행 차단: 코드 재확인 실패",
        "precheck_server": "실행 차단: 서버 연결 실패",
        "launch_requested": "독립 실행 요청",
        "launch_prepare": "macOS 독립 실행 준비",
        "process_before": "실행 전 KakaoTalk 메인 프로세스 수: {count}",
        "app_search_start": "KakaoTalk.app 검색 시작",
        "app_candidate_found": "KakaoTalk.app 발견: {path}",
        "app_candidate_missing": "KakaoTalk.app 후보 없음: {path}",
        "app_mdfind_found": "Spotlight 검색 결과 발견: {path}",
        "app_mdfind_empty": "Spotlight 검색 결과 없음",
        "app_missing": "실행 실패: KakaoTalk.app을 찾지 못함",
        "plist_read_ok": "앱 번들 정보 확인 완료: {exe_name}",
        "plist_read_fail": "앱 번들 정보 확인 실패: 기본 실행파일명 사용 / error={error}",
        "exe_found": "KakaoTalk 실행 파일 발견: {path}",
        "exe_missing": "실행 실패: 앱 번들 내부 실행 파일 없음",
        "profile_created": "Mac 독립 프로필 생성: {name}",
        "profile_create_error": "독립 프로필 생성 오류: {error}",
        "env_applied": "독립 실행 환경 적용 완료 / profile={profile}",
        "direct_start": "직접 실행 시도: KakaoTalk.app 내부 실행파일",
        "direct_pid": "직접 실행 요청 완료 / PID {pid}",
        "direct_error": "직접 실행 오류: {error}",
        "direct_after": "직접 실행 후 KakaoTalk 메인 프로세스 수: {count}",
        "direct_no_new": "직접 실행 결과: 새 메인 프로세스 증가 없음",
        "stderr_tail": "stderr 진단: {text}",
        "open_start": "보조 실행 시도: open -n KakaoTalk.app",
        "open_requested": "open -n 실행 요청 완료",
        "open_error": "open -n 실행 오류: {error}",
        "open_after": "보조 실행 후 KakaoTalk 메인 프로세스 수: {count}",
        "launch_success": "실행 성공: 새 프로세스 감지 / 총 {count}개 실행중",
        "launch_fail_no_new": "실행 실패: 새 KakaoTalk 메인 프로세스가 감지되지 않음",
        "launch_fail_reason": "실패 원인 후보: 카카오톡 앱 자체 단일 실행 차단, macOS 보안 정책, 앱 손상, 권한 문제, 또는 이미 실행 중인 인스턴스 재사용",
        "copy_required": "진단 필요: 로그 복사 후 전달",
        "refresh_profiles": "프로필 목록 새로고침",
        "kill_all_request": "전체 종료 요청",
        "kill_all_start": "카카오톡 전체 종료 시작 / 종료 전 {before}개",
        "kill_all_osascript": "정상 종료 명령 실행: osascript quit",
        "kill_all_term": "프로세스 종료 명령 실행: pkill -TERM KakaoTalk",
        "kill_all_force": "잔여 프로세스 강제 종료 실행: pkill -9 KakaoTalk",
        "kill_all_done": "카카오톡 전체 종료 완료: 종료 전 {before}개 / 남은 {after}개",
        "kill_one_request": "프로필 종료 요청 / PID {pid}",
        "kill_pid_start": "PID 종료 시도: {pid}",
        "kill_pid_term": "PID TERM 종료 명령 실행: {pid}",
        "kill_pid_force": "PID 강제 종료 명령 실행: {pid}",
        "kill_pid_done": "PID 종료 완료: {pid}",
        "kill_pid_failed": "PID 종료 실패 또는 잔여 프로세스 존재: {pid}",
        "pid_invalid": "PID 오류: 올바르지 않은 PID",
        "clear_log": "로그 지우기",
        "copy_log": "로그 복사 완료",
        "lang_ko": "언어 전환: 한국어",
        "lang_zh": "语言切换：中文",
        "close_start": "프로그램 종료 처리 시작: 카카오톡 전체 종료",
        "close_error": "프로그램 종료 처리 오류: {error}",
    },
    "zh": {
        "app_started": "启动器已启动",
        "not_macos": "已阻止：当前系统不是 macOS / platform={platform}",
        "auth_checking": "正在验证访问代码",
        "auth_ok": "访问认证完成 / role={role}",
        "auth_failed_invalid": "访问认证失败：代码不匹配",
        "auth_failed_disabled": "访问认证失败：当前已停用",
        "auth_failed_server": "访问认证失败：服务器连接失败",
        "precheck_start": "启动前检查服务器状态",
        "precheck_ok": "启动前服务器状态正常",
        "precheck_disabled": "启动已阻止：服务器已停用",
        "precheck_invalid": "启动已阻止：代码复检失败",
        "precheck_server": "启动已阻止：服务器连接失败",
        "launch_requested": "独立启动请求",
        "launch_prepare": "macOS 独立启动准备",
        "process_before": "启动前 KakaoTalk 主进程数量：{count}",
        "app_search_start": "开始查找 KakaoTalk.app",
        "app_candidate_found": "找到 KakaoTalk.app：{path}",
        "app_candidate_missing": "未找到 KakaoTalk.app 候选路径：{path}",
        "app_mdfind_found": "Spotlight 搜索结果：{path}",
        "app_mdfind_empty": "Spotlight 无搜索结果",
        "app_missing": "启动失败：未找到 KakaoTalk.app",
        "plist_read_ok": "应用包信息确认完成：{exe_name}",
        "plist_read_fail": "应用包信息确认失败：使用默认可执行文件名 / error={error}",
        "exe_found": "找到 KakaoTalk 可执行文件：{path}",
        "exe_missing": "启动失败：应用包内部没有可执行文件",
        "profile_created": "Mac 独立配置已创建：{name}",
        "profile_create_error": "独立配置创建错误：{error}",
        "env_applied": "独立启动环境已应用 / profile={profile}",
        "direct_start": "直接启动尝试：KakaoTalk.app 内部可执行文件",
        "direct_pid": "直接启动请求完成 / PID {pid}",
        "direct_error": "直接启动错误：{error}",
        "direct_after": "直接启动后 KakaoTalk 主进程数量：{count}",
        "direct_no_new": "直接启动结果：没有新增主进程",
        "stderr_tail": "stderr 诊断：{text}",
        "open_start": "辅助启动尝试：open -n KakaoTalk.app",
        "open_requested": "open -n 启动请求完成",
        "open_error": "open -n 启动错误：{error}",
        "open_after": "辅助启动后 KakaoTalk 主进程数量：{count}",
        "launch_success": "启动成功：检测到新进程 / 当前共 {count} 个",
        "launch_fail_no_new": "启动失败：未检测到新的 KakaoTalk 主进程",
        "launch_fail_reason": "失败原因候选：KakaoTalk 应用自身限制单实例、macOS 安全策略、应用损坏、权限问题，或复用了已运行实例",
        "copy_required": "需要诊断：复制日志后发送",
        "refresh_profiles": "刷新配置列表",
        "kill_all_request": "全部关闭请求",
        "kill_all_start": "开始关闭全部 KakaoTalk / 关闭前 {before} 个",
        "kill_all_osascript": "执行正常退出命令：osascript quit",
        "kill_all_term": "执行进程结束命令：pkill -TERM KakaoTalk",
        "kill_all_force": "执行残留进程强制结束：pkill -9 KakaoTalk",
        "kill_all_done": "全部 KakaoTalk 关闭完成：关闭前 {before} 个 / 剩余 {after} 个",
        "kill_one_request": "配置关闭请求 / PID {pid}",
        "kill_pid_start": "尝试结束 PID：{pid}",
        "kill_pid_term": "执行 PID TERM 结束命令：{pid}",
        "kill_pid_force": "执行 PID 强制结束命令：{pid}",
        "kill_pid_done": "PID 已结束：{pid}",
        "kill_pid_failed": "PID 结束失败或仍有残留进程：{pid}",
        "pid_invalid": "PID 错误：PID 无效",
        "clear_log": "清空日志",
        "copy_log": "日志复制完成",
        "lang_ko": "언어 전환: 한국어",
        "lang_zh": "语言切换：中文",
        "close_start": "程序退出处理开始：关闭全部 KakaoTalk",
        "close_error": "程序退出处理错误：{error}",
    },
}


def is_mac():
    return sys.platform == "darwin"


def now_time():
    return time.strftime("%H:%M:%S")


def normalize_proxy(proxy: str) -> str:
    proxy = (proxy or "").strip()
    if not proxy:
        return ""
    if proxy.startswith(("http://", "https://", "socks5://")):
        return proxy
    return "http://" + proxy


def safe_format(template, params):
    try:
        return template.format(**params)
    except Exception:
        return template


def log_text(lang, key, params=None):
    params = params or {}
    template = LOG_TEXTS.get(lang, LOG_TEXTS["ko"]).get(key) or LOG_TEXTS["ko"].get(key) or key
    return safe_format(template, params)


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
    except Exception:
        return False, "user", False, "server_error"


def run_quiet(args, timeout=None):
    try:
        return subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            errors="ignore",
            timeout=timeout,
        )
    except Exception as e:
        class Result:
            stdout = ""
            stderr = str(e)
            returncode = 1
        return Result()


def register_pid(pid, mode="mac", profile_dir=""):
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
            "profile_dir": str(profile_dir or ""),
            "started_at": now_time(),
        }


def cleanup_meta(active_pids):
    active = set(int(x) for x in active_pids)
    for pid in list(RUN_META.keys()):
        if int(pid) not in active:
            RUN_META.pop(pid, None)


# ======================================================
# macOS launcher logic
# ======================================================
def mac_process_rows():
    if not is_mac():
        return []
    rows = []
    r = run_quiet(["ps", "-axo", "pid=,command="])
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        cmd = parts[1]
        low = cmd.lower()
        if pid == os.getpid():
            continue
        if "kakaotalk" not in low:
            continue
        rows.append({"pid": pid, "cmd": cmd})
    return rows


def mac_list_main_pids():
    pids = []
    for row in mac_process_rows():
        cmd = row["cmd"]
        low = cmd.lower()
        if "helper" in low:
            continue
        if "kakaotalk.app/contents/macos/kakaotalk" in low or low.rstrip().endswith("/kakaotalk") or low.rstrip().endswith(" kakaotalk"):
            pids.append(row["pid"])
    return sorted(set(pids))


def append_log(logs, key, **params):
    logs.append((key, params))


def mac_find_app(logs):
    append_log(logs, "app_search_start")
    candidates = [
        "/Applications/KakaoTalk.app",
        str(Path.home() / "Applications" / "KakaoTalk.app"),
    ]
    for p in candidates:
        if os.path.exists(p):
            append_log(logs, "app_candidate_found", path=p)
            return p
        append_log(logs, "app_candidate_missing", path=p)

    # Fallback: Spotlight can find non-standard installation paths.
    r = run_quiet(["mdfind", "kMDItemFSName == 'KakaoTalk.app'"], timeout=3)
    for line in (r.stdout or "").splitlines():
        p = line.strip()
        if p.endswith("KakaoTalk.app") and os.path.exists(p):
            append_log(logs, "app_mdfind_found", path=p)
            return p
    append_log(logs, "app_mdfind_empty")
    return None


def mac_app_executable(app_path, logs):
    app_path = Path(app_path)
    plist_path = app_path / "Contents" / "Info.plist"
    exe_name = "KakaoTalk"
    try:
        with plist_path.open("rb") as f:
            info = plistlib.load(f)
        exe_name = str(info.get("CFBundleExecutable") or exe_name)
        append_log(logs, "plist_read_ok", exe_name=exe_name)
    except Exception as e:
        append_log(logs, "plist_read_fail", error=str(e))

    exe_path = app_path / "Contents" / "MacOS" / exe_name
    if exe_path.exists() and os.access(str(exe_path), os.X_OK):
        append_log(logs, "exe_found", path=str(exe_path))
        return str(exe_path)

    macos_dir = app_path / "Contents" / "MacOS"
    try:
        for p in macos_dir.iterdir():
            if p.is_file() and os.access(str(p), os.X_OK):
                append_log(logs, "exe_found", path=str(p))
                return str(p)
    except Exception as e:
        append_log(logs, "plist_read_fail", error=str(e))

    append_log(logs, "exe_missing")
    return ""


def mac_profile_dir_for_next_instance(logs):
    try:
        MAC_PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        append_log(logs, "profile_create_error", error=str(e))

    active_count = len(mac_list_main_pids())
    for idx in range(1, 300):
        p = MAC_PROFILE_ROOT / f"profile_{idx:03d}"
        marker = p / ".launcher_active"
        if idx > active_count or not marker.exists():
            try:
                p.mkdir(parents=True, exist_ok=True)
                (p / "Library" / "Application Support").mkdir(parents=True, exist_ok=True)
                (p / "Library" / "Preferences").mkdir(parents=True, exist_ok=True)
                (p / "Library" / "Caches").mkdir(parents=True, exist_ok=True)
                (p / "tmp").mkdir(parents=True, exist_ok=True)
                marker.write_text(str(time.time()), encoding="utf-8")
                append_log(logs, "profile_created", name=p.name)
            except Exception as e:
                append_log(logs, "profile_create_error", error=str(e))
            return p

    p = MAC_PROFILE_ROOT / f"profile_{int(time.time())}"
    try:
        p.mkdir(parents=True, exist_ok=True)
        append_log(logs, "profile_created", name=p.name)
    except Exception as e:
        append_log(logs, "profile_create_error", error=str(e))
    return p


def mac_launch_env(profile_dir, proxy=""):
    env = os.environ.copy()
    profile_dir = Path(profile_dir)
    tmp_dir = profile_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    env["HOME"] = str(profile_dir)
    env["USERPROFILE"] = str(profile_dir)
    env["TMPDIR"] = str(tmp_dir)
    env["KAKAO_LOCAL_PROFILE"] = str(profile_dir)

    proxy_url = normalize_proxy(proxy)
    if proxy_url:
        env["HTTP_PROXY"] = proxy_url
        env["HTTPS_PROXY"] = proxy_url
        env["http_proxy"] = proxy_url
        env["https_proxy"] = proxy_url
    return env


def tail_file(path, max_chars=1200):
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size <= 0:
            return ""
        data = p.read_bytes()[-max_chars:]
        text = data.decode("utf-8", errors="ignore").strip()
        text = " ".join(text.split())
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text
    except Exception:
        return ""


def mac_launch(proxy=""):
    logs = []
    if not is_mac():
        append_log(logs, "not_macos", platform=sys.platform)
        return False, logs

    append_log(logs, "launch_prepare")
    before = set(mac_list_main_pids())
    append_log(logs, "process_before", count=len(before))

    app = mac_find_app(logs)
    if not app:
        append_log(logs, "app_missing")
        append_log(logs, "copy_required")
        return False, logs

    exe = mac_app_executable(app, logs)
    if not exe:
        append_log(logs, "copy_required")
        return False, logs

    profile_dir = mac_profile_dir_for_next_instance(logs)
    env = mac_launch_env(profile_dir, proxy)
    append_log(logs, "env_applied", profile=str(profile_dir))

    stdout_path = Path(profile_dir) / "launcher_stdout.log"
    stderr_path = Path(profile_dir) / "launcher_stderr.log"

    try:
        append_log(logs, "direct_start")
        out_f = open(stdout_path, "ab")
        err_f = open(stderr_path, "ab")
        try:
            proc = subprocess.Popen(
                [exe],
                cwd=os.path.dirname(exe) or None,
                env=env,
                stdout=out_f,
                stderr=err_f,
                start_new_session=True,
            )
        finally:
            out_f.close()
            err_f.close()
        append_log(logs, "direct_pid", pid=proc.pid)
    except Exception as e:
        append_log(logs, "direct_error", error=str(e))

    time.sleep(2.8)
    after_direct = set(mac_list_main_pids())
    append_log(logs, "direct_after", count=len(after_direct))
    new_pids = sorted(after_direct - before)
    if new_pids:
        for pid in new_pids:
            register_pid(pid, "mac", str(profile_dir))
        append_log(logs, "launch_success", count=len(after_direct))
        return True, logs

    append_log(logs, "direct_no_new")
    stderr_tail = tail_file(stderr_path)
    if stderr_tail:
        append_log(logs, "stderr_tail", text=stderr_tail)

    try:
        append_log(logs, "open_start")
        subprocess.Popen(
            ["open", "-n", app],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        append_log(logs, "open_requested")
    except Exception as e:
        append_log(logs, "open_error", error=str(e))

    time.sleep(2.8)
    after_open = set(mac_list_main_pids())
    append_log(logs, "open_after", count=len(after_open))
    new_pids = sorted(after_open - before)
    if new_pids:
        for pid in new_pids:
            register_pid(pid, "mac", str(profile_dir))
        append_log(logs, "launch_success", count=len(after_open))
        return True, logs

    append_log(logs, "launch_fail_no_new")
    append_log(logs, "launch_fail_reason")
    append_log(logs, "copy_required")
    return False, logs


def mac_kill_pid(pid):
    logs = []
    try:
        pid = int(pid)
    except Exception:
        append_log(logs, "pid_invalid")
        return False, logs

    append_log(logs, "kill_pid_start", pid=pid)
    run_quiet(["kill", "-TERM", str(pid)])
    append_log(logs, "kill_pid_term", pid=pid)
    time.sleep(0.8)

    if pid in mac_list_main_pids():
        run_quiet(["kill", "-9", str(pid)])
        append_log(logs, "kill_pid_force", pid=pid)
        time.sleep(0.5)

    RUN_META.pop(pid, None)
    alive = pid in mac_list_main_pids()
    if alive:
        append_log(logs, "kill_pid_failed", pid=pid)
    else:
        append_log(logs, "kill_pid_done", pid=pid)
    return not alive, logs


def mac_kill_all():
    logs = []
    before = len(mac_list_main_pids())
    append_log(logs, "kill_all_start", before=before)

    run_quiet(["osascript", "-e", 'tell application "KakaoTalk" to quit'])
    append_log(logs, "kill_all_osascript")
    time.sleep(0.8)

    run_quiet(["pkill", "-TERM", "-f", "KakaoTalk"])
    append_log(logs, "kill_all_term")
    time.sleep(0.8)

    if mac_list_main_pids():
        run_quiet(["pkill", "-9", "-f", "KakaoTalk"])
        append_log(logs, "kill_all_force")
        time.sleep(0.5)

    after = len(mac_list_main_pids())
    if after == 0:
        RUN_META.clear()
        try:
            for marker in MAC_PROFILE_ROOT.glob("profile_*/.launcher_active"):
                marker.unlink(missing_ok=True)
        except Exception:
            pass

    append_log(logs, "kill_all_done", before=before, after=after)
    return after == 0, logs


# ======================================================
# GUI
# ======================================================
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("카카오톡 독립실행기")
        self.root.geometry("880x650")
        self.root.minsize(780, 580)
        self.root.configure(bg="#0f1117")
        try:
            self._app_icon = tk.PhotoImage(data=APP_ICON_BASE64)
            self.root.iconphoto(True, self._app_icon)
        except Exception:
            pass

        self._closing = False
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.lang = "ko"
        self.access_code = ""
        self.log_entries = []

        self.build_login()
        self.build_main()
        self.show_login()
        self.add_log_key("app_started")

        if not is_mac():
            self.add_log_key("not_macos", platform=sys.platform)

        self.root.after(2500, self.periodic_refresh)

    def t(self, key):
        return UI_TEXTS[self.lang][key]

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
        self.title_label.pack(fill="x", expand=False, pady=(12, 0))
        self.subtitle_label = tk.Label(title_box, text="", bg="#161a23", fg="#99a2b4", font=("Malgun Gothic", 9), anchor="w")
        self.subtitle_label.pack(fill="x", expand=False)

        self.logout_btn = tk.Button(top, text="", command=self.logout)
        self.style_btn(self.logout_btn, "#3a1f27", "#ffb3b3")
        self.logout_btn.pack(side="right", padx=(4, 14), pady=18)

        self.lang_btn = tk.Button(top, text="", command=self.toggle_lang)
        self.style_btn(self.lang_btn, "#2b3445", "#f6f7fb")
        self.lang_btn.pack(side="right", padx=4, pady=18)

        body = tk.Frame(self.main_frame, bg="#0f1117")
        body.pack(fill="both", expand=True, padx=16, pady=16)

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

        right_panel = tk.Frame(split, bg="#0f1117", width=400)
        right_panel.pack(side="right", fill="y", padx=(8, 0))
        right_panel.pack_propagate(False)

        log_head = tk.Frame(left_panel, bg="#0f1117")
        log_head.pack(fill="x")
        self.log_label = tk.Label(log_head, text="", bg="#0f1117", fg="#f6f7fb", font=("Malgun Gothic", 12, "bold"), anchor="w")
        self.log_label.pack(side="left")

        self.clear_btn = tk.Button(log_head, text="", command=self.clear_log)
        self.style_btn(self.clear_btn, "#2b3445", "#f6f7fb")
        self.clear_btn.pack(side="right", padx=(4, 0))

        self.copy_btn = tk.Button(log_head, text="", command=self.copy_logs)
        self.style_btn(self.copy_btn, "#2b3445", "#f6f7fb")
        self.copy_btn.pack(side="right", padx=(4, 0))

        self.log_text = tk.Text(left_panel, height=18, bg="#080b10", fg="#d9e2f1", insertbackground="#f6f7fb", relief="flat", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, pady=(6, 0))

        prof_head = tk.Frame(right_panel, bg="#0f1117")
        prof_head.pack(fill="x")
        self.profile_label = tk.Label(prof_head, text="", bg="#0f1117", fg="#f6f7fb", font=("Malgun Gothic", 12, "bold"), anchor="w")
        self.profile_label.pack(side="left")
        self.refresh_btn = tk.Button(prof_head, text="", command=self.refresh_profiles_clicked)
        self.style_btn(self.refresh_btn, "#2b3445", "#f6f7fb")
        self.refresh_btn.pack(side="right")

        self.profile_container = tk.Frame(right_panel, bg="#1f2531", highlightbackground="#303747", highlightthickness=1)
        self.profile_container.pack(fill="both", expand=True, pady=(6, 0))

        self.profile_canvas = tk.Canvas(self.profile_container, bg="#1f2531", highlightthickness=0, bd=0)
        self.profile_scrollbar = tk.Scrollbar(self.profile_container, orient="vertical", command=self.profile_canvas.yview)
        self.profile_inner = tk.Frame(self.profile_canvas, bg="#1f2531")
        self.profile_inner.bind("<Configure>", lambda e: self.profile_canvas.configure(scrollregion=self.profile_canvas.bbox("all")))
        self.profile_window = self.profile_canvas.create_window((0, 0), window=self.profile_inner, anchor="nw")
        self.profile_canvas.configure(yscrollcommand=self.profile_scrollbar.set)
        self.profile_canvas.pack(side="left", fill="both", expand=True)
        self.profile_scrollbar.pack(side="right", fill="y")
        self.profile_canvas.bind("<Configure>", lambda e: self.profile_canvas.itemconfigure(self.profile_window, width=e.width))
        self.profile_canvas.bind("<MouseWheel>", self._on_profile_mousewheel)
        self.profile_inner.bind("<MouseWheel>", self._on_profile_mousewheel)

        self.footer_label = tk.Label(body, text="", bg="#0f1117", fg="#687084", font=("Malgun Gothic", 8))
        self.footer_label.pack(fill="x")

    def apply_text(self):
        self.login_title.configure(text=self.t("code_title") + "\n" + self.t("code_title_alt"))
        self.login_btn.configure(text=self.t("login"))
        self.title_label.configure(text=self.t("title"))
        self.subtitle_label.configure(text=self.t("subtitle"))
        self.logout_btn.configure(text=self.t("logout"))
        self.lang_btn.configure(text=self.t("translate"))
        self.launch_btn.configure(text=self.t("launch"))
        self.kill_all_btn.configure(text=self.t("kill_all"))
        self.refresh_btn.configure(text=self.t("refresh"))
        self.profile_label.configure(text=self.t("profiles"))
        self.log_label.configure(text=self.t("logs"))
        self.clear_btn.configure(text=self.t("clear"))
        self.copy_btn.configure(text=self.t("copy_logs"))
        self.footer_label.configure(text=self.t("footer"))
        self.root.title(self.t("title"))

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

    def add_log_key(self, key, **params):
        self.log_entries.append({"ts": now_time(), "key": key, "params": params})
        self.render_logs()

    def add_log_events(self, events):
        for key, params in events:
            self.log_entries.append({"ts": now_time(), "key": key, "params": params or {}})
        self.render_logs()

    def render_logs(self):
        if not hasattr(self, "log_text"):
            return
        self.log_text.delete("1.0", "end")
        for entry in self.log_entries:
            msg = log_text(self.lang, entry["key"], entry.get("params") or {})
            self.log_text.insert("end", f"[{entry['ts']}] {msg}\n")
        self.log_text.see("end")

    def copy_logs(self):
        text = self.log_text.get("1.0", "end").strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.add_log_key("copy_log")
        try:
            messagebox.showinfo(self.t("logs"), self.t("copied"))
        except Exception:
            pass

    def clear_log(self):
        self.log_entries.clear()
        self.render_logs()
        self.add_log_key("clear_log")

    def login(self):
        code = self.code_entry.get().strip()
        if not code:
            self.login_msg.configure(text=self.t("need_code"))
            return
        self.login_btn.configure(state="disabled")
        self.login_msg.configure(text="확인중... / 正在确认...")
        self.add_log_key("auth_checking")
        threading.Thread(target=self._login_worker, args=(code,), daemon=True).start()

    def _login_worker(self, code):
        ok, role, enabled, reason = remote_check_code(code)

        def done():
            self.login_btn.configure(state="normal")
            if not ok:
                if reason == "disabled":
                    self.login_msg.configure(text=self.t("disabled"))
                    self.add_log_key("auth_failed_disabled")
                elif reason == "server_error":
                    self.login_msg.configure(text=self.t("server_fail"))
                    self.add_log_key("auth_failed_server")
                else:
                    self.login_msg.configure(text=self.t("bad_code"))
                    self.add_log_key("auth_failed_invalid")
                return

            self.access_code = code
            self.add_log_key("auth_ok", role=role)
            self.show_main()

        self.root.after(0, done)

    def logout(self):
        self.access_code = ""
        self.code_entry.delete(0, "end")
        self.login_msg.configure(text="")
        self.show_login()

    def toggle_lang(self):
        self.lang = "zh" if self.lang == "ko" else "ko"
        self.apply_text()
        self.add_log_key("lang_zh" if self.lang == "zh" else "lang_ko")
        self.render_logs()
        self.refresh_profiles()

    def check_before_action(self):
        self.add_log_key("precheck_start")
        ok, role, enabled, reason = remote_check_code(self.access_code)
        if ok:
            self.add_log_key("precheck_ok")
            return True
        if reason == "disabled":
            self.add_log_key("precheck_disabled")
            messagebox.showwarning("Stopped", self.t("disabled"))
        elif reason == "server_error":
            self.add_log_key("precheck_server")
            messagebox.showwarning("Server", self.t("server_fail"))
        else:
            self.add_log_key("precheck_invalid")
            self.logout()
        return False

    def launch_clicked(self):
        self.launch_btn.configure(state="disabled")
        self.add_log_key("launch_requested")
        threading.Thread(target=self._launch_worker, daemon=True).start()

    def _launch_worker(self):
        if not self.check_before_action():
            self.root.after(0, lambda: self.launch_btn.configure(state="normal"))
            return
        ok, events = mac_launch("")

        def done():
            self.add_log_events(events)
            self.refresh_profiles()
            self.launch_btn.configure(state="normal")

        self.root.after(0, done)

    def kill_all_clicked(self):
        self.add_log_key("kill_all_request")
        threading.Thread(target=self._kill_all_worker, daemon=True).start()

    def _kill_all_worker(self):
        ok, events = mac_kill_all()

        def done():
            if ok:
                RUN_META.clear()
            self.add_log_events(events)
            self.refresh_profiles()

        self.root.after(0, done)

    def refresh_profiles_clicked(self):
        self.add_log_key("refresh_profiles")
        self.refresh_profiles()

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

        pids = mac_list_main_pids() if is_mac() else []
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
                width=15,
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
                width=14,
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
        self.add_log_key("kill_one_request", pid=pid)
        threading.Thread(target=self._kill_one_worker, args=(pid,), daemon=True).start()

    def _kill_one_worker(self, pid):
        ok, events = mac_kill_pid(pid)
        self.root.after(0, lambda: (self.add_log_events(events), self.refresh_profiles()))

    def periodic_refresh(self):
        if self.main_frame.winfo_ismapped():
            self.refresh_profiles()
        self.root.after(3000, self.periodic_refresh)

    def on_close(self):
        if getattr(self, "_closing", False):
            return
        self._closing = True
        self.add_log_key("close_start")

        def worker():
            try:
                ok, events = mac_kill_all() if is_mac() else (True, [])
            except Exception as e:
                events = [("close_error", {"error": str(e)})]

            def finish():
                try:
                    self.add_log_events(events)
                    RUN_META.clear()
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
        if not is_mac():
            try:
                messagebox.showwarning(self.t("mac_only_title"), self.t("mac_only_body"))
            except Exception:
                pass
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
