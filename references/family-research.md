# 同族情报自动研究工作流（申请号 → 可复用论证）

收到巴西 OA 后、制定答复策略前执行本流程，自动还原案件的全球审查地图。产出直接进入 objection-playbook.md 的"运用国外同族审查结果"环节。

## 目录
- 第 0 步：申请号格式转换
- 第 1 步：Google Patents 锚定同族
- 第 2 步：PatentScope 调取 PCT 案卷
- 第 3 步：逐局深挖审查历史
- 第 4 步：综合产出
- 可达性对照与风控

## 第 0 步：申请号格式转换

INPI 申请号与公开号格式不同，联网查询前必须转换：

| INPI 申请号（含校验位） | Google Patents 公开号 | 说明 |
|---|---|---|
| BR 11 2019 020201-3 | BR112019020201A2 | PCT 国家阶段（发明），A2=公开文本 |
| BR 10 2023 001234-5 | BR102023001234A2 | 直接申请（发明） |
| BR 20 2023 000123-4 | BR202023000123U1 | 实用新型（U1） |
| 授权后 | ……B1 | B1=授权文本 |

规则：去掉空格与校验位（连字符后的数字），按审查状态加种类码（公开=A2，授权=B1，实用新型=U1）。查不到 A2 时试 B1。

## 第 1 步：Google Patents 锚定同族

访问 `https://patents.google.com/patent/{公开号}/en`，提取：
- **Worldwide applications**：全部同族成员及各国公开号（点击可跳转各成员页）；
- **Priority and Related Applications**：优先权链；
- **Legal events / Application events**：法律状态（授权、驳回、视撤等）；
- **Claims / Description**：葡语权项与说明书全文（附自动英译）；
- **Patent citations**：审查引证文献；
- **External links**：Espacenet、**USPTO Global Dossier**、PatentScope 的直达链接——保留这些链接供后续步骤使用。

## 第 2 步：PatentScope 调取 PCT 案卷

若同族含 WO 成员（PCT 申请），访问 `https://patentscope.wipo.int/search/en/detail.jsf?docId={WO文档号}`：
- 取 **ISR**（国际检索报告）与 **IPRP/IPER**（国际初步审查意见）：国际阶段的现有技术与可专利性结论，是 6.23 答复最直接的复用素材；
- 查看进入各国家阶段的记录与对照译文。

## 第 3 步：逐局深挖审查历史

按对本案的参考价值排序深挖（EP/US 文件历史最透明，优先）：

| 局 | 入口 | 目标内容 | 可达性 |
|---|---|---|---|
| INPI | Busca de Processos（busca.inpi.gov.br） | 本案 despacho 历史、已提交文件 | ✅ 公开（葡语界面） |
| USPTO | Patent Center（正常浏览器） | file wrapper：OA、答复、授权权项 PDF | ⚠️ 文件本身免费免登录公开，但自动化环境被 CloudFront 拦（API 405、页面反爬验证，Global Dossier 403）；**自动链降级**：Google Patents 取著录/法律事件/授权权项/审查员引证，OA 与答复全文请用户在正常浏览器打开 patentcenter.uspto.gov/applications/{申请号} 手动导出 |
| EPO | European Register（tab=doclist） | 审查历史、94(3) 通知及附件、答复+修改全文、EESR | ✅ 实测全通，免登录免验证，案卷全部文件可列表可下载——**EP/US 同族时优先用 EP 案卷替代被拦的 US 案卷**（同文献同争辩，论证全文可得） |
| WIPO | PatentScope | ISR/IPRP、国家阶段 | ✅ 较好 |
| JPO | J-PlatPat | 审查経過、拒絶理由通知 | ⚠️ 日文界面 |
| KIPO | KIPRIS | 심사 경과 | ⚠️ 韩文界面 |
| CNIPA | — | 官方系统需登录+验证码，**不直接抓取** | ❌ 用 Google Patents 的 CN 著录/法律状态替代 |

对每局提取四要素：**审查结论、引证文献（及对比对象权项）、申请人答复的论证/修改、最终权项版本**。

## 第 4 步：产出同族审查历史文档

将研究结果写成 md 文档保存到输出目录交付用户，内容固定为：

1. **同族对照表**：局 / 申请号 / 当前状态 / 关键引证 / 权项版本差异（与本案在审权项相比）；
2. **各局审查时间线**：OA 发文日、答复日、修改节点、授权/驳回结果（EP 直接取自 Register 事件列表；US 取自 Google Patents 法律事件）；
3. **可复用论证清单**：哪局克服了哪篇文献、用的什么论证或修改（注明出处文件与日期）；
4. **缺口提示**：国外未遇到、本案独有的反对意见风险。

## 第 5 步：交付最新审查意见与答复文件

对**每个有实质审查历史的同族成员**，交付其最新一次 OA 与答复，按可达性两种方式：

- **可直接下载**（EPO Register tab=doclist、WIPO PatentScope、INPI 公开页）：下载 PDF 存输出目录，文件名含局+日期+文件类型（如 `EP-2026-02-11-审查意见.pdf`）；
- **反爬拦截**（USPTO Patent Center）：在文档中列出**手动下载指引**——案卷页 URL（`patentcenter.uspto.gov/applications/{申请号}/ifw/docs`）+ 应下载文件的名称与日期（如 "Non-Final Rejection dated …"、"Response filed …"），请用户在正常浏览器下载后回传；缺失期间以 Google Patents 授权权项+审查员引证+EP 同族案卷替代，并在产出中标注"US 案卷全文未取"。

## 答复建议的衔接

同族研究结论在三表之后汇入答复草案阶段：将国外成功路径映射到本案 OA 的引证分级（X/Y/A/PN），给出"复用论证 / 复用修改 / 需另行应对"的逐项结论。

## 可达性对照与风控

- 稳定通道（实测）：Google Patents（著录/同族/法律事件/引证）、EP Register（案卷全文）、PatentScope、INPI Busca。
- USPTO 自动抓取受反爬限制时，替代信息组合：Google Patents 授权权项（反映审查员认可的最终文本）+ 审查员引证列表 + EP 同族案卷全文（覆盖争辩内容）；并在产出中明确标注"US 案卷全文未取，需人工补"。
- 任何自动抓取的文件都必须标注来源 URL 与抓取日期；**引用国外答复内容前，人工核对原件**。
- 各局法域差异（客体适格、修改规则）由 argumentation-core.md"法域差异过滤原则"与各国家包过滤，禁止把国外结论不经本国法律校验直接写进答复。
