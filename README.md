# Cinematic AI Studio

面向 OpenAI Codex 的可安装 Agent Skill，配套 Python 工具，用真实的视频生成 API 执行电影镜头和完整短剧流程。

**v0.5.0 提供完整的真实模型调用路径、逐镜制作数据、局部重做和本地制作工作台。已验证离线代码和真实 FFmpeg 媒体处理；真实模型、完整 AI 正片与人工影视验收仍为 Pending。** 本次开发没有配置生成 API Key，没有调用付费模型；版本号不代表画面已达到电影级质量。

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
| 导演与连续性 v2 | 故事主线、冲突、反转、高潮、悬念；变长镜头、三段动作、站位/视线/焦点；Scene Bible、服装版本/道具/轴线 | 结构和变化校验通过；实际画面连续性待验收 |
| 运动分析 | 全片均匀抽样、LK 光流、RANSAC 相机补偿、主体区域残差、重复内容、疑似平移缩放静图、突变/闪烁 | 真实编码测试片检测；不确定、静止特写和微表情进入人工复核 |
| 模型路由 | 按已核实能力过滤，再按配置顺序/用途偏好/费用上界选择；可配置同一厂商多个模型 | 离线请求与选择测试；不编造质量评分 |
| 局部重做与重剪 | 单镜头修订保留原始/口型素材；既有动态素材重剪；有权使用的动态视频导入 | 重做上限、原预算、未知收费阻断、零 API 重剪验证 |
| 本地工作台 | 角色/场景/镜头/任务/成本/质量、原片与成片预览、哈希绑定人工复核 | 本机令牌、来源检查、范围读取测试；不提供后台付费接口 |

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

安装器默认复制到 `~/.agents/skills/cinematic-ai-studio`，与当前 [OpenAI 官方 Skill 加载目录](https://learn.chatgpt.com/docs/build-skills)一致。旧版本宿主可通过 `--destination PATH` 选择 `~/.codex/skills/cinematic-ai-studio`。新装拒绝覆盖；升级已管理安装时运行 `python scripts/install_skill.py --upgrade`，先核对哈希，再把原目录保留到 `~/.agents/skill-backups/`。用户修改或未知文件会阻止覆盖，不修改其他 Skill。

安装后在新会话输入 `$cinematic-ai-studio`；如果暂时未出现，重启 Codex。使用安装目录里的脚本时，仍需选择已安装依赖的 Python。安装器不复制虚拟环境、凭据或生成项目。

FFmpeg 安装：Windows `winget install --id Gyan.FFmpeg --exact`；macOS `brew install ffmpeg-full`（普通 Homebrew `ffmpeg` 包可能不含 libass 字幕功能）。程序会优先寻找本机的 `ffmpeg-full`，`doctor` 会实际检查字幕、混音与编码能力。中文烧录字幕需本机中文字体，程序会寻找 Microsoft YaHei / PingFang / Noto Sans CJK；也可指定 `CINEMA_FONT` 或 `output.font_file`。

## 配置与成本

从 `assets/config.example.json` 复制一份项目配置。仅通过环境变量配置需要的 Key：

- `OPENAI_API_KEY`：图像、参考图编辑、配音、可选剧本规划和视觉 QC。
- `RUNWAYML_API_SECRET`：Runway 视频、生成音效。
- `KLING_API_KEY`，或 `KLING_ACCESS_KEY` + `KLING_SECRET_KEY`：Kling 视频。
- `SYNC_API_KEY`：独立口型同步。

示例配置的 `ceilings_usd` 故意为空，防止把过期价格或演示数字当作真实报价。按当前官方文档、账户计价和所选模型填入每次图像/TTS/规划/视觉复核及每秒视频/音效/口型同步的**费用上界**，详见 [Provider 配置指南](references/provider-guide.md)。

保留的 OpenAI 合同已进入官方弃用窗口：`gpt-image-1.5` 计划于 2026-12-01 停用，GPT-4.1 mini 快照为 2027-01-14，列出的 GPT-4o mini TTS 快照为 2027-01-06。正式制作前需按 Provider 指南核对当前别名、账户可用性和后续迁移；本版未把尚未实现的替代接口冒充兼容。提供的完整 `--plan` 不调用额外规划模型。

生成命令默认只输出估算。只有显式 `--allow-paid --budget-usd AMOUNT` 才能产生费用。每一步在提交前原子预留费用，超限停止，失败和未知结果继续占用预留，不自动退回额度。未确认收费结果时不会重复提交。

预算记录约束的是用户配置的上界，真实账单需与平台核对；程序不会把估算冒充发票。价格变化、低估单价和账户其他任务不能由本地账本控制，应搭配 Provider 的账户消费限制。不得把本地预算宣称为平台级绝对费用保证。

## 完整第一集

随包提供《被开除后，我的真实身份曝光了》第一集的 **30 个镜头、180 秒**完整 v2 分镜，时长在 3/4/5/6/7/8 秒间按情节变化，包含林辰、苏雨晴、王总，冲突、调查、身份反转及结尾悬念。附角色关系/状态/表情参考计划、Scene Bible、逐镜站位/视线/焦点/动作节拍、道具与服装连续性、配乐提示。这是可执行的制作输入，尚未生成正片。

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

其他入口：`image`、`character`、`shot`、`plan`、`providers`、`schema`，均有 `--help`。用 `--bible PREVIOUS_RUN/characters.json` 复用跨集角色。`shot` 的结果是单镜头片段，不能替代完整一集。v1 继续读取；`migrate --plan OLD.json --output NEW.v2.json` 保留原文件，推断的动作与缺失场景需导演复核。

## 本地工作台、审核与局部恢复

可先创建一个零生成费用的工作区，再打开工作台：

```text
python scripts/cinema.py plan --plan assets/episode01.plan.json --config PROJECT/config.json --out PROJECT/preview
python scripts/cinema.py studio --out PROJECT/preview
```

对已开始制作的项目，使用实际的 `--out PROJECT/episode01`。终端输出带随机会话令牌的本机地址并尝试打开浏览器；`--no-open --port 8765` 可手动访问。只监听 `127.0.0.1`，视频读取限于项目内注册素材。不要转发带令牌的地址。工作台显示项目实存数据和 Pending 状态。

```text
python scripts/cinema.py status --out PROJECT/episode01
python scripts/cinema.py cost --out PROJECT/episode01
python scripts/cinema.py review --out PROJECT/episode01
python scripts/cinema.py render --out PROJECT/episode01
```

`render` 只重用已验收的动态源片和混合音轨，不构造 Provider/付费执行器；可修复输出格式或用 `--plan EDIT.json` 重排同一组镜头、修改配乐/输出规格。时长和对白变化需显式修订镜头。人工 approve/reject 须提供素材当前 SHA-256、复核人和实际观察。素材变更后原通过记录失效。运动不确定的原片在付费口型同步前需复核，可在工作台“任务”页查看/批准原片，或使用 `review --raw --scope motion`。

```text
python scripts/cinema.py review --out PROJECT/episode01 --target s001 --scope motion --decision approve --reviewer "NAME" --note "实际审片观察" --sha256 EXACT_MEDIA_SHA256 --raw
python scripts/cinema.py regenerate --out PROJECT/episode01 --shot-id s001 --note "重做原因" --allow-paid --budget-usd ORIGINAL_AMOUNT --render
```

`regenerate` 只走指定镜头流程，其他镜头不提交生成；可用 `--shot-file SHOT.json` 替换其方向/动作，ID 与时长保持一致。固定原预算和 `max_shot_regenerations`，保留旧片和修订历史；未知扣费先对账，已知在途修订沿原任务恢复，不自动增加预算或次数。

有权使用的动态素材可填写 `source_video` 与 `source_license`，仍经过解码、时长、运动、重复与音频检查。来源记录为 `user_supplied_dynamic_video`，不会标成 AI 模型证据。详见 [v0.5 制作与审核](references/production-v2.md)。

## 输出

```text
PROJECT/episode01/
  episode_01.mp4
  manifest.json
  qc_report.json
  cost_report.json
  estimate.json
  quality_review.json
  director_plan.json
  scene_bible.json
  continuity_report.json
  edit_decision_list.json
  dialogue_plan.json
  reviews.json (有人工记录时)
  revisions.json (有局部重做时)
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

测试禁止真实外网连接；工作台集成测试只放行本机回环。显式区分 Mock API、真实 FFmpeg 后期处理与未执行的模型端到端验收。保留原 A–H 测试，增加运动、导演/连续性、路由、局部修订、工作台和安装升级覆盖。Mock 声音是音调，不能称为真实普通话配音；测试图案不能称为真人/动漫电影。

## 结构与资料

入口是 [SKILL.md](SKILL.md)，实现位于 `scripts/`，测试位于 `tests/`，默认案例位于 `assets/`。进一步阅读：[电影风格](references/cinematic-style.md)、[人物一致性](references/character-consistency.md)、[分镜](references/shot-generation.md)、[官方 Provider 与预算配置](references/provider-guide.md)、[声音与字幕](references/audio-pipeline.md)、[质量检测](references/quality-control.md)。

MIT 许可适用于本仓库代码与文档。模型服务、生成素材和用户导入素材分别遵循相应平台及素材的许可条件。
