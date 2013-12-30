from net import *
import pickle
from pylab import *
import copy as cp
    
class nntrainer2(object):
    def __init__(self, nn, streamer, lr, predhorizon, plotint, weightcost, alpha, beta): 
        self.nn = nn                                # store neural network
        self.streamer = streamer                  # store streamers
        self.context = None                         # series context store
        self.contextlen = self.nn.layers[0].insz    # series context length = nn input size
        self.lr = lr                                # sgd learning rate
        self.cur_params = self.nn.getparams()       # current state parameters initialization
        self.init_params = self.nn.getparams()      # store initial params
        self.streamcount = 0                        # count of streaming steps from data series
        self.sgdstep = 0                            # count of sgd steps
        self.estf = 0                               # current estimation of objective value
        self.estflist = []                          # full list of obj estimations
        self.running_objective_list = []                           # [mean/std est] running list of objective value        
        self.running_objective_length = 2000                          # [mean/std est] length of running list
        self.sgd_save_interval = 1000                      # how many sgd steps before saving
        self.predhorizon = predhorizon
        self.predlist = []
        self.predrunlist = []        
        self.errlist = []
        self.erridx = 50 #predhorizon
        self.plotint = plotint
        self.weightcost = weightcost
        self.alpha = alpha # 6e2
        self.beta = beta #6e3
        
    def multi_d_get_element(self):
        # -- obtain a multi-dimensional stream element from list of streamers --
        series_end = False
        element = []
        for streamer in self.streamers:
            x = streamer.get_element()
            if x == 'full':
                series_end = True
            element.append(x)
        element = matrix(element).T
        return [element, series_end]

    def append_to_context(self, context, contextlen, element):
        if context == None:
            context = element
            return 'init'         
        context = concatenate((context, element), axis=1)
        if context.shape[1]>contextlen:
            context = context[:, 1:context.shape[1]]
            return 'full'
        return 'filling'
        
    def gradient_descend(self, target):
        [f, g] = self.nn.gradfunc(self.cur_params, self.context.reshape(1, []).T, target)
        # -- add regularization --
        f = f + 0.5*self.weightcost*sum(square(self.cur_params))
        g = g + self.weightcost*self.cur_params
        self.cur_params = self.cur_params - self.alpha/(self.beta + self.sgdstep)*g
        return f
    
    # ---- func: take streamed value, add to context, take sgd step & estimate running obj value ----
    def streamstep(self, xt):
        if xt == 'full':
            return
        if self.context == None:
            self.context = xt
        else:
            if len(self.context)==self.context_sz:
                curf = self.gstep(self.context, xt)
                self.context.append(xt)            
                self.context.pop(0)
                self.series.append(xt)
                self.streamcount += 1
                self.runlist.append(curf)
                if len(self.runlist)>self.runlen:
                    self.runlist.pop(0)            
                    self.estf = mean(self.runlist)
                elif len(self.context)<self.context_sz:
                    self.context.append(xt)
                else:
                    print 'Context larger than specified size!'
        return self.estf
    
    # ---- func: perform on-line learning ----
    def nnlearnstream(self, testid):
        self.sgdstep = 0
        xt = self.streamer.get_element()
        ion()
        meanstore = []
        while xt != 'full':
            # 
            self.sgdstep += 1
            estf = self.streamstep(xt)
            self.estflist.append(estf)
            print 'sgd step '+ str(self.sgdstep) + '  objective value: ' + str(estf)
            xt = self.streamer.onestep()
            
            # --- save progress to file ---
            if mod(self.sgdstep, self.sgdsaveint) == 0:
                with open(self.gensavename(), 'wb') as output:
                    pickle.dump(self, output, pickle.HIGHEST_PROTOCOL)
                    
            if testid == 'test': 
                numplots = 8;
                if self.sgdstep==self.nn.layers[0].insz+1:
                    # ----- initialize subplots -----        
                    figure(num=None, figsize=(16, 12), dpi=80, facecolor='w', edgecolor='k')
                    ax=[]
                    for i in range(numplots):
                        ax.append(subplot(numplots, 1, i+1))
                        ax[i].grid('on')
                    
                    ax[0].set_ylabel('obj value')
                    #                    ax[0].set_xlabel('sgd step'); 
                    ax[1].set_ylabel('ts value')
                    #                    ax[1].set_xlabel('time step'); 
                    #                    ax[1].set_title('series + prediction')
                    #                    ax[2].set_title('1l weights')
                    #                    ax[3].set_title('2l weights')
                    
                    optline, = ax[0].plot([], [])
                    tsline, = ax[1].plot([], [])
                    predline, = ax[1].plot([], [], 'r')
                    seriesline, = ax[4].plot([], [], 'k')
                    testerrline, = ax[5].plot([], [], 'r')
                    trainerrline, = ax[5].plot([], [])
                    
                elif self.sgdstep > self.nn.layers[0].insz+1:
                    # --- run predictions ---
                    self.predlist = self.nn.fwpredict(self.context, self.predhorizon)
                    # store list of predictions
                    self.predrunlist.append(self.predlist[self.erridx-1])
                    if len(self.predrunlist) > self.erridx+1:
                        self.predrunlist.pop(0)
                        # retract prediction compare with context
                        #curerr = abs(self.context[len(self.context)-1] - self.predrunlist[len(self.predrunlist)-self.erridx-1])/2 #/abs(self.context[len(self.context)-1]))
                        curerr = abs(self.context[len(self.context)-1] - self.predrunlist[len(self.predrunlist)-self.erridx-1])/(abs(self.context[len(self.context)-1])+0.05)
                        self.errlist.append(curerr)
                        
                    if (mod(self.sgdstep, self.plotint)==0):
                        #                        print self.predrunlist(len(self.predrunlist-self.erridx-1))
                        # --- make visualizations ---
                        tsline.set_xdata(arange(len(self.context)))
                        tsline.set_ydata(self.context)
                        predline.set_xdata(arange(len(self.context), len(self.context)+len(self.predlist)))
                        predline.set_ydata(self.predlist)
                        
                        ax[0].set_title('optimization curve sgd iteration = '+str(self.sgdstep))
                                                
                        optline.set_xdata(arange(len(self.estflist)))
                        optline.set_ydata(self.estflist)
                        ax[0].axis([0, len(self.estflist), 0, max(self.estflist)])
                        ax[1].axis([0, len(self.context)+len(self.predlist), -2, +2])
                        #ax[1].axis([0, len(self.context)+len(self.predlist), min(min(self.context), min(self.predlist)), max(max(self.context), max(self.predlist))])
                        
                        if mod(self.sgdstep, self.plotint*3) == 0:
                            ax[2].imshow(self.nn.layers[0].W); ax[2].axes.get_xaxis().set_visible(False); ax[2].axes.get_yaxis().set_visible(False)
#                            [a1, a2] = self.nn.layers[0].W.shape
#                            ax[2].imshow(self.nn.layers[0].W[0,:]); ax[2].axes.get_xaxis().set_visible(False); ax[2].axes.get_yaxis().set_visible(False)
#                            ax[3].imshow(self.nn.layers[0].W[1:a1,:]); ax[2].axes.get_xaxis().set_visible(False); ax[2].axes.get_yaxis().set_visible(False)
                            
#                            ax[6].hist(self.nn.layers[0].W[0,:].flatten().T)
#                            ax[7].hist(self.nn.layers[0].W[1:a1,:].flatten().T)
                            ax[3].imshow(self.nn.layers[1].W); ax[3].axes.get_xaxis().set_visible(False); ax[3].axes.get_yaxis().set_visible(False)
#                        ax[4].plot(arange(self.sgdstep), self.streamer.series[0:self.sgdstep])
#                        print self.streamer.series[0:self.sgdstep]
                        seriesline.set_xdata(arange(self.sgdstep))
                        seriesline.set_ydata(self.streamer.series[0:self.sgdstep])
                        
                        ax[4].axis([0, self.sgdstep, min(self.streamer.series[0:self.sgdstep]), max(self.streamer.series[0:self.sgdstep])])
                        
                        testerrline.set_xdata(arange(len(self.errlist)))
                        testerrline.set_ydata(self.errlist)

                        if len(self.errlist)>0:
                            ax[5].axis([0, len(self.errlist), min(self.errlist), max(self.errlist)])
                            ax[5].set_title('mean percentage test err at pred length '+str(self.erridx) +': '+str(mean(self.errlist[(len(self.errlist)-1000):(len(self.errlist)-1)])))
                        draw()
    
    def gensavename(self):
        strname = '/oms/trainer_'
        # stream TS id
        strname+=self.streamer.id.split('.')[0]
        strname+='_'
        # neural network nh1 nh2 ...
        strname+='nh'
        for i in range(len(self.nn.layers)):
            strname=strname + str(self.nn.layers[i].insz) + '_'
        
        strname = strname + str(self.nn.layers[len(self.nn.layers)-1].ousz) + '_'
        
        # learning rate
        strname = strname + 'lr' + str(self.lr) + '_'
        strname = strname + 'wc' + str(self.weightcost) + '_'
        strname = strname + 'sgdstep' + str(self.sgdstep)
        strname += '.pk'
        
        return strname
    
