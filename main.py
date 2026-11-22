from __future__ import annotations

import copy
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException, Request as FastAPIRequest
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA_DIR = Path(os.environ.get("LOCAL_AGENT_HUB_DATA_DIR", str(ROOT))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = DATA_DIR / "config.json"
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

DEFAULT_CONFIG: dict[str, Any] = {
    "auto_start": True,
    "proxy_api_key": "sk-local-agent",
    "system_prompt": "你是一名可靠、清晰的本地 AI 助手。请直接回答问题；信息不足时明确说明。",
    "fallback_order": ["strata"],
    "startup_timeout_seconds": 120,
    "request_timeout_seconds": 600,
    "backends": {
        "llama": {
            "label": "llama.cpp",
            "enabled": True,
            "base_url": "http://127.0.0.1:8081/v1",
            "api_key": "sk-llama",
            "model": "qwen3-8b",
            "health_path": "/health",
            "start_cmd": [],
            "idle_shutdown_minutes": 0,
        },
        "strata": {
            "label": "Strata",
            "enabled": True,
            "base_url": "http://127.0.0.1:8080/v1",
            "api_key": "not-needed",
            "model": "qwen3.8-flash-next-coder",
            "health_path": "/v1/models",
            "start_cmd": [],
            "idle_shutdown_minutes": 5,
        },
        "airllm": {
            "label": "AirLLM",
            "enabled": True,
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key": "not-needed",
            "model": "meta-llama/Llama-3.1-70B-Instruct",
            "health_path": "/v1/models",
            "start_cmd": [],
            "idle_shutdown_minutes": 10,
        },
        "custom": {
            "label": "自定义本地模型",
            "enabled": False,
            "base_url": "http://127.0.0.1:1234/v1",
            "api_key": "",
            "model": "",
            "health_path": "/v1/models",
            "start_cmd": [],
            "idle_shutdown_minutes": 0,
        },
    },
}

BACKEND_KEYS = ("llama", "strata", "airllm", "custom")


def _merge_config(user_config: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(DEFAULT_CONFIG)
    for key in ("auto_start", "proxy_api_key", "system_prompt", "fallback_order", "startup_timeout_seconds", "request_timeout_seconds"):
        if key in user_config:
            merged[key] = user_config[key]
    for name in BACKEND_KEYS:
        if name in user_config.get("backends", {}):
            merged["backends"][name].update(user_config["backends"][name])
    return merged


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        config = copy.deepcopy(DEFAULT_CONFIG)
        save_config_file(config)
        return config
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return _merge_config(raw if isinstance(raw, dict) else {})
    except (OSError, json.JSONDecodeError):
        logging.exception("配置文件读取失败，将暂用默认设置")
        return copy.deepcopy(DEFAULT_CONFIG)


def save_config_file(config: dict[str, Any]) -> None:
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(CONFIG_PATH)


CONFIG = load_config()


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("后端地址必须是有效的 http:// 或 https:// URL")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _authorization_headers(backend: dict[str, Any]) -> dict[str, str]:
    api_key = str(backend.get("api_key") or "").strip()
    if not api_key or api_key.lower() == "not-needed":
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def _health_url(backend: dict[str, Any]) -> str:
    path = str(backend.get("health_path") or "/health")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return _origin(str(backend["base_url"])) + "/" + path.lstrip("/")


def health_check(name: str, timeout: float = 2.0) -> tuple[bool, str]:
    backend = CONFIG["backends"][name]
    try:
        url = _health_url(backend)
        headers = _authorization_headers(backend)
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=timeout) as response:
            if response.status < 500:
                return True, f"HTTP {response.status}"
            return False, f"HTTP {response.status}"
    except HTTPError as e:
        # A 401/404 still proves that the server is listening; 5xx does not.
        return (e.code < 500, f"HTTP {e.code}")
    except (URLError, TimeoutError, OSError, ValueError) as e:
        return False, str(e)


class BackendManager:
    def __init__(self) -> None:
        self.processes: dict[str, subprocess.Popen[Any]] = {}
        self.last_used: dict[str, float] = {}
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.monitor_thread: threading.Thread | None = None

    def status(self, name: str) -> dict[str, Any]:
        config = CONFIG["backends"][name]
        with self.lock:
            proc = self.processes.get(name)
            owned = proc is not None and proc.poll() is None
            if proc is not None and proc.poll() is not None:
                self.processes.pop(name, None)
            last_used = self.last_used.get(name)
        healthy, detail = health_check(name)
        return {
            "name": name,
            "label": config.get("label", name),
            "enabled": bool(config.get("enabled", True)),
            "healthy": healthy,
            "detail": detail[:160],
            "managed_by_app": owned,
            "pid": proc.pid if owned and proc else None,
            "last_used": last_used,
            "model": config.get("model", ""),
        }

    def start_backend(self, name: str) -> tuple[bool, str]:
        healthy, detail = health_check(name)
        if healthy:
            return True, "后端已在运行"
        backend = CONFIG["backends"][name]
        command = backend.get("start_cmd")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            return False, "尚未配置启动命令。请先在设置中填写命令参数数组。"
        with self.lock:
            existing = self.processes.get(name)
            if existing and existing.poll() is None:
                proc = existing
            else:
                log_path = LOG_DIR / f"{name}.log"
                try:
                    with open(log_path, "ab", buffering=0) as log_file:
                        kwargs: dict[str, Any] = {
                            "cwd": str(ROOT),
                            "stdout": log_file,
                            "stderr": subprocess.STDOUT,
                        }
                        if os.name == "nt":
                            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                        proc = subprocess.Popen(command, **kwargs)
                    self.processes[name] = proc
                    self.last_used[name] = time.time()
                except (OSError, ValueError) as e:
                    return False, f"启动命令执行失败：{e}"
        timeout_seconds = max(5, min(int(CONFIG.get("startup_timeout_seconds", 120)), 600))
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return False, f"启动进程已退出（代码 {proc.returncode}），请查看 logs/{name}.log"
            healthy, _ = health_check(name, timeout=2)
            if healthy:
                self.last_used[name] = time.time()
                return True, "后端启动成功"
            time.sleep(2)
        return False, f"等待后端就绪超时；请查看 logs/{name}.log。进程仍保留运行，可稍后重试检查。"

    def stop_backend(self, name: str) -> tuple[bool, str]:
        with self.lock:
            proc = self.processes.get(name)
            if not proc or proc.poll() is not None:
                self.processes.pop(name, None)
                return False, "该服务不是由本应用启动的，或进程已经停止；为安全起见不会结束外部进程。"
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        with self.lock:
            self.processes.pop(name, None)
            self.last_used.pop(name, None)
        return True, "已停止由本应用启动的服务"

    def touch(self, name: str) -> None:
        with self.lock:
            self.last_used[name] = time.time()

    def start_monitor(self) -> None:
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        self.stop_event.clear()
        self.monitor_thread = threading.Thread(target=self._monitor, name="backend-idle-monitor", daemon=True)
        self.monitor_thread.start()

    def _monitor(self) -> None:
        while not self.stop_event.wait(10):
            now = time.time()
            to_stop: list[str] = []
            with self.lock:
                for name, proc in list(self.processes.items()):
                    if proc.poll() is not None:
                        self.processes.pop(name, None)
                        continue
                    minutes = max(0, int(CONFIG["backends"][name].get("idle_shutdown_minutes", 0)))
                    last = self.last_used.get(name, now)
                    if minutes > 0 and now - last >= minutes * 60:
                        to_stop.append(name)
            for name in to_stop:
                self.stop_backend(name)

    def shutdown(self) -> None:
        self.stop_event.set()


MANAGER = BackendManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    MANAGER.start_monitor()
    yield
    MANAGER.shutdown()


app = FastAPI(title="本地 Agent Hub", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return copy.deepcopy(CONFIG)


@app.put("/api/config")
async def update_config(request: FastAPIRequest) -> dict[str, Any]:
    global CONFIG
    try:
        incoming = await request.json()
    except Exception:
        raise HTTPException(400, "配置必须是 JSON")
    if not isinstance(incoming, dict):
        raise HTTPException(400, "配置格式无效")
    updated = _merge_config(incoming)
    updated["auto_start"] = bool(updated.get("auto_start", True))
    updated["system_prompt"] = str(updated.get("system_prompt", ""))[:12000]
    updated["proxy_api_key"] = str(updated.get("proxy_api_key", "sk-local-agent"))[:200]
    try:
        updated["startup_timeout_seconds"] = max(5, min(int(updated.get("startup_timeout_seconds", 120)), 600))
        updated["request_timeout_seconds"] = max(10, min(int(updated.get("request_timeout_seconds", 600)), 3600))
        fallback = updated.get("fallback_order", ["strata"])
        if not isinstance(fallback, list) or any(name not in BACKEND_KEYS for name in fallback):
            raise ValueError("fallback_order 只能包含 llama、strata、airllm")
        updated["fallback_order"] = list(dict.fromkeys(fallback))
        for name in BACKEND_KEYS:
            b = updated["backends"][name]
            b["label"] = str(b.get("label", name))[:80]
            b["enabled"] = bool(b.get("enabled", True))
            b["base_url"] = str(b.get("base_url", "")).strip().rstrip("/")
            _origin(b["base_url"])
            b["api_key"] = str(b.get("api_key", ""))[:500]
            b["model"] = str(b.get("model", ""))[:200]
            b["health_path"] = str(b.get("health_path", "/health"))[:500]
            command = b.get("start_cmd", [])
            if not isinstance(command, list) or any(not isinstance(x, str) for x in command):
                raise ValueError(f"{name} 的启动命令必须是字符串数组")
            if len(command) > 100 or any(len(x) > 2000 for x in command):
                raise ValueError(f"{name} 的启动命令超出允许长度")
            b["start_cmd"] = command
            b["idle_shutdown_minutes"] = max(0, min(int(b.get("idle_shutdown_minutes", 0)), 1440))
        save_config_file(updated)
    except (ValueError, TypeError, OSError) as e:
        raise HTTPException(400, f"保存失败：{e}")
    CONFIG = updated
    return {"ok": True, "message": "设置已保存", "config": copy.deepcopy(CONFIG)}


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    return {
        "backends": {name: MANAGER.status(name) for name in BACKEND_KEYS},
        "api": {"base_url": "/v1", "model_aliases": ["auto", *BACKEND_KEYS]},
    }


def _fetch_models(base_url: str, api_key: str) -> list[str]:
    try:
        _origin(base_url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    headers = _authorization_headers({"api_key": api_key})
    request = Request(base_url.rstrip("/") + "/models", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=12) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        raise HTTPException(502, f"模型列表读取失败：服务返回 HTTP {e.code}") from e
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise HTTPException(502, f"无法读取模型列表：{e}") from e
    entries = body.get("data", body.get("models", [])) if isinstance(body, dict) else []
    if not isinstance(entries, list):
        raise HTTPException(502, "服务返回的模型列表格式无效")
    model_ids: list[str] = []
    for entry in entries:
        model_id = entry if isinstance(entry, str) else entry.get("id") if isinstance(entry, dict) else None
        if isinstance(model_id, str) and model_id.strip():
            model_id = model_id.strip()[:200]
            if model_id not in model_ids:
                model_ids.append(model_id)
        if len(model_ids) >= 200:
            break
    if not model_ids:
        raise HTTPException(404, "没有读取到模型；你仍可手动填写模型标识")
    return model_ids


@app.post("/api/backends/{name}/models")
async def list_backend_models(name: str, request: FastAPIRequest) -> dict[str, Any]:
    if name not in BACKEND_KEYS:
        raise HTTPException(404, "未知后端")
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, "请求必须是 JSON") from e
    if not isinstance(payload, dict):
        raise HTTPException(400, "请求格式无效")
    backend = CONFIG["backends"][name]
    base_url = str(payload.get("base_url", backend["base_url"])).strip().rstrip("/")[:1000]
    api_key = str(payload.get("api_key", backend.get("api_key", "")))[:500]
    models = await run_in_threadpool(_fetch_models, base_url, api_key)
    return {"models": models}


@app.post("/api/backends/{name}/start")
async def start_backend(name: str) -> dict[str, Any]:
    if name not in BACKEND_KEYS:
        raise HTTPException(404, "未知后端")
    if not CONFIG["backends"][name].get("enabled", True):
        raise HTTPException(400, "该后端已禁用，请先在设置中启用")
    ok, message = await run_in_threadpool(MANAGER.start_backend, name)
    return {"ok": ok, "message": message, "status": MANAGER.status(name)}


@app.post("/api/backends/{name}/stop")
def stop_backend(name: str) -> dict[str, Any]:
    if name not in BACKEND_KEYS:
        raise HTTPException(404, "未知后端")
    ok, message = MANAGER.stop_backend(name)
    return {"ok": ok, "message": message, "status": MANAGER.status(name)}


def choose_backend(task: str) -> str:
    lowered = task.lower()
    air_terms = ("超大", "70b", "405b", "极限", "airllm", "超长上下文", "批量深度分析")
    strata_terms = ("代码", "编程", "coder", "moe", "复杂推理", "系统设计", "深度分析", "strata", "架构", "debug", "refactor")
    if any(term in lowered for term in air_terms):
        return "airllm"
    if any(term in lowered for term in strata_terms):
        return "strata"
    return "llama"


def _user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content", "")
            if isinstance(content, str):
                return content
            return json.dumps(content, ensure_ascii=False)
    return ""


def _completion_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/chat/completions"


def _call_backend(name: str, messages: list[dict[str, Any]], temperature: float, max_tokens: int) -> str:
    backend = CONFIG["backends"][name]
    payload = {
        "model": backend["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Content-Type": "application/json", **_authorization_headers(backend)}
    request = Request(_completion_url(backend["base_url"]), data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    timeout = max(10, min(int(CONFIG.get("request_timeout_seconds", 600)), 3600))
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read(1500).decode("utf-8", errors="replace")
        raise RuntimeError(f"后端返回 HTTP {e.code}: {detail}") from e
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"连接后端失败：{e}") from e
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError("后端返回格式不是 OpenAI Chat Completions 格式") from e
    if isinstance(content, list):
        content = "\n".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)
    return str(content or "")


def run_chat(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages 必须是非空数组")
    normalized: list[dict[str, Any]] = []
    has_system = False
    for item in messages[-80:]:
        if not isinstance(item, dict) or item.get("role") not in ("system", "user", "assistant"):
            continue
        role = item["role"]
        content = item.get("content", "")
        if not isinstance(content, (str, list)):
            content = str(content)
        has_system = has_system or role == "system"
        normalized.append({"role": role, "content": content})
    if not normalized:
        raise ValueError("没有可发送的有效对话消息")
    if not has_system and CONFIG.get("system_prompt"):
        normalized.insert(0, {"role": "system", "content": CONFIG["system_prompt"]})
    model = str(payload.get("model", "auto"))
    if model not in ("auto", *BACKEND_KEYS):
        raise ValueError("model 仅支持 auto、llama、strata、airllm")
    temperature = max(0.0, min(float(payload.get("temperature", 0.7)), 2.0))
    max_tokens = max(1, min(int(payload.get("max_tokens", 2048)), 32768))
    hint = str(payload.get("task_hint", ""))
    user_text = _user_text(normalized)
    selected = choose_backend(hint + "\n" + user_text) if model == "auto" else model
    candidates = [selected]
    if model == "auto":
        if selected != "llama":
            candidates.append("llama")
        candidates.extend(CONFIG.get("fallback_order", []))
    candidates = list(dict.fromkeys(name for name in candidates if name in BACKEND_KEYS and CONFIG["backends"][name].get("enabled", True)))
    if not candidates:
        raise RuntimeError("没有启用可用的模型后端")
    failures: list[str] = []
    started = time.time()
    for name in candidates:
        healthy, _ = health_check(name)
        if not healthy:
            if not CONFIG.get("auto_start", True):
                failures.append(f"{name}: 服务未运行且自动启动已关闭")
                continue
            ok, message = MANAGER.start_backend(name)
            if not ok:
                failures.append(f"{name}: {message}")
                continue
        MANAGER.touch(name)
        try:
            answer = _call_backend(name, normalized, temperature, max_tokens)
            return {
                "reply": answer,
                "backend": name,
                "backend_label": CONFIG["backends"][name].get("label", name),
                "elapsed_seconds": round(time.time() - started, 2),
                "fallback_used": name != selected,
                "failures": failures,
            }
        except RuntimeError as e:
            failures.append(f"{name}: {e}")
            if model != "auto":
                break
    raise RuntimeError("所有候选后端均未能完成请求。" + ("\n" + "\n".join(failures) if failures else ""))


@app.post("/api/chat")
async def api_chat(request: FastAPIRequest) -> dict[str, Any]:
    try:
        payload = await request.json()
        return await run_in_threadpool(run_chat, payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.get("/v1/models")
def openai_models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_proxy_key(authorization)
    now = int(time.time())
    return {"object": "list", "data": [{"id": name, "object": "model", "created": now, "owned_by": "local-agent-hub"} for name in ("auto", *BACKEND_KEYS)]}


def _check_proxy_key(authorization: str | None) -> None:
    expected = str(CONFIG.get("proxy_api_key", ""))
    if expected and (not authorization or authorization != f"Bearer {expected}"):
        raise HTTPException(401, "API key 无效；请使用本地 Agent Hub 设置中的代理密钥")


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: FastAPIRequest, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_proxy_key(authorization)
    try:
        payload = await request.json()
        if payload.get("stream"):
            raise HTTPException(400, "当前版本仅支持 stream=false")
        result = await run_in_threadpool(run_chat, payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    created = int(time.time())
    return JSONResponse({
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": created,
        "model": str(payload.get("model", "auto")),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result["reply"]}, "finish_reason": "stop"}],
        "system_fingerprint": f"local-{result['backend']}",
    })


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("AGENT_HUB_HOST", "127.0.0.1")
    port = int(os.environ.get("AGENT_HUB_PORT", "7860"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
