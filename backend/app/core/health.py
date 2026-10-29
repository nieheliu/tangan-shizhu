"""依赖探测。任一组件失败都记为 down，不把异常抛给健康检查接口。"""

from sqlalchemy import create_engine, text

from app.core.config import get_settings

ComponentStatus = dict[str, str]


def check_postgres() -> str:
    settings = get_settings()
    if not settings.database_url:
        return "down"
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 2},
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()
    return "up"


def check_neo4j() -> str:
    settings = get_settings()
    if not settings.neo4j_uri or not settings.neo4j_password:
        return "down"
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=2,
    )
    try:
        driver.verify_connectivity()
    finally:
        driver.close()
    return "up"


def check_chroma() -> str:
    import chromadb

    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_path)
    client.heartbeat()
    return "up"


def check_llm() -> str:
    settings = get_settings()
    if not settings.llm_api_key:
        return "down"
    from openai import OpenAI

    from app.core.llm import resolve_cloud_base_url

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=resolve_cloud_base_url(settings),
        timeout=2,
    )
    client.models.list()
    return "up"


def check_all() -> ComponentStatus:
    checks = {
        "postgresql": check_postgres,
        "neo4j": check_neo4j,
        "chroma": check_chroma,
        "llm": check_llm,
    }
    status: ComponentStatus = {}
    for name, check in checks.items():
        try:
            status[name] = check()
        except Exception:  # noqa: BLE001  依赖失败不能让健康检查接口报错
            status[name] = "down"
    return status


def health_payload() -> dict[str, object]:
    return {"status": "ok", "components": check_all()}
