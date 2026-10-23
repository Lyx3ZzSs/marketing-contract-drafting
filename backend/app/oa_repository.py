"""Read-only OA access. Never reuse the application's PostgreSQL session."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import URL, Connection, Engine, create_engine, text

from app.core.config import get_settings


@lru_cache
def oa_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        URL.create(
            "mysql+pymysql",
            username=settings.oa_user,
            password=settings.oa_password.get_secret_value(),
            host=settings.oa_host,
            port=settings.oa_port,
            database=settings.oa_database,
            query={"charset": "utf8mb4"},
        ),
        pool_size=3,
        max_overflow=2,
        pool_timeout=3,
        pool_pre_ping=True,
        pool_recycle=300,
        isolation_level="REPEATABLE READ",
        hide_parameters=True,
        connect_args={
            "connect_timeout": settings.oa_connect_timeout,
            "read_timeout": settings.oa_query_timeout + 1,
            "write_timeout": settings.oa_connect_timeout,
        },
    )


@contextmanager
def read_connection() -> Iterator[Connection]:
    with oa_engine().connect() as connection:
        # Applies to the next transaction; both summary reads share one snapshot.
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        try:
            yield connection
        finally:
            connection.rollback()


def select_prefix() -> str:
    timeout_ms = get_settings().oa_query_timeout * 1000
    return f"SELECT /*+ MAX_EXECUTION_TIME({timeout_ms}) */"


MAIN_FIELDS = """ID AS id, field0055 AS serial_number,
    field0087 AS status, field0062 AS initiated_at"""


def find_contracts(serial_number: str) -> list[dict[str, Any]]:
    with read_connection() as connection:
        rows = connection.execute(
            text(
                f"{select_prefix()} {MAIN_FIELDS} FROM formmain_3396 "
                "WHERE BINARY field0055 = BINARY :serial ORDER BY ID LIMIT 101"
            ),
            {"serial": serial_number},
        )
        return [dict(row) for row in rows.mappings()]


def read_projects(record_id: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    with read_connection() as connection:
        main = (
            connection.execute(
                text(f"{select_prefix()} {MAIN_FIELDS} FROM formmain_3396 WHERE ID = :id"),
                {"id": record_id},
            )
            .mappings()
            .first()
        )
        if main is None:
            return None, []
        rows = connection.execute(
            text(
                f"{select_prefix()} ID AS id, field0110 AS project_code, "
                "field0445 AS station_code, field0140 AS province_id, "
                "field0132 AS project_name, field0238 AS station_name, field0385 AS amount, "
                "field0485 AS currency_id, field0384 AS software_copyright_name, "
                "field0233 AS hardware_amount, field0234 AS software_service_amount, "
                "field0291 AS other_software_service_amount "
                "FROM formson_3398 WHERE formmain_id = :id ORDER BY sort, ID LIMIT 10001"
            ),
            {"id": record_id},
        )
        return dict(main), [dict(row) for row in rows.mappings()]
