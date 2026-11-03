# V0.4：音效/语音播放接口与静音

后续进展：V0.7 已在此播放通道上接入本地 TTS 和近似口型，见 [语音与口型说明](tts-lipsync.md)。下文保留无素材阶段的资源检查和预留接口说明；预录素材清单仍为空，但新版本可以朗读聊天回复。

## 资源检查

对原始 `DeepSeek免费公皮.zip` 的 47 个文件检查了音频/媒体扩展名、常见媒体文件头，以及模型和 VTube Studio 的声音配置：

- 没有发现音频文件或常见媒体文件头。
- 原始模型入口没有动作 Sound 引用。
- 28 个热键声音配置均未启用，SoundSlots 全部为空。
- SoundTriggers 为空。

检查工具：`tools/inspect_audio_resources.py`。清单保存于 `.local/evidence/audio/resource-inventory.json`。

因此本轮不添加角色音效、配音或 TTS。`assets/audio/cues.json` 的 sounds、voices 都保持为空；当前程序仍然无声，关闭静音也不会产生声音。

## 静音开关

角色右键菜单和托盘菜单共用「静音」勾选项。勾选时同时静音音效和语音通道，并立即停止、清空正在加载或播放的媒体；取消勾选不会补播。

选择保存到用户数据目录的 `settings.json`，正常启动时为 `%LOCALAPPDATA%\Fishbowl\Fishbowl\settings.json`。默认不静音；没有素材时仍不播放任何内容。设置文件使用原子写入，保留其他设置字段。文件读写失败只记录日志，不阻止桌宠运行。

## 预留接口

`app/audio.py` 中的 PetAudio 使用两个独立的 QMediaPlayer/QAudioOutput 通道。加载和解码异步进行，同一通道的新请求替换旧请求，不积累播放队列。音效和语音可同时播放，静音对两者都有效。

| 接口 | 行为 |
| --- | --- |
| `playSound(cue)` | 播放 sounds 映射中的本地文件 |
| `playVoice(cue)` | 播放 voices 映射中的本地文件 |
| `stopAll()` | 停止并清空两个通道 |
| `setMuted(bool)` | 切换并保存静音状态 |
| `muted` / `mutedChanged` | 当前静音状态及变化通知 |
| `playbackFailed(channel, message)` | 文件不可用或解码失败的通知，同时写入日志 |

QWebChannel 注册名为 `audio`，桌面页面连接完成后也可以通过 `window.fishbowl.audio` 访问。playSound/playVoice 返回的布尔值表示播放请求是否接受，不表示音频已经解码成功。缺少映射或处于静音时返回 false，不影响动作和输入。

以后获得可使用的素材后，可将文件放入 `assets/audio/` 并修改清单，例如：

```json
{
  "sounds": {"tap": "tap.wav"},
  "voices": {"greeting": "greeting.wav"}
}
```

重启程序后，Python 可以调用 `window.audio.playSound('tap')` 或 `window.audio.playVoice('greeting')`。桌面前端调用示例：

```javascript
window.fishbowl.audio.playVoice('greeting', accepted => {
  // accepted 仅表示请求已接受；错误通过 playbackFailed 通知。
});
```

当前清单不包含这些示例文件。只允许根音频目录中的文件，目录外的路径会被拒绝。具体编码支持取决于 Qt 的解码后端；本轮实测 PCM WAV。

点击、拖动、随机待机没有新增播放触发点。以后可以在确认素材和声音映射后接入上述接口，当前不会为了缺失的音频更改已有互动流程。

## 验证

`tools/verify_audio.py` 用本机生成的 3 秒无声 PCM WAV 验证真实 Qt 后端，没有用模拟播放器替代关键行为，也没有向正式素材目录添加测试音频。7 组检查通过：

1. 未映射的音效和语音请求正常返回，不播放。
2. 两个通道都成功解码，时长正确且播放位置前进。
3. 静音立即停止两个通道，拒绝后续播放请求。
4. 取消静音不恢复丢弃的媒体。
5. 新服务实例读取保存的静音状态，其他设置字段保留。
6. 缺失或目录外的文件不会抛出异常打断应用。
7. 损坏音频异步报告错误，随后仍可播放有效文件。

原有 7 组浏览器点击/跟随/手势回归通过。Windows 工具还实际点击静音菜单项、检查托盘共用状态与设置写入，再验证切换后的拖动和点击；并通过真实 QWebChannel 调用空音效/语音接口和静音接口。

证据：`.local/evidence/audio/result.json`、`desktop-menu.json`、`desktop-tray.json`、`desktop-*-muted.png`。测试使用单独的设置文件，不修改用户的正常静音偏好。

没有验证扬声器可听输出、真实人物语音、TTS 或口型联动，因为资源包没有音频。这些不作为本轮已完成功能。

实现参考：[Qt QMediaPlayer](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QMediaPlayer.html)、[Qt QAudioOutput](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QAudioOutput.html)。
