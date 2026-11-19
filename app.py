from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from pathlib import Path
from contextlib import closing

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-this")

DB = Path(__file__).with_name("bloodbridge.db")

# DEMO ONLY: Simulated coordination, not a medical or transport system.
DEMO_HOSPITAL_USER = "hospital"
DEMO_HOSPITAL_PASSWORD = "1234"

VALID_BLOOD_GROUPS = {
    "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"
}


# ---------------- DATABASE CONNECTION ----------------

def get_db():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- DATABASE INITIALIZATION ----------------

def init_db():
    with closing(get_db()) as conn:
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

        # Check and update existing donor table
        donor_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(donors)")
        }

        if "contact" not in donor_cols:
            conn.execute(
                "ALTER TABLE donors ADD COLUMN contact TEXT DEFAULT ''"
            )

        # Check and update existing blood requests table
        request_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(blood_requests)")
        }

        if "contact" not in request_cols:
            conn.execute(
                "ALTER TABLE blood_requests ADD COLUMN contact TEXT DEFAULT ''"
            )

        if "request_type" not in request_cols:
            conn.execute(
                "ALTER TABLE blood_requests "
                "ADD COLUMN request_type TEXT NOT NULL DEFAULT 'Normal'"
            )

        if "created_at" not in request_cols:
            conn.execute(
                "ALTER TABLE blood_requests ADD COLUMN created_at TEXT"
            )

        conn.execute("""
            UPDATE blood_requests
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL OR TRIM(created_at) = ''
        """)

        # Check and update existing transfers table
        transfer_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(transfers)")
        }

        if "notes" not in transfer_cols:
            conn.execute(
                "ALTER TABLE transfers ADD COLUMN notes TEXT DEFAULT ''"
            )

        if "updated_at" not in transfer_cols:
            conn.execute(
                "ALTER TABLE transfers ADD COLUMN updated_at TEXT"
            )

        conn.execute("""
            UPDATE transfers
            SET updated_at = CURRENT_TIMESTAMP
            WHERE updated_at IS NULL OR TRIM(updated_at) = ''
        """)

        conn.commit()


# IMPORTANT: Actually execute database initialization.
# This creates the required tables when the application starts.
init_db()


# ---------------- HELPER FUNCTIONS ----------------

def normalize_city(city):
    if not city:
        return ""

    city = " ".join(city.strip().casefold().split())

    aliases = {
        "mysore": "mysuru",
        "mysuru": "mysuru",
        "bangalore": "bengaluru",
        "bengaluru": "bengaluru",
        "bombay": "mumbai",
        "mumbai": "mumbai",
        "calcutta": "kolkata",
        "kolkata": "kolkata",
        "madras": "chennai",
        "chennai": "chennai",
    }

    return aliases.get(city, city)


def blood_normalize(value):
    return (value or "").strip().upper()


def hospital_required():
    return bool(session.get("hospital_logged_in"))


# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    return render_template("home.html")


# ---------------- DONOR REGISTRATION ----------------

@app.route("/donor-register", methods=["GET", "POST"])
def donor_register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        blood_group = blood_normalize(request.form.get("blood_group"))
        location = request.form.get("location", "").strip()
        contact = request.form.get("contact", "").strip()

        if not name or blood_group not in VALID_BLOOD_GROUPS or not location:
            flash("Please fill in the required fields correctly.")
            return render_template("donor_register.html")

        with closing(get_db()) as conn:
            conn.execute(
                """
                INSERT INTO donors
                (name, blood_group, location, contact)
                VALUES (?, ?, ?, ?)
                """,
                (name, blood_group, location, contact)
            )
            conn.commit()

        flash("Donor registered successfully.")
        return redirect(url_for("donor_register"))

    return render_template("donor_register.html")


# ---------------- BLOOD REQUIREMENTS ----------------

@app.route("/requirements")
def requirements():

    city = request.args.get("city", "").strip()
    kind = request.args.get("kind", "all")

    sql = "SELECT * FROM blood_requests"
    params = []
    filters = []

    if kind in ("Emergency", "Normal"):
        filters.append("request_type = ?")
        params.append(kind)

    if filters:
        sql += " WHERE " + " AND ".join(filters)

    sql += """
        ORDER BY CASE request_type
            WHEN 'Emergency' THEN 0
            ELSE 1
        END,
        id DESC
    """

    with closing(get_db()) as conn:
        rows = conn.execute(sql, params).fetchall()

        cities = conn.execute(
            """
            SELECT DISTINCT location
            FROM blood_requests
            ORDER BY location
            """
        ).fetchall()

    if city:
        rows = [
            row for row in rows
            if normalize_city(row["location"]) == normalize_city(city)
        ]

    return render_template(
        "requirements.html",
        requests=rows,
        city=city,
        kind=kind,
        cities=cities
    )


# ---------------- HOSPITAL LOGIN ----------------

@app.route("/hospital-login", methods=["GET", "POST"])
def hospital_login():

    if request.method == "POST":

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if (
            username == DEMO_HOSPITAL_USER
            and password == DEMO_HOSPITAL_PASSWORD
        ):
            session["hospital_logged_in"] = True
            flash("Logged in to the demo hospital portal.")
            return redirect(url_for("hospital_dashboard"))

        flash("Incorrect demo login.")

    return render_template("hospital_login.html")


# ---------------- HOSPITAL DASHBOARD ----------------

@app.route("/hospital-dashboard")
def hospital_dashboard():

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    with closing(get_db()) as conn:

        req_count = conn.execute(
            "SELECT COUNT(*) FROM blood_requests"
        ).fetchone()[0]

        donor_count = conn.execute(
            "SELECT COUNT(*) FROM donors"
        ).fetchone()[0]

        transfer_count = conn.execute(
            "SELECT COUNT(*) FROM transfers"
        ).fetchone()[0]

    return render_template(
        "hospital_dashboard.html",
        req_count=req_count,
        donor_count=donor_count,
        transfer_count=transfer_count
    )


# ---------------- CREATE BLOOD REQUEST ----------------

@app.route("/blood-request", methods=["GET", "POST"])
def blood_request():

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    if request.method == "POST":

        hospital_name = request.form.get("hospital_name", "").strip()
        blood_group = blood_normalize(request.form.get("blood_group"))
        units = request.form.get("units", "")
        location = request.form.get("location", "").strip()
        contact = request.form.get("contact", "").strip()
        request_type = request.form.get("request_type", "Normal")

        if (
            not hospital_name
            or blood_group not in VALID_BLOOD_GROUPS
            or not location
            or not units.isdigit()
            or int(units) < 1
            or request_type not in {"Emergency", "Normal"}
        ):
            flash("Please complete the request form correctly.")
            return render_template("request.html")

        with closing(get_db()) as conn:
            conn.execute(
                """
                INSERT INTO blood_requests
                (
                    hospital_name,
                    blood_group,
                    units,
                    location,
                    contact,
                    request_type
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    hospital_name,
                    blood_group,
                    int(units),
                    location,
                    contact,
                    request_type
                )
            )
            conn.commit()

        flash("Blood request saved.")
        return redirect(url_for("view_requests"))

    return render_template("request.html")


# ---------------- VIEW DONORS ----------------

@app.route("/view-donors")
def view_donors():

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    group = blood_normalize(request.args.get("blood_group", ""))

    with closing(get_db()) as conn:
        donors = conn.execute(
            """
            SELECT * FROM donors
            WHERE (? = '' OR UPPER(TRIM(blood_group)) = ?)
            ORDER BY id DESC
            """,
            (group, group)
        ).fetchall()

    return render_template(
        "donors.html",
        donors=donors,
        selected_blood_group=group
    )


# ---------------- DELETE DONOR ----------------

@app.route("/delete-donor/<int:donor_id>", methods=["POST"])
def delete_donor(donor_id):

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    with closing(get_db()) as conn:
        conn.execute(
            "DELETE FROM donors WHERE id = ?",
            (donor_id,)
        )
        conn.commit()

    flash("Donor record deleted.")
    return redirect(url_for("view_donors"))


# ---------------- VIEW HOSPITAL REQUESTS ----------------

@app.route("/view-requests")
def view_requests():

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    with closing(get_db()) as conn:
        requests_list = conn.execute(
            "SELECT * FROM blood_requests ORDER BY id DESC"
        ).fetchall()

    return render_template(
        "view_requests.html",
        requests=requests_list
    )


# ---------------- COMPLETE REQUEST ----------------

@app.route("/complete-request/<int:request_id>", methods=["POST"])
def complete_request(request_id):

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    with closing(get_db()) as conn:

        transfer_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM transfers
            WHERE request_id = ?
            """,
            (request_id,)
        ).fetchone()[0]

        if transfer_count:
            flash(
                "This request has transfer tracking. "
                "Close the demo transfer first."
            )
            return redirect(url_for("view_requests"))

        conn.execute(
            "DELETE FROM blood_requests WHERE id = ?",
            (request_id,)
        )
        conn.commit()

    flash("Request completed and removed. Donor records were retained.")
    return redirect(url_for("view_requests"))


# ---------------- AUTOMATIC DONOR MATCHING ----------------

@app.route("/automatic-matching")
def automatic_matching():

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    with closing(get_db()) as conn:

        requests_list = conn.execute(
            "SELECT * FROM blood_requests ORDER BY id DESC"
        ).fetchall()

        donor_rows = conn.execute(
            "SELECT * FROM donors ORDER BY id DESC"
        ).fetchall()

    matches = []

    for req in requests_list:

        same_city = []
        other_city = []

        for donor in donor_rows:

            if (
                blood_normalize(donor["blood_group"])
                != blood_normalize(req["blood_group"])
            ):
                continue

            if (
                normalize_city(donor["location"])
                == normalize_city(req["location"])
            ):
                same_city.append(donor)
            else:
                other_city.append(donor)

        matches.append({
            "request": req,
            "priority_1": same_city,
            "priority_2": other_city
        })

    return render_template(
        "automatic_matching.html",
        matches=matches
    )


# ---------------- TRANSFER MANAGEMENT ----------------

@app.route("/transfers")
def transfers():

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    with closing(get_db()) as conn:

        transfer_rows = conn.execute(
            """
            SELECT t.*, r.hospital_name, r.blood_group, r.request_type
            FROM transfers t
            JOIN blood_requests r ON r.id = t.request_id
            ORDER BY t.id DESC
            """
        ).fetchall()

        requests_list = conn.execute(
            "SELECT * FROM blood_requests ORDER BY id DESC"
        ).fetchall()

        donors = conn.execute(
            "SELECT * FROM donors ORDER BY id DESC"
        ).fetchall()

    return render_template(
        "transfers.html",
        transfers=transfer_rows,
        requests=requests_list,
        donors=donors
    )


# ---------------- CREATE TRANSFER ----------------

@app.route("/transfer/create", methods=["POST"])
def create_transfer():

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    request_id = request.form.get("request_id", "")
    donor_id = request.form.get("donor_id") or None
    origin_city = request.form.get("origin_city", "").strip()
    destination_city = request.form.get("destination_city", "").strip()

    if not request_id or not origin_city or not destination_city:
        flash("Complete the transfer form.")
        return redirect(url_for("transfers"))

    with closing(get_db()) as conn:

        request_exists = conn.execute(
            "SELECT id FROM blood_requests WHERE id = ?",
            (request_id,)
        ).fetchone()

        if not request_exists:
            flash("Request not found.")
            return redirect(url_for("transfers"))

        if donor_id:

            donor_exists = conn.execute(
                "SELECT id FROM donors WHERE id = ?",
                (donor_id,)
            ).fetchone()

            if not donor_exists:
                flash("Selected donor was not found.")
                return redirect(url_for("transfers"))

        conn.execute(
            """
            INSERT INTO transfers
            (
                request_id,
                donor_id,
                origin_city,
                destination_city,
                updated_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                request_id,
                donor_id,
                origin_city,
                destination_city
            )
        )

        conn.commit()

    flash("Demo transfer record created.")
    return redirect(url_for("transfers"))


# ---------------- UPDATE TRANSFER STATUS ----------------

@app.route("/transfer/<int:transfer_id>/status", methods=["POST"])
def update_transfer(transfer_id):

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    allowed_statuses = {
        "Coordination started",
        "Donation centre confirmation pending",
        "Dispatch status recorded",
        "Receipt confirmed"
    }

    status = request.form.get("status", "")

    if status not in allowed_statuses:
        flash("Invalid transfer status.")
        return redirect(url_for("transfers"))

    with closing(get_db()) as conn:

        conn.execute(
            """
            UPDATE transfers
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, transfer_id)
        )

        conn.commit()

    flash("Transfer status updated.")
    return redirect(url_for("transfers"))


# ---------------- CLOSE TRANSFER ----------------

@app.route("/transfer/<int:transfer_id>/close", methods=["POST"])
def close_transfer(transfer_id):

    if not hospital_required():
        return redirect(url_for("hospital_login"))

    with closing(get_db()) as conn:

        row = conn.execute(
            """
            SELECT request_id, status
            FROM transfers
            WHERE id = ?
            """,
            (transfer_id,)
        ).fetchone()

        if not row or row["status"] != "Receipt confirmed":
            flash(
                "A demo transfer can only be closed "
                "after receipt is confirmed."
            )
            return redirect(url_for("transfers"))

        conn.execute(
            "DELETE FROM transfers WHERE id = ?",
            (transfer_id,)
        )

        conn.commit()

    flash("Transfer tracking record closed.")
    return redirect(url_for("transfers"))


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()
    return redirect(url_for("home"))


# ---------------- HEALTH CHECK ----------------

@app.route("/health")
def health():

    try:
        with closing(get_db()) as conn:
            conn.execute("SELECT 1").fetchone()

        return {"status": "healthy", "database": "connected"}, 200

    except sqlite3.Error:
        app.logger.exception("Database health check failed")
        return {"status": "unhealthy", "database": "error"}, 500


# ---------------- START APPLICATION ----------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )