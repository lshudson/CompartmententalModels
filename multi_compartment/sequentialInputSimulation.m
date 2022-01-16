close all
clear all



n_syn = [1]; %number of synapses for a connection.
dt = 0.0001;
numTimeSteps = 1000;

tau1 = 0.2/1000; %in seconds;
tau2 = 1.1/1000; %in seconds
factor = 1;
timevec = dt:dt:dt*numTimeSteps;

timeoffset = [  50  100  150  ];
Gsyn_raw = (exp(-timevec/tau2) - exp(-timevec/tau1));

%Set parameters for a "median" LHN:
dendriteSurfAreaCM2 =  1.2537e-05; %in cm^2
axonSurfAreaCM2 = 5.3566e-06; %in cm^2
r = 0.25 * (1/10000);
cablelength = 102;

V_axon = [];
V_dend = [];
for i = 1:length(timeoffset)
    Gsyn_raw_delay1 = [zeros(1,timeoffset(i)) Gsyn_raw(1:end-timeoffset(i))];
    Gsyn_raw_delay = [zeros(1,100) Gsyn_raw(1:end-100)];

    weight = 55e-12*n_syn; %in siemens. (on the order of picosiemens)
    Gsyn_dend = (Gsyn_raw_delay1/max(Gsyn_raw_delay1)) * weight;
    Gsyn_axon = (Gsyn_raw_delay/max(Gsyn_raw_delay)) * weight;
    V_all = realNcompartmentModel(Gsyn_dend*4, Gsyn_axon, r, cablelength,dendriteSurfAreaCM2,axonSurfAreaCM2);
    V_axon(:,i) = 1000*V_all(:,102);
    V_dend(:,i) = 1000*V_all(:,1);
    %V_axonFirstStim=realNcompartmentModel(Gsyn_axon/20, Gsyn_dend/20);
    
end

for i = 1:3
    subplot(2,3,i)
    plot(timevec,V_axon(:,i))
    hold on
    ylim([0 1.6])
    xlim([0 0.05])
    subplot(2,3,i+3)
    plot(timevec,V_dend(:,i))
    hold on
    ylim([0 1.6])
    xlim([0 0.05])
end