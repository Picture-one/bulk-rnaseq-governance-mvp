# T2 科研结果人工复核指南

## 自动判定

- PASS：counts 结构、样本列、数值域、GENCODE gene ID、参考追溯和 QC 均符合冻结规则。
- WARN：没有硬失败，但存在需人工解释的指标，例如 mapping 介于警告区间、rRNA/线粒体比例达到警告值、链方向不符或可选指标未报告。
- FAIL：缺少必须文件、样本列不一致、重复/空/未知 gene ID、NaN/Infinity/负值、低于 mapping 硬阈值或参考无法追溯。FAIL 不进入人工接受流程。

## 复核内容

至少检查：

1. `validation_report.json` 和 `validation_summary.tsv`；
2. `gene_counts` 的样本列及数量；
3. MultiQC 报告中的 reads、mapping、rRNA、线粒体和 strandedness；
4. T2B 的样本相关性/PCA 是否支持重复一致性；
5. input/reference manifest、参数和 run provenance；
6. WARN 的科学原因及是否影响拟开展的研究问题。

## 记录决定

```bash
uv run rnaseq-mvp review \
  --stage T2A \
  --run-id <RUN_ID> \
  --reviewer reviewer-001 \
  --decision accept \
  --comment "已核查counts、MultiQC、参考版本和运行溯源，警告不影响当前研究用途" \
  --workspace /data/rnaseq/runtime
```

决定只能写入一次，不能覆盖。WARN 的意见必须至少包含 20 个非空白字符，明确说明警告、判断依据和适用限制。若复核不足，应选择 `reject`；不得先 accept 再手工修改记录。

接受后运行 `package`。PASS 对应 `READY_FOR_RESEARCH`，经审查的 WARN 对应 `READY_WITH_REVIEWED_WARNINGS`。发布包仍不是“任意研究直接可用”：研究者必须结合研究设计完成下游过滤、标准化、协变量/批次建模和统计分析。
