from fastapi import FastAPI, Response,  HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.gzip import GZipMiddleware

from pydantic import BaseModel, Field, PositiveInt, PositiveFloat, NonNegativeInt, NonNegativeFloat, field_validator
from typing import Annotated, Tuple, Literal, Optional, Union

from mortier.tesselation import RegularTesselation, HyperbolicTesselation, PenroseTesselation
from mortier.writer import SVGWriter 
from mortier.writer.ornements import Ornements
from mortier.enums import TileType, ParamType, HatchType, OrnementsType, TesselationType, RegularTesselationType, FileType
from mortier.writer.hatching import Hatching
from mortier.writer.ornements import Ornements
from mortier.writer.hatching import Hatching
from fastapi.middleware.cors import CORSMiddleware

from matplotlib import colormaps

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

app = FastAPI()
with open('data/database.json', 'r') as file:
    js = json.load(file)

TESS_IDS = list(js.keys())
TESS_IDS.append("random")
VALID_COLORMAPS = set(colormaps())

class RegularTessParameters(BaseModel):
    type: Literal["regular"]
    tess_id: RegularTesselationType

class HyperbolicTessParameters(BaseModel):
    type: Literal["hyperbolic"]
    n_sides: PositiveInt 
    n_neigh: PositiveInt 
    depth: PositiveInt 
    refinements: int 
    half_plane: bool

class PenroseTessParameters(BaseModel):
    type: Literal["penrose"]
    tile:  Literal[TileType.P2, TileType.P3]
    depth: PositiveInt

class AngleParametrisation(BaseModel):
    type: ParamType

class OrnementsParameters(BaseModel):
    type:  OrnementsType
    width: NonNegativeFloat

class HatchingParameters(BaseModel):
    type: HatchType
    spacing: PositiveFloat
    cross_hatch: bool 
    angle: float
 
class Params(BaseModel):
    tess_parameters: Union[RegularTessParameters, 
                           HyperbolicTessParameters, 
                           PenroseTessParameters] = Field(discriminator = "type")
    size: Annotated[
        Tuple[PositiveInt, PositiveInt],
        Field(
            description="Width and height as two integers",
            min_length=2,
            max_length=2
        )
    ] = [200, 200]
    scale: PositiveInt = 70
    angle: float
    angle_parametrisation: Optional[ParamType] = None
    ornements: Optional[Ornements] = None
    hatching: Optional[Hatching] = None
    color_line: Tuple[NonNegativeInt, NonNegativeInt, NonNegativeInt] = [255, 255, 255]
    colormap: Optional[str] = None
    @field_validator("colormap")
    @classmethod
    def validate_colormap(cls, v):
        if v is not None and v not in VALID_COLORMAPS:
            raise ValueError(f"Invalid colormap '{v}'. Must be one of the matplotlib colormaps.")
        return v

   
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

@app.post("/tiling")
def tiling(params: Params):
    writer = SVGWriter("out", size = (0, 0, params.size[0], params.size[1]))
    writer.api_mode = True
    writer.n_tiles = params.scale 
    if params.tess_parameters.type == "regular":
        if params.tess_parameters.tess_id == "random":
            tess_id = random.choice(list(js.keys()))
        else:
            tess_id = params.tess_parameters.tess_id 
        tess = js[tess_id]
        tesselation = RegularTesselation(writer, tess, tess_id)
    elif params.tess_parameters.type == "hyperbolic":
        if (params.tess_parameters.n_sides - 2) * (params.tess_parameters.n_neigh - 2) < 4:
            raise HTTPException(status_code=400, detail="Invalid parameters for hyperbolic tesselation. (n_neigh - 2) * (n_sides - 2) < 4.")
        tesselation = HyperbolicTesselation(writer, 
                                            params.tess_parameters.n_sides,
                                            params.tess_parameters.n_neigh,
                                            params.tess_parameters.depth)
        tesselation.half_plane = params.tess_parameters.half_plane
        tesselation.refine_tiling(params.tess_parameters.refinements)
    else:
        writer.n_tiles = params.scale * 5
        tesselation = PenroseTesselation(writer, tile = TileType[params.tess_parameters.tile], level = params.tess_parameters.depth)

    writer.ornements = params.ornements
    writer.hatching = params.hatching
    writer.color_line = params.color_line
    if params.colormap:
        writer.set_colormap(colormaps[params.colormap])
    tesselation.set_angle(params.angle)
    if params.angle_parametrisation:
        tesselation.set_param_mode(params.angle_parametrisation)
    tesselation.writer = writer
    svg = tesselation.draw_tesselation()
    
    return Response(svg)


#app.add_middleware(
#    CORSMiddleware,
#    allow_origins=os.environ.get("ALLOWED_ORIGINS", "https://mortier.planch.es").split(","),
#    allow_methods=["POST"],
#    allow_headers=["Content-Type"],
#)

stripe.api_key   = os.environ["STRIPE_SECRET_KEY"]
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
    if not product:
        raise HTTPException(400, "Unknown product")

    async with httpx.AsyncClient(timeout=60.0) as client:
        file_id = f"{hash(body.svg + body.product_id)}.png"
        file_id = f"/tmp/test.png"
        img = render_svg_cover(body.svg, PRODUCTS[body.product_id]['size'][0], 
                                         PRODUCTS[body.product_id]['size'][1])
        img.save(file_id)

    # 4 ── Create Stripe Checkout session
    #      The user enters their shipping address and pays here.
    #TODO: Add upload to S3 to keep the image
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency":     "eur",
                "unit_amount":  product["price_cents"],
                "product_data": {"name": product["name"]
                                 "images": f"https://mortier_api.onrender.com/files/{file_id}"},

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
            "gelato_file_id":    file_id,
            "gelato_product_uid": product["gelato_uid"],
        },
        #success_url=SUCCESS_URL,
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
        shipping = s['collected_information'].get("shipping_details") or {}
        name = shipping.get("name", "")
        address = shipping.get("adress") or {}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # ⚠️  Verify this endpoint against the current Gelato API docs.
            # === Set-up order request ===
            orderUrl = "https://order.gelatoapis.com/v4/orders"
            orderJson = {
                "orderType": "order",
                "orderReferenceId": s["id"],
                "customerReferenceId": s['customer_details'].get("customer_email", ""),
                "currency": s['currency'].upper(),
                "items": [
                    {
                        "itemReferenceId": f"tiling-custom{s['id']}",
                        "productUid": s['metadata']["gelato_product_uid"] ,
                        "files": [
                            {
                                "type": "default",
                                "url": "https://cdn-origin.gelato-api-dashboard.ie.live.gelato.tech/docs/sample-print-files/logo.png"
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
                    "addressLine1": address.get("line1", ""),
                    "addressLine2": address.get("line2") or "",
                    "state": address.get("state") or "",
                    "city":         address.get("city", ""),
                    "postCode":     adress.get("postCode", ""),
                    "country":      adress.get("country", ""),
                    "email":      s['customer_details'].get("email", ""),
                    "phone":      s['customer_details'].get("phone", ""),
                    }
            }
            # === Send order request ===
            response = requests.request("POST", orderUrl, json=orderJson, headers=headers)
            response.raise_for_status()

    return {"received": True}
