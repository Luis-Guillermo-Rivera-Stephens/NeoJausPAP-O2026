-- =============================================================================
-- PAP - Esquema reducido (version didactica del RDS de produccion)
-- =============================================================================
-- Los nombres de tabla y de columna son los REALES de produccion. Lo unico que
-- se recorto es la CANTIDAD: 7 tablas en vez de 151, y en crm_clients 24
-- columnas en vez de 64. Una query escrita aqui corre casi igual alla.
--
-- Convencion de la casa (importante, no es la habitual):
--   uid  -> PK uuid
--   cat  -> created at   <- el timestamp de un mensaje es este
--   uat  -> updated at
-- En el esquema real NO existe created_at ni sent_at. Para "la semana pasada"
-- se usa `cat`. Todos los timestamps son timestamptz, como en produccion.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- --- Enums -------------------------------------------------------------------
-- Produccion tiene 53 tipos enum; aqui sobreviven 4, con sus valores EXACTOS.
-- Se descartaron los de domicilio (mexican_states son 32 valores) porque no
-- aportan nada a la analitica de WhatsApp.

CREATE TYPE crm_client_status_v1 AS ENUM (
    'new', 'contacted', 'active', 'closed', 'lost', 'inactive', 'archived');

CREATE TYPE crm_client_types_v1 AS ENUM (
    'buyer', 'seller', 'renter', 'landlord', 'investor', 'developer', 'other', 'agent');

CREATE TYPE preferred_contact_methods_v1 AS ENUM ('email', 'phone', 'whatsapp');

CREATE TYPE lost_reasons_v1 AS ENUM (
    'price', 'financing', 'no_answer', 'competitor', 'not_interested', 'other');


-- --- real_state_agencies -----------------------------------------------------
-- El tenant. Cada agencia tiene su zona horaria: un corte de "semana" correcto
-- se hace en la hora local de la agencia, no en UTC crudo.
CREATE TABLE real_state_agencies (
    cat       timestamptz   DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uat       timestamptz   DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uid       uuid          DEFAULT uuid_generate_v4() NOT NULL,
    name      varchar(128)  NOT NULL,
    timezone  varchar(64)   DEFAULT 'America/Mexico_City' NOT NULL,
    is_active boolean       DEFAULT true NOT NULL,
    CONSTRAINT real_state_agencies_pkey PRIMARY KEY (uid)
);


-- --- clients -----------------------------------------------------------------
-- OJO: estos son los USUARIOS DE LA PLATAFORMA (los asesores que contestan),
-- NO los contactos que escriben por WhatsApp. Esos viven en crm_clients.
CREATE TABLE clients (
    cat             timestamptz  DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uat             timestamptz  DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uid             uuid         DEFAULT uuid_generate_v4() NOT NULL,
    nickname        varchar(128) NOT NULL,
    first_name      varchar(32),
    first_last_name varchar(32),
    email           varchar(254),
    phone_number    varchar(10),
    agency_id       uuid         REFERENCES real_state_agencies (uid),
    CONSTRAINT clients_pkey PRIMARY KEY (uid)
);


-- --- crm_clients -------------------------------------------------------------
-- El contacto / lead del CRM. ESTE es "el usuario" que escribe por WhatsApp.
-- Se llega a el desde whatsapp_conversation.client_id.
CREATE TABLE crm_clients (
    cat                      timestamptz  DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uat                      timestamptz  DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uid                      uuid         DEFAULT uuid_generate_v4() NOT NULL,
    created_by               uuid         NOT NULL,
    assigned_to              uuid         NOT NULL,
    agency_id                uuid         NOT NULL,
    first_name               varchar(64)  NOT NULL,
    first_last_name          varchar(32),
    preferred_name           varchar(64),
    primary_email            varchar(254),
    primary_phone            varchar(14),
    phone_country_code       varchar(4)   DEFAULT '52' NOT NULL,
    preferred_contact_method preferred_contact_methods_v1,
    client_status            crm_client_status_v1 DEFAULT 'new',
    client_type              crm_client_types_v1,
    lead_source              varchar(254),
    tags                     text[],
    comments                 varchar(2048),
    is_deleted               boolean      DEFAULT false NOT NULL,
    -- Identidad de WhatsApp: asi un webhook entrante resuelve un telefono a un contacto.
    wa_id                    varchar(32),
    wa_profile_name          varchar(128),
    is_lost                  boolean      DEFAULT false NOT NULL,
    lost_reason              lost_reasons_v1,
    lost_at                  timestamptz,
    CONSTRAINT crm_clients_pkey PRIMARY KEY (uid),
    CONSTRAINT crm_clients_agency_id_fkey   FOREIGN KEY (agency_id)   REFERENCES real_state_agencies(uid),
    CONSTRAINT crm_clients_created_by_fkey  FOREIGN KEY (created_by)  REFERENCES clients(uid),
    CONSTRAINT crm_clients_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES clients(uid)
);


-- --- whatsapp_connection -----------------------------------------------------
-- "MI NUMERO": el numero de WhatsApp Business de la agencia.
-- En produccion esta tabla guarda ademas access_token_encrypted (bytea). Aqui NO
-- existe a proposito: es un secreto real y no tiene por que vivir en una base de practica.
CREATE TABLE whatsapp_connection (
    cat             timestamptz  DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uat             timestamptz  DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uid             uuid         DEFAULT uuid_generate_v4() NOT NULL,
    agency_id       uuid         NOT NULL,
    waba_id         varchar(64)  NOT NULL,
    phone_number_id varchar(64)  NOT NULL,
    display_phone   varchar(20),
    phone_e164      varchar(20),
    name            varchar(60),
    is_active       boolean      DEFAULT true NOT NULL,
    status          varchar(16)  DEFAULT 'connected' NOT NULL,
    CONSTRAINT whatsapp_connection_pkey PRIMARY KEY (uid),
    CONSTRAINT whatsapp_connection_agency_id_fkey FOREIGN KEY (agency_id) REFERENCES real_state_agencies(uid),
    CONSTRAINT whatsapp_connection_status_check CHECK (
        status IN ('connected','recovering','disconnected','limited','paused','replaced'))
);


-- --- whatsapp_conversation ---------------------------------------------------
-- Une un numero (connection) con un contacto (crm_clients). Tabla completa, sin recortes.
--
-- !! client_id apunta a crm_clients(uid), NO a clients(uid). Es el error mas facil
-- !! de cometer en este esquema, y no falla: devuelve resultados incorrectos en silencio.
CREATE TABLE whatsapp_conversation (
    cat                   timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uid                   uuid        DEFAULT uuid_generate_v4() NOT NULL,
    agency_id             uuid        NOT NULL,
    connection_id         uuid        NOT NULL,
    client_id             uuid        NOT NULL,
    conversation_category  varchar(16),
    window_expires_at     timestamptz,
    last_read_at          timestamptz,
    CONSTRAINT whatsapp_conversation_pkey PRIMARY KEY (uid),
    -- Un contacto tiene UNA conversacion por numero. Si escribe a dos numeros
    -- de la agencia, son dos filas.
    CONSTRAINT whatsapp_conversation_connection_id_client_id_key UNIQUE (connection_id, client_id),
    CONSTRAINT whatsapp_conversation_agency_id_fkey     FOREIGN KEY (agency_id)     REFERENCES real_state_agencies(uid),
    CONSTRAINT whatsapp_conversation_connection_id_fkey FOREIGN KEY (connection_id) REFERENCES whatsapp_connection(uid),
    CONSTRAINT whatsapp_conversation_client_id_fkey     FOREIGN KEY (client_id)     REFERENCES crm_clients(uid)
);


-- --- whatsapp_message --------------------------------------------------------
-- direction, message_type y m_status son varchar SIN CHECK, igual que en produccion:
-- alla se validan solo en el codigo de la aplicacion. Se replica tal cual para que
-- el comportamiento coincida. Valores validos:
--   direction    : 'inbound' | 'outbound'
--   message_type : 'text' | 'image' | 'audio' | 'document' | 'video' | 'location' | 'template'
--   m_status     : 'pending' | 'sent' | 'delivered' | 'read' | 'failed'
-- El texto del mensaje vive dentro de content (jsonb), en ->>'body'.
CREATE TABLE whatsapp_message (
    cat             timestamptz  DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uid             uuid         DEFAULT uuid_generate_v4() NOT NULL,
    conversation_id uuid         NOT NULL,
    connection_id   uuid         NOT NULL,
    wamid           varchar(128),
    direction       varchar(8)   NOT NULL,
    message_type    varchar(16),
    content         jsonb,
    m_status        varchar(16)  DEFAULT 'pending',
    error_code      varchar(16),
    sent_by         uuid,
    CONSTRAINT whatsapp_message_pkey PRIMARY KEY (uid),
    CONSTRAINT whatsapp_message_wamid_key UNIQUE (wamid),
    CONSTRAINT whatsapp_message_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES whatsapp_conversation(uid),
    CONSTRAINT whatsapp_message_connection_id_fkey   FOREIGN KEY (connection_id)   REFERENCES whatsapp_connection(uid),
    CONSTRAINT whatsapp_message_sent_by_fkey         FOREIGN KEY (sent_by)         REFERENCES clients(uid)
);


-- --- whatsapp_conversation_episode -------------------------------------------
-- Resumenes de conversacion generados por IA. No hace falta para las queries
-- basicas, pero es directamente util para un proyecto de agentes: en vez de leer
-- 200 mensajes, el agente lee el resumen.
CREATE TABLE whatsapp_conversation_episode (
    cat             timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uid             uuid        DEFAULT uuid_generate_v4() NOT NULL,
    conversation_id uuid        NOT NULL,
    window_from     timestamptz NOT NULL,
    window_to       timestamptz NOT NULL,
    summary         text        NOT NULL,
    key_topics      jsonb       DEFAULT '[]'::jsonb NOT NULL,
    model           varchar(64) NOT NULL,
    cost_usd_micros bigint      DEFAULT 0 NOT NULL,
    attributes      jsonb,
    CONSTRAINT whatsapp_conversation_episode_pkey PRIMARY KEY (uid),
    CONSTRAINT whatsapp_conversation_episode_window_key UNIQUE (conversation_id, window_to),
    CONSTRAINT whatsapp_conversation_episode_conversation_id_fkey
        FOREIGN KEY (conversation_id) REFERENCES whatsapp_conversation(uid) ON DELETE CASCADE
);


-- --- Indices -----------------------------------------------------------------
-- Copiados de produccion. Notese que NO hay indice suelto sobre whatsapp_message.cat:
-- un `WHERE cat > now() - interval '7 days'` sin acotar por conversacion o conexion
-- es un seq scan, tambien alla. Compruebenlo con EXPLAIN ANALYZE.

CREATE INDEX idx_message_conversation ON whatsapp_message (conversation_id, cat);
CREATE INDEX idx_message_connection   ON whatsapp_message (connection_id, cat);
CREATE INDEX idx_message_wamid        ON whatsapp_message (wamid);
CREATE INDEX idx_message_conversation_outbound
    ON whatsapp_message (conversation_id, cat DESC) WHERE direction = 'outbound';
CREATE INDEX idx_wa_unread_lookup
    ON whatsapp_message (conversation_id, direction, m_status)
    WHERE direction = 'inbound' AND m_status <> 'read';
-- Indice parcial de expresion: solo mensajes que llevan texto legible.
CREATE INDEX idx_message_conversation_text
    ON whatsapp_message (conversation_id, cat DESC, uid DESC)
    WHERE COALESCE(NULLIF(content ->> 'body', ''),
                   NULLIF(content ->> 'caption', ''),
                   NULLIF(content ->> 'transcription', '')) IS NOT NULL;

CREATE INDEX idx_conversation_client     ON whatsapp_conversation (client_id);
CREATE INDEX idx_conversation_connection ON whatsapp_conversation (connection_id);
CREATE INDEX idx_conversation_agency     ON whatsapp_conversation (agency_id);
CREATE INDEX idx_wa_conv_client_agency   ON whatsapp_conversation (client_id, agency_id);

CREATE UNIQUE INDEX idx_crm_clients_wa ON crm_clients (agency_id, wa_id) WHERE wa_id IS NOT NULL;
CREATE INDEX idx_crm_clients_phone_lookup
    ON crm_clients (phone_country_code, primary_phone, is_deleted, assigned_to) WHERE is_deleted = false;
CREATE INDEX idx_crm_clients_lost ON crm_clients (lost_at DESC) WHERE is_lost = true;

CREATE UNIQUE INDEX whatsapp_connection_active_phone_number_id_key
    ON whatsapp_connection (phone_number_id) WHERE is_active;
CREATE INDEX idx_connection_agency ON whatsapp_connection (agency_id, is_active);

CREATE INDEX idx_conversation_episode_latest
    ON whatsapp_conversation_episode (conversation_id, window_to DESC);
