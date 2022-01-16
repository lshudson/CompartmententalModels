x = xolotl;

% create three compartments named AB, LP, and PY
x.add('compartment', 'AB')
x.add('compartment', 'LP')
x.add('compartment', 'PY')

% define ion channels: fast Na, K+, leak
conds = {'prinz/NaV', 'prinz/ACurrent', 'Leak'};
     
% AB/PD
% gbars(:, 1) = [1200, 360, 0.3];

% LP
% gbars(:, 2) = [3600, 720, 0.6];

% PY
% gbars(:, 3) = [6000, 3000, 1.0];

comps = x.find('compartment');
for i = 1:length(comps)
    for j = 1:length(conds)
        x.(comps{i}).add(conds{j}, 'gbar', gbars(j, i))
    end
end

% adjust leak reversal potentials
x.AB.Leak.E = -55; % mV
x.LP.Leak.E = -55; % mV
x.PY.Leak.E = -55; % mV

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
