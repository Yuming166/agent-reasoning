# 标注指南(ANNOTATION_GUIDELINES)— eth-actions-benchmark-v1.0.0-candidate

版本:2026-10-06。本指南面向人工盲审(pilot 20 钱包优先)。**程序答案、模型预测、未来窗口数据一律不在标注包内**;标注者的判断字段在人类填写前保持空。机器(Claude 或其他模型)的任何输出不得记为人工审查。

## 1. 任务与材料

每个标注单元来自一个查询 (wallet, UTC cutoff)。你将看到:
- `history_parent_refs`:该钱包截止前的父动作引用(相对路径指向 `parent_actions/{split}.jsonl.gz`);
- `entity_alias_map`:实体别名映射(仅由严格历史前缀产生);
- grounding 任务中的 `claims`(陈述)与 `candidate_address`(候选);
- forecast 任务中的窗口起止时间戳。

你不会看到:程序计算的 target、任何 scope 的 gold 父动作集合、fact 标签、模型预测、7 天窗口内的任何链上材料(窗口源材料由协调者在受控步骤单独提供)。

## 2. 关键定义(与 RELEASE_PROTOCOL.md 第 4 节一致)

### 2.1 合格 outgoing external attempt(forecast 任务)
- `event_family == 'external_tx'`,钱包是真实 `from_address`;
- 目标非 null/空/全零地址、非 self;
- **attempted 口径**:失败回执 (receipt_status=0) **算合格**;零金额调用、合约创建同样按冻结规则处理,不按"成功且金额>0"筛选;
- 时间窗:`[cutoff, cutoff+7天)`,含头不含尾;
- 顺序:canonical `(block_number, transaction_index, event_index)`,取第一笔;
- 无此类动作 → inactive。

### 2.2 三个定位 scope(grounding 任务,三者分开标注,不得混填)
1. `candidate_relevant_parent_ids`:与候选出现相关的父动作(程序相关性);
2. `claim_required_parent_ids`:**该陈述成立所必需**的证明动作;无法从可信来源确定时,标 `not_available`,不要用第 1 类代填;
3. `latest_relation_parent_ids`:陈述中精确关系 key 的**最新一次**观察。

同一父动作可以同时出现在多个 scope;每个 scope 独立给出你自己的判断。

### 2.3 fact 标签(supported / conflicted / unknown)
- `supported`:历史中存在支持该陈述的证据;
- `conflicted`:存在与陈述冲突的证据;
- `unknown`:证据缺失或无法判定。**unknown 是状态,不是父动作 id**;不要把 "UNKNOWN" 写进任何 scope 的父动作列表。

### 2.4 unknown 边界(不要"补全")
- `raw_transaction = null` ≠ 没有调用;
- 空 raw log 列表 ≠ 没有 log(另标 raw_log_source_coverage=unknown);
- 缺少本钱包角色包 = unknown,**永远不要**复制其他钱包的角色证书;
- 本地观察完整 ≠ 完整 EVM 执行、当前真实 allowance、主观意图。这些一律 unknown。

### 2.5 金额与共指
- 不同 token 的原始金额不跨资产相加、不换算;
- 实体共指仅以 `entity_alias_map`(严格历史前缀)为准。

## 3. 流程

1. **独立标注**:两名标注者各自独立完成,不交流中间判断;在 `annotator_1_raw_judgment` / `annotator_2_raw_judgment` 原样记录;
2. **争议裁决**:不一致项由第三方(或两人协商后)在 `dispute_adjudication` 记录最终判断与理由;
3. **一致性计算**:在全部标注完成后统一计算(逐 scope exact、fact 一致率、Kappa),写入 `agreement_computation`;
4. 在此之前,所有标注字段保持空;任何未填写的字段在报告中如实报 pending。

## 4. 禁止事项

- 不查看程序 gold 文件(`forecast_gold/`、`grounding_gold/`、`gold_crosswalk/`)后再标注;
- 不把任何模型输出(包括 Claude)写进人工字段;
- 不在标注前查询链上或任何外部数据源;材料以发放的离线包为准;
- 不修改包内文件;判断只写入标注表的空字段。

## 5. pilot 范围

- 20 钱包(见 `pilot20/wallet_list.json`,种子 20261006):grounding 115 例、forecast 窗口 60 查询;
- pilot 目标:估计单例耗时、指南歧义率;完成后按 `BUDGET_PLAN_200CORE_80CHALLENGE.json` 的未执行预算方案决定是否扩展(200 随机 core + 最多 80 困难层;困难层只用历史结构/缺失/绑定规则定义)。

## 6. 记录归属

所有人工字段空缺时,数据集报告中保持 `human_status: pending`。自动标签(现有 grounding gold)在任何人工验证完成前只称 **automatic labels**。
