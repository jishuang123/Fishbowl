# V0.7：本地 TTS 与近似口型联动

## 使用

重新启动鱼缸，取消静音后，聊天的完整回复会自动使用本机中文系统声音朗读。文字仍然逐段显示，不等待语音生成。聊天窗口新增“停止朗读”，可以停止正在合成或播放的语音，文字与记忆不受影响。

本轮采用 Windows System.Speech，不调用云端 TTS，不新增服务 Key。当前机器实际使用的声音为 `Microsoft Huihui Desktop`，不是大肥鱼专属配音。没有中文系统声音或组件不可用时，只提示语音不可用，文字聊天继续。

## 先检查到的嘴部参数

| 参数 | 模型范围 / 默认值 | 本轮用途 |
| --- | --- | --- |
| ParamMouthOpenY | 0–1 / 0 | 主要嘴部开合，按音量驱动，限制到 0–0.85 |
| JawOpen | 0–1 / 0 | 下巴开合，跟随主要开合量的 40% |
| ParamMouthForm | -1–1 / 0 | 嘴形/微笑，保持模型自身状态，不由音量覆盖 |

cdi3 和 VTube Studio 配置还列出 MouthX、撅嘴、漏斗嘴、嘴唇卷曲、左右微笑等参数；这轮不做音素级嘴形。physics3 中嘴唇、脸颊、舌头的物理更新依赖 ParamMouthOpenY、JawOpen、ParamMouthForm 等输入，因此将开合值放在模型物理更新之前应用。

原模型入口的 LipSync 组为空。本轮通过独立音量驱动接入，没有修改原 ZIP 或原始模型参数文件。

## 播放和口型流程

1. SSE 文字先继续更新气泡。只有已完成、准备提交记忆的助手回复才触发 TTS；取消、失败、断流的半截回复不朗读。历史记忆恢复和欢迎气泡不会被自动重读。
2. 独立隐藏进程使用 Windows System.Speech 合成中文。回复通过标准输入 JSON 传递，不拼接为 PowerShell 命令，不放到进程参数或日志中。辅助进程也不继承 DEEPSEEK_API_KEY。
3. PCM 在内存中封装为 WAV，通过 QBuffer 交给原有 Qt 语音通道播放。正常运行不写回复文本临时文件、语音缓存文件或录音文件。测试样本另存于已忽略的本地证据目录。
4. 从播放器实际解码的 PCM 缓冲区计算 RMS 音量，经过静音门限和前端平滑，将开合值经 QWebChannel 送给模型。网页只接收播放状态和幅度，不接收 Key 或聊天正文。
5. 在官方 SDK 的姿态保存之后、表情更新之后、物理更新之前应用嘴和下巴参数，不将开合量烘焙进基础姿态。V0.9 使用独立的 `NativeMouthUpdater` 排定更新顺序，避免自定义张嘴表情覆盖音频口型。停止、结束、静音以及信号中断时回到原来的姿态。

它是音量包络驱动的近似联动，不是音素/视素匹配。音频设备缓存可能造成小幅延迟。参考 [Qt QAudioBufferOutput](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QAudioBufferOutput.html) 的播放缓冲区同步说明，以及 [Microsoft SpeechSynthesizer](https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer) 的本机合成接口。

## 优先级与边界

- 现有静音开关同时控制音效和 TTS。静音立即停止播放、取消正在生成的语音并闭嘴；取消静音不补播已丢弃内容。回复完成时若处于静音，不启动 TTS。
- 新消息会停止旧语音，不积累朗读队列。“停止朗读”、清空记忆、关闭聊天面板、退出程序也会取消待播内容。
- 既有 `audio.stopAll()` 也取消正在合成的 TTS。
- 语音合成使用子进程，播放和网络均为异步；不增加等待网络或合成结果的界面阻塞。
- 为免朗读代码围栏和网址，朗读文本做少量 Markdown 清理，最多取前 3000 字符。较长内容仍可在文字气泡中完整查看。没有可读文字时不生成声音。
- 合成限时 30 秒，播放器加载限时 15 秒；语音异常只影响独立朗读状态，不改变流式文字或成功会话记忆。
- 需要 Windows 和可用的中文系统声音。当前未加入音色选择、语速设置、边生成边分句朗读或语音克隆。

## 已完成的验证

`tools/verify_speech.py`：10 组真实本机语音/播放器检查，包括中文合成产生非零 PCM、事件循环仍响应、实际音频缓冲区产生变化的开合包络、静音/取消静音、合成中静音、主动停止、旧 stopAll 接口、新消息抢占、代码内容跳过、自然结束释放音频。

`tools/verify_speech_ui.py`：6 组端到端场景，通过本地 SSE 验收服务连接真实聊天面板、本机 TTS、播放器、QWebChannel 和 Live2D 模型：

- 流式首段先显示，尚未启动语音时可继续拖动桌宠。
- 完整回复触发真实系统合成和播放，模型嘴部及下巴参数实际变化。
- 静音后播放停止，嘴部/下巴回到 0，文字不受影响。
- 取消静音不补播。
- “停止朗读”按钮复位口型，保留完成的对话。
- 取消的半截回复不生成语音、不写入记忆。

本机最终一次实测开口值为 ParamMouthOpenY≈0.272、JawOpen≈0.109，静音后两者均为 0；ParamMouthForm 保持为 0。另完成原有音频 7 组、聊天界面 8 组、鼠标交互 7 组及待机/Windows 菜单回归。

证据目录为 `.local/evidence/tts/`：`result.json`、`sample-speech.wav`、`ui/result.json`、`ui/stream-first.png`、`ui/reading.png`、`ui/mouth-open.png`、`ui/mouth-muted.png`。

测试使用实际中文系统引擎和实际播放器，测试时输出音量设为 0，避免打扰；没有验证扬声器听感或精确口型同步。聊天内容由本地 SSE 验收服务提供，未进行真实 DeepSeek Key 联调。其他 Windows 机器的声音安装情况和长期连续朗读尚未验收。

```powershell
.venv\Scripts\python.exe tools\verify_speech.py
.venv\Scripts\python.exe tools\verify_speech_ui.py
.venv\Scripts\python.exe tools\verify_audio.py
.venv\Scripts\python.exe tools\verify_chat_ui.py
```
