# 🐟 Fishbowl · 电子鱼缸

V0.11：性能优化与 Windows EXE 免安装打包。Windows 桌宠原型，使用 Python + PySide6、Qt WebEngine、QWebChannel，以及官方 Cubism SDK for Web R5 的渲染示例。

[首次启动、API Key、角色导入和常见问题](docs/windows-release.md) · [发布范围、授权和隐私检查](docs/publishing.md)

已支持透明显示、自动眨眼和呼吸、全局鼠标跟随、点击表情/手势、随机待机、带人格的流式聊天气泡、每个角色独立的最近会话记忆、本地 TTS 与近似口型、模型导入和角色切换、互动配置、本机插件注册和时间查询工具、拖动、全局静音、右键退出和托盘退出。大肥鱼模型包没有预录音频，朗读使用本机中文系统声音。尚未接入长期事实库或外部插件安装器。

## 本机运行

完成下方的源码构建后，可以双击根目录的 **启动鱼缸.cmd**。已有本机 Windows 包时，按使用说明解压并运行。

- 在桌面移动鼠标，大肥鱼的头部和眼睛会跟随，鼠标在桌宠窗口外也有效。
- 点角色头部，依次显示脸红、爱心眼、开心眼，约 2.5 秒后恢复。
- 点角色身体，抬手抚胸、短暂停留后自动回位。动作期间重复点身体不会排队。
- 按住左键移动超过 6 像素可拖动大肥鱼；拖动不会触发表情或手势。
- 点击透明背景不会触发互动，但当前仍会接收该区域的鼠标事件。
- 安静一段时间后，每隔约 45–100 秒随机出现短暂表情或抚胸动作。操作桌宠会重新计时；手动点击和拖动优先，菜单打开或窗口隐藏时暂停。详细规则见 `docs/idle-interactions.md`。
- 右键打开菜单，选择「退出 Fishbowl」。
- 角色右键菜单或托盘菜单勾选「静音」可关闭音效和语音，选择会保存。静音立即停止朗读和口型，取消静音不会补播。
- 右键选择「和大肥鱼聊天…」，在「API 设置」中填入本机 Key 后即可发送文字。Enter 发送，Shift+Enter 换行，回复会逐段出现在同一个气泡里。聊天窗口独立于角色画布，生成时仍能拖动桌宠。
- 聊天中问“现在几点？”或“今天星期几？”，大肥鱼会调用本机时间工具。绿色结果卡显示实际查询的日期、时间、星期及 UTC 偏移，随后继续流式回答。只有完整回复才朗读，结果卡不单独朗读；静音、取消、清空及角色记忆隔离继续有效。使用和插件扩展见 [工具调用](docs/tools.md)。
- 大肥鱼的人格偏温和、慢悠悠、偶尔调皮，认真问题会认真回答。最近 10 轮完整对话保存在本机，重启后恢复；“清空记忆”可删除，取消或断流的半截回复不计入。设计与验收见 `docs/persona-memory.md`，Key 配置见 `docs/chat.md`。
- 回复完成后自动使用 Windows 中文系统声音朗读，不阻塞流式文字。聊天面板可“停止朗读”，新消息也会打断旧语音。口型按音量近似开合，非逐字匹配。实现、限制与证据见 `docs/tts-lipsync.md`。
- 右键或托盘打开「切换角色 → 导入 Live2D 模型…」，选择已解压模型目录中的 `.model3.json`。导入成功自动切换，以后可从同一菜单切换，重启记住上次角色。每个角色分别保存最近 10 轮对话，清空只影响当前角色；静音和 API Key 全局共享。导入模型默认使用通用跟随和口型，详见 [角色包与导入](docs/characters.md)。
- 右键或托盘选择「角色互动设置…」，分别设置点击头部、点击身体和随机待机。可保留默认、自定义或关闭，每个触发可组合动作、表情和本地语音，不用改 JSON。语音可以从模型资源选择，也可导入 WAV / MP3 / OGG；遵守全局静音，聊天朗读优先，不补播被跳过的语音。保存立即生效，不重载角色或清空聊天，详见 [互动设置](docs/interaction-settings.md)。
- 系统托盘鱼形图标也可以右键退出，双击可以显示角色。
- 桌宠显示与互动使用本机资源；只有主动发送聊天时才调用 DeepSeek API。

免安装版见 `dist/Fishbowl/Fishbowl.exe`，或解压 `dist/Fishbowl-0.11.0-windows-x64.zip` 后双击运行。请保留旁边的 `_internal` 文件夹。API Key、记忆和个人配置不进入包，仍使用原有的本机用户目录。此包包含受限模型，仅供本机使用。透明区域目前也会接收鼠标，尚未实现按角色轮廓点击穿透。

## 打包与性能

前端构建完成后执行：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe tools\build_release.py
.venv\Scripts\python.exe tools\verify_archive.py
.venv\Scripts\python.exe tools\verify_release.py --benchmark
```

打包采用文件夹形式，无需安装 Python 或 Node.js，也无需每次启动解压依赖。资源按明确清单收集，自动扫描包中的本机 Key 和个人数据文件；压缩包校验后生成。`--live` 会使用已经在本机配置的 Key 发送一次真实时间查询，其他验收使用临时配置与隔离记忆。使用说明见 [Windows 运行](docs/windows-release.md)，性能数据和验收范围见 [性能与打包](docs/performance-packaging.md)。

默认将内置角色贴图宽高各减半，原始资源不修改，可用 `tools\build_release.py --full-textures` 保留原尺寸。渲染上限为 30 帧，隐藏时暂停绘制，静止鼠标不重复发送视线更新。导入角色保留其原贴图尺寸。

## 从源码准备

需要 Windows x64、Python 3.11、Node.js 22.12+ 或 24，以及支持 WebGL2、最大贴图尺寸至少 8192 的显卡环境。源码审核包需要另行准备两份原始 ZIP：

- 阅读 Live2D 下载条款并取得 **Cubism SDK for Web 5 R5** 的完整 ZIP。构建依赖这一版的目录和示例代码。[下载页及许可](https://www.live2d.com/en/sdk/download/web/) · [官方 R5 ZIP](https://cubism.live2d.com/sdk-web/bin/CubismSdkForWeb-5-r.5.zip)
- 从神宫凉子的原始配布渠道取得 `DeepSeek免费公皮.zip`，阅读包内须知。

保持两个 ZIP 原样，在源码目录打开 PowerShell，将示例路径换成实际下载位置：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe tools\prepare_web.py --sdk-zip "C:\Downloads\CubismSdkForWeb-5-r.5.zip" --model-zip "C:\Downloads\DeepSeek免费公皮.zip"
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
.venv\Scripts\python.exe -m app.main
```

构建依赖通过 pip 和 npm 安装，准备脚本从给定 ZIP 提取资源。若已有 `.local/CubismSdkForWeb-5-r.5.zip`，可省略 `--sdk-zip`。准备脚本按原模型 ZIP 的中文编码解压，生成目录供本机使用。再次准备会覆盖生成的示例文件，自有修改请放在 `frontend/src/`。模型渲染和基本互动可以在未配置 API Key 时验证。

## 目录与边界

| 目录 | 职责 |
| --- | --- |
| `app/` | 透明窗口、托盘、菜单、鼠标拖动、音频服务、异步聊天与气泡、本机设置、通信桥及静态服务 |
| `app/plugins/` | 显式注册的本机插件；当前内置只读时间查询 |
| `assets/audio/` | 空音频映射清单；未来放置可使用的本地音效与配音 |
| `characters/` | 大肥鱼的模型入口、动作/表情/参数映射、资源准备配置和人格；通用导入模板 |
| `frontend/src/` | 渲染启动、鼠标意图、视线/表情/手势控制、桌面通信及诊断 |
| `frontend/vendor/` | 从官方 SDK 生成的示例代码，未纳入 Git |
| `frontend/public/` | 本机 Core、着色器和模型资源，未纳入 Git |
| `frontend/dist/` | 可由桌面程序加载的构建结果，未纳入 Git |
| `.local/` | 官方 SDK 下载缓存、验证截图和日志，未纳入 Git |
| `tools/` | 资源准备、真实浏览器和 Windows 验证工具 |

桌面窗口不直接绘制模型。前端通过 QWebChannel 发出拖动和菜单请求，Python 负责窗口及系统操作。本机静态服务只绑定 `127.0.0.1` 的随机端口，退出时关闭；它只提供页面与资源。窗口阻止导航到其他站点。

日志位于 `%LOCALAPPDATA%\Fishbowl\Fishbowl\fishbowl.log`。

聊天 Key 通过原生设置界面保存到 `%LOCALAPPDATA%\Fishbowl\Fishbowl\deepseek.json`，或读取 `DEEPSEEK_API_KEY` 环境变量，环境变量优先。Key 不进入源码、插件参数或网页。最近会话另存为该目录下的 `memories/<角色 ID>.json`，不写日志，可清空。旧 `chat-memory.json` 首次使用时迁移给大肥鱼。已验证真实 DeepSeek 流式连接及时间工具调用；人格的长期表现尚未验收，详见 `docs/chat.md`。

## 官方示例复现

先执行上面的资源准备，然后在一个 PowerShell 窗口运行：

```powershell
cd .local\sdk\CubismSdkForWeb-5-r.5\Samples\TypeScript\Demo
npm.cmd install --no-audit --no-fund
npm.cmd run start -- --host 127.0.0.1
```

浏览器打开 `http://127.0.0.1:5000/`。此示例保留官方背景和渲染流程，只替换模型入口并将遮罩缓冲区调整为两个；原模型的 49 组遮罩超过默认单缓冲区的 36 组容量。

自动验证需在项目根目录安装开发依赖：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe tools\verify_web.py --name official-web-verified
.venv\Scripts\python.exe tools\verify_frontend.py
.venv\Scripts\python.exe tools\verify_interactions.py
.venv\Scripts\python.exe tools\verify_idle.py
.venv\Scripts\python.exe tools\inspect_audio_resources.py
.venv\Scripts\python.exe tools\verify_audio.py
.venv\Scripts\python.exe tools\verify_speech.py
.venv\Scripts\python.exe tools\verify_speech_ui.py
.venv\Scripts\python.exe tools\verify_chat.py
.venv\Scripts\python.exe tools\verify_stream_memory.py
.venv\Scripts\python.exe tools\verify_chat_ui.py
.venv\Scripts\python.exe tools\verify_characters.py
.venv\Scripts\python.exe tools\verify_characters_ui.py
.venv\Scripts\python.exe tools\verify_mappings.py
.venv\Scripts\python.exe tools\verify_mappings_ui.py
.venv\Scripts\python.exe tools\verify_tools.py
.venv\Scripts\python.exe tools\verify_tools_ui.py
.venv\Scripts\python.exe tools\verify_desktop.py
.venv\Scripts\python.exe tools\verify_desktop.py --exit-via tray
```

可选真实 API 验证：`.venv\Scripts\python.exe tools\verify_tools_live.py --live`。读取本机 Key 并发送一次时间问题（含工具结果续答），使用隔离记忆和静音测试窗口；不会修改个人设置或会话，也不会输出 Key。此命令会调用官方服务，普通回归脚本只连接本地验收服务。

Web 验证使用本机 Chrome；桌面验证会打开洋红色背景测试窗口，使用 Qt 鼠标事件驱动真实 WebEngine，运行期间请暂勿操作测试窗口。验证真实渲染、SDK 错误日志、眨眼/呼吸变化、透明合成、拖动、右键退出及托盘菜单退出动作。托盘验证直接调用实际托盘菜单项，不测试 Windows 托盘溢出区的位置。

## 已知范围

- 五张原始贴图按 RGBA8 展开约 592 MiB；免安装版使用半尺寸贴图约 148 MiB，另有 mipmap、遮罩和浏览器开销。源码运行默认仍用原始贴图。
- 大肥鱼默认继续使用自动眨眼/呼吸，不自动播放包内 IDLE；默认只触发完整抚胸手势及三个表情。互动设置还可选择包内其他动作/表情；普通动作限制单次播放并恢复，原资源不改动。额外资源未逐个做完整视觉验收，模型导出名直接显示在设置列表中。
- 头部点击按画布上部 35% 的可见像素判定，尚未做骨骼级命中。
- 其余动作和表情尚未逐项动态验收。筛选说明及本轮结果见 `docs/model-interactions.md`。
- 当前窗口位置不持久保存，尚未验证多屏、不同缩放比例混用、休眠唤醒及长期运行。
- 首版验收记录见 `docs/validation-v0.1.md`；模型交互说明见 `docs/model-interactions.md`；随机待机规则与验收见 `docs/idle-interactions.md`。

## 素材与第三方来源

Fishbowl 自有源码及随附自编文档、默认配置和自制图标采用 MIT 许可。大肥鱼模型及其适配资源遵守作者配布须知，Live2D SDK 及其生成副本适用各自的 SDK 条款。分发含第三方组件的构建产物时，须分别满足各组件的分发条件。[MIT LICENSE](LICENSE) · [授权范围与发布说明](docs/publishing.md)

模型：DeepSeek-chan（大肥鱼）。原画及拆分：神宫凉子；Live2D 建模：霓虹猫_NeonNeko；模型来源：神宫凉子免费配布模型。

模型包自带的须知禁止擅自重新分发完整模型。源码排除原始 ZIP、PSD、模型、SDK 缓存及包含模型的构建结果。请自行从作者处获取素材；不要直接将本机构建文件作为公开发布包上传。模型及 PSD 的原始须知保留在用户 ZIP 中。

渲染来源：[Live2D/CubismWebSamples](https://github.com/Live2D/CubismWebSamples/tree/5-r.5)。生成的官方代码保留版权声明；Framework、Core、示例素材的许可文件位于 `.local/sdk/CubismSdkForWeb-5-r.5/`。SDK 与模型素材的授权彼此独立，公开发布前需核对各自许可。
