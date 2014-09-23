import time
from walking_generator.visualization import Plotter
from walking_generator.classic import ClassicGenerator

# instantiate pattern generator
gen = ClassicGenerator(fsm_state='L/R')

# instantiate plotter
show_canvas = True
save_to_file = False
plot = Plotter(gen, show_canvas, save_to_file)

# Pattern Generator Preparation
# set reference velocities to zero
gen.dC_kp1_x_ref[...] = 0.1
gen.dC_kp1_y_ref[...] = 0.1
gen.dC_kp1_q_ref[...] = 0.0

gen.set_security_margin(0.04, 0.04)

# set initial values
comx = [0.06591456,0.07638739,-0.1467377]
comy = [2.49008564e-02,6.61665254e-02,6.72712187e-01]
comz = 0.814
footx = 0.00949035
footy = 0.095
footq = 0.0
gen.set_initial_values(comx, comy, comz, footx, footy, footq, foot='left')

gen.simulate()
gen._update_data()

# Pattern Generator Event Loop
for i in range(160):
    print 'iteration: ', i

    if 50 <= i < 100:
        gen.dC_kp1_x_ref[...] =  0.2
        gen.dC_kp1_y_ref[...] =  0.0
        gen.dC_kp1_q_ref[...] =  0.0
    if 100 <= i < 130:
        gen.dC_kp1_x_ref[...] =  0.0
        gen.dC_kp1_y_ref[...] = -0.2
        gen.dC_kp1_q_ref[...] =  0.0
    if 130 <= i:
        gen.dC_kp1_x_ref[...] = -0.3
        gen.dC_kp1_y_ref[...] =  0.0
        gen.dC_kp1_q_ref[...] =  0.0

    # solve QP
    gen.solve()

    # initial value embedding by internal states and simulation
    comx, comy, comz, footx, footy, footq, foot, comq= \
    gen.update()
    gen.set_initial_values(comx, comy, comz, footx, footy, footq, foot, comq)
    plot.update()

    #raw_input('press key:')
    time.sleep(0.1)

gen.data.save_to_file('./data.json')

