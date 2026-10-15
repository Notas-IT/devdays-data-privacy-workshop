ALTER TABLE business.people ADD COLUMN IF NOT EXISTS emergency_contact_email TEXT;
ALTER TABLE business.people ADD COLUMN IF NOT EXISTS payload JSONB;
ALTER TABLE business.people ADD COLUMN IF NOT EXISTS favorite_color TEXT;

UPDATE business.people
SET emergency_contact_email = 'contact-' || person_id || '@example.com',
    favorite_color = (ARRAY['red', 'green', 'blue'])[1 + person_id % 3];

-- Sparse nested PII: non-null sampling must inspect the final person's payload.
UPDATE business.people SET payload = jsonb_build_object(
    'delivery', jsonb_build_object('email', 'delivery-secret@example.com', 'phone', '0612 34 567')
) WHERE person_id = (SELECT max(person_id) FROM business.people);
