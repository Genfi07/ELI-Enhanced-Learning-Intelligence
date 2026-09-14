"""Ejemplos etiquetados para el clasificador semántico.

Cada ruta (FAST / STANDARD / DEEP) tiene un conjunto de frases representativas.
El clasificador embebe estas frases una vez y luego mide similitud coseno contra
el mensaje del usuario. La ruta del ejemplo más cercano (o voto mayoritario de
los K más cercanos) gana.

Reglas para añadir ejemplos:
  - Deben ser FRASES REALES, no descripciones meta.
  - Cubrir variedad: sinónimos, distintos tonos, distintas longitudes.
  - Máximo ~15 por ruta para mantener el coste bajo.
  - Si dos ejemplos son casi idénticos, uno sobra.
"""

FAST_EXAMPLES: list[str] = [
    "¿Cuánto es 25 por 4?",
    "Hola",
    "¿Qué hora es?",
    "Dime un chiste corto",
    "Traduce 'hola' al inglés",
    "¿Cuál es la capital de Francia?",
    "Convierte 100 dólares a euros",
    "Buenos días",
    "Gracias",
    "¿Quién escribió el Quijote?",
    "Dame un número aleatorio del 1 al 10",
    "¿Cuántos días tiene un año?",
]

STANDARD_EXAMPLES: list[str] = [
    "Como te dije antes, prefiero explicaciones paso a paso",
    "Recuérdame qué proyectos tengo pendientes",
    "Según el documento que subí, resume los puntos clave",
    "¿Qué sabes de mí?",
    "¿Puedes explicarme esto con el estilo que te pedí?",
    "Como comentamos la última vez, sigo con lo mismo",
    "Resume el archivo PDF que te compartí",
    "Prefiero respuestas en español neutro",
    "¿Qué me habías dicho sobre este tema?",
    "Basándote en lo que sabes de mí, ¿qué me recomiendas?",
    "Ayúdame a entender esto aplicando mi contexto",
    "Teniendo en cuenta mis preferencias, ¿qué opción me conviene?",
]

DEEP_EXAMPLES: list[str] = [
    "Analiza mi proyecto y dime cómo convertirlo en una plataforma comercial",
    "Diseña la arquitectura de un sistema de inventario para mi empresa",
    "Planifica los pasos para lanzar un producto al mercado",
    "Compara estas tres opciones y recomiéndame la mejor con justificación",
    "Refactoriza este código y explica qué cambios haces y por qué",
    "Diseña un plan de estudio de 3 meses para aprender machine learning",
    "Construye un roadmap técnico para escalar esta aplicación",
    "Implementa una estrategia completa de marketing digital para una startup",
    "Ayúdame a depurar esta funcionalidad compleja paso a paso",
    "Evalúa los riesgos de esta decisión estratégica y sugiere mitigaciones",
    "Divide este problema complejo en subproblemas manejables",
    "Arquitectura de microservicios para un sistema de pagos con alta disponibilidad",
]

EXAMPLES_BY_ROUTE: dict[str, list[str]] = {
    "FAST": FAST_EXAMPLES,
    "STANDARD": STANDARD_EXAMPLES,
    "DEEP": DEEP_EXAMPLES,
}