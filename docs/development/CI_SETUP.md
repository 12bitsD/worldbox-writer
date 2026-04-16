# CI/CD 配置说明 (CI Setup Guide)

**文档状态**：Draft (Sprint 0)

## 1. GitHub Actions 权限配置

在推送 CI workflow 文件之前，需要先在仓库设置中开启 Workflow 写权限：

1. 进入仓库 `Settings → Actions → General`
2. 在 **Workflow permissions** 区域，选择 **Read and write permissions**
3. 点击 **Save**

## 2. CI Workflow 文件

将以下内容保存为 `.github/workflows/ci.yml` 并推送到仓库：

```yaml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install black isort mypy pytest pytest-cov

      - name: Check formatting (black)
        run: black --check .

      - name: Check import order (isort)
        run: isort --check-only .

      - name: Run tests
        run: pytest --cov=src --cov-report=term-missing -v
```

## 3. 本地开发环境快速启动

```bash
# 克隆仓库
git clone https://github.com/12bitsD/worldbox-writer.git
cd worldbox-writer

# 安装依赖（Sprint 1 后会有 pyproject.toml）
pip install black isort mypy pytest pytest-cov

# 运行代码格式化
black .
isort .

# 运行测试
pytest -v
```
