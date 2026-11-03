# DeepSeek 文字聊天与气泡

V0.6 已增加人格、本机最近会话记忆和流式显示，专项设计及验证见 [人格、记忆与流式回复](persona-memory.md)。

V0.10 已支持基础插件与时间工具调用，详见 [工具调用](tools.md)。2026-11-03 已使用本机配置完成真实 DeepSeek 流式时间查询：模型发出调用、应用读取系统时间、模型接收结果并继续回答。验证使用隔离记忆和静音窗口，个人配置和 Key 不进入证据文件。

## 如何使用

1. 启动 Fishbowl（免安装版双击 EXE，源码版可用「启动鱼缸.cmd」）。
2. 在角色或托盘的右键菜单选择「和大肥鱼聊天…」。
3. 点击聊天面板的「API 设置」，填入自己的 DeepSeek API Key 并保存。
4. 输入文字，按 Enter 或点击「发送」。Shift+Enter 换行。

聊天面板显示你和大肥鱼的消息气泡，默认放在角色旁边。它有独立的窗口、输入区和关闭按钮，不占用角色画布的鼠标事件。等待回复时仍可点击、拖动角色，自动眨眼、呼吸和待机也继续运行。

「取消」终止当前生成，不加入该次对话上下文；失败时恢复待发送文字，方便修改或重试。「清空记忆」取消生成并丢弃本机最近会话。关闭聊天窗口会取消请求并隐藏面板，桌宠继续运行。修改 API 设置会保留会话和尚未发送的草稿。

## 本地 Key 配置

推荐使用原生「API 设置」对话框。正常启动时设置保存在：

`%LOCALAPPDATA%\Fishbowl\Fishbowl\deepseek.json`

该文件在用户数据目录，包含本地明文 Key 和模型名，不在项目源码目录。应用不将 Key 发给 Live2D 网页或本机静态服务器，不通过 QWebChannel 暴露聊天配置，也不记录 Key、请求头、聊天正文或服务端错误原文。

已有 `DEEPSEEK_API_KEY` 环境变量时优先使用它；否则读取本地文件。环境变量由 Windows 启动的进程继承，修改后需重新启动鱼缸。环境变量不是自动读取 `.env` 文件。保存空 Key 可移除本地文件中的 Key，但不会删除系统环境变量。

如需手动配置，文件结构如下，api_key 保持空白直到你在本机填写：

```json
{
  "api_key": "",
  "model": "deepseek-flash"
}
```

本轮默认模型为 `deepseek-flash`，设置界面也可选 `deepseek-v4-pro`。名称和请求参数依据 2026-11-02 查看的[官方首次调用文档](https://api-docs.deepseek.com/)及[Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)。

源码忽略 `.env`、`.env.*`、`deepseek.json` 和 `deepseek.local.json`；正常用户配置根本不位于仓库中。不要将个人配置作为项目文件分享。

## 范围与行为

- 固定向官方 `https://api.deepseek.com/chat/completions` 发送文字请求，使用 SSE 流式回复、关闭思考模式，每段回复最多生成 512 tokens。主动发送聊天后，模型可调用本机时间工具，并在同一轮中自动请求续答；没有主动聊天或联网搜索。
- 使用 Qt 原生异步网络，不在界面线程等待 HTTP 返回。一次只允许一个请求；不会自动重试或排队。
- 发送内容包括角色人格提示、最近最多 10 轮完整对话和本次输入；不读取屏幕、用户文件或桌面内容。
- 单条输入最多 2000 字符；最近成功会话保存在本机 `memories/<角色 ID>.json`，下次运行恢复，可用“清空记忆”删除当前角色的会话。V0.8 会将旧 `chat-memory.json` 迁移给大肥鱼。界面最多保留 60 个气泡，服务端回复大小也有上限。
- 失败、取消或超时的消息不进入后续模型上下文。界面可能仍保留该次已发送的气泡，方便回看。
- 45 秒总超时；Key 错误、余额不足、限流、网络异常及空/异常响应会给出简短中文提示。服务端错误原文不展示，避免错误回显泄露配置。
- 不跟随 HTTP 重定向，不把 Authorization 转发到其他地址。测试工具通过构造参数使用本机回环地址；用户设置不能修改官方地址。
- 气泡按纯文字显示，不执行模型返回的 HTML，不加载回复中的远程图片。
- 静音只影响音频通道，不关闭文字聊天。大肥鱼人格提示来源为 `characters/deepseek/persona.txt`；其他角色使用各自角色包的人格。完整回复的本地 TTS 与近似口型见 [语音与口型说明](tts-lipsync.md)。当前不做长期事实库或人格编辑界面。

## 验证与证据

`tools/verify_chat.py` 使用真实 QNetworkAccessManager 和本地 HTTP 协议验收服务，10 组检查通过：缺少 Key 不请求、请求格式与并发控制、连续对话、错误脱敏、异常响应、取消、超时、拒绝重定向、输入/上下文边界、清空会话。

`tools/verify_chat_ui.py` 使用真实 Qt 气泡面板、WebEngine 和本地协议验收服务，8 组界面场景通过，包含流式气泡、生成期间拖动、纯文字、记忆恢复、设置保留记忆以及取消/清空与重新打开。原有浏览器交互回归 7 组也通过，Windows 桌宠与静音/托盘验收通过。

本地截图与结果：

- `.local/evidence/chat/service-result.json`
- `.local/evidence/chat/ui/result.json`
- `.local/evidence/chat/ui/chat-reply.png`
- `.local/evidence/chat/ui/api-settings-masked.png`
- `.local/evidence/chat/ui/request-error.png`
- `.local/evidence/chat/ui/cancelled.png`

**上述聊天回归截图中的回复来自本地协议验收服务，不是真实 DeepSeek 回复。** 真实时间工具联调单独记录在 `.local/evidence/tools/live/`。普通回归脚本继续只用占位 Key；真实联调需显式运行 `verify_tools_live.py --live`。未进行账户余额检查或长期模型质量验收。

运行检查：

```powershell
.venv\Scripts\python.exe tools\verify_chat.py
.venv\Scripts\python.exe tools\verify_chat_ui.py
.venv\Scripts\python.exe tools\verify_interactions.py
```

测试设置和占位 Key 只写入已忽略的 `.local/evidence/chat/`，本机协议服务不接触官方 API，也不消耗真实 API 额度。
