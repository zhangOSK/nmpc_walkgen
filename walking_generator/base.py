import numpy
from math import cos, sin

class BaseGenerator(object):
    """
    Base class of walking pattern generator for humanoids, cf.
    LAAS-UHEI walking report.

    BaseClass provides all matrices and timestepping methods that are
    defined for the pattern generator family. In derived classes different
    problems and their solvers can be realized.
    """
    # define some constants
    g = 9.81

    def __init__(self, N=16, T=0.1, T_step=0.8, h_com=0.81):
        """
        Initialize pattern generator, i.e.
        * allocate memory for matrices
        * populate them according to walking reference document

        Parameters
        ----------

        N : int
            Number of time steps of prediction horizon

        T : float
            Time increment between two time steps (default: 0.1 [s])

        nf : int
            Number of foot steps planned in advance (default: 2 [footsteps])

        h_com: float
            Height of center of mass for the LIPM (default: 0.81 [m])

        T_step : float
            Time for the robot to make 1 step

        T_window : float
            Duration of the preview window of the controller
        """
        self.N = N
        self.T = T
        self.T_window = N*T
        self.T_step = T_step
        self.nf = (int)(self.T_window/T_step)
        if self.T_window/T_step - self.nf > 0:
            self.nf = self.nf + 1
        self.h_com = h_com

        # objective weights

        self.a = 1.0 # weight for CoM velocity tracking
        self.b = 0.0 # weight for CoM average velocity tracking
        self.c = 1.0 # weight for ZMP reference tracking
        self.d = 1.0 # weight for jerk minimization

        # matrix to get average velocity

        self.E = numpy.zeros((self.N/self.nf, self.N))
        self.E[:, :self.N/self.nf] = -numpy.eye(self.N/self.nf)
        self.E[:,-self.N/self.nf:] =  numpy.eye(self.N/self.nf)
        self.E /= 2*self.T_step

        # center of mass initial values

        self.c_k_x = numpy.zeros((3,), dtype=float)
        self.c_k_y = numpy.zeros((3,), dtype=float)
        self.c_k_q = numpy.zeros((3,), dtype=float)

        # center of mass matrices

        self.  C_kp1_x = numpy.zeros((N,), dtype=float)
        self. dC_kp1_x = numpy.zeros((N,), dtype=float)
        self.ddC_kp1_x = numpy.zeros((N,), dtype=float)

        self.  C_kp1_y = numpy.zeros((N,), dtype=float)
        self. dC_kp1_y = numpy.zeros((N,), dtype=float)
        self.ddC_kp1_y = numpy.zeros((N,), dtype=float)

        self.  C_kp1_q = numpy.zeros((N,), dtype=float)
        self. dC_kp1_q = numpy.zeros((N,), dtype=float)
        self.ddC_kp1_q = numpy.zeros((N,), dtype=float)

        # jerk controls for center of mass

        self.dddC_k_x = numpy.zeros((N,), dtype=float)
        self.dddC_k_y = numpy.zeros((N,), dtype=float)
        self.dddC_k_q = numpy.zeros((N,), dtype=float)

        # reference matrices

        self. dC_kp1_x_ref = numpy.zeros((N,), dtype=float)
        self. dC_kp1_y_ref = numpy.zeros((N,), dtype=float)
        self. dC_kp1_q_ref = numpy.zeros((N,), dtype=float)

        # feet matrices

        self.F_kp1_x = numpy.zeros((N,), dtype=float)
        self.F_kp1_y = numpy.zeros((N,), dtype=float)
        self.F_kp1_q = numpy.zeros((N,), dtype=float)

        self.f_k_x = 0.0
        self.f_k_y = 0.0
        self.f_k_q = 0.0

        self.F_k_x = numpy.zeros((self.nf,), dtype=float)
        self.F_k_y = numpy.zeros((self.nf,), dtype=float)
        self.F_k_q = numpy.zeros((self.nf,), dtype=float)

        # zero moment point matrices

        self.Z_kp1_x = numpy.zeros((N,), dtype=float)
        self.Z_kp1_y = numpy.zeros((N,), dtype=float)

        # transformation matrices

        self.Pps = numpy.zeros((N,3), dtype=float)
        self.Ppu = numpy.zeros((N,N), dtype=float)

        self.Pvs = numpy.zeros((N,3), dtype=float)
        self.Pvu = numpy.zeros((N,N), dtype=float)

        self.Pas = numpy.zeros((N,3), dtype=float)
        self.Pau = numpy.zeros((N,N), dtype=float)

        self.Pzs = numpy.zeros((N,3), dtype=float)
        self.Pzu = numpy.zeros((N,N), dtype=float)

        # convex hulls used to bound the free placement of the foot
            # set of points
        self.lfhull = numpy.zeros((5,2), dtype=float)
        self.rfhull = numpy.zeros((5,2), dtype=float)
            # set of cartesian equalities
        self.A0r = numpy.zeros((5,2), dtype=float)
        self.ubB0r = numpy.zeros((5,), dtype=float)
        self.A0l = numpy.zeros((5,2), dtype=float)
        self.ubB0l = numpy.zeros((5,), dtype=float)

        # Linear constraints matrix
        self.Acop = numpy.zeros((), dtype=float)
        self.Afoot = numpy.zeros((), dtype=float)
        self.eqAfoot = numpy.zeros((), dtype=float)

        # Linear contraints vector
        self.ubBfoot = numpy.zeros((), dtype=float)
        self.ubBcop = numpy.zeros((), dtype=float)
        self.eqBfoot = numpy.zeros((), dtype=float)

        # Position of the foot in the local foot frame
        self.lfoot = numpy.zeros((4,2), dtype=float)
        self.rfoot = numpy.zeros((4,2), dtype=float)
        # Corresponding linear system
        self.A0rf = numpy.zeros((4,2), dtype=float)
        self.ubB0rf = numpy.zeros((4,), dtype=float)
        self.A0lf = numpy.zeros((4,2), dtype=float)
        self.ubB0lf = numpy.zeros((4,), dtype=float)

        # Current support state
        self.currentSupport = BaseTypeSupport()
        self.currentSupport.__init__()

        """
        NOTE number of foot steps in prediction horizon changes between
        nf and nf+1, because when robot takes first step nf steps are
        planned on the prediction horizon, which makes a total of nf+1 steps.
        """
        self.v_kp1 = numpy.zeros((N,),   dtype=int)
        self.V_kp1 = numpy.zeros((N,self.nf), dtype=int)

        # initialize transformation matrices
        self._initialize_matrices()

        # build the constraints linked to
        # the foot step placement and to the cop
        self.buildConstraints()

    def _initialize_matrices(self):
        """
        initializes the transformation matrices according to the walking report
        """
        T_step = self.T_step
        T = self.T
        N = self.N
        nf = self.nf
        h_com = self.h_com
        g = self.g

        for i in range(N):
            self.Pzs[i, :] = (1.,   i*T, (i**2*T**2)/2. + h_com/g)
            self.Pps[i, :] = (1.,   i*T,           (i**2*T**2)/2.)
            self.Pvs[i, :] = (0.,    1.,                      i*T)
            self.Pas[i, :] = (0.,    0.,                       1.)

            for j in range(N):
                if j <= i:
                    self.Pzu[i, j] = (3.*(i-j)**2 + 3.*(i-j) + 1.)*T**3/6. + T*h_com/g
                    self.Ppu[i, j] = (3.*(i-j)**2 + 3.*(i-j) + 1.)*T**3/6.
                    self.Pvu[i, j] = (2.*(i-j) + 1.)*T**2/2.
                    self.Pau[i, j] = T

        # initialize foot decision vector and matrix
        nstep = int(self.T_step/T) # time span of single support phase
        self.v_kp1[:nstep] = 1 # definitions of initial support leg

        for j in range (nf):
            a = min((j+1)*nstep, N)
            b = min((j+2)*nstep, N)
            self.V_kp1[a:b,j] = 1

        # support foot : right
        self.rfhull[0,0] = -0.28  ;  self.rfhull[0,1] = -0.2 ;
        self.rfhull[1,0] = -0.2   ;  self.rfhull[1,1] = -0.3 ;
        self.rfhull[2,0] =  0     ;  self.rfhull[2,1] = -0.4 ;
        self.rfhull[3,0] =  0.2   ;  self.rfhull[3,1] = -0.3 ;
        self.rfhull[4,0] =  0.28  ;  self.rfhull[4,1] = -0.2 ;
        # support foot : left
        self.lfhull[0,0] = -0.28  ;  self.lfhull[0,1] =  0.2 ;
        self.lfhull[1,0] = -0.2   ;  self.lfhull[1,1] =  0.3 ;
        self.lfhull[2,0] =  0     ;  self.lfhull[2,1] =  0.4 ;
        self.lfhull[3,0] =  0.2   ;  self.lfhull[3,1] =  0.3 ;
        self.lfhull[4,0] =  0.28  ;  self.lfhull[4,1] =  0.2 ;
        # linear system corresponding to the convex hulls
        self.ComputeLinearSystem( self.rfhull, "right", self.A0r, self.ubB0r)
        self.ComputeLinearSystem( self.lfhull, "left", self.A0l, self.ubB0l)

        # position of the vertices of the feet in the foot coordinates.
        # left foot
        self.lfoot[0,0] =  0.0686   ;  self.lfoot[0,1] =  0.029 ;
        self.lfoot[1,0] =  0.0686   ;  self.lfoot[1,1] = -0.029 ;
        self.lfoot[2,0] = -0.0686   ;  self.lfoot[2,1] = -0.029 ;
        self.lfoot[3,0] = -0.0686   ;  self.lfoot[3,1] =  0.029 ;
        # right foot
        self.rfoot[0,0] =  0.0686   ;  self.rfoot[0,1] = -0.029 ;
        self.rfoot[1,0] =  0.0686   ;  self.rfoot[1,1] =  0.029 ;
        self.rfoot[2,0] = -0.0686   ;  self.rfoot[2,1] =  0.029 ;
        self.rfoot[3,0] = -0.0686   ;  self.rfoot[3,1] = -0.029 ;
        # linear system corresponding to the convex hulls
        self.ComputeLinearSystem( self.rfoot, "right", self.A0rf, self.ubB0rf)
        self.ComputeLinearSystem( self.lfoot, "left", self.A0lf, self.ubB0lf)

        print '[v, V0, ...]'
        print numpy.hstack((self.v_kp1.reshape(self.v_kp1.shape[0],1), self.V_kp1))

    def update(self):
        self.updatev()

    def simulate(self):
        """
        integrates model for given jerks and feet positions and orientations
        """

        self.  C_kp1_x = self.Pps.dot(self.c_k_x) + self.Ppu.dot(self.dddC_k_x)
        self. dC_kp1_x = self.Pvs.dot(self.c_k_x) + self.Pvu.dot(self.dddC_k_x)
        self.ddC_kp1_x = self.Pas.dot(self.c_k_x) + self.Pau.dot(self.dddC_k_x)

        self.  C_kp1_y = self.Pps.dot(self.c_k_y) + self.Ppu.dot(self.dddC_k_y)
        self. dC_kp1_y = self.Pvs.dot(self.c_k_y) + self.Pvu.dot(self.dddC_k_y)
        self.ddC_kp1_y = self.Pas.dot(self.c_k_y) + self.Pau.dot(self.dddC_k_y)

        self.  C_kp1_q = self.Pps.dot(self.c_k_q) + self.Ppu.dot(self.dddC_k_q)
        self. dC_kp1_q = self.Pvs.dot(self.c_k_q) + self.Pvu.dot(self.dddC_k_q)
        self.ddC_kp1_q = self.Pas.dot(self.c_k_q) + self.Pau.dot(self.dddC_k_q)

        self.Z_kp1_x = self.Pzs.dot(self.c_k_x) + self.Pzu.dot(self.dddC_k_x)
        self.Z_kp1_y = self.Pzs.dot(self.c_k_y) + self.Pzu.dot(self.dddC_k_y)

    def updatev(self):
        """
        Update selection vector v_kp1 and selection matrix V_kp1.

        Therefore shift foot decision vector and matrix by one row up,
        i.e. the first entry in the selection vector and the first row in the
        selection matrix drops out and selection vector's dropped first value
        becomes the last entry in the decision matrix
        """
        nf = self.nf
        nstep = int(self.T_step/self.T)
        N = self.N

        # save first value for concatenation
        first_entry_v_kp1 = self.v_kp1[0].copy()

        self.v_kp1[:-1]   = self.v_kp1[1:]
        self.V_kp1[:-1,:] = self.V_kp1[1:,:]

        # clear last row
        self.V_kp1[-1,:] = 0

        # concatenate last entry
        self.V_kp1[-1, -1] = first_entry_v_kp1

        # when first column of selection matrix becomes zero,
        # then shift columns by one to the front
        if (self.v_kp1 == 0).all():
            self.v_kp1[:] = self.V_kp1[:,0]
            self.V_kp1[:,:-1] = self.V_kp1[:,1:]
            self.V_kp1[:,-1] = 0

        """
        # @Max: this is the old implementation
        # using slices is much better, because underneath is super fast c++.
        # doing anything else, especially loops can be bad in python because of
        # dynamic types.

        self.v_kp1 = numpy.delete(self.v_kp1,0,None)
        self.v_kp1 = numpy.append(self.v_kp1,[0],axis=0)

        if self.v_kp1[0]==0:
            self.v_kp1 = numpy.zeros((N,), dtype=float)
            self.V_kp1 = numpy.zeros((N,self.nf), dtype=float)
            nf = 1
            for i in range(nstep):
                self.v_kp1[i] = 1
            for i in range(N-nstep):
                self.v_kp1[i+nstep] = 0
            step = 0
            for i in range (N) :
                step = (int)( i / nstep )
                for j in range (nf):
                    self.V_kp1[i,j] = (int)( i+1>nstep and j==step-1)

        else:
            self.V_kp1 = numpy.delete(self.V_kp1,0,axis=0)
            tmp = numpy.zeros( (1,self.V_kp1.shape[1]) , dtype=float)
            self.V_kp1 = numpy.append(self.V_kp1, tmp, axis=0)
            for j in range(self.V_kp1.shape[1]) :
                if self.V_kp1[:,j].sum() < nstep :
                    self.V_kp1[self.V_kp1.shape[0]-1][j] = 1
                    break
                else :
                    self.V_kp1[self.V_kp1.shape[0]-1][j] = 0

        """
        # TODO delete debug output
        print '[v, V0, ...]'
        print numpy.hstack((self.v_kp1.reshape(self.v_kp1.shape[0],1), self.V_kp1))

    def ComputeLinearSystem(self, hull, foot, A0, B0 ):

        nEdges = hull.shape[0]
        print nEdges
        if foot == "left" :
            sign = 1
        else :
            sign = -1
        for i in range(nEdges):
            if i == nEdges-1 :
                k = 0
            else :
                k = i + 1

            x1 = hull[i,0]
            y1 = hull[i,1]
            x2 = hull[k,0]
            y2 = hull[k,1]

            dx = y1 - y2
            dy = x2 - x1
            dc = dx*x1 + dy*y1

            # symmetrical constraints
            A0[i,0] = sign * dx
            A0[i,1] = sign * dy
            B0[i] =   sign * dc

    def buildConstraints(self):
        self.nc = 0
        self.buildCoPconstraint()
        self.buildFootConstraint()

    def buildCoPconstraint(self):










        self.Acop
        self.ubBcop

    def buildFootConstraint(self):
        # need the self.currentSupport to be updated
        #               before calling this function

        # inequality constraint on both feet A u + B <= 0
        # A0 R(theta) [Fx_k+1 - Fx_k] <= ubB0
        #             [Fy_k+1 - Fy_k]
        self.Afoot.resize(2*(self.N+self.nf,2*self.nf))

        matSelec = numpy.array([ [1, 0],[-1, 1] ])
        footSelec = numpy.array([ [self.currentSupport.x, 0],[self.currentSupport.y, 0] ])
        theta = self.currentSupport.theta
        # rotation matrice from F_k+1 to F_k
        rotMat = numpy.array([[cos(theta), sin(theta)],[-sin(theta), cos(theta)]])
        nf = self.nf
        nEdges = self.A0l.shape[0]
        N = self.N
        ncfoot = nf * nEdges

        A0lrot = self.A0l.dot(rotMat)
        A0rrot = self.A0r.dot(rotMat)
        if self.currentSupport.foot == "left":
            tmp1 = numpy.array( [A0lrot[:,0],numpy.zeros((nEdges,),dtype=float)] )
            tmp2 = numpy.array( [numpy.zeros((nEdges,),dtype=float),A0rrot[:,0]] )
            tmp3 = numpy.array( [A0lrot[:,1],numpy.zeros((nEdges,),dtype=float)] )
            tmp4 = numpy.array( [numpy.zeros(nEdges,),A0rrot[:,1]] )
        else :
            tmp1 = numpy.array( [A0rrot[:,0],numpy.zeros((nEdges,),dtype=float)] )
            tmp2 = numpy.array( [numpy.zeros((nEdges,),dtype=float),A0lrot[:,0]] )
            tmp3 = numpy.array( [A0rrot[:,1],numpy.zeros((nEdges,),dtype=float)] )
            tmp4 = numpy.array( [numpy.zeros((nEdges,),dtype=float),A0lrot[:,1]] )

        X_mat = numpy.concatenate( (tmp1.T,tmp2.T) , 0)
        A0x = X_mat.dot(matSelec)
        Y_mat = numpy.concatenate( (tmp3.T,tmp4.T) , 0)
        A0y = Y_mat.dot(matSelec)

        B0full = numpy.concatenate( (self.ubB0l, self.ubB0r) , 0 )
        B0 = B0full + X_mat.dot(footSelec[0,:]) + Y_mat.dot(footSelec[1,:])

        self.Afoot = numpy.concatenate ( (numpy.zeros((ncfoot,N),dtype=float),\
                                          A0x,\
                                          numpy.zeros((ncfoot,N),dtype=float),\
                                          A0y) , 1 )
        self.Bfoot = B0
        self.nc = self.nc + ncfoot

        print A0x
        print A0y
        print B0

    def solve(self):
        """
        Solve problem on given prediction horizon with implemented solver.
        """
        err_str = 'Please derive from this class to implement your problem and solver'
        raise NotImplementedError(err_str)

class BaseTypeSupport(object):

    def __init__(self, x=0, y=0, theta=0, foot="left"):
        self.x = x
        self.y = y
        self.theta = theta

        self.dx = 0
        self.dy = 0
        self.dtheta = 0

        self.ddx = 0
        self.ddy = 0
        self.ddtheta = 0

        self.foot = foot
