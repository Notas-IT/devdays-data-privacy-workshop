ALTER TABLE business.people ADD COLUMN IF NOT EXISTS internal_memo TEXT;
UPDATE business.people SET internal_memo = 'follow up after the next meeting';
