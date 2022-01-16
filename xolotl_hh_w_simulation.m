function x = hhTwoCompartmentModel()

resistivity = 1e-3; % MOhm mm; 

r_soma = .025;
L_soma = .025; % mm

r_neurite = .01;
L_neurite = .35; % mm, from Otopalik et al

shell_thickness = .01; % 10 micrometres

x = xolotl;

x.add('compartment','Dendrite','A',0.01,'radius',r_soma,'len',L_soma,'Ca_out',3000,'tree_idx',0,'shell_thickness',shell_thickness);
x.add('compartment','CellBody','A',0.01,'radius',r_neurite,'len',L_neurite,'Ca_out',3000);

% set simulation parameters
numTimeSteps = 1000;
dt = 0.0001; % in seconds
timevec = dt:dt:dt*numTimeSteps;

% define synaptic conductance waveform.
n_syn = 100; % number of synapses for a connection.
 
tau1 = 0.2/1000; % in seconds
tau2 = 1.1/1000; % in seconds
weight = 55e-12*n_syn; % in siemens. (on the order of picosiemens)
factor = 1;
Gsyn_raw = (exp(-timevec/tau2) - exp(-timevec/tau1));
Gsyn = (Gsyn_raw/max(Gsyn_raw)) * weight;

x.Dendrite.add('liu/NaV', 'gbar', 1000)
x.Dendrite.add('liu/Kd', 'gbar', 300)
x.Dendrite.add('Leak', 'gbar', 1)
x.Dendrite.add('prinz/ACurrent', 'gbar', 104)
x.Dendrite.add('Gsyn', 'gbar', 2)

x.CellBody.add('liu/NaV', 'gbar', 1000)
x.CellBody.add('liu/Kd', 'gbar', 300)
x.CellBody.add('Leak', 'gbar', 1)
% x.CellBody.add('prinz/ACurrent', 'gbar', 104)
x.CellBody.add('Gsyn', 'gbar', 2)

x.CellBody.tree_idx = 0; % mark this as the cell body
x.connect('Dendrite','CellBody','Axial', 'resistivity',resistivity);
x.connect('CellBody','Dendrite','Axial', 'resistivity',resistivity);

x.dt = .1;
x.sim_dt = .05;
x.t_end = 5e3;
x.plot
x.manipulate
