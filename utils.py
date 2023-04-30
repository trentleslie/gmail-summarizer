import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
from bs4 import BeautifulSoup

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
    
def mark_as_read(service, message_id):
    service.users().messages().modify(
        userId='me',
        id=message_id,
        body={'removeLabelIds': ['UNREAD']}
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
        print(F'Successfully sent message.')
    except Exception as error:
        print(F'Error: {error} ')
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
