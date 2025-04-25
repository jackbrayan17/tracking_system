from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime
import uuid

# App Config
app = Flask(__name__)
CORS(app)

DB = 'tracking.sqlite'
LOCATIONS_JSON = 'locations.json'

# Database Setup
def init_db():
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        # Create locations table
        c.execute('''
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT,
                town TEXT,
                latitude REAL,
                longitude REAL
            )
        ''')
        # Create tracks table
        c.execute('''
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                start_time TEXT,
                end_time TEXT,
                route TEXT,
                sender_name TEXT,
                sender_phone TEXT,
                receiver_name TEXT,
                receiver_phone TEXT,
                departure_location_id INTEGER,
                arrival_location_id INTEGER,
                FOREIGN KEY(departure_location_id) REFERENCES locations(id),
                FOREIGN KEY(arrival_location_id) REFERENCES locations(id)
            )
        ''')

# Populate Locations from JSON
def load_locations_from_json():
    with open(LOCATIONS_JSON, 'r', encoding='utf-8') as f:
        locations_data = json.load(f)

    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        for country, towns in locations_data.items():
            for town_data in towns:
                name = town_data['name']
                latitude = town_data['latitude']
                longitude = town_data['longitude']

                # Avoid inserting duplicates
                c.execute("SELECT id FROM locations WHERE country=? AND town=?", (country, name))
                if not c.fetchone():
                    c.execute(
                        "INSERT INTO locations (country, town, latitude, longitude) VALUES (?, ?, ?, ?)",
                        (country, name, latitude, longitude)
                    )

# Routes

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "OK", "message": "API is up and running 🚀"})

@app.route("/countries", methods=["GET"])
def get_countries():
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT DISTINCT country FROM locations ORDER BY country")
        countries = [row[0] for row in c.fetchall()]
    return jsonify(countries)

@app.route("/towns/<country>", methods=["GET"])
def get_towns(country):
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT id, town, latitude, longitude FROM locations WHERE country=? ORDER BY town", (country,))
        towns = [{"id": row[0], "town": row[1], "latitude": row[2], "longitude": row[3]} for row in c.fetchall()]
    return jsonify(towns)

@app.route("/create-track", methods=["POST"])
def create_track():
    data = request.json
    code = data.get("code") or str(uuid.uuid4())
    sender_name = data.get("sender_name")
    sender_phone = data.get("sender_phone")
    receiver_name = data.get("receiver_name")
    receiver_phone = data.get("receiver_phone")
    departure_location_id = data.get("departure_location_id")
    arrival_location_id = data.get("arrival_location_id")
    # route = data.get("route", [])  # optional route list

    # required_fields = [sender_name, sender_phone, receiver_name, receiver_phone, departure_location_id, arrival_location_id]
    # if not all(required_fields):
    #     return jsonify({"error": "Missing required fields"}), 400

    try:
        with sqlite3.connect(DB) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO tracks (
                    code, start_time, sender_name, sender_phone, receiver_name, receiver_phone, 
                    departure_location_id, arrival_location_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                code,
                datetime.now().isoformat(),
                sender_name,
                sender_phone,
                receiver_name,
                receiver_phone,
                departure_location_id,
                arrival_location_id,
                # json.dumps(route)  # serialize route list to JSON string
            ))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Code already exists"}), 400

    return jsonify({"message": "Track created", "code": code}), 201

@app.route("/track/<code>", methods=["GET"])
def get_track(code):
    try:
        with sqlite3.connect(DB) as conn:
            conn.row_factory = sqlite3.Row  # makes rows act like dicts
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.start_time, t.end_time, t.route, t.sender_name, t.sender_phone,
                       t.receiver_name, t.receiver_phone,
                       dl.country AS departure_country, dl.town AS departure_town, dl.latitude AS departure_latitude, dl.longitude AS departure_longitude,
                       al.country AS arrival_country, al.town AS arrival_town, al.latitude AS arrival_latitude, al.longitude AS arrival_longitude
                FROM tracks t
                LEFT JOIN locations dl ON t.departure_location_id = dl.id
                LEFT JOIN locations al ON t.arrival_location_id = al.id
                WHERE t.code = ?
            ''', (code,))
            row = cursor.fetchone()

        if row:
            # Safe JSON loading with fallback to empty list if parsing fails
            route_data = []
            if row["route"]:
                try:
                    route_data = json.loads(row["route"])
                except (ValueError, TypeError) as e:
                    app.logger.error(f"Error parsing route data: {e}")

            # Prepare the response data
            response = {
                "code": code,
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "route": route_data,
                "sender_name": row["sender_name"],
                "sender_phone": row["sender_phone"],
                "receiver_name": row["receiver_name"],
                "receiver_phone": row["receiver_phone"],
                "departure_location": {
                    "country": row["departure_country"],
                    "town": row["departure_town"],
                    "latitude": float(row["departure_latitude"]) if row["departure_latitude"] else None,
                    "longitude": float(row["departure_longitude"]) if row["departure_longitude"] else None
                },
                "arrival_location": {
                    "country": row["arrival_country"],
                    "town": row["arrival_town"],
                    "latitude": float(row["arrival_latitude"]) if row["arrival_latitude"] else None,
                    "longitude": float(row["arrival_longitude"]) if row["arrival_longitude"] else None
                }
            }

            return jsonify(response), 200

        else:
            return jsonify({"error": "No track found for this code."}), 404

    except sqlite3.Error as e:
        # Handle unexpected DB errors gracefully
        app.logger.error(f"Database error: {str(e)}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500

    except Exception as e:
        # Catch-all for unknown errors
        app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

# Launch App
if __name__ == "__main__":
    init_db()
    load_locations_from_json()
    app.run(debug=True)
