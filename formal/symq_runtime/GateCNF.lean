import Std

/-!
  Abstract Tseitin correctness for the AND/XOR clauses used by SymQ's
  hash-consed Boolean graph. All valuations and ALL finite gate lists.
  The Python encoder's refinement to this model remains a separate obligation.
-/
namespace SymQFormal

abbrev Valuation := Nat → Bool

structure Literal where
  node : Nat
  positive : Bool
  deriving DecidableEq, Repr

def positive (n : Nat) : Literal := ⟨n, true⟩
def negative (n : Nat) : Literal := ⟨n, false⟩
def complement (l : Literal) : Literal := ⟨l.node, !l.positive⟩

def value (v : Valuation) (l : Literal) : Bool :=
  if l.positive then v l.node else !(v l.node)

@[simp] theorem value_positive (v : Valuation) (n : Nat) :
    value v (positive n) = v n := rfl
@[simp] theorem value_negative (v : Valuation) (n : Nat) :
    value v (negative n) = !(v n) := rfl
@[simp] theorem value_complement (v : Valuation) (l : Literal) :
    value v (complement l) = !(value v l) := by
  cases l with
  | mk node s => cases s <;> simp [complement, value]

def clauseValue (v : Valuation) : List Literal → Bool
  | [] => false
  | l :: ls => value v l || clauseValue v ls

def cnfValue (v : Valuation) : List (List Literal) → Bool
  | [] => true
  | c :: cs => clauseValue v c && cnfValue v cs

def andCNF (z : Nat) (a b : Literal) : List (List Literal) :=
  [[negative z, a], [negative z, b], [positive z, complement a, complement b]]

def xorCNF (z : Nat) (a b : Literal) : List (List Literal) :=
  [[complement a, complement b, negative z],
   [a, b, negative z], [a, complement b, positive z],
   [complement a, b, positive z]]

theorem andCNF_exact (v : Valuation) (z : Nat) (a b : Literal) :
    cnfValue v (andCNF z a b) = (v z == (value v a && value v b)) := by
  simp only [andCNF, cnfValue, clauseValue, value_positive,
    value_negative, value_complement, Bool.or_false, Bool.and_true]
  cases hz : v z <;> cases ha : value v a <;> cases hb : value v b <;>
    simp [hz, ha, hb]

theorem xorCNF_exact (v : Valuation) (z : Nat) (a b : Literal) :
    cnfValue v (xorCNF z a b) = (v z == (value v a != value v b)) := by
  simp only [xorCNF, cnfValue, clauseValue, value_positive,
    value_negative, value_complement, Bool.or_false, Bool.and_true]
  cases hz : v z <;> cases ha : value v a <;> cases hb : value v b <;>
    simp [hz, ha, hb]

inductive Gate where
  | input (node : Nat)
  | andGate (node : Nat) (a b : Literal)
  | xorGate (node : Nat) (a b : Literal)
  deriving Repr

def gateCNF : Gate → List (List Literal)
  | .input _ => []
  | .andGate z a b => andCNF z a b
  | .xorGate z a b => xorCNF z a b

def gateMatches (v : Valuation) : Gate → Bool
  | .input _ => true
  | .andGate z a b => v z == (value v a && value v b)
  | .xorGate z a b => v z == (value v a != value v b)

theorem gateCNF_exact (v : Valuation) (g : Gate) :
    cnfValue v (gateCNF g) = gateMatches v g := by
  cases g with
  | input n => simp [gateCNF, gateMatches, cnfValue]
  | andGate z a b => simpa [gateCNF, gateMatches] using andCNF_exact v z a b
  | xorGate z a b => simpa [gateCNF, gateMatches] using xorCNF_exact v z a b

theorem cnfValue_append (v : Valuation) (cs ds : List (List Literal)) :
    cnfValue v (cs ++ ds) = (cnfValue v cs && cnfValue v ds) := by
  induction cs with
  | nil => simp [cnfValue]
  | cons c cs ih => simp [cnfValue, ih, Bool.and_assoc]

def encode (gs : List Gate) : List (List Literal) :=
  gs.flatMap gateCNF

def graphMatches (v : Valuation) (gs : List Gate) : Bool :=
  gs.all (gateMatches v)

/-- ALL finite gate sequences: their Tseitin CNF is satisfied precisely when
    EVERY gate is semantically satisfied, including complemented references. -/
theorem encode_exact (v : Valuation) (gs : List Gate) :
    cnfValue v (encode gs) = graphMatches v gs := by
  induction gs with
  | nil => rfl
  | cons g gs ih =>
    calc
      cnfValue v (encode (g :: gs))
          = cnfValue v (gateCNF g) && cnfValue v (encode gs) := by
              simp [encode, cnfValue_append]
      _ = gateMatches v g && graphMatches v gs := by
              rw [gateCNF_exact, ih]
      _ = graphMatches v (g :: gs) := rfl

/-- A genuinely unsatisfiable relational graph plus root assertion excludes any
    valuation satisfying every gate semantics and the root. No solver is used. -/
theorem unsat_excludes_gate_counterexample (gs : List Gate) (root : Literal)
    (hunsat : ∀ v : Valuation,
      cnfValue v (encode gs ++ [[root]]) = false)
    (v : Valuation) (hok : graphMatches v gs = true) :
    value v root = false := by
  have hcnf : cnfValue v (encode gs) = true := by
    rw [encode_exact]
    exact hok
  cases hr : value v root with
  | false => rfl
  | true =>
    have hbad : cnfValue v (encode gs ++ [[root]]) = true := by
      simp [cnfValue_append, hcnf, cnfValue, clauseValue, hr]
    have hfalse := hunsat v
    rw [hbad] at hfalse
    cases hfalse

#print axioms andCNF_exact
#print axioms xorCNF_exact
#print axioms encode_exact
#print axioms unsat_excludes_gate_counterexample
end SymQFormal
