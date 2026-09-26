from pydantic import BaseModel, Field


class AiResponse(BaseModel):
    response: str = Field(
        description="Mensaje que ve el usuario. Solo la respuesta, sin la memoria ni metadatos."
    )
    new_summary: str = Field(
        description=(
            "Relato solo de la ventana actual (estas 24 h): preguntas, respuestas y hechos "
            "(nombres, uids, estatus, cifras, temas). No copies la ventana cerrada; "
            "incorpora lo que ya decía la ventana actual."
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
