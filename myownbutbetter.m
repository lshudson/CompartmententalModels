x = xolotl;

% create three compartments called CellBody, Axon, and Dendrite
x.add('compartment', 'CellBody');
x.add('compartment', 'Axon');
x.add('compartment', 'Dendrite');

% define Na, K, Leak, Ks, Kf, NaT, and NaP ion channels
conds = {'prinz/NaV','prinz/Kd','Leak','turrigiano/ASlow' ...
         'hill/KACurrent','lin/NaT','hill/NaP'};
     
% set Na, K, Leak, Ks, Kf, NaT, and NaP conductances
% CellBody
gbars = [0, 0.36, 0.0005, 0.001, 50, 0.001, 0,   0];

% Axon
gbars = [1.2,  0.36, 0.00328, 0.7,  0,  0,2, 0.18, 0.00001];

% Dendrite
gbars = [1.2, 0.36, 0.0063, 0.7,  0, 0.2, 0.18, 0.00001];

% set Na, K, Leak, Ks, Kf, NaT, and NaP reversal potentials
% CellBody
Es(:, 1) = [0, -90, -55];

% Axon
Es(:, 2) = [48,  -90, -55];

% Dendrite
Es(:, 3) = [48, -90, -55];

% connect synapses
x.connect('CellBody','Axon','prinz/Chol','gmax',3);
x.connect('CellBody','Dendrite','prinz/Glut','gmax',30);
x.connect('CellBody','Axon','prinz/Glut','gmax',10);
x.connect('Dendrite','Axon','prinz/Glut','gmax',1);
x.connect('Axon','Dendrite','prinz/Glut','gmax',30);
x.connect('Dendrite','CellBody','prinz/Glut','gmax',30);

x.t_end = 100; % ms
% x.I_ext = .2; %nA
x.plot
x.manipulate

