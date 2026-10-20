# Visión y Doctrina: MOSAUTHOR (Global Author & Bibliographic Corpus Standard)

> **Proclamación Doctrinal:** MOSAUTHOR es el pilar raíz de la rama bibliográfica y epistemológica de MetsuOS. Define la arquitectura de almacenamiento, despiece atómico y evaluación de confiabilidad para todo el corpus de fuentes, autores y obras de referencia que sostienen o refutan la metodología y las especificaciones del sistema.

---

## 🏛️ Principios Doctrinales y Metodológicos

### 1. Herencia No Mandatoria y Enlace Implícito (Lazy Reference)
* **Inyección Transparente:** Todos los proyectos del ecosistema MetsuOS heredan de forma implícita y no mandatoria de `MOSAUTHOR` y sus derivados, sin necesidad de declarar formalmente la herencia en su `project.json`.
* **Resolución por Referencia Activa:** Un proyecto de desarrollo o especificación técnica solo extraerá e incluirá en su compilación los nodos bibliográficos que cite explícitamente (`parent_ids` / referencias de soporte), junto con su cadena ascendente estricta (Frase → Párrafo → Página → Capítulo → Obra → Autor). Los miles de nodos no citados del catálogo bibliográfico permanecen aislados para no contaminar la documentación del proyecto.

---

### 2. Mapeo Semántico de Fases ESA para Bibliografía
Para mantener la homogeneidad con el esquema de 5 fases ESA de MetsuOS sin alterar la estructura del compilador, se establece la siguiente equivalencia semántica de granularidad para la rama `AUTHOR-*`:

* **`COR` (Core / Visión):** Obra Completa, Corpus Global o Tesis Central (`AUTHOR-<Autor>-<Obra>`).
* **`URD` (User Requirements):** Capítulos, Partes o Secciones Principales de la obra.
* **`SRD` (System Requirements):** Páginas, Subsecciones o Pasajes concretos.
* **`ADD` (Architectural Design):** Párrafos o Argumentos Estructurados.
* **`DDD` (Detailed Design):** Frases Atómicas, Citas Textuales Directas o Proposiciones de Referencia.

---

### 3. Red de Evaluación Epistemológica Ponderada (`MOSCON` / `MOSNATO`)
* **Evaluación Local de Atómicos:** Cada nodo atómico (cita/frase) cuenta con su evaluación individual de confiabilidad de la fuente (A-F) y credibilidad de la información (1-6) según el estándar OTAN (`MOSNATO`) y el nivel de conocimiento (`MOSCON`).
* **Propagación Ascendente:** El valor de fiabilidad de una Obra (`COR`) o Autor (`AUTHOR-<Nombre>`) se computa mediante el agregado ponderado (media, mediana o límite de seguridad) de sus proposiciones atómicas.
* **Cálculo de Soporte y Contrapunto Cruzado:** Los requisitos de software o componentes de MetsuOS pueden vincularse con aristas de **soporte (+1)** o **refutación (-1)** desde múltiples frases en diversas obras. La fiabilidad neta del componente técnico se calcula automáticamente en función de la credibilidad de la evidencia bibliográfica a favor y en contra.

---

### 4. Estructura Topológica Invertida
La rama bibliográfica se organiza en vaults especializados con la siguiente jerarquía de proyectos:
1. `MOSAUTHOR` (Nodo Raíz Global)
2. `AUTHOR-<NombreAutor>` (Ejemplo: `AUTHOR-Platon`, `AUTHOR-W3C`)
3. `AUTHOR-<NombreAutor>-<Obra>` (Ejemplo: `AUTHOR-W3C-WCAG22`, `AUTHOR-Platon-LaRepublica`)

---