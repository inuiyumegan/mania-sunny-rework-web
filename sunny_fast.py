import os; os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import math, bisect
import numpy as np
from collections import defaultdict

import parser as _parser_mod

CROSS_MATRIX = {
    1: [0.075, 0.075], 2: [0.125, 0.05, 0.125],
    3: [0.125, 0.125, 0.125, 0.125], 4: [0.175, 0.25, 0.05, 0.25, 0.175],
    5: [0.175, 0.25, 0.175, 0.175, 0.25, 0.175],
    6: [0.225, 0.35, 0.25, 0.05, 0.25, 0.35, 0.225],
    7: [0.225, 0.35, 0.25, 0.225, 0.225, 0.25, 0.35, 0.225],
    8: [0.275, 0.45, 0.35, 0.25, 0.05, 0.25, 0.35, 0.45, 0.275],
    9: [0.275, 0.45, 0.35, 0.25, 0.275, 0.275, 0.25, 0.35, 0.45, 0.275],
    10: [0.325, 0.55, 0.45, 0.35, 0.25, 0.05, 0.25, 0.35, 0.45, 0.55, 0.325],
}

def _csum(x, f):
    F = np.zeros(len(x)); F[1:] = np.cumsum(f[:-1] * np.diff(x)); return F

def _smooth(x, f, w, scale=1.0, mode="sum"):
    x, f = np.asarray(x,float), np.asarray(f,float)
    F = _csum(x,f); a=np.clip(x-w,x[0],x[-1]); b=np.clip(x+w,x[0],x[-1])
    ia=np.clip(np.searchsorted(x,a)-1,0,len(x)-2); ib=np.clip(np.searchsorted(x,b)-1,0,len(x)-2)
    v=(F[ib]+f[ib]*(b-x[ib]))-(F[ia]+f[ia]*(a-x[ia]))
    if mode=="avg": return np.where(b>a,v/(b-a),0.0)
    return scale*v

def _rh(sr): return sr if sr<=9 else 9+(sr-9)/1.2
def _bl(a,t): return bisect.bisect_left(a,t)
def _br(a,t): return bisect.bisect_right(a,t)

def _ln_sparse(ln_seq,T):
    diff=defaultdict(float)
    for _,h,t in ln_seq:
        t0,t1=min(h+60,t),min(h+120,t); diff[t0]+=1.3; diff[t1]+=-0.3; diff[t]-=1.0
    pts=sorted({0,T}|set(diff)); vals=[]; cs=[0.0]; curr=0.0
    for i in range(len(pts)-1):
        curr+=diff.get(pts[i],0); v=min(curr,2.5+0.5*curr); vals.append(v)
        cs.append(cs[-1]+(pts[i+1]-pts[i])*v)
    return {"pts":pts,"cs":cs,"vals":vals}

def _lns(a,b,r):
    i=_br(r["pts"],a)-1; j=_br(r["pts"],b)-1
    if i==j: return (b-a)*r["vals"][i]
    return (r["pts"][i+1]-a)*r["vals"][i]+(r["cs"][j]-r["cs"][i+1])+(b-r["pts"][j])*r["vals"][j]

def _nxt(note,times,nbc):
    k,h=note[0],note[1]; idx=_bl(times,h)
    return nbc[k][idx+1] if idx+1<len(nbc[k]) else [0,10**9,10**9]

def _pre(file_path,sr=1.0,odf=None):
    p=_parser_mod.OsuFileParser(file_path); p.parse()
    od=p.od
    if odf=="HR": od=6.462+0.715*od
    elif odf=="EZ": od=-20.761+2.566*od
    elif odf is not None: od=float(odf)
    ts=1.0/sr if sr!=0 else 1.0
    ns=p.get_note_seq_with_tails(ts)
    x=0.3*math.sqrt((64.5-math.ceil(od*3))/500); x=min(x,0.6*(x-0.09)+0.09)
    K=p.column_count; nbc=p.get_note_seq_by_column(ns,K)
    ln_seq=[n for n in ns if n[2]>=0]; tail_seq=sorted(ln_seq,key=lambda n:n[2])
    T=max((max((n[1] for n in ns),default=0),max((n[2] for n in ns),default=0)))+1
    return{"x":x,"K":K,"T":T,"note_seq":ns,"nbc":nbc,"ln_seq":ln_seq,"tail_seq":tail_seq,
           "lr":p.ln_ratio,"cc":K,"tn":p.total_notes,"lnc":p.ln_count,"od":p.od}

def _corners(T,ns):
    cb={0,T}; ca={0,T}
    for _,h,t in ns:
        cb.update([h,h+501,h-499,h+1])
        if t>=0: cb.update([t,t+501,t-499,t+1])
    for _,h,t in ns:
        ca.update([h,h+1000,h-1000])
        if t>=0: ca.update([t,t+1000,t-1000])
    base=sorted(s for s in cb if 0<=s<=T)
    ac=sorted(s for s in ca if 0<=s<=T)
    return np.array(sorted(set(base)|set(ac)),float),np.array(base,float),np.array(ac,float)

def _ku(K,T,ns,bc):
    ku=np.zeros((K,len(bc)),dtype=bool)
    N=len(ns)
    ks=np.array([n[0] for n in ns],dtype=np.int32)
    hs=np.array([max(n[1]-150,0) for n in ns],float)
    ts=np.array([min(n[2]+150,T-1) if n[2]>=0 else min(n[1]+150,T-1) for n in ns],float)
    li=np.searchsorted(bc,hs,"left"); ri=np.searchsorted(bc,ts,"left")
    for i in range(N):
        if ri[i]>li[i]: ku[ks[i],li[i]:ri[i]]=True
    return ku

def _ku400(K,T,ns,bc):
    N=len(ns)
    ks=np.array([n[0] for n in ns],dtype=np.int32)
    hs=np.array([max(n[1],0) for n in ns],float)
    es=np.array([n[2] if n[2]>=0 else n[1] for n in ns],float)
    es=np.clip(es,0,T-1)
    dur=np.maximum(es-hs,1)

    l400=np.searchsorted(bc,hs-400,"left"); ll=np.searchsorted(bc,hs,"left")
    rr=np.searchsorted(bc,es,"left"); r400=np.searchsorted(bc,es+400,"left")

    ku=np.zeros((K,len(bc)))
    inv_denom=3.75/400**2

    for i in range(N):
        k=ks[i]; h=hs[i]; e=es[i]
        l4=l400[i]; l=ll[i]; r=rr[i]; r4=r400[i]

        ku[k,l:r]+=3.75+min(dur[i],1500)/150.0

        if l4<l:
            d=bc[l4:l]-h; ku[k,l4:l]+=3.75-inv_denom*d*d
        if r<r4:
            d=bc[r:r4]-e; ku[k,r:r4]+=3.75-inv_denom*d*d

    return ku

def _anchor(K,ku400,bc):
    c=np.sort(ku400.T,axis=1)[:,::-1]; nz=c>0; nnz=nz.sum(axis=1)
    c0,c1=c[:,:-1],c[:,1:]; safe=np.where(c0>0,c0,1.0)
    ratio=np.where(c0>0,c1/safe,0.0); w=1-4*(0.5-ratio)**2
    pv=nz[:,:-1]&nz[:,1:]; walk=np.sum(np.where(pv,c0*w,0),axis=1)
    mw=np.sum(np.where(pv,c0,0),axis=1)
    raw=np.where(nnz>1,walk/np.maximum(mw,1e-9),0.0)
    return 1+np.minimum(raw-0.18,5*(raw-0.22)**3)

def _Jbar(K,x,nbc,bc):
    def jn(d): return 1-7e-5*(0.15+abs(d-0.08))**(-4)
    J=np.zeros((K,len(bc))); D=np.full((K,len(bc)),1e9)
    for k in range(K):
        notes=nbc[k]
        if len(notes)<2: continue
        starts=np.array([n[1] for n in notes[:-1]],float)
        ends=np.array([n[1] for n in notes[1:]],float)
        li=np.searchsorted(bc,starts,"left"); ri=np.searchsorted(bc,ends,"left")
        deltas=0.001*(ends-starts)
        vals=deltas**-1*(deltas+0.11*x**0.25)**-1*jn(deltas)
        for j in range(len(li)):
            if ri[j]>li[j]: J[k,li[j]:ri[j]]=vals[j]; D[k,li[j]:ri[j]]=deltas[j]

    Jb=np.array([_smooth(bc,J[k],500,0.001,"sum") for k in range(K)])
    w=1.0/D
    return D,(np.sum(np.maximum(Jb,0)**5*w,axis=0)/np.maximum(np.sum(w,axis=0),1e-9))**0.2

def _Xbar(K,x,nbc,act,bc):
    cross=CROSS_MATRIX.get(K,[1.0/(K+1)]*(K+1))
    Xks={k:np.zeros(len(bc)) for k in range(K+1)}
    fc={k:np.zeros(len(bc)) for k in range(K+1)}
    for k in range(K+1):
        notes=list(nbc[0]) if k==0 else (list(nbc[K-1]) if k==K else sorted(list(nbc[k-1])+list(nbc[k]),key=lambda n:n[1]))
        for i in range(1,len(notes)):
            s,e=notes[i-1][1],notes[i][1]
            if e<=s: continue
            li,ri=np.searchsorted(bc,s,"left"),np.searchsorted(bc,e,"left")
            if ri<=li: continue
            d=0.001*(e-s); val=0.16*max(x,d)**-2
            la=act[li] if li<len(act) else set(); ra=act[min(ri,len(act)-1)]
            if(k-1 not in la and k-1 not in ra)or(k not in la and k not in ra): val*=1-cross[k]
            Xks[k][li:ri]=val; fc[k][li:ri]=max(0,0.4*max(d,0.06,0.75*x)**-2-80)
    Xb=np.zeros(len(bc))
    for i in range(len(bc)):
        s1=sum(Xks[k][i]*cross[k] for k in range(K+1))
        s2=sum(np.sqrt(max(fc[k][i]*cross[k]*fc[k+1][i]*cross[k+1],0)) for k in range(K))
        Xb[i]=s1+s2
    return _smooth(bc,Xb,500,0.001,"sum")

def _Pbar(x,ns,ln_rep,anchor,bc):
    def sb(delta):
        expr=7.5/delta
        if 160<expr<360: return 1+1.7e-7*(expr-160)*(expr-360)**2
        return 1.0
    Ps=np.zeros(len(bc))
    for i in range(len(ns)-1):
        hl,hr=ns[i][1],ns[i+1][1]; dt=hr-hl
        if dt<1e-9:
            spike=1000*(0.02*(4/x-24))**0.25
            li,ri=np.searchsorted(bc,hl,"left"),np.searchsorted(bc,hl,"right")
            if ri>li: Ps[li:ri]+=spike
            continue
        li,ri=np.searchsorted(bc,hl,"left"),np.searchsorted(bc,hr,"left")
        if ri<=li: continue
        d=0.001*dt; v=1+6*0.001*_lns(hl,hr,ln_rep); bv=sb(d)
        if d<2*x/3:
            inner=0.08*x**-1*(1-24*x**-1*(d-x/2)**2)
            inc=d**-1*max(inner,0)**0.25*max(bv,v)
        else:
            inner=0.08*x**-1*(1-24*x**-1*(x/6)**2)
            inc=d**-1*max(inner,0)**0.25*max(bv,v)
        Ps[li:ri]+=np.minimum(inc*anchor[li:ri],np.maximum(inc,inc*2-10))
    return _smooth(bc,Ps,500,0.001,"sum")

def _Abar(K,act,d_ks,Ac,bc):
    dks=np.zeros((K-1,len(bc)))
    for i in range(len(bc)):
        cols=sorted(act[i])
        for j in range(len(cols)-1):
            k0,k1=cols[j],cols[j+1]; dks[k0,i]=abs(d_ks[k0,i]-d_ks[k1,i])+0.4*max(0,max(d_ks[k0,i],d_ks[k1,i])-0.11)
    As=np.ones(len(Ac)); bci=np.clip(np.searchsorted(bc,Ac),0,len(bc)-1)
    for i in range(len(Ac)):
        idx=bci[i]; cols=sorted(act[idx])
        for j in range(len(cols)-1):
            k0,k1=cols[j],cols[j+1]; dv=dks[k0,idx]; dk0,dk1=d_ks[k0,idx],d_ks[k1,idx]
            if dv<0.02: As[i]*=min(0.75+0.5*max(dk0,dk1),1)
            elif dv<0.07: As[i]*=min(0.65+5*dv+0.5*max(dk0,dk1),1)
    return _smooth(Ac,As,250,1.0,"avg")

def _Rbar(K,x,nbc,tail_seq,bc):
    Rs=np.zeros(len(bc))
    tbc={k:[n[1] for n in nbc[k]] for k in range(K)}; Il=[]
    for k,h_i,t_i in tail_seq:
        nxt=_nxt([k,h_i,t_i],tbc[k],nbc); hj=nxt[1]
        Ih=0.001*abs(t_i-h_i-80)/x; It=0.001*abs(hj-t_i-80)/x
        Il.append(2/(2+math.exp(-5*(Ih-0.75))+math.exp(-5*(It-0.75))))
    for i in range(len(tail_seq)-1):
        ts,te=tail_seq[i][2],tail_seq[i+1][2]
        li,ri=np.searchsorted(bc,ts,"left"),np.searchsorted(bc,te,"left")
        if ri<=li: continue
        rv=0.08*(0.001*(te-ts))**-0.5*x**-1*(1+0.8*(Il[i]+Il[i+1])); Rs[li:ri]=rv
    return _smooth(bc,Rs,500,0.001,"sum")

def _CK(K,ns,ku,bc):
    nht=np.array(sorted(n[1] for n in ns),float)
    lo=np.searchsorted(nht,bc-500,"left"); hi=np.searchsorted(nht,bc+500,"left")
    Cs=(hi-lo).astype(float); Kss=np.maximum(ku.sum(axis=0),1).astype(float)
    return Cs,Kss

def calculate(file_path,speed_rate=1.0,od_flag=None):
    pp=_pre(file_path,speed_rate,od_flag)
    x,K,T=pp["x"],pp["K"],pp["T"]; ns=pp["note_seq"]
    nbc,ln_seq,tail_seq=pp["nbc"],pp["ln_seq"],pp["tail_seq"]
    ac,bc,Ac=_corners(T,ns)
    ku=_ku(K,T,ns,bc)
    act=[set(k for k in range(K) if ku[k,i]) for i in range(len(bc))]
    ku400=_ku400(K,T,ns,bc); anchor=_anchor(K,ku400,bc)

    d_ks,Jb=_Jbar(K,x,nbc,bc); Jbar=np.interp(ac,bc,Jb)
    ln_rep=_ln_sparse(ln_seq,T)
    Xb=_Xbar(K,x,nbc,act,bc); Xbar=np.interp(ac,bc,Xb)
    Pb=_Pbar(x,ns,ln_rep,anchor,bc); Pbar=np.interp(ac,bc,Pb)
    Ab=_Abar(K,act,d_ks,Ac,bc); Abar=np.interp(ac,Ac,Ab)
    Rb=_Rbar(K,x,nbc,tail_seq,bc); Rbar=np.interp(ac,bc,Rb)
    Cs,Kss=_CK(K,ns,ku,bc); Carr=np.interp(ac,bc,Cs)
    idx=np.clip(np.searchsorted(bc,ac,"right")-1,0,len(Kss)-1); Ks=Kss[idx]

    Sa=(0.4*(Abar**(3/Ks)*np.minimum(Jbar,8+0.85*Jbar))**1.5+
        0.6*(Abar**(2/3)*(0.8*Pbar+Rbar*35/(Carr+8)))**1.5)**(2/3)
    Ta=(Abar**(3/Ks)*Xbar)/(Xbar+Sa+1)
    Da=2.7*Sa**0.5*Ta**1.5+Sa*0.27

    g=np.empty_like(ac); g[0]=(ac[1]-ac[0])/2; g[-1]=(ac[-1]-ac[-2])/2
    g[1:-1]=(ac[2:]-ac[:-2])/2
    we=Carr*g; order=np.argsort(Da); Ds,ws=Da[order],we[order]
    cw=np.cumsum(ws); norm=cw/cw[-1]
    tg=np.array([0.945,0.935,0.925,0.915,0.845,0.835,0.825,0.815])
    ip=np.searchsorted(norm,tg,"left")
    p93=np.mean(Ds[ip[:4]]); p83=np.mean(Ds[ip[4:8]])
    wm=(np.sum(Ds**5*ws)/np.sum(ws))**0.2
    sr=0.88*p93*0.25+0.94*p83*0.2+wm*0.55
    ln_len=sum(min(t-h,1000)/200.0 for _,h,t in ln_seq)
    tn=len(ns)+0.5*ln_len; sr*=tn/(tn+60); sr=_rh(sr)*0.975
    return{"star":sr,"ln_ratio":pp["lr"],"column_count":pp["cc"],"total_notes":pp["tn"],"ln_count":pp["lnc"],"od":pp["od"]}
