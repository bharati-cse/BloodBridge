from flask import Flask, render_template, request
import sqlite3
from database import create_database

app = Flask(__name__)
create_database()

# HOME PAGE
@app.route("/")
def home():
    return render_template("home.html")


# DONOR REGISTRATION
@app.route("/donor-register", methods=["GET", "POST"])
def donor_register():
    if request.method == "POST":
        name = request.form.get("name")
        blood_group = request.form.get("blood_group")
        location = request.form.get("location")

        conn = sqlite3.connect("bloodbridge.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO donors (name, blood_group, location)
            VALUES (?, ?, ?)
        """, (name, blood_group, location))

        conn.commit()
        conn.close()

        return f"""
        <h1>Donor Registered Successfully!</h1>
        <p>Name: {name}</p>
        <p>Blood Group: {blood_group}</p>
        <p>Location: {location}</p>
        <a href="/">Back to Home</a>
        """

    return render_template("form.html")

# DONOR LOGIN
@app.route("/donor-login", methods=["GET", "POST"])
def donor_login():
    if request.method == "POST":
        return "<h1>Donor Login Submitted!</h1><a href='/'>Home</a>"

    return render_template("login.html")


# HOSPITAL LOGIN
@app.route("/hospital-login", methods=["GET", "POST"])
def hospital_login():
    if request.method == "POST":
        return "<h1>Hospital Login Submitted!</h1><a href='/'>Home</a>"

    return render_template("hospital_login.html")


# BLOOD REQUEST

@app.route("/blood-request", methods=["GET", "POST"])
def blood_request():
    if request.method == "POST":
        hospital_name = request.form.get("hospital_name")
        blood_group = request.form.get("blood_group")
        units = request.form.get("units")
        location = request.form.get("location")
        contact = request.form.get("contact")

        conn = sqlite3.connect("bloodbridge.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO blood_requests
            (hospital_name, blood_group, units, location, contact)
            VALUES (?, ?, ?, ?, ?)
        """, (hospital_name, blood_group, units, location, contact))

        conn.commit()
        conn.close()

        return """
        <h1>Blood Request Saved Successfully!</h1>
        <a href="/">Back to Home</a>
        """

    return render_template("request.html")

# DONOR DASHBOARD
@app.route("/donor-dashboard")
def donor_dashboard():
    return render_template("dashboard.html")


# HOSPITAL DASHBOARD
@app.route("/hospital-dashboard")
def hospital_dashboard():
    return render_template("hospital_dashboard.html")



@app.route("/view-donors")
def view_donors():
    blood_group = request.args.get("blood_group")

    conn = sqlite3.connect("bloodbridge.db")
    cursor = conn.cursor()

    if blood_group:
        cursor.execute(
            "SELECT * FROM donors WHERE blood_group = ?",
            (blood_group,)
        )
    else:
        cursor.execute("SELECT * FROM donors")

    donors = cursor.fetchall()
    conn.close()

    return render_template("donors.html", donors=donors)

@app.route("/view-requests")
def view_requests():
    conn = sqlite3.connect("bloodbridge.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM blood_requests")
    requests = cursor.fetchall()

    conn.close()

    return render_template("view_requests.html", requests=requests)



# RUN APPLICATION
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)