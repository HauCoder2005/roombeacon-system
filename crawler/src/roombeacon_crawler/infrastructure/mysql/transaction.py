import logging
from typing import Any

from roombeacon_crawler.domain.ports.persistence_port import TransactionManagerPort
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory

logger = logging.getLogger(__name__)


class MySQLTransactionManager(TransactionManagerPort):
    """Quản lý ranh giới giao dịch tập trung (Unit of Work) cho MySQL."""

    def __init__(self, engine=None) -> None:
        self.engine = engine or MySQLConnectionFactory.get_engine()
        self._connection = None
        self._transaction = None

    @property
    def connection(self):
        if self._connection is None:
            self._connection = self.engine.connect()
        return self._connection

    def begin(self) -> Any:
        if self._transaction is None:
            self._transaction = self.connection.begin()
            logger.debug("Bắt đầu MySQL transaction.")
        return self._transaction

    def commit(self) -> None:
        if self._transaction is not None:
            self._transaction.commit()
            logger.debug("Đã commit MySQL transaction.")
            self._transaction = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def rollback(self) -> None:
        if self._transaction is not None:
            self._transaction.rollback()
            logger.warning("Đã rollback MySQL transaction do lỗi.")
            self._transaction = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None
