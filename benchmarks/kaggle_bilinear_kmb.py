"""Small independent Kickmix KMB v2 parser and exact basis simulator.

This implements the wire operations directly from raw bytes, not by importing
workbench or bilinear_cert from the source dataset.
"""
import struct

MAGIC=bytes.fromhex('d750c7d5c329d326e3cc9f6834f2b8bf')


def parse(raw:bytes):
    if len(raw)<104 or raw[:16]!=MAGIC: raise ValueError('invalid KMB header')
    version,qubits,bits,nregs=struct.unpack_from('<4I',raw,16)
    if version!=2 or bits or nregs!=3: raise ValueError('unsupported KMB layout')
    counts=struct.unpack_from('<9Q',raw,32)
    pos=104
    registers={}
    def read(typ):
        nonlocal pos
        if pos+16>len(raw): raise ValueError('truncated packet header')
        found,size=struct.unpack_from('<QQ',raw,pos)
        if found!=typ or pos+16+size>len(raw): raise ValueError(f'bad packet {typ}')
        b=raw[pos+16:pos+16+size]
        pos+=16+size
        return b
    for _ in range(nregs):
        b=read(0)
        name_len,n=struct.unpack_from('<II',b)
        if len(b)!=8+name_len+4*n: raise ValueError('invalid register')
        name=b[8:8+name_len].decode('utf8')
        ids=struct.unpack_from(f'<{n}I',b,8+name_len)
        registers[name]=tuple((i & 0x7fffffff) for i in ids)
        if any(not i & (1<<31) for i in ids): raise ValueError('non-qubit register')
    op_data=read(1)
    if len(op_data)!=counts[0]: raise ValueError('invalid op count')
    s={}
    for typ,key,count in ((2,'qqq0',counts[1]),(3,'qqq1',counts[1]),(4,'qqq2',counts[1]),
                           (5,'qq0',counts[2]),(6,'qq1',counts[2]),(7,'q0',counts[3]),
                           (8,'b0',counts[4]),(9,'bc',counts[5])):
        b=read(typ)
        if len(b)!=count*4: raise ValueError(f'bad stream {key}')
        s[key]=struct.unpack(f'<{count}I',b)
    if len(read(10))!=counts[6]*16: raise ValueError('angles not supported')
    tag=read(11)
    if len(tag)<8: raise ValueError('bad tags')
    if pos!=len(raw): raise ValueError('trailing bytes')
    if registers!={'a':tuple(range(qubits//3)),
                   'b':tuple(range(qubits//3,2*qubits//3)),
                   't':tuple(range(2*qubits//3,qubits))}:
        raise ValueError('wrong register mapping')
    if s['q0'] or s['b0'] or s['bc']: raise ValueError('unsupported streams')
    j=k=0
    ops=[]
    for op in op_data:
        if op==6: continue
        if op==33 or op==34:
            a=s['qq0'][j];b=s['qq1'][j];j+=1
            if a>=qubits or b>=qubits or a==b: raise ValueError('invalid op')
            ops.append((op,a,b,-1))
        elif op==49:
            a=s['qqq0'][k];b=s['qqq1'][k];c=s['qqq2'][k];k+=1
            if min(a,b,c)<0 or max(a,b,c)>=qubits or len({a,b,c})<3: raise ValueError('invalid op')
            ops.append((op,a,b,c))
        else: raise ValueError(f'unknown operation {op}')
    if j!=len(s['qq0']) or k!=len(s['qqq0']): raise ValueError('unused streams')
    return qubits,ops


def simulate(ops:list[tuple[int,int,int,int]],state:int)->int:
    for op,a,b,c in ops:
        if op==33:
            state ^= ((state>>a)&1)<<b
        elif op==49:
            state ^= ((state>>a)&1 & (state>>b)&1)<<c
        else:
            assert op==34
            if ((state>>a)^(state>>b))&1: state ^= (1<<a)|(1<<b)
    return state


def encode(ops: list[tuple[int, int, int, int]], n: int) -> bytes:
    """Encode a strict no-ancilla KMB v2 with registers a, b, t."""
    if n not in (4, 6):
        raise ValueError("field width outside pinned corpus")
    out = bytearray(MAGIC)
    three = [op for op in ops if op[0] == 49]
    two = [op for op in ops if op[0] in (33, 34)]
    if len(three) + len(two) != len(ops):
        raise ValueError("unknown gate in KMB encoder")
    out.extend(struct.pack("<4I", 2, 3 * n, 0, 3))
    out.extend(struct.pack("<9Q", len(ops), len(three), len(two), 0, 0, 0, 0, 0, 0))

    def packet(kind: int, data: bytes) -> None:
        out.extend(struct.pack("<2Q", kind, len(data)))
        out.extend(data)

    for index, name in enumerate(("a", "b", "t")):
        indices = [0x80000000 | (index * n + i) for i in range(n)]
        raw = name.encode("ascii")
        packet(0, struct.pack("<2I", len(raw), n) + raw + struct.pack(f"<{n}I", *indices))
    packet(1, bytes(op[0] for op in ops))
    for typ, field in ((2, 1), (3, 2), (4, 3)):
        values = [op[field] for op in three]
        packet(typ, struct.pack(f"<{len(values)}I", *values))
    for typ, field in ((5, 1), (6, 2)):
        values = [op[field] for op in two]
        packet(typ, struct.pack(f"<{len(values)}I", *values))
    for typ in (7, 8, 9, 10):
        packet(typ, b"")
    packet(11, struct.pack("<Q", 0))
    return bytes(out)


def pivot_fanout(n: int, terms: list[tuple[int, int, int]]) -> list[tuple[int, int, int, int]]:
    """One CCX per tensor term, using an existing dirty target bit as fanout pivot.

    CX(p,k); CCX(u,v,p); CX(p,k) adds u*v to both bits even if p was dirty.
    All folded input parities are restored. No extra wires or measurements.
    """
    def cx(control: int, target: int) -> tuple[int, int, int, int]:
        return (33, control, target, -1)

    out: list[tuple[int, int, int, int]] = []
    for a_mask, b_mask, out_mask in terms:
        if not all(0 < v < (1 << n) for v in (a_mask, b_mask, out_mask)):
            raise ValueError("zero or out-of-range factor mask")
        ap = (a_mask & -a_mask).bit_length() - 1
        bp = (b_mask & -b_mask).bit_length() - 1
        tp = (out_mask & -out_mask).bit_length() - 1
        af = [i for i in range(n) if i != ap and (a_mask >> i) & 1]
        bf = [i for i in range(n) if i != bp and (b_mask >> i) & 1]
        tf = [i for i in range(n) if i != tp and (out_mask >> i) & 1]
        out.extend(cx(i, ap) for i in af)
        out.extend(cx(n + i, n + bp) for i in bf)
        out.extend(cx(2 * n + tp, 2 * n + i) for i in tf)
        out.append((49, ap, n + bp, 2 * n + tp))
        out.extend(cx(2 * n + tp, 2 * n + i) for i in tf)
        out.extend(cx(n + i, n + bp) for i in reversed(bf))
        out.extend(cx(i, ap) for i in reversed(af))
    return out
