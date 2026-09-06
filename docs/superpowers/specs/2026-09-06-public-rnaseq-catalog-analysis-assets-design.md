# 公共 Bulk RNA-seq 数据目录与标准分析资产库 v0.1 设计规范

## 1. 文档信息

| 项目 | 固定值 |
|---|---|
| 文档版本 | `v0.1` |
| 编制日期 | 2026-09-06 |
| 子项目 | 公共组学数据目录与标准分析资产库 |
| 上游分析引擎 | `bulk-rnaseq-governance-mvp` |
| 数据范围 | 人类、Illumina 短读长、常规 Bulk RNA-seq、Poly(A)+、单端或双端 |
| 标准分析路线 | STAR + Salmon + tximport |
| 正式参考 | GRCh38.p14 + GENCODE Release 50 |
| 目录维护方式 | 标准 Excel/CSV 人工整理、机器校验、一名管理员确认发布 |
| 当前状态 | 设计已确认，尚未开始实现 |

本设计扩展现有 Bulk RNA-seq 治理 MVP，但不改变已经冻结的 counts 定义、参考、流程和 QC/DQ 规则。若上游分析引擎尚未完成某类输入的科学验证，该类数据可以进入目录，但不得生成 `PUBLISHED` 标准分析资产。

## 2. 建设目标

建设一个经过人工审核、可由智能体检索的公共 Bulk RNA-seq 数据目录，并把平台按照同一冻结方法生成的分析结果保存为不可变、可复用的公共分析资产。

系统应满足：

1. 管理员可以用标准 Excel/CSV 登记人工筛选的公共研究、样本、Run、FASTQ 和适用性证据。
2. 正式目录中的每个 FASTQ 都能追溯到公共数据库编号、来源地址、官方校验值和平台 SHA-256。
3. 首次需要某批公共数据时，平台下载、校验并调用冻结分析流程。
4. 相同数据和相同标准方法已有合格结果时，不再重复计算。
5. 所有已发布标准结果和已成功分析的 FASTQ 长期保存。
6. 多个用户在各自项目中引用同一底层公共资产，互相不可见且不复制底层文件。
7. 为后续微信智能体提供结构化检索、资产状态和项目引用接口。

## 3. v0.1 范围

### 3.1 包含

- 人工筛选后通过 Excel/CSV 导入公共数据。
- 四类目录实体：研究、样本、测序文件、适用性审核。
- Excel 暂存、自动校验、差异预览和单管理员发布。
- 公共目录版本及完整变更审计。
- FASTQ 服务器端下载、断点续传、校验、隔离和归档。
- 平台冻结标准分析的唯一任务调度与结果复用。
- 数据指纹、方法指纹和分析指纹。
- 标准发布包的不可变存储、完整性验证和多用户只读引用。
- 面向未来微信智能体的只读检索和受控项目引用接口。

### 3.2 不包含

- 实时自动爬取 GEO、SRA、ENA 后直接发布。
- 智能体自主判断并发布公共数据。
- 用户自定义参考、流程、参数或 counts 定义。
- 将公共数据库提供的异质 counts 自动合并到标准资产。
- 差异表达、批次校正、Meta 分析、通路富集或机器学习。
- 微信登录、消息推送和微信端界面实现。
- dbGaP 等受控访问数据导入。
- 公共样本与本地患者身份匹配。
- 平台内保存本地患者姓名、身份证号、住院号等直接标识符。

## 4. 核心设计决策

### 4.1 目录与资产分离

公共目录回答“有哪些数据、是否适用”；原始数据登记库回答“FASTQ 在哪里、是否完整”；分析资产库回答“是否已有可交付的标准结果”。三者使用稳定 ID 连接，但生命周期和权限分开管理。

### 4.2 Excel 仅作为受控录入入口

Excel/CSV 不作为在线查询数据库。文件导入暂存区，通过校验并经管理员确认后，写入正式关系数据库。原始导入文件及 SHA-256 永久保留，以支持审计和重放。

### 4.3 只复用完全一致的标准分析

v0.1 只有一个经批准的标准方法族。用户不选择生物信息学参数。数据指纹和方法指纹均一致时才能复用；任何输入、参考、方法或参数变化都创建新资产版本，不覆盖旧资产。

### 4.4 公共资产全局唯一、项目引用租户隔离

FASTQ 和标准分析资产属于平台全局公共资源。用户项目只保存只读引用、访问授权和使用记录，不复制底层对象，也不能修改或删除全局资产。

### 4.5 永久内容与临时内容分层

已成功分析的 FASTQ 和标准发布包长期保存。Nextflow 工作目录、容器缓存、可重建中间文件和默认 BAM 不属于永久资产，可依据运行保留策略清理。

## 5. 总体架构

```text
管理员整理四表 Excel/CSV
          │
          ▼
导入校验器 ──失败──> 暂存错误报告
          │通过
          ▼
目录暂存区 ──管理员确认──> 版本化正式公共目录
                                  │
                     ┌────────────┴────────────┐
                     ▼                         ▼
                结构化检索                 FASTQ 获取器
                     │                         │
              未来微信智能体             校验与归档存储
                                               │
                                               ▼
                                      分析资产匹配器
                                      │            │
                                   命中           未命中
                                      │            ▼
                                      │      RNA-seq 治理 MVP
                                      │            │
                                      │      验证与人工复核
                                      │            │
                                      └──────> 不可变资产库
                                                    │
                                                    ▼
                                             用户项目只读引用
```

## 6. 标识符与实体关系

### 6.1 平台标识符

| 标识符 | 含义 | 规则 |
|---|---|---|
| `catalog_release_id` | 一次正式目录发布 | 发布后不可变 |
| `public_study_id` | 平台内公共研究 | 与来源数据库及 study accession 唯一映射 |
| `public_sample_id` | 平台内公共样本 | 保留来源命名空间 |
| `public_subject_id` | 公共研究内受试者 | 只用于该公共研究内部关联 |
| `assay_id` | 一次测序实验 | 连接样本、文库和 Run |
| `raw_asset_id` | 一个经过校验的原始文件 | 由来源记录和内容校验值约束 |
| `analysis_asset_id` | 一版不可变标准分析资产 | 对应唯一分析指纹 |
| `project_asset_ref_id` | 用户项目对公共资产的引用 | 受租户和项目权限控制 |

公共 `public_subject_id` 不得用于推断或匹配平台中的本地患者 `person_link_id`。未来如需跨来源身份连接，必须由独立的合法授权和隐私保护设计处理。

### 6.2 关系

```text
public_study 1 ── n public_sample
public_sample 1 ── n assay
assay 1 ── n sequencing_run
sequencing_run 1 ── 1..2 raw_asset(FASTQ)
raw_asset n ── n analysis_asset（经输入集合关联表）
analysis_asset 1 ── n project_asset_ref
```

同一样本的多个 lane 或 Run 必须逐项保留来源关系；是否合并由冻结分析方法决定，不能在目录中静默拼接。

## 7. 标准 Excel 工作簿

工作簿包含四张必需工作表。CSV 录入时使用四个同名文件组成一个导入包。

### 7.1 `studies`

必需字段：

- `source_database`
- `study_accession`
- `study_title`
- `study_summary_raw`
- `organism_raw`
- `organism_normalized`
- `disease_raw`
- `disease_normalized`
- `tissue_raw`
- `tissue_normalized`
- `study_design_raw`
- `case_control_status`
- `reported_sample_count`
- `publication_doi`
- `source_record_url`
- `access_status`
- `curated_by`
- `curated_at`

### 7.2 `samples`

必需字段：

- `source_database`
- `study_accession`
- `sample_accession`
- `biosample_accession`
- `public_subject_id`
- `group_raw`
- `group_normalized`
- `disease_raw`
- `disease_normalized`
- `tissue_raw`
- `tissue_normalized`
- `sex_raw`
- `sex_normalized`
- `age_raw`
- `age_value`
- `age_unit`
- `intervention_raw`
- `timepoint_raw`
- `sample_source_url`

未报告的信息使用字面值 `NOT_REPORTED`；不适用使用 `NOT_APPLICABLE`。二者不得与空值混用。

### 7.3 `runs_files`

必需字段：

- `source_database`
- `study_accession`
- `sample_accession`
- `experiment_accession`
- `run_accession`
- `file_accession`
- `file_role`
- `file_name`
- `download_url`
- `expected_bytes`
- `expected_md5`
- `library_strategy`
- `library_selection`
- `library_layout`
- `strandedness`
- `instrument_platform`
- `instrument_model`
- `read_length`
- `run_source_url`

`file_role` 只能为 `R1` 或 `R2`。单端记录只有 `R1`；双端记录必须同时存在唯一的 `R1` 和 `R2`。

### 7.4 `eligibility_review`

每个判断字段保存结果、证据和确认状态：

- `study_accession`
- `eligibility_status`
- `human_status`
- `illumina_short_read_status`
- `bulk_rnaseq_status`
- `polya_status`
- `layout_status`
- `fastq_available_status`
- `evidence_source_url`
- `evidence_location`
- `evidence_text`
- `confidence`
- `human_confirmed`
- `reviewed_by`
- `reviewed_at`
- `ineligibility_reason`

状态值限定为 `PASS`、`FAIL`、`NOT_REPORTED`、`NOT_APPLICABLE`。`eligibility_status=PASS` 要求所有当前 MVP 硬条件均为 `PASS` 且 `human_confirmed=true`。

## 8. 导入、审核和目录发布

### 8.1 导入状态

```text
UPLOADED → VALIDATING → VALIDATION_FAILED
                      └→ READY_FOR_REVIEW → PUBLISHED
                                            └→ REJECTED
```

校验失败不能产生部分正式记录。修正后的文件作为新的导入尝试保存，旧错误报告不覆盖。

### 8.2 自动校验

校验器至少检查：

1. 工作表、表头、字段类型和受控值。
2. study、sample、experiment、run、file 外键完整性。
3. accession 格式和来源命名空间。
4. 同一来源 accession 的唯一性。
5. 单端/双端与 R1/R2 数量一致性。
6. URL 格式、可访问性和重定向结果。
7. 文件大小、MD5 格式及必要字段。
8. 物种、平台、实验类型和 Poly(A)+ 适用性。
9. `NOT_REPORTED`、空值和不适用值的合法使用。
10. 本次导入相对当前正式目录的新增、修改和移除差异。

### 8.3 发布

v0.1 由一名具有目录管理员角色的用户确认发布。发布操作保存操作者、时间、输入文件 SHA-256、校验报告、差异摘要和发布理由。已发布目录版本只读；修订必须创建新的 `catalog_release_id`。

## 9. FASTQ 获取、校验和归档

### 9.1 获取流程

```text
REGISTERED → DOWNLOADING → DOWNLOADED → VERIFIED → ARCHIVED
                        └→ DOWNLOAD_FAILED
                                     └→ QUARANTINED（校验失败）
```

下载使用临时 `.part` 对象和断点续传。只有字节数、官方 MD5（来源提供时）、gzip 完整性和平台 SHA-256 均满足策略后，文件才能从暂存区移动到长期归档区。

### 9.2 内容寻址与去重

归档对象以 SHA-256 为内容身份。不同 URL 或 accession 若得到完全相同内容，可以共享一个物理对象，但必须保留各自来源记录。内容不同的文件不得因文件名相同而覆盖。

### 9.3 来源变化

来源链接失效不删除已归档文件。公共源的文件大小、MD5 或内容发生变化时，创建新 `raw_asset_id`，旧原始资产和既有分析资产保留，并标记来源变化事件供管理员审核。

## 10. 标准分析、指纹和复用

### 10.1 指纹

`data_fingerprint` 是规范化输入清单的 SHA-256，输入包括按稳定顺序排列的 sample、assay、run、file role、raw asset SHA-256 及合并关系。

`method_fingerprint` 是规范化方法清单的 SHA-256，输入包括：

- 治理工具版本和 Git commit；
- nf-core/rnaseq 版本；
- Nextflow 版本；
- 容器及软件版本；
- 完整参数快照；
- FASTA、GTF 及索引校验值；
- GRCh38.p14 和 GENCODE Release 50 标识；
- STAR + Salmon + tximport 方法定义；
- counts measure type；
- QC/DQ 策略版本。

`analysis_fingerprint = SHA256(data_fingerprint + method_fingerprint)`。

### 10.2 复用判断

只有同时满足以下条件才能直接复用：

1. `analysis_fingerprint` 完全一致。
2. 资产状态为 `PUBLISHED`。
3. 发布包完整性复检通过。
4. 资产未被撤销、隔离或标记为损坏。
5. 当前用户对所属项目具有引用权限。

同一指纹在任一时刻最多有一个活动计算任务。并发请求加入同一任务的订阅列表，不创建重复计算。

### 10.3 资产状态

```text
DISCOVERED
→ CURATED
→ ELIGIBLE
→ FASTQ_VERIFIED
→ PROCESSING
→ AWAITING_REVIEW
→ PUBLISHED
```

任一计算错误进入 `FAILED`；被更高版本替代但仍可追溯的资产进入 `SUPERSEDED`；完整性或科学问题导致禁止交付的资产进入 `WITHDRAWN`。只有 `PUBLISHED` 可以创建新的用户项目引用。

## 11. 永久分析资产

### 11.1 永久保存

- 归档 FASTQ。
- 未缩放 Salmon/tximport gene estimated counts。
- scaled counts、length-scaled counts、TPM 和 gene length。
- SummarizedExperiment RDS。
- 样本级 QC、MultiQC 报告和关键指标表。
- input、reference、parameters、output manifests。
- 输入、参考、结果文件校验值。
- pipeline provenance、软件和容器版本。
- 验证报告、人工审核记录和目录元数据快照。
- 资产清单和分析指纹。

### 11.2 默认不永久保存

- Nextflow `work` 目录。
- 容器缓存。
- 解压、排序和格式转换临时文件。
- 可由 FASTQ 和冻结方法重建的中间文件。
- BAM 文件，除非未来方法配置将其显式列为发布资产。

“永久”表示平台不按普通生命周期策略自动删除；管理员仍可在法律、来源撤回、安全事件或科学错误要求下执行受控撤回。受控撤回保留元数据、审计记录和撤回原因，不再向用户分发相关内容。

## 12. 用户项目引用与权限

### 12.1 角色

- `catalog_curator`：上传和修订暂存目录。
- `catalog_admin`：查看差异、确认或拒绝发布。
- `asset_reviewer`：复核分析结果并决定是否发布。
- `registered_user`：检索正式目录并把已发布资产引用到有权访问的项目。
- `platform_operator`：处理下载、计算、存储和完整性事件，不获得无关用户项目内容权限。

### 12.2 引用语义

用户确认使用某公共资产后，平台创建 `project_asset_ref`。该记录保存 tenant、project、analysis asset、创建人、创建时间和授权状态。删除引用只影响该项目，不删除全局目录、FASTQ 或分析资产。

不同租户不能看到对方的项目、查询历史、资产引用和研究问题。公共目录元数据及已发布资产身份可以全局共享。

## 13. 检索与未来智能体接口

### 13.1 可信检索边界

v0.1 检索范围仅包括正式发布的目录版本。未审核的实时网络搜索结果、暂存记录和失败导入不能作为“平台已收录数据”返回。

### 13.2 结构化检索条件

接口支持疾病、组织、样本类型、年龄、性别、病例对照设计、干预、时间点、样本数量、测序布局、数据源、适用性和分析资产状态等组合条件，并同时返回标准化值和来源原文。

### 13.3 返回数据卡片

每个候选研究至少返回：

- 研究名称和公共 accession；
- 研究人群、病例/对照和样本数量；
- 组织、实验和测序概要；
- 适用性结论及证据；
- FASTQ 获取状态；
- 标准分析资产是否可直接复用；
- 已知缺失、限制和 `NOT_REPORTED` 字段；
- 数据来源页面。

未来微信智能体把自然语言需求转换为结构化查询。智能体可以解释结果、提出缺失条件和请求项目引用，但不能编造 accession、直接修改目录、改变标准分析参数或绕过权限与审核。

当正式目录无匹配项时，回答必须表述为“当前平台已审核目录中未发现”，不能表述为“公共数据库中不存在”。系统可以登记一条数据挖掘需求供管理员后续处理。

## 14. 异常处理

1. Excel 校验失败：保留在暂存区，输出工作表、行号、字段和原因。
2. 发布事务失败：正式目录保持原版本，不允许部分发布。
3. 下载中断：保留可验证的分片状态并支持续传。
4. 校验失败：对象进入隔离区并阻止分析。
5. 分析失败：保留状态、日志和 provenance，不生成可复用资产。
6. QC/DQ 未通过：进入失败或等待人工判断状态，不自动发布。
7. 并发相同请求：订阅唯一活动任务，不重复提交。
8. 公共来源变化：创建新来源版本并通知管理员，不覆盖旧资产。
9. 已发布资产完整性失败：立即停止新分发并进入 `WITHDRAWN` 审核流程。
10. 用户项目引用删除：只撤销引用，不删除全局资产。

## 15. 审计与可追溯性

下列操作必须形成不可静默修改的审计事件：

- 目录导入、校验、拒绝和发布；
- 记录新增、修改、移除和证据变更；
- FASTQ 下载、续传、校验、隔离和归档；
- 分析任务创建、复用命中、失败和恢复；
- 人工复核、资产发布、替代和撤回；
- 用户项目引用创建、访问和撤销；
- 权限、角色和存储策略变更。

审计事件至少保存事件 ID、对象类型、对象 ID、操作者或系统主体、UTC 时间、动作、前后版本、理由和关联证据。

## 16. 验收标准

v0.1 必须通过以下端到端验收：

1. 完整四表 Excel 能进入暂存区并通过结构校验。
2. 缺少 R2 的双端样本被拒绝且错误定位到具体行。
3. 研究、样本、实验、Run 和文件关系冲突被拒绝。
4. 重复 accession 不产生重复正式实体。
5. 正确生成导入相对上一目录版本的差异预览。
6. 一名管理员确认后形成只读目录版本和完整审计记录。
7. 下载中断后可以续传，错误内容不能进入归档区。
8. FASTQ 字节数、MD5、gzip 和 SHA-256 校验均有记录。
9. 首次请求符合范围的数据时创建唯一标准分析任务。
10. 同一分析指纹的并发请求只触发一次计算。
11. 输入、参数或参考变化时不能错误命中既有资产。
12. 未经验证和人工复核的结果不能进入 `PUBLISHED`。
13. 发布包包含规定的 counts、TPM、QC、provenance、验证和审核材料。
14. 已发布资产完整性复检通过后才能创建项目引用。
15. 两个租户可引用同一底层资产，但不能看到对方项目和引用记录。
16. 删除项目引用不会删除全局 FASTQ 和分析资产。
17. 来源链接失效后，已归档内容仍可验证，目录显示来源异常。
18. 公共源内容变化产生新原始资产版本且旧结果不被覆盖。
19. 结构化检索只返回正式目录，并明确展示缺失和限制。
20. 任一正式结果可以追溯到公共 accession、FASTQ 校验值、方法、参考、验证和审核决定。

## 17. 子项目边界与后续顺序

本规范只定义子项目 A。推荐实施顺序：

1. 标准 Excel/CSV schema、暂存导入和校验。
2. 正式目录实体、版本和审计。
3. FASTQ 获取、内容寻址归档和来源变化管理。
4. 指纹、唯一任务和现有 RNA-seq MVP 适配。
5. 不可变分析资产发布和项目只读引用。
6. 结构化检索接口和端到端验收。

子项目 A 验收后，再分别设计：

- 子项目 B：微信智能体、注册登录、自然语言查询、通知和结果交付。
- 子项目 C：GEO/SRA/ENA 自动发现、元数据同步、机器初筛和人工发布。

后续版本可以登记公共数据库提供的 counts，但不得在没有明确 measure type、参考、注释、方法和兼容性验证时与平台标准 counts 自动合并。
