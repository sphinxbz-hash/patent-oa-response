# 发布与安装验证

目标仓库：sphinxbz-hash/patent-oa-response。默认分支：main。

## 发布前

1. 更新 VERSION 与 CHANGELOG.md，确认已知问题仍在 KNOWN_ISSUES.md 中准确标注。
2. 执行 python scripts/package_skill.py --check 和 python scripts/package_skill.py --build。
3. 检查提交清单只包含 skill 和维护文件。案件原件、工作草案、账户凭据和本地路径不入库。
4. 打包校验通过仅证明安装结构完整，不证明法律结论正确。

## 提交版本

现有仓库的日常修订建议使用功能分支和 Pull Request。发布版本时，在所选提交上创建与 VERSION 一致的标签，如 v0.2.1，再创建 GitHub Release。

把同一提交生成的版本化 .skill、.zip 和 SHA256SUMS.txt 附在 Release 上。Release 说明应区分仅打包/文档调整、行为修订、规则更新和实案验证。不要因外国申请人已递交答复，就写成该局已接受该策略。

## 发布后验证

1. 在 GitHub 打开默认分支 SKILL.md，确认前言、相对引用和文件目录完整。
2. 从远端下载该提交到全新的临时技能目录，验证入口、参考资料、模板都可读取。
3. 对 Release 附件重新计算 SHA-256，与 SHA256SUMS.txt 对比。
4. 记录实际提交 SHA、标签、远端安装测试结果。不要把“本地已打包”写成“远端已发布”。

不需要为了发版新增长期令牌；优先使用已有、与目标账号一致的授权。
