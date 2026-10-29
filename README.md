# 糖安食助

面向 2 型糖尿病成人的饮食参考助手。推荐先经过规则、知识图谱和指南检索，大模型只根据给定食谱和检索片段生成解释。营养数字由后端计算。

本系统仅供饮食参考，不能替代医生诊疗建议。

## 文档

开发以 [PLAN.md](PLAN.md) 为准，按第 9 节的任务顺序推进。给执行模型的守则见 [AGENTS.md](AGENTS.md)。

## 目录

- `backend/`：FastAPI
- `frontend/`：Vue 3
- `data/`：食材、食谱和指南的本地数据。`data/raw/*.pdf` 不进入 Git
- `deploy/`：虚拟机与后续部署配置
- `docs/`：接口约定和答辩材料

## 环境

- Windows，PowerShell。命令之间用 `;` 连接。
- Python 3.11（`py -3`）。虚拟环境在 `backend\.venv`。
- 后端和前端的启动方式会随任务补全。目前可以启动后端健康检查。

## 启动后端

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

浏览器打开 http://127.0.0.1:8000/docs 。健康检查是 `GET /api/v1/health`。

```powershell
cd backend
.\.venv\Scripts\python -m pytest
```
