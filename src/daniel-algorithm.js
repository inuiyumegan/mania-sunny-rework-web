var computeDanielSR = (function () {
function bsl(arr, t) { var l=0,r=arr.length; while(l<r){var m=(l+r)>>1;if(arr[m]<t)l=m+1;else r=m;} return l; }
function bsr(arr, t) { var l=0,r=arr.length; while(l<r){var m=(l+r)>>1;if(arr[m]<=t)l=m+1;else r=m;} return l; }
function csum(x, f) { var F=new Float64Array(x.length); for(var i=1;i<x.length;i++)F[i]=F[i-1]+f[i-1]*(x[i]-x[i-1]); return F; }
function qcsum(q,x,F,f){if(q<=x[0])return 0;if(q>=x[x.length-1])return F[F.length-1];var i=bsr(x,q)-1;return F[i]+f[i]*(q-x[i]);}
function smoothCorners(x,f,w,sc,m){sc=sc||1;m=m||"sum";var F=csum(x,f),g=new Float64Array(f.length);
 for(var i=0;i<x.length;i++){var s=x[i],a=Math.max(s-w,x[0]),b=Math.min(s+w,x[x.length-1]);
 var v=qcsum(b,x,F,f)-qcsum(a,x,F,f);g[i]=m==="avg"&&(b-a)>0?v/(b-a):sc*v;}return g;}
function interpV(newX,oldX,oldV){var o=new Float64Array(newX.length),idx=0;
 for(var i=0;i<newX.length;i++){var x=newX[i];if(x<=oldX[0]){o[i]=oldV[0];continue;}if(x>=oldX[oldX.length-1]){o[i]=oldV[oldV.length-1];continue;}
 while(idx+1<oldX.length&&oldX[idx+1]<x)idx++;var x0=oldX[idx],x1=oldX[idx+1],y0=oldV[idx],y1=oldV[idx+1];if(x1===x0){o[i]=y0;continue;}
 o[i]=y0+(x-x0)/(x1-x0)*(y1-y0);}return o;}
function stepI(newX,oldX,oldV){var o=new Float64Array(newX.length),idx=0;
 for(var i=0;i<newX.length;i++){var x=newX[i];while(idx+1<oldX.length&&oldX[idx+1]<=x)idx++;o[i]=oldV[Math.max(0,Math.min(idx,oldV.length-1))];}return o;}
function rescaleH(sr){return sr<=9?sr:9+(sr-9)*(1/1.2);}

// Daniel 4K RC algorithm by TheBagelOfMan (https://github.com/TheBagelOfMan/Daniel)
// IMPORTANT: By design, this algorithm treats all notes as single taps (rice).
// Long notes (LNs) are NOT treated differently — only note start times are used,
// note end times and types are ignored. This is intentional for RC (rice) tier estimation.
return function computeDanielSR(columns, noteStarts, noteEnds, noteTypes, columnCount, speedRate) {
  speedRate = speedRate || 1.0;
  if (columnCount !== 4) return -3;
  var K = 4;
  var timeScale = 1 / speedRate;
  var od = 9;

  var noteSeq = [];
  for (var i = 0; i < columns.length; i++) {
    var k = columns[i];
    var h = Math.floor(noteStarts[i] * timeScale);
    noteSeq.push([k, h]);
  }
  noteSeq.sort(function(a,b){return a[1]!==b[1]?a[1]-b[1]:a[0]-b[0];});

  var noteSeqByColumn = [[],[],[],[]];
  for (var i = 0; i < noteSeq.length; i++) noteSeqByColumn[noteSeq[i][0]].push(noteSeq[i]);

  var x = 0.3 * Math.sqrt((64.5 - Math.ceil(od * 3)) / 500);
  x = Math.min(x, 0.6 * (x - 0.09) + 0.09);
  var T = noteSeq.length ? noteSeq[noteSeq.length-1][1] + 1 : 0;

  if (!noteSeq.length || T <= 0) return -1;

  // corners
  var cb = new Set();
  for (var i2=0;i2<noteSeq.length;i2++){var h=noteSeq[i2][1];cb.add(h);cb.add(h+501);cb.add(h-499);cb.add(h+1);}
  cb.add(0);cb.add(T);
  var baseC = Array.from(cb).filter(function(s){return s>=0&&s<=T;}).sort(function(a,b){return a-b;});

  var cA = new Set();
  for (var i3=0;i3<noteSeq.length;i3++){var h2=noteSeq[i3][1];cA.add(h2);cA.add(h2+1000);cA.add(h2-1000);}
  cA.add(0);cA.add(T);
  var AC = Array.from(cA).filter(function(s){return s>=0&&s<=T;}).sort(function(a,b){return a-b;});

  var allC = Array.from(new Set(baseC.concat(AC))).sort(function(a,b){return a-b;});

  // keyUsage
  var ku = {0:new Uint8Array(baseC.length),1:new Uint8Array(baseC.length),2:new Uint8Array(baseC.length),3:new Uint8Array(baseC.length)};
  for (var i4=0;i4<noteSeq.length;i4++){var k2=noteSeq[i4][0],h3=noteSeq[i4][1];
   var st=Math.max(h3-150,0),et=Math.min(h3+150,T-1);
   var li=bsl(baseC,st),ri=bsl(baseC,et);
   for(var idx=li;idx<ri;idx++)ku[k2][idx]=1;}

  var ac=baseC.map(function(_,i){var a=[];for(var k3=0;k3<K;k3++)if(ku[k3][i])a.push(k3);return a;});

  // keyUsage400 — aligned with algorithm.js getKeyUsage400
  var ku4 = {0:new Float64Array(baseC.length),1:new Float64Array(baseC.length),2:new Float64Array(baseC.length),3:new Float64Array(baseC.length)};
  for (var i5=0;i5<noteSeq.length;i5++){var k4=noteSeq[i5][0],h4=noteSeq[i5][1],t4=0;
   var li4=bsl(baseC,h4-400),li=bsl(baseC,h4),ri=bsl(baseC,t4<0?h4:t4),ri4=bsl(baseC,(t4<0?h4:t4)+400);
   if(li>=ri){ri=bsl(baseC,h4+1);}
   for(var idx2=li;idx2<ri;idx2++)ku4[k4][idx2]+=3.75;
   for(var idx3=li4;idx3<li;idx3++)ku4[k4][idx3]+=3.75-(3.75/160000)*Math.pow(baseC[idx3]-h4,2);
   for(var idx4=ri;idx4<ri4;idx4++)ku4[k4][idx4]+=3.75-(3.75/160000)*Math.pow(baseC[idx4]-(t4<0?h4:t4),2);}

  // anchor
  var anchor = new Float64Array(baseC.length);
  for(var i6=0;i6<baseC.length;i6++){var cnts=[ku4[0][i6],ku4[1][i6],ku4[2][i6],ku4[3][i6]];cnts.sort(function(a,b){return b-a;});
   var nz=cnts.filter(function(v){return v>0;});var raw=0;
   if(nz.length>1){var walk=0,mw=0;for(var j2=0;j2<nz.length-1;j2++){var r2=nz[j2+1]/nz[j2];walk+=nz[j2]*(1-4*Math.pow(0.5-r2,2));mw+=nz[j2];}raw=mw>0?walk/mw:0;}
   anchor[i6]=1+Math.min(raw-0.18,5*Math.pow(raw-0.22,3));}

  // Jbar
  var jj=function(d){return 1-7e-5*Math.pow(0.15+Math.abs(d-0.08),-4);};
  var Jks={0:new Float64Array(baseC.length),1:new Float64Array(baseC.length),2:new Float64Array(baseC.length),3:new Float64Array(baseC.length)};
  var dKs={0:new Float64Array(baseC.length),1:new Float64Array(baseC.length),2:new Float64Array(baseC.length),3:new Float64Array(baseC.length)};
  for(var k5=0;k5<4;k5++){dKs[k5].fill(1e9);var ns=noteSeqByColumn[k5];
   for(var i7=0;i7<ns.length-1;i7++){var st2=ns[i7][1],en=ns[i7+1][1];if(en<=st2)continue;
    var li5=bsl(baseC,st2),ri5=bsl(baseC,en);if(li5>=ri5)continue;
    var d2=0.001*(en-st2),val=Math.pow(d2,-1)*Math.pow(d2+0.11*Math.pow(x,0.25),-1)*jj(d2);
    for(var idx4=li5;idx4<ri5;idx4++){Jks[k5][idx4]=val;dKs[k5][idx4]=d2;}}}
  var JbarKs={};for(var k6=0;k6<4;k6++)JbarKs[k6]=smoothCorners(baseC,Jks[k6],500,0.001,"sum");
  var Jbar = new Float64Array(baseC.length);
  for(var i8=0;i8<baseC.length;i8++){var num=0,den=0;for(var k7=0;k7<4;k7++){var v=JbarKs[k7][i8],w=1/Math.max(dKs[k7][i8],1e-9);num+=Math.pow(Math.max(v,0),5)*w;den+=w;}Jbar[i8]=Math.pow(num/Math.max(den,1e-9),0.2);}

  // Xbar
  var cm=[[-1],[0.075,0.075],[0.125,0.05,0.125],[0.125,0.125,0.125,0.125],[0.175,0.25,0.05,0.25,0.175]];
  var cc=cm[4];
  var Xks={};var fc={};
  for(var k8=0;k8<=4;k8++){Xks[k8]=new Float64Array(baseC.length);fc[k8]=new Float64Array(baseC.length);}
  for(var k9=0;k9<=4;k9++){var np=[];if(k9===0)np=noteSeqByColumn[0];else if(k9===4)np=noteSeqByColumn[3];else{
    np=noteSeqByColumn[k9-1].concat(noteSeqByColumn[k9]);np.sort(function(a,b){return a[1]-b[1];});}
   for(var j3=1;j3<np.length;j3++){var st3=np[j3-1][1],en2=np[j3][1];if(en2<=st3)continue;
    var li6=bsl(baseC,st3),ri6=bsl(baseC,en2);if(ri6<=li6)continue;
    var d3=0.001*(en2-st3),val2=0.16*Math.pow(Math.max(x,d3),-2);
    var lcols=ac[li6]||[],rcols=ac[ri6]||[];
    var li7=(!lcols.includes(k9-1)&&!rcols.includes(k9-1)),ri7=(!lcols.includes(k9)&&!rcols.includes(k9));
    if(li7||ri7)val2*=1-cc[k9];
    var fv=Math.max(0,0.4*Math.pow(Math.max(d3,0.06,0.75*x),-2)-80);
    for(var idx5=li6;idx5<ri6;idx5++){Xks[k9][idx5]=val2;fc[k9][idx5]=fv;}}}
  var XB=new Float64Array(baseC.length);
  for(var i9=0;i9<baseC.length;i9++){var s1=0,s2=0;for(var ka=0;ka<=4;ka++)s1+=Xks[ka][i9]*cc[ka];
   for(var kb=0;kb<4;kb++){var p=fc[kb][i9]*cc[kb]*fc[kb+1][i9]*cc[kb+1];if(p>0)s2+=Math.sqrt(p);}XB[i9]=s1+s2;}
  var Xbar = smoothCorners(baseC,XB,500,0.001,"sum");
  var Ji=interpV(allC,baseC,Jbar);
  var Xi=interpV(allC,baseC,Xbar);

  // Pbar
  var sb=function(d){var bpm=Math.max(0,Math.min(7.5/Math.max(d,1e-9),420));var p2=0.10/(1+Math.exp(-0.06*(bpm-175)));var s=(bpm>=200&&bpm<=350)?0.30*(1-Math.exp(-0.02*(bpm-200))):0;return 1+p2+s;};
  var PS=new Float64Array(baseC.length);
  for(var j4=0;j4<noteSeq.length-1;j4++){var hL=noteSeq[j4][1],hR=noteSeq[j4+1][1],dt=hR-hL;
   if(dt<1e-9){var sp=1000*Math.pow(0.02*(4/x-24),0.25);var li8=bsl(baseC,hL),ri8=bsr(baseC,hL);for(var idx6=li8;idx6<ri8;idx6++)PS[idx6]+=sp;continue;}
   var li9=bsl(baseC,hL),ri9=bsl(baseC,hR);if(ri9<=li9)continue;
   var d4=0.001*dt,bV=sb(d4),baseInc=Math.pow(0.08/x*(1-24/x*Math.pow(x/6,2)),0.25);
   var inc;if(d4<2*x/3)inc=Math.pow(d4,-1)*Math.pow(0.08/x*(1-24/x*Math.pow(d4-x/2,2)),0.25)*Math.max(bV,1);
   else inc=Math.pow(d4,-1)*baseInc*Math.max(bV,1);
   for(var idx7=li9;idx7<ri9;idx7++){var b=inc*anchor[idx7];PS[idx7]+=Math.min(b,Math.max(inc,inc*2-10));}}
  var Pbar=smoothCorners(baseC,PS,500,0.001,"sum");
  var Pi=interpV(allC,baseC,Pbar);

  // Abar
  var dks={};for(var kc=0;kc<3;kc++)dks[kc]=new Float64Array(baseC.length);
  for(var ia=0;ia<baseC.length;ia++){var cols=ac[ia]||[];for(var j5=0;j5<cols.length-1;j5++){var k0=cols[j5],k1=cols[j5+1];dks[k0][ia]=Math.abs(dKs[k0][ia]-dKs[k1][ia])+0.4*Math.max(0,Math.max(dKs[k0][ia],dKs[k1][ia])-0.11);}}
  var AS=new Float64Array(AC.length).fill(1);
  for(var ib=0;ib<AC.length;ib++){var idx8=Math.max(0,Math.min(bsl(baseC,AC[ib]),baseC.length-1));var cols2=ac[idx8]||[];
   for(var j6=0;j6<cols2.length-1;j6++){var k02=cols2[j6],k12=cols2[j6+1],dV=dks[k02][idx8];if(dV<0.02)AS[ib]*=Math.min(0.75+0.5*Math.max(dKs[k02][idx8],dKs[k12][idx8]),1);
    else if(dV<0.07)AS[ib]*=Math.min(0.65+5*dV+0.5*Math.max(dKs[k02][idx8],dKs[k12][idx8]),1);}}
  var Abar=smoothCorners(AC,AS,250,1,"avg");
  var Ai=interpV(allC,AC,Abar);

  // C and Ks
  var nht=noteSeq.map(function(n){return n[1];}).sort(function(a,b){return a-b;});
  var CS=new Float64Array(baseC.length);var lo2=0,hi2=0;
  for(var ic=0;ic<baseC.length;ic++){var s3=baseC[ic],low=s3-500,high=s3+500;
   while(lo2<nht.length&&nht[lo2]<low)lo2++;while(hi2<nht.length&&nht[hi2]<high)hi2++;CS[ic]=hi2-lo2;}
  var KS=new Float64Array(baseC.length);for(var id=0;id<baseC.length;id++){var cnt=0;for(var kd=0;kd<4;kd++)if(ku[kd][id])cnt++;KS[id]=Math.max(cnt,1);}
  var Ci=stepI(allC,baseC,CS);
  var Ksi=stepI(allC,baseC,KS);

  // D
  var DA=new Array(allC.length);
  for(var ie=0;ie<allC.length;ie++){
   var lp=0.4*Math.pow(Math.pow(Ai[ie],3/Ksi[ie])*Math.min(Ji[ie],8+0.85*Ji[ie]),1.5);
   var rp=0.6*Math.pow(Math.pow(Ai[ie],2/3)*(0.8*Pi[ie]),1.5);
   var SA=Math.pow(lp+rp,2/3);
   var TA=Math.pow(Ai[ie],3/Ksi[ie])*Xi[ie]/(Xi[ie]+SA+1);
   DA[ie]=2.7*Math.pow(SA,0.5)*Math.pow(TA,1.5)+SA*0.27;}

  var gaps=new Array(allC.length);gaps[0]=(allC[1]-allC[0])/2;gaps[gaps.length-1]=(allC[allC.length-1]-allC[allC.length-2])/2;
  for(var i2=1;i2<allC.length-1;i2++)gaps[i2]=(allC[i2+1]-allC[i2-1])/2;
  var ew=Ci.map(function(c,i){return c*gaps[i];});
  var si=DA.map(function(_,i){return i;}).sort(function(a,b){return DA[a]-DA[b];});
  var DS=si.map(function(i){return DA[i];});
  var wS=si.map(function(i){return ew[i];});
  var cw=new Array(wS.length);var run=0;for(var i3=0;i3<wS.length;i3++){run+=wS[i3];cw[i3]=run;}
  var tw=cw[cw.length-1];if(!isFinite(tw)||tw<=0)return 0;
  var ncw=cw.map(function(w){return w/tw;});
  var tps=[0.945,0.935,0.925,0.915,0.845,0.835,0.825,0.815];
  var pi2=tps.map(function(p){return bsl(ncw,p);});
  var fg=pi2.slice(0,4).map(function(idx){return DS[Math.min(idx,DS.length-1)];});
  var sg=pi2.slice(4,8).map(function(idx){return DS[Math.min(idx,DS.length-1)];});
  var p93=fg.reduce(function(a,v){return a+v;},0)/4;
  var p83=sg.reduce(function(a,v){return a+v;},0)/4;
  var num2=0,den2=0;for(var i4=0;i4<DS.length;i4++){num2+=Math.pow(DS[i4],5)*wS[i4];den2+=wS[i4];}
  var wm=Math.pow(num2/Math.max(den2,1e-9),0.2);
  var sr=(0.88*p93)*0.25+(0.94*p83)*0.2+wm*0.55;
  sr*=noteSeq.length/(noteSeq.length+60);
  sr=rescaleH(sr)*0.975;
  return sr;
};
})();
