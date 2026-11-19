"""一次性脚本：在虚拟机上安装 Docker 并启动 PostgreSQL 与 Neo4j。密码从环境变量读取，不写入仓库。"""

import os
import secrets
from pathlib import Path

import paramiko

password = os.environ["VM_SSH_PASSWORD"]
db_password = secrets.token_urlsafe(18)
host = "192.168.88.138"
remote_dir = "/home/liuyi/tangan-vm"
compose = (
    Path(__file__).resolve().parents[2] / "deploy" / "vm" / "docker-compose.vm.yml"
)
local_env = Path(__file__).resolve().parents[1] / ".env"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 900) -> int:
    print("CMD", cmd, flush=True)
    stdin, stdout, _stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    stdin.write(password + "\n")
    stdin.flush()
    stdin.channel.shutdown_write()
    out = stdout.read().decode(errors="replace").replace(password, "***")
    code = stdout.channel.recv_exit_status()
    print(out[-5000:])
    print("EXIT", code, flush=True)
    return code


def main() -> None:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        username="liuyi",
        password=password,
        timeout=20,
        allow_agent=False,
        look_for_keys=False,
    )
    if run(client, "sudo -S DEBIAN_FRONTEND=noninteractive apt-get update -y") != 0:
        raise SystemExit("apt-get update failed")
    if (
        run(
            client,
            "sudo -S DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2",
        )
        != 0
    ):
        raise SystemExit("docker install failed")
    run(client, "sudo -S systemctl enable --now docker")
    run(client, "sudo -S docker --version")
    run(client, "sudo -S docker compose version")
    run(client, f"mkdir -p {remote_dir}")

    sftp = client.open_sftp()
    sftp.put(str(compose), f"{remote_dir}/docker-compose.vm.yml")
    with sftp.file(f"{remote_dir}/.env", "w") as env_file:
        env_file.write(
            "POSTGRES_USER=tangan\n"
            f"POSTGRES_PASSWORD={db_password}\n"
            "POSTGRES_DB=tangan\n"
            f"NEO4J_PASSWORD={db_password}\n"
        )
    sftp.chmod(f"{remote_dir}/.env", 0o600)
    sftp.close()

    compose_cmd = (
        f"cd {remote_dir} && sudo -S docker compose --env-file .env "
        "-f docker-compose.vm.yml up -d"
    )
    if run(client, compose_cmd, timeout=1200) != 0:
        raise SystemExit("docker compose failed")

    local_env.write_text(
        "\n".join(
            [
                f"DATABASE_URL=postgresql+psycopg://tangan:{db_password}@{host}:5432/tangan",
                f"NEO4J_URI=bolt://{host}:7687",
                "NEO4J_USER=neo4j",
                f"NEO4J_PASSWORD={db_password}",
                "LLM_PROVIDER=deepseek",
                "LLM_API_KEY=",
                "LLM_BASE_URL=https://api.deepseek.com",
                "LLM_MODEL=deepseek-chat",
                "OLLAMA_BASE_URL=http://127.0.0.1:11434/v1",
                "OLLAMA_MODEL=qwen2.5:7b-instruct",
                "EMBEDDING_MODEL=bge-m3",
                "CHROMA_PATH=data/chroma",
                "JWT_SECRET=dev-only-change-this-jwt-secret-key",
                "APP_TIMEZONE=Asia/Shanghai",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("LOCAL_ENV_WRITTEN", flush=True)
    client.close()


if __name__ == "__main__":
    main()
