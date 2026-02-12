from fastapi import FastAPI, Response,  HTTPException
from pydantic import BaseModel, Field, PositiveInt, PositiveFloat, NonNegativeInt 
from typing import Annotated, Tuple, Literal
from mortier.tesselation import RegularTesselation, HyperbolicTesselation, PenroseTesselation
from mortier.writer import SVGWriter 
from mortier.enums import TileType, ParamType, HatchType 
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
        Tuple[PositiveInt, PositiveInt],
        Field(
            description="Width and height as two integers",
            min_length=2,
            max_length=2
        )
    ]
    scale: PositiveInt 
    angle: float
    n_sides: PositiveInt 
    n_neigh: PositiveInt 
    depth: PositiveInt 
    refinements: int 
    half_plane: bool
    parametrisation: Literal["none", "SIMPLEX", "PERLIN"]
    ornement: Literal["none", "bands", "laces"]
    bands_width: PositiveFloat 
    hatching: Literal["none", "LINE", "DOT"]
    cross_hatch: bool
    hatch_spacing: PositiveFloat
    tile:  Literal["P2", "P3"]
    color_line: Tuple[NonNegativeInt, NonNegativeInt, NonNegativeInt]

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
    writer = SVGWriter("out", size = (0, 0, 370, 220))
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
        if (params.n_sides - 2) * (params.n_neigh - 2) < 4:
            raise HTTPException(status_code=400, detail="Invalid parameters for hyperbolic tesselation. (n_neigh - 2) * (n_sides - 2) < 4.")
        tesselation = HyperbolicTesselation(writer, params.n_sides, params.n_neigh, params.depth)
        tesselation.half_plane = params.half_plane
        tesselation.refine_tiling(params.refinements)
    else:
        tesselation = PenroseTesselation(writer, tile = TileType[params.tile])
    tesselation.set_angle(params.angle)
    if params.ornement == "bands":
        writer.bands_mode = True 
    if params.ornement == "laces":
        writer.lacing_mode = True 
    writer.bands_width = params.bands_width
    writer.color_line = params.color_line
    #writer.bezier_curve = bezier 
    writer.hatch_fill_parameters["angle"] = 0  
    writer.hatch_fill_parameters["spacing"] = params.hatch_spacing
    writer.hatch_fill_parameters["crosshatch"] = params.cross_hatch 
    if params.hatching == "none":
        writer.hatch_fill_parameters["type"] = None
    else:
        writer.hatch_fill_parameters["type"] = HatchType[params.hatching]
        tesselation.set_param_mode(ParamType[params.parametrisation])
    tesselation.writer = writer
    svg = tesselation.draw_tesselation()

    return Response(svg, media_type="image/svg+xml")
