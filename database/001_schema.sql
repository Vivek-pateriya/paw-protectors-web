BEGIN;
CREATE TABLE IF NOT EXISTS schema_versions(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE users (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
 email text NOT NULL UNIQUE CHECK(email = lower(email)),
 password_hash text NOT NULL,
 role text NOT NULL DEFAULT 'owner' CHECK(role IN ('owner','vet','admin')),
 active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE revoked_sessions (
 token_hash text PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES users(id),
 revoked_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE pets (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 owner_id bigint NOT NULL REFERENCES users(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
 species text NOT NULL, breed text NOT NULL DEFAULT '',
 age_months integer NOT NULL DEFAULT 0 CHECK(age_months BETWEEN 0 AND 1200),
 gender text NOT NULL CHECK(gender IN ('male','female','unknown')),
 image_path text, medical_notes text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(id,owner_id)
);
CREATE TABLE veterinarians (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 user_id bigint NOT NULL UNIQUE REFERENCES users(id),
 specialization text NOT NULL DEFAULT 'General care',
 clinic text NOT NULL DEFAULT '', available boolean NOT NULL DEFAULT true
);
CREATE TABLE appointment_slots (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 veterinarian_id bigint NOT NULL REFERENCES veterinarians(id),
 starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL,
 CHECK(ends_at > starts_at), UNIQUE(veterinarian_id,starts_at)
);
CREATE TABLE appointments (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 slot_id bigint NOT NULL REFERENCES appointment_slots(id),
 pet_id bigint NOT NULL REFERENCES pets(id),
 owner_id bigint NOT NULL REFERENCES users(id),
 status text NOT NULL DEFAULT 'booked' CHECK(status IN ('booked','cancelled','completed')),
 reason text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
 ,FOREIGN KEY(pet_id,owner_id) REFERENCES pets(id,owner_id)
);
CREATE UNIQUE INDEX one_active_booking_per_slot ON appointments(slot_id) WHERE status IN ('booked','completed');
CREATE INDEX pets_owner_idx ON pets(owner_id);
CREATE INDEX appointments_owner_idx ON appointments(owner_id,created_at DESC);
CREATE INDEX slots_vet_time_idx ON appointment_slots(veterinarian_id,starts_at);
CREATE TABLE medical_records (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 pet_id bigint NOT NULL REFERENCES pets(id),
 veterinarian_id bigint NOT NULL REFERENCES veterinarians(id),
 diagnosis text NOT NULL, treatment text NOT NULL DEFAULT '',
 recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX medical_pet_idx ON medical_records(pet_id,recorded_at DESC);
CREATE TABLE vaccination_records (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 pet_id bigint NOT NULL REFERENCES pets(id), vaccine text NOT NULL,
 administered_on date NOT NULL, next_due date,
 CHECK(next_due IS NULL OR next_due >= administered_on)
);
CREATE INDEX vaccination_pet_idx ON vaccination_records(pet_id);
CREATE TABLE reminders (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 vaccination_id bigint NOT NULL UNIQUE REFERENCES vaccination_records(id) ON DELETE CASCADE,
 owner_id bigint NOT NULL REFERENCES users(id),
 due_at timestamptz NOT NULL, message text NOT NULL,
 acknowledged boolean NOT NULL DEFAULT false
);
CREATE INDEX reminders_owner_due_idx ON reminders(owner_id,due_at) WHERE NOT acknowledged;
CREATE TABLE audit_logs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 actor_id bigint REFERENCES users(id), entity text NOT NULL,
 entity_id bigint, action text NOT NULL, details jsonb NOT NULL DEFAULT '{}',
 transaction_id bigint NOT NULL DEFAULT txid_current(), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION audit_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE row_data jsonb; actor bigint;
BEGIN
 row_data := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
 actor := nullif(current_setting('app.actor_id',true),'')::bigint;
 INSERT INTO audit_logs(actor_id,entity,entity_id,action,details)
 VALUES(actor,TG_TABLE_NAME,(row_data->>'id')::bigint,TG_OP,row_data - 'password_hash');
 RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER appointments_audit AFTER INSERT OR UPDATE OR DELETE ON appointments FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER users_audit AFTER INSERT OR UPDATE ON users FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER pets_audit AFTER INSERT OR UPDATE OR DELETE ON pets FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE FUNCTION vaccination_reminder() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.next_due IS NULL THEN
   DELETE FROM reminders WHERE vaccination_id=NEW.id;
 ELSE
   INSERT INTO reminders(vaccination_id,owner_id,due_at,message)
   SELECT NEW.id,p.owner_id,NEW.next_due::timestamp AT TIME ZONE 'UTC',p.name || ': ' || NEW.vaccine || ' vaccination due'
   FROM pets p WHERE p.id=NEW.pet_id
   ON CONFLICT(vaccination_id) DO UPDATE SET due_at=EXCLUDED.due_at,message=EXCLUDED.message,acknowledged=false;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER vaccination_reminder_trigger AFTER INSERT OR UPDATE ON vaccination_records FOR EACH ROW EXECUTE FUNCTION vaccination_reminder();
CREATE FUNCTION book_appointment(p_slot bigint,p_pet bigint,p_owner bigint,p_reason text DEFAULT '')
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE result bigint; slot appointment_slots%ROWTYPE;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pets WHERE id=p_pet AND owner_id=p_owner) THEN
   RAISE EXCEPTION 'Pet does not belong to owner' USING ERRCODE='42501';
 END IF;
 SELECT * INTO slot FROM appointment_slots WHERE id=p_slot FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Slot not found' USING ERRCODE='P0002'; END IF;
 IF slot.starts_at <= now() OR NOT EXISTS(SELECT 1 FROM veterinarians v JOIN users u ON u.id=v.user_id WHERE v.id=slot.veterinarian_id AND v.available AND u.active) THEN
   RAISE EXCEPTION 'Slot unavailable' USING ERRCODE='P0001';
 END IF;
 IF EXISTS(SELECT 1 FROM appointments WHERE slot_id=p_slot AND status IN ('booked','completed')) THEN
   RAISE EXCEPTION 'Slot already booked' USING ERRCODE='23505';
 END IF;
 INSERT INTO appointments(slot_id,pet_id,owner_id,reason) VALUES(p_slot,p_pet,p_owner,p_reason) RETURNING id INTO result;
 RETURN result;
END $$;
CREATE VIEW available_slots AS
 SELECT s.*,u.name AS veterinarian_name,v.clinic FROM appointment_slots s
 JOIN veterinarians v ON v.id=s.veterinarian_id JOIN users u ON u.id=v.user_id
 WHERE s.starts_at>now() AND v.available AND u.active
 AND NOT EXISTS(SELECT 1 FROM appointments a WHERE a.slot_id=s.id AND a.status IN ('booked','completed'));
CREATE VIEW appointment_details AS
 SELECT a.*,p.name AS pet_name,u.name AS veterinarian_name,s.veterinarian_id,s.starts_at,s.ends_at
 FROM appointments a JOIN pets p ON p.id=a.pet_id JOIN appointment_slots s ON s.id=a.slot_id
 JOIN veterinarians v ON v.id=s.veterinarian_id JOIN users u ON u.id=v.user_id;
INSERT INTO schema_versions(version) VALUES(1);
COMMIT;
