import random
import unittest
from src.anf_backends import PackedRing,Sparse,ANFMachine,DegreeOverflow
from src.circuits import gf12_instructions,parse_kmx_subset
from src.field_phase import inverse_factorized, gf_inverse_or_zero,eval_masked_phase,flat_terms,gf_mul

class ANFTests(unittest.TestCase):
    def test_roundtrip_monomials(self):
        for n in (3,5,8):
            for degree in (0,1,2,min(n,3)):
                ring=PackedRing(n,degree)
                for ix,m in enumerate(ring.masks):
                    self.assertEqual(ring.decode(1<<ix).terms, frozenset([m]))
                    self.assertEqual(ring.encode(Sparse(frozenset([m]))),1<<ix)

    def test_exact_idempotent_multiplication(self):
        rng=random.Random(127)
        for n in (4,6,8):
            ring=PackedRing(n,n)
            for _ in range(250):
                pa=Sparse(frozenset(m for m in range(1<<n) if rng.random()<0.09))
                pb=Sparse(frozenset(m for m in range(1<<n) if rng.random()<0.09))
                self.assertEqual(ring.decode(ring.mul(ring.encode(pa),ring.encode(pb))),pa*pb)
                self.assertEqual(ring.decode(ring.encode(pa)^ring.encode(pb)),pa^pb)

    def test_fail_closed_high_degree(self):
        ring=PackedRing(5,2)
        with self.assertRaises(DegreeOverflow):ring.mul(ring.vars[0]*1,ring.encode(Sparse(frozenset([6]))))
        with self.assertRaises(DegreeOverflow):ring.encode(Sparse(frozenset([7])))

    def test_gf12_basis_oracle(self):
        # Independent carryless polynomial multiplication followed by long division.
        def slow_mul(a,b):
            value=0
            for bit in range(12):
                if b & (1<<bit):value ^= a<<bit
            while value.bit_length()>12:
                value ^= 0x1053 << (value.bit_length()-13)
            return value
        for i in range(12):
            for j in range(12):
                self.assertEqual(gf_mul(1<<i,1<<j), slow_mul(1<<i,1<<j))
        rng=random.Random(9107)
        for _ in range(2000):
            a,b=rng.randrange(4096),rng.randrange(4096)
            self.assertEqual(gf_mul(a,b),slow_mul(a,b))
        self.assertEqual(gf_mul(0xFFF,0),0)

    def test_gf12_machine_vs_oracle(self):
        ops=gf12_instructions(echo_pairs=48,with_hmr=True)
        a=ANFMachine(36,tuple(range(36)),backend='sparse')
        b=ANFMachine(36,tuple(range(36)),backend='packed')
        for m in range(12):
            a.new_classical(f'm{m}');b.new_classical(f'm{m}')
        for op in ops:
            a.step(*op);b.step(*op)
            self.assertEqual(a.snapshot(),b.snapshot())
        self.assertFalse(any(a.get(j).terms for j in range(36,49)))
        self.assertNotIn(b.classical['h0'],b.phase.data)
        rng=random.Random(441)
        for _ in range(80):
            x,y,c,m=[rng.randrange(4096) for _ in range(4)]
            raw=x | (y<<12) | (c<<24)
            output=0
            for k in range(12):
                output |= a.get(24+k).eval(raw)<<k
            self.assertEqual(output, c ^ gf_mul(x,y))
            phase=0
            for mask,p in a.phase.as_sparse().items():
                # No outcome key should survive the cancelled HMR gadget.
                self.assertEqual(mask.bit_count(),1)
                bit=mask.bit_length()-1
                self.assertLess(bit,12)
                if (m>>bit)&1:phase ^= p.eval(raw)
            self.assertEqual(phase,((output&m).bit_count()&1))

    def test_phase_mutation_is_detected(self):
        good=gf12_instructions(with_hmr=False)
        def execute(ops):
            a=ANFMachine(36,tuple(range(36)))
            for i in range(12):a.new_classical(f'm{i}')
            return a.execute(ops).snapshot()
        bad=good.copy()
        index=next(i for i,op in enumerate(bad) if op[0]=='Z')
        bad.pop(index)
        self.assertNotEqual(execute(good),execute(bad))

    def test_unsupported_rejected(self):
        m=ANFMachine(2,(0,1),backend='packed')
        with self.assertRaisesRegex(ValueError,'unsupported'):m.step('R',(0,))
        with self.assertRaisesRegex(ValueError,'conditional data'):m.step('CX',(0,1),'mask')
        with self.assertRaises(ValueError):parse_kmx_subset('QFT q0')

    def test_hmr_cancellation(self):
        seq=[('CCX',(0,1,2),None,None),('HMR',(2,),None,'h'),('CZ',(0,1),'h',None)]
        a=ANFMachine(2,(0,1),backend='sparse').execute(seq)
        b=ANFMachine(2,(0,1),backend='packed').execute(seq)
        self.assertEqual(a.snapshot(),b.snapshot())
        self.assertEqual(a.phase.as_sparse(),{})
        self.assertEqual(a.get(2),Sparse())
        # A missing feed-forward phase leaves a symbolic measurement dependency.
        faulty=ANFMachine(2,(0,1),backend='sparse').execute(seq[:-1])
        self.assertNotEqual(a.snapshot(),faulty.snapshot())
        self.assertEqual(len(faulty.phase.data),1)
        with self.assertRaises(ValueError):a.step('HMR',(0,),None,'illegal')

class FactorizedPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.factor=inverse_factorized()
    def test_all_inverses_oracle(self):
        for x in range(4096):
            expected=gf_inverse_or_zero(x)
            reconstructed=sum(((sum(((c>>s)&1) for s in self.subsets(x))&1)<<k) for k,c in enumerate(self.factor))
            self.assertEqual(expected,reconstructed)
    @staticmethod
    def subsets(x):
        sub=x
        while True:
            yield sub
            if not sub:break
            sub=(sub-1)&x
    def test_factorized_flat_terms_and_masked_phase(self):
        terms=flat_terms(self.factor)
        self.assertGreater(len(terms),10000)
        self.assertEqual(len(terms),sum(p.bit_count() for p in self.factor))
        rng=random.Random(18)
        for _ in range(200):
            x,m=rng.randrange(4096),rng.randrange(4096)
            self.assertEqual(eval_masked_phase(self.factor,x,m),((gf_inverse_or_zero(x)&m).bit_count()&1))

if __name__=='__main__':unittest.main()

class RealAdapterTests(unittest.TestCase):
    def test_git_blob_sha_and_differential_parser(self):
        from pathlib import Path
        import tempfile
        from tools.replay_qant_fixture import git_blob_sha,run
        data=b'X q0\nCX q0 q2\nCZ q0 q1\nHMR q2 b1\nCZ q0 q1 if b1\n'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'test.kmx';p.write_bytes(data)
            sha=git_blob_sha(data)
            r=run(str(p),sha,inputs=2,degree=2)
            self.assertEqual(r['operations'],5)
            self.assertEqual(r['snapshot_checks'],5)
            with self.assertRaisesRegex(ValueError,'SHA mismatch'):run(str(p),'0'*40,inputs=2)
