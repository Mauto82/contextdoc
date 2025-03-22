FROM python:3.10-slim

WORKDIR /app

# Copy all application files to the container
COPY todo_app.py ./
COPY models/ ./models/
COPY services/ ./services/

# Create an empty data directory for persistence
RUN mkdir -p /app/data

# Set the default storage location to the data directory
ENV STORAGE_PATH=/app/data/todos.json

# Run the application
CMD ["python", "todo_app.py"]