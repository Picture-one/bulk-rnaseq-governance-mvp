# Bulk RNA-seq Governance MVP

这是一个面向真实世界研究数据治理的 Bulk RNA-seq MVP。它把冻结范围内的人类 Illumina、poly(A)+、双端、reverse-stranded FASTQ，经固定版本的 nf-core/rnaseq 转换为可追溯的基因级 estimated counts，并保留输入、参考、参数、QC、人工复核和发布记录。

## v0.1 范围

支持：

- 人类常规 Bulk RNA-seq；
- Illumina paired-end；
- poly(A)+ 建库；
- reverse stranded；
- GRCh38.p14 primary assembly；
- GENCODE Release 50；
- STAR + Salmon + tximport；
- nf-core/rnaseq 3.26.0、Nextflow 25.10.4、Docker。

暂不支持：single-end、非链特异或 forward stranded、rRNA-depletion total RNA、单细胞/单核 RNA-seq、长读长、其他物种或参考版本，以及临床样本身份映射。超出范围的数据必须新增并验证独立科学定义，不能直接套用 T2A/T2B。

## 安装

建议在 WSL2 Ubuntu 或 Linux 服务器运行，不在 Windows PowerShell 中直接执行流程。

```bash
git clone <private-repository-url>
cd bulk-rnaseq-governance-mvp
uv sync --frozen --extra dev
uv run rnaseq-mvp version
uv run rnaseq-mvp --help
```

运行依赖：Python 3.10–3.12、Java 17、Nextflow 25.10.4、Docker Engine/Docker Desktop。服务器推荐至少 64 GiB 内存；本地小型 nf-core 测试不代表能够运行完整人类 STAR 比对。

## 执行 profile

| Profile | 平台 | 用途 |
|---|---|---|
| `local_docker` | 本地 x86_64 Linux/WSL2 | 小型工具链测试；资源不足只报告 WARN |
| `server_docker` | x86_64 Linux 服务器 | 常规服务器运行 |
| `server_docker_arm64` | aarch64/arm64 Linux 服务器 | Docker + Wave 原生 ARM64 运行 |

`server_docker_arm64` 使用 Wave 根据流程中的 Conda 依赖提供 ARM64 容器，禁止自动回退到 QEMU/amd64 模拟。本 profile 不启用远程任务执行或远程文件系统；FASTQ、参考文件、Nextflow work、counts 和 QC 结果仍位于并处理于本地服务器。

## 使用顺序

```text
preflight → prepare → run → validate → review → package
```

一条命令自动执行到等待人工复核：

```bash
uv run rnaseq-mvp execute \
  --stage T2A \
  --profile server_docker \
  --workspace /data/rnaseq/runtime
```

分步命令：

```bash
uv run rnaseq-mvp preflight --profile local_docker --workspace runtime
uv run rnaseq-mvp prepare --stage T2A --workspace runtime
uv run rnaseq-mvp run --stage T2A --run-id <RUN_ID> --profile server_docker --workspace runtime
uv run rnaseq-mvp validate --stage T2A --run-id <RUN_ID> --workspace runtime
uv run rnaseq-mvp review --stage T2A --run-id <RUN_ID> --reviewer <ID> --decision accept --comment "已核查counts、QC、参考和provenance" --workspace runtime
uv run rnaseq-mvp package --stage T2A --run-id <RUN_ID> --workspace runtime
uv run rnaseq-mvp status --stage T2A --workspace runtime --format json
uv run rnaseq-mvp smoke-test --profile local_docker --workspace runtime-smoke
```

ARM64 服务器首次部署时，先完成预检和小型 smoke-test：

```bash
uv run rnaseq-mvp preflight \
  --profile server_docker_arm64 \
  --workspace /data/rnaseq-arm/runtime

uv run rnaseq-mvp smoke-test \
  --profile server_docker_arm64 \
  --workspace /data/rnaseq-arm/runtime
```

只有两项均为 `PASS` 后，才运行 T2A/T2B 或其他真实人类数据。

人工复核是强制门。`execute` 不会自动接受或打包结果。

## 运行状态

```text
NEW → PREFLIGHT_PASSED → PREPARED → RUNNING → EXECUTED
    → VALIDATED_PASS / VALIDATED_WITH_WARNINGS → AWAITING_REVIEW
    → REVIEW_ACCEPTED → PACKAGED
```

运行失败进入 `RUN_FAILED`；数据质量硬失败进入 `VALIDATION_FAILED`；人工拒绝进入 `REVIEW_REJECTED`。

## 数据位置

- `runtime/raw/`：校验后的 FASTQ；
- `runtime/reference/`：冻结参考文件；
- `runtime/runs/<run_id>/`：状态、manifest、参数、日志、provenance、验证和复核；
- `runtime/results/<stage>/<run_id>/`：nf-core 结果；
- `runtime/release/<stage>/<run_id>/`：人工接受后的标准科研包；
- `runtime/quarantine/`：校验失败的隔离文件；
- `runtime/work/`：Nextflow 工作目录。

这些目录不得提交到 Git。

## Counts 的含义

发布文件 `gene_counts_raw_estimated.tsv` 是 Salmon 定量后经 tximport 聚合到基因层级的未缩放 estimated counts，允许小数。它不是 TPM、CPM、标准化 counts 或差异表达结果。差异表达分析必须在下游使用完整 count 矩阵并按研究设计进行过滤、标准化和批次处理。

## 退出码

| 代码 | 含义 |
|---:|---|
| 0 | 成功 |
| 2 | 配置或定义错误 |
| 3 | 环境预检失败 |
| 4 | 下载或输入准备失败 |
| 5 | Nextflow 或冒烟测试失败 |
| 6 | 科研数据质量验证失败 |
| 7 | 人工复核记录失败 |
| 8 | 发布包生成失败 |

## 隐私与安全

仓库不得包含 FASTQ、BAM/CRAM、FASTA/GTF、Nextflow work/results、密钥、`.env`、患者姓名、证件号、住院号或其他可识别临床信息。提交前运行：

```bash
uv run python scripts/check_repository_safety.py .
```

公共测试数据仍应记录数据库、experiment/accession 和样本 ID；公共来源不等于可以省略数据来源追溯。

## 验证与来源

```bash
uv run ruff check .
uv run python scripts/export_schemas.py --output-dir schemas
git diff --exit-code -- schemas
uv run pytest -v
uv run python scripts/check_repository_safety.py .
```

流程与工具来源：[nf-core/rnaseq](https://nf-co.re/rnaseq/3.26.0/)、[Nextflow](https://www.nextflow.io/)、[GENCODE human release 50](https://www.gencodegenes.org/human/release_50.html)、[ENCODE](https://www.encodeproject.org/)。使用结果时还应按照 nf-core/rnaseq 和具体工具的建议进行引用。

详细操作见 [本地 Docker](docs/operations/local-docker.md)、[服务器 Docker](docs/operations/server-docker.md) 和 [T2 人工复核](docs/operations/t2-review.md)。
