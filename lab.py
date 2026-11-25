"""Durable, stepwise compensation for simulated local resource reservations."""

import json
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tick:
    state: str
    action: str
    resource: str | None = None


class Workflow:
    def __init__(self, path: str | Path):
        self.path = path
        with closing(self._connect()) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, plan TEXT NOT NULL,
                    cursor INTEGER NOT NULL, state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    resource TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id)
                );
                CREATE TABLE IF NOT EXISTS journal (
                    seq INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    action TEXT NOT NULL, resource TEXT NOT NULL
                );
            ''')

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def start(self, run: str, resources: Iterable[str]) -> None:
        plan = list(resources)
        if not run or not plan or not all(isinstance(x, str) and x for x in plan):
            raise ValueError('run and resource names are required')
        if len(plan) != len(set(plan)):
            raise ValueError('each resource may appear only once per plan')
        payload = json.dumps(plan)
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT plan FROM runs WHERE id=?', (run,)).fetchone()
            if current is None:
                db.execute('INSERT INTO runs VALUES (?, ?, 0, ?)', (run, payload, 'forward'))
            elif current[0] != payload:
                raise ValueError('run already exists with a different plan')

    def tick(self, run: str) -> Tick:
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT plan, cursor, state FROM runs WHERE id=?', (run,)).fetchone()
            if row is None:
                raise KeyError(run)
            plan, cursor, state = row
            resources = json.loads(plan)
            if state in {'completed', 'compensated'}:
                return Tick(state, 'noop')
            if state == 'forward':
                resource = resources[cursor]
                inserted = db.execute(
                    'INSERT INTO reservations VALUES (?, ?) ON CONFLICT(resource) DO NOTHING',
                    (resource, run),
                ).rowcount
                if inserted:
                    cursor += 1
                    action = 'reserve'
                    state = 'completed' if cursor == len(resources) else 'forward'
                else:
                    action = 'conflict'
                    state = 'compensating' if cursor else 'compensated'
            else:
                cursor -= 1
                resource = resources[cursor]
                deleted = db.execute(
                    'DELETE FROM reservations WHERE resource=? AND run_id=?', (resource, run),
                ).rowcount
                if deleted != 1:
                    raise RuntimeError('missing reservation: compensation cannot continue')
                action = 'release'
                state = 'compensating' if cursor else 'compensated'
            db.execute('UPDATE runs SET cursor=?, state=? WHERE id=?', (cursor, state, run))
            db.execute(
                'INSERT INTO journal (run_id, action, resource) VALUES (?, ?, ?)',
                (run, action, resource),
            )
            return Tick(state, action, resource)

    def history(self, run: str) -> list[tuple[str, str]]:
        with closing(self._connect()) as db:
            return db.execute(
                'SELECT action, resource FROM journal WHERE run_id=? ORDER BY seq', (run,),
            ).fetchall()

    def held(self) -> dict[str, str]:
        with closing(self._connect()) as db:
            return dict(db.execute('SELECT resource, run_id FROM reservations ORDER BY resource'))
