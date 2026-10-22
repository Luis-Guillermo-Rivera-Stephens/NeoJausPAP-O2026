-- Historial completo del chat. ai_memory solo apunta al hilo; no guarda cada mensaje.
CREATE TABLE IF NOT EXISTS chats (
    uid       uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id uuid        NOT NULL REFERENCES clients (uid),
    cat       timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uat       timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    uid     uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
    chat_id uuid        NOT NULL REFERENCES chats (uid),
    role    varchar(16) NOT NULL CHECK (role IN ('user', 'assistant')),
    body    text        NOT NULL,
    cat     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_chat ON chat_messages (chat_id, cat);

ALTER TABLE ai_memory
    ADD COLUMN IF NOT EXISTS chat_id uuid REFERENCES chats (uid);
