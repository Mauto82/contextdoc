# Project 1: User Management API

A FastAPI REST API demonstrating ContextDoc on an async, multi-file project with authentication.

## Overview

This project implements a minimal user management API with:
- User registration and login (JWT)
- Password hashing (bcrypt)
- Soft delete (users are never hard-deleted)
- Async SQLAlchemy + SQLite

It deliberately contains non-obvious architectural choices — JWT statelessness, bcrypt cost, soft delete, `is_active` default — all of which are documented in `.ctx` files, not in comments.

## File Structure

```
./
├── main.py          # FastAPI app, lifespan, routes
├── main.py.ctx
├── auth.py          # JWT + bcrypt
├── auth.py.ctx
├── models.py        # SQLAlchemy model + Pydantic schemas
├── models.py.ctx
├── database.py      # Async engine, session factory, FastAPI dependency
└── database.py.ctx
```

## Running the Application

```bash
pip install fastapi uvicorn[standard] sqlalchemy aiosqlite python-jose passlib httpx
uvicorn main:app --reload
```

API docs available at `http://localhost:8000/docs`.

## Exploring ContextDoc

This example contrasts with project-0 in two ways:

**Different tensions.** The constraints here are about security and data integrity: why tokens can't be revoked, why bcrypt rounds are non-negotiable, why email can't be changed, why users are never deleted. These are easy to accidentally undo in a refactor — the `.ctx` makes them explicit.

**Different `conceptualTests`.** Project-0 tests a synchronous CLI loop. Here the tests describe HTTP flows, status codes, and state transitions — still declarative, still language-agnostic, still useful as a spec for generating real tests with pytest + httpx.

Open `auth.py` and `auth.py.ctx` side by side: the source shows *what* the code does, the `.ctx` shows *why* it's structured that way and what the intended behavior is across all scenarios.
