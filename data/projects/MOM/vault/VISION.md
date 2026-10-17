---
document_type: "VISION"
standard: "ESA PSS-05 Pre-Phase / MOM Framework"
project: "MOM (MetsuOS Methodology)"
version: "1.0.0"
date: "2026-10-15"
author: "Metsuke / Equipo de Arquitectura"
status: "APROBADO"
---
---
document_type: "VISION"
standard: "ESA PSS-05 Pre-Phase / MOM Framework"
project: "MOM (MetsuOS Methodology)"
version: "1.1.0"
date: "2026-10-17"
author: "Metsuke / Equipo de Arquitectura"
status: "APROBADO"
---

# MARCO CONCEPTUAL Y DOCUMENTO DE VISIÓN GENERAL (VISION)

## HOJA DE CONTROL DOCUMENTAL

### INFORMACIÓN GENERAL DEL PROYECTO
* **Nombre del Proyecto:** MOM (MetsuOS Methodology)[cite: 2]
* **Código de Referencia:** MOM-COR-VISION-1.1
* **Entidad / Dominio:** MetsuOS Ecosystem[cite: 2]
* **Estándar Metodológico Base:** ESA PSS-05 (Software Engineering Standards)[cite: 2]
* **Versión Actual:** 1.1.0
* **Fecha de Emisión:** 17 de Octubre de 2026

---

### REGISTRO DE CAMBIOS Y HISTORIAL DE VERSIONES
| Versión | Descripción del Cambio | Autor / Rol | Fecha |
| :---: | :--- | :---: | :---: |
| **1.0.0** | Elaboración inicial del Documento de Visión Narrativa e Integración del Marco Doctrinal/Filosófico en MOM.[cite: 2] | Metsuke (Arquitecto Principal)[cite: 2] | 15/10/2026[cite: 2] |
| **1.1.0** | Integración del Núcleo `MOSCON`, Auditoría de Fuentes `AUTHOR`, Estándar `MOSNATO`, Álgebra Probabilística `MOSPSH` y Resolución Compleja de Problemas `MOSCPS`. | Metsuke (Arquitecto Principal) | 17/10/2026 |

---

### LISTA DE DISTRIBUCIÓN
* **Operadores del Sistema / Mantenedores Humanos**[cite: 2]
* **Agentes de Inteligencia Artificial (AI Operators / Proposals Generators)**[cite: 2]
* **Repositorio de Configuración Abierta de MOM**[cite: 2]

---

## 1. INTRODUCCIÓN Y PROPÓSITO

### 1.1 Objetivo del Documento
El presente documento tiene como propósito establecer la **introducción general, el marco conceptual, las decisiones de soberanía y los fundamentos doctrinales** del sistema **MOM (MetsuOS Methodology)**[cite: 2].

A diferencia de las especificaciones atómicas estructuradas en formato JSON/Markdown individual (fases `COR`, `URD`, `SRD`, `ADD`, `DDD`)[cite: 2], este documento ofrece una **redacción narrativa continua**, estructurada bajo la rigurosidad formal del estándar **ESA PSS-05**[cite: 2], sirviendo como puerta de entrada, onboarding contextual y justificación filosófica pre-fase 1[cite: 2].

### 1.2 Alcance del Marco Metodológico
MOM es un marco de desarrollo metodológico orientado a proyectos de software y sistemas complejos[cite: 2] que prioriza:
1. **Soberanía Tecnológica Absoluta:** Minimización o eliminación de dependencias de terceros, asegurando que la lógica principal repose en la biblioteca estándar del lenguaje motor o en estándares abiertos duraderos (HTML, JSON, Markdown)[cite: 2].
2. **Trazabilidad Bi-direccional Estricta:** Vínculos DAG (Grafo Acíclico Dirigido) desde los principios filosóficos iniciales hasta las funciones de código y pruebas de integración[cite: 2].
3. **Control Humano e Interoperabilidad con IA:** Un entorno donde los agentes de IA generan propuestas atómicas, pero la validación, aprobación e integración final recaen exclusivamente en el operador humano bajo un flujo FIFO inmutable[cite: 2].

---

## 2. MARCO DOCTRINAL Y FILOSOFÍA DE SOBERANÍA (CORPUS - FASE 0)

### 2.1 Naturaleza del Documento COR y Pre-URD
En las metodologías de ingeniería de software convencionales, las decisiones filosóficas, los límites de soberanía y los estándares organizativos se tratan como documentación informal o guías flotantes[cite: 2]. En MOM, siguiendo la distinción de la ESA entre *Capacidades* y *Restricciones*[cite: 2], estas reglas constituyen el **Nivel 0 (COR / Corpus)** del grafo de herencia[cite: 2].

El **Corpus de Filosofía y Estándares (COR)** condiciona[cite: 2]:
* **El Requisito de Usuario (URD):** Ningún usuario puede exigir una funcionalidad que viole un axioma de soberanía[cite: 2].
* **El Requisito de Software (SRD):** Las bibliotecas y arquitecturas elegidas deben responder a la política de autosuficiencia[cite: 2].
* **El Diseño de Arquitectura (ADD) y Detallado (DDD):** Los diagramas y flujos deben ser interpretables por herramientas estándar de texto plano sin formatos propietarios[cite: 2].

### 2.2 Pilares Epistemológicos e Integración Metodológica

1. **`MOSCON` (MetsuOS Conocimiento - Núcleo y Norma Geopolítica):**
   * **Control de Dominio y Seguridad Antiabuso:** La base operativa primaria del sistema está definida obligatoriamente en **español de España (es-ES)** como salvaguarda geopolítica de control humano y peaje antiabuso.
   * **Dinámica Temporal y Obsolescencia Parametrizable ($\lambda$):** El conocimiento no es estático. Todo elemento atómico sufre obsolescencia parametrizable por proyecto. En la herencia DAG se aplica la **Regla de Máxima Obsolescencia**: el elemento hijo asume el ratio de degradación más exigente (más rápido en degradarse) entre sus padres.

2. **`AUTHOR` (Auditoría de Fuentes y Red Bibliográfica):**
   * **Regla de Filtrado 3/3:** Ninguna especificación atómica puede ser calificada por encima del nivel de ruido/no evaluable (`⚫① Dark1`) sin contar con al menos **3 fuentes independientes a favor y 3 en contra** mapeadas en la red bibliográfica de soporte/refutación.
   * **Principio del Eslabón más Débil:** La fiabilidad de un elemento atómico surge del cómputo combinado del eslabón más débil entre las fuentes que lo respaldan.

3. **`MOSNATO` (Adaptación del Estándar OTAN STANAG 2010 / AJP-2.1):**
   * **Matriz Bidimensional:** Evaluación de la **Fiabilidad de la Fuente (A–F)** y la **Credibilidad de la Información (1–6)**.
   * **Techo Estricto de Certidumbre (`🟢④ Green4`):** Ninguna evaluación OTAN por sí sola clasifica un elemento por encima de `Green4`. Los niveles `🔵⑤ Blue5` (demostración científica formal) y `⚪⑥ Light6` (axioma inmutable) se consideran inalcanzables bajo la implementación actual para evitar la contaminación por ego, consensos humanos, modas académicas o ideológicas.

4. **`MOSPSH` (MetsuOS Psicohistoria - Álgebra Probabilística):**
   * **Asíntota de Certeza:** La verdad absoluta ($100\%$) no existe. El rango de evaluación probabilística es estrictamente asintótico entre **$-99.99999\%$ y $+99.99999\%$**, expresado mediante niveles de confianza por sigmas ($\sigma$).
   * **Navaja de Ockham Dinámica:** La opción asumida como más probable es simplemente la hipótesis $P_{\max}$ del estado actual $S(t)$, con capacidad de conmutar automáticamente ante un nuevo vector de evidencia sin resistencia ideológica ni sesgo de persistencia.

5. **`MOSCPS` (MetsuOS Complex Problem Solving):**
   * **Desarticulación No Lineal:** Descomposición de problemas complejos mediante reglas de combate sistemáticas en la búsqueda de información, garantizando avances progresivos con nivel de error controlado.

---

## 3. ESTRUCTURA Y CICLO DE VIDA EN ESA PSS-05 / MOM

El ciclo de vida en MOM sigue una progresión formal de 5 fases interconectadas[cite: 2]:

$$\text{COR (Corpus)} \longrightarrow \text{URD (User Requirements)} \longrightarrow \text{SRD (Software Requirements)} \longrightarrow \text{ADD (Architectural Design)} \longrightarrow \text{DDD (Detailed Design)}$$
[cite: 2]

### 3.1 Descripción Narrativa de las Fases[cite: 2]

#### Fase 0: COR (Corpus de Filosofía, Axiomas y Estándares)[cite: 2]
* **Propósito:** Definir los marcos éticos, tecnológicos, legales, epistemológicos y de soberanía del proyecto[cite: 2].
* **Carácter:** Raíz inmutable del grafo de herencia[cite: 2].

#### Fase 1: URD (User Requirements Document)[cite: 2]
* **Propósito:** Especificar las necesidades operativas del usuario final o del cliente[cite: 2].
* **Carácter:** Define qué debe hacer el sistema desde una perspectiva funcional y operativa, vinculándose formalmente a los axiomas `COR`[cite: 2].

#### Fase 2: SRD (Software Requirements Document)[cite: 2]
* **Propósito:** Traducir los `URD` a requisitos técnicos verificables de software[cite: 2].
* **Carácter:** Define las interfaces, formatos de datos, límites de memoria y métodos de verificación (`TEST`, `INSPECTION`, `ANALYSIS`, `DEMONSTRATION`)[cite: 2].

#### Fase 3: ADD (Architectural Design Document)[cite: 2]
* **Propósito:** Definir la estructura modular de alto nivel, la descomposición en subsistemas y la estrategia de persistencia/red[cite: 2].
* **Carácter:** Mapea la transformación de `SRD` a módulos arquitectónicos concretos[cite: 2].

#### Fase 4: DDD (Detailed Design Document)[cite: 2]
* **Propósito:** Especificar las estructuras de datos exactas, algoritmos, firmas de funciones y modelos de clases/ficheros[cite: 2].
* **Carácter:** Base directa para la codificación y compilación[cite: 2].

---

## 4. GOBERNANZA Y MODO DE TRABAJO CON INTELIGENCIA ARTIFICIAL

MOM establece una separación clara de roles para prevenir el descontrol de código o especificaciones generadas automáticamente[cite: 2]:

1. **Agentes de IA (Proposers):** Leen el contexto del proyecto (`AGENTS.md`, notas del `vault/` de Obsidian y especificaciones consolidadas) y generan propuestas atómicas estructuradas en `data/ai-proposals/`[cite: 2].
2. **Operador Humano (Approver):** Ejecuta la herramienta de gestión CLI (`mos.sh`), revisa las propuestas en orden estricto de llegada (FIFO), evalúa los *AI Guardrails* e integra o descarta los elementos[cite: 2].

---

## 5. CONCLUSIÓN Y CONTINUIDAD OPERATIVA

Este documento constituye la piedra angular narrativa del ecosistema MOM[cite: 2]. Toda iteración sobre el código de los motores (`mom-py`, `mom-c`, `mom-js`) o sobre los proyectos creados dentro de la estructura `data/projects/` toma esta visión como el marco doctrinal predeterminado[cite: 2].