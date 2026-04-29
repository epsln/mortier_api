from fastapi import FastAPI, Response,  HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.gzip import GZipMiddleware

from pydantic import BaseModel, Field, PositiveInt, PositiveFloat, NonNegativeInt, NonNegativeFloat, field_validator
from typing import Annotated, Tuple, Literal, Optional, Union


import time 
import json
import random

import cairosvg

import io
import os

import httpx
import stripe
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Optional
import boto3

app = FastAPI()

origins = [
        "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=9)

#app.add_middleware(
#    CORSMiddleware,
#    allow_origins=os.environ.get("ALLOWED_ORIGINS", "https://mortier.planch.es").split(","),
#    allow_methods=["POST"],
#    allow_headers=["Content-Type"],
#)

stripe.api_key   = os.environ["STRIPE_SECRET_KEY"]
S3_ACCESS_KEY       = os.environ["AWS_S3_ACCESS_KEY"]
S3_SECRET_ACCESS_KEY       = os.environ["AWS_S3_SECRET_ACCESS_KEY"]
GELATO_KEY       = os.environ["GELATO_API_KEY"]
WEBHOOK_SECRET   = os.environ["STRIPE_WEBHOOK_SECRET"]
MORTIER_URL      = os.environ.get("MORTIER_API_URL", "https://mortier.planch.es/tiling")
SUCCESS_URL      = os.environ.get("SUCCESS_URL", "https://mortier.planch.es/mortier/")
CANCEL_URL       = os.environ.get("CANCEL_URL",  "https://mortier.planch.es/mortier/")

# ⚠️  Verify Gelato product UIDs against your Gelato catalog before going live.
# Log in at gelato.com → Catalog → find the UID for each product you want to offer.
PRODUCTS = {
    "card_15x20": {
        "name":        "Card (15x20cm)",
        "price_cents": 1500,                                   # €15.00
        "gelato_uid":  "flat_150x200-mm-6x8-inch_170-gsm-65lb-uncoated_4-0_ver",
        "size":        [1772, 2362],                           # 15x20cm in portrait @ 300 dpi
    },
    "poster_a4": {
        "name":        "A4 Poster (21x29.7cm)",
        "price_cents": 2000,                                   # €20.00
        "gelato_uid":  "flat_a4-8x12-inch_170-gsm-65lb-uncoated_4-0_ver",
        "size":        [1748, 2480],                           # A4 portrait @ 300 dpi
    },
    "poster_a3": {
        "name":        "A3 Poster (29.7x42cm)",
        "price_cents": 2500,                                   # €25.00
        "gelato_uid":  "flat_a3_170-gsm-65lb-uncoated_4-0_ver",
        "size":        [2480, 3508],                           # A3 portrait @ 300 dpi
    },
}

import cairosvg
from PIL import Image
import io

import re

def get_svg_size(svg_data: str):
    match = re.search(r'viewBox="([^"]+)"', svg_data)
    if not match:
        return 1000, 1000  # fallback

    values = re.split(r'[,\s]+', match.group(1).strip())

    if len(values) != 4:
        return 1000, 1000  # fallback

    _, _, w, h = map(float, values)
    return w, h

def render_svg_cover(svg_data: str, target_width: int, target_height: int) -> Image.Image:
    # Step 1 — Render SVG at high enough resolution
    # First, we need an estimate of SVG size
    # If your SVG has a viewBox, extract it (recommended)

    # For simplicity, assume square fallback if unknown
    svg_width, svg_height = get_svg_size(svg_data) 

    scale = max(target_width / svg_width, target_height / svg_height)

    render_width = int(svg_width * scale)
    render_height = int(svg_height * scale)

    # Step 2 — Render SVG to PNG buffer
    png_bytes = cairosvg.svg2png(
        bytestring=svg_data.encode("utf-8"),
        output_width=svg_width * scale,
        output_height=svg_height * scale
    )

    img = Image.open(io.BytesIO(png_bytes))

    # Step 3 — Center crop
    left = (render_width - target_width) // 2
    top = (render_height - target_height) // 2
    right = left + target_width
    bottom = top + target_height

    img = img.crop((left, top, right, bottom))

    return img

class PrintRequest(BaseModel):
    product_id:            str
    svg:            str           

@app.post("/api/print")
async def create_print_session(body: PrintRequest):
    product = PRODUCTS.get(body.product_id)
    s3 = boto3.client(
        "s3",
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_ACCESS_KEY,
        region_name="us-east-1"
    )
    if not product:
        raise HTTPException(400, "Unknown product")

    async with httpx.AsyncClient(timeout=60.0) as client:
        file_id = f"{hash(body.svg + body.product_id)}.png"
        img = render_svg_cover(body.svg, PRODUCTS[body.product_id]['size'][0], 
                                         PRODUCTS[body.product_id]['size'][1])
        img.save(file_id)
        s3.upload_file(
            f'{file_id}',
            "s3-mortier-img-orders",
            f'tilings_order/{file_id}',
        )
        file_url = f"https://s3-mortier-img-orders.s3.us-east-1.amazonaws.com/tilings_order/{file_id}"
        print(file_url)

    # 4 ── Create Stripe Checkout session
    #      The user enters their shipping address and pays here.
    #TODO: Add upload to S3 to keep the image
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency":     "eur",
                "unit_amount":  product["price_cents"],
                "product_data": {"name": product["name"],
                                 "images": [file_url]},

            },
            "quantity": 1,
        }],
        mode="payment",
        shipping_address_collection={
            "allowed_countries": ["FR", "BE", "DE", "NL", "LU", "ES", "IT", "PT", "AT", "CH", "GB"],
        },
        shipping_options=[{
        "shipping_rate_data": {
            "type":         "fixed_amount",
            "fixed_amount": {"amount": 0, "currency": "eur"},
            "display_name": "Standard shipping",
            "delivery_estimate": {
                "minimum": {"unit": "business_day", "value": 3},
                "maximum": {"unit": "business_day", "value": 7},
            },
        },
        }],
        # We pass the Gelato file ID through Stripe metadata so the webhook can use it.
        metadata={
            "tiling_s3_url":    file_url,
            "gelato_product_uid": product["gelato_uid"],
        },
        success_url=SUCCESS_URL,
        cancel_url=CANCEL_URL,
    )
    return {"checkout_url": session.url}

@app.get("/files/{id}")
def serve_file(id):
    return FileResponse(f"/tmp/{id}.png")

import requests 

@app.post("/api/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig     = request.headers.get("stripe-signature", "")
    headers = {
        'Content-Type': 'application/json',
        'X-API-KEY': f'{GELATO_KEY}'
    }

    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Bad signature")

    if event["type"] == "checkout.session.completed":
        s        = event["data"]["object"]
        meta     = s["metadata"]
        shipping = s['customer_details']
        firstName = shipping["name"].split(" ")[0]
        lastName = ' '.join(shipping["name"].split(" ")[1:])
        address = shipping["address"] 
        print(s['metadata']['tiling_s3_url'])
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # ⚠️  Verify this endpoint against the current Gelato API docs.
            # === Set-up order request ===
            orderUrl = "https://order.gelatoapis.com/v4/orders"
            orderJson = {
                "orderType": "order",
                "orderReferenceId": s["id"],
                "customerReferenceId": s['customer_details']["email"],
                "currency": s['currency'].upper(),
                "items": [
                    {
                        "itemReferenceId": f"tiling-custom{s['id']}",
                        "productUid": s['metadata']["gelato_product_uid"] ,
                        "files": [
                            {
                                "type": "default",
                                "url": s['metadata']['tiling_s3_url']
                            }
                        ],
                        "quantity": 1
                    }
                ],        
                "shipmentMethodUid": "express",
                "shippingAddress": {
                    "companyName": "",
                    "firstName":    firstName,
                    "lastName":     lastName,
                    "addressLine1": address["line1"],
                    "addressLine2": address["line2"],
                    "state": address["state"],
                    "city":         address["city"],
                    "postCode":     address["postal_code"],
                    "country":      address["country"],
                    "email":      s['customer_details']["email"],
                    "phone":      s['customer_details']["phone"],
                    }
            }
            # === Send order request ===
            response = requests.request("POST", orderUrl, json=orderJson, headers=headers)
            response.raise_for_status()

    return {"received": True}
