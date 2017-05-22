import math

def pplavg(fname):
    ppls=[]
    tops=[]
    with open(fname) as f:
        lines=f.readlines()
        for line in lines[:-4]:
            words=line.split()
            ppls.extend([math.log(float(k)) for k in words])
            tops.extend([float(k=='1') for k in words])
    print(len(ppls))
    print(sum(ppls)/len(ppls))
    print(sum(tops)/len(tops))
    #print(math.exp(sum(ppls)/len(ppls)))

def rankrnnlm(fname):
    logranks=[]
    tops=[]
    with open(fname) as f:
        lines=f.readlines()
        print(len(lines))
        for line in lines[7:-6]:
            words=line.split()
            if words[2]!='</s>':
                logranks.append(math.log(float(words[1])))
                tops.append(float(words[1]=='1'))
    print(len(tops))
    print(sum(tops)/len(tops))
    print(sum(logranks)/len(logranks))

def avg_whole(origin,test):
    ppls=[]
    wppls=[]
    lines=open(origin).readlines()
    results=open(test).readlines()
    for r in results:
        ws=r.split()
	wppls.extend(float(ppl) for ppl in ws)
    index=0
    wcn=0
    print(len(wppls))
    print(sum(wppls)/len(wppls))
    for l in lines:
        wcn+=len(l.split())
        index+=8
        ws=l.split()
        for w in ws[8:]:
            if w!="<unk>":
                ppls.append(wppls[index])
                index+=1
            else:
                index+=1
        index+=1
        #ppls.append(wppls[index])
	#ppls.extend([math.log(rank+1) for rank in wppls[index:index+n-7]])
        #index+=(n-7)
    print(len(ppls))
    print(wcn)
    print(sum(ppls)/len(ppls))
    print('ppl:',math.exp(sum(ppls)/len(ppls)))

def avg_whole_rank(origin,test):
    ppls=[]
    wppls=[]
    lines=open(origin).readlines()
    results=open(test).readlines()
    for r in results:
        ws=r.split()
	wppls.extend(float(ppl) for ppl in ws)
    index=0
    wcn=0
    print(len(wppls))
    print(sum(wppls)/len(wppls))
    for l in lines:
        wcn+=len(l.split())
        index+=8
        ws=l.split()
        for w in ws[8:]:
            if w!="<unk>":
                ppls.append(math.log(wppls[index]+1))
                index+=1
            else:
                index+=1
        index+=1
        #ppls.append(wppls[index])
	#ppls.extend([math.log(rank+1) for rank in wppls[index:index+n-7]])
        #index+=(n-7)
    print(len(ppls))
    print(wcn)
    print('rank:',sum(ppls)/len(ppls))
    #print(math.exp(sum(ppls)/len(ppls)))

def avg_whole_top(origin,test):
    ppls=[]
    wppls=[]
    lines=open(origin).readlines()
    results=open(test).readlines()
    for r in results:
        ws=r.split()
	wppls.extend(float(ppl.strip()=="True") for ppl in ws)
    index=0
    print(len(wppls))
    print(sum(wppls)/len(wppls))
    for l in lines:
        index+=8
        ws=l.split()
        for w in ws[8:]:
            if w!="<unk>":
                ppls.append(wppls[index])
                index+=1
            else:
                index+=1
        index+=1
	#ppls.extend(wppls[index:index+n-7])
        #index+=(n-7)
    print('top_1:',sum(ppls)/len(ppls))

model="n3gram"

print('../models/ngram/'+model+'.rank')
#rankrnnlm('../models/rnnlm/'+model+'.rank')
pplavg('../models/ngram/'+model+'.rank')
#avg_whole("../data/test_unk.txt",'../models/tf/'+model+'/test_all')
#avg_whole_rank("../data/test_unk.txt",'../models/tf/'+model+'/test_rank')
#avg_whole_top("../data/test_unk.txt",'../models/tf/'+model+'/test_top_1')
