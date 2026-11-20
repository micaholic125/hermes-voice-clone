# 本地音色克隆 TTS

> [English](README.md) · **中文**

一个 Hermes Agent 技能：给代理一副**自己的嗓子**——用几秒钟参考音做零样本克隆，全程跑在你自己机器上。

不上传素材、不按字符计费、不依赖任何云语音。

```bash
# 装好技能与 venv 之后
python scripts/doctor.py            # PASS / WARN / FAIL 体检
python scripts/voice_switch.py on   # 接进 Hermes 并当场验证
```

---

## 它到底在做什么

```
文本 ──► voice_client.py ──HTTP──► voice_server.py ──► mp3
        （Hermes 指令提供者，        （模型常驻显存，
          120 秒硬超时）              每次生成都用 Whisper 复核）
```

- **零样本克隆**：3–25 秒单人音频即可，不需要训练。
- **质量闸门**：每段生成后用 Whisper 转回文字、与原文比对。跑飞、含糊、时长离谱的废片会被丢弃重生成（最多三次，总耗时压在 70 秒内，永不触碰 Hermes 的 120 秒上限）。
- **语种路由**：英文走专用英文模型（韵律最好）；中文、日文、韩文、俄文、阿拉伯文等 22 种语言走同包自带的多语模型，按文字自动切换。多语模型不可用时才退回云端语音。
- **常驻服务**：权重只加载一次，之后每次请求只算几秒。
- **可逆**：`voice_switch.py off` 立刻退回 Edge 云语音并停掉服务，不删任何文件。

## 多语言

| 输入文本 | 由谁发声 | 效果 |
|---|---|---|
| 英文 | 英文专用模型 | 韵律最好 |
| 中文、日文、韩文、俄文、阿拉伯文、希伯来文、希腊文、印地文… | 多语模型（23 种语言） | 良好，但有一条前提 |
| 两者都不支持的语言 | 云端语音（可选回退） | 能听懂，音色不对 |

**参考音必须与输出语言一致。** 这是除「参考音是否干净」之外影响最大的一个因素，而且反直觉：零样本克隆跨语言迁移的是**音色**，不是**口音**。用英文参考音去念中文，得到的是「中文的词、英文的嘴」——能听懂，但一听就是外国人。用中文参考音，才有中文的味儿。

服务按文字自动路由，所以同一个会话里可以中英混用；模型按需换入换出（`VOICE_MAX_MODELS=1` 只保留一个，8 GB 显卡应当如此）。

上手前先确认两件事：

```bash
python prepare_reference.py 素材.wav --target-language zh   # 语言不符会提示 MISMATCH
python doctor.py                                            # 看 "non-English" 一行是否就绪
```

```yaml
VOICE_MULTILINGUAL=1        # 0 = 只用英文，非英文退回云端
VOICE_MAX_MODELS=1          # 1 = 换模型，2 = 两个都常驻
VOICE_CJK_CPS=4.0           # 时长质检用的「字符/秒」
```

## 为什么是常驻服务而不是一次性脚本

加载权重需要 45 秒到 4 分钟，而 Hermes 对指令提供者的上限是 120 秒。把模型常驻在本机 HTTP 服务里，客户端只为「合成」付费，不为「启动」付费。`MAX_SECONDS` 的存在就是为了让重试循环永远待在这个上限之内——别把它调到 90 以上。

## 环境要求

| 项目 | 说明 |
|---|---|
| Python 3.10–3.11 | torch 与 chatterbox 的轮子跟不上更新版本 |
| NVIDIA 显卡 6 GB+ | CPU 也能跑，但慢 4–5 倍——这是「为什么这么慢」的头号答案 |
| ffmpeg 在 PATH 里 | 每一步裁剪与编码都靠它 |
| 约 5 GB 磁盘 | CUDA 版 PyTorch 占大头；注意别让它落到 C 盘 |
| Hermes Agent | 本包以 `tts.providers.<name>` 的 command 形式接入 |

## 安装

```bash
git clone <本仓库> ~/.hermes/skills/local-voice-clone-tts
cd ~/.hermes/skills/local-voice-clone-tts

uv venv -p 3.11 venv
uv pip install --python venv/Scripts/python.exe chatterbox-tts "setuptools<81" resemble-perth edge-tts demucs
uv pip install --python venv/Scripts/python.exe --reinstall \
    --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0+cu124 torchaudio==2.6.0+cu124
```

`setuptools<81` 不能省：`resemble-perth` 依赖 `pkg_resources`，而 setuptools 81 把它删了，缺了水印器模型直接初始化失败。

## 制作参考音

```bash
python prepare_reference.py episode.mp4 --start 302 --end 311
```

解码 → demucs 分离人声（去掉配乐与音效）→ 去静音 → 响度归一化 → 24 kHz 单声道 WAV。短于 3 秒拒收，长于 25 秒警告。

**参考音就是质量天花板。** 音乐残留会变成克隆声音里洗不掉的金属感，任何参数都救不回来。

## 使用

```bash
python scripts/doctor.py                 # 各项是否健康
python scripts/voice_switch.py on        # 接入 Hermes，并合成一句验收
python scripts/voice_switch.py status
python scripts/voice_switch.py off
```

接入靠 `hermes config set`，**绝不手改 `config.yaml`**。

## 调参（实测，不是猜的）

| `cfg_weight` | 15 词句子的语速 |
|---|---|
| 0.30 | 73 词/分 —— 沉稳，偏慢 |
| 0.45 | 107 词/分 —— **推荐默认** |
| 0.55 | 129 词/分 —— 接近日常对话 |

`temperature` 从默认 0.8 降到 0.65，能明显减少「每次生成都不一样」的抖动。完整表格见 `references/tuning.md`。

## 目录结构

```
SKILL.md                     技能入口（Hermes 读这个文件）
scripts/
  voice_server.py            常驻合成服务
  voice_client.py            Hermes 指令提供者客户端
  voice_switch.py            幂等的 on / off / status / restart
  prepare_reference.py       原始音频 → 干净参考音
  doctor.py                  只读体检
  voice_config.py            全部旋钮，相对路径，可用环境变量覆盖
references/                  流程、调参、故障、合规
examples/                    带真实数字的案例复盘
```

## 合规

克隆声音在多数司法辖区都受监管，而平台的执行速度比法院快。**不要发布或分发任何你不持有权利的真实人声或表演的克隆。** 发布前请先读 `references/legal-and-ethics.md`。

本仓库**不含任何参考音频**。请自行从你有权使用的素材中裁剪——最安全的第一份素材是你自己的声音。

## 许可证

MIT，见 `LICENSE`。许可只覆盖代码，不授予任何声音、录音或表演的权利；详见 `references/legal-and-ethics.md`。
