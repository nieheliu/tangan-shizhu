# 糖安食助 · 执行守则

完整方案见 [PLAN.md](PLAN.md)。下面是必须遵守的摘要。

1. 不要修改 `D:\javawebworkspace\personnal-Agent` 和 `D:\javawebworkspace\aiops`，也不要从中复制代码。全部新代码写在本仓库。
2. Windows PowerShell 里用 `;` 连接命令，不用 `&&`。Python 虚拟环境是 `backend\.venv`。
3. 按 PLAN.md 第 9 节一次做一个任务。完成后把该条 `[ ]` 改成 `[x]`，在第 13 节开发日志追加一行，并按第 11 节的格式提交。
4. 需要 API Key、虚拟机密码、删除或重建数据库、改变已确定的技术选型时，停下来问用户。
5. GI、禁忌和营养素数值不能编造。不确定的标 `source: "待核对"`。
6. 密钥只放 `.env`。提交 `.env.example`，不要提交 `.env` 或 `data/raw/*.pdf`。
7. 推荐和问答是一条 LangGraph 工作流，不引入多 Agent 框架。
8. 营养数字由后端计算。模型只返回食谱 id、解释和引用 id。
