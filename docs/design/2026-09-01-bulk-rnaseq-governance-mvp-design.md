# Bulk RNA-seq治理MVP软件设计说明

## 1. 文档信息

| 项目 | 固定值 |
|---|---|
| 文档版本 | 1.0 |
| 编制日期 | 2026-09-01 |
| 目标软件版本 | `v0.1.0` |
| 仓库名 | `bulk-rnaseq-governance-mvp` |
| 仓库权限 | GitHub私有仓库 |
| MVP类型 | T2A/T2B验证型MVP，架构可扩展 |
| 核心实现 | Python CLI治理层 + Nextflow + nf-core/rnaseq + Docker |
| 当前状态 | 设计已确认，尚未开始代码实现 |

本设计继承以下已冻结材料：

- `docs/人类常规Bulk RNA-seq数据治理MVP设计与测试说明_v0.2.docx`
- `docs/人类Bulk RNA-seq治理MVP_T2真实数据测试冻结表_v0.1.docx`

如本设计与T2冻结表在数据accession、参考版本、pipeline版本、方法路线或验收标准上发生冲突，以T2冻结表为科学验证基线，并通过新版本文档显式修订，不允许静默改变。

## 2. 目标与原则

### 2.1 目标

构建一个可版本化、可下载、可验证、可在合格Linux服务器上运行的人类常规Bulk RNA-seq数据治理工具。该工具将固定范围内的公共原始FASTQ转化为可追溯的基因层面counts数据资产，并同步交付QC、输入血缘、参考血缘、参数快照、软件版本和运行证据。

### 2.2 核心原则

1. 同一输入、参考、方法和软件版本应得到可重复验证的结果。
2. 科学事实、计算配置、运行时状态和最终数据资产分层保存。
3. 任何输入、参考或参数变化都必须被发现并记录。
4. 数据治理硬失败不能被自动降级为警告。
5. 科学QC与数据治理DQ分开判断。
6. 自动化不替代正式科学验证中的人工复核。
7. GitHub只保存代码、配置、定义和测试，不保存大型组学数据或患者数据。
8. v0.1采用确定性CLI，不引入能够自主改变分析参数的智能体。

## 3. v0.1功能边界

### 3.1 正式支持

- 阶段：T2A和T2B。
- 物种：`Homo sapiens`。
- 实验：Illumina、Poly(A)+、paired-end、reverse-stranded Bulk RNA-seq。
- 公共实验：ENCODE `ENCSR000AEM`。
- 参考：GRCh38.p14、GENCODE Release 50 primary assembly FASTA与配套GTF。
- 方法：STAR + Salmon + tximport。
- pipeline：nf-core/rnaseq `3.26.0`。
- Nextflow：`25.10.4`。
- 执行环境：单机Linux Docker模式。
- 输出：未缩放Salmon/tximport gene-level estimated counts、TPM、gene lengths、MultiQC、provenance及校验清单。

### 3.2 暂不支持

- Slurm、PBS或其他集群调度器。
- Apptainer/Singularity执行profile。
- 单端测序、total RNA-seq、单细胞RNA-seq、空间转录组。
- 其他物种、其他参考版本或其他GENCODE release。
- 自动切换aligner、quantifier、strandedness或counts定义。
- 差异表达、批次校正、通路富集和生物标志物发现。
- 将患者数据、临床数据或可识别身份信息上传GitHub。
- 智能体直接调用STAR、修改参数或绕过DQ/QC规则。

“暂不支持”表示v0.1不对这些场景作正确性承诺；后续必须通过新定义、新测试和新版本显式扩展。

## 4. 总体架构

```text
用户
  │
  ▼
Python CLI治理层
  ├── preflight：检查运行环境
  ├── prepare：下载并校验输入与参考
  ├── run：调用固定Nextflow流程
  ├── validate：校验counts、QC和provenance
  ├── review：记录人工复核决定
  ├── package：生成标准发布包
  ├── status：查询状态与下一动作
  ├── execute：自动运行至等待人工复核
  └── smoke-test：运行小数据工具链测试
  │
  ▼
Nextflow执行层
  └── nf-core/rnaseq 3.26.0
          │
          ▼
Docker容器
  └── STAR、Salmon、FastQC、MultiQC及pipeline绑定工具
          │
          ▼
标准counts + QC + provenance + validation + release package
```

Python层负责治理、校验、状态和审计；Nextflow负责流程调度、缓存和失败恢复；nf-core/rnaseq及其容器负责RNA-seq算法执行。v0.1不复制或重写nf-core/rnaseq内部流程。

## 5. 仓库与运行目录

### 5.1 Git仓库结构

```text
bulk-rnaseq-governance-mvp/
├── pyproject.toml
├── README.md
├── VERSION
├── LICENSE
├── .gitignore
├── src/rnaseq_mvp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── preflight.py
│   ├── prepare.py
│   ├── runner.py
│   ├── validator.py
│   ├── reviewer.py
│   ├── packager.py
│   ├── state.py
│   ├── manifests.py
│   ├── checksums.py
│   ├── logging_utils.py
│   └── models.py
├── definitions/
│   ├── stages/T2A.yaml
│   ├── stages/T2B.yaml
│   ├── datasets/ENCSR000AEM.yaml
│   ├── references/human_grch38_gencode_v50_primary.yaml
│   ├── methods/bulk_rnaseq_star_salmon_v1.yaml
│   └── validation/bulk_rnaseq_t2_v1.yaml
├── configs/
│   ├── params/t2a.yaml
│   ├── params/t2b.yaml
│   ├── profiles/local_docker.config
│   └── profiles/server_docker.config
├── samplesheets/
│   ├── t2a.csv
│   └── t2b.csv
├── schemas/
│   ├── stage.schema.json
│   ├── dataset.schema.json
│   ├── reference.schema.json
│   ├── method.schema.json
│   ├── validation_policy.schema.json
│   ├── run_state.schema.json
│   └── data_asset.schema.json
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
└── .github/workflows/ci.yml
```

### 5.2 运行时目录

```text
runtime/
├── raw/
├── reference/
├── work/
├── results/
├── runs/
├── logs/
├── manifests/
├── validation/
├── quarantine/
└── release/
```

运行时目录由`.gitignore`排除。`raw`、`reference`、`work`和`results`不得提交GitHub。

## 6. 命令行接口

### 6.1 `preflight`

```bash
rnaseq-mvp preflight --profile server_docker --workspace runtime
```

检查Linux、CPU架构、CPU数量、内存、磁盘、Java 17、Nextflow 25.10.4、Docker、网络、写权限及work目录位置。输出`preflight_report.json`和人工可读日志。结果为`PASS`、`WARN`或`FAIL`；`FAIL`禁止进入`prepare`。

### 6.2 `prepare`

```bash
rnaseq-mvp prepare --stage T2A --workspace runtime
```

读取stage、dataset和reference定义，下载输入和参考，核对字节数、官方MD5及gzip完整性，计算SHA-256，生成运行时samplesheet、input manifest、reference manifest和本次运行专属的`parameters.yaml`。仓库内`configs/params/t2a.yaml`与`t2b.yaml`只保存可移植的冻结科学参数；`prepare`将其与本次运行的绝对input、outdir、FASTA和GTF路径合并，写入`runtime/runs/<run_id>/parameters.yaml`并计算SHA-256。已存在且校验正确的文件不重复下载；错误文件进入quarantine并阻断流程。

### 6.3 `run`

```bash
rnaseq-mvp run --stage T2A --profile server_docker --workspace runtime --resume
```

运行前重新检查输入、参考、samplesheet、本次运行专属参数快照和代码版本。固定调用中的`RUN_ID`由`prepare`生成：

```bash
NXF_VER=25.10.4 nextflow run nf-core/rnaseq \
  -r 3.26.0 \
  -profile docker \
  -params-file "runtime/runs/${RUN_ID}/parameters.yaml" \
  -c configs/profiles/server_docker.config \
  -work-dir runtime/work \
  -resume
```

每次正式运行生成唯一`run_id`和唯一outdir；不同服务器路径不会写回仓库参数模板。`--resume`只允许在输入、参考、运行参数快照和pipeline版本未改变时复用缓存。

### 6.4 `validate`

```bash
rnaseq-mvp validate --stage T2A --workspace runtime
```

检查pipeline完成状态、主counts、样本列、gene ID、负值、NaN、Infinity、重复键、参考可追溯性、MultiQC及provenance。结果为`PASS`、`PASS_WITH_WARNINGS`或`FAIL`。

### 6.5 `review`

```bash
rnaseq-mvp review \
  --stage T2A \
  --run-id <运行生成的run_id> \
  --reviewer <复核人姓名或受控编号> \
  --decision accept \
  --comment <复核意见>
```

人工复核记录复核人、时间、自动验证结果、异常、决定及是否允许进入下一阶段。`reject`的运行永久保留但不得发布。

### 6.6 `package`

```bash
rnaseq-mvp package --stage T2A --run-id <run_id> --workspace runtime
```

仅允许对人工复核接受的运行生成正式发布包。打包只复制、重命名和生成元数据，不改变counts数值。

### 6.7 `status`

```bash
rnaseq-mvp status --stage T2A --workspace runtime --format text
```

显示当前stage、run ID、状态、最近错误、下一动作和发布许可。`--format json`提供相同字段的结构化输出，供自动脚本在不解析人类文本的情况下取得实际`run_id`。

### 6.8 `execute`

```bash
rnaseq-mvp execute --stage T2A --profile server_docker --workspace runtime
```

自动执行`preflight → prepare → run → validate`，随后停在`AWAITING_REVIEW`。任何步骤失败立即停止。

### 6.9 `smoke-test`

```bash
rnaseq-mvp smoke-test --profile local_docker --workspace runtime-smoke
```

使用nf-core/rnaseq的小型test profile验证Docker、Nextflow、pipeline和结果识别，不使用完整T2 FASTQ，不替代T2科学验证。

## 7. 科学数据定义

### 7.1 T2A与T2B

- T2A：`K562_POLYA_REP1`，完整R1/R2。
- T2B：`K562_POLYA_REP1`与`K562_POLYA_REP2`，四个完整FASTQ。

### 7.2 ENCODE输入

| Sample | Mate | File accession | Expected bytes | Official MD5 |
|---|---|---|---:|---|
| K562_POLYA_REP1 | R1 | ENCFF001RED | 7,668,466,665 | `0e88b38c8d48806ee98929a5bad06fc4` |
| K562_POLYA_REP1 | R2 | ENCFF001RDZ | 7,848,217,965 | `3a25713488522b0ea8a4d9635b5afa41` |
| K562_POLYA_REP2 | R1 | ENCFF001REG | 9,397,127,882 | `4c646fa9b822b7f52f9c2c5a9da0f5e3` |
| K562_POLYA_REP2 | R2 | ENCFF001REF | 9,670,426,425 | `5dd317654eb81f577a0f78745a3c8e66` |

数据定义保存公共源提供的expected值；运行时计算的SHA-256只写入运行manifest，不回写冻结定义。

### 7.3 GENCODE参考

| Role | File | Expected bytes | Official MD5 |
|---|---|---:|---|
| Genome FASTA | `GRCh38.primary_assembly.genome.fa.gz` | 845,635,028 | `da1a11258be075cfa7af718162c894e7` |
| Comprehensive GTF | `gencode.v50.primary_assembly.annotation.gtf.gz` | 124,650,284 | `289b91e5e95e8b0450d223246f10a12e` |

固定`reference_profile_id`为`human_grch38_gencode_v50_primary`。

## 8. 数据模型与文件格式

### 8.1 格式职责

- YAML：人工维护的stage、dataset、reference、method和validation policy定义。
- TSV：输入、参考、QC指标及矩阵型数据清单。
- JSON：运行状态、provenance、验证报告和data asset metadata。
- 所有结构化文件包含`schema_version`。

### 8.2 输入manifest字段

`run_id`、`stage_id`、`sample_id`、`source_database`、`experiment_accession`、`file_accession`、`file_role`、`local_path`、`expected_bytes`、`observed_bytes`、`expected_md5`、`observed_md5`、`observed_sha256`、`gzip_status`、`verification_status`、`verified_at`。

### 8.3 参考manifest字段

除通用文件校验字段外，包含`reference_profile_id`、`organism`、`genome_build`、`assembly_patch`、`annotation_provider`、`annotation_release`、`assembly_scope`和`file_role`。

### 8.4 运行provenance

记录`run_id`、stage、起止时间、MVP version、Git commit、仓库地址、Nextflow版本、pipeline名称与版本、profile、方法、参考profile、输入/参考/参数校验值、完整命令、容器和软件版本及退出码。

### 8.5 counts数据资产元数据

主counts定义：

- `data_asset_type = gene_expression_matrix`
- `measure_type = estimated_counts_unscaled`
- `aggregation_level = gene`
- `value_type = floating_point`
- `normalization = none`
- `gene_identifier.namespace = GENCODE`
- `gene_identifier.annotation_release = 50`
- `gene_identifier.genome_build = GRCh38.p14`
- `gene_identifier.key = gene_id`

estimated counts允许小数，不强制取整。TPM、scaled counts和length-scaled counts不得标记为raw counts。

### 8.6 Hybrid CDM稳定关联键

v0.1保留`sample_id`、`run_id`、`data_asset_id`、`reference_profile_id`和`method_profile_id`。公共测试数据只记录公共来源、experiment accession和sample ID，不伪造患者或就诊信息。

## 9. 状态机与重复运行

```text
NEW
 ↓
PREFLIGHT_PASSED
 ↓
PREPARED
 ↓
RUNNING
 ↓
EXECUTED
 ↓
VALIDATED_PASS / VALIDATED_WITH_WARNINGS / VALIDATION_FAILED
 ↓
AWAITING_REVIEW
 ↓
REVIEW_ACCEPTED / REVIEW_REJECTED
 ↓
PACKAGED
```

状态文件不可静默回退。每次新运行使用独立目录；旧counts、日志和provenance不得覆盖。相同输入和参数可resume，任何校验值变化要求新运行。

## 10. 错误处理与退出码

| 退出码 | 含义 |
|---:|---|
| 0 | 成功 |
| 2 | 命令、schema或配置错误 |
| 3 | preflight失败 |
| 4 | 输入或参考准备失败 |
| 5 | Nextflow运行失败 |
| 6 | counts或QC验证失败 |
| 7 | 人工复核未完成或被拒绝 |
| 8 | 发布包生成失败 |

下载使用`.part`临时文件；只有字节数、gzip和MD5全部通过才原子改名。失败文件及证据进入quarantine。程序不得为了完成运行而自动降低资源、修改参数或切换方法。

## 11. 日志与安全

每次运行保存人工日志`mvp.log`和结构化事件日志`events.jsonl`。结构化事件至少包含timestamp、run ID、component、event、status和相关对象ID。

日志和Git仓库禁止包含Token、密码、SSH私钥、患者标识及未脱敏临床信息。`.gitignore`必须排除FASTQ、BAM、CRAM、参考文件、索引、work、results、release、`.env`、密钥及Nextflow运行目录。

## 12. 验证与发布规则

### 12.1 DQ硬失败

- 输入或参考字节数、MD5、gzip结构不通过。
- paired-end缺少R1/R2或配对关系错误。
- pipeline未成功结束。
- 主counts、MultiQC或provenance缺失。
- counts为空，或存在负数、NaN、Infinity、空/重复gene ID。
- 样本列与stage定义不一致。
- gene ID无法追溯至GENCODE v50 GTF。

DQ硬失败禁止发布。

### 12.2 科学QC

- 总体mapping ≥70%：PASS。
- 总体mapping 50%–70%：WARN。
- 总体mapping <50%：FAIL。
- rRNA比例 ≥10%：WARN。
- 线粒体reads比例 ≥20%：WARN。
- 报告链方向不是reverse：WARN并要求人工复核。
- T2B必须产生PCA与重复相关性结果；v0.1报告相关系数，不用未经验证的固定阈值自动删除样本。

### 12.3 人工复核

自动`PASS`或`PASS_WITH_WARNINGS`均进入`AWAITING_REVIEW`。只有`REVIEW_ACCEPTED`才允许生成正式发布包。警告必须写入复核意见和最终README。

## 13. 标准发布包

```text
runtime/release/<stage>/<run_id>/
├── gene_counts_raw_estimated.tsv
├── gene_counts_raw_estimated.metadata.json
├── gene_tpm.tsv
├── gene_lengths.tsv
├── multiqc_report.html
├── input_manifest.tsv
├── reference_manifest.tsv
├── samplesheet.csv
├── parameters.yaml
├── validation_report.json
├── review_record.json
├── software_versions.yml
├── run_provenance.json
├── README.txt
└── checksums.sha256
```

`PASS`并经接受后标记`READY_FOR_RESEARCH`；`PASS_WITH_WARNINGS`并经接受后标记`READY_WITH_REVIEWED_WARNINGS`；自动或人工拒绝均不得生成科研可用状态。

## 14. 测试体系

### 14.1 单元测试

测试schema、校验和、配对、状态转换、run ID、counts值域、gene ID、样本列、发布清单和退出码，不依赖网络、Docker或大内存。

### 14.2 组件集成测试

使用临时小文件和受控模拟下载，测试续传、`.part`、quarantine、manifest、samplesheet、幂等prepare、参数变化阻断resume及多运行隔离。

### 14.3 本地冒烟测试

包装nf-core/rnaseq `test,docker` profile，验证Docker、Nextflow、pipeline及结果识别。该测试不替代T2科学验证。

### 14.4 服务器冒烟测试

在目标服务器检出候选tag，安装MVP，执行preflight和smoke-test，验证服务器Java、Nextflow、Docker、网络及权限。

### 14.5 T2A/T2B科学验证

T2A通过要求完整Rep 1输入与参考校验、pipeline完成、1列正确样本counts、DQ通过、QC与provenance完整、人工接受和发布包完整。T2B另要求两个样本列、两套QC、PCA与相关性可评估及人工重复一致性复核。

### 14.6 重复性

相同代码、输入、参考和参数重新运行时，gene/sample轴必须一致。数值比较使用绝对容差`1e-6`、相对容差`1e-8`；若正式验证证明该容差不适配，必须通过版本化变更调整。run ID、时间和运行日志允许不同。

## 15. GitHub工作流与版本

仓库采用`main`加短期`feature/*`或`fix/*`分支。Pull Request必须通过Ruff、schema、单元和组件集成测试，并检查误提交的大文件、数据和秘密。GitHub Actions不运行完整T2A/T2B。

版本规则：

- `v0.1.0`：T2A/T2B验证型MVP正式版。
- `v0.1.1`：不改变科研方法的缺陷修复。
- `v0.2.0`：新增向后兼容功能、stage或执行环境。
- `v1.0.0`：接口与科学验证稳定后的正式主版本。
- 破坏CLI/schema或改变核心科学语义：升级主版本。

开发版本依次使用`v0.1.0-alpha.1`、`v0.1.0-beta.1`、`v0.1.0-rc.1`。服务器正式运行只检出固定tag或commit，不直接运行可变`main`。

## 16. 技术栈

- Python 3.10及以上。
- Typer：CLI。
- Pydantic：模型和字段校验。
- PyYAML：YAML定义。
- HTTPX：下载和网络检查。
- pandas：TSV与counts校验。
- pytest：测试。
- Ruff：格式与静态检查。
- Nextflow 25.10.4。
- nf-core/rnaseq 3.26.0。
- Docker：v0.1容器运行时。

Python依赖在`pyproject.toml`和锁定文件中固定。服务器不得在正式运行中自动升级依赖。

## 17. v0.1.0验收标准

发布`v0.1.0`前必须满足：

1. 私有GitHub仓库、README、LICENSE、版本与安装说明完整。
2. `preflight`、`prepare`、`run`、`validate`、`review`、`package`、`status`、`execute`和`smoke-test`可用。
3. 单元测试、组件集成测试和GitHub Actions全部通过。
4. 本地Docker冒烟测试通过。
5. 目标服务器Docker冒烟测试通过。
6. T2A与T2B完整科学验证通过。
7. 标准发布包、provenance和人工复核记录完整。
8. 文档、schema和实际命令一致。
9. 仓库不存在FASTQ、BAM、患者数据、密码、Token或私钥。

最终状态链为：

```text
T2A_PASSED → T2B_PASSED → SERVER_SCIENTIFIC_VALIDATION_PASSED
```

## 18. 实现顺序

1. 创建独立仓库骨架及Python包。
2. 实现schema、数据定义和测试fixtures。
3. 实现状态、日志、校验和与manifest公共组件。
4. 实现`preflight`。
5. 实现`prepare`。
6. 实现`run`与provenance。
7. 实现`validate`。
8. 实现`review`与`package`。
9. 实现`status`、`execute`和`smoke-test`。
10. 配置GitHub Actions并完成本地测试。
11. 创建私有GitHub仓库并发布候选版本。
12. 完成服务器冒烟、T2A、T2B和正式`v0.1.0`发布。

## 19. 后续扩展方向

v0.1通过后，扩展必须以新profile、schema和验证数据集为单位进行。优先方向为Slurm/Apptainer执行profile、通用人类Poly(A)+批次输入、更多公开验证集和Hybrid CDM导入适配器。智能体只能调用已经批准的CLI能力、读取结构化状态并解释结果，不得绕过校验或自主改变科学方法。
