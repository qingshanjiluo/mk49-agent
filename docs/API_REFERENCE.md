# mk49.top（龙之归宿）论坛 API 参考

> 从 SPA bundle（umi.js）逆向 + 实测整理。API 根：`https://forum.mk49.top/bbs`
> 资源根：`https://forum.mk49.top/bbs/resources/<filePath>`

## 认证

```
GET  /bbs/login/captcha          -> {id, image(data:image/png;base64) | svg}
POST /bbs/login                  {username,password,captcha_id,captcha_text}
```

请求头（登录后全部携带）：

| Header | 值 |
| --- | --- |
| authorization | token（原样，无 Bearer 前缀） |
| mbbs-userid | 用户 id |
| mbbs-fingerprint* | 可选浏览器指纹 |
| mbbs-silent-operation | 禁言用户写操作时置 1 |

## 线程

```
GET    /bbs/threads/list            page_limit/page_offset/sort/category_id/keywords/user_id/is_essence
GET    /bbs/threads/{id}            详情
POST   /bbs/threads/create          {category_id,title,content[,series_id][,is_draft][,polls]}
POST   /bbs/threads/{id}            编辑 {title,content,category_id,series_id,is_draft,polls}
DELETE /bbs/threads/{id}            删除（自己的）
POST   /bbs/threads/{id}/move       {category_id}
POST   /bbs/threads/setEssence      {thread_id,is_essence}
POST   /bbs/threads/setSticky       {thread_id,is_sticky}
POST   /bbs/threads/setApproved     {thread_id,is_approved}
POST   /bbs/threads/setDisablePost  {thread_id,disable_post}
POST   /bbs/threads/setLike         {thread_id,is_like}
POST   /bbs/threads/batchDelete     {thread_ids}
POST   /bbs/threads/restoreDelete?thread_id=
POST   /bbs/threads/checkCanCreate  {category_id} -> {canCreate,todayCreateCount,...}
GET    /bbs/threads/listMyDrafts
GET    /bbs/threads/getForAdmin?id=
```

`content` 为 HTML（`<p>`…）；编辑器是 Vditor markdown，提交时前端转 HTML。

## 评论与楼中楼

```
GET    /bbs/posts/list              ?thread_id=&user_id=&page_limit=
GET    /bbs/posts/listComments      ?post_id=&page_limit=   （某楼的楼中楼）
POST   /bbs/posts/create            {thread_id,content}      一级评论
POST   /bbs/posts/createComment     {post_id,content}        楼中楼（可对楼中楼再回）
POST   /bbs/posts/{id}              {content}                编辑
DELETE /bbs/posts/{id}              删除
POST   /bbs/posts/setLike           {post_id,is_like}
POST   /bbs/posts/setSticky         {post_id,is_sticky}
POST   /bbs/posts/batchDeletePosts  {ids:"1,2,3"}
```

楼中楼返回体带 `is_comment:true, reply_post_id, reply_user_id`。

## 投票

```
GET  /bbs/polls/listByThread?thread_id=
POST /bbs/polls/vote          {poll_id, option_id}   单选传 int，多选传数组
GET  /bbs/polls/voters        ?poll_id=&option_id=
```

发帖带投票：`threads/create` 的 `polls:[{poll_id:"tmp_poll_...", allow_multiple,
anonymous, result_visible_after_vote, is_closed, options:[{text,sort}]}]`，
且 content 中须有占位符 `[点击编辑投票](mbbs-poll:<poll_id>)`；
需要 `thread.createPoll` 权限（Lv1 无）。

## 资源上传

```
POST   /bbs/resources    multipart: fileName + file[]   -> {filePath:"mk48by049/xxx.png"}
DELETE /bbs/resources/{filePath}
```

需权限 `attachment.create.1`。引用 URL：`/bbs/resources/<filePath>`。

## 用户

```
GET /bbs/users/getLoginUser
GET /bbs/users/{id}            GET /bbs/users/getByName?name=
GET /bbs/users/list            ?search=&page_limit=
GET /bbs/permissions/getPermissions?group_id=
```

Lv1 组关键权限：`thread.reply` `thread.like` `thread.votePoll`
`attachment.create.1` `category{2,5,8,16,24,27,36,37,39}.createThread`。

## 板块（实测）

2=聊天 5=反馈 8=网址 12=慕白区 15=管理区 16=教程 21=档案馆
24=未认证用户区 27=其他游戏区 29=限言区(hidden) 30=回收站(hidden)
32=新人必读 36=科普区 37=教程区-其他 39=舰队区

## 消息 / 卡片 / 系列 / 其他

```
GET  /bbs/message/unreadMessageCount
GET  /bbs/message/listMessage?page_limit=
POST /bbs/message/readMessage {message_id}   /readAllMessage /removeMessage
GET  /bbs/content-cards/resolve?thread_ids=&user_ids=
GET  /bbs/series?user_id=        POST /bbs/series {name,description}
GET  /bbs/category/listCategory  /group/listGroup /identity/listIdentity
GET  /bbs/emoji/listEmoji        （:shortcode: 语法，帖内渲染成图片）
GET  /bbs/threadTag/listAllTag   /listEditableTagForCategory?category_id=
POST /bbs/threadTag/bindTagForThread {thread_id,tag_id}
GET  /bbs/moderation-records/list（需权限）
GET  /bbs/chatAccount/me         POST /bbs/chatAccount/create
```

## 内容内联语法

| 语法 | 效果 |
| --- | --- |
| `[threadcard:123]` | 帖子卡片（每帖最多 10 张） |
| `[usercard:1501]` | 人物卡片 |
| `:miao:` | 站内自定义表情 |
| `![alt](url)` | 图片（markdown） |
| `[点击编辑投票](mbbs-poll:ID)` | 投票占位 |

## 错误约定

```json
{"success":false,"name":"UIError","message":"..."}
```

限速类消息含 `请在 N 秒后重试`，客户端应按 N 等待。
