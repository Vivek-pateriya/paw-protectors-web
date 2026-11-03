BEGIN;
CREATE TABLE adoption_listings (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 creator_id bigint NOT NULL REFERENCES users(id),
 name text NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 120),
 species text NOT NULL CHECK(length(trim(species)) BETWEEN 1 AND 100),
 breed text NOT NULL DEFAULT '' CHECK(length(breed)<=120),
 age_months integer NOT NULL DEFAULT 0 CHECK(age_months BETWEEN 0 AND 1200),
 gender text NOT NULL CHECK(gender IN ('male','female','unknown')),
 location text NOT NULL CHECK(length(trim(location)) BETWEEN 1 AND 200),
 description text NOT NULL CHECK(length(trim(description)) BETWEEN 1 AND 5000),
 health_summary text NOT NULL DEFAULT '' CHECK(length(health_summary)<=5000),
 weight_kg numeric(7,3) CHECK(weight_kg>0 AND weight_kg<=2000),
 allergies text NOT NULL DEFAULT '' CHECK(length(allergies)<=5000),
 image_path text,
 status text NOT NULL CHECK(status IN ('pending_review','available','reserved','adopted','rejected','archived')),
 moderation_reason text NOT NULL DEFAULT '',
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 selected_application_id bigint,
 adopted_pet_id bigint UNIQUE REFERENCES pets(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK((status IN ('reserved','adopted'))=(selected_application_id IS NOT NULL)),
 CHECK((status='adopted')=(adopted_pet_id IS NOT NULL))
);
CREATE INDEX adoption_browse_idx ON adoption_listings(status,created_at DESC,id DESC);
CREATE INDEX adoption_creator_idx ON adoption_listings(creator_id,id DESC);
CREATE TABLE adoption_applications (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 listing_id bigint NOT NULL REFERENCES adoption_listings(id),
 applicant_id bigint NOT NULL REFERENCES users(id),
 motivation text NOT NULL CHECK(length(trim(motivation)) BETWEEN 10 AND 2000),
 housing text NOT NULL CHECK(housing IN ('house','apartment','farm','other')),
 has_other_pets boolean NOT NULL DEFAULT false,
 experience text NOT NULL DEFAULT '' CHECK(length(experience)<=2000),
 contact_phone text NOT NULL DEFAULT '' CHECK(length(contact_phone)<=30),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','withdrawn','completed')),
 decision_reason text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(id,listing_id)
);
CREATE UNIQUE INDEX adoption_one_active_request ON adoption_applications(listing_id,applicant_id) WHERE status IN ('pending','approved');
CREATE UNIQUE INDEX adoption_one_winner ON adoption_applications(listing_id) WHERE status IN ('approved','completed');
CREATE INDEX adoption_applicant_idx ON adoption_applications(applicant_id,id DESC);
CREATE INDEX adoption_review_idx ON adoption_applications(status,listing_id,id);
ALTER TABLE adoption_listings ADD FOREIGN KEY(selected_application_id,id) REFERENCES adoption_applications(id,listing_id);
CREATE TABLE adoption_history (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 listing_id bigint NOT NULL REFERENCES adoption_listings(id),
 application_id bigint,
 actor_id bigint NOT NULL REFERENCES users(id),
 from_status text,
 to_status text NOT NULL,
 reason text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(application_id,listing_id) REFERENCES adoption_applications(id,listing_id)
);
CREATE INDEX adoption_history_idx ON adoption_history(listing_id,id);
CREATE TRIGGER adoption_listings_audit AFTER INSERT OR UPDATE ON adoption_listings FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER adoption_applications_audit AFTER INSERT OR UPDATE ON adoption_applications FOR EACH ROW EXECUTE FUNCTION audit_change();
ALTER TABLE reminders ADD COLUMN adoption_listing_id bigint REFERENCES adoption_listings(id);
ALTER TABLE reminders ADD COLUMN adoption_application_id bigint REFERENCES adoption_applications(id);
ALTER TABLE reminders ADD COLUMN event_key text;
CREATE UNIQUE INDEX reminder_event_once ON reminders(owner_id,event_key) WHERE event_key IS NOT NULL;
ALTER TABLE reminders DROP CONSTRAINT reminders_kind_check;
ALTER TABLE reminders ADD CONSTRAINT reminders_kind_check CHECK(kind IN ('vaccination','medication','appointment_reminder','appointment_booked','appointment_cancelled','appointment_completed','adoption_listing','adoption_application'));
ALTER TABLE reminders DROP CONSTRAINT reminder_source;
ALTER TABLE reminders ADD CONSTRAINT reminder_source CHECK(
 (kind='vaccination' AND vaccination_id IS NOT NULL AND medication_id IS NULL AND appointment_id IS NULL AND adoption_listing_id IS NULL AND adoption_application_id IS NULL) OR
 (kind='medication' AND medication_id IS NOT NULL AND vaccination_id IS NULL AND appointment_id IS NULL AND adoption_listing_id IS NULL AND adoption_application_id IS NULL) OR
 (kind LIKE 'appointment_%' AND appointment_id IS NOT NULL AND vaccination_id IS NULL AND medication_id IS NULL AND adoption_listing_id IS NULL AND adoption_application_id IS NULL) OR
 (kind IN ('adoption_listing','adoption_application') AND adoption_listing_id IS NOT NULL AND vaccination_id IS NULL AND medication_id IS NULL AND appointment_id IS NULL)
);
INSERT INTO schema_versions(version) VALUES(5);
COMMIT;
