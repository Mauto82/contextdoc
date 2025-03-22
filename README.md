# ConceptDoc: Enhanced Documentation for the AI Era

ConceptDoc is an emerging standard for creating structured, machine-readable documentation that enhances collaboration between human developers and AI assistants.

## 🚀 The Vision

As AI tools become integral to software development, our documentation practices need to evolve. ConceptDoc provides a standardized way to document code that goes beyond traditional approaches, offering rich context that both humans and AI systems can understand and leverage.

## 🔍 Core Concept

ConceptDoc introduces parallel documentation files (e.g., `user_service.py.cdoc`) that contain structured metadata about your code files. These files include:

- **State models** with explicit transitions
- **Invariants** that must be maintained
- **Pre/post-conditions** for methods
- **Standardized fixtures** for testing
- **Conceptual tests** in a declarative format
- **Business logic** rules and constraints
- **AI-specific guidance** for code generation

## 💡 Example

```json
// user_service.py.cdoc
{
  "metadata": {
    "filename": "user_service.py",
    "version": "1.2.0",
    "lastUpdate": "2025-03-22"
  },
  "purpose": "Manages user authentication and authorization",
  "stateModel": {
    "states": ["unregistered", "unverified", "active", "suspended"],
    "initialState": "unregistered",
    "transitions": [
      {
        "from": "unregistered",
        "to": "unverified",
        "trigger": "register()",
        "conditions": ["Valid email", "Password meets requirements"]
      },
      // More transitions...
    ]
  },
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
        "A new user is created with 'unverified' state",
        "A verification email is sent to the user"
      ],
      "examples": [
        // Examples...
      ],
      "errors": [
        // Potential errors...
      ]
    }
  ],
  "conceptualTests": [
    {
      "name": "Registration and login flow",
      "steps": [
        {
          "action": "register() with valid data",
          "expect": "User created with 'unverified' state"
        },
        // More test steps...
      ]
    }
  ]
}
```

## 🛠️ Current State of the Project

This project is currently in the **concept and standardization phase**. We are:

0. Defining the schema for ConceptDoc files

## 🤝 How to Contribute

We're looking for contributors to help shape this standard:

- **Schema designers**: Help define the structure of ConceptDoc files
- **Tool developers**: Build utilities for working with ConceptDoc files
- **Early adopters**: Try the approach in your projects and provide feedback
- **Documentation writers**: Help improve explanations and examples
- **AI researchers**: Provide insights on how to maximize utility for AI systems

## 📚 Getting Started

1. Check out the [schema specification](./schema/README.md)
2. Look at the [examples](./examples/) directory

## 🔮 Future Roadmap

- Q1 2025: Finalize v1.0 of the schema (we're already behind schedule, of course! 🙈 🤣)
- Q2 2025: Start development of tools and and IDE plugins
- Q3 2025: Release stable versions of tooling
- Q4 2025: Publish case studies and best practices
- 2026: Propose integration with major frameworks

## 📝 License

This project is licensed under the MIT License

---

*ConceptDoc: Because your code deserves documentation that both humans and machines can truly understand.*
