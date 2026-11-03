# Fishbowl V0.1 验证记录

日期：2026-11-02。平台：当前 Windows 本机。Python 3.11、PySide6 6.12.0、官方 Cubism SDK for Web R5（随包 Core 输出版本 6.0.1）。Chrome 和 Qt WebEngine 均使用 NVIDIA GeForce RTX 4060 Laptop GPU，经 ANGLE / Direct3D11 渲染，MAX_TEXTURE_SIZE 为 16384。桌面测试画布为 400×640 逻辑像素、500×800 设备像素，即当前 125% 缩放环境。

## 通过的验收场景

| 场景 | 执行方式 | 结果 |
| --- | --- | --- |
| 官方示例加载、渲染和眨眼/呼吸 | `tools/verify_web.py --name official-web-verified` | 通过 |
| 构建后的透明页面及浏览器鼠标流程 | `tools/verify_frontend.py` | 通过 |
| Windows 透明合成、拖动、右键菜单退出 | `tools/verify_desktop.py` | 通过 |
| Windows 托盘图标及其菜单退出动作 | `tools/verify_desktop.py --exit-via tray` | 通过 |

前端 `npm.cmd run build`（包含 TypeScript 检查）、官方示例 `npm.cmd test`（TypeScript 检查）和 Python 语法编译也通过。以上验收工具通过断言判定结果，非仅凭程序能启动。

## 关键证据

- 模型 5 张原始贴图全部加载，Core 枚举得到 509 个参数、715 个绘制对象。
- 官方示例中左右眼开合采样均覆盖 0 到 1，呼吸采样接近 0 到 1。
- 桌面版本同样确认双眼闭合和呼吸变化。
- WebGL 未丢失上下文，检查时 glError 为 0；最终场景没有网页异常、资源错误或 `[CSM][E]` 日志。
- 透明页 PNG 左上角 alpha 为 0。桌面帧缓冲区角落 alpha 为 0，Windows 合成截图的对应像素为底层测试窗口的 `#ee25be`，角色区域有实际绘制内容。
- Qt 鼠标事件经 WebEngine DOM → QWebChannel → Python 窗口完成拖动；窗口从 `(180,100)` 移到 `(245,135)`，与事件位移 `(65,35)` 一致。
- 右键菜单实际显示并点击退出；独立场景调用实际托盘菜单的退出项，均观察到应用退出。两次场景的系统托盘可用且图标可见。

本地证据位于 `.local/evidence/`：

- `official-web-verified.png` / `.json` / `.log`：最终官方示例。
- `transparent-web.png` / `.json`：构建后透明页面。
- `desktop-menu.png` / `desktop-menu-menu.png` / `.json` / `.log`：桌面透明合成、右键流程。
- `desktop-tray.png` / `desktop-tray-menu.png` / `.json` / `.log`：托盘退出场景。

`official-web.*` 是早期未调整遮罩数量时的诊断记录，不能作为最终通过证据。截图及模型构建结果均留在本机，没有提交到公开服务。

## 验证中解决的问题

1. **默认遮罩缓冲区不足。** 初始画面虽能显示，SDK 持续报告 49 组遮罩超过单缓冲区 36 组容量。已将示例的 createRenderer 默认 maskBufferCount 改为 2，最终日志错误消失。验证工具现在也检查 `[CSM][E]`，避免将这类 console.log 日志漏判为成功。
2. **HTTP 页面不能直接加载 qrc 脚本。** Qt WebChannel 脚本改为从 Qt 自带资源读取，通过同一本机 HTTP 来源提供；没有放开 Chromium 的本地资源访问限制。
3. **IDLE 会抑制自动眨眼。** 该动作不含眼睑曲线，但官方示例在动作更新期间跳过自动眨眼。V0.1 沿用原模型入口不登记动作，使用官方自动眨眼、呼吸和物理更新。包内动作和表情完整保留，后续再接入。
4. **拖动坐标与通信延迟。** Python 使用鼠标事件传来的 screenX/screenY，而非在异步消息到达时重新读取全局指针位置；取消事件和失焦会清理拖动状态。

官方示例保留其背景和渲染流程，仅作模型路径及遮罩缓冲区适配。桌面版本由该示例生成，额外去除背景和齿轮、将清屏 alpha 设为 0，并添加桌面通信。

## 未验证或未实现

- 尚未测试其他显卡、其他 Windows 机器、多屏、混合缩放、休眠唤醒或长时间稳定性。
- 尚未测量精确显存、CPU 占用和长期帧率。原始贴图 RGBA8 单份约 592 MiB，不含 mipmap 及其他开销。
- 尚未逐项验证 8 个动作、23 个表情，也未接入 AI 或语音。
- 尚未测试 Windows 托盘溢出区的实际鼠标定位；退出动作测试直接调用真实托盘菜单项。
- 尚未打包 EXE、持久保存位置或实现按角色轮廓点击穿透。

## 来源

- [官方 SDK 下载及许可入口](https://www.live2d.com/en/sdk/download/web/)
- [官方 R5 Web 示例](https://github.com/Live2D/CubismWebSamples/tree/5-r.5)
- [Qt QWebEnginePage 背景颜色接口](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEnginePage.html)
- [Qt QWebChannel 对象注册接口](https://doc.qt.io/qtforpython-6/PySide6/QtWebChannel/QWebChannel.html)
