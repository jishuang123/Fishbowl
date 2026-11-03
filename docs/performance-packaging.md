# V0.11 性能与 Windows 打包

## 改动

- 默认将内置大肥鱼的五张贴图宽高各减半，保持透明通道、UV 和模型文件不变；原始 ZIP、开发资源与导入角色不修改。基础 RGBA 像素占用从 592 MiB 减到 148 MiB，不包含 mipmap、遮罩或浏览器内存。可用 `build_release.py --full-textures` 构建原画质版。
- 页面实际绘制上限 30 FPS，隐藏时暂停，恢复时重置计时，避免补算长时间动画。鼠标跟随仍每 33 ms 检查，但仅变化时通过通信桥发送。
- 复用 GPU 纹理，加载完成后不再保留 PNG 的解码图像引用。按实际贴图尺寸检查显卡能力，加载失败仍通过现有错误界面显示。
- 本地资源服务支持 HTTP/1.1 连接复用，增大并发资源请求队列，减少 Cubism 同时加载动作、表情时的连接等待。
- Python 入口延迟载入 Qt，日志轮转，使用 PyInstaller 文件夹打包。每次启动直接载入依赖，不需要先展开单文件包。

## 本机测量

Windows x64、Python 3.11.9、PySide6 6.12.0，同一台机器、同一模型和默认 400×640 逻辑像素窗口，优化前后各启动三次，取中位数。启动时间从父进程创建子进程前到模型报告就绪；就绪后采样约 8 秒，统计整个进程树的私有内存和 CPU 时间。测试不发送聊天，不生成语音。

| 指标 | 优化前 | 优化后 |
| --- | ---: | ---: |
| 源码运行器启动至模型就绪 | 5.10 秒 | 3.61 秒 |
| 进程树私有内存 | 1.25 GiB | 0.77 GiB |
| CPU（100% 为一个逻辑核心） | 147% | 85% |
| 渲染帧率 | 约 60 FPS | 约 30 FPS |

对应启动耗时约降低 29%、私有内存约降低 38%、CPU 时间占用约降低 42%。这些是同机对比，CPU 降幅包含降低绘制帧率的效果；私有内存不等于独占显存。冷启动、杀毒扫描、不同显卡与驱动都会影响结果，尚未验证另一台干净 Windows 机器。

实际 EXE 在构建和压缩结束后的第一批三次启动为 8.54、7.62、4.17 秒，帧率和 CPU 也有波动；同一时段源码复查为 5.81 秒，不能据此认定波动仅由 EXE 引起，也未定位具体系统因素。这批原始数据保留为 `exe-initial-{1,2,3}.json`。

随后复测三次实际 EXE：3.51、3.52、3.49 秒，中位数 3.51 秒；进程树私有内存中位数 0.76 GiB，CPU 中位数约 85%（一个逻辑核心为 100%），帧率约 30 FPS。这里是运行数次后的表现，不能当作首次启动保证。第二批数据为 `exe-{1,2,3}.json`。两批全部正常加载、透明渲染且没有模型错误；没有删除较慢的第一批结果。

证据位于 `.local/evidence/performance/baseline-{1,2,3}.json`、`optimized-{1,2,3}.json`。用 `tools/measure_runtime.py --report 路径 --renderer 暂存资源/frontend/dist` 可测源码运行器；`tools/verify_release.py --benchmark` 测实际 EXE，结果为 `exe-{1,2,3}.json`，另存每次截图。首次启动与后续启动分开保留，不把源码结果称为 EXE 的测量结果。

## 构建和隐私边界

运行 `tools/build_release.py` 前先安装 `requirements-build.txt`、准备模型与官方 SDK，并构建前端。脚本只从明确清单收集前端构建、模型引用资源、默认角色及人格、空音频映射、图标、本机 TTS 脚本和第三方许可；不读取用户数据目录作为打包输入。每次创建独立暂存目录与资源哈希清单。

输出为 `dist/Fishbowl/Fishbowl.exe` 及旁边 `_internal/`，以及 `dist/Fishbowl-0.11.0-windows-x64.zip`。文件夹版无需 Python、Node.js 或源码目录，启动时不解压运行库。默认用户数据目录与源码版一致：`%LOCALAPPDATA%\Fishbowl\Fishbowl\`，保留既有 Key、角色选择、记忆、映射和静音设置。也可用 `--data-dir` 指定程序目录以外的独立位置。

打包脚本自动运行 `tools/audit_release.py`，检查资源 SHA-256、窗口程序类型、个人配置/记忆文件名、个人数据目录，以及当前本机 Key 的 UTF-8、UTF-16 和 Base64 字节；报告只记录校验结果，不记录 Key。编译模块排除项目验收脚本目录。随后生成 ZIP 并做完整 CRC 校验。报告在 `.local/evidence/package/audit.json`。

构建时曾发现 PATH 中的其他软件 ICU DLL 被错误收集，导致 QtCore 导入失败。发布配置明确排除这些冲突 DLL，由 Windows 提供 Qt 使用的系统 ICU，审计脚本同时阻止打包 `icuuc.dll`。不是通过修改 Windows 系统文件解决。

## 验收方式与限制

`tools/verify_release.py` 启动真实 EXE，工作目录为临时目录，PATH 只保留 Windows 系统目录，清除 Python 环境路径。通过原生 Qt 鼠标和键盘事件操作实际 WebEngine 与聊天界面，使用临时 Key 和临时记忆验证：

- 透明模型加载、点击、拖动、隐藏暂停与恢复。
- 本地 SSE 验收服务发送流式工具请求，真实执行本机时间插件，显示结果卡；完整回复后才启动 Windows 本机 TTS，PCM 驱动实际模型嘴部参数。
- 全局静音停止声音与口型，静音下继续流式聊天。
- 原生互动编辑器保存表情与语音映射，播放本地 WAV 并联动口型。
- 从外部官方样例资源导入第二个角色，再切回大肥鱼；各角色记忆隔离，互动设置与静音保留。第二个测试角色不打入包。
- 用户设置和完整会话落盘到临时用户目录，实际退出菜单动作结束应用。

加 `--live` 才读取本机已有的真实 Key，发送一次 DeepSeek 时间问题和工具结果续答，使用隔离记忆且不修改个人配置。这个结果与本地 SSE 验收结果分别标记。截图和报告在 `.local/evidence/package/`；声音输出音量设为零，验证播放状态、PCM 和模型嘴部变化，未进行扬声器音质听验。

`tools/verify_archive.py --live` 会先把交付 ZIP 解压到带空格和中文的临时目录，再运行同一套 EXE 验收，并重新扫描解压后的全部文件。校验结果在 `audit-extracted.json`，压缩包 SHA-256 与迁移运行结果在 `archive.json`。

这是未签名的本机构建。测试运行于当前 Windows x64 主机；尚未验证多屏混合缩放、休眠恢复与长时间稳定性。内置模型原始须知禁止完整模型再分发，因此当前包不可直接作为公开发布物。随包附带可获得的 SDK、Python 和依赖许可文本；公开分发还须核对模型及各依赖的具体授权。

参考：[PyInstaller 文件夹与单文件运行方式](https://pyinstaller.org/en/stable/operating-mode.html)、[Qt WebEngine 配置与存储](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineProfile.html)。沿用 WebEngine 的非持久化网页配置，没有为了提速增加磁盘缓存。
