from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3

app = Flask(__name__)
app.secret_key = "bloodbridge-secret-key"


def get_db():
    conn = sqlite3.connect("bloodbridge.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            location TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blood_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            units INTEGER NOT NULL,
            location TEXT NOT NULL,
            contact TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/donor-register", methods=["GET", "POST"])
def donor_register():
    if request.method == "POST":
        name = request.form.get("name")
        blood_group = request.form.get("blood_group")
        location = request.form.get("location")

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO donors (name, blood_group, location)
            VALUES (?, ?, ?)
        """, (name, blood_group, location))

        conn.commit()
        conn.close()

        return render_template(
            "form.html",
            success="Donor registered successfully!"
        )

    return render_template("form.html")


@app.route("/hospital-login", methods=["GET", "POST"])
def hospital_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # Demo hospital login
        if username == "hospital" and password == "1234":
            session["hospital_logged_in"] = True
            return redirect(url_for("hospital_dashboard"))

        return render_template(
            "hospital_login.html",
            error="Invalid username or password."
        )

    return render_template("hospital_login.html")


@app.route("/hospital-dashboard")
def hospital_dashboard():
    if not session.get("hospital_logged_in"):
        return redirect(url_for("hospital_login"))

    return render_template("hospital_dashboard.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("hospital_login"))


@app.route("/view-donors")
def view_donors():
    blood_group = request.args.get("blood_group", "").strip().upper()

    conn = get_db()
    cursor = conn.cursor()

    if blood_group:
        cursor.execute("""
            SELECT * FROM donors
            WHERE UPPER(blood_group) = ?
        """, (blood_group,))
    else:
        cursor.execute("""
            SELECT * FROM donors
        """)

    donors = cursor.fetchall()
    conn.close()

    return render_template(
        "donors.html",
        donors=donors,
        selected_blood_group=blood_group
    )


@app.route("/blood-request", methods=["GET", "POST"])
def blood_request():
    if not session.get("hospital_logged_in"):
        return redirect(url_for("hospital_login"))

    if request.method == "POST":
        hospital_name = request.form.get("hospital_name")
        blood_group = request.form.get("blood_group")
        units = request.form.get("units")
        location = request.form.get("location")
        contact = request.form.get("contact")

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO blood_requests
            (hospital_name, blood_group, units, location, contact)
            VALUES (?, ?, ?, ?, ?)
        """, (
            hospital_name,
            blood_group,
            units,
            location,
            contact
        ))

        conn.commit()

        cursor.execute("""
            SELECT * FROM donors
            WHERE UPPER(blood_group) = UPPER(?)
        """, (blood_group,))

        matching_donors = cursor.fetchall()

        conn.close()

        return render_template(
            "request_result.html",
            hospital_name=hospital_name,
            blood_group=blood_group,
            units=units,
            location=location,
            contact=contact,
            matching_donors=matching_donors
        )

    return render_template("request.html")


@app.route("/view-requests")
def view_requests():
    if not session.get("hospital_logged_in"):
        return redirect(url_for("hospital_login"))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM blood_requests
        ORDER BY id DESC
    """)

    requests = cursor.fetchall()
    conn.close()

    return render_template(
        "view_requests.html",
        requests=requests
    )
@app.route("/automatic-matching")
def automatic_matching():
    if not session.get("hospital_logged_in"):
        return redirect(url_for("hospital_login"))

    conn = get_db()
    cursor = conn.cursor()

    # Normalize city names
    def normalize_city(city):
        if not city:
            return ""

        # Remove extra spaces and make lowercase
        city = " ".join(city.strip().lower().split())

        # Common city-name variations
        city_aliases = {
            "mysore": "mysuru",
            "mysuru": "mysuru",

            "bangalore": "bengaluru",
            "bengaluru": "bengaluru",

            "bombay": "mumbai",
            "mumbai": "mumbai",

            "calcutta": "kolkata",
            "kolkata": "kolkata",

            "madras": "chennai",
            "chennai": "chennai"
        }

        return city_aliases.get(city, city)

    # Get all blood requests
    cursor.execute("""
        SELECT * FROM blood_requests
        ORDER BY id DESC
    """)

    requests = cursor.fetchall()

    matches = []

    for blood_request in requests:

        # Normalize blood group too
        required_blood_group = (
            blood_request["blood_group"]
            .strip()
            .upper()
        )

        # Normalize requested city
        required_city = normalize_city(
            blood_request["location"]
        )

        # Blood group is the matching condition.
        # City is used only for priority.
        cursor.execute("""
            SELECT * FROM donors
            WHERE UPPER(TRIM(blood_group)) = ?
        """, (required_blood_group,))

        donors = cursor.fetchall()

        priority_1 = []
        priority_2 = []

        for donor in donors:

            # Normalize donor city
            donor_city = normalize_city(
                donor["location"]
            )

            # PRIORITY 1
            # Same blood group + same city
            if donor_city == required_city:
                priority_1.append(donor)

            # PRIORITY 2
            # Same blood group + different city
            else:
                priority_2.append(donor)

        matches.append({
            "request": blood_request,
            "priority_1": priority_1,
            "priority_2": priority_2
        })

    conn.close()

    return render_template(
        "automatic_matching.html",
        matches=matches
    )

    return render_template(
        "automatic_matching.html",
        matches=matches
    )
@app.route("/complete-request/<int:request_id>", methods=["POST"])
def complete_request(request_id):
    if not session.get("hospital_logged_in"):
        return redirect(url_for("hospital_login"))

    conn = get_db()
    cursor = conn.cursor()

    # Delete only the completed blood request
    # The donor remains in the database.
    cursor.execute("""
        DELETE FROM blood_requests
        WHERE id = ?
    """, (request_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("view_requests"))

@app.route("/delete-donor/<int:donor_id>", methods=["POST"])
def delete_donor(donor_id):
    if not session.get("hospital_logged_in"):
        return redirect(url_for("hospital_login"))

    conn = get_db()
    cursor = conn.cursor()

    # Manually delete only this donor
    cursor.execute("""
        DELETE FROM donors
        WHERE id = ?
    """, (donor_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("view_donors"))



if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)