# Workflow Compensation Lab

A local, restartable example of a compensating workflow. Two pretend event bookings contend for the same resources. When the second run cannot reserve a room, it releases only its own earlier reservations in reverse order and leaves the other booking intact.

```sh
python demo.py
python -m pip install pytest ruff
python -m pytest -q
ruff check .
```

`start(run_id, resources)` is idempotent for an unchanged plan. Each `tick(run_id)` performs at most one transition: reserve, record a conflict, release, or do nothing when terminal. The cursor points to the number of acquired resources. A SQLite transaction commits the resource effect, cursor and audit record together. A process can reopen the file between steps and continue without repeating the committed transition. Tests exercise resumed compensation, a first-step conflict, terminal no-ops, and rollback when the journal write fails.

All effects in this example are local SQLite writes, so atomicity comes from sharing the same database. Real distributed Sagas need idempotent external operations and independent failure/retry handling; this lab does not provide cross-service transactions, persistence of retry schedules or a scheduler. Completed runs keep their reservations; there is no separate cancellation operation.
