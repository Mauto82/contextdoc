# Project 0: Todo List Manager

A simple demonstration of ContextDoc in action, using a basic todo list application.

## Overview

This project implements a command-line todo list manager with the following features:
- Create, read, update, and delete todo items
- Mark items as complete/incomplete
- Filter by status
- Persist data to a JSON file

The primary purpose is to demonstrate ContextDoc in practice: lightweight `.ctx` companions that capture what the code cannot say about itself.

## File Structure

```
./
├── Dockerfile                      # Container definition
├── docker-compose.yml              # Container orchestration
├── todo_app.py                     # Main application
├── todo_app.py.ctx                # ContextDoc for main application
├── models/
│   ├── todo_item.py                # Todo item model
│   └── todo_item.py.ctx           # ContextDoc for model
└── services/
    ├── todo_service.py             # Business logic
    ├── todo_service.py.ctx        # ContextDoc for business logic
    ├── storage_service.py          # Persistence layer
    └── storage_service.py.ctx     # ContextDoc for persistence
```

## Running the Application

### Option 1: Using Docker 🐳 (recommended)

The easiest way to run the application is using Docker:

```bash
# Build and start the container
docker-compose up -d

# Run the app
docker-compose run --rm --service-ports todo-app

# To exit: Press Ctrl+C, then Ctrl+P, Ctrl+Q to detach without stopping
# Or just exit the app with the 'exit' command
```

The data will persist between container restarts in the `./data` directory.

### Option 2: Running Locally

If you prefer to run the application directly:

```bash
# Make sure you have Python 3.8+ installed
python todo_app.py
```

## Available Commands

Once the application is running, you can use the following commands:

- `add` - Create a new todo
- `complete <id>` - Mark a todo as complete
- `delete <id>` - Delete a todo
- `update <id>` - Update a todo's title
- `filter active` - Show only active todos
- `filter completed` - Show only completed todos
- `filter all` - Show all todos
- `help` - Display available commands
- `exit` - Exit the application

## Exploring ContextDoc

The `.ctx` files accompany each Python file and contain only what the code cannot say about itself:

- **Tensions** — architectural decisions that look arbitrary but are intentional
- **Workflows** — key flows as readable sequences, including error paths
- **Conceptual tests** — declarative, language-agnostic scenarios that survive refactors
- **TODOs** — pending work in the context of the specific file

Open `todo_app.py` and `todo_app.py.ctx` side by side: the source tells you *what* the code does, the `.ctx` tells you *why* certain constraints exist and *what* the intended behavior should be across full scenarios.