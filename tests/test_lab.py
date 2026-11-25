import sqlite3

import pytest

from lab import Tick, Workflow


def test_reopened_process_releases_in_reverse(tmp_path):
    path = tmp_path / 'test.sqlite'
    w = Workflow(path)
    w.start('a', ['locked'])
    assert w.tick('a') == Tick('completed', 'reserve', 'locked')
    w.start('b', ['first', 'second', 'locked'])
    assert [w.tick('b').state for _ in range(3)] == ['forward', 'forward', 'compensating']
    w = Workflow(path)
    assert w.tick('b') == Tick('compensating', 'release', 'second')
    assert Workflow(path).tick('b') == Tick('compensated', 'release', 'first')
    assert w.tick('b') == Tick('compensated', 'noop')
    assert w.held() == {'locked': 'a'}
    assert w.history('b') == [('reserve', 'first'), ('reserve', 'second'),
                              ('conflict', 'locked'), ('release', 'second'), ('release', 'first')]


def test_idempotent_start_and_terminal_tick(tmp_path):
    w = Workflow(tmp_path / 'test.sqlite')
    w.start('a', ['first'])
    w.start('a', ['first'])
    with pytest.raises(ValueError, match='different plan'):
        w.start('a', ['other'])
    assert w.tick('a').state == 'completed'
    assert w.tick('a') == Tick('completed', 'noop')
    assert w.history('a') == [('reserve', 'first')]


def test_first_step_conflict_no_release(tmp_path):
    w = Workflow(tmp_path / 'test.sqlite')
    w.start('a', ['x'])
    w.tick('a')
    w.start('b', ['x'])
    assert w.tick('b') == Tick('compensated', 'conflict', 'x')
    assert w.held() == {'x': 'a'}


def test_transaction_rolls_back_on_journal_failure(tmp_path):
    path = tmp_path / 'test.sqlite'
    w = Workflow(path)
    w.start('a', ['x'])
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TRIGGER fail_log BEFORE INSERT ON journal
                          BEGIN SELECT RAISE(ABORT, 'journal unavailable'); END;""")
    with pytest.raises(sqlite3.IntegrityError, match='journal unavailable'):
        w.tick('a')
    assert w.held() == {}
    assert w.history('a') == []
    with sqlite3.connect(path) as db:
        db.execute('DROP TRIGGER fail_log')
    assert Workflow(path).tick('a') == Tick('completed', 'reserve', 'x')


def test_invalid_plan_and_unknown_run(tmp_path):
    w = Workflow(tmp_path / 'test.sqlite')
    with pytest.raises(ValueError):
        w.start('a', ['x', 'x'])
    with pytest.raises(KeyError):
        w.tick('missing')
