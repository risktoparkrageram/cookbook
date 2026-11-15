-- The cookbook has exactly one account, the admin's. A second row is refused, so setting
-- a password (recipe-db set-password) updates the existing row instead of adding one.
CREATE TRIGGER users_single_account BEFORE INSERT ON users
WHEN EXISTS (SELECT 1 FROM users)
BEGIN
    SELECT RAISE(ABORT, 'the cookbook has a single account; set-password replaces it');
END;
