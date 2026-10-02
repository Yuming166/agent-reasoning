# EX-Graph v2 因子/证书验证器设计（2026-09-30）

## 目标与边界

`scripts/verify_factors_certificates_v2.py` 是独立的、label-free 的 as-of 验证器。它只把每个 `(wallet, cutoff)` 投影为 `case_id/wallet/cutoff/split/evidence`，在内存中不保留未来活动、新对手方或未来目标字段。所有计算均使用严格满足 `event_time < cutoff` 的 `raw_events.jsonl` 事件。

它不调用 LLM，也不训练模型；用途是先固定可执行因子和证书协议，之后再作为 teacher 输出的独立 executor。

## 因子定义

### `repeat_recency`

- 历史窗口：`[cutoff - 30d, cutoff)`。
- 事件范围：钱包主动发出的 `external_tx`，且有 `counterparty_address`。
- 规则：某一对手方在窗口内至少出现 2 笔事件。
- 证书：窗口、对手方、分母、计数、全部见证事件的 canonical event IDs、最新见证事件。

### `activity_shift`

- 比较两个不重叠窗口：近期 `[t-30d,t)` 与先前 `[t-60d,t-30d)`。
- 事件范围同上。
- 规则：两窗口事件数差值非零；输出 `up` 或 `down`。
- 证书：两个窗口边界、两侧计数、差值及两侧事件 IDs。差值为 0 时为 `insufficient`，不输出伪证书。

### `typed_graph_path` / `shared_contract_path`

只接受如下严格历史路径：

```text
wallet --(outgoing event, token_contract=c)--> peer
peer   --(outgoing event, same token_contract=c)--> another_counterparty
```

两笔事件均必须早于 cutoff，且事件类型、合约地址、节点地址和 event IDs 均由原始事件索引重新核对。该定义不是“共享 token 字符串”的文本匹配，也不使用未来 active 节点筛选。

## Event ID 与旧 `E1` 兼容

验证器为每条原始事件生成 `ev:<24位sha256前缀>`。旧 cases 中的 `E1` 等局部 ID 不直接视为真实事件；只有能通过钱包、交易 hash、时间、event family、event index、sequence index 唯一匹配原始事件时才被解析为 canonical ID。无法匹配或多重匹配均拒绝。

本次 720 cases 审计：

- 原始事件：58,979；
- cases：720；
- 局部证据别名唯一解析：8,640；
- 歧义解析：0。

## Teacher proposal 最小输入

JSONL 每行可为：

```json
{
  "case_id": "wallet:cutoff",
  "factor": "repeat_recency",
  "evidence_event_ids": ["ev:..."],
  "rule": {"op": "recent_repeat", "window_days": 30, "min_count": 2}
}
```

也接受 `{case_id, proposal: {...}}`。验证器会重新执行规则，并检查：

1. factor 是否在冻结本体中；
2. 每个 evidence ID 是否是 cutoff 前真实事件；
3. evidence 是否属于 executor 重新计算出的 witness 集合；
4. shared-contract path 的两条 typed edge 是否真实存在；
5. 不满足条件时返回 `rule_insufficient`，不把自然语言或 ID 存在性当成证明。

## 本次运行产物

- `artifacts/factor_certificate_verifier_v2_20260930_run03/`
  - `factor_certificates.jsonl`
  - `factor_summary.csv`
  - `manifest.json`
- `artifacts/factor_certificate_verifier_v2_20260930_run04/`
  - `smoke_proposals.jsonl`
  - `proposal_verification.jsonl`
  - `proposal_verification.csv`

`run03` 的 720 cases 因子可执行率：

| factor | verified | insufficient |
|---|---:|---:|
| repeat_recency | 394 | 326 |
| activity_shift | 611 | 109 |
| typed_graph_path | 3 | 717 |

这些是历史证据可执行覆盖，不是预测准确率，也不涉及未来标签。

## 当前限制与下一步

1. `typed_graph_path` 当前是最小严格路径，覆盖仅 3/720；应先作为稀疏高精度因子，不宜强行扩展为高覆盖“图解释”。
2. `repeat_recency` 和 `activity_shift` 目前为程序枚举器；teacher 只能选择这些已生成的 factor/rule/certificate，不能自由发明阈值或证据。
3. 下一步可把本脚本作为 `run_temporal_wallet_hypotheses_v4.py` 的独立 executor：LLM 只输出 factor、rule 和 event IDs；证书由本脚本重新生成，不接受模型回传的数值、counterparty 或 path 作为事实。
4. paired revision 应对原始 history 做受控删除/时间移动后重新运行本 executor，由证书状态和 metric 变化判定 `CHANGE/INVARIANT/WITHDRAW`，而不是按编辑类型预设标签。
