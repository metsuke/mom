# 🏛️ MOM — MetsuOS Methodology

**MOM** (MetsuOS Methodology) es un marco metodológico, motor de herramientas e infraestructura de especificación atómica de software basado en el estándar **ESA PSS-05**, los principios de portabilidad **POSIX** y una arquitectura de **herencia en Grafo Acíclico Dirigido (DAG)**.

Diseñado para garantizar la **soberanía tecnológica**, la trazabilidad bi-direccional estricta y el control humano inmutable sobre agentes de Inteligencia Artificial.

---

## 🚀 Características Principales

* **Estructura ESA PSS-05 Completa:** Gestión de ciclo de vida por fases formales:
  * `COR` — Phase 0: Corpus de Filosofía, Axiomas y Estándares
  * `URD` — Phase 1: User Requirements Document
  * `SRD` — Phase 2: Software Requirements Document
  * `ADD` — Phase 3: Architectural Design Document
  * `DDD` — Phase 4: Detailed Design Document
* **Documento de Visión Narrativa (`VISION`):** Marco conceptual continuo pre-fase 0 integrado junto a especificaciones atómicas.
* **Cero Dependencias Externas (POSIX / Std Lib):** Desarrollado en Python puro utilizando únicamente su biblioteca estándar y scripts Shell POSIX (`mos.sh`), permitiendo ejecución en entornos *air-gapped*.
* **Herencia DAG Flexible y Condicional (`mandatory: true/false`):** Soporte para herencia de proyectos mandatoria o condicional por referencia (ideal para proyectos bibliográficos o de estándares).
* **Flujo FIFO de Gobernanza IA (`data/ai-proposals/`):** Los agentes de IA generan propuestas atómicas independientes sin alterar directamente la base de código. El operador humano revisa y aprueba cada cambio manualmente.
* **Evaluación Doctrinal y de Fuentes:**
  * **MetsuOS Knowledge Level:** Clasificación formal en 6 niveles de sabiduría/conocimiento (`⚫① Dark1` a `⚪⑥ Light6`).
  * **Matriz OTAN (STANAG 2015):** Evaluación alfanumérica de fiabilidad de la fuente y credibilidad de la información.
* **Compilación Multicanal:** Generación automática de documentos consolidados en `doc/` y un Vault hipervinculado navegable en **Obsidian** (`vault/` e `INDEX.md`).

---

## 📂 Estructura del Repositorio

```text
.
├── data/
│   ├── ai-proposals/     # Bandeja de entrada FIFO para propuestas de agentes IA
│   ├── projects/         # Directorio de proyectos y especificaciones JSON
│   └── templates/        # Plantillas Markdown globales para compilación
├── doc/                  # Entregables consolidados de documentación
├── mom-py/               # Motor principal en Python
│   ├── cli.py            # Interfaz interactiva CLI / TUI
│   ├── compiler.py       # Compilador de entregables ESA y Vault
│   ├── projects.py       # Gestión de proyectos, herencia DAG y Privacy Sync
│   ├── schemas.py        # Modelos de datos, enumerados e identificadores
│   └── mos.sh            # Script de entrada principal
└── vault/                # Notas atómicas e índice para Obsidian