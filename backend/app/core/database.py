from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, echo=settings.sql_echo, pool_pre_ping=True)  # pre_ping: 끊긴 연결 자동 교체
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """요청 하나 = 세션 하나 = 트랜잭션 하나. 성공하면 COMMIT, 예외면 ROLLBACK (docs/04-transaction.md).

    그래서 Service는 commit/rollback을 직접 부르지 않는다. 일을 마치면 return, 실패면 raise만 한다.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise  # 삼키면 실패한 요청이 200으로 나간다
    finally:
        db.close()


# scope="function": 응답을 보내기 "전에" commit한다. 기본값(request)이면 응답 뒤에 commit해서 실패해도 200이 나간다
DbSession = Annotated[Session, Depends(get_db, scope="function")]


def check_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
