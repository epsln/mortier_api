from fastapi import FastAPI, Response,  HTTPException
from fastapi.middleware.gzip import GZipMiddleware

from pydantic import BaseModel, Field, PositiveInt, PositiveFloat, NonNegativeInt, NonNegativeFloat
from typing import Annotated, Tuple, Literal, Optional

from mortier.tesselation import RegularTesselation, HyperbolicTesselation, PenroseTesselation
from mortier.writer import SVGWriter 
from mortier.enums import TileType, ParamType, HatchType, OrnementsType, TesselationType, RegularTesselationType
from mortier.writer.hatching import Hatching
from mortier.writer.ornements import Ornements
from fastapi.middleware.cors import CORSMiddleware

import json
import random
import time

app = FastAPI()
with open('data/database.json', 'r') as file:
    js = json.load(file)

TESS_IDS = list(js.keys())
TESS_IDS.append("random")

class RegularTessParameters(BaseModel):
    tess_id: RegularTesselationType

class HyperbolicTessParameters(BaseModel):
    n_sides: PositiveInt 
    n_neigh: PositiveInt 
    depth: PositiveInt 
    refinements: int 
    half_plane: bool

class AngleParametrisation(BaseModel):
    type: ParamType

class PenroseTessParameters(BaseModel):
    tile:  Literal[TileType.P2, TileType.P3]

class OrnementsParameters(BaseModel):
    type:  OrnementsType
    width: NonNegativeFloat

class HatchingParameters(BaseModel):
    type: HatchType
    spacing: PositiveFloat
    cross_hatch: bool 
    angle: float
 
class Params(BaseModel):
    tess_type: TesselationType 
    tess_id: RegularTesselationType 
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
    ornements: Optional[OrnementsParameters] = None
    hatching: Optional[HatchingParameters] = None
    color_line: Tuple[NonNegativeInt, NonNegativeInt, NonNegativeInt] = [255, 255, 255]

   
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

app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

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

    if (params.ornements):
        writer.ornements = Ornements(type = params.ornements.type, 
                                     width = params.ornements.width) 
    writer.color_line = params.color_line
    tesselation.set_angle(params.angle)
    if params.hatching:
        hatch_type = Hatching(
            angle=params.hatching.angle,
            spacing=params.hatching.spacing,
            crosshatch=params.hatching.cross_hatch,
            type=params.hatching.type,
        )
        writer.hatching = hatch_type
    if params.angle_parametrisation:
        tesselation.set_param_mode(params.angle_parametrisation)
    tesselation.writer = writer
    t = time.time()
    svg = tesselation.draw_tesselation()
    
    return Response(svg)
