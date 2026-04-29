---
name: software-architecture
description: Implements design patterns including Clean Architecture, SOLID principles, and comprehensive software design best practices. Use when planning system architecture, refactoring code, or designing new modules.
---

# Software Architecture & Design Principles

## Core Principles (SOLID)
1. **Single Responsibility Principle**: A class should have one, and only one, reason to change.
2. **Open/Closed Principle**: Software entities should be open for extension, but closed for modification.
3. **Liskov Substitution Principle**: Objects in a program should be replaceable with instances of their subtypes without altering the correctness of that program.
4. **Interface Segregation Principle**: Many client-specific interfaces are better than one general-purpose interface.
5. **Dependency Inversion Principle**: Depend upon abstractions, not concretions.

## Clean Architecture Guidance
- **Domain/Entities**: Core business logic and models. No external dependencies.
- **Use Cases/Interactors**: Application specific business rules.
- **Interface Adapters**: Controllers, Presenters, and Gateways.
- **Frameworks and Drivers**: Web frameworks, Databases, UI, etc. (Outermost layer).

## When building new features:
- Separate the parsing logic from the database storage logic.
- Use abstract interfaces (e.g., `BaseParser`, `BaseDatabaseConnector`) to allow adding new DBs or file types without changing the core engine.
- Favor dependency injection for database connections.
