# 服务器 Docker 操作指南

## 推荐资源

- Linux x86_64；
- 16 CPU 或以上；
- 64 GiB RAM 或以上；
- 500 GiB 可用磁盘或以上；
- Java 17、Nextflow 25.10.4、Docker；
- 能访问 GitHub、ENCODE、GENCODE 和容器镜像仓库。

不要在共享 HPC 登录节点运行 STAR 或 Docker 工作负载。应申请计算节点，或使用机构批准的作业调度/容器方案；v0.1 仅冻结了 Docker profile，若服务器只支持 Apptainer，需要新增、测试并冻结单独 profile。

## 部署

```bash
git clone <private-repository-url>
cd bulk-rnaseq-governance-mvp
git checkout <release-tag>
uv sync --frozen --extra dev
uv run rnaseq-mvp version
```

代码仓库与 runtime 应分离。示例：代码在 `/opt/bulk-rnaseq-governance-mvp`，运行数据在 `/data/rnaseq/runtime`。

## 执行

```bash
uv run rnaseq-mvp preflight \
  --profile server_docker \
  --workspace /data/rnaseq/runtime

uv run rnaseq-mvp execute \
  --stage T2A \
  --profile server_docker \
  --workspace /data/rnaseq/runtime
```

`server_docker` 的 CPU、内存或磁盘未达阈值时预检为 FAIL。预检报告必须属于同一 workspace、同一 profile，且生成时间不超过 24 小时。

## 恢复与检查

```bash
uv run rnaseq-mvp status --stage T2A --workspace /data/rnaseq/runtime
uv run rnaseq-mvp run --stage T2A --run-id <RUN_ID> --profile server_docker --workspace /data/rnaseq/runtime --resume
```

运行前系统会复核 prepare 阶段保存的 manifest、samplesheet 和参数哈希。任何变更都会阻断运行；不要手工编辑 run 目录内的冻结文件。

完成后将整个 `runs/<run_id>`、发布包和必要日志按机构数据管理政策备份。FASTQ、参考、结果及 work 目录不得推送到 GitHub。
