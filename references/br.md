# 巴西（INPI）国家包

## 目录
- 一、程序与期限（despacho 图谱 / GRU / 上诉修改新规）
- 二、LPI 关键法条对照（葡语原文+中文释义）
- 三、驳回理由应对策略（含 6.23/7.1 战术、引证分级、同族运用）
- 四、模板与递交

答复巴西案件前完整阅读本文件；正式答复使用 assets/br-resposta-exigencia.md 模板。

---

# 一、程序与期限

## Despacho 全图谱

RPI 公布的审查行为以 despacho 代码标识，**不同代码对应不同的答复方式与缴费代码**：

| 代码 | 名称 | 含义 | 期限 | GRU 缴费代码 |
|---|---|---|---|---|
| 2.5 | Exigência formal（Art. 21） | 申请文件形式缺陷（缺文件/缴费瑕疵） | **30 天**（全流程最短） | 视具体事项 |
| 6.1 | Exigência Técnica | 实质审查意见：客体（10/18）、单一性（22）、充分公开（24）、清楚性（25）、修改（32）+ 可专利性（8/11/13/15） | 90 个日历日 | **207** |
| 6.21 / 6.23 | Exigência preliminar | 初步审查意见，附**国外同族检索报告**（6.23 适用于 2017 年起申请，Portaria INPI/PR 34/2022） | 90 个日历日 | **207** |
| 6.22 | Exigência preliminar | 初步审查意见，附 **INPI 自行检索**的检索报告 | 90 个日历日 | **207** |
| 6.7 | Outras exigências | 对 6.1/6.21-6.23 答复不满意后的补充意见 | 90 个日历日 | **207** |
| 7.1 | Conhecimento de Parecer Técnico | "审查意见知悉"：前述答复未说服审查员，给予**第二次（也是驳回前最后一次）陈述机会** | 90 个日历日 | **281**（不是 207！） |
| 9.2 | Indeferimento | 驳回决定 | 上诉期 60 天 | **214**（recurso） |
| 9.2.4 | Manutenção do Indeferimento | 维持驳回（未按期上诉时确认） | — | — |
| 11.2 | Arquivamento definitivo | 确定归档（未答复 6.1 等） | 不可上诉 | — |

答复 6.1/6.21/6.22/6.23/6.7 用 GRU 207（cumprimento de exigência）；答复 7.1 用 GRU 281（manifestação sobre o parecer）；提上诉用 GRU 214。**用错缴费代码会导致 petição 不被受理**。

## 一审答复的"三次机会"结构

巴西实务中申请人通常有三轮说服审查员的机会：
1. **初步审查意见**（6.21/6.22/6.23）：基于检索报告（多为国外同族或 PCT 检索结果）；
2. **6.1 实质审查意见 / 6.7 补充意见**：审查员全面审查后发出；
3. **7.1 审查意见知悉**：答复未说服审查员时发出——这是驳回前最后一次机会，要"留一张牌"，但也要全力应对，因为之后就是 9.2 驳回，只能上诉（上诉平均耗时 3–4 年以上）。

## 6.23 初步审查意见的直接驳回风险

Portaria INPI/PR 34/2022 明确规定：对 6.23 的答复若**既未提交能克服引证文献的修改后权项、也未提交实质论证**，申请将被**直接驳回**（indeferimento），不再给 6.1/7.1 轮次。因此 6.23 的答复必须"论证 + 修改"双齐全，不能走过场。

6.23 的 parecer 中引证文献带有相关性类别标记（沿用 PCT 分类）：
- **X**：单篇即可破坏新颖性/创造性——必须逐特征对抗或修改规避；
- **Y**：与其他文献结合时影响创造性——攻击组合逻辑；
- **A**：一般现有技术，无特别相关性——可指出其仅描述技术背景，并援引国外同族的正面审查结果支持可专利性，通常无需修改；
- **PN**：申请日在后、公开在后的巴西抵触申请，仅评新颖性（Art. 11 §2º/§3º）。

## 期限计算规则

- 期限自 RPI 公布该 despacho 后的**第一个工作日**起算（LPI 第 223、226 条）；首日不计、末日计入（第 222 条）。
- 90 天为 **dias corridos（日历日，含周末节假日）**——INPI 官方特别提醒不要把 90 天误算成"三个月"。
- RPI 每周二出版；INPI **不会主动发邮件通知**，须自行通过 Busca de Processos 监控或以公布日为准。
- **INPI 在线系统可达性差（2026-10 实测）**：busca.inpi.gov.br 经常超时/503，自动化环境几乎无法直连；Google Patents / EP Register / Espacenet 均**不收录 BR 的 despacho 法律状态事件**。因此"本案是否已发 6.23"往往无法自动确认——此时：①请用户提供 RPI 期号或 despacho 截图；②或引导人工核查（busca.inpi.gov.br → Pesquisa de Patentes → 输入申请号 → Despachos 页签；或翻查公布日后各期 RPI 公报）；③在等待本案 OA 期间，可以先按同族（EP/WO 检索报告）主引证做预案式答复草案，并在草案中显著标注"假定情形"。
- 期限连续（prazos contínuos，第 221 条），逾期权利自动消灭，**无延期制度**；唯一补救为 justa causa（第 221 条 §1º，举证严格，不可依赖）。
- 未按期答复实质审查意见 → 确定归档（11.2），且**不得上诉**（第 212 条 §2º）。

## 递交方式与缴费

- 一律通过 **e-Patentes** 电子递交：先在线生成并支付 GRU，再在系统中录入 GRU 的"Nosso Número"并附上答复文件；代理人还须附 procuração。
- 修改后权利要求**项数增加**的，须补缴审查费差额：GRU **código 800**（complementação de retribuição），凭证随答复一并提交。
- 逾期递交或缺缴费凭证 → petição 不予受理（LPI 第 218、219 条）。
- 外国申请人必须维持巴西境内合格代理人（第 216/217 条）；委托书（葡语，无需领事认证）须在当事人首次行为后 60 天内提交，否则申请确定归档。

## 驳回与上诉（recurso）

- 对 9.2 驳回决定：**60 天**内上诉至 INPI 局长（第 212 条），GRU 214；上诉有完全中止与移审效力，由 CGREC（上诉与无效协调总局）提供技术意见，行政终局（第 215 条）。
- 上诉书（razões de recurso）必须有具体的**事实与法律论据**；泛泛请求重审的"通用上诉"不予受理。
- 上诉阶段 INPI 可发 exigência 要求补充理由（第 214 条，60 天）。
- 核准后 60 天内缴颁证费（第 38 条 §1º），另有 30 天附加费宽限期。

## 上诉阶段修改规则（2024 年新规，重要）

规则演变：Portaria INPI/PR 52/2023 曾拟全面禁止上诉阶段修改；经业界反对，INPI 以 Parecer CGPI 19/2023 与 03/2024 及 **Portaria INPI nº 10/2024**（2024 年 4 月 2 日生效）确立**有限允许**的现行规则。上诉时提交修改后权项须同时满足：

a) **因果关联**：修改必须与一审驳回指出的缺陷直接对应，且能说明修改如何克服该缺陷；
b) **逻辑收窄**：只能是被驳回权项的逻辑限制性推导（convergência），不得重新引入一审中已放弃的主题，不得新增内容；
c) **来源限于权项**：收窄特征只能来自**从属权利要求的明示记载**或独立/关联权利要求的组合——**仅记载于说明书的特征不得用于上诉修改**（违反则修改不被接纳，INPI 会先依第 214 条发 exigência 给申辩机会，但不允许再改）；
d) **不得改变申请性质**（发明→实用新型），除非一审已提出过该请求。

上诉阶段允许提交实验数据/文件**仅为支撑创造性论证**，不得含新内容。一审中已放弃或未答复的问题在上诉中**失权**（preclusão）。

**由此推导的一审策略（务必向用户强调）**：所有有价值的退路特征必须在一审阶段就写进（从属）权利要求；说明书里有但从权没有的特征，到上诉阶段就用不了了。

## 特殊情形

- **医药专利**：ANVISA 事先同意（原第 229-C 条）已于 2021 年被 Lei 14.195 废除；医药案件正常由 INPI 审查。新用途权利要求按**方法权利要求**对待；剂量方案、给药途径、患者人群不构成新颖性特征（INPI 化学审查指引方向，2025 年征求意见版亦延续此立场）。
- **遗传资源**：涉及巴西遗传资源/传统知识（PG/CTA）的申请会收到 despacho 6.6.1 自动 exigência（60 天），须提交 CGEN 登记号或附说明的积极声明（GRU 264）；暂未取得的，审查结论会暂停直至补齐。
- **分案**：审查终结前可提（第 26–28 条），保留申请日/优先权；单一性反对或保护被放弃主题时使用。
- **恢复**：因未提审查请求而归档，60 天内可 desarquivamento（第 33 条）；其他归档可 3 个月内 restauração（第 87 条，缴费）。
- **宽限期**：申请日/优先权日前 12 个月内源于发明人的公开不破坏新颖性（第 12 条）。
- **审查排队**：2024 年 1 月起按**提出审查请求的日期**排队（不再按申请日）；PPH（与 EPO/JPO/KIPO/USPTO 等有协议）与 PT-Verde 等优先审查通道可大幅缩短周期。

## 知识来源

本文件内容依据：LPI 9.279/96 官方合并文本（planalto.gov.br）、INPI 官方快速指南（6.1/7.1 与 6.21/6.22/6.23）、Portaria INPI/PR 34/2022、Portaria INPI 10/2024 及 Pareceres CGPI/PFE-INPI 19/2023 与 03/2024、RPI 公告文本，以及 Guerra IP、Kasznar Leonardos、Peduti、Murta Goyanes、SMA、Dannemann/Di Blasi Parente 等巴西律所实务解读（检索于 2026-10）。法规与 INPI 口径可能更新，重大案件递交前请核对最新版本。

---

# 二、LPI 关键法条对照

葡语原文摘自总统府公布文本（planalto.gov.br/ccivil_03/leis/l9279.htm，含 Lei 14.195/2021 等修订）；中文为工作释义。答复文件中引用法条时用葡语原文。

## 可专利性要件

**Art. 8º** — É patenteável a invenção que atenda aos requisitos de novidade, atividade inventiva e aplicação industrial.
（发明须满足新颖性、创造性、工业实用性。）

**Art. 9º** — É patenteável como modelo de utilidade o objeto de uso prático, ou parte deste, suscetível de aplicação industrial, que apresente nova forma ou disposição, envolvendo ato inventivo, que resulte em melhoria funcional no seu uso ou em sua fabricação.
（实用新型：实用物品的新形态/新布置，含创造性活动，带来功能改进。）

**Art. 13** — A invenção é dotada de atividade inventiva sempre que, para um técnico no assunto, não decorra de maneira evidente ou óbvia do estado da técnica.
（创造性：对本领域技术人员非明显/显而易见。）

**Art. 14** — O modelo de utilidade é dotado de ato inventivo sempre que, para um técnico no assunto, não decorra de maneira comum ou vulgar do estado da técnica.
（实用新型创造性活动：非"普通/常见"即可，标准低于发明。）

**Art. 15** — A invenção e o modelo de utilidade são considerados suscetíveis de aplicação industrial quando possam ser utilizados ou produzidos em qualquer tipo de indústria.

## 现有技术与宽限期

**Art. 11 §1º** — O estado da técnica é constituído por tudo aquilo tornado acessível ao público antes da data de depósito do pedido de patente, por descrição escrita ou oral, por uso ou qualquer outro meio, no Brasil ou no exterior...
（绝对新颖性：申请日前全球任何方式公开。）

**Art. 12** — 12 个月宽限期：申请日/优先权日前 12 个月内由发明人、INPI（未经同意公布）、或基于发明人信息的第三方所作的公开，不构成现有技术。INPI 可要求提交公开声明及证明。

## 客体排除

**Art. 10**（不视为发明/实用新型）：
- I – descobertas, teorias científicas e métodos matemáticos（发现、科学理论、数学方法）
- II – concepções puramente abstratas（纯抽象构思）
- III – esquemas, planos, princípios ou métodos comerciais, contábeis, financeiros, educativos, publicitários, de sorteio e de fiscalização（商业/金融/广告等方法）
- V – programas de computador em si（计算机程序本身）
- VI – apresentação de informações（信息呈现）
- VII – regras de jogo（游戏规则）
- VIII – técnicas e métodos operatórios ou cirúrgicos, bem como métodos terapêuticos ou de diagnóstico, para aplicação no corpo humano ou animal（人体/动物外科、治疗、诊断方法）
- IX – o todo ou parte de seres vivos naturais e materiais biológicos encontrados na natureza...（天然生物体及生物材料，含基因组）

**Art. 18**（不可专利）：
- I – 违反道德、公共秩序与健康的；
- II – 原子核变换产物；
- III – 生物体整体或部分，**转基因微生物除外**（须满足 Art. 8 三要件且非单纯发现）。

## 说明书与权利要求

**Art. 24** — O relatório deverá descrever clara e suficientemente o objeto, de modo a possibilitar sua realização por técnico no assunto e indicar, quando for o caso, a melhor forma de execução.
（充分公开 + 最佳实施方式。）

**Art. 25** — As reivindicações deverão ser fundamentadas no relatório descritivo, caracterizando as particularidades do pedido e definindo, de modo claro e preciso, a matéria objeto da proteção.
（权利要求须以说明书为依据、清楚准确地限定保护主题。）

**Art. 22** — 单一发明构思（único conceito inventivo）。

## 修改、分案与审查程序

**Art. 32** — 申请人为更好澄清或界定申请，可在**提出审查请求之前**修改，且修改限于原始揭示范围。

**Art. 26/27/28** — 审查终结前可分案（依职权或应请求）；分案须引用原申请、不超原揭示范围；保留原申请日与优先权；单独缴费。

**Art. 36**（审查意见答复核心条款）：
> Quando o parecer for pela não patenteabilidade ou pelo não enquadramento do pedido na natureza reivindicada ou formular qualquer exigência, o depositante será intimado para manifestar-se no prazo de **90 (noventa) dias**.
> § 1º Não respondida a exigência, o pedido será definitivamente arquivado.
> § 2º Respondida a exigência, ainda que não cumprida, ou contestada sua formulação, e havendo ou não manifestação sobre a patenteabilidade ou o enquadramento, dar-se-á prosseguimento ao exame.

（意见不认可可专利性/归类不当/提出任何要求时，申请人 90 天内答复；不答复→确定归档；只要答复——即使未满足要求或仅对要求的成立性提出异议——审查继续。）

**Art. 31** — 申请公布至审查终结前，任何利害关系人可提交文件与信息辅助审查（第三方意见）。

**Art. 33** — 审查请求须自申请日起 36 个月内提出；逾期归档后 60 天内可请求恢复（desarquivamento）。

## 上诉与期限通则

**Art. 212** — 除另有规定外，本法所指决定均可上诉，上诉期 **60 天**。§1º 上诉具有中止与完全移审效力。§2º 对**确定归档**与**核准**决定不得上诉。§3º 上诉由 INPI 局长裁决，行政程序终结。

**Art. 215** — 上诉决定为终局，行政层面不得再上诉。

**Art. 221** — 期限连续，逾期权利自动消灭，除非当事人证明因 justa causa（不可预见、非其意愿、阻碍行事的突发事件）未能行事。

**Art. 222/223/224/226** — 期限计算：首日不计、末日计入；自官方公报（RPI）公布后第一个工作日起算；无明确规定时默认 60 天；INPI 行为自公布之日起生效。

**Art. 87** — restauração：自归档/失效通知起 3 个月内，缴费可请求恢复申请/专利。

## 已废止提示

**Art. 229-C（已废止）** — 原规定医药产品/方法专利须经 ANVISA 事先同意（anuência prévia），已被 **Lei 14.195/2021** 废除。答复涉及医药案件时不要再引用该条作为程序前提。

---

# 三、驳回理由应对策略

## 通用论证结构

每项反对意见的答复按四段式组织（葡语小标题可用：Análise / Diferenciação / Efeito técnico / Conclusão）：
1. 重述审查员的认定与依据的法条、引证文件；
2. 指出区别特征或认定错误（事实层面）；
3. 论证区别特征带来的技术效果与本领域技术人员的认知过程（法律适用层面）；
4. 小结：权利要求满足相应要件，请求撤销该项反对。

多份引证文件组合评价创造性时，先逐份排除单篇破坏新颖性/创造性的可能，再攻击组合逻辑。

## 按 despacho 类型的答复战术

### 6.23 / 6.21 / 6.22（初步审查意见，附检索报告）

- **必须"论证 + 合格权项"双齐全**：Portaria INPI/PR 34/2022 规定，答复若既未提交能克服引证文献的修改后权项、又无实质论证，将被**直接驳回**（跳过 6.1/7.1），只剩上诉一途（上诉平均 3–4 年）。切忌形式化答复。
- 随答复重新提交说明书、摘要、附图及修改后权项的全套替换页（INPI 公告文本明确要求 reapresentar 各文件版本）。
- 逐份评论检索报告中的文献：类别、公开内容、与权项的差异、为何不破坏可专利性。
- 引证文献全部只是 A 类（一般背景）时：指出无 X/Y 类文献，并强调国外同族检索/审查的正面结论（EP、PCT、US 等），通常**无需修改权项**。

### 6.1（实质审查意见）

- 审查员此时已全面审查：法条 8/10/11/13/15/18/22/24/25/32 均可能涉及，逐项编号回应，不要遗漏任何一项（漏答的问题到上诉阶段会失权）。
- 权项修改必须能在说明书中找到依据（Art. 25），否则审查员有权拒评新版本。

### 7.1（审查意见知悉，驳回前最后一次机会）

- 审查员已明确表示"未被说服"。答复要**升级论证强度**：补充更细的特征对比、更具体的技术效果证据（可提交实验数据支撑创造性）、更清晰的法律适用分析。
- 同时保留部分论据作为上诉筹码，但不要因为"留牌"而在 7.1 阶段提交明显弱化的答复——争取在一审终结前解决，远比上诉划算。
- 7.1 用 GRU **281** 缴费，不是 207。

### 上诉（recurso，对 9.2）

- 上诉书须有具体的事实与法律论据；泛泛请求重审不予受理。
- 修改空间已被 Portaria INPI 10/2024 大幅压缩：仅限从权明示特征的收窄，不得引入仅记载于说明书的特征（详见本文件"上诉阶段修改规则"节）。起草上诉书时同步评估现有从权里还有哪些收窄组合可用。
- 可以提交实验数据/文件，但只能用于支撑创造性论证，不能引入新内容。

## 引证文献分类与应对（X / Y / A / PN）

INPI 检索报告沿用 PCT 式分类标记：

| 标记 | 含义 | 应对 |
|---|---|---|
| **X** | 单篇即破坏新颖性或创造性 | 逐特征对照找未公开特征；找不到则修改并入区别特征 |
| **Y** | 与另一篇结合才影响创造性 | 攻击组合的教导/动机、领域差异、结合障碍 |
| **A** | 一般现有技术，非特别相关 | 说明其仅构成背景；援引国外同族正面结果；无需修改 |
| **PN** | 公开在后的巴西在先申请（抵触申请） | 仅评新颖性；核对两案申请日/优先权日与公开日 |

先核对每份文献的**公开日**是否早于申请日/优先权日；PN 类还要核对其申请日/优先权日。

## 运用国外同族审查结果

INPI 明确将国外审查结果作为审查基础（降积压计划），但保持独立判断。实务要点：

- **INPI 不偏好任何特定外国局的权项版本**——不必照搬 EP/US 授权文本，可在巴西争取更宽的保护范围（这是一大优势）。
- 即使提交的权项与国外已授权同族一致、引证文献也相同，**仍应完整提交新颖性/创造性论证**（可复用国外答复的论证逻辑），强化授权前景，不要只写"请参照某局授权"。
- 引证文献与国外 OA 重合时，优先复用已在国外成功的论证与修改，但要按 LPI 法条和葡语表述重新组织。
- 巴西无 PTA/PTE/最低保护期（STF ADI 5529 后），拖延直接损耗商业独占期——答复质量和一次通过率就是金钱。

## 新颖性（novidade，Art. 11）

- 巴西采**绝对新颖性**：申请日前在世界任何地点以书面、口头、使用或任何方式公开即构成现有技术（Art. 11 §1º）；另含巴西在先申请未公开内容（§2º，仅评新颖性）。
- 应对：
  - **特征对照表**：将权利要求全部技术特征与引证文件逐一对照，指出至少一项特征未被直接、无歧义地公开（ausência de antecipação direta e inequívoca）；
  - 审查员常用"隐含公开"（divulgação implícita），要求其论证本领域技术人员必然且唯一地得到该特征；
  - 核查引证文件公开日，优先权成立时以优先权日为准；
  - 核查是否落入 12 个月宽限期（Art. 12）；
  - 若单篇文献确实公开全部特征：从说明书/从属权项并入区别特征收窄，勿做无谓抗辩。

## 创造性（atividade inventiva，Art. 13）

定义：对本领域技术人员（técnico no assunto）而言，非以明显或显而易见方式（de maneira evidente ou óbvia）从现有技术得出。实用新型适用 Art. 14（ato inventivo，标准更低：非"普通/常见"——de maneira comum ou vulgar）。

INPI 的分析路径接近"最接近现有技术 + 客观技术问题 + 显而易见性"。答复要点：
1. **确定最接近现有技术**及区别特征；
2. **重构客观技术问题**：基于区别特征实际实现的技术效果，防止审查员把区别特征本身写进技术问题（变相事后诸葛亮）；
3. **攻击组合动机**：多篇文献组合需有教导/动机，指出技术领域差异、组合障碍、相反教导（afastamento do ensinamento）；
4. 指出审查意见的**事后分析**（análise hindsight / conhecimento a posteriori）痕迹——以申请文件为蓝图倒推组合；
5. 主张**意料不到的技术效果**（efeito técnico inesperado）：说明书中有对比数据时务必引用具体段落/实施例；
6. 从权项附加特征未被任何引证文件评价，论证独权落入从权范围即具备创造性。

## 可专利性客体（Art. 10 / Art. 18）

Art. 10 为"不视为发明/实用新型"清单，高频项：
- **III**：商业、会计、金融、教育、广告、抽奖、监督的方案/计划/原理/方法——论证方案解决了具体技术问题、产生了技术效果，而非纯商业规则；
- **V**：计算机程序本身（programas de computador em si）——参照 INPI 计算机实现发明审查指引：若要求保护的是由程序实现的技术方法/系统、产生超出常规软硬件正常交互的技术效果，即非"程序本身"。把独权改写为 método implementado por computador / sistema 并强调技术手段与技术效果；
- **VIII**：人体/动物外科、治疗、诊断方法——改写为用途/产品形式；注意巴西将**新用途权利要求按方法权利要求**对待，且剂量方案、给药途径、患者人群不构成新颖性特征；
- **IX**：自然界存在的天然生物体/生物材料（含基因组、天然生物过程）——主张分离、修饰、非天然状态的产物，强调人工干预。

Art. 18 为"不可专利"：
- **III**：生物体整体或部分，**转基因微生物除外**（需满足 Art. 8 三要件且非单纯发现）；植物/动物品种不在保护范围——转向生产方法、培养物、组合物等替代主题。

## 说明书充分公开（suficiência descritiva，Art. 24）

- 标准：本领域技术人员依据说明书即可实施，并指明最佳实施方式。
- 应对：引用说明书具体段落说明实施路径完整；可援引申请日时的公知常识补强（不得新增内容）；提交技术文献/声明作为辅助证据。
- 警告：公开不充分**无法通过修改克服**（补内容即超范围），只能抗辩；预判不足时及早评估撤回重报或分案的可行性。

## 权利要求清楚与支持（clareza e fundamentação，Art. 25）

- 相对术语（aproximadamente、substancialmente 等）、参数无测量方法、功能性概括过宽是高频反对点；INPI 还会审查**权项间引用关系**是否正确、用词是否会被误读。
- 应对：以说明书定义/实施例澄清术语；将相对表述替换为说明书中的具体范围；删除说明书无对应记载的特征；功能性限定改为结构/步骤限定。
- 此类反对通常用**修改**解决，成本低、成功率高，不建议硬抗。

## 单一性（unidade de invenção，Art. 22）与分案

- 标准：多项发明须相互关联、构成单一发明构思（único conceito inventivo）——论证各组权利要求共享的**特定技术特征**（对现有技术有贡献的特征）。
- 应对两选一或并用：
  - 抗辩单一性成立；
  - 删除/放弃一组权利要求，就该主题在**审查终结前**提交分案（Art. 26-28，保留申请日与优先权）。
- 审查员同时指出单一性 + 创造性问题时，优先保住商业价值最高的一组。

## 修改策略通则

- 只能**收窄**：并入从属权项特征、并入说明书记载的特征、限定数值范围、删除并列方案。
- 每项修改必须给出**原始申请文件中的出处**（页码/段落/原权项号），制作修改依据表；超范围修改本身会成为新的反对理由（亦见 Art. 50 III 无效事由）。
- 采用"抗辩 + 修改"双层结构：主请求维持原权项并论证；**辅助请求**（subsidiariamente）提交收窄后的权项。
- **一审就把退路写进从权**：上诉阶段只能收窄到从属权项明示的特征（Portaria INPI 10/2024），说明书独有的特征届时无法使用。6.23/6.1 答复是构筑上诉弹药库的最后好时机。
- 答复后权利要求项数增加时记得补缴 GRU 800（见本文件"程序与期限"章）。

---

# 四、模板与递交

- 答复模板：`assets/br-resposta-exigencia.md`（**中/英/葡三语对照**的 RESPOSTA À EXIGÊNCIA TÉCNICA，含 6.1/6.23/7.1 三种情形的递交说明；正式提交仅用葡语部分，提交前删除中英对照）。
- 交付组合：葡语正式答复 + 修改清稿/对照 + 修改依据表 + 中文摘要（反对意见清单、答复思路、风险与后续期限）。
