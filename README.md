# Cinematic AI Studio

面向 OpenAI Codex 的可安装 Agent Skill，配套 Python 工具，用真实的视频生成 API 执行电影镜头和完整短剧流程。

**v0.1.0 是可执行的初始版本。已完成离线自动化与真实 FFmpeg 处理验证；尚未进行付费模型端到端验收。** 没有配置 API Key，也没有花费生成费用。本仓库不提供冒充 AI 正片的图片轮播或静态动画样片。

## 能力与边界

| 功能 | 实现 | 验证状态 |
|---|---|---|
| 四种视觉模式 | 真人、动漫、动态漫画、AI 短剧，统一结构化分镜 | 离线模式路由通过；实际视觉表现待模型验收 |
| 图像与参考图编辑 | OpenAI Images；角色正面、侧面、全身与场景首帧 | 官方请求格式和 Mock 流程测试 |
| 真实动态视频 | Runway、Kling 官方异步 API；下载、首帧、受支持模型的尾帧/Element | 请求契约、恢复与失败处理测试；真实生成待验收 |
| 中文多角色配音 | OpenAI TTS、固定声音 ID、对白时间窗、有限速度调整 | 请求与音轨排程测试；真实普通话效果待验收 |
| 口型同步 | Sync 官方动态视频+音频 API，单个可见说话者 | 上传/轮询契约测试；实际准确度、动漫适配待验收 |
| 音效与音乐 | Runway 音效、授权本地素材、原创程序化氛围音乐、自动压低配乐 | 本地合成与混音通过；生成音效待验收 |
| 字幕、剪辑、MP4 | SRT/ASS、字体测量换行、FFmpeg、H.264/AAC | 真正执行导出与解码验证 |
| QC | 时长、帧率、尺寸、音轨、黑屏、冻结、缺失镜头、解码重复；可选视觉复核 | 本地检测通过；人物/动作/口型保留不确定性 |
| 预算和恢复 | SQLite 原子费用预留、并发上限、有限重试、内容缓存、已知任务恢复 | 包含中断、损坏缓存、预算并发等测试 |

正式执行器不选择 Mock Provider，也不创建伪动态视频。`tests/run_offline_demo.py` 使用动态测试图案和音调，输出以 `TEST_ONLY_` 命名，只用于验证媒体处理。

## 安装

需要 Python 3.11+、FFmpeg/FFprobe（含 libx264/libass），Windows 或 macOS；CI 也验证 Linux。API 费用与 ChatGPT/Codex 订阅分开。

```text
git clone https://github.com/hhhoratioxu/cinematic-ai-studio.git
cd cinematic-ai-studio
python -m venv .venv
```

激活虚拟环境：Windows PowerShell 用 `.venv\Scripts\Activate.ps1`，macOS 用 `source .venv/bin/activate`。随后执行：

```text
python -m pip install -r requirements.txt
python scripts/cinema.py doctor
python scripts/install_skill.py
```

安装器默认复制到 `~/.agents/skills/cinematic-ai-studio`，与当前 [OpenAI 官方 Skill 加载目录](https://learn.chatgpt.com/docs/build-skills)一致。旧版本宿主可通过 `--destination PATH` 选择 `~/.codex/skills/cinematic-ai-studio`。不覆盖已有目录、不修改其他 Skill。

安装后在新会话输入 `$cinematic-ai-studio`；如果暂时未出现，重启 Codex。使用安装目录里的脚本时，仍需选择已安装依赖的 Python。安装器不复制虚拟环境、凭据或生成项目。

FFmpeg 安装：Windows `winget install --id Gyan.FFmpeg --exact`；macOS `brew install ffmpeg`。中文烧录字幕需本机中文字体，程序会寻找 Microsoft YaHei / PingFang / Noto Sans CJK；也可指定 `CINEMA_FONT` 或 `output.font_file`。

## 配置与成本

从 `assets/config.example.json` 复制一份项目配置。仅通过环境变量配置需要的 Key：

- `OPENAI_API_KEY`：图像、参考图编辑、配音、可选剧本规划和视觉 QC。
- `RUNWAYML_API_SECRET`：Runway 视频、生成音效。
- `KLING_API_KEY`，或 `KLING_ACCESS_KEY` + `KLING_SECRET_KEY`：Kling 视频。
- `SYNC_API_KEY`：独立口型同步。

示例配置的 `ceilings_usd` 故意为空，防止把过期价格或演示数字当作真实报价。按当前官方文档、账户计价和所选模型填入每次图像/TTS/规划/视觉复核及每秒视频/音效/口型同步的**费用上界**，详见 [Provider 配置指南](references/provider-guide.md)。

生成命令默认只输出估算。只有显式 `--allow-paid --budget-usd AMOUNT` 才能产生费用。每一步在提交前原子预留费用，超限停止，失败和未知结果继续占用预留，不自动退回额度。未确认收费结果时不会重复提交。

预算记录约束的是用户配置的上界，真实账单需与平台核对；程序不会把估算冒充发票。价格变化、低估单价和账户其他任务不能由本地账本控制，应搭配 Provider 的账户消费限制。不得把本地预算宣称为平台级绝对费用保证。

## 完整第一集

随包提供《被开除后，我的真实身份曝光了》第一集的 **30 个镜头、180 秒**完整分镜，包含林辰、苏雨晴、王总，冲突、调查、身份反转及结尾悬念。这是可执行的制作输入，尚未生成正片。

先准备 `PROJECT/config.json` 中的真实费用上界，再估算：

```text
python scripts/cinema.py estimate --plan assets/episode01.plan.json --config PROJECT/config.json
```

在用户已明确授权对应美元预算后执行（将 `AMOUNT` 换成获准数额）：

```text
python scripts/cinema.py episode --plan assets/episode01.plan.json --config PROJECT/config.json --out PROJECT/episode01 --allow-paid --budget-usd AMOUNT
```

也可以从故事自动规划并完成制作，规划调用另行记录成本：

```text
python scripts/cinema.py episode --story-file assets/episode01.story.txt --seconds 180 --mode ai_drama --config PROJECT/config.json --out PROJECT/story_episode01 --allow-paid --budget-usd AMOUNT
```

Codex 本身可以先依据 `schema plan` 写好分镜，再使用 `--plan`，省去额外规划 API。默认竖屏 1080×1920、24fps、中文配音/字幕、H.264/AAC。更改计划中的 `output` 可用横屏或其他已验证比例。后期统一分辨率的记录会明确指出是否进行了普通放大。

恢复与检查：

```text
python scripts/cinema.py resume --out PROJECT/episode01 --allow-paid --budget-usd ORIGINAL_AMOUNT
python scripts/cinema.py inspect PROJECT/episode01/episode_01.mp4 --plan assets/episode01.plan.json
```

不完整任务保留全部成功素材与账本。未知提交先用 `reconcile` 挂接已确认的任务 ID 或返回文件；具体参数见 `--help` 与 Provider 指南。不要为了恢复而删除账本或使用新的输出目录重买同一批素材。

其他入口：`image`、`character`、`shot`、`plan`、`providers`、`schema`，均有 `--help`。用 `--bible PREVIOUS_RUN/characters.json` 复用跨集角色。`shot` 的结果是单镜头片段，不能替代完整一集。

## 输出

```text
PROJECT/episode01/
  episode_01.mp4
  manifest.json
  qc_report.json
  cost_report.json
  estimate.json
  characters.json
  shot_plan.json
  run.json
  tasks.sqlite3
  characters/ scenes/ shots/ normalized/ audio/
  edit/subtitles.srt
  edit/subtitles.ass
  edit/subtitle_layout.json
```

`manifest.json` 在完整技术检查通过后为 `rendered_requires_editorial_review`；失败为 `incomplete`。人物换脸、肢体、表演、口型与实际字幕渲染仍需看完整视频。视觉模型三帧辅助检查也不能保证整段连续表演合格。

## 不产生费用的测试

```text
python -m pip install -r requirements-dev.txt
python -m pytest -q
python tests/run_offline_demo.py --out OUTPUT_TEST_ONLY
```

测试禁止真实网络连接，显式区分 Mock API、真实 FFmpeg 后期处理与未执行的模型端到端验收。A–H 覆盖图像流程、真人/动漫等模式路由、角色档案复用、多声音中文文本排程、完整时间线、QC/恢复及 MP4 导出。Mock 声音是音调，不能称为真实普通话配音；测试图案不能称为真人/动漫电影。

## 结构与资料

入口是 [SKILL.md](SKILL.md)，实现位于 `scripts/`，测试位于 `tests/`，默认案例位于 `assets/`。进一步阅读：[电影风格](references/cinematic-style.md)、[人物一致性](references/character-consistency.md)、[分镜](references/shot-generation.md)、[官方 Provider 与预算配置](references/provider-guide.md)、[声音与字幕](references/audio-pipeline.md)、[质量检测](references/quality-control.md)。

MIT 许可适用于本仓库代码与文档。模型服务、生成素材和用户导入素材分别遵循相应平台及素材的许可条件。
