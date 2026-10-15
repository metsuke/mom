# Manual de Usuario y Operación: Motor Python `mom-py` (v0.2.2)

---

## 1. Introducción y Propósito

El motor `mom-py` constituye la implementación en Python 3.11+ (basada exclusivamente en la biblioteca estándar `stdlib`) del marco metodológico **MOM (MetsuOS Methodology)**.

Su objetivo es administrar especificaciones atómicas bajo el estándar **ESA PSS-05**, resolver grafos de herencia múltiple (DAG) entre proyectos y generar entregables consolidados (`doc/*.md`), estructuras navegables para Obsidian (`vault/`) y reglas inmutables de contención para inteligencias artificiales (`AGENTS.md`).

---

## 2. Estructura de Rutas y Auto-inicialización

El motor opera bajo la siguiente jerarquía de directorios:

```text
mom/                 <-- Raíz del repositorio
├── LICENSE          <-- Licencia global del proyecto
├── data/            <-- Creado automáticamente por el código
│   └── projects/    <-- Almacenamiento de proyectos atómicos
└── mom-py/          <-- Motor Python
    ├── pyproject.toml
    ├── USER_MANUAL.md
    ├── schemas.py
    ├── projects.py
    ├── crud.py
    ├── compiler.py
    ├── agent.py
    └── cli.py