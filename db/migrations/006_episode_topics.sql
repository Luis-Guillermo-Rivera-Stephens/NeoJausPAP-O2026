-- Idempotente: parte key_topics jsonb en catálogo + entidad débil.
CREATE TABLE IF NOT EXISTS whatsapp_key_topic (
    cat  timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    uid  uuid        DEFAULT uuid_generate_v4() NOT NULL,
    name varchar(64) NOT NULL,
    CONSTRAINT whatsapp_key_topic_pkey PRIMARY KEY (uid),
    CONSTRAINT whatsapp_key_topic_name_key UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS whatsapp_episode_topic (
    episode_id uuid NOT NULL,
    topic_id   uuid NOT NULL,
    CONSTRAINT whatsapp_episode_topic_pkey PRIMARY KEY (episode_id, topic_id),
    CONSTRAINT whatsapp_episode_topic_episode_id_fkey
        FOREIGN KEY (episode_id) REFERENCES whatsapp_conversation_episode (uid) ON DELETE CASCADE,
    CONSTRAINT whatsapp_episode_topic_topic_id_fkey
        FOREIGN KEY (topic_id) REFERENCES whatsapp_key_topic (uid) ON DELETE CASCADE
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'whatsapp_conversation_episode'
          AND column_name = 'key_topics'
    ) THEN
        INSERT INTO whatsapp_key_topic (name)
        SELECT DISTINCT trim(value)
        FROM whatsapp_conversation_episode,
             jsonb_array_elements_text(key_topics) AS value
        WHERE trim(value) <> ''
        ON CONFLICT (name) DO NOTHING;

        INSERT INTO whatsapp_episode_topic (episode_id, topic_id)
        SELECT e.uid, t.uid
        FROM whatsapp_conversation_episode e,
             jsonb_array_elements_text(e.key_topics) AS value
        JOIN whatsapp_key_topic t ON t.name = trim(value)
        ON CONFLICT DO NOTHING;

        ALTER TABLE whatsapp_conversation_episode DROP COLUMN key_topics;
    END IF;
END $$;
