CREATE TABLE IF NOT EXISTS ai_memory (
    uid         uuid        NOT NULL DEFAULT uuid_generate_v4(),
    client_id   uuid        NOT NULL,
    window_from timestamptz NOT NULL,
    window_to   timestamptz NOT NULL,
    summary     text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (uid),
    FOREIGN KEY (client_id) REFERENCES clients (uid)
);
