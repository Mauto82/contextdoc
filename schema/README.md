# ConceptDoc Schema Specification

This document defines the standard schema for ConceptDoc files (`.cdoc`), designed to provide structured and machine-readable documentation to improve collaboration between human developers and AI assistants.

## Documentation Papers

For a comprehensive introduction to ConceptDoc, please refer to these papers:
- [ConceptDoc Paper (English)](https://mautoblog.com/docs/conceptdoc-en)
- [ConceptDoc Paper (Italiano)](https://mautoblog.com/docs/conceptdoc-it)

## Basic Structure

A ConceptDoc file is a JSON document with the following basic structure:

```json
{
  "metadata": {
    "filename": "example.py",
    "version": "1.0.0",
    "lastUpdate": "YYYY-MM-DD"
  },
  "purpose": "Brief description of the file's purpose",
  "dependencies": [],
  "invariants": [],
  "components": [],
  "testFixtures": [],
  "conceptualTests": [],
  "businessLogic": {},
  "stateModel": {},
  "aiNotes": {}
}
```

## Main Sections

### 1. Metadata

Basic information about the documented file:

```json
"metadata": {
  "filename": "example.py",       // Name of the documented file
  "version": "1.0.0",             // File version
  "lastUpdate": "2025-03-22",     // Date of the last update
  "authors": ["Author Name"]      // Optional: authors of the file
}
```

### 2. Purpose

A concise description of the file's purpose:

```json
"purpose": "Provides functionality for user management, including authentication and authorization"
```

### 3. Dependencies

List of the file's dependencies with explanations of their use:

```json
"dependencies": [
  {
    "name": "StorageService",
    "reason": "Manages data persistence",
    "usage": "Used to load and save data"
  },
  {
    "name": "UserModel",
    "reason": "Main domain model",
    "usage": "Manipulated by all methods in this service"
  }
]
```

### 4. Invariants

Conditions that must always be maintained:

```json
"invariants": [
  "User IDs are unique and never reused",
  "Passwords are always hashed before being stored",
  "Usernames cannot be empty"
]
```

### 5. Components

Detailed documentation of classes, methods, and functions:

```json
"components": [
  {
    "name": "UserService.register",
    "signature": "register(email: str, password: str) -> User",
    "description": "Registers a new user in the system",
    "preconditions": [
      "Email must be valid and not already registered",
      "Password must meet security requirements"
    ],
    "postconditions": [
      "A new user is created with 'unverified' status",
      "A verification email is sent to the user"
    ],
    "examples": [
      {
        "input": {"email": "user@example.com", "password": "SecurePass123!"},
        "output": "User object with id=1, email='user@example.com', status='unverified'",
        "description": "Standard user registration"
      }
    ],
    "errors": [
      {
        "condition": "Email already registered",
        "response": "EmailExistsError",
        "mitigation": "Check if the email exists before registration"
      },
      {
        "condition": "Password does not meet requirements",
        "response": "WeakPasswordError",
        "mitigation": "Validate the password before registration"
      }
    ],
    "algorithmNotes": "Uses bcrypt for password hashing with a cost factor of 12"
  }
]
```

### 6. State Model

Definition of possible states and transitions:

```json
"stateModel": {
  "states": ["unregistered", "unverified", "active", "suspended", "deleted"],
  "initialState": "unregistered",
  "transitions": [
    {
      "from": "unregistered",
      "to": "unverified",
      "trigger": "register()",
      "conditions": ["Valid email", "Password meets requirements"]
    },
    {
      "from": "unverified",
      "to": "active",
      "trigger": "verify_email(token)",
      "conditions": ["Valid token", "Token not expired"]
    },
    {
      "from": "active",
      "to": "suspended",
      "trigger": "suspend(reason)",
      "conditions": ["User has violated terms of service"]
    },
    {
      "from": "suspended",
      "to": "active",
      "trigger": "reactivate()",
      "conditions": ["Suspension period ended"]
    },
    {
      "from": "*",
      "to": "deleted",
      "trigger": "delete()",
      "conditions": []
    }
  ]
}
```

### 7. Test Fixtures

Example data for tests:

```json
"testFixtures": [
  {
    "name": "empty_service",
    "description": "Service with no users",
    "data": {
      "users": [],
      "_next_id": 1
    }
  },
  {
    "name": "populated_service",
    "description": "Service with example users",
    "data": {
      "users": [
        {
          "id": 1,
          "email": "user1@example.com",
          "status": "active",
          "created_at": "2025-03-22T10:00:00"
        },
        {
          "id": 2,
          "email": "user2@example.com",
          "status": "unverified",
          "created_at": "2025-03-22T11:00:00"
        }
      ],
      "_next_id": 3
    }
  }
]
```

### 8. Conceptual Tests

Conceptual tests in a declarative format:

```json
"conceptualTests": [
  {
    "name": "Registration and login flow",
    "steps": [
      {
        "action": "register() with valid data",
        "expect": "User created with 'unverified' status"
      },
      {
        "action": "verify_email() with valid token",
        "expect": "User transitions to 'active' status"
      },
      {
        "action": "login() with correct credentials",
        "expect": "User session created"
      },
      {
        "action": "logout()",
        "expect": "User session terminated"
      }
    ]
  }
]
```

### 9. Business Logic

Business rules and constraints:

```json
"businessLogic": {
  "passwordPolicy": {
    "minLength": 8,
    "requireUppercase": true,
    "requireLowercase": true,
    "requireDigits": true,
    "requireSpecialChars": true
  },
  "emailVerification": {
    "tokenValidity": "24h",
    "resendCooldown": "15m"
  },
  "rateLimit": {
    "loginAttempts": {
      "maxAttempts": 5,
      "windowPeriod": "15m",
      "lockoutDuration": "30m"
    }
  }
}
```

### 10. AI Notes

Specific notes for AI assistants:

```json
"aiNotes": {
  "generationTips": [
    "Ensure all authentication operations are protected against timing attacks",
    "Implement input validation for all publicly exposed parameters",
    "Use prepared statements for database queries to prevent SQL injection"
  ],
  "commonPatterns": [
    "The service follows the Repository pattern for persistence",
    "Uses the Factory pattern for creating new users"
  ],
  "avoidPatterns": [
    "Avoid storing passwords in plaintext",
    "Avoid using predictable session tokens"
  ]
}
```

## Extensibility

The ConceptDoc schema is designed to be extensible. Teams can add custom sections to meet specific project needs while maintaining compatibility with standard tools.

## Validation

To ensure ConceptDoc files comply with the schema, it is recommended to use a JSON Schema validation tool. A complete validation schema will be provided in a future version.

## Examples

For complete examples of ConceptDoc files, see the [examples](../examples/) directory which contains reference implementations.

## Versioning

The ConceptDoc schema follows [Semantic Versioning](https://semver.org/). The current version is 0.1.0 (pre-release).

---

*ConceptDoc: Because your code deserves documentation that is truly understandable by both humans and machines.*