# 服务器 Docker 操作指南

## 选择执行 profile

- x86_64 Linux 服务器使用 `server_docker`；
- aarch64/arm64 Linux 服务器使用 `server_docker_arm64`；
- ARM64 profile 使用 Docker + Wave 原生 ARM64 容器，禁止回退到 QEMU/amd64 模拟。

两种服务器 profile 都要求至少 16 个逻辑 CPU、64 GiB 内存和 500 GiB 可用磁盘。不要在共享 HPC 登录节点运行 STAR 或 Docker 工作负载。若服务器只支持 Apptainer，必须另建并验证独立 profile。

## 基础软件

要求 Java 17、Nextflow 25.10.4、Docker、Git 和 uv。Ubuntu 示例：

```bash
apt-get update
apt-get install -y openjdk-17-jre-headless curl git
java -version

export NXF_VER=25.10.4
curl -s https://get.nextflow.io | bash
install -m 0755 nextflow /usr/local/bin/nextflow
nextflow -version

docker info
uv --version
```

`java -version` 必须显示 17，`nextflow -version` 必须显示 25.10.4。ARM64 服务器还应确认：

```bash
uname -m
docker info --format '{{.Architecture}}'
```

两项均应为 `aarch64` 或 `arm64`。

## 获取私有仓库

使用 GitHub CLI、SSH key 或机构批准的凭据访问私有仓库。不要把 token 写入命令、远程 URL、脚本或日志。

```bash
git clone https://github.com/Picture-one/bulk-rnaseq-governance-mvp.git \
  /opt/bulk-rnaseq-governance-mvp
cd /opt/bulk-rnaseq-governance-mvp
git checkout <release-tag-or-validated-branch>
uv sync --frozen --extra dev
uv run rnaseq-mvp version
```

代码与 runtime 必须分离：代码放在 `/opt/bulk-rnaseq-governance-mvp`，ARM64 运行数据放在 `/data/rnaseq-arm/runtime`。

## ARM64网络要求

除 GitHub、ENCODE、GENCODE 和 Docker registry 外，`server_docker_arm64` 还必须访问：

- `https://wave.seqera.io`；
- `https://community.wave.seqera.io/v2/`；
- `https://registry.nextflow.io`。

registry 返回 HTTP 401 表示服务可达并要求认证，不等于网络失败。Wave只根据流程的软件依赖构建或提供ARM64容器；本MVP不启用远程任务执行或Fusion。FASTQ、参考、work、counts和QC结果仍位于服务器本地。

## 首次ARM64验证

```bash
mkdir -p /data/rnaseq-arm/runtime

uv run rnaseq-mvp preflight \
  --profile server_docker_arm64 \
  --workspace /data/rnaseq-arm/runtime

uv run rnaseq-mvp smoke-test \
  --profile server_docker_arm64 \
  --workspace /data/rnaseq-arm/runtime \
  --fresh
```

必须同时满足：预检为 `PASS`；smoke报告为 `PASS`；生成 gene counts 和 MultiQC；日志中没有 `exec format error`；实际容器架构为 ARM64。若Wave构建失败，应记录失败process、Conda定义和Wave响应，不得自动改用amd64模拟。

## 真实数据执行

ARM64 smoke-test 通过后，才运行冻结的 T2A/T2B：

```bash
uv run rnaseq-mvp execute \
  --stage T2A \
  --profile server_docker_arm64 \
  --workspace /data/rnaseq-arm/runtime
```

x86_64服务器将 profile 和 workspace 分别替换为 `server_docker` 与 `/data/rnaseq/runtime`。

预检报告必须属于同一workspace、同一profile，且生成时间不超过24小时。运行前系统会复核prepare阶段保存的manifest、samplesheet和参数哈希；不要手工编辑run目录内的冻结文件。

## 恢复、检查与备份

```bash
uv run rnaseq-mvp status \
  --stage T2A \
  --workspace /data/rnaseq-arm/runtime

uv run rnaseq-mvp run \
  --stage T2A \
  --run-id <RUN_ID> \
  --profile server_docker_arm64 \
  --workspace /data/rnaseq-arm/runtime \
  --resume
```

完成后按机构数据管理政策备份 `runs/<run_id>`、发布包和必要日志。FASTQ、参考、结果、work、凭据和患者标识不得推送到GitHub。
