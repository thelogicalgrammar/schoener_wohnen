# Automatic event creation from schoener-wohnen mailing list

This project aims at automatically adding events from the emails in Tübingen's shoener-wohnen mailing list (of which I'm a big fan) to a google calendar. It was a Sunday afternoon project so there's more to do, but the current basic version is working. 

# Setup

## Gmail and google calendar API access

To set up the project and run the script, you'll need to set up API access for both Gmail and Google Calendar. Before you start, make sure to follow these steps:

- Go to the Google Developers Console: https://console.developers.google.com/
- Create a new project, or use an existing one.
- Enable both the Gmail API and the Google Calendar API for your project.
- Create OAuth 2.0 credentials and download the JSON file.
- Install the required libraries: google-auth, google-auth-oauthlib, google-auth-httplib2, google-api-python-client.

You should use an OAuth 2.0 Client ID of the "Desktop app" type. This type of Client ID is appropriate for command-line applications or other native applications that run on your local machine. To create a new OAuth 2.0 Client ID, follow these steps:

- Go to the Google Developers Console: https://console.developers.google.com/
- Select your project or create a new one.
- In the left-hand menu, click on "Credentials."
- Click the "Create credentials" button and select "OAuth client ID."
- Choose "Desktop app" as the application type.
- Enter a name for your OAuth 2.0 Client ID (e.g., "Gmail and Calendar Script") and click "Create."
- After you've created the Client ID, you'll be provided with the client ID and client secret. However, for this script, you should download the JSON configuration file by clicking on the download icon next to your newly created client ID in the "Credentials" page. Save the file as credentials.json and place it in the same directory as your Python script. The script will use this file to authenticate and authorize your application.

## OpenAI w/ langchain

- You'll need to install openai and langchain for the conversion from the email text to a json event 
- You'll need an openAI account with API access (or set it up to use an open access LLM).
- You'll need beautifulsoup to parse the emails.
- You'll need the dotenv library. Store your credentials in a .env file in the project folder.

## New calendar

You'll also need to create a google calendar called `shoener-wohnen`, in which the events will be added.

# TODO

- Deal with inputs that are too long, e.g. truncate after max number of tokens. Or possibly first summarize the text.
- Sometimes the json isn't well formatted. Do something about that.
- Deal with emails which contain multiple events, e.g., over multiple days.
- Deal with events that don't have a precise begin/end.
- Add support for open access LLM.

