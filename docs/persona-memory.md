# V0.6：大肥鱼人格、简单记忆与流式回复

## 大肥鱼是什么样的伙伴

大肥鱼人格提示词的唯一正式来源是 `characters/deepseek/persona.txt`，由同目录的 `character.json` 引用。每次发起请求时读取，以 system 消息发送；修改这个文本后，下次发送就会生效。无法读取时退回简短的温和伙伴提示，不阻止桌宠运行。V0.8 起，其他角色使用各自角色包的人格与记忆，详见 [角色说明](characters.md)。

她的性格是温和、慢悠悠、有一点偷懒的小机灵。平时接住用户的话题，偶尔调侃自己；遇到认真问题则收起玩笑，具体帮忙。默认 1–3 句，但用户需要代码或长分析时可以展开。

几个设计约束：

- 轻松而不黏人，不催回复，不用委屈、占有欲或讨好换取关注。
- 不机械加“咕噜”、昵称或表情，不把每句话都变成鱼的角色扮演。
- 不固定以问题收尾，也不把闲聊改成任务清单。
- 不编造记忆、用户姓名或共同经历。不声称读取屏幕、打开文件或已经操作桌面。
- 被问到身份时坦诚自己是 AI 桌面伙伴；不代表 DeepSeek 公司发言。

提示词中的语气参考是人工设计示例，不是实测模型输出：

| 用户 | 语气参考 |
| --- | --- |
| 我回来了。 | 回来啦。今天顺利不顺利，都可以慢慢说。 |
| 今天什么都没做成。 | 先别急着给今天判零分嘛。要是还有一点力气，我们就只挑最小的一件事。 |
| 帮我看一下报错。 | 把报错文字贴过来，我陪你一处处找。 |
| 我要专心工作了。 | 好，我安静漂着。有事叫我就行。 |

## 简单会话记忆

只保留最近 10 轮成功接收的 user/assistant 对话，不做人物画像、自动摘要、向量检索或永久事实库。

正常启动时保存到：

`%LOCALAPPDATA%\Fishbowl\Fishbowl\memories\deepseek.json`

旧 `chat-memory.json` 会在目标不存在时迁移给大肥鱼；成功迁移后旧文件移走，清空不会让旧记忆再次出现。导入角色使用各自 ID 的记忆文件。

这是本机明文聊天记录，与 `deepseek.json` 中的 API Key 分开保存，不进入源码或 Live2D 网页，不作为日志记录。下次启动会恢复这些气泡，并在你主动发送新消息时作为最近上下文发给 DeepSeek。

- 一轮回复确认完整后，才同时保存用户消息和助手回复。采用原子替换，文件中只包含版本号、角色和正文。
- 取消、超时、格式异常、缺少结束标记、网络断流以及服务中止都不写入记忆。界面保留已出现的半截文字，并标明“未完成，不计入记忆”。
- API 以 `finish_reason=length` 和 `[DONE]` 正常结束时，保留已生成内容并提示达到长度上限。这与网络断流区分。
- “清空记忆”会取消当前生成，清空界面、内存和本机记忆文件中的消息。后到的数据不会把旧记忆写回来。清空不会删除 API Key。
- 修改 API 设置保留记忆和未发送草稿，不再隐式清空聊天。
- 文件损坏或结构异常时从空会话开始，给出提示。保存失败时显示“当前只在本次运行中保留”；清空写入失败时保留现有记忆并提示，不能虚报清空成功。

## 真正的流式回复

请求改为 `stream: true`，按 [DeepSeek 官方 SSE 协议](https://api-docs.deepseek.com/api/create-chat-completion/)读取 `delta.content` 和 `data: [DONE]`，并非先等完整回复再做打字动画。

网络仍使用 Qt 异步事件循环，不新增阻塞等待。解析器处理任意字节分片、跨分片的中文/表情符号、CRLF、多行 data、心跳与 usage 事件，只展示正文，不展示 reasoning_content。单次传输限制 1 MiB，正文限制 16000 字符，仍保留 45 秒总超时。

气泡约每 32 毫秒合并一次界面更新，在同一个助手气泡中增长。结束时去掉“正在说…”标签，不生成重复气泡。取消按钮在生成期间可用；聊天关闭时终止生成。聊天窗口仍独立于 Live2D 画布，角色点击、拖动、视线和随机待机不走聊天网络路径。

## 验证结果

`tools/verify_stream_memory.py`：11 组专项场景通过，覆盖单字节中文/emoji、CRLF 和 SSE 控制事件，大小限制，首段提前到达，完整提交，重新实例化恢复并携带人格与旧上下文，取消/异常/断流/超时不保存，清空不复活，十轮边界，损坏文件和写入失败。

`tools/verify_chat_ui.py`：8 组真实 Qt/WebEngine 场景通过。实际检查首段出现时网络仍在等待；生成期间继续拖动并观察渲染帧增长；最终仅一个助手回复气泡；取消时标明半截回复；重新创建面板恢复气泡；API 设置不丢记忆或草稿；清空与关闭正常。

原有网络服务回归 10 组、浏览器交互回归 7 组通过。Windows 桌宠菜单、静音、拖动与退出也完成回归检查。

本地证据：

- `.local/evidence/stream-memory/result.json`
- `.local/evidence/chat/ui/result.json`
- `.local/evidence/chat/ui/streaming-partial.png`
- `.local/evidence/chat/ui/chat-reply.png`
- `.local/evidence/chat/ui/cancelled.png`
- `.local/evidence/chat/ui/memory-restored.png`

以上使用真实 Qt 网络与文件系统，连接本地 SSE 协议验收服务。测试 Key 和记忆位于已忽略的 `.local/`，不使用个人配置。此处截图中的话是测试回复，不代表实际模型的人格表现。V0.10 的真实时间工具调用已另行验收，见 [工具说明](tools.md)；长期聊天体验以及多实例同时使用同一记忆文件尚未验收。

```powershell
.venv\Scripts\python.exe tools\verify_stream_memory.py
.venv\Scripts\python.exe tools\verify_chat.py
.venv\Scripts\python.exe tools\verify_chat_ui.py
.venv\Scripts\python.exe tools\verify_interactions.py
```
