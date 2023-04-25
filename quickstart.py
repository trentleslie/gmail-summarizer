from __future__ import print_function

import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import base64
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
from bs4 import BeautifulSoup

import openai
from api_key import api_key, chatgpt_model
import traceback
import time

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.modify']

def email_summarizer(text):
    text_chunks = chunk_text(text, 3000)  # Use a smaller character limit to accommodate token limits
    #print(text_chunks)
    summarized_chunks = []
    
    for email_text in text_chunks:
        if len(email_text) > 0:
            # Set your OpenAI API key
            openai.api_key = api_key
            
            system_prompt = '''You are a language model that summarizes emails. Summarize in paragraph form or bullet points where appropriate.'''
                                
            user_input = f'''Summarize the following: {email_text}'''
                                        
            # Define a list of styles
            style = "Conversational but terse and professional."

            # Build messages payload
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": style},
                {"role": "assistant", "content": "On what topic?"},
                {"role": "user", "content": user_input}
            ]
            
            max_retries = 3
            retry_count = 0
            retry_flag = True
            
            while retry_flag and retry_count < max_retries:
                try:
                    # Call the ChatCompletion endpoint
                    print("Calling OpenAI API...")
                    response = openai.ChatCompletion.create(
                            model = chatgpt_model,
                            messages=messages,
                            temperature = 1,
                            top_p = 1, 
                            presence_penalty = 0.5,
                            frequency_penalty = 0.4            
                        )
                    print("Successfully called OpenAI API.")
                    retry_flag = False
                except Exception:
                    print("Exception occurred in OpenAI API call. Retrying...")
                    retry_count += 1
            
            # Extract the generated text from the API response
            email_summary_chunk = (response['choices'][0]['message']['content'])
            
            summarized_chunks.append(email_summary_chunk)
            
            time.sleep(3)
        
    email_summary = ' '.join(summarized_chunks)

    return email_summary

def chunk_text(text, max_chars):
    paragraphs = re.split(r'\n+', text)
    chunks = []
    current_chunk = ''
    
    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) <= max_chars:
            current_chunk += paragraph + '\n'
        else:
            chunks.append(current_chunk.strip())
            current_chunk = paragraph + '\n'
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def get_unread_emails(service):
    query = "is:unread is:inbox"
    response = service.users().messages().list(userId='me', q=query).execute()
    messages = []

    if 'messages' in response:
        messages.extend(response['messages'])

    while 'nextPageToken' in response:
        page_token = response['nextPageToken']
        response = service.users().messages().list(userId='me', q=query, pageToken=page_token).execute()
        
        if 'messages' in response:
            messages.extend(response['messages'])

    return messages

def mark_as_read_and_archive(service, message_id):
    service.users().messages().modify(
        userId='me',
        id=message_id,
        body={'removeLabelIds': ['UNREAD', 'INBOX']}
    ).execute()

def create_email(sender, to, subject, body):
    message = MIMEMultipart()
    message['To'] = to
    message['From'] = sender
    message['Subject'] = subject
    message.attach(MIMEText(body, 'plain'))

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw_message}

def send_email(service, email):
    try:
        sent_message = service.users().messages().send(userId='me', body=email).execute()
        print(F'sent message to {email["to"]} Message Id: {sent_message["id"]}')
    except Exception as error:
        print(F'An error occurred: {error}')
        sent_message = None
    return sent_message

def remove_hyperlinks(text):
    # Remove URLs starting with http/https
    text = re.sub(r'http\S+', '', text)
    # Remove URLs containing '.com'
    text = re.sub(r'\S+\.com\S*', '', text)
    text = re.sub(r'\S+\.net\S*', '', text)
    text = re.sub(r'\S+\.org\S*', '', text)
    return text

def get_email_data(service, message_id):
    msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
    payload = msg['payload']
    headers = payload['headers']
    email_data = {'id': message_id}

    for header in headers:
        name = header['name']
        value = header['value']
        if name == 'From':
            email_data['from'] = value
        if name == 'Date':
            email_data['date'] = value
        if name == 'Subject':
            email_data['subject'] = value

    if 'parts' in payload:
        parts = payload['parts']
        data = None
        for part in parts:
            if part['mimeType'] == 'text/plain':
                data = part['body']['data']
            elif part['mimeType'] == 'text/html':
                data = part['body']['data']

        if data is not None:
            if data is not None:
                text = base64.urlsafe_b64decode(data.encode('UTF-8')).decode('UTF-8')
                soup = BeautifulSoup(text, 'html.parser')
                clean_text = soup.get_text()
                clean_text = remove_hyperlinks(clean_text)
                email_data['text'] = clean_text
            else:
                data = payload['body']['data']
                text = base64.urlsafe_b64decode(data.encode('UTF-8')).decode('UTF-8')
                soup = BeautifulSoup(text, 'html.parser')
                clean_text = soup.get_text()
                clean_text = remove_hyperlinks(clean_text)
                email_data['text'] = clean_text
    else:
        data = payload['body']['data']
        text = base64.urlsafe_b64decode(data.encode('UTF-8')).decode('UTF-8')
        soup = BeautifulSoup(text, 'html.parser')
        email_data['text'] = soup.get_text()

    return email_data

def main():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)

    # Retrieve unread emails in the inbox
    unread_emails = get_unread_emails(service)

    # Start with an empty string or list to store the email summaries
    email_summaries = ""

    # Get total number of unread emails
    total_emails = len(unread_emails)

    for idx, message in enumerate(unread_emails, start=1):
        try:
            # Retrieve the email text
            email_data = get_email_data(service, message['id'])
            print(f"Trying subject '{email_data['subject']}'.")

            # Submit the email text to the email_summarizer function and print the output
            if 'text' in email_data:
                summary = email_summarizer(email_data['text'])
                #print(summary)
            else:
                summary = "Skipping email because no text content was found."
                print(f"Skipping email with ID {email_data['id']} because no text content was found.")

            # Add the output to an ongoing list or string called email_summaries
            email_summaries += f"From: {email_data['from']}\n"
            email_summaries += f"Subject: {email_data['subject']}\n"
            email_summaries += f"Timestamp: {email_data['date']}\n"
            email_summaries += f"Summary:\n{summary}\n"
            
            # Add a hyperlink to the original email
            email_link = f"https://mail.google.com/mail/u/0/#inbox/{message['id']}"
            email_summaries += f"Link: {email_link}\n\n"

            # Mark the summarized emails as read and archived
            if "Skipping email because no text content was found." not in summary:
                mark_as_read_and_archive(service, message['id'])
            
            print(f"({idx} of {total_emails}) emails processed.")
        except:
            traceback.print_exc()
            continue

    # Compose an email with the contents of email_summaries
    composed_email = create_email("trentleslie@gmail.com", ["trentleslie@gmail.com"], "Email Summaries", email_summaries)

    # Send the composed email to trentleslie@gmail.com
    send_email(service, composed_email)

if __name__ == '__main__':
    main()