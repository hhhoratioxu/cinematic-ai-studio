# Cinematic AI Studio

面向 Codex 的通用 AI 电影制作 Skill，支持真人电影、动漫、动态漫画和完整 AI 短剧。根据用户每次提供的创意、故事、剧本或分镜，建立独立本地项目，调用真实模型制作动态镜头，再完成配音、口型、声音、剪辑、字幕和质量审核。

**v0.5.1 仓库只维护通用工具、配置结构和技术测试。** 不附带任何特定作品、剧情、角色故事或默认用户项目。用户素材、分镜、角色参考、生成结果和付费记录保存在仓库外；例如 `E:\SKILL\projects\<项目名>\`。

## 能力与验收边界

| 能力 | 实现与边界 |
|---|---|
| 四种制作模式 | `live_action`、`anime`、`motion_comic`、`ai_drama`；实际画面效果须用真实模型验收 |
| 图像与角色参考 | OpenAI 图像生成/编辑，正面、侧面、全身、表情参考；角色档案与服装版本跨镜头复用 |
| 导演与连续性 | 结构化故事分析、动作节拍、站位、视线、焦点、镜头运动、Scene Bible、道具/服装/光照/轴线变化检查 |
| 真实动态视频 | Runway、Kling 官方适配器，按输入、时长、比例、帧控制、音频能力及用户偏好选择配置模型 |
| 普通话配音与口型 | 固定声线、说话风格/情绪/速度意图、实测音轨时长适配；Sync 对已有动态视频处理，单个可见说话者策略 |
| 声音、剪辑、输出 | 对白/SFX/BGM、淡入淡出、重叠配乐提示、对白优先混音，逐镜剪辑、SRT/ASS、H.264/AAC MP4 |
| 运动与质量 | 解码、规格、冻结/黑屏、重复、光流、相机补偿、主体区域残差、疑似平移缩放静图、闪烁；不确定结果需人工复核 |
| 恢复与局部制作 | 内容缓存、已知任务恢复、下载恢复、单镜头有限重做、原片/口型版本保留、已有动态素材零 API 重剪 |
| 本地工作台 | 角色、场景、镜头、任务、错误、预算、视频预览、当前素材哈希绑定的人工通过/驳回；只监听本机 |

离线自动化和真实 FFmpeg 流程与模型效果分开验收。`Provider Live Verified`、`Full Episode Rendered`、`Editorially Reviewed` 在没有真实生成与人工审片证据时保持 **Pending**。技术测试不代表电影质量，测试音调不代表真实普通话，动态图案不代表 AI 正片。

## 安装与调用

需要 Python 3.11+、FFmpeg/FFprobe（含 libx264、libass）和本机可用的中文字幕字体。CI 覆盖 Windows、macOS、Linux 和 Python 3.11/3.13。

```text
git clone https://github.com/hhhoratioxu/cinematic-ai-studio.git
cd cinematic-ai-studio
python -m venv .venv
```

Windows PowerShell 激活 `.venv\Scripts\Activate.ps1`；macOS/Linux 使用 `source .venv/bin/activate`。随后运行：

```text
python -m pip install -r requirements.txt
python scripts/cinema.py doctor
python scripts/install_skill.py
```

安装目录默认是 `~/.agents/skills/cinematic-ai-studio`，旧宿主可用 `--destination` 选择其他受支持目录。已有本工具管理的安装使用 `python scripts/install_skill.py --upgrade`：先验证文件，再完整备份到 `~/.agents/skill-backups/`；用户修改或未知文件会阻止覆盖。升级不操作仓库外的项目。

在 Codex 输入 `$cinematic-ai-studio`，接着提供本次创意/故事、模式、目标时长、画幅、语言和已授权素材。Codex 根据通用 Schema 为本次输入建立项目；没有内置作品可供默认生成。所有命令有 `--help`。

FFmpeg：Windows 可安装 Gyan.FFmpeg；macOS 使用 `ffmpeg-full` 以获得 libass；Linux 安装 ffmpeg 和本地 CJK 字体。`doctor` 实际检查工具与媒体能力，只检查 Key 是否存在，不请求生成。字体可由 `output.font_file` 或 `CINEMA_FONT` 指向有权使用的本地文件，不随安装包分发专有字体。

## 项目与配置

以 `E:\SKILL\projects\my-film\` 为例，由用户为每个作品选择独立目录。故事写入该目录的 `story.txt`，参考图片、角色档案、分镜和全部生成记录也保留在此。将 [config.example.json](assets/config.example.json) 复制成项目的 `config.json`，不要覆盖已有配置。[characters.example.json](assets/characters.example.json) 仅说明字段结构，实际角色由用户故事定义。

只通过环境变量配置需要的凭据：

- `OPENAI_API_KEY`：图像/参考编辑、TTS、可选规划和视觉检查。
- `RUNWAYML_API_SECRET`：Runway 视频及生成音效。
- `KLING_API_KEY`，或 `KLING_ACCESS_KEY` + `KLING_SECRET_KEY`：Kling 视频。
- `SYNC_API_KEY`：独立口型同步。

`ceilings_usd` 故意为空。根据当前官方文档、账户计价及所选模型填写每次图像/TTS/规划/视觉检查、每秒视频/口型/音效的费用上界，详见 [Provider 指南](references/provider-guide.md)。这些是原子预留上界，实际账单须与平台对账；失败和未知提交不自动退回预留。

沿用的 OpenAI 合同有已公布的弃用窗口，当前日期与迁移边界见 Provider 指南。正式制作前核对别名、账户可用性、请求字段和费用；不静默切换到尚未验证的新接口。

CLI 未指定 `--out` 时，为每次新制作选择 `~/CinematicAIStudio/projects/` 下的独立目录；可用 `CINEMA_PROJECTS_DIR` 改变默认项目根目录。生产写入禁止进入任一 Cinematic AI Studio 仓库/安装目录。原有外部项目的 `--out`、账本与预算在恢复时保持不变。

## 从当前用户输入开始制作

Codex 可以使用 `schema plan`，直接把当前用户的故事变成项目内的 `shot_plan.json`，不产生额外规划 API 费用。分镜时长必须精确覆盖本次目标，按动作和对白变化，不能重复片段、循环、冻结或黑屏补齐。

以下路径中的 `PROJECT` 代表仓库外的用户项目，命令不包含付费授权：

```text
python scripts/cinema.py schema plan
python scripts/cinema.py character --bible PROJECT/characters.json
python scripts/cinema.py estimate --plan PROJECT/shot_plan.json --config PROJECT/config.json
python scripts/cinema.py plan --plan PROJECT/shot_plan.json --config PROJECT/config.json --out PROJECT/render
python scripts/cinema.py studio --out PROJECT/render
python scripts/cinema.py episode --plan PROJECT/shot_plan.json --config PROJECT/config.json --out PROJECT/render
```

最后一条在未带 `--allow-paid` 时仍只估算。用户明确批准美元预算后，才给生成命令添加 `--allow-paid --budget-usd AMOUNT`。API Key、一般电影请求或示例中的参数都不独立构成消费授权。

也可将当前用户的 `story.txt` 交给预算内规划接口。`--story-file` 必须明确指定 `--seconds`，没有固定作品或时长。下面先询问本次用户要求的时长，并只显示规划估算；真正执行仍需单独添加既有授权的付费参数：

```powershell
$Seconds = [int](Read-Host '本次作品的目标时长（秒）')
python scripts/cinema.py episode --story-file PROJECT/story.txt --seconds $Seconds --mode live_action --config PROJECT/config.json --out PROJECT/render
```

`shot --plan PROJECT/shot_plan.json --shot-id SHOT_ID --out PROJECT/shot-render` 制作指定镜头；`--bible PREVIOUS_PROJECT/characters.json` 复用跨集角色。单镜头仍是片段，不能代替用户要求的完整作品。v1 计划继续读取；`migrate --plan OLD.json --output NEW.v2.json` 保留原文件，推断内容需要复核。

## 审核、恢复和重剪

```text
python scripts/cinema.py status --out PROJECT/render
python scripts/cinema.py cost --out PROJECT/render
python scripts/cinema.py review --out PROJECT/render
python scripts/cinema.py render --out PROJECT/render
python scripts/cinema.py resume --out PROJECT/render --allow-paid --budget-usd ORIGINAL_AMOUNT
```

`status`、`cost`、只读 `review` 不生成素材。`render` 不构造付费执行器，验证来源哈希后用既有动态源片和混合音轨重剪，可更改同一组镜头的顺序、配乐、输出规格；改变时长/对白须显式修订镜头。`regenerate --out PROJECT/render --shot-id SHOT_ID --note REASON --allow-paid --budget-usd ORIGINAL_AMOUNT` 只重做指定镜头，保留版本与费用，受原预算和次数上限约束。

`reconcile` 只挂接已确认的任务或文件；未知提交先对账，不删除账本重买。默认 Sync 要求单个可见说话者；运动不确定的原片先做 `review --raw --scope motion`，再考虑付费口型处理。工作台的重做按钮只复制命令，不提交付费请求。审核须记录实际观察、复核人、当前媒体 SHA-256；素材改变后原通过记录失效。

每个项目保留生成的 `episode_NN.mp4`、原始/口型镜头、角色与分镜、任务数据库、字幕、导演/场景/连续性/剪辑数据、技术和人工审核、费用报告。编号来自项目计划。技术成功状态仍为 `rendered_requires_editorial_review`。实际身份、动作、表演、解剖、字幕字形和口型需要观看素材。

## 仓库与安装包边界

GitHub 保留 Python 引擎、Skill、文档、通用配置/角色结构、安装脚本及技术测试。`.gitignore` 屏蔽项目目录、故事/分镜、参考图片、视频/音频、数据库、生成记录、Key 和费用文件。CI 审核受跟踪文件；安装器和打包器使用同一允许清单，即使文件被忽略也不会被递归打进包。意外出现的未批准输入会阻止安装/打包。

不要将用户故事改成测试 Fixture 或文档范例。`tests/fixtures.py` 仅程序化生成校准主体、动作和 Schema 字段，独立覆盖完整多镜头时间线；生产代码不导入这些 Fixture。合成媒体只生成在临时/外部目录。

```text
python -m pip install -r requirements-dev.txt
python tests/validate_distribution.py
python -m pytest -q
python tests/run_offline_demo.py --out EXTERNAL_TEST_DIRECTORY
```

测试保留视频、配音、口型请求、预算、恢复、运动、导演/连续性、路由、修订、工作台、安装等覆盖。离线测试禁止外网，工作台集成仅放行回环。`TEST_ONLY_` 输出是测试证据，不能当作电影。旧版本发布与 Git 历史按版本保留，当前发行包遵循通用内容边界。

更多资料：[电影风格](references/cinematic-style.md)、[角色一致性](references/character-consistency.md)、[分镜](references/shot-generation.md)、[Provider](references/provider-guide.md)、[声音](references/audio-pipeline.md)、[QC](references/quality-control.md)、[v2 制作](references/production-v2.md)。MIT 适用于代码和文档；服务与用户素材遵循各自许可。
