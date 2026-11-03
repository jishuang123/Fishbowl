# Fishbowl 发布说明

当前可以准备供审核的源码和文档。V0.11 的 Windows EXE 和 ZIP 是本机验收产物，含受限模型；不要上传至 GitHub Releases、公开网盘或其他下载渠道。现有构建脚本生成的也是这个本机版本。

Fishbowl 自有源码采用 MIT 许可。分发自有源码的副本或实质部分时，请保留版权声明和许可文本。第三方组件分别适用各自的条款。[MIT LICENSE](../LICENSE)

| 内容 | 处理方式 |
| --- | --- |
| Fishbowl 自有源码、说明、默认角色配置与空音频清单 | 纳入 MIT 源码审核包，随包保留 `LICENSE`。默认配置只提供模型文件名与参数映射。 |
| 大肥鱼 ZIP、PSD、模型、贴图、动作、表情及本机导入角色 | 不进入公开源码或发布附件。从原作者处获取，遵守各素材的使用须知。 |
| SDK 下载包、Core、生成的示例/Framework 副本及前端构建产物 | 当前公开源码方案全部排除；使用者按 README 从官方渠道准备依赖。 |
| API Key、记忆、设置、互动映射、导入语音、日志和验收截图 | 保留在本机；不要附在源码、发布包、问题报告或截图中。 |

## 模型和 SDK 分别核对

- **Fishbowl 自有文件**。MIT 覆盖 Fishbowl 权利人有权授权的 Python 应用和插件、`frontend/src/` 中的自编 TypeScript、构建与验证脚本、自编文档、默认配置和自制图标。依赖清单中的软件各用其许可。
- **本机生成的文件**：资源准备脚本里的自编适配逻辑可纳入自有源码范围。它生成的 SDK 示例副本、模型适配文件、混合了 Framework 的前端构建产物和含这些组件的 EXE 文件夹，需要分别核对其中各组件的条款。
- **大肥鱼模型**：原画及拆分为神宫凉子，Live2D 建模为霓虹猫_NeonNeko。作者须知禁止擅自再分发完整模型或二次销售，并要求公开创作注明来源和作者。分享时指向作者原始获取页面，不能用打包或缩小贴图代替授权。其他角色及音频也须分别确认权利。
- **Cubism SDK for Web 5 R5**：Framework 和示例代码按其随附的 Live2D Open Software License 等条款使用；Cubism Core 属于 Live2D Proprietary Software License，不由官方 GitHub 提供。以对应版本的许可文件及 [官方 Web SDK 下载页](https://www.live2d.com/en/sdk/download/web/) 为准，保留要求的版权和许可声明。示例模型素材另看各自许可。
- **程序发布**：分发含 SDK 的应用时，还要核对 [SDK Release License](https://www.live2d.com/en/sdk/license/) 和 PySide6、Qt、Python 等实际打入包的依赖条款。Fishbowl 可导入多个模型，发布前应向 Live2D 确认是否适用 [Expandable Applications](https://www.live2d.com/en/sdk/license/expandable/)；若属于该类，官方要求先审核并签订专门协议，个人或免费发布不能直接视为豁免。即使换成自有模型，这项确认仍需单独进行。

## 发布前检查

1. 从干净的源码候选清单出发。不要把整个工作目录压缩上传，也不要强制添加被忽略的资源。运行下列检查；它检查 Git 已跟踪文件、未忽略的新文件以及暂存内容，报告路径而不显示 Key。

   ```powershell
   python tools\audit_public_source.py
   git diff --cached --stat
   ```

   如果从审核 ZIP 开始，在全新解压目录先运行 `git init`，再执行检查。请先检查 ZIP 的原始文件列表，再按 README 安装依赖并生成本机资源。

2. 人工复核实际要发布的文件、截图、附件和 Git 历史。脚本检查路径清单、常见 Key 格式及本机已配置的 Key，无法识别任意正文里的私密信息，也不扫描旧提交或远程附件。尤其检查用户目录 `%LOCALAPPDATA%\Fishbowl\Fishbowl\` 中的 `deepseek.json`、`memories/`、旧版 `chat-memory.json`、`settings.json`、`characters/`、`interactions/` 和 `interaction-audio/` 没有被复制进去。若 Key 曾出现在公开提交或附件，撤销并更换它；仅删除当前文件无法收回已经公开的值。
3. 需要制作可公开下载的 Windows 版时，先解决模型、SDK 和依赖的授权；准备不含受限模型的独立构建。用 `tools\audit_release.py` 检查实际构建内容，并在新用户目录验收首次启动和角色导入。隐私扫描通过不代表获得分发授权。

运行说明见 [Windows 使用说明](windows-release.md)，本机打包与测试记录见 [性能与打包](performance-packaging.md)。
