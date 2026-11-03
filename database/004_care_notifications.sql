BEGIN;
ALTER TABLE pets ADD COLUMN weight_kg numeric(7,3) CHECK(weight_kg > 0 AND weight_kg <= 2000);
ALTER TABLE pets ADD COLUMN allergies text NOT NULL DEFAULT '' CHECK(length(allergies)<=5000);
CREATE TABLE medication_schedules (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 pet_id bigint NOT NULL REFERENCES pets(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 200),
 dosage text NOT NULL CHECK(length(dosage) BETWEEN 1 AND 500),
 instructions text NOT NULL DEFAULT '' CHECK(length(instructions)<=2000),
 starts_at timestamptz NOT NULL,
 ends_at timestamptz NOT NULL,
 interval_hours integer NOT NULL CHECK(interval_hours BETWEEN 1 AND 720),
 active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(ends_at>=starts_at AND ends_at<=starts_at+interval '366 days')
);
CREATE INDEX medications_pet_idx ON medication_schedules(pet_id,starts_at DESC);
CREATE TRIGGER medications_audit AFTER INSERT OR UPDATE ON medication_schedules FOR EACH ROW EXECUTE FUNCTION audit_change();
ALTER TABLE reminders ALTER COLUMN vaccination_id DROP NOT NULL;
ALTER TABLE reminders ADD COLUMN kind text NOT NULL DEFAULT 'vaccination'
 CHECK(kind IN ('vaccination','medication','appointment_reminder','appointment_booked','appointment_cancelled','appointment_completed'));
ALTER TABLE reminders ADD COLUMN medication_id bigint REFERENCES medication_schedules(id);
ALTER TABLE reminders ADD COLUMN appointment_id bigint REFERENCES appointments(id);
ALTER TABLE reminders ADD COLUMN read_at timestamptz;
ALTER TABLE reminders ADD COLUMN cancelled boolean NOT NULL DEFAULT false;
CREATE UNIQUE INDEX medication_dose_once ON reminders(medication_id,due_at) WHERE medication_id IS NOT NULL;
CREATE UNIQUE INDEX appointment_event_once ON reminders(appointment_id,kind) WHERE appointment_id IS NOT NULL;
ALTER TABLE reminders ADD CONSTRAINT reminder_source CHECK(
 (kind='vaccination' AND vaccination_id IS NOT NULL AND medication_id IS NULL AND appointment_id IS NULL) OR
 (kind='medication' AND medication_id IS NOT NULL AND vaccination_id IS NULL AND appointment_id IS NULL) OR
 (kind LIKE 'appointment_%' AND appointment_id IS NOT NULL AND vaccination_id IS NULL AND medication_id IS NULL));
CREATE FUNCTION medication_reminders() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
   INSERT INTO reminders(owner_id,medication_id,kind,due_at,message)
   SELECT p.owner_id,NEW.id,'medication',dose,p.name || ': ' || NEW.name || ' — ' || NEW.dosage
   FROM pets p CROSS JOIN generate_series(NEW.starts_at,NEW.ends_at,make_interval(hours=>NEW.interval_hours)) dose
   WHERE p.id=NEW.pet_id;
 ELSIF OLD.active AND NOT NEW.active THEN
   UPDATE reminders SET cancelled=true WHERE medication_id=NEW.id AND NOT acknowledged;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER medication_reminder_trigger AFTER INSERT OR UPDATE ON medication_schedules FOR EACH ROW EXECUTE FUNCTION medication_reminders();
CREATE FUNCTION appointment_notifications() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE visit_at timestamptz; pet_name text;
BEGIN
 IF TG_OP='UPDATE' AND NEW.status=OLD.status THEN RETURN NEW; END IF;
 SELECT starts_at INTO visit_at FROM appointment_slots WHERE id=NEW.slot_id;
 SELECT name INTO pet_name FROM pets WHERE id=NEW.pet_id;
 INSERT INTO reminders(owner_id,appointment_id,kind,due_at,message)
 VALUES(NEW.owner_id,NEW.id,'appointment_' || NEW.status,now(),pet_name || ': appointment ' || NEW.status || ' (' || to_char(visit_at AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI') || ' UTC)')
 ON CONFLICT(appointment_id,kind) WHERE appointment_id IS NOT NULL DO NOTHING;
 IF NEW.status='booked' THEN
   INSERT INTO reminders(owner_id,appointment_id,kind,due_at,message)
   VALUES(NEW.owner_id,NEW.id,'appointment_reminder',greatest(now(),visit_at-interval '24 hours'),pet_name || ': upcoming appointment (' || to_char(visit_at AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI') || ' UTC)');
 ELSE
   UPDATE reminders SET cancelled=true WHERE appointment_id=NEW.id AND kind='appointment_reminder';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER appointment_notification_trigger AFTER INSERT OR UPDATE ON appointments FOR EACH ROW EXECUTE FUNCTION appointment_notifications();
CREATE TRIGGER vaccinations_audit AFTER INSERT OR UPDATE OR DELETE ON vaccination_records FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER medical_records_audit AFTER INSERT OR UPDATE OR DELETE ON medical_records FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER veterinarians_audit AFTER INSERT OR UPDATE OR DELETE ON veterinarians FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER slots_audit AFTER INSERT OR UPDATE OR DELETE ON appointment_slots FOR EACH ROW EXECUTE FUNCTION audit_change();
-- Include existing future bookings without fabricating historical booking events.
INSERT INTO reminders(owner_id,appointment_id,kind,due_at,message)
SELECT a.owner_id,a.id,'appointment_reminder',greatest(now(),s.starts_at-interval '24 hours'),
 p.name || ': upcoming appointment (' || to_char(s.starts_at AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI') || ' UTC)'
FROM appointments a JOIN pets p ON p.id=a.pet_id JOIN appointment_slots s ON s.id=a.slot_id
WHERE a.status='booked' AND s.starts_at>now();
CREATE OR REPLACE PROCEDURE acknowledge_reminder(p_reminder bigint,p_owner bigint)
LANGUAGE plpgsql AS $$
BEGIN
 UPDATE reminders SET acknowledged=true,read_at=coalesce(read_at,now()) WHERE id=p_reminder AND owner_id=p_owner AND NOT cancelled;
 IF NOT FOUND THEN RAISE EXCEPTION 'Reminder not found' USING ERRCODE='P0002'; END IF;
END $$;
INSERT INTO schema_versions(version) VALUES(4);
COMMIT;
