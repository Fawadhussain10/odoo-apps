import urllib
from urllib.request import Request, urlopen
import json
import requests

#Documentation link: https://docs.google.com/document/d/150Opv-aEBfDk4pGdjFmE2VDND_1VnFvltb8UaHcHVR0

def SentNotification(domain, token):
    data = """{
  "field": "messages",
  "value": {
    "messaging_product": "whatsapp",
    "metadata": {
      "display_phone_number": "16505551111",
      "phone_number_id": "123456123"
    },
    "contacts": [
      {
        "profile": {
          "name": "test user name"
        },
        "wa_id": "16315551181"
      }
    ],
    "messages": [
      {
        "from": "16315551181",
        "id": "ABGGFlA5Fpa",
        "timestamp": "1504902988",
        "type": "text",
        "text": {
          "body": "this is a text message"
        }
      }
    ]
  }
}"""
    url = domain + '/pb/waba/webhooks'
    return requests.post(url, data, headers={'accept': 'application/json', 'Content-Type': 'application/json'})

domain = 'http://localhost:8069'
token = 'pb'

reply = SentNotification(domain, token)

print ("-------",reply,reply.text);