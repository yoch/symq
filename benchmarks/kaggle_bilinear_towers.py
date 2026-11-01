"""Independently derive GF(16) rank-nine and GF(64) rank-fifteen bilinear decompositions.

Mathematical context: https://github.com/ZIB-IOL/polytof (MIT) and
https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation
Reference only: this file is independently written, not copied from the dataset.
"""
from functools import reduce


def gf4mul(a, b):
    p = (a&1)*(b&1)
    q = (a&1)*((b>>1)&1) ^ ((a>>1)&1)*(b&1)
    r = ((a>>1)&1)*((b>>1)&1)
    return (p^r) | ((q^r)<<1)


def gf4pow(a,k):
    v=1
    for _ in range(k): v=gf4mul(v,a)
    return v


def tower_mul(a,b,degree):
    assert degree in (2,3)
    assert 0<=a<1<<(2*degree) and 0<=b<1<<(2*degree)
    A=[(a>>(2*i))&3 for i in range(degree)]
    B=[(b>>(2*i))&3 for i in range(degree)]
    p=[0]*(2*degree-1)
    for i in range(degree):
        for j in range(degree):
            p[i+j]^=gf4mul(A[i],B[j])
    if degree==2:
        # z^2 = z + omega
        p[0]^=gf4mul(p[2],2)
        p[1]^=p[2]
    else:
        # z^3 = z + 1; z^4 = z^2 + z
        for i in (4,3):
            p[i-3]^=p[i]
            p[i-2]^=p[i]
    return sum(p[i]<<(2*i) for i in range(degree))


def field_mul(a,b,n,mod):
    r=0
    for _ in range(n):
        if b&1: r ^=a
        b >>=1
        a<<=1
        if a&(1<<n): a^=mod
    return r


def rank(columns):
    piv={}
    for x in columns:
        while x:
            k=x.bit_length()-1
            if k not in piv:
                piv[k]=x
                break
            x^=piv[k]
    return len(piv)


def field_isomorphism(degree,mod):
    n=2*degree
    for g in range(2,1<<n):
        powers=[1]
        for _ in range(n): powers.append(tower_mul(powers[-1],g,degree))
        poly_image=0
        for i in range(n+1):
            if mod>>i&1: poly_image ^=powers[i]
        if poly_image or rank(powers[:n]) != n: continue
        forward=tuple(
            reduce(int.__xor__,(powers[i] for i in range(n) if a>>i&1),0)
            for a in range(1<<n)
        )
        inv=[0]*(1<<n)
        for i,v in enumerate(forward): inv[v]=i
        assert len(set(forward))==1<<n
        for a in range(1<<n):
            for b in range(1<<n):
                assert forward[field_mul(a,b,n,mod)]==tower_mul(forward[a],forward[b],degree)
        return forward,tuple(inv),g
    raise ValueError('field iso not found')


def solve4(m,rhs):
    rows=[list(row)+[rhs[i]] for i,row in enumerate(m)]
    for col in range(4):
        p=next((i for i in range(col,4) if rows[i][col]),None)
        assert p is not None
        rows[col],rows[p]=rows[p],rows[col]
        inv=gf4pow(rows[col][col],2)
        rows[col]=[gf4mul(inv,v) for v in rows[col]]
        for j in range(4):
            if j!=col and rows[j][col]:
                v=rows[j][col]
                rows[j]=[x^gf4mul(v,y) for x,y in zip(rows[j],rows[col])]
    return [x[-1] for x in rows]


def reconstruct(sample,value,degree):
    if degree==2:
        # sample 0 means evaluation at z=0, 1 means evaluation at z=1,
        # sample 2 means infinity. degree-2 product coefficients:
        # P0 = y(0), P2 = y(inf), P1 = y(1) + P0 + P2;
        # mod z^2 = z+omega gives
        # c0 = P0 + omega*P2, c1=P1+P2=y(1)+P0.
        if sample==0: return value | (value<<2)
        if sample==1: return value<<2
        if sample==2: return gf4mul(2,value)
        raise ValueError('invalid sample')
    points=(0,1,2,3)
    m=[[gf4pow(x,j) for j in range(4)] for x in points]
    high=value if sample==4 else 0
    rhs=[(value if i==sample else 0) ^ gf4mul(high,gf4pow(x,4)) for i,x in enumerate(points)]
    p0,p1,p2,p3=solve4(m,rhs)
    return (p0^p3)|((p1^p3^high)<<2)|((p2^high)<<4)


def evaluation(linear_basis,sample,degree):
    if degree==2:
        a0=linear_basis&3; a1=(linear_basis>>2)&3
        if sample==0: return a0
        if sample==1: return a0^a1
        if sample==2: return a1
        raise ValueError('invalid sample')
    if sample==4: return (linear_basis>>4)&3
    point=(0,1,2,3)[sample]
    return (linear_basis&3)^gf4mul((linear_basis>>2)&3,point)^gf4mul((linear_basis>>4)&3,gf4pow(point,2))


def build_terms(n,mod):
    degree=n//2
    assert n in (4,6)
    fwd,inv,g=field_isomorphism(degree,mod)
    terms=[]
    for sample in range(2*degree-1):
        l0=sum(((evaluation(fwd[1<<i],sample,degree)>>0)&1)<<i for i in range(n))
        l1=sum(((evaluation(fwd[1<<i],sample,degree)>>1)&1)<<i for i in range(n))
        assert l0 and l1
        for mask,elem in ((l0,0b11),(l1,0b01),(l0^l1,0b10)):
            output=inv[reconstruct(sample,elem,degree)]
            terms.append((mask,mask,output))
    assert len(terms)==(9 if n==4 else 15)
    assert all(a and b and out for a,b,out in terms)
    for i in range(n):
        for j in range(n):
            measured=0
            for u,v,w in terms:
                if u>>i&v>>j&1: measured^=w
            assert measured==field_mul(1<<i,1<<j,n,mod),(i,j,measured,field_mul(1<<i,1<<j,n,mod))
    return terms,g

