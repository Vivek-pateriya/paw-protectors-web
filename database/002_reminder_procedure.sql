BEGIN;
CREATE PROCEDURE acknowledge_reminder(p_reminder bigint,p_owner bigint)
LANGUAGE plpgsql AS $$
BEGIN
 UPDATE reminders SET acknowledged=true WHERE id=p_reminder AND owner_id=p_owner;
 IF NOT FOUND THEN RAISE EXCEPTION 'Reminder not found' USING ERRCODE='P0002'; END IF;
END $$;
INSERT INTO schema_versions(version) VALUES(2);
COMMIT;
