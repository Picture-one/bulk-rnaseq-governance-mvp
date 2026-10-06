# RNA-seq profile 扩展后处理设计说明

本文档说明当前 MVP 代码结构对两个新增 RNA-seq profile 的支持边界：

1. `human_illumina_rrna_depletion_bulk_v1`
2. `human_longread_rnaseq_v1`

这次修改的目标不是一次性完成所有真实上游分析流程，而是先把 MVP 从“只认识一个 Poly(A)+ paired-end STAR/Salmon 流程”扩展为“按 profile 和 method family 分流的治理框架”。这样后续接入真实 GEO/SRA 数据、rRNA depletion 数据和长读长 RNA-seq 数据时，不会把不同技术路线混成同一种 counts。

## 1. 已保留的原始 MVP 路线

原始 MVP 路线仍然是：

- 数据类型：Homo sapiens、Illumina 短读长、常规 Bulk RNA-seq、Poly(A)+
- 方法：nf-core/rnaseq 3.26.0
- 核心工具：STAR + Salmon + tximport
- 主要 counts：`star_salmon/salmon.merged.gene_counts.tsv`
- measure type：`estimated_counts_unscaled`

现有 `T2A`、`T2B` 的定义和验证逻辑保持兼容。

## 2. rRNA depletion Bulk RNA-seq 扩展

`human_illumina_rrna_depletion_bulk_v1` 面向：

- Homo sapiens
- Illumina 短读长
- Bulk RNA-seq
- rRNA depletion / Ribo-Zero 等建库
- single-end 或 paired-end FASTQ

该 profile 当前仍可复用 `nf-core/rnaseq 3.26.0` 的 STAR + Salmon + tximport 路线，因此 method family 仍为：

```text
shortread_star_salmon
```

与 Poly(A)+ 不同的是，rRNA depletion 数据的 reads 组成、rRNA 残留解释和建库方向推断可能不同，因此新增独立 validation policy：

```text
bulk_rnaseq_rrna_depletion_v1
```

当前代码已经支持 single-end 样本生成 nf-core samplesheet：`fastq_2` 字段留空。

## 3. long-read RNA-seq 扩展

`human_longread_rnaseq_v1` 面向：

- Homo sapiens
- Oxford Nanopore 或 PacBio 等长读长 RNA-seq
- 第一版只治理 gene-level counts

长读长 RNA-seq 不能当作 STAR + Salmon 的小参数变化。当前代码将其单独定义为：

```text
method_family: longread_gene_counts
method_profile_id: longread_rnaseq_minimap2_gene_counts_v1
counts_measure_type: assigned_longread_gene_counts
```

当前 long-read 支持的是后处理输出契约，要求结果目录中存在：

```text
longread/gene_counts_raw.tsv
longread/alignment_summary.tsv
longread/longread_qc_metrics.tsv
longread/provenance.json
```

这意味着：后续可以接入 minimap2 + gene assignment 的确定性上游流程，但不能把 long-read 结果伪装成 Salmon estimated counts。

## 4. 输入定义变化

数据集定义现在增加或放宽了以下字段：

- `profile_id`
- `source_database`
- `library_selection`
- `read_layout`
- `strandedness`
- `sequencing_center`

样本文件支持：

- paired-end：必须有一个 `R1` 和一个 `R2`
- single-end：必须只有一个 `R1`
- long-read：必须只有一个 `R1`

这些约束在 Pydantic 模型层执行，避免静默接受不完整或不明确的数据。

## 5. 输出与验证分流

验证器现在根据 `method_family` 分流：

| method_family | counts 文件 | 主要用途 |
| --- | --- | --- |
| `shortread_star_salmon` | `star_salmon/salmon.merged.gene_counts.tsv` | Poly(A)+ 和 rRNA depletion 短读长 |
| `longread_gene_counts` | `longread/gene_counts_raw.tsv` | 长读长 gene-level assigned counts |

短读长继续读取 MultiQC/STAR/Salmon 相关指标；long-read 当前先要求长读长后处理产物存在，后续再扩展更细的 long-read QC 指标解析。

## 6. 当前边界

本次修改已经完成“代码结构可扩展”的第一步，但仍有边界：

- 已新增 long-read 命令分流入口，但当前命令是 `rnaseq-mvp-longread` 的受控占位入口；真正的 minimap2/featureCounts 执行包装仍需下一步实现和服务器验证。
- 尚未新增真实 rRNA depletion 或 long-read stage。
- 尚未将公共数据库 Excel 目录自动映射为这些 profile。
- 已新增 long-read 后处理 helper，可写出 `longread/gene_counts_raw.tsv`、`alignment_summary.tsv`、`longread_qc_metrics.tsv` 和 `provenance.json`；long-read QC 仍需继续扩展为指标级验证。

这些边界是有意保留的，目的是先把数据模型和后处理分流做稳，再逐步接入真实数据。

## 7. long-read MVP 的新增入口

当前 long-read MVP 已经与 short-read 路线分开：

- prepare 阶段会额外生成 `longread_samplesheet.csv`
- runner 阶段通过 `method_family=longread_gene_counts` 分流到 long-read 命令
- validator 阶段要求 long-read 专属输出契约
- postprocess helper 会发布 long-read 专属 counts 文件

这表示平台已经具备“共享治理框架 + 独立 long-read 通道”的代码骨架。下一步重点不是继续改 short-read MVP，而是实现 `rnaseq-mvp-longread` 背后的真实确定性流程。
