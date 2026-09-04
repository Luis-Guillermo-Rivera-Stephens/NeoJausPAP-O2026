from datetime import datetime
from typing import Annotated, Optional

import strawberry


@strawberry.type
class Appointment:
    id: strawberry.ID
    fecha_hora: datetime
    cliente_id: strawberry.Private[int]
    servicio_id: strawberry.Private[int]

    @strawberry.field
    def cliente(self) -> Annotated["Client", strawberry.lazy("api.schema.client")]:
        from api.managers.client_manager import ClientManager

        print(f"[API] Appointment.cliente appointment_id={self.id} cliente_id={self.cliente_id}")
        return ClientManager().get_client_by_id(self.cliente_id)

    @strawberry.field
    def servicio(self) -> Annotated["Service", strawberry.lazy("api.schema.service")]:
        from api.managers.service_manager import ServiceManager

        print(f"[API] Appointment.servicio appointment_id={self.id} servicio_id={self.servicio_id}")
        return ServiceManager().get_service_by_id(self.servicio_id)
