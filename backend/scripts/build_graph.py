"""重建 Neo4j 图谱。在 backend 目录执行：

    .\\.venv\\Scripts\\python scripts\\build_graph.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_sessionmaker
from app.graph.sync import build_graph


def main() -> None:
    with get_sessionmaker()() as session:
        stats = build_graph(session)
    print(
        "foods={foods} recipes={recipes} contains={contains} "
        "relations={relations} skipped={skipped}".format(**stats)
    )


if __name__ == "__main__":
    main()
