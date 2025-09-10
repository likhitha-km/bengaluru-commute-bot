import os
import requests
import googlemaps
from datetime import datetime
import json
import math
from urllib.parse import quote_plus

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
CHAT_ID = os.getenv('CHAT_ID')
USER_MESSAGE = os.getenv('USER_MESSAGE')

try:
    with open('metro_data.json', 'r') as f:
        metro_data = json.load(f)
except FileNotFoundError:
    metro_data = None

gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

def send_telegram_message(text, keyboard=None):
    """Sends a message and returns the message_id."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload['reply_markup'] = json.dumps(keyboard)
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Initial message sent successfully!")
        return response.json()['result']['message_id']
    except requests.exceptions.RequestException as e:
        print(f"Error sending initial message: {e}")
        return None

def delete_telegram_message(message_id):
    """Deletes a message."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage"
    payload = {"chat_id": CHAT_ID, "message_id": message_id}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Message deleted successfully!")
    except requests.exceptions.RequestException as e:
        print(f"Error deleting message: {e}")


def send_telegram_photo(caption, photo_url, keyboard=None):
    """Sends a photo with a caption and an optional keyboard."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    if keyboard:
        payload['reply_markup'] = json.dumps(keyboard)
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Photo message sent successfully!")
    except requests.exceptions.RequestException as e:
        print(f"Error sending photo message: {e}")


# --- (get_metro_options and get_cab_auto_options functions remain the same) ---
def get_metro_options(origin_coords, dest_coords):
    """Calculates the best metro route based on proximity to stations."""
    if not metro_data:
        return ""
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371
        dLat, dLon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = math.sin(dLat / 2) * math.sin(dLat / 2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon / 2) * math.sin(dLon / 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    stations = metro_data['stations']
    start_station = min(stations, key=lambda s: haversine(origin_coords['lat'], origin_coords['lng'], s['lat'], s['lon']))
    end_station = min(stations, key=lambda s: haversine(dest_coords['lat'], dest_coords['lng'], s['lat'], s['lon']))
    if haversine(origin_coords['lat'], origin_coords['lng'], start_station['lat'], start_station['lon']) > 3:
        return ""
    interchange = metro_data['interchange']
    if start_station['name'] == end_station['name']:
        return ""
    if start_station['line'] == end_station['line'] or start_station['line'] == 'Both' or end_station['line'] == 'Both':
        num_stations = abs(start_station['id'] - end_station['id'])
        route_desc = f"from *{start_station['name']}* to *{end_station['name']}*"
    else:
        interchange_station = next(s for s in stations if s['name'] == interchange)
        num_stations = abs(start_station['id'] - interchange_station['id']) + abs(interchange_station['id'] - end_station['id'])
        route_desc = f"from *{start_station['name']}* to *{end_station['name']}* (via {interchange})"
    fare = min(10 + (num_stations - 1) * 5, 60)
    time = num_stations * 3 + 15
    return (
        f"🚇 *Metro Option*\n"
        f"   - *Route:* {route_desc}\n"
        f"   - *Est. Time:* ~{time} min\n"
        f"   - *Est. Fare:* ₹{fare:.0f}\n"
    )

def get_cab_auto_options(directions_result):
    """Formats the cab/auto options."""
    if not directions_result:
        return "Could not find driving directions."
    leg = directions_result[0]['legs'][0]
    duration = leg['duration']['text']
    distance = leg['distance']['text']
    dist_km = float(distance.replace(' km', ''))
    auto_fare = 30 + (dist_km * 15)
    cab_fare = 70 + (dist_km * 20)
    return (
        f"🚗 *Cab/Auto Estimate*\n"
        f"   - *Travel Time:* {duration}\n"
        f"   - *Distance:* {distance}\n"
        f"   - *Est. Auto Fare:* ₹{auto_fare:.0f} - ₹{auto_fare + 30:.0f}\n"
        f"   - *Est. Cab Fare:* ₹{cab_fare:.0f} - ₹{cab_fare + 50:.0f}\n"
    )

# --- UPDATED MAIN EXECUTION BLOCK ---
if __name__ == "__main__":
    if not all([TELEGRAM_BOT_TOKEN, GOOGLE_API_KEY, CHAT_ID, USER_MESSAGE]):
        print("Error: Missing one or more environment variables.")
    else:
        try:
            parts = USER_MESSAGE.split(" to ")
            if len(parts) == 2:
                origin_loc, dest_loc = parts[0].strip(), parts[1].strip()
                
                # 1. Send a "Searching..." message and get its ID
                searching_msg_id = send_telegram_message(f"Searching for routes from *{origin_loc.title()}* to *{dest_loc.title()}*...")

                # 2. Do all the work
                now = datetime.now()
                directions_result = gmaps.directions(origin_loc, dest_loc, mode="driving", region="in", departure_time=now)
                
                cab_info = get_cab_auto_options(directions_result)
                
                origin_coords = directions_result[0]['legs'][0]['start_location']
                dest_coords = directions_result[0]['legs'][0]['end_location']
                metro_info = get_metro_options(origin_coords, dest_coords)
                
                # 3. Build the final response text
                final_caption = f"📍 *Route: {origin_loc.title()} to {dest_loc.title()}*\n---------------------------------------\n"
                final_caption += cab_info
                if metro_info:
                    final_caption += "\n" + metro_info
                
                # 4. Build the Google Maps URL and Inline Keyboard
                google_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={quote_plus(origin_loc)}&destination={quote_plus(dest_loc)}"
                inline_keyboard = {"inline_keyboard": [[{"text": "View Route on Google Maps", "url": google_maps_url}]]}
                
                # 5. Build the Static Map URL
                # We add markers for origin (O) and destination (D)
                static_map_url = (
                    f"https://maps.googleapis.com/maps/api/staticmap?size=600x400"
                    f"&markers=color:green%7Clabel:O%7C{origin_coords['lat']},{origin_coords['lng']}"
                    f"&markers=color:red%7Clabel:D%7C{dest_coords['lat']},{dest_coords['lng']}"
                    f"&path=color:0x0000ff|weight:5|enc:{directions_result[0]['overview_polyline']['points']}"
                    f"&key={GOOGLE_API_KEY}"
                )

                # 6. Delete the "Searching..." message
                if searching_msg_id:
                    delete_telegram_message(searching_msg_id)
                
                # 7. Send the final photo with caption and keyboard
                send_telegram_photo(final_caption, static_map_url, inline_keyboard)
                
            else:
                send_telegram_message("Please format your request as: `Origin to Destination`.")
        except Exception as e:
            print(f"An error occurred during execution: {e}")
            send_telegram_message("Oops! Something went wrong. I couldn't find that route, please check the locations.")
