# mbbs.cc 站点被黑事件 — 排查与修复报告

**事件对象**：`mk48by049.mbbs.cc`（mbbs.cc 平台托管的「龙之归宿 mk49」论坛）
**报告时间**：2026-11-15
**处置人**：石井（本地工作区执行层）
**关联自有站**：`forum.mk49.top`（125.208.22.194，自托管，未受影响）

---

## 一、事件结论（已实锤）

黑客（署名 `jz`）对 `mk48by049.mbbs.cc` 做了**站点设置级篡改**，注入全屏勒索覆盖页。

篡改位置 = 站点设置的 **3 个键**（经 `GET setting/getAll` 匿名读全量比对确认）：

| 键 | 被改后 | 原值 |
|---|---|---|
| `site_name` | `hk by jz` | `龙之归宿` |
| `site_introduction` | `HK BY JZ - QQ 3783129055 / Q群 1080785768` | `mk49 \| 龙之归宿\n` |
| `site_custom_append_body_html` | 注入整页 HTML（`#jz-root` 覆盖层，隐藏原 SPA） | `""`（空） |

**内容未被删除**：全站 28,867 帖完整，所有分类完好。「数据已备份，问题请到群里说」（QQ 3783129055 / Q群 1080785768）为勒索/接管话术。该站 2026-07-07 已公告迁移至 mk49.top 后冻结，黑客是在迁移后的废弃站上做的接管展示。

---

## 二、攻击路径分析

黑客拿到的是**站长级权限**（`setting/set` 与平台 `manage/*` 接口对普通号均正确返回「无权操作/无权调用」→ 权限模型本身正常）。

最可能成因：
1. **站长账号 `admin`（昵称 049）弱口令被爆破** — 平台登录验证码仅 `ddddocr` 一档（本机 bot 即用它一发即过登录），爆破成本极低；注册无需邮箱/手机，站长号无强身份锚点。
2. 无多因素认证（MFA），拿到密码即完全接管。

---

## 三、漏洞检查结果（安全墙加固清单）

| # | 漏洞/风险 | 严重度 | 位置 |
|---|---|---|---|
| 1 | **上传扩展名校验不完整**：`.php` 扩展名可上传落盘（`probe2.php` 返回 200 原样直出） | 中 | `POST /bbs/resources` |
| 2 | **上传黑名单只拦 `.html` 类**：「不允许上传可执行网页/脚本文件」，`.php` 未拦 | 中 | 同上 |
| 3 | **登录验证码强度不足**（`ddddocr` 一发即过）→ 支持密码爆破 | 高 | `POST /bbs/login` |
| 4 | **无 MFA** | 中 | 认证 |
| 5 | **站长账号无邮箱强绑定**（`sendResetPasswordEmailVerifyCode` 需 email，说明可绑但未见绑定） | 中 | 找回 |
| 6 | **`setting/getAll` 匿名可读全量**（含站点管理配置面） | 低 | 信息泄露 |
| 7 | 自有站 `forum.mk49.top`：`setting/getAll` 亦匿名可读；无自定义注入 | 低 | — |

> 注：`.php` 在 Node/OSS 静态托管下仅作为静态文件直出、不触发解释器执行，RCE 危害低；但若私有化部署走本地磁盘 + 可执行容器则风险升级。**已建议平台方修复扩展名白名单。**

---

## 四、删除勒索信的可行路径（需其一）

真正删除那 3 个设置键需要站长权限或平台方介入。三选一：

- **路径 A（最快）**：操作者提供站长 `admin` 账号凭据 → 用现成 MBBSClient 登录 → `setting/batchSet` 写回原值 → 改强密码 → 踢出所有登录会话。
- **路径 B**：操作者提供站长绑定邮箱 → `sendResetPasswordEmailVerifyCode` + `resetPasswordByBindEmail` 自助重置密码 → 同 A 清设置。
- **路径 C**：向 mbbs.cc 平台方（官方论坛 `bbs.mbbs.cc` 站务）提交本报告 + 上传漏洞证据，请平台重置站长密码或直接代清 3 键。

---

## 五、修复后加固（自有站 forum.mk49.top 立即执行）

1. 轮换 `zzhx` 账号弱口令（`qwertyuiop` → 强随机）；其他账号同查。
2. 站长 `admin` 绑定邮箱 + 开启登录校验（`register_validate`/`create_thread_validate` 已开，`site_enable_third_platform_login` 建议关闭）。
3. 上传接口走扩展名+魔数白名单（图片类仅 `png/jpg/webp/gif`），`.php/.jsp/.html/.svg` 全拒。
4. `setting/getAll` 脱敏（敏感管理键仅管理员可读）。
5. 平台侧：提交 .php 上传绕过漏洞，请求补扩展名黑名单。

---

## 六、取证产物（本地已固化）

`G:\皮皮\编程项目\admin_bot\security_audit\out\`
- `audit_stage1.json` 全站内容/用户面扫描
- `audit_stage2_settings.json` 被黑站 vs 自有站设置全量
- `audit_stage3_restore_attempt.json` 写回尝试（权限拒绝证据）
- `audit_stage4_admin_probe.json` 平台管理面鉴权边界
- `audit_stage5_content_integrity.json` 内容完整性（28,867 帖未删）
- `audit_stage6_admin_rotation.json` 站长定位 + 改密探测
- `audit_stage7_upload_reset.json` 上传扩展名校验 + 密码重置链路
- `audit_stage8_php_confirm.json` `.php` 上传绕过实锤
- `umi_bundle.js` 平台前端 bundle（API 面逆向依据）