"""Add error_type and error_details columns to scrape_run_metrics table."""
import sqlite3
from pathlib import Path


def migrate():
    """Add error tracking columns to existing database."""
    db_path = Path(__file__).parent.parent / "data" / "cache.db"

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check if columns already exist
    cur.execute("PRAGMA table_info(scrape_run_metrics)")
    columns = {row[1] for row in cur.fetchall()}

    if "error_type" in columns and "error_details" in columns:
        print("Columns already exist, no migration needed.")
        conn.close()
        return

    # Add columns
    if "error_type" not in columns:
        print("Adding error_type column...")
        cur.execute("ALTER TABLE scrape_run_metrics ADD COLUMN error_type TEXT")

    if "error_details" not in columns:
        print("Adding error_details column...")
        cur.execute("ALTER TABLE scrape_run_metrics ADD COLUMN error_details TEXT")

    conn.commit()
    conn.close()
    print("Migration complete!")


if __name__ == "__main__":
    migrate()
