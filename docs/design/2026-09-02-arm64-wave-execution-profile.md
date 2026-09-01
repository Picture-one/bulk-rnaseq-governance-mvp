# ARM64 Wave 执行 Profile 设计

## 目标

让 Bulk RNA-seq 治理 MVP 能在 Ubuntu 24.04 ARM64 服务器上原生运行，同时保留已经验证的 x86_64 Docker 路径。

目标服务器：

- 架构：aarch64/ARM64；
- CPU：20；
- 内存：119 GiB；
- 磁盘可用空间：719 GiB；
- Docker：28.3.3；
- 网络可访问 Wave、Seqera Containers 和 Nextflow Registry。

## 兼容性原则

现有 `server_docker` profile 保持不变，继续只支持 x86_64。

新增 `server_docker_arm64` profile，只支持 ARM64。禁止自动回退到 QEMU/amd64 模拟。

科学参数保持不变：

- nf-core/rnaseq 3.26.0；
- Nextflow 25.10.4；
- STAR + Salmon + tximport；
- GRCh38.p14 primary assembly；
- GENCODE Release 50；
- T2A/T2B 输入、参数和质控规则不变。

## ARM64 运行配置

新增 `configs/profiles/server_docker_arm64.config`，包含：

- `docker.enabled = true`；
- `wave.enabled = true`；
- `wave.strategy = ['conda']`；
- `process.arch = 'linux/arm64'`；
- CPU 上限 16；
- 单任务内存上限 60 GB；
- 单任务时间上限 72 小时。

Wave 只负责根据软件依赖构建和提供 ARM64 容器。FASTQ、参考文件、counts 和分析任务仍保留并执行在本地服务器。

## MVP 接口变化

新增合法 profile：

```text
server_docker_arm64
```

需要更新：

- preflight、runner、execute 和 smoke-test 的 profile 类型；
- ARM64 网络预检；
- 服务器操作文档。

架构规则：

- `local_docker`：非 x86_64 时为 WARN；
- `server_docker`：必须为 x86_64；
- `server_docker_arm64`：必须为 aarch64 或 arm64。

ARM profile 额外检查：

- `wave.seqera.io`；
- `community.wave.seqera.io`；
- `registry.nextflow.io`。

## 验证顺序

1. 本地单元测试验证 profile 分流；
2. 服务器安装 Java 17 和 Nextflow 25.10.4；
3. ARM64 preflight 必须 PASS；
4. ARM64 小型 smoke-test；
5. 检查运行容器为 ARM64；
6. 验证 counts、MultiQC 和运行报告；
7. 运行 T2A；
8. T2A 通过后运行 T2B。

## 验收条件

ARM smoke-test 必须满足：

- Nextflow 退出码为 0；
- 不出现 `exec format error`；
- 不启用 QEMU；
- counts 和 MultiQC 存在；
- gene ID 与样本列正确；
- counts 为非负数；
- 机器可读报告记录 ARM profile、架构和执行命令。

跨架构结果允许存在浮点数末位差异，不要求文件 SHA-256 完全一致，但必须使用相同科学定义和软件版本。

## 失败处理

如果任一 nf-core 模块无法生成或拉取 ARM64 容器：

1. 立即停止；
2. 记录失败模块、Conda 定义和 Wave 响应；
3. 不使用 amd64 模拟自动绕过；
4. 评估是否需要单独构建并冻结 ARM64 镜像。

## 非目标

本次不包括：

- 修改 T2A/T2B 科学参数；
- 升级 nf-core/rnaseq；
- 支持其他组学流程；
- 删除或放宽 x86_64 profile；
- 使用 QEMU 运行完整人类数据。

## 版本策略

- `v0.1.0-alpha.1`：x86_64 本地验证版本；
- ARM64 功能完成并通过 smoke-test 后发布 `v0.1.0-alpha.2`；
- T2A/T2B 完成后再决定正式 MVP 标签。
