"""Exercise the production persistence engine in an isolated test schema."""
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from test_zoning import client, plan, command  # noqa: F401
from test_development import building, parcel_source  # noqa: F401
from app.services.simulation.planning import store


@pytest.fixture
def postgres_store(monkeypatch):
    url = os.getenv('PLANNING_TEST_DATABASE_URL') or os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('PLANNING_TEST_DATABASE_URL is required for isolated PostgreSQL tests')
    schema = 'planning_test_' + uuid4().hex
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def connect():
        return psycopg.connect(url, options=f'-c search_path={schema}')
    monkeypatch.setattr(store, 'warehouse_configured', lambda: True)
    monkeypatch.setattr(store, 'connect_to_warehouse', connect)
    monkeypatch.delenv('PLANNING_SQLITE_PATH', raising=False)
    try:
        yield connect
    finally:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_development_study_is_visible_to_next_request_and_worker(client, plan, parcel_source, postgres_store):
    plan = command(client, plan, 'save_building', building())
    response = client.post(f"/api/v1/zoning/plans/{plan['id']}/simulation/studies", json={
        'revision': plan['revision'], 'scenario_id': plan['scenarios'][1]['id'], 'parcel_id': '3885881'})
    assert response.status_code == 201, response.text
    study = response.json()
    response = client.get(f"/api/v1/planning/studies/{study['id']}")
    assert response.status_code == 200, response.text
    job = client.post(f"/api/v1/planning/studies/{study['id']}/runs", json={
        'mode': 'screening', 'idempotency_key': 'postgres-bridge'})
    assert job.status_code == 202, job.text
    claimed = store.claim()
    assert claimed['id'] == job.json()['id']
    assert store.load_document(claimed['study_id'], 'study')['id'] == study['id']


def test_atomic_submission_is_readable_and_retry_safe_in_postgres(client, plan, parcel_source, postgres_store, tmp_path, monkeypatch):
    from app.services.simulation.planning.jobs import process_one
    monkeypatch.setenv('SIMULATION_WORK_DIR', str(tmp_path / 'solvers'))
    plan = command(client, plan, 'save_building', building())
    path = f"/api/v1/zoning/plans/{plan['id']}/simulation/runs"
    body = {'revision': plan['revision'], 'scenario_id': plan['scenarios'][1]['id'],
            'parcel_id': '3885881', 'mode': 'screening', 'idempotency_key': 'postgres-atomic'}
    result = client.post(path, json=body)
    assert result.status_code == 202, result.text
    again = client.post(path, json=body).json()
    assert again['job']['id'] == result.json()['job']['id']
    finished = process_one()
    assert finished['status'] == 'succeeded', finished
    assert client.get(f"/api/v1/planning/runs/{finished['result_id']}").status_code == 200


def test_atomic_submission_rolls_back_study_if_enqueue_fails(postgres_store, monkeypatch):
    execute = store.Session.execute
    def fail_job(self, statement, arguments=()):
        if statement.startswith('INSERT INTO planning_jobs'):
            raise psycopg.OperationalError('Injected job write failure')
        return execute(self, statement, arguments)
    monkeypatch.setattr(store.Session, 'execute', fail_job)
    with pytest.raises(store.StoreError):
        store.start_study({'title': 'rollback'}, 'hash', 'test', 'screening', 'rollback-key')
    with store.transaction() as session:
        assert session.execute('SELECT count(*) FROM planning_documents').fetchone()[0] == 0
        assert session.execute('SELECT count(*) FROM planning_jobs').fetchone()[0] == 0
