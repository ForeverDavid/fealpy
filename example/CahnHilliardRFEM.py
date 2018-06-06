import numpy as np

import matplotlib.pyplot as plt
import matplotlib.animation as animation

from fealpy.model.lcy  import CahnHilliardData1
from fealpy.femmodel.CahnHilliardRFEMModel import CahnHilliardRFEMModel 


def init():
    return lines, points

def animate(i):
    global fem
    fem.step()


pde = CahnHilliardData1(0, 10, )
fem = CahnHilliardRFEMModel(pde, 4, 0.001, 3)
