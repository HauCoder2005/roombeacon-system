import pytest
import json
from unittest.mock import MagicMock
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.infrastructure.mysql.repositories.observation_repository import MySQLObservationRepository
from roombeacon_crawler.models.persistence_context import PersistenceContext
from roombeacon_crawler.enums.ingestion_origin import IngestionOrigin

@pytest.fixture
def mock_conn():
    conn = MagicMock()
    res = MagicMock()
    res.lastrowid = 100
    conn.execute.return_value = res
    return conn

def test_live_crawler_origin(mock_conn):
    repo = MySQLObservationRepository(connection=mock_conn)
    obs = BronzeObservation(
        source="test_src", run_id="run_1", url="http", title_raw="title", listing_id="1"
    )
    context = PersistenceContext(ingestion_origin=IngestionOrigin.LIVE_CRAWLER)
    
    version_id, is_inserted = repo.insert_observation(obs, 10, context)
    
    assert version_id == 100
    assert is_inserted is True
    
    called_query, called_params = mock_conn.execute.call_args[0]
    assert called_params["ingestion_origin"] == "LIVE_CRAWLER"

def test_reconciler_origin(mock_conn):
    repo = MySQLObservationRepository(connection=mock_conn)
    obs = BronzeObservation(
        source="test_src", run_id="run_1", url="http", title_raw="title", listing_id="1"
    )
    context = PersistenceContext(ingestion_origin=IngestionOrigin.BRONZE_RECONCILER)
    
    version_id, is_inserted = repo.insert_observation(obs, 10, context)
    
    called_query, called_params = mock_conn.execute.call_args[0]
    assert called_params["ingestion_origin"] == "BRONZE_RECONCILER"

def test_unknown_origin(mock_conn):
    repo = MySQLObservationRepository(connection=mock_conn)
    obs = BronzeObservation(
        source="test_src", run_id="run_1", url="http", title_raw="title", listing_id="1"
    )
    
    version_id, is_inserted = repo.insert_observation(obs, 10)
    
    called_query, called_params = mock_conn.execute.call_args[0]
    assert called_params["ingestion_origin"] == "UNKNOWN"

def test_duplicate_origin_preserved(mock_conn):
    orig = MagicMock()
    orig.args = (1062,)
    
    select_res = MagicMock()
    select_res.fetchone.return_value = (100,)
    
    mock_conn.execute.side_effect = [IntegrityError("","", orig), select_res]
    
    repo = MySQLObservationRepository(connection=mock_conn)
    obs = BronzeObservation(
        source="test_src", run_id="run_1", url="http", title_raw="title", listing_id="1"
    )
    
    context = PersistenceContext(ingestion_origin=IngestionOrigin.LIVE_CRAWLER)
    version_id, is_inserted = repo.insert_observation(obs, 10, context)
    
    assert version_id == 100
    assert is_inserted is False
    assert mock_conn.execute.call_count == 2
