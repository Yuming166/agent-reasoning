# AI 使用说明

- 本数据集候选由 Claude Code(GLM/Anthropic CLI 会话)在人类授权与协议约束下构建:读取冻结记录、写构建/评分脚本、执行校验并撰写文档;所有构建决策遵循 RELEASE_PROTOCOL.md 与 handoff 合同。
- **数据本体**是 2022 年以太坊公开链上事实,与 AI 无关;AI 未生成任何链上内容。
- `action_views` 的 text 字段为程序模板渲染(确定性代码输出),逐条在 `structured_and_text_semantic_scope` 声明;数据集中无自由生成的机器文本。
- grounding gold 为**程序自动标签**;Claude 或其他模型的判断未被记为人工审查;人工一致率字段全部为空,等待真实人类标注(阶段 E 材料)。
- 已有模型诊断(v27lean locator)来自本项目训练的 Qwen3.5-4B 定位器,在 RESULTS.json 冻结;其输入接口与限制见原记录。
