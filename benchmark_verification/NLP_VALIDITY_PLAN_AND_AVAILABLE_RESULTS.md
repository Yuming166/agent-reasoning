# NLP 有效性:计划与已有结果(benchmark_release_candidate_v1_20261006,阶段 D)

日期:2026-10-06。本文分开两类内容:**(1) 已有 automatic 结果**(来自冻结 v27lean 诊断与本地数据统计,未经人工验证);**(2) pending 计划**(离线可做;本轮未运行模型,不伪造分数)。资源边界:本地 CPU 离线;0 新训练、0 模型 API、0 链上/云查询。

## 1. 已有 automatic 结果(未人工验证)

### 1.1 事实标签构成(SEMANTIC_COVERAGE.json 同源)
- grounding gold(TRAIN,automatic):3,755 例 = role_binding 2,075 + owner_binding 840 + latest_relation 840;标签 supported 2,203 / conflicted 965 / **unknown 587(保留为状态)**。
- claim_required(fact_required)父动作:无 None;587 个 unknown 例携带**空列表**(=无需证据的 unknown 状态)。`not_available` 机制保留,当前计数 0。
- 三个定位 scope(candidate_relevant / claim_required / latest_relation)在 gold 中分列,不混填。

### 1.2 冻结 v27lean locator 诊断(aggregate,未经人工验证)
- 每外折(3 折,冻结 seed0):held 钱包 200/折;事实例 1,232/折;held fact 准确率 0.893(outer0),多数类基线 0.598;完整父动作 exact/micro-F1 = 1.0(定位闭包任务性质所致,不得写成"有效预测证据 100%");最新父动作命中 0.987;角色 micro-F1 0.830。
- **自然绑定变化切片**(措辞变化之外的真变化):76 例/折;train 措辞 0.842 / held 措辞 0.776(outer0)。
- **仅陈述/无关历史诊断**:claim_only_dependence 120 例,删除证据后预测变化率 0.292;编辑后事实标签重算为 unknown,不沿用原标签。
- 以上全部为 automatic 聚合;人工一致率字段保持空。

### 1.3 机器生成文本的来源标注
- action_views 的 text 字段是确定性模板渲染(程序生成),在 `structured_and_text_semantic_scope` 中声明与结构化字段同语义范围;数据集中不存在自由生成的机器文本。

## 2. pending 计划(离线可做,本轮未运行)

### 2.1 受控事实编辑与单元样例(确定性,可离线)
- 输入:grounding_gold 例 + 其引用父动作视图。
- 操作:对单父动作做确定性编辑(owner 交换 / 金额清零 / 时间平移 / 删除证据父动作),按冻结角色规则**重算**事实标签;编辑后若证据不足,标签重算为 unknown——绝不沿用原标签或未来行为标签。
- 产出:单元样例集 + 重算标签表,用于检查方法对"同一陈述、最小历史变化"的敏感性。
- 状态:**pending**;需要模型前向才能产生方法侧分数,本轮不运行。

### 2.2 模板内/模板外表达检查
- 计划:对同一事实构造"仅措辞不同"的两组陈述,检验事实判断是否随措辞漂移;与 1.2 的自然变化切片互补。
- 状态:**pending**(同上,不运行模型)。

### 2.3 无关历史/干扰注入诊断
- 计划:注入同 asset/不同 owner、同 owner/不同 asset 的干扰父动作,检验 scope 分离是否被破坏(评分器 `binding_tuple_errors` 已能标记 scope 混用错误)。
- 状态:**pending**。

### 2.4 人工审查(阶段 E 衔接)
- 所有 automatic 标签的验证只能由人工盲审完成(20-wallet pilot 优先);在人工数据存在前,任何"人工一致率"保持空/unknown,不得以 Claude 或其他模型判断冒充。

## 3. 不得声明的事项
- 定位/父动作任务的 exact=1.0 不得写成预测证据或预测能力 100%。
- claim_only_dependence 变化率 0.292 不得写成因果证据或可解释性证明。
- DEV/TEST 无角色包:任何角色方法的跨 split 差异首先是**来源覆盖差异**(SEMANTIC_COVERAGE.json critical_gap),不是泛化结论。
- 以上 automatic 结果未人工验证;引用时必须带 automatic 限定。

## 4. 证据指针
- QUALITY_AUDIT.json / SEMANTIC_COVERAGE.json(本阶段)
- SCORER_VALIDATION.json、SCORING_V27LEAN_TRAIN*.json(阶段 C)
- 冻结源:artifacts/action_evidence_rerank_v27lean_20261006/LOCATORS/*/seed0/outer_train/DIAGNOSTICS.json(未修改)
