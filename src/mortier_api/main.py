from fastapi import FastAPI, Response,  HTTPException
from fastapi.middleware.gzip import GZipMiddleware

from pydantic import BaseModel, Field, PositiveInt, PositiveFloat, NonNegativeInt, NonNegativeFloat
from typing import Annotated, Tuple, Literal, Optional, Union

from mortier.tesselation import RegularTesselation, HyperbolicTesselation, PenroseTesselation
from mortier.writer import SVGWriter 
from mortier.writer.ornements import Ornements
from mortier.enums import TileType, ParamType, HatchType, OrnementsType, TesselationType, RegularTesselationType
from mortier.writer.hatching import Hatching
from mortier.writer.ornements import Ornements
from mortier.writer.hatching import Hatching
from fastapi.middleware.cors import CORSMiddleware

import time 
import json
import random

app = FastAPI()
with open('data/database.json', 'r') as file:
    js = json.load(file)

TESS_IDS = list(js.keys())
TESS_IDS.append("random")

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
        tesselation = PenroseTesselation(writer, tile = TileType[params.tess_parameters.tile], level = params.tess_parameters.depth)

    writer.ornements = params.ornements
    writer.hatching = params.hatching
    writer.color_line = params.color_line
    tesselation.set_angle(params.angle)
    if params.angle_parametrisation:
        tesselation.set_param_mode(params.angle_parametrisation)
    tesselation.writer = writer
    t = time.time()
    svg = tesselation.draw_tesselation()
    print(time.time() - t)
    
    return Response(svg)
