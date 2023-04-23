import os
from pprint import pprint
import base64
import re
import json
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bs4 import BeautifulSoup

import openai
from langchain import PromptTemplate, FewShotPromptTemplate
from langchain.prompts.example_selector.base import BaseExampleSelector
from langchain.example_generator import generate_example
from langchain.llms import OpenAI
from langchain.chains.llm import LLMChain
from langchain.chains import SequentialChain, TransformChain
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")


def body_to_event(email_body):
    # Process email_body and return a JSON-formatted Google Calendar event

    model = OpenAI(
        model_name='text-davinci-003',
        temperature=0.1,
    )

    prompt = PromptTemplate(
        template = (
            "Your task is to create a Google Calendar event from an email body.\n"
            "The language of the email body is either German or English.\n"
            "The output should be a JSON-formatted Google Calendar event.\n"
            "The event should have ALL the following fields:\n"
            "  - summary\n"
            "  - description\n"
            "  - end\n"
            "  - start\n"
            "  - location\n"
            "\n"
            "Start and end should be dictionaries with the field dateTime, "
            "which should be a string in the ISO 8601 format, "
            "and the field timeZone, which should be the CET.\n"
            "If the email body is not a valid event with and identifiable time and place, "
            "return an empty string. "
            "Don't forget to include both the start and end times in the event.\n"
            "\n\n"
            "Input:\n"
            "'''\n"
            "{body}\n"
            "'''\n"
            "\n"
            "Output:\n"
        ),
        input_variables = ['body']
    )

    chain = LLMChain(
        llm=model,
        prompt=prompt,
        verbose=True,
    )

    json_event = chain(email_body)

    return json_event


def get_credentials():
    creds = None
    token_file = "token.pickle"
    credentials_file = "credentials.json"
    
    if os.path.exists(token_file):
        with open(token_file, "rb") as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file,
                ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/calendar"])
            creds = flow.run_local_server(port=0)
        
        with open(token_file, "wb") as token:
            pickle.dump(creds, token)
    
    return creds


def get_email_part_text(part, mime_type):
    if part["mimeType"] == mime_type and "data" in part["body"]:
        return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
    if "parts" in part:
        for subpart in part["parts"]:
            text = get_email_part_text(subpart, mime_type)
            if text is not None:
                return text
    return None


def get_email_body(msg):
    payload = msg["payload"]
    text_plain = None
    text_html = None

    text_plain = get_email_part_text(payload, "text/plain")
    text_html = get_email_part_text(payload, "text/html")

    if text_html is not None:
        return BeautifulSoup(text_html, "html.parser").get_text()
    elif text_plain is not None:
        return text_plain

    return None


def get_emails_matching_subject_pattern(service):
    query = f'subject:"[schoener-wohnen-tuebingen]" newer_than:7d'
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get("messages", [])

    emails = []
    for message in messages:
        msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()
        email_body = get_email_body(msg)
        if email_body is not None:
            emails.append(email_body)

    return emails


def get_calendars_list(service):
    calendars_list = service.calendarList().list().execute()
    return calendars_list.get("items", [])


def get_calendar_id(service, calendar_name):
    calendars_list = get_calendars_list(service)
    for calendar in calendars_list:
        if calendar["summary"] == calendar_name:
            return calendar["id"]
    return None


def create_event(service, event_json, calendar_id):
    event = service.events().insert(calendarId=calendar_id, body=event_json).execute()
    print(f"Event created: {event.get('htmlLink')}")


def main():

    creds = get_credentials()
    gmail_service = build('gmail', 'v1', credentials=creds)
    calendar_service = build('calendar', 'v3', credentials=creds)

    emails = get_emails_matching_subject_pattern(
        gmail_service
    )

    # Find the calendar ID for the desired calendar
    calendar_name = "schoener-wohnen"  
    calendar_id = get_calendar_id(calendar_service, calendar_name)
    
    if calendar_id is None:
        print(f"No calendar found with name '{calendar_name}'")
        return

    for email in emails[:3]:

        json_event = body_to_event(email)['text']
        # clean from newline characters
        json_event = json_event.replace('\n', '')
        try:
            # parse as json
            json_event = json.loads(json_event)
        except json.decoder.JSONDecodeError:
            print("Error parsing event as JSON")

        print(json_event)

        try:
            # Create the event in the specified calendar
            create_event(calendar_service, json_event, calendar_id)
        except HttpError as e:
            print(f"Error creating event: {e}")

if __name__ == '__main__':
    main()

