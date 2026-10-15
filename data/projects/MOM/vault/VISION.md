---
document_type: "VISION"
standard: "ESA PSS-05 Pre-Phase / MOM Framework"
project: "MOM (MetsuOS Methodology)"
version: "1.0.0"
date: "2026-10-15"
author: "Metsuke / Equipo de Arquitectura"
status: "APROBADO"
---

# MARCO CONCEPTUAL Y DOCUMENTO DE VISIÓN GENERAL (VISION)

## HOJA DE CONTROL DOCUMENTAL

### INFORMACIÓN GENERAL DEL PROYECTO
* **Nombre del Proyecto:** MOM (MetsuOS Methodology)
* **Código de Referencia:** MOM-COR-VISION-1.0
* **Entidad / Dominio:** MetsuOS Ecosystem
* **Estándar Metodológico Base:** ESA PSS-05 (Software Engineering Standards)
* **Versión Actual:** 1.0.0
* **Fecha de Emisión:** 15 de Octubre de 2026

---

### REGISTRO DE CAMBIOS Y HISTORIAL DE VERSIONES
| Versión | Descripción del Cambio | Autor / Rol | Fecha |
| :---: | :--- | :---: | :---: |
| **1.0.0** | Elaboración inicial del Documento de Visión Narrativa e Integración del Marco Doctrinal/Filosófico en MOM. | Metsuke (Arquitecto Principal) | 15/10/2026 |

---

### LISTA DE DISTRIBUCIÓN
* **Operadores del Sistema / Mantenedores Humanos**
* **Agentes de Inteligencia Artificial (AI Operators / Proposals Generators)**
* **Repositorio de Configuración Abierta de MOM**

---

## 1. INTRODUCCIÓN Y PROPÓSITO

### 1.1 Objetivo del Documento
El presente documento tiene como propósito establecer la **introducción general, el marco conceptual, las decisiones de soberanía y los fundamentos doctrinales** del sistema **MOM (MetsuOS Methodology)**.

A diferencia de las especificaciones atómicas estructuradas en formato JSON/Markdown individual (fases `COR`, `URD`, `SRD`, `ADD`, `DDD`), este documento ofrece una **redacción narrativa continua**, estructurada bajo la rigurosidad formal del estándar **ESA PSS-05**, sirviendo como puerta de entrada, onboarding contextual y justificación filosófica pre-fase 1.

### 1.2 Alcance del Marco Metodológico
MOM es un marco de desarrollo metodológico orientado a proyectos software y sistemas complejos que priorizan:
1. **Soberanía Tecnológica Absoluta:** Minimización o eliminación de dependencias de terceros, asegurando que la lógica principal repose en la biblioteca estándar del lenguaje motor o en estándares abiertos duraderos (HTML, JSON, Markdown).
2. **Trazabilidad Bi-direccional Estricta:** Vínculos DAG (Grafo Acíclico Dirigido) desde los principios filosóficos iniciales hasta las funciones de código y pruebas de integración.
3. **Control Humano e Interoperabilidad con IA:** Un entorno donde los agentes de IA generan propuestas atómicas, pero la validación, aprobación e integración final recaen exclusivamente en el operador humano bajo un flujo FIFO inmutable.

---

## 2. MARCO DOCTRINAL Y FILOSOFÍA DE SOBERANÍA (CORPUS)

### 2.1 Naturaleza del Documento COR y Pre-URD
En las metodologías de ingeniería de software convencionales, las decisiones filosóficas, los límites de soberanía y los estándares organizativos se tratan como documentación informal o guías flotantes. En MOM, siguiendo la distinción de la ESA entre *Capacidades* y *Restricciones*, estas reglas constituyen el **Nivel 0 (COR / Corpus)** del grafo de herencia.

El **Corpus de Filosofía y Estándares (COR)** condiciona:
* **El Requisito de Usuario (URD):** Ningún usuario puede exigir una funcionalidad que viole un axioma de soberanía.
* **El Requisito de Software (SRD):** Las bibliotecas y arquitecturas elegidas deben responder a la política de autosuficiencia.
* **El Diseño de Arquitectura (ADD) y Detallado (DDD):** Los diagramas y flujos deben ser interpretables por herramientas estándar de texto plano sin formatos propietarios.

### 2.2 Principios Axiomáticos Fundamentales
1. **Inmutabilidad de la Fuente de Verdad:** El estado primario del proyecto reside exclusivamente en archivos de texto plano rastreados por Git (`data/projects/<proyecto>/`).
2. **Aislamiento por Herencia:** La lógica de un motor informático (ej. `mom-py`, `mom-c`, `mom-js`) no debe alterar las plantillas globales o agnósticas ni romper la independencia de otros proyectos.
3. **Sincronización Transparente de Privacidad:** Los proyectos privados se protegen a nivel de sistema mediante reglas dinámicas generadas en `.gitignore`, impidiendo filtraciones involuntarias en repositorios públicos.

---

## 3. ESTRUCTURA Y CICLO DE VIDA EN ESA PSS-05 / MOM

El ciclo de vida en MOM sigue una progresión formal de 5 fases interconectadas:

$$\text{COR (Corpus)} \longrightarrow \text{URD (User Requirements)} \longrightarrow \text{SRD (Software Requirements)} \longrightarrow \text{ADD (Architectural Design)} \longrightarrow \text{DDD (Detailed Design)}$$

### 3.1 Descripción Narrativa de las Fases

#### Fase 0: COR (Corpus de Filosofía, Axiomas y Estándares)
* **Propósito:** Definir los marcos éticos, tecnológicos, legales y de soberanía del proyecto.
* **Carácter:** Raíz inmutable del grafo de herencia.

#### Fase 1: URD (User Requirements Document)
* **Propósito:** Especificar las necesidades operativas del usuario final o del cliente.
* **Carácter:** Define qué debe hacer el sistema desde una perspectiva funcional y operativa, vinculándose formalmente a los axiomas `COR`.

#### Fase 2: SRD (Software Requirements Document)
* **Propósito:** Traducir los `URD` a requisitos técnicos verificables de software.
* **Carácter:** Define las interfaces, formatos de datos, límites de memoria y métodos de verificación (`TEST`, `INSPECTION`, `ANALYSIS`, `DEMONSTRATION`).

#### Fase 3: ADD (Architectural Design Document)
* **Propósito:** Definir la estructura modular de alto nivel, la descomposición en subsistemas y la estrategia de persistencia/red.
* **Carácter:** Mapea la transformación de `SRD` a módulos arquitectónicos concretos.

#### Fase 4: DDD (Detailed Design Document)
* **Propósito:** Especificar las estructuras de datos exactas, algoritmos, firmas de funciones y modelos de clases/ficheros.
* **Carácter:** Base directa para la codificación y compilación.

---

## 4. GOBERNANZA Y MODO DE TRABAJO CON INTELIGENCIA ARTIFICIAL

MOM establece una separación clara de roles para prevenir el descontrol de código o especificaciones generadas automáticamente:

1. **Agentes de IA (Proposers):** Leen el contexto del proyecto (`AGENTS.md`, notas del `vault/` de Obsidian y especificaciones consolidadas) y generan propuestas atómicas estructuradas en `data/ai-proposals/`.
2. **Operador Humano (Approver):** Ejecuta la herramienta de gestión CLI (`mos.sh`), revisa las propuestas en orden estricto de llegada (FIFO), evalúa los *AI Guardrails* y decide su integración o descarte final.

---

## 5. CONCLUSIÓN Y CONTINUIDAD OPERATIVA

Este documento constituye la piedra angular narrativa del ecosistema MOM. Toda iteración futura sobre el código de los motores (`mom-py`, `mom-c`, `mom-js`) o sobre los proyectos creados dentro de la estructura `data/projects/` deberá tomar esta visión como el marco doctrinal predeterminado.