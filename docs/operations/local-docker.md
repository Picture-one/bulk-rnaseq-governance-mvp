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

## 常见问题

- `docker API ... daemon is running`：打开 Docker Desktop，等待 Engine 状态正常。
- WSL 中找不到 `docker`：Docker Desktop → Settings → Resources → WSL Integration，启用 Ubuntu-22.04。
- `localhost proxy` 警告：这是 WSL NAT 与 Windows localhost 代理的提示；若下载失败，应为 WSL 配置可访问的代理地址或关闭无效代理。
- 重新执行 smoke-test 会使用 Nextflow `-resume`，但每次生成独立报告和结果目录。
