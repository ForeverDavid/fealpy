import numpy as np
from itertools import compress
from scipy.sparse import coo_matrix, csc_matrix, csr_matrix, spdiags, eye

from ..functionspace.vem_space import VirtualElementSpace2d 
from ..solver import solve
from ..boundarycondition import DirichletBC
from ..vemmodel import doperator
from .integral_alg import PolygonMeshIntegralAlg

from ..quadrature import GaussLegendreQuadrture

from timeit import default_timer as timer

class PoissonInterfaceVEMModel():
    def __init__(self, model, mesh, p=1, integrator=None):
        """
        Parameters
        ----------
        
        See Also
        --------

        Notes
        -----
        """
        self.model = model  
        self.vemspace = VirtualElementSpace2d(mesh, p) 
        self.mesh = self.vemspace.mesh
        self.uh = self.vemspace.function() 
        self.aux_data()

        point = mesh.point
        self.wh = self.vemspace.function()
        self.wh[self.isInterfacePoint] = self.model.func_jump(point[self.isInterfacePoint])

        self.uIE = self.vemspace.function() 
        self.uIE[self.isExtPoint] = model.solution_plus(point[self.isExtPoint])       
        self.uII = self.vemspace.function()
        self.uII[self.isIntPoint] = model.solution_minus(point[self.isIntPoint])

        self.area = self.vemspace.smspace.area 

        self.integrator = integrator

        self.integralalg = PolygonMeshIntegralAlg(
                self.integrator, 
                self.mesh, 
                area=self.area, 
                barycenter=self.vemspace.smspace.barycenter)

        self.H = doperator.matrix_H(self.vemspace)
        self.D = doperator.matrix_D(self.vemspace, self.H)
        self.B = doperator.matrix_B(self.vemspace)
        self.G = doperator.matrix_G(self.vemspace, self.B, self.D)
        self.C = doperator.matrix_C(self.vemspace, self.B, self.D, self.H, self.area)

        self.PI0 = doperator.matrix_PI_0(self.vemspace, self.H, self.C)
        self.PI1 = doperator.matrix_PI_1(self.vemspace, self.G, self.B)

    def aux_data(self):
        barycenter = self.vemspace.smspace.barycenter
        # TODO: Notice that here we assume barycenter is inside each cell
        self.isIntCell = self.model.interface(barycenter) < 0

        mesh = self.mesh

        N = mesh.number_of_points()        
        NV = mesh.number_of_vertices_of_cells()
        cell = mesh.ds.cell
        edge = mesh.ds.edge 
        edge2cell = mesh.ds.edge_to_cell()

        self.isInterfaceEdge = (self.isIntCell[edge2cell[:, 0]] != self.isIntCell[edge2cell[:, 1]])
        self.isInterfacePoint = np.zeros(N, dtype=np.bool)
        self.isInterfacePoint[edge[self.isInterfaceEdge]] = True

        self.interfaceEdge = edge[self.isInterfaceEdge]

        self.isExtPoint = np.zeros(N, dtype=np.bool)
        self.isExtPoint[cell[np.repeat(~self.isIntCell, NV)]] = True

        self.isIntPoint = np.zeros(N, dtype=np.bool)
        self.isIntPoint[cell[np.repeat(self.isIntCell, NV)]] = True
        
    def reinit(self, mesh, p=None):
        if p is None:
            p = self.vemspace.p
        self.vemspace =VirtualElementSpace2d(mesh, p) 
        self.mesh = self.vemspace.mesh
        self.uh = self.vemspace.function() 
        self.aux_data()

        point = mesh.point
        self.wh = self.vemspace.function()
        self.wh[self.isInterfacePoint] = self.model.func_jump(point[self.isInterfacePoint])

        self.uIE = self.vemspace.function() 
        self.uIE[self.isExtPoint] = self.model.solution_plus(point[self.isExtPoint])
        self.uII = self.vemspace.function()
        self.uII[self.isIntPoint] = self.model.solution_minus(point[self.isIntPoint])

        self.area = self.vemspace.smspace.area 

        self.integralalg = PolygonMeshIntegralAlg(
                self.integrator, 
                self.mesh, 
                area=self.area, 
                barycenter=self.vemspace.smspace.barycenter)
        self.uI = self.vemspace.interpolation(self.model.solution, self.integralalg.integral)

        self.H = doperator.matrix_H(self.vemspace)
        self.D = doperator.matrix_D(self.vemspace, self.H)
        self.B = doperator.matrix_B(self.vemspace)
        self.G = doperator.matrix_G(self.vemspace, self.B, self.D)
        self.C = doperator.matrix_C(self.vemspace, self.B, self.D, self.H, self.area)

        self.PI0 = doperator.matrix_PI_0(self.vemspace, self.H, self.C)
        self.PI1 = doperator.matrix_PI_1(self.vemspace, self.G, self.B)


    def project_to_smspace(self, uh=None):
        vemspace = self.vemspace
        mesh = vemspace.mesh
        NC = mesh.number_of_cells()
        NV = mesh.number_of_vertices_of_cells()
        cell = mesh.ds.cell
        ldof = vemspace.smspace.number_of_local_dofs()

        S = self.vemspace.smspace.function()
        if uh is None:
            uh = self.uh
        idx = np.repeat(range(NC), NV)
        for i in range(3):
            S[i::ldof] = np.bincount(idx, weights=self.B[i, :]*uh[cell], minlength=NC)
        return S


    def get_left_matrix(self):
        return self.get_stiff_matrix() 
        #return doperator.stiff_matrix(self.vemspace, self.area, vem=self)

    def get_right_vector(self):

        f = self.model.source
        integral = self.integralalg.integral 
        b0 = doperator.source_vector(integral, f, self.vemspace, self.PI0)
        
        b1 = self.get_flux_jump_vector()
        return b0 - b1 + self.AI@self.wh 
        
        #return b0 


    def get_flux_jump_vector(self):

        qf = GaussLegendreQuadrture(3)
        bcs, ws = qf.quadpts, qf.weights 
        point = self.mesh.point
        iedge = self.interfaceEdge
        
        ps = np.einsum('ij, kjm->ikm', bcs, point[iedge])
        val = self.model.flux_jump(ps)
        bb = np.einsum('i, ij, ik->kj', ws, bcs, val)
       
        l = np.sqrt(np.sum((point[iedge[:, 0], :] - point[iedge[:, 1], :])**2, axis=1))
        
        bb *= l.reshape(-1, 1)
        gdof = self.vemspace.number_of_global_dofs()
        b = np.bincount(iedge.flat, weights=bb.flat, minlength=gdof)
        return b

    def get_stiff_matrix(self):
        vemspace = self.vemspace
        B = self.B
        D = self.D

        cell2dof, cell2dofLocation = vemspace.dof.cell2dof, vemspace.dof.cell2dofLocation
        NC = len(cell2dofLocation) - 1
        
        cd = np.hsplit(cell2dof, cell2dofLocation[1:-1])
        BB = np.hsplit(B, cell2dofLocation[1:-1])
        DD = np.vsplit(D, cell2dofLocation[1:-1])
        tG = np.array([(0, 0, 0), (0, 1, 0), (0, 0, 1)])

        barycenter = self.vemspace.smspace.barycenter 
        #TODO: Notice that here we assume barycenter is inside each cell
        k = self.model.diffusion_coefficient(barycenter)
        f1 = lambda x: (x[1].T@tG@x[1] + (np.eye(x[1].shape[1]) - x[0]@x[1]).T@(np.eye(x[1].shape[1]) - x[0]@x[1]))*x[2]
        K = list(map(f1, zip(DD, BB, k)))

        f2 = lambda x: np.repeat(x, x.shape[0]) 
        f3 = lambda x: np.tile(x, x.shape[0])
        f4 = lambda x: x.flatten()


        gdof = vemspace.number_of_global_dofs()
        I = np.concatenate(list(map(f2, compress(cd, self.isIntCell))))
        J = np.concatenate(list(map(f3, compress(cd, self.isIntCell))))
        val = np.concatenate(list(map(f4, compress(K, self.isIntCell))))
        self.AI = csr_matrix((val, (I, J)), shape=(gdof, gdof), dtype=np.float)

        I = np.concatenate(list(map(f2, compress(cd, ~self.isIntCell))))
        J = np.concatenate(list(map(f3, compress(cd, ~self.isIntCell))))
        val = np.concatenate(list(map(f4, compress(K, ~self.isIntCell))))
        self.AE = csr_matrix((val, (I, J)), shape=(gdof, gdof), dtype=np.float)

        return  self.AI + self.AE 

    def solve(self):
        uh = self.uh
        bc = DirichletBC(self.vemspace, self.model.dirichlet)
        self.A, b = solve(self, uh, dirichlet=bc, solver='direct')
    
    def l2_error(self):
        uII = self.uII
        uIE = self.uIE
        uh = self.uh
        wh = self.wh
        eI = np.zeros(uII.shape, dtype=np.float)
        eE = np.zeros(uII.shape, dtype=np.float)
        eI[:] =  uII - (uh - wh)
        eE[:] =  uIE - uh
        
        eI = eI[self.isIntPoint] 
        eE = eE[self.isExtPoint]
        return np.sqrt((np.mean(eI**2) + np.mean(eE**2))/2)

    def uIuh_error(self):
        uII = self.uII
        uIE = self.uIE
        uh = self.uh
        wh = self.wh
        eI = np.zeros(uII.shape, dtype=np.float)
        eE = np.zeros(uII.shape, dtype=np.float)
        eI[:] =  uII - (uh - wh)
        eE[:] =  uIE - uh
        
        eI[~self.isIntPoint] = 0
        eE[~self.isExtPoint] = 0
        return np.sqrt(eI@self.AI@eI + eE@self.AE@eE)

        
    def L2_error(self):
        uh = self.uh
        wh = self.wh
        SI = self.project_to_smspace(uh-wh)
        uhwh = SI.value
        eI = self.integralalg.L2_error(self.model.solution_minus, uhwh, celltype=True)

        SE = self.project_to_smspace(uh)
        uh = SE.value
        eE = self.integralalg.L2_error(self.model.solution_plus, uh, celltype=True)

        eI = eI**2
        eE = eE**2
        
        eI = eI[self.isIntCell]
        eE = eE[~self.isIntCell]
        return np.sqrt(eI.sum() + eE.sum())

    def H1_semi_error(self):
        uh = self.uh
        wh = self.wh
        SI = self.project_to_smspace(uh-wh)
        uhwh = SI.grad_value
        eI = self.integralalg.L2_error(self.model.gradient_minus, uhwh, celltype=True)

        SE = self.project_to_smspace(uh)
        uh = SE.grad_value
        eE = self.integralalg.L2_error(self.model.gradient_plus, uh, celltype=True)

        eI = eI**2
        eE = eE**2
        
        eI = eI[self.isIntCell]
        eE = eE[~self.isIntCell]
        return np.sqrt(eI.sum() + eE.sum())
