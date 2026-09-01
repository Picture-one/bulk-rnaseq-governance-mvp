# 本地 WSL2 + Docker 操作指南

## 用途

本地环境用于代码测试、环境预检和 nf-core 小型冒烟测试。内存低于 40 GiB 时，不建议运行完整人类 STAR 比对；完整 T2A/T2B 应转移到至少 64 GiB 内存的服务器。

## 前置检查

在 Windows 打开 Docker Desktop，启用 WSL integration 和 Ubuntu-22.04。随后在 WSL 中执行：

```bash
docker --version
docker info
docker run --rm hello-world
java -version
nextflow -version
uv --version
```

## 安装与自动测试

```bash
cd /path/to/bulk-rnaseq-governance-mvp
uv sync --frozen --extra dev
uv run ruff check .
uv run pytest -v
```

## 本地预检与冒烟

```bash
uv run rnaseq-mvp preflight \
  --profile local_docker \
  --workspace "$PWD/runtime-local"

uv run rnaseq-mvp smoke-test \
  --profile local_docker \
  --workspace "$PWD/runtime-smoke"
```

`local_docker` 的资源不足可标记为 WARN；Docker、Java、Nextflow、操作系统或必要网络不可用仍为 FAIL。冒烟测试使用 nf-core 内置小数据，只证明工具链可执行，不证明完整人类数据能够在本机内存中完成。

本地 smoke-test 通过独立的 `smoke_local.config` 把 nf-core 小数据测试中标记为 `process_high` 的任务，以及被流程单独提高内存的 `SALMON_QUANT`，限制为 14 GB，使它们低于约 15 GiB 的 WSL 上限。该配置只属于独立冒烟命令，不会降低 T2A/T2B 服务器流程的资源要求，也不改变科学算法。

冒烟命令同时显式设置 `skip_bbsplit=true`。BBSplit 是 nf-core 测试 profile 默认启用的附加污染筛查，但冻结的 T2A/T2B 方法本身已跳过该步骤；它不属于 FASTQ→STAR/Salmon→counts/MultiQC 主链。

首次运行需要在线取得固定版本的 nf-core/rnaseq。若本地 Nextflow 缓存中的流程代码与固定版本 `3.26.0` 完全一致，后续运行会直接使用该本地流程代码；否则仍从 `nf-core/rnaseq` 获取指定 revision。流程代码缓存并不代表测试数据也已缓存，因此网络不稳定时建议使用本地资产清单。

## 使用本地测试资产

当 WSL 访问 GitHub 较慢或远程文件暂存不稳定时，可通过 YAML 清单显式指定本地测试资产。清单允许使用绝对路径，也允许使用相对于清单文件所在目录的相对路径。

示例 `smoke-assets.yaml`：

```yaml
input: samplesheet.csv
fasta: genome.fasta
gtf: genes.gtf.gz
transcript_fasta: transcriptome.fasta
additional_fasta: additional.fa.gz


salmon_index: salmon.tar.gz

```

所有字段均为必填：

- `input`：nf-core samplesheet；
- `fasta`：参考基因组 FASTA；
- `gtf`：基因注释 GTF；
- `transcript_fasta`：转录本 FASTA；
- `additional_fasta`：附加序列 FASTA；
- `salmon_index`：预构建 Salmon 索引压缩包。

运行命令：

```bash
uv run rnaseq-mvp smoke-test \
  --profile local_docker \
  --workspace "$PWD/runtime-smoke" \
  --assets-manifest /path/to/smoke-assets.yaml
```

其中 `/path/to/smoke-assets.yaml` 是占位路径，实际运行时必须替换为本机真实清单路径。例如当前本机使用：

```bash
uv run rnaseq-mvp smoke-test \
  --profile local_docker \
  --workspace "$PWD/runtime-smoke" \
  --assets-manifest /home/heng/.cache/rnaseq-mvp/smoke-assets/v3.26.0/smoke-assets.yaml
```

MVP 会在启动 Nextflow 前检查清单字段及所有文件。任一文件不存在时立即停止，不会提交部分分析任务。

WSL 中如果仓库位于 `/mnt/c`、`/mnt/d` 或 `/mnt/e` 等 Windows 挂载盘，MVP 会自动把 Nextflow 工作目录放在 Linux 文件系统的 `~/.cache/rnaseq-mvp/smoke_work/` 下，以支持 STAR 所需的命名管道；最终结果和运行报告仍保存在指定 workspace 中。

默认启用 Nextflow `-resume`。需要完全开启新会话时可增加 `--fresh`。

## 常见问题

- `docker API ... daemon is running`：打开 Docker Desktop，等待 Engine 状态正常。
- WSL 中找不到 `docker`：Docker Desktop → Settings → Resources → WSL Integration，启用 Ubuntu-22.04。
- `localhost proxy` 警告：这是 WSL NAT 与 Windows localhost 代理的提示；若下载失败，应为 WSL 配置可访问的代理地址或关闭无效代理。
- 重新执行 smoke-test 会使用 Nextflow `-resume`，但每次生成独立报告和结果目录。
