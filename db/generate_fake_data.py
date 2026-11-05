"""Append synthetic CRM and WhatsApp data to the local PAP database."""

import argparse
import os
import random
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from faker import Faker
from psycopg.types.json import Jsonb
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTACT_METHODS = ("email", "phone", "whatsapp")
CLIENT_STATUSES = ("new", "contacted", "active", "closed", "lost", "inactive", "archived")
CLIENT_TYPES = ("buyer", "seller", "renter", "landlord", "investor", "developer", "other", "agent")
LOST_REASONS = ("price", "financing", "no_answer", "competitor", "not_interested", "other")
CONVERSATION_CATEGORIES = ("marketing", "service", "utility", "referral")
# Cada camino contiene pares de mensajes relacionados y una conclusion propia.
# Las opciones dentro de una etapa son ramas completas, no respuestas aisladas.
CONVERSATION_TREES = (
    {
        "opening": (("inbound", "Hola, vi anunciada la Casa Jardines. ¿Sigue disponible?"),
                    ("outbound", "Hola, sí está disponible. ¿Te gustaría conocer el precio y la ubicación?"),
                    ("inbound", "Sí, por favor."),
                    ("outbound", "Está en la zona centro y el precio publicado es de $2,500,000.")),
        "branches": (
            {"messages": (("inbound", "Me interesa. ¿Podemos agendar una visita?"),
                          ("outbound", "Claro, ¿te acomoda el sábado a las 11 de la mañana?"),
                          ("inbound", "Sí, me queda bien."),
                          ("outbound", "Perfecto, queda agendada. Te enviaré la ubicación antes de la visita.")),
             "summary": "El contacto consultó disponibilidad y precio; acordó una visita el sábado.",
             "topics": ("casa jardines", "disponibilidad", "precio", "visita")},
            {"messages": (("inbound", "Está fuera de mi presupuesto. ¿Tienen opciones más económicas?"),
                          ("outbound", "Sí, puedo buscar alternativas. ¿Cuál es tu presupuesto máximo?"),
                          ("inbound", "Hasta $2,000,000."),
                          ("outbound", "Gracias, buscaré opciones dentro de ese presupuesto y te contactaré.")),
             "summary": "El contacto consultó el precio y solicitó alternativas dentro de su presupuesto.",
             "topics": ("casa jardines", "disponibilidad", "precio", "presupuesto", "seguimiento")},
        ),
    },
    {
        "opening": (("inbound", "Hola, me interesa comprar una casa. ¿Aceptan crédito hipotecario?"),
                    ("outbound", "Hola, sí. Trabajamos con crédito hipotecario. ¿Ya tienes una preaprobación?")),
        "branches": (
            {"messages": (("inbound", "Sí, ya tengo una preaprobación bancaria."),
                          ("outbound", "Excelente. ¿De cuánto es el monto autorizado?"),
                          ("inbound", "De hasta $2,000,000."),
                          ("outbound", "Perfecto, te compartiré propiedades compatibles con ese monto.")),
             "summary": "El contacto tiene un crédito preaprobado y recibirá opciones según su monto.",
             "topics": ("credito hipotecario", "presupuesto", "seguimiento")},
            {"messages": (("inbound", "Todavía no, apenas estoy investigando."),
                          ("outbound", "Podemos orientarte para iniciar la preaprobación. ¿Te comparto los requisitos?"),
                          ("inbound", "Sí, por favor."),
                          ("outbound", "Te enviaré la lista de documentos y los siguientes pasos.")),
             "summary": "El contacto busca orientación para obtener una preaprobación hipotecaria.",
             "topics": ("credito hipotecario", "requisitos", "seguimiento")},
        ),
    },
    {
        "opening": (("inbound", "Hola, busco un departamento en renta. ¿Tienen opciones?"),
                    ("outbound", "Hola, sí. ¿Qué presupuesto mensual tienes?"),
                    ("inbound", "Hasta $12,000 al mes."),
                    ("outbound", "Gracias. Tenemos opciones en ese rango. ¿Cuándo necesitas mudarte?")),
        "branches": (
            {"messages": (("inbound", "El próximo mes."),
                          ("outbound", "Bien, te enviaré las opciones disponibles para esa fecha."),
                          ("inbound", "Gracias, las reviso."),
                          ("outbound", "Con gusto. Si alguna te interesa, coordinamos una visita.")),
             "summary": "El contacto busca renta de hasta $12,000 y desea mudarse el próximo mes.",
             "topics": ("renta", "presupuesto", "seguimiento")},
            {"messages": (("inbound", "Aún no tengo fecha; solo estoy comparando."),
                          ("outbound", "Entendido, te compartiré algunas opciones para que las compares."),
                          ("inbound", "Perfecto, muchas gracias."),
                          ("outbound", "Con gusto, quedo pendiente si tienes preguntas.")),
             "summary": "El contacto compara departamentos en renta y todavía no tiene fecha de mudanza.",
             "topics": ("renta", "presupuesto", "seguimiento")},
        ),
    },
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Agrega contactos, conversaciones y mensajes ficticios a la base local."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=15,
        help="cantidad de contactos nuevos (default: 15)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="semilla para reproducir los datos generados (default: 2026)",
    )
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count debe ser mayor que cero.")
    return args


def get_local_connection():
    load_dotenv(PROJECT_ROOT / ".env")

    host = os.getenv("DB_HOST") or "localhost"
    port = int(os.getenv("DB_PORT") or "5433")
    if host.lower() not in ("localhost", "127.0.0.1", "::1") or port != 5433:
        raise ValueError(
            "Este generador solo se conecta a localhost:5433 para evitar modificar "
            "una base remota o el Postgres de trabajo."
        )

    return psycopg.connect(
        host=host,
        port=port,
        dbname=os.getenv("DB_NAME") or "papdb",
        user=os.getenv("DB_USER") or "pap",
        password=os.getenv("DB_PASSWORD") or "pap",
    )


def get_agency_options(cursor):
    cursor.execute(
        """
        SELECT a.uid, wc.uid, cl.uid
        FROM real_state_agencies AS a
        JOIN whatsapp_connection AS wc
          ON wc.agency_id = a.uid AND wc.is_active = true
        JOIN clients AS cl
          ON EXISTS (
              SELECT 1
              FROM crm_clients AS existing
              WHERE existing.agency_id = a.uid
                AND existing.assigned_to = cl.uid
          )
        WHERE a.is_active = true
        ORDER BY a.uid, wc.uid, cl.uid
        """
    )
    rows = cursor.fetchall()
    options = defaultdict(lambda: {"connections": set(), "agents": set()})
    for agency_id, connection_id, agent_id in rows:
        options[agency_id]["connections"].add(connection_id)
        options[agency_id]["agents"].add(agent_id)

    if not options:
        raise RuntimeError(
            "No hay agencias activas con un numero de WhatsApp activo y un asesor asignado. "
            "Inicializa la base con `docker compose up -d --wait` y vuelve a intentarlo."
        )
    return options


def make_unique_phone(rng, used_phones):
    prefixes = ("33", "55", "81", "664", "656")
    while True:
        prefix = rng.choice(prefixes)
        suffix = "".join(str(rng.randrange(10)) for _ in range(10 - len(prefix)))
        phone = prefix + suffix
        if phone not in used_phones:
            used_phones.add(phone)
            return phone


def make_contact(fake, rng, agency_id, agent_id, used_phones, used_wa_ids, index, now):
    first_name = fake.first_name()
    last_name = fake.last_name()[:32]
    phone = make_unique_phone(rng, used_phones)
    wa_id = f"52{phone}"
    while wa_id in used_wa_ids:
        phone = make_unique_phone(rng, used_phones)
        wa_id = f"52{phone}"
    used_wa_ids.add(wa_id)

    status = rng.choice(CLIENT_STATUSES)
    lost = status == "lost"
    created_at = now - timedelta(days=rng.randint(1, 180))
    return {
        "uid": uuid.uuid4(),
        "created_by": agent_id,
        "assigned_to": agent_id,
        "agency_id": agency_id,
        "first_name": first_name,
        "first_last_name": last_name,
        "preferred_name": first_name,
        "primary_email": f"contacto{index}.{uuid.uuid4().hex[:8]}@example.com",
        "primary_phone": phone,
        "phone_country_code": "52",
        "preferred_contact_method": rng.choice(CONTACT_METHODS),
        "client_status": status,
        "client_type": rng.choice(CLIENT_TYPES),
        "lead_source": rng.choice(
            ("facebook_ads", "portal_inmuebles24", "referido", "google", "whatsapp_directo")
        ),
        "tags": [rng.choice(("nuevo", "interesado", "seguimiento", "referido"))],
        "comments": "Contacto ficticio generado para pruebas.",
        "is_deleted": False,
        "wa_id": wa_id,
        "wa_profile_name": f"{first_name} {last_name}"[:128],
        "is_lost": lost,
        "lost_reason": rng.choice(LOST_REASONS) if lost else None,
        "lost_at": min(now, created_at + timedelta(days=rng.randint(1, 15))) if lost else None,
        "cat": created_at,
        "uat": created_at,
    }


def insert_contacts(cursor, contacts):
    cursor.executemany(
        """
        INSERT INTO crm_clients (
            uid, created_by, assigned_to, agency_id, first_name, first_last_name,
            preferred_name, primary_email, primary_phone, phone_country_code,
            preferred_contact_method, client_status, client_type, lead_source, tags,
            comments, is_deleted, wa_id, wa_profile_name, is_lost, lost_reason,
            lost_at, cat, uat
        ) VALUES (
            %(uid)s, %(created_by)s, %(assigned_to)s, %(agency_id)s, %(first_name)s,
            %(first_last_name)s, %(preferred_name)s, %(primary_email)s, %(primary_phone)s,
            %(phone_country_code)s, %(preferred_contact_method)s::preferred_contact_methods_v1,
            %(client_status)s::crm_client_status_v1, %(client_type)s::crm_client_types_v1,
            %(lead_source)s, %(tags)s, %(comments)s, %(is_deleted)s, %(wa_id)s,
            %(wa_profile_name)s, %(is_lost)s, %(lost_reason)s::lost_reasons_v1,
            %(lost_at)s, %(cat)s, %(uat)s
        )
        """,
        contacts,
    )


def make_conversation(contact, connection_id, rng, now):
    recent = rng.random() < 0.6
    days_ago = rng.randint(0, 6) if recent else rng.randint(8, 45)
    last_activity = now - timedelta(
        days=days_ago,
        hours=rng.randrange(24),
        minutes=rng.randrange(60),
    )
    tree = rng.choice(CONVERSATION_TREES)
    branch = rng.choice(tree["branches"])
    dialogue = tree["opening"] + branch["messages"]
    count = len(dialogue)
    conversation_id = uuid.uuid4()
    return {
        "uid": conversation_id,
        "agency_id": contact["agency_id"],
        "connection_id": connection_id,
        "client_id": contact["uid"],
        "conversation_category": rng.choice(CONVERSATION_CATEGORIES),
        "window_expires_at": (
            last_activity + timedelta(hours=24)
            if last_activity >= now - timedelta(hours=24)
            else None
        ),
        "last_read_at": last_activity - timedelta(minutes=rng.randrange(60)),
        "cat": last_activity - timedelta(hours=4 * (count - 1)),
        "last_activity": last_activity,
        "message_count": count,
        "dialogue": dialogue,
        "summary": branch["summary"],
        "topics": branch["topics"],
        "agent_id": contact["assigned_to"],
    }


def insert_conversations(cursor, conversations):
    cursor.executemany(
        """
        INSERT INTO whatsapp_conversation (
            uid, agency_id, connection_id, client_id, conversation_category,
            window_expires_at, last_read_at, cat
        ) VALUES (
            %(uid)s, %(agency_id)s, %(connection_id)s, %(client_id)s,
            %(conversation_category)s, %(window_expires_at)s, %(last_read_at)s, %(cat)s
        )
        """,
        conversations,
    )


def make_messages(conversations, rng):
    messages = []
    for conversation in conversations:
        for index, (direction, text) in enumerate(conversation["dialogue"]):
            message_type = "text"
            content = {"body": text}

            message_at = conversation["last_activity"]
            if index < conversation["message_count"] - 1:
                message_at -= timedelta(
                    hours=3 * (conversation["message_count"] - index - 1),
                    minutes=rng.randrange(60),
                )
            if direction == "inbound":
                status = rng.choice(("read", "read", "delivered"))
                sent_by = None
            else:
                status = rng.choice(("sent", "delivered", "read"))
                sent_by = conversation["agent_id"]

            messages.append(
                (
                    uuid.uuid4(),
                    conversation["uid"],
                    conversation["connection_id"],
                    f"wamid.fake.{uuid.uuid4().hex}",
                    direction,
                    message_type,
                    Jsonb(content),
                    status,
                    sent_by,
                    message_at,
                )
            )
    return messages


def insert_messages(cursor, messages):
    cursor.executemany(
        """
        INSERT INTO whatsapp_message (
            uid, conversation_id, connection_id, wamid, direction, message_type,
            content, m_status, sent_by, cat
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        messages,
    )


def make_episodes(conversations, rng):
    episodes = []
    for conversation in conversations:
        if rng.random() >= 0.2:
            continue
        window_to = conversation["last_activity"]
        episodes.append(
            (
                uuid.uuid4(),
                conversation["uid"],
                window_to - timedelta(days=3),
                window_to,
                conversation["summary"],
                "demo-faker",
                rng.randint(100, 3000),
                window_to,
            )
        )
    return episodes


def insert_episodes(cursor, episodes, conversations):
    topics = sorted({topic for conversation in conversations for topic in conversation["topics"]})
    cursor.executemany(
        """
        INSERT INTO whatsapp_key_topic (name) VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        """,
        [(name,) for name in topics],
    )
    cursor.executemany(
        """
        INSERT INTO whatsapp_conversation_episode (
            uid, conversation_id, window_from, window_to, summary,
            model, cost_usd_micros, cat
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        episodes,
    )
    topics_by_conversation = {conversation["uid"]: conversation["topics"] for conversation in conversations}
    links = [(episode[0], name) for episode in episodes for name in topics_by_conversation[episode[1]]]
    cursor.executemany(
        """
        INSERT INTO whatsapp_episode_topic (episode_id, topic_id)
        SELECT %s, uid FROM whatsapp_key_topic WHERE name = %s
        ON CONFLICT DO NOTHING
        """,
        links,
    )


def main():
    args = parse_args()
    rng = random.Random(args.seed)
    fake = Faker("es_MX")
    fake.seed_instance(args.seed)
    now = datetime.now(timezone.utc)

    with get_local_connection() as conn:
        with conn.cursor() as cursor:
            agency_options = get_agency_options(cursor)
            agency_ids = list(agency_options)
            cursor.execute(
                """
                SELECT agency_id, primary_phone, wa_id
                FROM crm_clients
                WHERE agency_id = ANY(%s)
                """,
                (agency_ids,),
            )
            used_phones = defaultdict(set)
            used_wa_ids = defaultdict(set)
            for agency_id, phone, wa_id in cursor.fetchall():
                if phone:
                    used_phones[agency_id].add(phone)
                if wa_id:
                    used_wa_ids[agency_id].add(wa_id)

            contacts = []
            conversations = []
            for index in range(1, args.count + 1):
                agency_id = rng.choice(agency_ids)
                options = agency_options[agency_id]
                agent_id = rng.choice(sorted(options["agents"], key=str))
                contact = make_contact(
                    fake,
                    rng,
                    agency_id,
                    agent_id,
                    used_phones[agency_id],
                    used_wa_ids[agency_id],
                    index,
                    now,
                )
                connection_id = rng.choice(sorted(options["connections"], key=str))
                contacts.append(contact)
                conversations.append(make_conversation(contact, connection_id, rng, now))

            messages = make_messages(conversations, rng)
            episodes = make_episodes(conversations, rng)

            insert_contacts(cursor, contacts)
            insert_conversations(cursor, conversations)
            insert_messages(cursor, messages)
            insert_episodes(cursor, episodes, conversations)

    print(
        f"Datos ficticios agregados: {len(contacts)} contactos, "
        f"{len(conversations)} conversaciones, {len(messages)} mensajes "
        f"y {len(episodes)} resumenes."
    )


if __name__ == "__main__":
    main()
