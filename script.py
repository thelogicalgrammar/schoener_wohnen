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
import langchain
from langchain import PromptTemplate, FewShotPromptTemplate
from langchain.prompts.example_selector.base import BaseExampleSelector
from langchain.example_generator import generate_example
from langchain.llms import OpenAI
from langchain.chains.llm import LLMChain
from langchain.chains import SequentialChain, TransformChain
from langchain.chat_models import ChatOpenAI
from langchain.agents.tools import Tool
from langchain.agents import initialize_agent
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")


def get_calendars_list(service):
    calendars_list = service.calendarList().list().execute()
    return calendars_list.get("items", [])


def get_calendar_id(service, calendar_name):
    calendars_list = get_calendars_list(service)
    for calendar in calendars_list:
        if calendar["summary"] == calendar_name:
            return calendar["id"]
    return None


def define_tools(creds):

    calendar_service = build(
        'calendar',
        'v3',
        credentials=creds
    )
    # Find the calendar ID for the desired calendar
    calendar_name = "schoener-wohnen"  
    calendar_id = get_calendar_id(
        calendar_service,
        calendar_name
    )

    if calendar_id is None:
        print(f"No calendar found with name '{calendar_name}'")
        return

    ####### create event #######
    create_json_tool_description = (
        "This tool adds a new event to the Google Calendar. "
        "Before you use this tool, make sure to check if the event already exists in the Google Calendar.\n"
        "The input to this tool is a JSON-formatted value encoding a Google Calendar event.\n"
        "The event should have ALL the following fields:\n"
        "- summary\n"
        "- description\n"
        "- end\n"
        "- start\n"
        "- location\n"
        "\n"
        "Start and end should be dictionaries with the field dateTime, "
        "which should be a string in the ISO 8601 format, "
        "and the field timeZone, which should be the CET.\n"
        "Don't forget to include both the start and end times in the event.\n"
        "The output of this tool is the server output of attempting to add the event to a Google Calendar.\n"
    )

    def create_event_tool_f(**event_json):
        try:
            event = (
                calendar_service
                .events()
                .insert(calendarId=calendar_id, body=event_json)
                .execute()
            )
            return f"Event created: {event.get('htmlLink')}"
        except HttpError as err:
            return err

    json_create_tool = Tool(
        name='calendar-event-creator',
        description=create_json_tool_description,
        func=create_event_tool_f,
    )

    ####### Check if event exists #######
    check_json_tool_description = (
        "This tool checks if an event already exists in the Google Calendar.\n"
        "The input to this tool is a JSON-formatted value encoding a Google Calendar event.\n"
        "The event should have ALL the following fields:\n"
        "- summary\n"
        "- description\n"
        "- end\n"
        "- start\n"
        "- location\n"
        "\n"
        "Start and end should be dictionaries with the field dateTime, "
        "which should be a string in the ISO 8601 format, "
        "and the field timeZone, which should be the CET.\n"
        "Don't forget to include both the start and end times in the event.\n"
        "The output of this tool is a boolean value indicating whether the event already exists in the Google Calendar.\n"
    )

    def check_event_tool_f(**event_json):
        try:
            time_min = event_json["start"]["dateTime"]
            time_max = event_json["end"]["dateTime"]

            events_list = (
                calendar_service
                .events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime"
                ).execute()
            )

            for event in events_list.get("items", []):
                if (
                    event.get("location") == event_json.get("location") and
                    event["start"].get("dateTime") == event_json["start"]["dateTime"] and
                    event["end"].get("dateTime") == event_json["end"]["dateTime"]
                ):
                    return "Event already exists"

            return "Event does not exist yet"

        except HttpError as err:
            return err

    json_check_tool = Tool(
        name='calendar-event-checker',
        description=check_json_tool_description,
        func=check_event_tool_f,
    )

    return [
        json_create_tool,
        json_check_tool
    ] 


def agent_to_event(email, creds):

    prompt = PromptTemplate(
        template = (
            "Your task is to create one or more Google Calendar events, based on the text of an email, "
            "if the events do not already exist.\n"
            "The language of the email body is either German or English.\n"
            "To achieve your task, you have various tools at your disposal. "
            "First, calendar-event-checker checks if an event already exists in the Google Calendar. "
            "Second, calendar-event-creator creates a new event in the Google Calendar.\n"
            "To achieve your task, first check if the event(s) already exist in the Google Calendar. "
            "Only if the event does not already exist, use the Google Calendar API tool to create the event(s).\n"
            "If the event already exists or no event can be found in the email, you can stop.\n"
            "Make sure to check if an event already exists before creating it.\n"
            "\n\n"
            "Date that the email was sent:\n"
            "{date}\n"
            "\n\n"
            "Email body:\n"
            "{body}\n"
        ),
        input_variables = ['body', 'date'],
    )

    model = ChatOpenAI(
        temperature=0.1,
        request_timeout=120
    )

    tools = define_tools(creds)

    agent = initialize_agent(
        tools=tools,
        llm=model,
        agent='chat-zero-shot-react-description',
        verbose=True,
    )

    try:

        email_body = email['body']
        email_date = email['date']

        value = agent.run({
            'input': {
                'body': email_body,
                'date': email_date,
            }
        })
    except langchain.schema.OutputParserException:
        print("Parsing error, moving onto next email")


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


def get_header_value(headers, name):
    for header in headers:
        if header["name"].lower() == name.lower():
            return header["value"]
    return None


def get_emails_matching_subject_pattern(service):
    query = f'subject:"[schoener-wohnen-tuebingen]" newer_than:15d'
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get("messages", [])

    emails = []
    for message in messages:
        msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()
        email_body = get_email_body(msg)
        email_date = get_header_value(msg["payload"]["headers"], "Date")
        if email_body is not None:
            emails.append({"body": email_body, "date": email_date})

    return emails


def main():

    creds = get_credentials()
    gmail_service = build(
        'gmail',
        'v1',
        credentials=creds
    )

    emails = get_emails_matching_subject_pattern(
        gmail_service
    )

    for email in emails:

        print("Working on next email from " + email["date"])

        # check if email has been processed already from a json file
        # if so, skip it
        with open("email_dates.json", "r") as f:
            email_dates = json.load(f)
            if email["date"] in email_dates:
                print("Email already processed, moving onto next email")
                continue

        # add email date to json file
        with open("email_dates.json", "w") as f:
            email_dates.append(email["date"])
            json.dump(email_dates, f)

        agent_to_event(
            email,
            creds
        )


if __name__ == '__main__':
    print("Starting")
    main()

