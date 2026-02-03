from fastapi import FastAPI, Response
from pydantic import BaseModel, Field
from typing import Annotated, Tuple
from mortier.tesselation import RegularTesselation
from mortier.writer import SVGWriter 
from fastapi.middleware.cors import CORSMiddleware
import json
import random

app = FastAPI()

class Params(BaseModel):
    size: Annotated[
        Tuple[int, int],
        Field(
            description="Width and height as two integers",
            min_length=2,
            max_length=2
        )
    ]
    scale: int
    angle: float

with open('data/database.json', 'r') as file:
    js = json.load(file)

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

@app.post("/tiling")
def tiling(params: Params):
    writer = SVGWriter("out")
    writer.api_mode = True
    writer.output_size = [0, 0, params.size[0], params.size[1]]
    tess_id = random.choice(list(js.keys()))
    writer.n_tiles = params.scale 
    tess = js[tess_id]

    tesselation = RegularTesselation(writer, tess, tess_id)
    tesselation.set_angle(params.angle)
    
    svg = tesselation.draw_tesselation()

    return Response(svg, media_type="image/svg+xml")
