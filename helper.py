def num_contain(f,token):
    with open(f) as fin:
        lines=fin.readlines()
	r=[l for l in lines if token not in l]
	print(len(r))

def combine(f1,f2,w):
    l1=open(f1).readlines()
    l2=open(f2).readlines()
    pair=zip(l1,l2)
    print(pair[0])
    r=[lin1.strip()+" "+lin2.strip()+"\n" for lin1,lin2 in zip(l1,l2)]
    print(r[0])
    with open(w,"w") as fout:
        fout.writelines(r)

def combine_for_lstm(f1,f2,w):
    l1=open(f1).readlines()
    l2=open(f2).readlines()
    r=[lin1.strip()+" "+lin2.strip()+" "+lin3 for lin1,lin2,lin3 in zip(l1,l2[:400],l2[400:])]
    with open(w,"w") as fout:
        fout.writelines(r)
    print(w)

#num_contain('../models/tf/8192-2048nd/complete.txt','<S>')
#combine('../data/generate.txt','../models/tf/biglstm/generate_all','../models/tf/biglstm/generate.txt')
combine_for_lstm('../data/generate.txt','../models/tf/biglstm/generate_all','../models/tf/biglstm/complete.txt')
