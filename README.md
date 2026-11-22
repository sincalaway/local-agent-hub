# 本地 Agent Hub

一个适配 8GB 显卡工作流的本地模型聊天与路由应用。它提供中文网页界面、按需启动模型服务、自动任务路由、失败回退，以及 OpenAI 兼容 API。

## 启动

需要 Python 3.10 或更新版本。将整个文件夹放到要运行模型的电脑上：

- Windows：双击 `run_windows.bat`。
- Linux/macOS：在终端运行 `bash run.sh`。

首次启动会创建 Python 虚拟环境并安装应用依赖。随后在浏览器打开 `http://127.0.0.1:7860`。

## 接入模型

本应用是路由与聊天界面，不会下载或附带模型权重，也不会代替安装 llama.cpp、Strata 或 AirLLM。点击界面左下角“后端与 API 设置”，为本机已安装的服务填写 API 地址、模型标识、健康检查路径和启动命令。启动命令必须是 JSON 字符串数组；留空时应用只连接已经运行的服务。

llama.cpp 示例（请改成你的模型文件路径和实际程序位置）：

```json
["llama-server", "-m", "./models/qwen3-8b-q4_k_m.gguf", "-ngl", "99", "-c", "16384", "--host", "127.0.0.1", "--port", "8081", "--api-key", "sk-llama"]
```

示例中的模型名称、启动参数和 Strata/AirLLM 命令需要与你实际安装的版本相符。程序会把启动输出写入 `logs/`；若服务无法启动，请查看相应日志。

## 路由与启停

“自动路由”默认把普通对话交给 llama.cpp；识别到代码、编程、MoE、系统设计或复杂推理时会优先尝试 Strata；明确提到 70B、超大模型、AirLLM 等任务时才会尝试 AirLLM。自动路由失败会按设置中的回退顺序尝试其他后端，默认回退到 llama.cpp 再到 Strata。手动选定后端时不会悄悄切换到其他模型。

后端健康检查通过后会复用现有服务。应用只会终止自己启动的进程，不会停止你从其他终端或程序启动的服务。Strata 与 AirLLM 的默认闲置关闭时间分别为 5 和 10 分钟；llama.cpp 默认常驻。可在设置中更改，填 0 表示不自动关闭。

对 8GB 显存的建议：llama.cpp 可先试 7B–8B 的 Q4 量化模型；较长上下文会增加显存占用。Strata 建议优先使用较精简的 Coder 模型，系统内存越充足越好。AirLLM 70B 量级通常只适合慢速、非实时任务，并可能依赖大量系统内存。实际可运行性取决于模型量化、上下文长度、驱动和系统内存；本项目没有在你的显卡电脑上预先验证这些组合。

## OpenAI 兼容 API

代理默认监听本机 `127.0.0.1:7860`，API 根地址为 `http://127.0.0.1:7860/v1`。密钥在界面设置里查看或修改，默认值为 `sk-local-agent`。

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:7860/v1",
    api_key="sk-local-agent",
)
response = client.chat.completions.create(
    model="auto",  # 或 llama / strata / airllm
    messages=[{"role": "user", "content": "你好"}],
)
print(response.choices[0].message.content)
```

当前 API 支持非流式 `chat.completions` 与 `/v1/models`；`stream=true` 尚不支持。应用界面对话记录只保存在当前浏览器的本地存储中。

## 安全提示

默认只绑定 `127.0.0.1`，不要在没有额外鉴权与网络防护时改成公网可访问地址。设置中的启动命令会在本机执行，仅填写自己信任的软件和参数。模型服务也建议绑定本机地址；不要把包含密钥的服务暴露到局域网或公网。
