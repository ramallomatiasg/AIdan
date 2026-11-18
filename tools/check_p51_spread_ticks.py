"""check_p51_spread_ticks.py - P51: spread REAL (ticks MT5) en el momento de la entrada vs el minimo de la vela de la cache.
READ-ONLY. Requiere MT5 => correr con AIdan CERRADO. MT5 solo guarda ticks desde 2026.
"""
import sys;sys.path.insert(0,r'F:\AIdan')
import numpy as np, MetaTrader5 as mt5
from datetime import datetime,timezone
import tools.backtest_p51_gap_semanal as M
from tools.backtest_fase4_planes import load_pair
assert mt5.initialize(), mt5.last_error()
# offset server-UTC: los ticks de MT5 vienen en hora server; la cache tiene t (server) y utc
rows=[]
for s in M.DISC+M.RES_LEFT:
    ev,_=M.run_pair(s,0.5); P=load_pair(s); u=P['utc']; pip=P['pip']
    di={int(x):i for i,x in enumerate(u)}
    for e in ev:
        i=di[e['t']]; ts=int(P['t'][i])   # hora server del open de la vela de entrada
        tk=mt5.copy_ticks_range(s, datetime.fromtimestamp(ts,timezone.utc), datetime.fromtimestamp(ts+120,timezone.utc), mt5.COPY_TICKS_ALL)
        if tk is None or len(tk)==0: continue
        b,a=tk[0]['bid'],tk[0]['ask']
        rows.append((s,e["t"],(b-P["o"][i])/pip,(a-b)/pip,P["spr"][i],e["net"]))
mt5.shutdown()
r=np.array([x[2:] for x in rows],float)
print('n',len(r),'bid tick - open cache (p) mediana',np.median(r[:,0]).round(2),'| spread real tick mediano',np.median(r[:,1]).round(2),'media',r[:,1].mean().round(2),'| spread cache mediano',np.median(r[:,2]).round(2))
net=r[:,3]; adj=net-(r[:,1]-r[:,2])
print('neto cache',net.mean().round(2),'| neto con spread real del tick',adj.mean().round(2),'mediana',np.median(adj).round(2),'ganados',(adj>0).mean().round(2))
from datetime import datetime as _d
yrs=np.array([_d.fromtimestamp(x[1],timezone.utc).year for x in rows])
for y in sorted(set(yrs)):
    m=yrs==y; print(y,'n',m.sum(),'spread tick med',np.median(r[m,1]).round(1),'neto cache',net[m].mean().round(2),'neto real',adj[m].mean().round(2))
