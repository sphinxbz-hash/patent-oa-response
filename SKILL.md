---
name: patent-oa-response
description: 各国专利审查意见答复技能（当前覆盖巴西 INPI、美国 USPTO、欧洲 EPO，可扩展）。当用户收到专利审查意见（office action / exigência / communication under Art. 94(3) / final rejection 等），需要解析驳回理由、制定答复策略（意见陈述、权利要求修改、分案/续案）、起草该国语言的正式答复文件、计算答复期限与官费、处理驳回后救济（上诉 recurso/appeal、RCE、复审），或根据申请号联网研究国外同族审查历史以复用外国论证时使用。触发词包括：专利审查意见答复、OA response、office action、INPI、USPTO、EPO、exigência、巴西/美国/欧洲专利答复、final OA、Art. 94(3)、RCE、专利上诉。
---

# 各国专利审查意见答复

## 通用红线（任何法域）

1. **期限第一**：先算截止日再谈内容。各国期限规则见对应国家包；用户没给发文日/公布日时必须询问。
2. **语言合规**：巴西=葡萄牙语；美国=英语；EPO=程序语言（英/德/法）。
3. **修改不出圈**：不得引入原始申请未记载的内容；答复后期阶段修改受限——退路特征尽早在从属权项布局。
4. **工作底稿声明**：AI 产出为代理人工作底稿，须由该国执业代理人审核并递交。

## 工作流程

输入只有一个：**一个申请号（不限法域）**。产出三样：**同族审查历史文档、最新审查意见与答复文件（或可下载链接）、答复草案（意见陈述书 + 权利要求修改标记页）**。

### 第 0 步：识别法域，加载国家包

按申请号前缀/审查局确定法域，**完整阅读对应国家包**后再动手：

| 法域 | 申请号特征 | 国家包 | 答复模板 |
|---|---|---|---|
| 巴西 INPI | BR 10/11/20/21/22 开头 | [references/br.md](references/br.md) | [assets/br-resposta-exigencia.md](assets/br-resposta-exigencia.md) |
| 美国 USPTO | 申请号 16/17/18 开头；公开号 US 20XX/ | [references/us.md](references/us.md) | [assets/us-oa-response-template.md](assets/us-oa-response-template.md) |
| 欧洲 EPO | EP XX XXX XXX；公开号 EP 4XXXXXX | [references/ep.md](references/ep.md) | [assets/ep-reply-94-3-template.md](assets/ep-reply-94-3-template.md) |

未覆盖的法域：用本技能通用流程+方法论处理，并明确告诉用户"该法域暂无国家包，以下内容按通用规则生成、需当地代理人核对"。

### 第 1 步：同族研究 + 文件获取

执行 [references/family-research.md](references/family-research.md)，产出**两类交付物**：

1. **同族审查历史文档**（保存为 md 交付用户）：同族对照表 + 各局审查时间线 + 可复用论证清单；
2. **最新一次审查意见与答复文件**：按可达性分两种交付方式——
   - 可直接下载的局（EPO Register、WIPO PatentScope、INPI 公开页）：**下载 PDF 保存到输出目录**供用户打开；
   - 被反爬拦截的局（USPTO Patent Center）：给出**手动下载指引**（案卷页 URL + 应下载文件的名称与日期清单），请用户在正常浏览器下载后回传。

同时确定本案的 **pending claims**：以案卷中最新的权项文件为准（EP 案卷可直接取最新 "Claims" 文件）；自动渠道只能拿到公开文本时，必须标注并请用户确认"公开后是否提交过修改"。

### 第 2 步：解析审查意见，制定策略

本案 OA 来源：用户上传，或本案本身处于可直连的局（EP/INPI）时从案卷获取。逐条提取审查员认定，按该国驳回理由分类（见国家包）；记录发文日/公布日、答复期限、缴费要求。

对每项反对意见选择并组合：**抗辩 / 修改（附修改依据表）/ 分案或续案**。通用论证方法论见 [references/argumentation-core.md](references/argumentation-core.md)；法域特定打法见国家包。复用同族论证前必须先过"法域差异过滤"（argumentation-core.md 末节）。

### 第 3 步：起草答复草案并交付

以对应国家包的模板起草，交付**一套四件**：

1. **意见陈述书**（该国语言正式文本）；
2. **权利要求修改标记页**（删除=删除线、新增=下划线；格式规范见 argumentation-core.md"交付物规范"）；
3. **修改后权利要求清洁稿** + 修改依据表；
4. **中文摘要**：反对意见清单、答复思路、修改说明、风险与后续期限、缴费与递交提醒。

## 扩展新法域

新增国家时只需：在 references/ 增加 `{国家码}.md`（程序期限 + 法条 + 驳回应对）、在 assets/ 增加模板、更新上方路由表与 description 触发词。编写前先核对该国官方现行法规与审查基准。
