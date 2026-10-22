from pydantic import BaseModel, Field


class AiResponse(BaseModel):
    response: str = Field(
        description=(
            "Mensaje que ve el usuario, en Markdown. No escribas la gráfica: el server pinta el dashboard. "
            "Solo la respuesta, sin la memoria ni metadatos."
        )
    )
    new_summary: str = Field(
        description=(
            "Relato del hilo del chat en esta ventana, no una lista de datos: qué se preguntó y qué se respondió, en orden. "
            "Conserva la ventana actual y añade lo nuevo; no la reduzcas al último hecho. "
            "Cada asesor, contacto, número o conversación de la API va como {uid-real/nombre} dentro de la frase. "
            "Incorrecto: 'el cliente de rgomez es Ana Ortiz'. "
            "Correcto: 'preguntó el más reciente de {c0000000-0000-4000-8000-000000000001/rgomez}: {a1b2c3d4-0000-4000-8000-000000000010/Ana Ortiz}, alta 2026-07-05'. "
            "No inventes un uid. Si el token ya está, reutilízalo. No copies la ventana cerrada."
        )
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Vacío si las herramientas respondieron bien.",
    )
    title: str | None = Field(
        default=None,
        description=(
            "Solo si el prompt dice que el chat es nuevo: título de 3 a 6 palabras "
            "en español, sin comillas ni punto. Si el chat ya existe, null."
        ),
    )
