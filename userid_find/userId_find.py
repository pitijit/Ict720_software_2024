import os
import sys
import logging
from datetime import datetime
import json

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    FollowEvent,
    UnfollowEvent
)

# logging configuration
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# linebot configuration
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
liff_id = os.getenv('USER_ID_FIND_LIFF_ID', None)
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
channel_access_token = os.getenv('LINE_ACCESS_TOKEN', None)
if channel_access_token is None:
    print('Specify LINE_ACCESS_TOKEN as environment variable.')
    sys.exit(1)
if liff_id is None:
    print('Specify USER_ID_FIND_LIFF_ID as environment variable.')
    sys.exit(1)
configuration = Configuration(
    access_token=channel_access_token
)

# API URL
user_api_url = os.getenv('USER_API_URL', None)
if user_api_url is None:
    print('Specify USER_API_URL as environment variable.')
    sys.exit(1)
dev_api_url = os.getenv('DEV_API_URL', None)
if dev_api_url is None:
    print('Specify DEV_API_URL as environment variable.')
    sys.exit(1)

# start instance
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

handler = WebhookHandler(channel_secret)


@app.post("/callback")
async def handle_callback(request: Request):
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = await request.body()
    body = body.decode()
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return 'OK'

# code for web UI


@app.get('/')
async def liff_ui(request: Request):
    return templates.TemplateResponse(
        request=request, name="uid_index.html", context={"LIFF_ID": liff_id}
    )

# code to handle Follow event


@handler.add(FollowEvent)
def handle_follow_event(event):
    pass

# code to handle text messages