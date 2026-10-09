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
            "Relato solo de la ventana actual (estas 24 h). Cada entidad de la API va como {uid/nombre} "
            "(asesor nickname, contacto preferred_name o first_name, número name o phone). "
            "Ejemplo: cliente más reciente de {uid/rgomez} es {uid/Ana Ortiz}, alta 2026-07-05. "
            "Si la ventana ya trae el token, reutiliza el uid. No inventes uids. "
            "No copies la ventana cerrada; incorpora la ventana actual."
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
