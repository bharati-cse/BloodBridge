import sqlite3
from pathlib import Path

DB = Path(__file__).with_name("bloodbridge.db")


def get_connection():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS donors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            location TEXT NOT NULL,
            contact TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS blood_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            units INTEGER NOT NULL,
            location TEXT NOT NULL,
            contact TEXT DEFAULT '',
            request_type TEXT NOT NULL DEFAULT 'Normal',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            donor_id INTEGER,
            origin_city TEXT NOT NULL,
            destination_city TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Coordination started',
            notes TEXT DEFAULT '',
            updated_at TEXT,
            FOREIGN KEY(request_id) REFERENCES blood_requests(id),
            FOREIGN KEY(donor_id) REFERENCES donors(id)
        );
        """)

        # Migrate older databases safely. SQLite cannot add a column with
        # CURRENT_TIMESTAMP as its DEFAULT to an existing table.
        donor_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(donors)")
        }
        if "contact" not in donor_columns:
            conn.execute("ALTER TABLE donors ADD COLUMN contact TEXT DEFAULT ''")

        request_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(blood_requests)")
        }
        if "contact" not in request_columns:
            conn.execute("ALTER TABLE blood_requests ADD COLUMN contact TEXT DEFAULT ''")
        if "request_type" not in request_columns:
            conn.execute(
                "ALTER TABLE blood_requests "
                "ADD COLUMN request_type TEXT NOT NULL DEFAULT 'Normal'"
            )
        if "created_at" not in request_columns:
            conn.execute("ALTER TABLE blood_requests ADD COLUMN created_at TEXT")
        conn.execute("""
            UPDATE blood_requests
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL OR TRIM(created_at) = ''
        """)

        transfer_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(transfers)")
        }
        if "notes" not in transfer_columns:
            conn.execute("ALTER TABLE transfers ADD COLUMN notes TEXT DEFAULT ''")
        if "updated_at" not in transfer_columns:
            conn.execute("ALTER TABLE transfers ADD COLUMN updated_at TEXT")
        conn.execute("""
            UPDATE transfers
            SET updated_at = CURRENT_TIMESTAMP
            WHERE updated_at IS NULL OR TRIM(updated_at) = ''
        """)


if __name__ == "__main__":
    initialize_database()
    print("BloodBridge database is ready.")