from __future__ import print_function

import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
#from googleapiclient.errors import HttpError
import os

import openai
from api_key import api_key, chatgpt_model
import traceback
import time

from utils import chunk_text, get_unread_emails, mark_as_read_and_archive, mark_as_read, create_email, send_email, get_email_data

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.modify']

def email_summarizer(text):
    text_chunks = chunk_text(text, 3000)  # Use a smaller character limit to accommodate token limits
    summarized_chunks = []
    
    for idx, email_text in enumerate(text_chunks):
        if idx >= 5:
            break
        if len(email_text) > 0:
            # Set your OpenAI API key
            openai.api_key = api_key
            
            system_prompt = '''You are a language model that summarizes emails in 3-5 bullet points.'''
                                
            user_input = f'''Summarize the following in less than 100 words and only using 3-5 bullet points: {email_text}'''
                                        
            # Define a list of styles
            style = "Powerpoint slide with 3-5 bullet points"

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

def main():
    creds = None
    if os.path.exists('/home/ubuntu/github/gmail-summarizer/token.json'):
        creds = Credentials.from_authorized_user_file('/home/ubuntu/github/gmail-summarizer/token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('/home/ubuntu/github/gmail-summarizer/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('/home/ubuntu/github/gmail-summarizer/token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)

    # Retrieve unread emails in the inbox
    unread_emails = get_unread_emails(service)

    # Start with an empty string or list to store the email summaries
    email_summaries = ""

    # Get total number of unread emails
    total_emails = len(unread_emails)
    
    if total_emails >= 5:
        for idx, message in enumerate(unread_emails, start=1):
            try:
                # Retrieve the email text
                email_data = get_email_data(service, message['id'])
                print(f"Trying subject '{email_data['subject']}'.")

                # Submit the email text to the email_summarizer function and print the output
                if 'text' in email_data:
                    summary = email_summarizer(email_data['text'])
                    # Loop until the summary is fewer than 150 words
                    while len(summary.split()) >= 125:
                        # You can adjust the parameters of the email_summarizer function if necessary
                        summary = email_summarizer(summary)
                else:
                    summary = "Skipping email because no text content was found."
                    print(f"Skipping email with ID {email_data['id']} because no text content was found.")

                # Add the output to an ongoing list or string called email_summaries
                email_summaries += f"From: {email_data['from']}\n"
                email_summaries += f"Subject: {email_data['subject']}\n"
                email_summaries += f"Timestamp: {email_data['date']}\n"
                email_summaries += f"Link: https://mail.google.com/mail/u/0/#inbox/{message['id']}\n"
                email_summaries += f"Summary:\n{summary}\n\n\n"

                # Mark the summarized emails as read and archived
                if "Skipping email because no text content was found." not in summary and "Email Summaries" not in email_data['subject']:
                    mark_as_read_and_archive(service, message['id'])
                if "Email Summaries" in email_data['subject']:
                    mark_as_read(service, message['id'])
                
                print(f"({idx} of {total_emails}) emails processed.")
            except:
                traceback.print_exc()
                continue

        # Compose an email with the contents of email_summaries
        composed_email = create_email("trentleslie@gmail.com", "trentleslie@gmail.com", "Email Summaries", email_summaries)

        # Send the composed email to trentleslie@gmail.com
        send_email(service, composed_email)
    else:
        print("Not enough emails to run.")

if __name__ == '__main__':
    main()