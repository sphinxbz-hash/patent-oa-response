# Changelog

本项目记录版本变化。下方0.2.0及更早条目为Kimi上游记录，其中“全流程验证”等表述不代表维护者已独立确认；以README和KNOWN_ISSUES中的当前状态为准。

## [0.2.1] - 2026-10-15

### Packaging
- 保留Kimi的SKILL.md、references和assets原文，以及原MIT许可。
- 补充目标仓库安装说明、已知问题清单、贡献/发布规范和来源校验值。
- 增加仅依赖Python标准库的结构校验、确定性打包和SHA-256清单。
- 增加提交和PR时的GitHub Actions检查与构建附件。

### Status
- 本版未修复核心法律/论证规则；不是“巴西实案答复已验证”的声明。
- 案例原件和工作草案不随本仓库发布。

## [0.2.0] - 2026-10-15

### Added
- EP 国家包新增「八、案卷文件获取（EP Register 实战）」：doclist 全选 + Zip Archive 整包下载通道（实测 22 份 135 页整包可用）；单文件直链限流（403）的避坑说明；EP 案卷文件类型码对照（1503=ESR、1703=ESOP、1082=R.70a 通知、CLMSABEX=修改权项清稿等）
- BR 国家包新增 INPI 在线系统可达性警示与人工核查降级路径（busca.inpi.gov.br 超时/503 实测；BR despacho 不被 Google Patents/Espacenet 收录）

### Validated
- 全流程端到端实战验证：BR 10 2024 025604-2（阳光电源，巴黎公约直申，电学 H02J3/38）
  - 步骤①：Google Patents 同族检索 + CN 优先权案首页 (74) 栏回溯核实中国代理机构——确认"BR 著录无中国代理信息，须回溯 CN/PCT 首页"为有效核实链
  - 步骤②：EP4568088 案卷（ESR 三篇 X 类引证 + ESOP 6 页 + 申请人 2025-12-11 答复全套）整包获取并通读
  - 步骤③：基于 BR 葡语 pending claims + EP 同族历史产出答复草案四件套（意见陈述书三语版 / 权项修改标记页 / 清稿与修改依据表 / 中文摘要）；确认 EP 修改方案向 BR 移植时的本地化要点（BR 无同类多独权限制；修改依据可在 BR 说明书段落闭环）
- 确认 USPTO Patent Center / Global Dossier 对自动化环境需认证或 403，US 案卷维持人工指引

## [0.1.0] - 初始版本

### Added
- 三步流程技能骨架：法域识别 → 同族审查历史研究 → 答复草案产出
- 国家包：BR（despacho 图谱/GRU 代码/2024 上诉修改新规）、US（AFCP/After Final/RCE/Track One）、EP（PSA/Rule 137/口审分层）
- 模板：BR 三语意见陈述书、US OA response、EP Art. 94(3) reply
- family-research.md 同族研究规范、argumentation-core.md 论证方法论
