import matplotlib.pyplot as plt
import numpy as np
import sys

from fealpy.mesh.meshio import load_mat_mesh, write_mat_mesh, write_mat_linear_system
from fealpy.mesh.simple_mesh_generator import rectangledomainmesh  
from fealpy.mesh.simple_mesh_generator import triangle, unitsquaredomainmesh

from fealpy.functionspace.tools import function_space 
from fealpy.femmodel.BiharmonicFEMModel import BiharmonicRecoveryFEMModel
from fealpy.boundarycondition.BoundaryCondition import DirichletBC
from fealpy.solver import solve
from fealpy.functionspace.function import FiniteElementFunction
from fealpy.erroranalysis.PrioriError import L2_error, div_error, H1_semi_error
from fealpy.model.BiharmonicModel2d import SinSinData, BiharmonicData2, BiharmonicData3, BiharmonicData4, BiharmonicData5, BiharmonicData6
from fealpy.tools.show import show_error_table 

from fealpy.tools.show import showmultirate

m = int(sys.argv[1]) 
meshtype = int(sys.argv[2])
rtype = int(sys.argv[3])
if rtype == 1:
    rtype='simple'
elif rtype == 2:
    rtype='inv_area'

print('rtype:', rtype)
sigma = 1

if m == 1:
    model = SinSinData()
    box = [0, 1, 0, 1]
elif m == 2:
    model = BiharmonicData2(1.0,1.0)
    box = [0, 1, 0, 1]
elif m == 3:
    model = BiharmonicData3()
    box = [0, 1, 0, 1]
elif m == 4:
    model = BiharmonicData4()
    box = [0, 1, 0, 1]
elif m == 5:
    model = BiharmonicData5()
    box = [-1, 1, -1, 1]

maxit = 4
degree = 1

Ndof = np.zeros((maxit,), dtype=np.int)

errorType = ['$\| u - u_h\|$',
         '$\|\\nabla u - \\nabla u_h\|$',
         '$\|\\nabla u_h - G(\\nabla u_h) \|$',
         '$\|\\nabla u - G(\\nabla u_h)\|$',
         '$\|\Delta u - \\nabla\cdot G(\\nabla u_h)\|$',
         '$\|\Delta u -  G(\\nabla\cdot G(\\nabla u_h))\|$',
         '$\|G(\\nabla\cdot G(\\nabla u_h)) - \\nabla\cdot G(\\nabla u_h)\|$'
         ]
errorMatrix = np.zeros((len(errorType), maxit), dtype=np.float)

h0 = 0.025
if (meshtype == 3):
    mesh = load_mat_mesh('../data/square'+str(1)+'.mat')

for i in range(maxit):
    if meshtype == 1: # uniform mesh 
        n = 20*2**i
        mesh = rectangledomainmesh(box, nx=n, ny=n)  
    elif meshtype == 2: # CVT mesh
        mesh = load_mat_mesh('../data/square'+str(i+2)+'.mat')
    elif meshtype == 3: # Delaunay uniform refine mesh 
        mesh.uniform_refine()
    elif meshtype == 4: # Delaunay mesh
        mesh = triangle(box, h0/2**i)
    elif meshtype == 5:
        mesh = load_mat_mesh('../data/sqaureperturb'+str(i+2)+'.'+str(0.5) + '.mat')

    V = function_space(mesh, 'Lagrange', degree)
    V2 = function_space(mesh, 'Lagrange_2', degree)
    uh = FiniteElementFunction(V)
    rgh = FiniteElementFunction(V2)
    rlh = FiniteElementFunction(V)

    fem = BiharmonicRecoveryFEMModel(V, model, sigma=sigma, rtype=rtype)
    bc = DirichletBC(V, model.dirichlet)
    solve(fem, uh, dirichlet=bc, solver='direct')
    fem.recover_grad(uh, rgh)
    fem.recover_laplace(rgh, rlh)

    eta1 = fem.grad_recover_estimate(uh, rgh)
    eta2 = fem.laplace_recover_estimate(rgh, rlh, etype=1, order=2)

    Ndof[i] = V.number_of_global_dofs() 
    errorMatrix[0, i] = L2_error(model.solution, uh, order=5)
    errorMatrix[1, i] = H1_semi_error(model.gradient, uh, order=5)
    errorMatrix[2, i] = np.sqrt(np.sum(eta1**2))
    errorMatrix[3, i] = L2_error(model.gradient, rgh, order=5)
    errorMatrix[4, i] = div_error(model.laplace, rgh, order=5)
    errorMatrix[5, i] = L2_error(model.laplace, rlh, order=5)
    errorMatrix[6, i] = np.sqrt(np.sum(eta2**2)) 

#order = np.log(error[0:-1]/error[1:])/np.log(2)

show_error_table(Ndof, errorType, errorMatrix, end='\\\\\\hline\n')

optionlist = ['k-*', 'b-o', 'r--^', 'g->', 'm-8', 'c-D','y-x']
fig = plt.figure()
axes = fig.gca()
showmultirate(axes, 1, Ndof, errorMatrix, optionlist, errorType)
axes.legend(loc=3)
axes.axis('tight')
plt.show()
