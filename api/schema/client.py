from typing import Annotated, List

import strawberry


@strawberry.type
class Client:
    id: int
    name: str
    email: str
    phone: str

    @strawberry.field
    def appointments(
        self,
    ) -> List[Annotated["Appointment", strawberry.lazy("api.schema.appointments")]]:
        from api.managers.appointment_manager import AppointmentManager

        print(f"[API] Client.appointments client_id={self.id}")
        items = AppointmentManager().get_by_client_id(self.id)
        print(f"[API] Client.appointments → {len(items)} resultados")
        return items
