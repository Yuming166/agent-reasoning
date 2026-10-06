# 发布协议 v1(benchmark_release_candidate_v1_20261006)

日期:2026-10-06。本文件冻结本候选版本的任务定义、窗口、输入权限、角色定义、统计单位与旧队列使用记录。它是工程与效度审计合同,不是新方法搜索;不预设论文结论或语言预测增益。

## 1. 任务定义(与 BENCHMARK_SPEC v1 一致,不改历史实验)

- **查询**:q=(wallet, UTC cutoff)。历史仅 `timestamp < cutoff`。
- **主预测目标**:`[cutoff, cutoff+7天)` 内第一笔合格、由钱包发起的 external ATTEMPT 的 `to`:
  - qualifying = `event_family=='external_tx'`、钱包为真实 `from_address`、目标非 null/空/全零地址、非 self;
  - **attempted 口径**:保留 `receipt_status=0` 失败回执;不做成功/金额过滤;
  - 顺序 = canonical `(block_number, transaction_index, event_index)`;
  - 无此类后续动作记 `inactive`(仅表示声明来源窗口内无合格 external 动作)。
- **两个评测入口**:
  1. **完整检索与预测**(track=retrieval):截止前历史 + 版本化合法索引;输出至多 50 个不同合法对象。主分母 = 全部合格活跃查询;Top5 / MRR@5 / Recall@50。
  2. **固定 50 精排**(track=fixed_pool):同一历史 + 独立冻结参考 Top50;必须完整排序同一 50 个对象,池外失败。
- **四类实质结果**分列:`y∉D`(索引域外)、`y∈D` 但不在该方法 50、在 50 不在 5、在 5。非法/缺失输出单列,仍计主任务失败。不把域外失败称为随机或不可预测。

## 2. 三个域对象(不混用)

1. **全局合法可见域 D(t)**:声明来源中截止前可观测地址(共享 first-seen 索引),不依赖答案或学习方法;
2. **方法提名域 R(q)**:方法自建候选,是 D(t) 子集,单报;
3. **参考 Top50**:独立冻结的固定池,不是世界,也不按目标入池筛总体。

## 3. 历史与标签窗口

| split | 钱包 | 查询 | cutoff | 标签窗口 | 来源 |
|---|---:|---:|---|---|---|
| train | 600 | 1800 | 2022-05-01/03/05 | 各+7天 | offline_chain_events_v1_20260929_full(2022-05.parquet) |
| dev | 150 | 150 | 2022-05-15 | +7天 | offline_chain_events_v1(2022-05.parquet) |
| external test | 250 | 250 | 2022-06-01 | +7天 | external_fresh250/canonical_ledger.parquet(独立获取,至2022-06-08) |

合计 1000 钱包、2200 查询。活跃查询 985/84/95(共 1164)。**三个历史队列均已探索**;本候选包不将它们重命名为 fresh test。

## 4. 角色、unknown 与语义边界

- **role_observation**:owner/asset/candidate/role/modality/token_id/time/parent_id/source_field/verification/missingness。来源未知不填已知;NFT 缺 tokenId 不做精确状态键;request/event 不混同。
- **unknown 规则**(与 views 构建一致):缺失语义源 = unknown,永不复制他钱包的证书;`raw_transaction=null` ≠ 无调用;空 raw log 列表 ≠ 无 log(另标 `raw_log_source_coverage=unknown`);无本钱包 packet 保持 `unknown_missing_packet`,不是 role=false。
- **三种定位 scope 严格分开**:
  1. `candidate_relevant_parent_ids` = 程序相关性(候选出现的相关父动作);
  2. `claim_required_parent_ids` / `fact_required_parent_ids` = 具体陈述的必要证明动作;
  3. `latest_relation_parent_ids` / `fact_latest_parent_ids` = 精确关系 key 的最新观察。
  "父动作定位100%"不得写成"有效预测证据100%"。
- 无法从可信源确定陈述必要父动作时标 `not_available`,不用候选通用相关集代填。
- **边界主张**:本地观察完整 ≠ 完整EVM执行、当前真实 allowance、钱包主观意图或后续动作原因。统一 schema ≠ 统一语义覆盖(TRAIN 30483/53024 本钱包可信角色;DEV 0/13411;TEST 0/25270)。
- 不同 token 原始金额不跨资产相加;共指仅由 query 严格历史前缀产生。

## 5. 统计单位

- wallet-parent 视图(91,705)≠ 物理交易;真实不同父交易 ID 83,065 单报。
- 跨钱包共享父交易 3,912、跨 split 共享 1,934:不是新增独立事件,不自动构成泄漏,单独计数报告。
- 主结果保留重叠日历查询;钱包聚类配对 bootstrap 为配对推断单位;逐 cutoff、目标集中度敏感性另报。

## 6. 同时间钱包 OOF 与向前时间评价分开

- TRAIN 的 label-trained 粗筛/R0 采用嵌套钱包外折 OOF(3 外折);这是**同时间钱包 OOF 开发筛查**。
- DEV(05-15)与 external TEST(06-01)是**向前时间**评价,但钱包与时段均已探索,不得称独立确认或新时间泛化。
- 原 400 确认队列**不进入本候选包**:不读取其标签/预测/逐例结果,不用其选择任何配置。其标签获取与开标签登记已完成、root 曾部分暴露(EXPOSURE_EVENT.json);V24/V26 开标签前冻结的模型与预测保持原协议,不修改、不重新评价。

## 7. 输入/答案隔离(导出合同)

- 预测输入(query/parent_action/role/text_view)不得出现 target、gold_parent、latest=true 等答案性标记。
- gold(forecast/grounding)放独立目录,引用相对路径;主 gold 由原 external 来源产生,不强插真实目标、不按目标入池筛总体。
- 程序自动事实标签没有人工验证前只称 automatic labels;人工一致率字段保持空/unknown,不填模拟值。

## 8. 冻结与状态增补

- 所有上游冻结记录(CONFIG_FROZEN、COHORT_FROZEN、TEST_COHORT_FROZEN、V27lean 全套、V24/V26 锁)原样保留;本候选包不覆盖、不重写任何既有文件。
- 本候选目录新增 `SPLIT_EXPOSURE_LEDGER.json`,为旧快照写状态增补,引用 POSTBUILD_REVIEW(2026-10-06T09:15:45Z)与 EXPOSURE_EVENT(2026-10-06T08:50:43Z)。
- 偏差与失败记录保留原样;新发现的问题在新文件登记,不回改。

## 9. 资源与停止边界

本地 CPU 离线;0 新训练、0 模型 API、0 链上/云查询、0 新确认队列;不读取他人端点/凭据;不上传不发布。人工审查与实际发布仍未完成,本包为本地发布候选。
