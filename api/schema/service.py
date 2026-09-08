from typing import Annotated, List

import strawberry


@strawberry.type
class Service:
    id: int
    name: str
    description: str

    @strawberry.field
    def appointments(
        self,
    ) -> List[Annotated["Appointment", strawberry.lazy("api.schema.appointments")]]:
        from api.managers.appointment_manager import AppointmentManager

        print(f"[API] Service.appointments service_id={self.id}")
        items = AppointmentManager().get_by_service_id(self.id)
        print(f"[API] Service.appointments → {len(items)} resultados")
        return items
