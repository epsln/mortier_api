from fastapi import FastAPI, Response
from pydantic import BaseModel, Field
from typing import Annotated, Tuple, Literal
from mortier.tesselation import RegularTesselation, HyperbolicTesselation, PenroseTesselation
from mortier.writer import SVGWriter 
from fastapi.middleware.cors import CORSMiddleware
import json
import random

app = FastAPI()
with open('data/database.json', 'r') as file:
    js = json.load(file)

TESS_IDS = list(js.keys())
TESS_IDS.append("random")
class Params(BaseModel):
    tess_type: Literal["regular", "hyperbolic", "penrose"]
    tess_id: Literal["random", "t3001", "t3003"]
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
    n_sides: int
    n_neigh: int
    depth: int
    refinements: int
    half_plane: bool
    parametrisation: Literal["none", "simplex", "perlin"]
    ornement: Literal["none", "bands", "laces"]
    bands_width: float 
    hatching: Literal["none", "line", "dot"]
    cross_hatch: bool
    hatch_spacing: int


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
    writer = SVGWriter("out", size = (0, 0, 300, 200))
    writer.api_mode = True
    if params.tess_id == "random":
        tess_id = random.choice(list(js.keys()))
    else:
        tess_id = params.tess_id 
    writer.n_tiles = params.scale 
    tess = js[tess_id]
    if params.tess_type == "regular":
        tesselation = RegularTesselation(writer, tess, tess_id)
    elif params.tess_type == "hyperbolic":
        tesselation = HyperbolicTesselation(writer, params.n_sides, params.n_neigh, params.depth)
        tesselation.half_plane = params.half_plane
        print(params.half_plane)
        tesselation.refine_tiling(params.refinements)
    else:
        tesselation = PenroseTesselation(writer)
    tesselation.set_angle(params.angle)
    if params.ornement == "bands":
        writer.bands_mode = True 
    if params.ornement == "laces":
        writer.lacing_mode = True 
    writer.bands_width = params.bands_width
    #writer.bezier_curve = bezier 
    writer.hatch_fill_parameters["angle"] = 0  
    writer.hatch_fill_parameters["spacing"] = params.hatch_spacing
    writer.hatch_fill_parameters["crosshatch"] = params.cross_hatch 
    if params.hatching == "none":
        writer.hatch_fill_parameters["type"] = None
    else:
        writer.hatch_fill_parameters["type"] = params.hatching 
    svg = tesselation.draw_tesselation()

    return Response(svg, media_type="image/svg+xml")
