# 功能模块说明（14 个自研功能）

所有功能位于 `features/`，注册制（`@register`），由 `agent.act(plan)` 按
计划触发，可被 `plan` 的键控制，也可独立触发（守门员类）。

## 1. smart_comment — 自主回帖/楼中楼

- 从 `plan.reply_targets` 取目标（LLM 规划产出，经 `is_replyable` 校验）
- 整帖评论：基于帖子元数据 + 楼层上下文生成 40~150 字口语评论
- 楼中楼：引用父楼 60 字 + 直接回应；可回楼中楼的楼中楼（深度 ≤ max_reply_depth）
- 不回自己楼层；`render.pretty_comment` 统一排版；安检通过才发

## 2. image_post — 生图配图发帖

链路：LLM 提炼话题 → `image_prompt_for` 转英文提示词 → 福瑞网关
`agnes-image-2.5-flash` 生图（Pollinations 兜底）→ 论坛 `/bbs/resources`
上传 → `render.pretty_post` 组装（标题/正文/配图/页脚）→ 发帖。
每日限额受 `daily_post_limit` 约束。

## 3. url_card — 在线 URL 预览

对出站文本中的裸 URL 抓取 `<title>`/og:description，替换为
`[标题](url)` 形式；失败时保留原样。

## 4. welcome_newcomer — 新人欢迎

判定：新人板块（24/32）发帖 或 uid 帖子数 ≤2 或注册 ≤7 天。
生成 40~80 字欢迎语并带 `[usercard:uid]`；每用户只欢迎一次（state 记账）。

## 5. daily_digest — 每日速览

每天一篇（`state.daily` 记账防重复）：热帖 threadcard 列表（≤7 张，硬上限
10）、标题关键词统计、页脚说明。由 agent 调度（9:00–23:00 间首个循环）或
`/digest` 命令触发。

## 6. poll_rider — 投票参与

扫新帖开放投票，`can_vote` 且未投过才参与；选项可由 LLM 挑选（失败随机）。
**选举/民选/竞选类标题自动回避**（`avoid_poll_keywords`）。API 用
`{poll_id, option_id}`（多选传数组）。

## 7. like_curator — 点赞策展

质量启发式（正文长度 + 楼层数）打分，≥0.35 才点赞；每日 ≤15；顺手给优质
评论点赞。不点赞自己的帖子。

## 8. mention_watch — @点名响应

任何新楼层命中马甲/用户名/关键词（`mention_keywords`）即优先定向回复，
使用楼中楼接口。

## 9. command_center — 指令中心

监听自己帖子下的新楼层：

```
/help /summary /image <描述> /card <id> /post <板块> <主题> /digest /status
```

非命令但 @机器人 的自然语言交给 LLM 简答。所有回复经安检。

## 10. content_safety — 出站安检

正则红线（键政人物/事件、低俗、导流广告、开盒）→ 命中即拒；
其余文本再过 LLM JSON 复核（失败视为通过，不阻塞）。守门员模式：
每轮 `act` 前先注册，所有写操作主动调用 `check()`。

## 11. thread_summarizer — 长帖摘要

正文 ≥1200 字且无人在该帖发过摘要时，追加「📌 摘要（自动整理）」3 行要点。
每帖只做一次（state 记账）。

## 12. hot_topic_tracker — 热点榜

跨轮累计标题关键词热度（停用词过滤），保留 Top200，供速览与 `/status` 用。

## 13. series_builder — 系列聚合

LLM 把新帖按主题分组（≤2 组、每组 ≥2 帖），创建系列并归入。
无权限时记录降级（Lv1 实测无 `thread.series.create`）。

## 14. emoji_enhancer — 表情点缀

从 `emoji/listEmoji` 拉取启用表情池（state 缓存），以约 55% 概率在出站
文本尾部追加一个 `:shortcode:`（已有表情则跳过）。

---

## 决策流水线

```
observe():  拉新帖 -> 元数据标注(作者/楼层/深度/own) -> is_replyable 过滤
            -> 楼层拉取(含楼中楼) -> mention 检测 -> 私信未读
decide():   digest(带元数据+配额) -> LLM JSON 计划(reply_targets...)
            -> _normalize_plan 白名单校验 -> 调度器叠加(daily_digest)
act():      按 feature 注册表执行；每个 feature 独立 try/except
reflect():  去重落账 -> 状态保存 -> 行为日志
```
