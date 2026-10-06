# 本地 Bulk RNA-seq 治理 MVP 冒烟验证证据

## 1. 验证目的

验证 RNA-seq 治理 MVP 能够在 Windows 11/WSL2、Docker Desktop 和本地低内存环境中，调用固定版本的 nf-core/rnaseq，将小型 FASTQ 测试数据自动转换为 gene-level counts，并生成 MultiQC 报告和机器可读运行记录。

本验证属于工具链冒烟测试，不属于完整人类 T2A/T2B 科学验证。

## 2. 验证日期与代码基线

- 验证完成日期：2026-09-02
- 时区：Asia/Shanghai
- 验证前 Git 基线：`9683ce9`
- 执行环境：Ubuntu-22.04 on WSL2
- 运行配置：`local_docker`

## 3. 软件环境

- Docker：29.7.2，build `a7dcaa6`
- Java：OpenJDK 17.0.20
- Nextflow：25.10.4，build 11173
- uv：0.11.7
- nf-core/rnaseq：3.26.0
- Python 测试环境：3.11.15

## 4. 本地测试资产

本地稳定资产目录：

```text
/home/heng/.cache/rnaseq-mvp/smoke-assets/v3.26.0
