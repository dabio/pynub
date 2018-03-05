--CREATE USER dev WITH PASSWORD '[your secret password]';
--GRANT dev TO root;
--CREATE DATABASE pinub_dev OWNER dev;
--REVOKE dev FROM root;
--DROP TABLE IF EXISTS users CASCADE;
CREATE TABLE IF NOT EXISTS users (
  "id" SERIAL PRIMARY KEY,
  "email" character varying (254) NOT NULL UNIQUE,
  "password" character varying (80),
  "created_at" timestamp (0) NOT NULL DEFAULT (now() at time zone 'utc')
);

--DROP TABLE IF EXISTS links CASCADE;
CREATE TABLE IF NOT EXISTS links (
  "id" SERIAL PRIMARY KEY,
  "url" character varying NOT NULL UNIQUE,
  "created_at" timestamp (0) NOT NULL DEFAULT (now() at time zone 'utc')
);

--DROP TABLE IF EXISTS user_links CASCADE;
CREATE TABLE IF NOT EXISTS user_links (
  "user_id" integer NOT NULL REFERENCES users ON DELETE CASCADE,
  "link_id" integer NOT NULL REFERENCES links ON DELETE CASCADE,
  "created_at" timestamp (0) NOT NULL DEFAULT (now() at time zone 'utc'),
  PRIMARY KEY ("user_id", "link_id")
);

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
--DROP TABLE IF EXISTS logins CASCADE;
CREATE TABLE IF NOT EXISTS logins (
    "user_id" integer NOT NULL REFERENCES users ON DELETE CASCADE,
    "token" UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    "active_at" timestamp (0) NOT NULL DEFAULT (now() at time zone 'utc'),
    "created_at" timestamp (0) NOT NULL DEFAULT (now() at time zone 'utc'),
    PRIMARY KEY ("user_id", "token")
);
