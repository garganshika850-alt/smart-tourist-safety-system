# Smart Tourist Safety and Emergency Response System

A real-time tourist safety monitoring and emergency response system demonstrating **Operating Systems** and **Database Management Systems** concepts.

## Overview

The system records tourist safety events in PostgreSQL, prioritizes emergencies
with a thread-safe priority queue, and assigns available resources inside a
database transaction. The separate Banker's Algorithm module demonstrates safe
state checking; the emergency priority queue does not implement Banker's.

## Architecture

```
Browser Dashboard → Flask API / WebSocket → PostgreSQL
                              │
                   Priority Queue and Workers
                              │
                    Transactional Dispatch
```

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python / Flask |
| Database | PostgreSQL |
| Real-time | Flask-SocketIO |
| Dashboard data | Flask REST API |

## Project layout

```text
backend/      Console, Flask API modules, database access, dispatch, and workers
database/     PostgreSQL schema, seed data, and setup/verification scripts
requirements.txt Python dependencies
```

## OS Concepts Demonstrated

- Multithreading (worker thread pool)
- Priority Scheduling (PriorityQueue)
- Synchronization (Lock, Semaphore)
- Resource Allocation
- Banker's safety checking (separate module)

## DBMS Concepts Demonstrated

- Relational Database Design (ER Model, Normalization)
- Constraints (PK, FK, NOT NULL, UNIQUE, CHECK)
- Transactions (BEGIN, COMMIT, ROLLBACK)
- ACID Properties
- Concurrency Control (MVCC, Locking)
- SQL Queries and Joins

## Phase 1: Runnable 50% Milestone

The runnable application is the PostgreSQL-backed interactive console and
Python dispatch core. It includes tourist registration, emergency creation, a thread-safe
priority queue, worker threads, synchronized resource allocation, transactional
dispatch, and database audit logs. Priority scheduling and the separate Banker's
safety algorithm are different demonstrations.

### Requirements

- Python 3.10 or newer
- PostgreSQL 14 or newer
- The packages listed in `requirements.txt`

### Setup

From this project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
touch .env
```

Set `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, and
`DATABASE_PASSWORD` in `.env` to match a PostgreSQL role that can create tables
and data in the selected database. Create the PostgreSQL role/database, start
PostgreSQL, then run:

```sh
sudo systemctl start postgresql
sudo -u postgres createuser --pwprompt tourist_admin
sudo -u postgres createdb --owner=tourist_admin tourist_safety_db
./database/setup_db.sh
```

On Debian/Ubuntu systems with a versioned cluster, use this instead of the
`systemctl` command (replace `18` with the installed PostgreSQL major version):

```sh
sudo pg_ctlcluster 18 main start
```

The setup script loads `schema.sql` and `seed.sql`. **It drops/recreates the
project tables and resets seed data**, so use it only on a disposable project
database. The Python-only setup commands are also available:

```sh
python -m database.load_schema
python -m database.load_seed
python -m database.verify_schema
```

### Run the console

```sh
python -m backend.console.main
```

Use the menu to register tourists, create and process emergencies, inspect
resources and logs, and start or stop background workers. PostgreSQL must be
running and configured before starting the console.
After an incident has been dispatched, use menu option 11 when its response is
complete; this releases its active resource assignments and recalculates the
assigned rescue teams' capacity.

## License

Academic Project
