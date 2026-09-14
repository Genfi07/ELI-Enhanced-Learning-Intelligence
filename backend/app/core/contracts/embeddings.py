from typing import Protocol


class EmbeddingsProvider(Protocol):
    """Convierte texto a vectores para búsqueda semántica.

    El contrato es mínimo: todo lo que ELI necesita es embedder un texto
    o un batch de textos. Cualquier proveedor (OpenAI, Cohere, local)
    puede implementarlo sin que el resto del sistema cambie.
    """

    name: str
    dimension: int

    async def embed(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...