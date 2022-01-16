x = xolotl;

% create three compartments named AB, LP, and PY
x.add('compartment', 'AB')
x.add('compartment', 'LP')
x.add('compartment', 'PY')

% define ion channels
conds = {'prinz/NaV', 'prinz/CaT', 'prinz/CaS','prinz/ACurrent', ...
        'prinz/KCa', 'prinz/Kd', 'prinz/HCurrent', 'Leak'};
   
% AB/PD
gbars(:, 1) = [1000, 25, 60, 500, 50, 1000, 0.1, 0];

% LP
gbars(:, 2) = [1000,  0, 40, 200,  0,  250, 0.5, 0.3];

% PY
gbars(:, 3) = [1000, 24, 20, 500,  0, 1250, 0.5, 0.1];

comps       = x.find('compartment');
for i = 1:length(comps)
    for j = 1:length(conds)
        x.(comps{i}).add(conds{j}, 'gbar', gbars(j, i))
    end
end

% adjust leak reversal potentials
x.AB.Leak.E = -50; % mV
x.LP.Leak.E = -50; % mV
x.PY.Leak.E = -50; % mV

% add Ca dynamics
for i = 1:length(comps)
    x.(comps{i}).add('prinz/CalciumMech')
end

% add synapses
x.connect('AB', 'LP', 'prinz/Cholinergic', 'gmax', 30)
x.connect('AB','PY','prinz/Chol','gmax',3)
x.connect('AB','LP','prinz/Glut','gmax',30)
x.connect('AB','PY','prinz/Glut','gmax',10)
x.connect('LP','PY','prinz/Glut','gmax',1)
x.connect('PY','LP','prinz/Glut','gmax',30)
x.connect('LP','AB','prinz/Glut','gmax',30)

% simulate model for 5 sec
x.t_end = 5000; % milliseconds

% integrate and plot voltage trace and calcium concentration
x.plot