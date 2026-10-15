# patent-oa-response

专利审查意见答复 skill：根据申请号研究同族审查历史、取得可获取的案卷文件，并辅助拟定答复策略和工作草案。

**当前版本：0.2.1，Kimi 基线发布版。** 保留 Kimi 的 SKILL.md、国家参考资料和模板原文；本次补充安装、打包、校验及维护文档。欧洲案例已有检索意见和申请人回复原件可核对；巴西案例仍属于假定审查意见下的预案。已知问题见 [KNOWN_ISSUES.md](KNOWN_ISSUES.md)，本版本尚未修复这些核心问题。

## 安装

仓库根目录就是 skill 目录，SKILL.md 是入口。需要安装整个目录，包括 references/ 和 assets/。

### 让 agent 安装

把下面这段话发送给支持从 GitHub 安装技能的 agent：

> 请从 https://github.com/sphinxbz-hash/patent-oa-response 安装 patent-oa-response skill，技能路径是仓库根目录，安装目录名为 patent-oa-response。先阅读 README 和 KNOWN_ISSUES，再确认当前版本的适用范围。

### Codex

在已带 skill-installer 的 Codex 中，可直接提出上面的安装请求。调用标准安装器时，根目录必须同时指定 --name：

```bash
python "$HOME/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py" --repo sphinxbz-hash/patent-oa-response --path . --name patent-oa-response
```

Windows PowerShell（需要 Python 命令可用）：

```powershell
python "$HOME\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py" --repo sphinxbz-hash/patent-oa-response --path . --name patent-oa-response
```

若自定义了 CODEX_HOME，把上述 .codex 路径换成该目录。指定 --ref 加提交SHA或已发布标签，可固定版本，避免复现实验时跟随 main 变化。

### 其他支持 SKILL.md 的 agent

```bash
git clone https://github.com/sphinxbz-hash/patent-oa-response.git
```

将整个 patent-oa-response 目录放入目标 agent 的技能目录。不同产品的安装目录、重新加载方式与 .skill 支持情况不同，应按其说明操作。

也可下载仓库 ZIP 后解压并将目录重命名为 patent-oa-response。.skill 文件是包含同名根目录的 ZIP 包，仅供支持这种导入方式的 agent 使用；不支持时使用目录安装。

## 使用

示例请求：

> 使用 patent-oa-response。以 CN117691670A 为检索入口，研究欧洲等同族的审查历史，交付取得的审查意见、答复和权项原件。目标法域为巴西。先确认本案 OA 与当前有效权项；缺少本案资料时只生成明确标注假设的策略预案，不把欧洲申请人的意见写成审查机关认可。

如果已持有本案通知书和待审权项，同时提供这些文件及版本信息。单独一个申请号可以启动检索，但不保证所有法域的案卷可自动取得，也不能保证已核验答复期限。

## 当前覆盖

| 法域 | 参考资料 | 模板 | 本版本定位 |
| --- | --- | --- | --- |
| 巴西 INPI | [br.md](references/br.md) | [葡语/中英工作模板](assets/br-resposta-exigencia.md) | 有已知规则问题，需结合问题清单核验 |
| 欧洲 EPO | [ep.md](references/ep.md) | [EPO答复模板](assets/ep-reply-94-3-template.md) | 有案卷获取案例；回复提交不等于审查认可 |
| 美国 USPTO | [us.md](references/us.md) | [US答复模板](assets/us-oa-response-template.md) | 访问能力及程序规则须按当次情况核实 |
| 中国及其他法域 | 通用研究方法 | 暂无专门国家包 | 不宣称已经实现专门的中国OA答复模块 |

输出通常包括：同族审查历史、取得的原件与缺件清单、意见陈述书、权项修改标记稿及清稿、修改依据表、中文摘要。本仓库提供指引和模板，不内置收费数据库账号、通用自动下载服务或无人审核的提交功能。

## 迭代和版本

- [CHANGELOG.md](CHANGELOG.md)：发布变化与上游历史。
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md)：已发现问题，修复后逐项关闭并保留证据。
- [CONTRIBUTING.md](CONTRIBUTING.md)：修改、验证、提交和版本规范。
- [DEPLOY.md](DEPLOY.md)：维护者发布步骤。
- [UPSTREAM.json](UPSTREAM.json)：Kimi 来源文件的校验值，便于比对基线。

本地检查和打包仅需要 Python 3.10+ 标准库：

```bash
python scripts/package_skill.py --check
python scripts/package_skill.py --build
```

输出位于 dist/：版本化 .skill、.zip 和 SHA256SUMS.txt。GitHub Actions 配置为提交/PR时检查并生成构建附件；是否运行成功以仓库 Actions 结果为准。GitHub Release 是否存在及附件是否发布，以实际 Release 页面为准。

## 来源与许可

由用户提供的 Kimi patent-oa-response v0.2.0 基线整理。核心文件在本次打包发布中保持不变；已知问题不代表已经修复。MIT 许可沿用上游 [LICENSE](LICENSE)。具体案件的原件、分析草案和本地路径不属于本发布包。
