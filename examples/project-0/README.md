# Project 0: Todo List Manager

A simple demonstration of ConceptDoc in action, using a basic todo list application.

## Overview

This project implements a command-line todo list manager with the following features:
- Create, read, update, and delete todo items
- Mark items as complete/incomplete
- Filter by status
- Persist data to a JSON file

The primary purpose is to demonstrate how ConceptDoc can provide rich contextual information about even a simple application.

## File Structure

```
./
├── Dockerfile                      # Container definition
├── docker-compose.yml              # Container orchestration
├── todo_app.py                     # Main application
├── todo_app.py.cdoc                # ConceptDoc for main application
├── models/
│   ├── todo_item.py                # Todo item model
│   └── todo_item.py.cdoc           # ConceptDoc for model
└── services/
    ├── todo_service.py             # Business logic
    ├── todo_service.py.cdoc        # ConceptDoc for business logic
    ├── storage_service.py          # Persistence layer
    └── storage_service.py.cdoc     # ConceptDoc for persistence
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

## Exploring ConceptDoc

The key feature of this project is the `.cdoc` files that accompany each Python file. These provide:

1. **Rich context** about the purpose and design of each component
2. **State models** that define valid states and transitions
3. **Invariants** that must be maintained 
4. **Conceptual tests** that verify behavior
5. **Test fixtures** for standardized testing

To see the power of ConceptDoc

1. Open a `.py` file and its corresponding `.py.cdoc` file side by side
2. Note how the doc file explains not just what the code does, but why
3. See how conceptual tests describe high-level behaviors
4. Observe how invariants capture critical properties that must be maintained

## ConceptDoc Benefits Demonstrated

This simple example shows how ConceptDoc

- **Clarifies intent**: Understanding why code works as it does
- **Defines boundaries**: Clear expectations about states and transitions
- **Establishes contracts**: Explicit pre- and post-conditions
- **Creates tests**: Ready-made scenarios for validation
- **Sets standards**: Consistent test data across components

Even in this minimal example, these benefits add significant value beyond traditional documentation approaches.