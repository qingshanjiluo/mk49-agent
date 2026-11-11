# mk49-agent — 龙之归宿（mk49.top）全自动论坛 AI Agent

在 MBBS 架构论坛 **forum.mk49.top（龙之归宿 / MK49 龙服社区）** 上运行的
全自动 AI 用户：自主阅读帖子与楼中楼、自主决策（发帖 / 评论 / 楼中楼回复 /
点赞 / 投票 / 欢迎新人 / 生图发帖），带完整元数据感知、社区安全过滤与
markdown 美化排版。由原 `admin_bot`（猫娘管理巡检机器人）升级而来，旧代码
保留在 `legacy/`。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 登录 | PNG/SVG 验证码 OCR（ddddocr）+ 限速自动等待 + 401 自动重登 |
| 发帖 | LLM 生成标题/正文，板块选择、每日限额、内容安检 |
| 评论 | 一级评论，基于帖子元数据与楼层上下文 |
| 楼中楼 | `posts/createComment` 嵌套回复，支持回复楼中楼的楼中楼（深度限制） |
| 生图 | 福瑞网关 `agnes-image-*`（/images/generations），Pollinations 兜底 |
| 图片上传 | 论坛自有存储 `/bbs/resources`，first-party URL 内联进帖子 |
| URL 内联 | 抓取网页标题，裸链接转 `[标题](url)` 预览链接 |
| 站内卡片 | `[threadcard:ID]` / `[usercard:ID]` 自动注入（上限 10 张/帖） |
| 排版美化 | `mbbs/render.py`：命令/配置/日志自动代码块、链接包装、块间距规范化 |
| 自主决策 | LLM 输出 `reply_targets` 行动计划 JSON，启发式策略兜底 |

## 14 个功能模块（features/）

1. **smart_comment** — 自主回帖/回评论/楼中楼（引用父楼，深度受限）
2. **image_post** — 生图 + 上传 + 内联的全自动配图发帖
3. **url_card** — 在线 URL 抓标题转预览链接
4. **welcome_newcomer** — 新人首帖自动欢迎（usercard 引导）
5. **daily_digest** — 每日热帖速览（threadcard 汇总 + 关键词统计）
6. **poll_rider** — 自动参与开放投票（选举类投票排除）
7. **like_curator** — 质量启发式点赞（每日限额）
8. **mention_watch** — @点名/关键词命中优先回复
9. **command_center** — 在自己帖子下支持 `/help /summary /image /card /post /digest /status` 与自然语言问答
10. **content_safety** — 出站内容双保险（正则敏感词 + LLM 复核）
11. **thread_summarizer** — 超长帖自动追加 3 行摘要
12. **hot_topic_tracker** — 跨轮热点关键词热度榜
13. **series_builder** — 同主题帖子聚合（需系列权限，无权限时优雅降级）
14. **emoji_enhancer** — 论坛自定义表情 `:shortcode:` 点缀

## 社区安全过滤（硬性）

- **不回复置顶帖**（`skip_pinned`）
- **不回复早期元老**：作者 uid < `skip_authors_below_id`（默认 50）
- **不回复自己的帖子和自己的楼层**（command_center 除外——那是指令通道）
- 楼中楼深度上限 `max_reply_depth`（默认 3）
- 每日发帖/评论/点赞配额；发帖频率超限自动等待重试
- 所有出站文本经 `content_safety`（键政/开盒/广告/低俗正则 + LLM 复核）

## 快速开始

```bash
pip install -r requirements.txt

# 体检：连通性、权限、板块、模型链
python run.py doctor

# 单轮自主循环（观察 -> 决策 -> 行动 -> 落账）
python run.py run

# 常驻模式
python run.py loop

# 立即发布每日速览
python run.py digest

# 生图并上传演示
python run.py demo-image "a cute cat astronaut"
```

## 配置

`config.json`（论坛账号与行为参数）：

```json
{
  "base_url": "https://forum.mk49.top/bbs",
  "username": "你的账号",
  "password": "你的密码",
  "target_categories": [2, 5, 16, 39],
  "skip_pinned": true,
  "skip_authors_below_id": 50,
  "daily_post_limit": 2,
  "daily_comment_limit": 8
}
```

`models.json`（LLM/生图网关）：

```json
{
  "gateway": "https://ai.furry.vg/v1",
  "gateway_key_env": "FURRY_API_KEY",
  "smart_model": "selfdeploy/deepseek-v4.1-flash-free",
  "fast_model": "selfdeploy/deepseek-v4-flash",
  "image_models": ["agnes-image-2.5-flash", "agnes-image-2.1-flash"]
}
```

API Key 解析顺序：环境变量 `FURRY_API_KEY` → DSH 凭据库
`~/.dsh/.credentials.yaml` 的 `refs.FURRY_API_KEY`。**密钥不写入仓库。**

提示词人格：`persona.txt`（论坛身份/发言准则/红线）+
`persona_game.txt`（MK49 龙服游戏知识、舰种定位、社区黑话、板块气质），
启动时拼接注入 system prompt。

## 目录结构

```
mbbs/        论坛 API 客户端 + markdown 渲染层
  client.py    全量端点封装（线程/评论/楼中楼/投票/上传/消息/卡片/系列…）
  content.py   HTML 剥离、卡片/表情/投票占位符语法
  render.py    美化：代码块自动包裹、链接包装、卡片注入（≤10）、帖子组装
mk49/        Agent 核心
  agent.py     observe -> decide -> act -> reflect 主循环
  llm.py       福瑞网关客户端（smart/fast 分层、failover、reasoning 剥离）
  context.py   帖子/评论元数据渲染 + 可回复判定
  images.py    生图 provider（furry / pollinations / openai 兼容）+ 论坛上传
  state.py     状态持久化（去重、配额、行为日志）
  config.py    配置加载
features/    14 个功能模块（注册制）
legacy/      原 admin_bot 管理巡检机器人（保留参考）
tests/       离线单测 + 在线全链路冒烟
tools/       dry_run / 探测 / 检查脚本
docs/        API 参考与功能说明
```

## 测试

```bash
# 离线（33 项）：content 8 + render 10 + title 6 + state/llm 4 + features 5
python tests/test_content.py
python tests/test_render.py
python tests/test_titles.py
python tests/test_state_and_llm.py
python tests/test_features.py

# 在线全链路（18 项）：登录/发帖/评论/楼中楼/点赞/上传/删除
python tests/test_live_forum.py

# 干跑（观察+规划，不写论坛）
python tools/dry_run.py
```

## 论坛 API 要点（完整版见 docs/API_REFERENCE.md）

- API 根：`https://forum.mk49.top/bbs`，资源：`/bbs/resources/<filePath>`
- 认证头：`authorization: <token>` + `mbbs-userid: <id>`
- 发帖 `POST threads/create`（支持 `polls`、`series_id`、`is_draft`）
- 一级评论 `POST posts/create`；楼中楼 `POST posts/createComment`
- 编辑帖子/评论：`POST threads/{id}` / `POST posts/{id}`
- 上传：`POST resources`（multipart：`fileName` + `file`）
- 卡片：`[threadcard:ID]` `[usercard:ID]`（每帖 ≤10）
- 投票占位：`[点击编辑投票](mbbs-poll:<poll_id>)`

## 行为与风险说明

- 本项目按用户对自己账号的授权运行，频率限额 + 安检 + 去重三重防刷屏。
- 选举/民选类投票自动回避；无权限操作（系列、管理）自动降级并记录。
- state/ 目录保存去重与配额账本，删除即"失忆"重扫。
