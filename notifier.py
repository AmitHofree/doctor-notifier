import requests
from bs4 import BeautifulSoup
import os
import re
import json
import time
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}/"
CHAT_IDS_FILE = "active_chat_ids.json"
LAST_APPOINTMENT_FILE = "last_appointment.json"
TELEGRAM_POLL_INTERVAL = 1  # 1 second for Telegram API polling
WEB_PAGE_POLL_INTERVAL = 60  # 60 seconds for web page polling
APPOINTMENT_URL = os.getenv("APPOINTMENT_URL")

# Configure logging to output to STDOUT
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

last_web_poll_time = 0
last_telegram_poll_time = 0

def load_chat_ids():
    try:
        with open(CHAT_IDS_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning("Starting without an existing chat IDs file. Reason: %s", e)
        return []

def save_chat_ids(chat_ids):
    try:
        with open(CHAT_IDS_FILE, "w") as file:
            json.dump(chat_ids, file)
    except Exception as e:
        logging.error("Could not save chat IDs to file. Reason: %s", e)

def load_last_appointment():
    try:
        with open(LAST_APPOINTMENT_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_last_appointment(appointment_date):
    with open(LAST_APPOINTMENT_FILE, "w") as file:
        json.dump({"date": appointment_date}, file)

def fetch_appointment_date():
    try:
        response = requests.get(APPOINTMENT_URL)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            # Find the script tag that contains the JSON variable
            script_content = None
            for script in soup.find_all("script"):
                if 'window.__INITIAL_STATE__' in script.text:
                    script_content = script.text
                    break

            if script_content:
                # Extract the JSON string
                json_str_match = re.search(r'window\.__INITIAL_STATE__ = ({.*?})\s*;', script_content, re.DOTALL)
                if json_str_match:
                    json_str = json_str_match.group(1)
                    data = json.loads(json_str)
                    # Extract the appointment date from the JSON data
                    full_date_str = data.get("info", {}).get("infoResults", {}).get("AppointmentDateTime")
                    if full_date_str:
                        # Extract only the numerical part of the date string
                        numerical_date_match = re.search(r'\d{2}/\d{2}/\d{2,4}', full_date_str)
                        if numerical_date_match:
                            numerical_date = numerical_date_match.group(0)
                            return numerical_date
    except Exception as e:
        logging.error("Failed to fetch or parse appointment date: %s", e)
    return None

def is_appointment_within_next_days(appointment_date_str):
    """Check if the appointment date is within the next 30 days."""
    try:
        # Assuming the date format is DD/MM/YYYY
        appointment_date = datetime.strptime(appointment_date_str, "%d/%m/%y")
        today = datetime.today()
        thirty_days_later = today + timedelta(days=60)
        return today <= appointment_date <= thirty_days_later
    except ValueError:
        logging.error("Error parsing the appointment date: %s", appointment_date_str)
        return False

def check_and_notify_users(chat_ids, last_appointment_date, new_appointment):
    if new_appointment and new_appointment != last_appointment_date:
        # Update the state every time regardless of the date check
        save_last_appointment(new_appointment)
        if is_appointment_within_next_days(new_appointment):
            for chat_id in chat_ids:
                send_message(chat_id, f"New available appointment date: {new_appointment}")
            logging.info("Notified users of new appointment date: %s", new_appointment)
        else:
            logging.info("New appointment date is not within the next 30 days: %s", new_appointment)
        return new_appointment  # Update the in-memory tracking with the new appointment date
    return last_appointment_date  # Return the old date if no update was necessary

def get_updates(last_update_id):
    try:
        response = requests.get(URL + "getUpdates", params={"offset": last_update_id + 1}, timeout=10)
        response.raise_for_status()
        return response.json().get("result", [])
    except requests.exceptions.RequestException as e:
        logging.error("Error fetching updates: %s", e)
        return []

def send_message(chat_id, text):
    try:
        response = requests.post(URL + "sendMessage", data={"chat_id": chat_id, "text": text}, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error("Error sending message to %s: %s", chat_id, e)

def handle_updates(updates, chat_ids):
    last_update_id = 0
    for update in updates:
        try:
            if "message" in update:
                message = update["message"]
                chat_id = message["chat"]["id"]
                text = message.get("text", "")
                last_update_id = update["update_id"]

                if text == "/start":
                    intro_message = ("Welcome to the Doctor Appointment Notification Bot!\n"
                                     "Use this bot to get notified about doctor appointment availabilities.\n\n"
                                     "Commands:\n"
                                     "/register - Register for new updates.\n"
                                     "/unregister - Unregister from updates.")
                    send_message(chat_id, intro_message)
                    logging.info("User %s started the bot.", chat_id)

                elif text == "/register":
                    if chat_id in chat_ids:
                        send_message(chat_id, "You are already registered for updates!")
                        logging.info("User %s attempted to register again.", chat_id)
                    else:
                        chat_ids.append(chat_id)
                        send_message(chat_id, "You are now registered for updates.")
                        logging.info("User %s registered for updates.", chat_id)

                elif text == "/unregister":
                    if chat_id not in chat_ids:
                        send_message(chat_id, "You are not registered for updates.")
                        logging.info("User %s attempted to unregister but was not registered.", chat_id)
                    else:
                        chat_ids.remove(chat_id)
                        send_message(chat_id, "You are now unregistered from updates.")
                        logging.info("User %s unregistered from updates.", chat_id)
                        
        except KeyError as e:
            logging.error("Error processing an update: %s", e)

    return last_update_id, chat_ids

def main():
    last_update_id = 0
    chat_ids = load_chat_ids()
    last_appointment = load_last_appointment().get("date", None)

    global last_web_poll_time
    global last_telegram_poll_time

    while True:
        current_time = time.time()

        # Telegram API Polling
        if current_time - last_telegram_poll_time >= TELEGRAM_POLL_INTERVAL:
            updates = get_updates(last_update_id)
            if updates:
                last_update_id, chat_ids = handle_updates(updates, chat_ids)
                save_chat_ids(chat_ids)
            last_telegram_poll_time = current_time

        # Web Page Polling
        if current_time - last_web_poll_time >= WEB_PAGE_POLL_INTERVAL:
            new_appointment = fetch_appointment_date()
            last_appointment = check_and_notify_users(chat_ids, last_appointment, new_appointment)
            last_web_poll_time = current_time

        time.sleep(1)  # Sleep for the shortest interval

if __name__ == "__main__":
    main()
