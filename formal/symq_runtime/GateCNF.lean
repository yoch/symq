import Std

/-!
  Abstract Tseitin correctness for the AND/XOR clauses used by SymQ's
  hash-consed Boolean graph. This is a theorem about ALL finite graph gate
  constraint sequences, not merely a run of a SAT solver or a sample fixture.
  Linking the Python producer to this syntax is a separate refinement task.
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
  | mk node s => cases s <;> rfl

def clauseValue (v : Valuation) : List Literal → Bool
  | [] => false
  | l :: ls => value v l || clauseValue v ls

def cnfValue (v : Valuation) : List (List Literal) → Bool
  | [] => true
  | c :: cs => clauseValue v c && cnfValue v cs

-- These clauses follow Python Graph._clauses_for *including* signed edges.
def andCNF (z : Nat) (a b : Literal) : List (List Literal) :=
  [[negative z, a], [negative z, b], [positive z, complement a, complement b]]

def xorCNF (z : Nat) (a b : Literal) : List (List Literal) :=
  [[complement a, complement b, negative z],
   [a, b, negative z], [a, complement b, positive z],
   [complement a, b, positive z]]

theorem andCNF_iff (v : Valuation) (z : Nat) (a b : Literal) :
    cnfValue v (andCNF z a b) = true ↔ v z = (value v a && value v b) := by
  simp only [andCNF, cnfValue, clauseValue, value_positive,
    value_negative, value_complement, Bool.or_false, Bool.and_true]
  cases hz : v z <;> cases ha : value v a <;> cases hb : value v b <;>
    simp [hz, ha, hb]

theorem xorCNF_iff (v : Valuation) (z : Nat) (a b : Literal) :
    cnfValue v (xorCNF z a b) = true ↔ v z = (value v a != value v b) := by
  simp only [xorCNF, cnfValue, clauseValue, value_positive,
    value_negative, value_complement, Bool.or_false, Bool.and_true]
  cases hz : v z <;> cases ha : value v a <;> cases hb : value v b <;>
    simp [hz, ha, hb]

inductive Gate where
  | variable (node : Nat)
  | andGate (node : Nat) (a b : Literal)
  | xorGate (node : Nat) (a b : Literal)
  deriving Repr

def gateCNF : Gate → List (List Literal)
  | .variable _ => []
  | .andGate z a b => andCNF z a b
  | .xorGate z a b => xorCNF z a b

def gateHolds (v : Valuation) : Gate → Prop
  | .variable _ => True
  | .andGate z a b => v z = (value v a && value v b)
  | .xorGate z a b => v z = (value v a != value v b)

theorem gateCNF_iff (v : Valuation) (g : Gate) :
    cnfValue v (gateCNF g) = true ↔ gateHolds v g := by
  cases g with
  | variable n => simp [gateCNF, gateHolds, cnfValue]
  | andGate z a b => simpa [gateCNF, gateHolds] using andCNF_iff v z a b
  | xorGate z a b => simpa [gateCNF, gateHolds] using xorCNF_iff v z a b

theorem cnfValue_append (v : Valuation) (cs ds : List (List Literal)) :
    cnfValue v (cs ++ ds) = (cnfValue v cs && cnfValue v ds) := by
  induction cs with
  | nil => simp [cnfValue]
  | cons c cs ih => simp [cnfValue, ih, Bool.and_assoc]

def encode (gs : List Gate) : List (List Literal) :=
  gs.flatMap gateCNF

/-- All gates in an arbitrary finite graph are satisfied iff their concatenated
    Tseitin clauses are satisfied. No assumption about a finite sample is used. -/
theorem encode_iff (v : Valuation) (gs : List Gate) :
    cnfValue v (encode gs) = true ↔ gs.Forall (gateHolds v) := by
  induction gs with
  | nil => simp [encode, cnfValue]
  | cons g gs ih =>
    have hstep : cnfValue v (encode (g :: gs)) =
        (cnfValue v (gateCNF g) && cnfValue v (encode gs)) := by
      simp [encode, cnfValue_append]
    rw [hstep]
    constructor
    · intro h
      have hp := Bool.and_eq_true.mp h
      exact .cons ((gateCNF_iff v g).mp hp.1) (ih.mp hp.2)
    · intro hg
      cases hg with
      | cons hfirst hrest =>
        exact Bool.and_eq_true.mpr
          ⟨(gateCNF_iff v g).mpr hfirst, ih.mpr hrest⟩

/-- An UNSAT relational graph formula cannot hide a valuation satisfying all
    gate semantics and the claimed counterexample output. This uses no solver. -/
theorem unsat_excludes_gate_counterexample (gs : List Gate) (root : Literal)
    (hunsat : ∀ v : Valuation,
      cnfValue v (encode gs ++ [[root]]) = false)
    (v : Valuation) (hok : gs.Forall (gateHolds v)) :
    value v root = false := by
  have hcnf : cnfValue v (encode gs) = true := (encode_iff v gs).mpr hok
  cases hr : value v root with
  | false => exact hr
  | true =>
    have hbad : cnfValue v (encode gs ++ [[root]]) = true := by
      simp [cnfValue_append, hcnf, cnfValue, clauseValue, hr]
    have hfalse := hunsat v
    rw [hbad] at hfalse
    cases hfalse

#print axioms andCNF_iff
#print axioms xorCNF_iff
#print axioms encode_iff
#print axioms unsat_excludes_gate_counterexample

end SymQFormal
