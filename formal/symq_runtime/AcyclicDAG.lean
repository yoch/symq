import Std

/-!
  Well-typed append-only Boolean DAG semantics, with all child references
  restricted by Fin n to earlier nodes. The user-supplied input valuation
  determines one and only one full node valuation.

  Unlike formula CNF soundness this theorem is about executing an acyclic DAG;
  connecting the concrete Python Graph to this inductive model is a separate
  implementation-refinement obligation.
-/
namespace SymQFormal

abbrev InputBits := Nat → Bool
abbrev NodeBits (n : Nat) := Fin n → Bool

def signedRead (v : NodeBits n) (node : Fin n) (positive : Bool) : Bool :=
  if positive then v node else !(v node)

def extend (v : NodeBits n) (bit : Bool) : NodeBits (n+1) :=
  fun i => if h : i.val < n then v ⟨i.val, h⟩ else bit

def restrict (v : NodeBits (n+1)) : NodeBits n :=
  fun i => v i.castSucc

def finalBit (v : NodeBits (n+1)) : Bool :=
  v (Fin.last n)

theorem restrict_extend (v : NodeBits n) (bit : Bool) :
    restrict (extend v bit) = v := by
  funext i
  simp [restrict, extend, Fin.castSucc, i.isLt]

theorem finalBit_extend (v : NodeBits n) (bit : Bool) :
    finalBit (extend v bit) = bit := by
  simp [finalBit, extend, Fin.last]

theorem extend_restrict_final (v : NodeBits (n+1)) :
    extend (restrict v) (finalBit v) = v := by
  funext i
  by_cases h : i.val < n
  · simp [extend, h, restrict, Fin.castSucc]
  · have hn : i.val = n := by omega
    have eqi : i = Fin.last n := Fin.ext hn
    rw [eqi]
    simp [extend, finalBit, Fin.last]

/-- Every child is a Fin n reference, strictly earlier than the newly appended
    output. No separate future-child or cycle test is an unproved assumption. -/
inductive DAG : Nat → Type where
  | nil : DAG 0
  | input {n} (previous : DAG n) (source : Nat) : DAG (n+1)
  | andGate {n} (previous : DAG n)
      (a b : Fin n) (pa pb : Bool) : DAG (n+1)
  | xorGate {n} (previous : DAG n)
      (a b : Fin n) (pa pb : Bool) : DAG (n+1)

/-- Source-independent semantics of every node, in topological append order. -/
def execute {n : Nat} (dag : DAG n) (source : InputBits) : NodeBits n :=
  match dag with
  | .nil => fun i => Fin.elim0 i
  | .input previous key =>
      extend (execute previous source) (source key)
  | .andGate previous a b pa pb =>
      let earlier := execute previous source
      extend earlier (signedRead earlier a pa && signedRead earlier b pb)
  | .xorGate previous a b pa pb =>
      let earlier := execute previous source
      extend earlier (signedRead earlier a pa != signedRead earlier b pb)

/-- The defining equations, independent of the constructive evaluator.
    The prefix is checked against the projection of the whole valuation. -/
def satisfies {n : Nat} (dag : DAG n) (source : InputBits)
    (values : NodeBits n) : Prop :=
  match dag with
  | .nil => True
  | .input previous key =>
      satisfies previous source (restrict values) ∧
        finalBit values = source key
  | .andGate previous a b pa pb =>
      satisfies previous source (restrict values) ∧
        finalBit values =
          (signedRead (restrict values) a pa && signedRead (restrict values) b pb)
  | .xorGate previous a b pa pb =>
      satisfies previous source (restrict values) ∧
        finalBit values =
          (signedRead (restrict values) a pa != signedRead (restrict values) b pb)

/-- Existence: the executable semantics satisfies *every* defining equation. -/
theorem execute_satisfies {n : Nat} (dag : DAG n) (source : InputBits) :
    satisfies dag source (execute dag source) := by
  induction dag with
  | nil => trivial
  | input previous key ih =>
      simpa [execute, satisfies, restrict_extend, finalBit_extend] using ih
  | andGate previous a b pa pb ih =>
      simpa [execute, satisfies, restrict_extend, finalBit_extend] using ih
  | xorGate previous a b pa pb ih =>
      simpa [execute, satisfies, restrict_extend, finalBit_extend] using ih

/-- Uniqueness: no alternative auxiliary valuation can satisfy all gates
    for the same initial input assignment. -/
theorem satisfies_unique {n : Nat} (dag : DAG n) (source : InputBits)
    (values : NodeBits n) (h : satisfies dag source values) :
    values = execute dag source := by
  induction dag with
  | nil =>
      funext i
      exact Fin.elim0 i
  | input previous key ih =>
      change satisfies previous source (restrict values) ∧
        finalBit values = source key at h
      have hp := ih (restrict values) h.1
      calc
        values = extend (restrict values) (finalBit values) :=
          (extend_restrict_final values).symm
        _ = extend (execute previous source) (source key) := by rw [hp, h.2]
        _ = execute (.input previous key) source := rfl
  | andGate previous a b pa pb ih =>
      change satisfies previous source (restrict values) ∧
        finalBit values =
          (signedRead (restrict values) a pa && signedRead (restrict values) b pb) at h
      have hp := ih (restrict values) h.1
      have hout : finalBit values =
          (signedRead (execute previous source) a pa &&
            signedRead (execute previous source) b pb) := by
        simpa [hp] using h.2
      calc
        values = extend (restrict values) (finalBit values) :=
          (extend_restrict_final values).symm
        _ = extend (execute previous source)
              (signedRead (execute previous source) a pa &&
                signedRead (execute previous source) b pb) := by rw [hp, hout]
        _ = execute (.andGate previous a b pa pb) source := rfl
  | xorGate previous a b pa pb ih =>
      change satisfies previous source (restrict values) ∧
        finalBit values =
          (signedRead (restrict values) a pa != signedRead (restrict values) b pb) at h
      have hp := ih (restrict values) h.1
      have hout : finalBit values =
          (signedRead (execute previous source) a pa !=
            signedRead (execute previous source) b pb) := by
        simpa [hp] using h.2
      calc
        values = extend (restrict values) (finalBit values) :=
          (extend_restrict_final values).symm
        _ = extend (execute previous source)
              (signedRead (execute previous source) a pa !=
                signedRead (execute previous source) b pb) := by rw [hp, hout]
        _ = execute (.xorGate previous a b pa pb) source := rfl

/-- Strong principal theorem: every finite well-typed acyclic DAG and
    every input have exactly one auxiliary valuation satisfying its equations. -/
theorem unique_model {n : Nat} (dag : DAG n) (source : InputBits) :
    ∃ values : NodeBits n,
      satisfies dag source values ∧
        ∀ other : NodeBits n, satisfies dag source other → other = values := by
  refine ⟨execute dag source, execute_satisfies dag source, ?_⟩
  intro other h
  exact satisfies_unique dag source other h


/-- The three Boolean clauses of a signed AND gate, evaluated without a solver. -/
def andClauses (out a b : Bool) : Bool :=
  ((!out || a) && (!out || b)) && (out || !a || !b)

/-- The four Boolean clauses of a signed XOR gate. -/
def xorClauses (out a b : Bool) : Bool :=
  (((!a || !b || !out) && (a || b || !out)) &&
    (a || !b || out)) && (!a || b || out)

theorem andClauses_exact (out a b : Bool) :
    andClauses out a b = (out == (a && b)) := by
  cases out <;> cases a <;> cases b <;> decide

theorem xorClauses_exact (out a b : Bool) :
    xorClauses out a b = (out == (a != b)) := by
  cases out <;> cases a <;> cases b <;> decide

/-- An input-pin unit clause and the local 3/4-clause Tseitin encodings,
    conjoined recursively along the acyclic graph. A later bridge must relate
    this hierarchical view to the concrete *flat* Python clause serializer. -/
def pinnedCNF {n : Nat} (dag : DAG n) (source : InputBits)
    (values : NodeBits n) : Bool :=
  match dag with
  | .nil => true
  | .input previous key =>
      pinnedCNF previous source (restrict values) &&
        (finalBit values == source key)
  | .andGate previous a b pa pb =>
      pinnedCNF previous source (restrict values) &&
        andClauses (finalBit values)
          (signedRead (restrict values) a pa) (signedRead (restrict values) b pb)
  | .xorGate previous a b pa pb =>
      pinnedCNF previous source (restrict values) &&
        xorClauses (finalBit values)
          (signedRead (restrict values) a pa) (signedRead (restrict values) b pb)

/-- Soundness AND completeness, for *all* typed acyclic graphs and inputs.
    This proves the hierarchical 3/4-clause semantics, without trusting SAT. -/
theorem pinnedCNF_exact {n : Nat} (dag : DAG n) (source : InputBits)
    (values : NodeBits n) :
    pinnedCNF dag source values = true ↔ satisfies dag source values := by
  induction dag with
  | nil => simp [pinnedCNF, satisfies]
  | input previous key ih =>
      simp [pinnedCNF, satisfies, ih]
  | andGate previous a b pa pb ih =>
      simp [pinnedCNF, satisfies, ih, andClauses_exact]
  | xorGate previous a b pa pb ih =>
      simp [pinnedCNF, satisfies, ih, xorClauses_exact]

/-- Exactly one satisfying assignment of all encoded auxiliary gates and input
    pins exists for every well-typed acyclic graph. -/
theorem pinnedCNF_unique_model {n : Nat} (dag : DAG n) (source : InputBits) :
    ∃ values : NodeBits n,
      pinnedCNF dag source values = true ∧
        ∀ other : NodeBits n, pinnedCNF dag source other = true → other = values := by
  obtain ⟨values, hv, hu⟩ := unique_model dag source
  refine ⟨values, (pinnedCNF_exact dag source values).mpr hv, ?_⟩
  intro other hc
  exact hu other ((pinnedCNF_exact dag source other).mp hc)

/-- A correct UNSAT assertion on the encoded root excludes a true output from
    the unique run of the corresponding typed acyclic graph. -/
theorem pinnedCNF_root_unsat {n : Nat} (dag : DAG n) (source : InputBits)
    (root : Fin n)
    (hunsat : ∀ values : NodeBits n,
      pinnedCNF dag source values = true → values root = false) :
    (execute dag source) root = false := by
  exact hunsat _ ((pinnedCNF_exact dag source _).mpr (execute_satisfies dag source))

#print axioms andClauses_exact
#print axioms xorClauses_exact
#print axioms pinnedCNF_exact
#print axioms pinnedCNF_unique_model
#print axioms pinnedCNF_root_unsat


/-!
  Flattening bridge. We model the *actual semantic clauses* of Graph:
  signed physical node indices start at 2, the solver's true constant uses
  physical node 1, and an asserted root is a separate unit clause.
  Input pins are an augmentation for a fixed source assignment; the Python
  runtime normally leaves these variables free. The following theorem is about
  the data model, not the unverified Python serializer itself.
-/

structure FlatLiteral where
  node : Nat
  polarity : Bool
  deriving DecidableEq, Repr

def flatPositive (node : Nat) : FlatLiteral := ⟨node, true⟩
def flatNegative (node : Nat) : FlatLiteral := ⟨node, false⟩
def flatNegate (literal : FlatLiteral) : FlatLiteral :=
  ⟨literal.node, !literal.polarity⟩

def flatValue (v : InputBits) (l : FlatLiteral) : Bool :=
  if l.polarity then v l.node else !(v l.node)

@[simp] theorem flatValue_positive (v : InputBits) (node : Nat) :
    flatValue v (flatPositive node) = v node := rfl
@[simp] theorem flatValue_negative (v : InputBits) (node : Nat) :
    flatValue v (flatNegative node) = !(v node) := rfl

@[simp] theorem flatValue_negate (v : InputBits) (l : FlatLiteral) :
    flatValue v (flatNegate l) = !(flatValue v l) := by
  cases l with
  | mk node polarity => cases polarity <;> simp [flatNegate, flatValue]

def flatClause (v : InputBits) : List FlatLiteral → Bool
  | [] => false
  | l :: ls => flatValue v l || flatClause v ls

def flatCNFValue (v : InputBits) : List (List FlatLiteral) → Bool
  | [] => true
  | c :: cs => flatClause v c && flatCNFValue v cs

theorem flatCNF_append (v : InputBits) (a b : List (List FlatLiteral)) :
    flatCNFValue v (a ++ b) =
      (flatCNFValue v a && flatCNFValue v b) := by
  induction a with
  | nil => simp [flatCNFValue]
  | cons h t ih => simp [flatCNFValue, ih, Bool.and_assoc]

/-- Exactly the signed three-clause AND pattern of Graph._clauses_for. -/
def flatAnd (z : Nat) (a b : FlatLiteral) : List (List FlatLiteral) :=
  [[flatNegative z, a], [flatNegative z, b],
   [flatPositive z, flatNegate a, flatNegate b]]

/-- Exactly the signed four-clause XOR pattern of Graph._clauses_for. -/
def flatXor (z : Nat) (a b : FlatLiteral) : List (List FlatLiteral) :=
  [[flatNegate a, flatNegate b, flatNegative z],
   [a, b, flatNegative z], [a, flatNegate b, flatPositive z],
   [flatNegate a, b, flatPositive z]]

def flatPin (node : Nat) (expected : Bool) : List (List FlatLiteral) :=
  [[⟨node, expected⟩]]

theorem flatAnd_exact (v : InputBits) (z : Nat) (a b : FlatLiteral) :
    flatCNFValue v (flatAnd z a b) =
      andClauses (v z) (flatValue v a) (flatValue v b) := by
  cases hz : v z <;> cases ha : flatValue v a <;> cases hb : flatValue v b <;>
    simp [flatAnd, flatCNFValue, flatClause, flatValue_negate,
      flatValue_positive, flatValue_negative, andClauses, hz, ha, hb]

theorem flatXor_exact (v : InputBits) (z : Nat) (a b : FlatLiteral) :
    flatCNFValue v (flatXor z a b) =
      xorClauses (v z) (flatValue v a) (flatValue v b) := by
  cases hz : v z <;> cases ha : flatValue v a <;> cases hb : flatValue v b <;>
    simp [flatXor, flatCNFValue, flatClause, flatValue_negate,
      flatValue_positive, flatValue_negative, xorClauses, hz, ha, hb]

theorem flatPin_exact (v : InputBits) (node : Nat) (expected : Bool) :
    flatCNFValue v (flatPin node expected) = (v node == expected) := by
  cases expected <;> cases hn : v node <;>
    simp [flatPin, flatCNFValue, flatClause, flatValue, hn]

/-- Physical index n+2 corresponds to newly appended DAG node n.
    The constant 1 is reserved; a free input may be created after earlier gates. -/
def physicalNodeBits {n : Nat} (v : InputBits) : NodeBits n :=
  fun i => v (i.val + 2)

def flatChild {n : Nat} (i : Fin n) (polarity : Bool) : FlatLiteral :=
  ⟨i.val + 2, polarity⟩

def dagCount {n : Nat} (_ : DAG n) : Nat := n

theorem physical_restrict (v : InputBits) (n : Nat) :
    restrict (physicalNodeBits (n := n+1) v) =
      physicalNodeBits (n := n) v := rfl

theorem physical_final (v : InputBits) (n : Nat) :
    finalBit (physicalNodeBits (n := n+1) v) = v (n+2) := rfl

theorem flatChild_value (v : InputBits) (i : Fin n) (polarity : Bool) :
    flatValue v (flatChild i polarity) =
      signedRead (physicalNodeBits v) i polarity := rfl

theorem flatAnd_bridge (v : InputBits) (n : Nat)
    (a b : Fin n) (pa pb : Bool) :
    flatCNFValue v (flatAnd (n+2) (flatChild a pa) (flatChild b pb)) =
      andClauses (finalBit (physicalNodeBits (n := n+1) v))
        (signedRead (restrict (physicalNodeBits (n := n+1) v)) a pa)
        (signedRead (restrict (physicalNodeBits (n := n+1) v)) b pb) := by
  simpa only [physical_final, physical_restrict, flatChild_value] using
    (flatAnd_exact v (n+2) (flatChild a pa) (flatChild b pb))

theorem flatXor_bridge (v : InputBits) (n : Nat)
    (a b : Fin n) (pa pb : Bool) :
    flatCNFValue v (flatXor (n+2) (flatChild a pa) (flatChild b pb)) =
      xorClauses (finalBit (physicalNodeBits (n := n+1) v))
        (signedRead (restrict (physicalNodeBits (n := n+1) v)) a pa)
        (signedRead (restrict (physicalNodeBits (n := n+1) v)) b pb) := by
  simpa only [physical_final, physical_restrict, flatChild_value] using
    (flatXor_exact v (n+2) (flatChild a pa) (flatChild b pb))

/-- Flat, ordered clause list, with explicit input pins for a fixed valuation.
    The normal Graph solver leaves inputs FREE: these are extra query units. -/
def flatPinned {n : Nat} (dag : DAG n) (source : InputBits) :
    List (List FlatLiteral) :=
  match dag with
  | .nil => []
  | .input previous key =>
      flatPinned previous source ++
        flatPin (dagCount previous + 2) (source key)
  | .andGate previous a b pa pb =>
      flatPinned previous source ++
        flatAnd (dagCount previous + 2) (flatChild a pa) (flatChild b pb)
  | .xorGate previous a b pa pb =>
      flatPinned previous source ++
        flatXor (dagCount previous + 2) (flatChild a pa) (flatChild b pb)

/-- Soundness and completeness for a genuinely flat list of concrete signed
    clauses, over every finite well-typed DAG, source and physical valuation. -/
theorem flatPinned_exact (v source : InputBits) {n : Nat} (dag : DAG n) :
    flatCNFValue v (flatPinned dag source) =
      pinnedCNF dag source (physicalNodeBits v) := by
  induction dag with
  | nil => rfl
  | input previous key ih =>
      change flatCNFValue v
          (flatPinned previous source ++ flatPin (dagCount previous + 2) (source key)) =
        (pinnedCNF previous source (restrict (physicalNodeBits v)) &&
          (finalBit (physicalNodeBits v) == source key))
      rw [flatCNF_append, ih, flatPin_exact]
      rfl
  | andGate previous a b pa pb ih =>
      change flatCNFValue v
          (flatPinned previous source ++ flatAnd (dagCount previous + 2)
            (flatChild a pa) (flatChild b pb)) =
        (pinnedCNF previous source (restrict (physicalNodeBits v)) &&
          andClauses (finalBit (physicalNodeBits v))
            (signedRead (restrict (physicalNodeBits v)) a pa)
            (signedRead (restrict (physicalNodeBits v)) b pb))
      rw [flatCNF_append, ih, flatAnd_bridge]
      rfl
  | xorGate previous a b pa pb ih =>
      change flatCNFValue v
          (flatPinned previous source ++ flatXor (dagCount previous + 2)
            (flatChild a pa) (flatChild b pb)) =
        (pinnedCNF previous source (restrict (physicalNodeBits v)) &&
          xorClauses (finalBit (physicalNodeBits v))
            (signedRead (restrict (physicalNodeBits v)) a pa)
            (signedRead (restrict (physicalNodeBits v)) b pb))
      rw [flatCNF_append, ih, flatXor_bridge]
      rfl

/-- The constant-unit clause and root assumption are separate from the
    fully flattened gate+fixed-input clauses. -/
def flatQuery {n : Nat} (dag : DAG n) (source : InputBits)
    (root : FlatLiteral) : List (List FlatLiteral) :=
  [[flatPositive 1]] ++ flatPinned dag source ++ [[root]]

theorem flatQuery_exact (v source : InputBits) (dag : DAG n)
    (root : FlatLiteral) :
    flatCNFValue v (flatQuery dag source root) =
      (v 1 && pinnedCNF dag source (physicalNodeBits v) && flatValue v root) := by
  simp [flatQuery, flatCNF_append, flatPinned_exact,
    flatCNFValue, flatClause, Bool.and_assoc]


/-- Lift the finite DAG valuation into the SAT variable namespace. Other SAT
    variables are deliberately left false; node1 is pinned true as Graph expects.
    No solver, channel or Python implementation is involved in this definition. -/
def physicalFromNodes {n : Nat} (bits : NodeBits n) : InputBits :=
  fun node =>
    if node = 1 then true
    else if h : 2 ≤ node ∧ node < n + 2 then
      bits ⟨node - 2, by omega⟩
    else false

theorem physicalFromNodes_one {n : Nat} (bits : NodeBits n) :
    physicalFromNodes bits 1 = true := by
  simp [physicalFromNodes]

theorem physicalFromNodes_read {n : Nat} (bits : NodeBits n) :
    physicalNodeBits (physicalFromNodes bits) = bits := by
  funext i
  have hnot : i.val + 2 ≠ 1 := by omega
  have hbound : 2 ≤ i.val + 2 ∧ i.val + 2 < n + 2 := by omega
  simp [physicalNodeBits, physicalFromNodes, hnot, hbound]

/-- For a fixed source and an asserted physical DAG output, the FLAT SAT
    query is satisfiable iff the unique mathematical execution makes that
    signed output true. Both directions are proved for any finite DAG. -/
theorem flatQuery_sat_iff (dag : DAG n) (source : InputBits)
    (node : Fin n) (polarity : Bool) :
    (∃ physical : InputBits,
      flatCNFValue physical (flatQuery dag source (flatChild node polarity)) = true) ↔
        signedRead (execute dag source) node polarity = true := by
  constructor
  · rintro ⟨physical, hquery⟩
    rw [flatQuery_exact] at hquery
    have hpin : pinnedCNF dag source (physicalNodeBits physical) = true := by
      cases hp : pinnedCNF dag source (physicalNodeBits physical) with
      | false => simp [hp] at hquery
      | true => rfl
    have hroot : flatValue physical (flatChild node polarity) = true := by
      cases hr : flatValue physical (flatChild node polarity) with
      | false => simp [hr] at hquery
      | true => rfl
    have hsem := (pinnedCNF_exact dag source (physicalNodeBits physical)).mp hpin
    have heq := satisfies_unique dag source (physicalNodeBits physical) hsem
    rw [flatChild_value, heq] at hroot
    exact hroot
  · intro hroot
    let values := execute dag source
    let physical := physicalFromNodes values
    have hpin : pinnedCNF dag source values = true :=
      (pinnedCNF_exact dag source values).mpr (execute_satisfies dag source)
    have hconst : physical 1 = true := physicalFromNodes_one values
    have hprojection : physicalNodeBits physical = values := physicalFromNodes_read values
    have hroot' : flatValue physical (flatChild node polarity) = true := by
      rw [flatChild_value, hprojection]
      exact hroot
    refine ⟨physical, ?_⟩
    rw [flatQuery_exact, hconst, hprojection, hpin, hroot']
    rfl

/-- Exact decision theorem (not a proposed method): the FLAT pinned-source
    query is UNSAT precisely when the corresponding typed DAG output is false. -/
theorem flatQuery_unsat_iff (dag : DAG n) (source : InputBits)
    (node : Fin n) (polarity : Bool) :
    (∀ physical : InputBits,
      flatCNFValue physical (flatQuery dag source (flatChild node polarity)) = false) ↔
        signedRead (execute dag source) node polarity = false := by
  have hsat := flatQuery_sat_iff dag source node polarity
  constructor
  · intro hunsat
    cases hr : signedRead (execute dag source) node polarity with
    | false => rfl
    | true =>
      obtain ⟨physical, hyes⟩ := hsat.mpr hr
      have hno := hunsat physical
      rw [hyes] at hno
      cases hno
  · intro hfalse physical
    cases hc : flatCNFValue physical
        (flatQuery dag source (flatChild node polarity)) with
    | false => rfl
    | true =>
      have hroot := hsat.mp ⟨physical, hc⟩
      rw [hfalse] at hroot
      cases hroot


/-- The BASE runtime clause stream: no source-input pins. A free input creates
    no clauses (matching Graph._clauses_for for var nodes), unlike flatPinned.
    The [1] constant and queried root are added separately below. -/
def runtimeGateClauses {n : Nat} (dag : DAG n) : List (List FlatLiteral) :=
  match dag with
  | .nil => []
  | .input previous _key => runtimeGateClauses previous
  | .andGate previous a b pa pb =>
      runtimeGateClauses previous ++
        flatAnd (dagCount previous + 2) (flatChild a pa) (flatChild b pb)
  | .xorGate previous a b pa pb =>
      runtimeGateClauses previous ++
        flatXor (dagCount previous + 2) (flatChild a pa) (flatChild b pb)

/-- Unlike satisfies, input nodes are genuinely free in the SAT formula. -/
def runtimeMatches {n : Nat} (dag : DAG n) (bits : NodeBits n) : Bool :=
  match dag with
  | .nil => true
  | .input previous _key => runtimeMatches previous (restrict bits)
  | .andGate previous a b pa pb =>
      runtimeMatches previous (restrict bits) &&
        andClauses (finalBit bits)
          (signedRead (restrict bits) a pa) (signedRead (restrict bits) b pb)
  | .xorGate previous a b pa pb =>
      runtimeMatches previous (restrict bits) &&
        xorClauses (finalBit bits)
          (signedRead (restrict bits) a pa) (signedRead (restrict bits) b pb)

/-- Exact flattened UNPINNED runtime-gate clause semantics. -/
theorem runtimeGateClauses_exact (v : InputBits) (dag : DAG n) :
    flatCNFValue v (runtimeGateClauses dag) =
      runtimeMatches dag (physicalNodeBits v) := by
  induction dag with
  | nil => rfl
  | input previous _key ih =>
      change flatCNFValue v (runtimeGateClauses previous) =
        runtimeMatches previous (restrict (physicalNodeBits v))
      rw [ih]
      rfl
  | andGate previous a b pa pb ih =>
      change flatCNFValue v (runtimeGateClauses previous ++
          flatAnd (dagCount previous + 2) (flatChild a pa) (flatChild b pb)) =
        (runtimeMatches previous (restrict (physicalNodeBits v)) &&
          andClauses (finalBit (physicalNodeBits v))
            (signedRead (restrict (physicalNodeBits v)) a pa)
            (signedRead (restrict (physicalNodeBits v)) b pb))
      rw [flatCNF_append, ih, flatAnd_bridge]
      rfl
  | xorGate previous a b pa pb ih =>
      change flatCNFValue v (runtimeGateClauses previous ++
          flatXor (dagCount previous + 2) (flatChild a pa) (flatChild b pb)) =
        (runtimeMatches previous (restrict (physicalNodeBits v)) &&
          xorClauses (finalBit (physicalNodeBits v))
            (signedRead (restrict (physicalNodeBits v)) a pa)
            (signedRead (restrict (physicalNodeBits v)) b pb))
      rw [flatCNF_append, ih, flatXor_bridge]
      rfl

/-- Every legal source evaluation satisfies the UNPINNED gate constraints.
    No uniqueness of source input names is assumed for this direction. -/
theorem runtimeMatches_of_satisfies (dag : DAG n) (source : InputBits)
    (bits : NodeBits n) (h : satisfies dag source bits) :
    runtimeMatches dag bits = true := by
  induction dag with
  | nil => rfl
  | input previous key ih =>
      change satisfies previous source (restrict bits) ∧
        finalBit bits = source key at h
      change runtimeMatches previous (restrict bits) = true
      exact ih (restrict bits) h.1
  | andGate previous a b pa pb ih =>
      change satisfies previous source (restrict bits) ∧
        finalBit bits =
          (signedRead (restrict bits) a pa && signedRead (restrict bits) b pb) at h
      have hp := ih (restrict bits) h.1
      change (runtimeMatches previous (restrict bits) &&
          andClauses (finalBit bits)
            (signedRead (restrict bits) a pa)
            (signedRead (restrict bits) b pb)) = true
      simp [hp, andClauses_exact, h.2]
  | xorGate previous a b pa pb ih =>
      change satisfies previous source (restrict bits) ∧
        finalBit bits =
          (signedRead (restrict bits) a pa != signedRead (restrict bits) b pb) at h
      have hp := ih (restrict bits) h.1
      change (runtimeMatches previous (restrict bits) &&
          xorClauses (finalBit bits)
            (signedRead (restrict bits) a pa)
            (signedRead (restrict bits) b pb)) = true
      simp [hp, xorClauses_exact, h.2]

/-- Runtime SAT structure: [1] pins the always-true node, gate clauses are
    incremental/free-input, the root is a separate assumption-as-unit. -/
def runtimeQuery (dag : DAG n) (root : FlatLiteral) :
    List (List FlatLiteral) :=
  [[flatPositive 1]] ++ runtimeGateClauses dag ++ [[root]]

theorem runtimeQuery_exact (v : InputBits) (dag : DAG n)
    (root : FlatLiteral) :
    flatCNFValue v (runtimeQuery dag root) =
      (v 1 && runtimeMatches dag (physicalNodeBits v) && flatValue v root) := by
  simp [runtimeQuery, flatCNF_append, runtimeGateClauses_exact,
    flatCNFValue, flatClause, Bool.and_assoc]

/-- The runtime-shaped, UNPINNED graph query is sound: UNSAT forbids a
    counterexample on every coherent source input. There is deliberately no
    completeness claim for a DAG with repeated source variable names. -/
theorem runtimeQuery_unsat_sound (dag : DAG n)
    (node : Fin n) (polarity : Bool)
    (hunsat : ∀ physical : InputBits,
      flatCNFValue physical (runtimeQuery dag (flatChild node polarity)) = false)
    (source : InputBits) :
    signedRead (execute dag source) node polarity = false := by
  cases hr : signedRead (execute dag source) node polarity with
  | false => rfl
  | true =>
      let bits := execute dag source
      let physical := physicalFromNodes bits
      have hsem : satisfies dag source bits := execute_satisfies dag source
      have hgate : runtimeMatches dag bits = true :=
        runtimeMatches_of_satisfies dag source bits hsem
      have hroot : flatValue physical (flatChild node polarity) = true := by
        rw [flatChild_value, physicalFromNodes_read]
        exact hr
      have hconst : physical 1 = true := physicalFromNodes_one bits
      have hprojection : physicalNodeBits physical = bits :=
        physicalFromNodes_read bits
      have hyes : flatCNFValue physical
          (runtimeQuery dag (flatChild node polarity)) = true := by
        rw [runtimeQuery_exact, hconst, hprojection, hgate, hroot]
        rfl
      have hno := hunsat physical
      rw [hyes] at hno
      cases hno

/-- A deliberately ill-formed *input-name mapping* (but a typed acyclic DAG):
    two independent physical input nodes carry the same source key. This
    counterexample proves why runtime-UNSAT soundness is claimed in only one
    direction without a separate unique-input-key invariant. -/
def duplicateKeyDAG : DAG 3 :=
  DAG.xorGate (DAG.input (DAG.input DAG.nil 0) 0)
    ⟨0, by decide⟩ ⟨1, by decide⟩ true true

theorem duplicateKeySourceAlwaysZero (source : InputBits) :
    signedRead (execute duplicateKeyDAG source) ⟨2, by decide⟩ true = false := by
  change (source 0 != source 0) = false
  cases h : source 0 <;> decide

/-- The UNPINNED runtime clause model can nevertheless admit a spurious
    assignment: the duplicated input source key is represented by distinct
    SAT variables. The production Graph.var hash-conses input IDs instead. -/
theorem duplicateKeyUnpinnedSAT :
    ∃ physical : InputBits,
      flatCNFValue physical
        (runtimeQuery duplicateKeyDAG (flatChild (⟨2, by decide⟩ : Fin 3) true)) = true := by
  refine ⟨(fun node => node == 1 || node == 2 || node == 4), ?_⟩
  decide


/-!
  Source-name coherence for the unpinned Graph SAT query.

  The previous universal UNSAT -> no-source-counterexample theorem did NOT
  require unique input keys. This section gives the reverse direction under
  a structural uniqueness guard, and retains the proved duplicate-key
  counterexample for why that guard cannot simply be omitted.

  This is about the Lean typed-DAG model; it does NOT formally certify that
  the Python Graph.var hash-consing implementation establishes the guard.
-/

def inputKeys : {n : Nat} → DAG n → List Nat
  | _, .nil => []
  | _, .input previous key => key :: inputKeys previous
  | _, .andGate previous _ _ _ _ => inputKeys previous
  | _, .xorGate previous _ _ _ _ => inputKeys previous

def uniqueInputKeys : {n : Nat} → DAG n → Prop
  | _, .nil => True
  | _, .input previous key =>
      uniqueInputKeys previous ∧ key ∉ inputKeys previous
  | _, .andGate previous _ _ _ _ => uniqueInputKeys previous
  | _, .xorGate previous _ _ _ _ => uniqueInputKeys previous

/-- Only constraints on input variables, without any gate equations. -/
def inputMatches : {n : Nat} → (dag : DAG n) → InputBits → NodeBits n → Prop
  | _, .nil, _, _ => True
  | _, .input previous key, source, bits =>
      inputMatches previous source (restrict bits) ∧
        finalBit bits = source key
  | _, .andGate previous _ _ _ _, source, bits =>
      inputMatches previous source (restrict bits)
  | _, .xorGate previous _ _ _ _, source, bits =>
      inputMatches previous source (restrict bits)

/-- Programs agreeing on all referenced input names satisfy the same input pins. -/
theorem inputMatches_congr (dag : DAG n) :
    ∀ (s t : InputBits) (bits : NodeBits n),
      (∀ key, key ∈ inputKeys dag → s key = t key) →
      inputMatches dag s bits → inputMatches dag t bits := by
  induction dag with
  | nil =>
      intro s t bits heq hm
      trivial
  | input previous key ih =>
      intro s t bits heq hm
      change inputMatches previous s (restrict bits) ∧ finalBit bits = s key at hm
      change inputMatches previous t (restrict bits) ∧ finalBit bits = t key
      constructor
      · apply ih s t (restrict bits)
        · intro j hj
          exact heq j (by simp [inputKeys, hj])
        · exact hm.1
      · rw [← heq key (by simp [inputKeys])]
        exact hm.2
  | andGate previous a b pa pb ih =>
      intro s t bits heq hm
      exact ih s t (restrict bits) heq hm
  | xorGate previous a b pa pb ih =>
      intro s t bits heq hm
      exact ih s t (restrict bits) heq hm

/-- When names are not repeated, every assignment to the physical input nodes
    can be represented by one consistent source valuation. -/
theorem source_exists_unique_keys (dag : DAG n) :
    ∀ bits : NodeBits n, uniqueInputKeys dag →
      ∃ source : InputBits, inputMatches dag source bits := by
  induction dag with
  | nil =>
      intro bits _
      exact ⟨fun _ => false, trivial⟩
  | input previous key ih =>
      intro bits hu
      change uniqueInputKeys previous ∧ key ∉ inputKeys previous at hu
      obtain ⟨source, hprev⟩ := ih (restrict bits) hu.1
      let updated : InputBits := fun j => if j = key then finalBit bits else source j
      have hpres : ∀ j, j ∈ inputKeys previous → source j = updated j := by
        intro j hj
        have hne : j ≠ key := by
          intro heq
          subst j
          exact hu.2 hj
        simp [updated, hne]
      refine ⟨updated, ?_⟩
      change inputMatches previous updated (restrict bits) ∧
        finalBit bits = updated key
      constructor
      · exact inputMatches_congr previous source updated
          (restrict bits) hpres hprev
      · simp [updated]
  | andGate previous a b pa pb ih =>
      intro bits hu
      obtain ⟨source, hprev⟩ := ih (restrict bits) hu
      exact ⟨source, hprev⟩
  | xorGate previous a b pa pb ih =>
      intro bits hu
      obtain ⟨source, hprev⟩ := ih (restrict bits) hu
      exact ⟨source, hprev⟩

/-- Free-input gate constraints plus correctly bound input pins imply the
    ordinary acyclic DAG semantics. There is no dependency on SAT. -/
theorem runtimeMatches_inputMatches (dag : DAG n) :
    ∀ (source : InputBits) (bits : NodeBits n),
      runtimeMatches dag bits = true →
      inputMatches dag source bits →
      satisfies dag source bits := by
  induction dag with
  | nil =>
      intro source bits _ _
      trivial
  | input previous key ih =>
      intro source bits hr hi
      change runtimeMatches previous (restrict bits) = true at hr
      change inputMatches previous source (restrict bits) ∧
        finalBit bits = source key at hi
      exact ⟨ih source (restrict bits) hr hi.1, hi.2⟩
  | andGate previous a b pa pb ih =>
      intro source bits hr hi
      change (runtimeMatches previous (restrict bits) &&
        andClauses (finalBit bits)
          (signedRead (restrict bits) a pa)
          (signedRead (restrict bits) b pb)) = true at hr
      have hp : runtimeMatches previous (restrict bits) = true := by
        cases h : runtimeMatches previous (restrict bits) with
        | false => simp [h] at hr
        | true => rfl
      have hout : finalBit bits =
          (signedRead (restrict bits) a pa && signedRead (restrict bits) b pb) := by
        cases hz : finalBit bits <;>
          cases ha : signedRead (restrict bits) a pa <;>
          cases hb : signedRead (restrict bits) b pb <;>
          simp [andClauses, hz, ha, hb] at hr ⊢
      exact ⟨ih source (restrict bits) hp hi, hout⟩
  | xorGate previous a b pa pb ih =>
      intro source bits hr hi
      change (runtimeMatches previous (restrict bits) &&
        xorClauses (finalBit bits)
          (signedRead (restrict bits) a pa)
          (signedRead (restrict bits) b pb)) = true at hr
      have hp : runtimeMatches previous (restrict bits) = true := by
        cases h : runtimeMatches previous (restrict bits) with
        | false => simp [h] at hr
        | true => rfl
      have hout : finalBit bits =
          (signedRead (restrict bits) a pa != signedRead (restrict bits) b pb) := by
        cases hz : finalBit bits <;>
          cases ha : signedRead (restrict bits) a pa <;>
          cases hb : signedRead (restrict bits) b pb <;>
          simp [xorClauses, hz, ha, hb] at hr ⊢
      exact ⟨ih source (restrict bits) hp hi, hout⟩

/-- With unique source keys, every satisfying unpinned physical model corresponds
    to a *real* source program execution with the requested signed root. -/
theorem runtimeQuery_sat_complete_unique_keys (dag : DAG n)
    (hunique : uniqueInputKeys dag)
    (node : Fin n) (polarity : Bool) :
    (∃ physical : InputBits,
      flatCNFValue physical
        (runtimeQuery dag (flatChild node polarity)) = true) →
    (∃ source : InputBits,
      signedRead (execute dag source) node polarity = true) := by
  rintro ⟨physical, hq⟩
  rw [runtimeQuery_exact] at hq
  have hgate : runtimeMatches dag (physicalNodeBits physical) = true := by
    cases hg : runtimeMatches dag (physicalNodeBits physical) with
    | false => simp [hg] at hq
    | true => rfl
  have hroot : flatValue physical (flatChild node polarity) = true := by
    cases hr : flatValue physical (flatChild node polarity) with
    | false => simp [hr] at hq
    | true => rfl
  obtain ⟨source, hinputs⟩ :=
    source_exists_unique_keys dag (physicalNodeBits physical) hunique
  have hsem :=
    runtimeMatches_inputMatches dag source
      (physicalNodeBits physical) hgate hinputs
  have heq := satisfies_unique dag source (physicalNodeBits physical) hsem
  rw [flatChild_value, heq] at hroot
  exact ⟨source, hroot⟩

/-- Conversely the runtime-shaped CNF is satisfiable precisely when some
    source input makes the output true, PROVIDED input names are unique. -/
theorem runtimeQuery_sat_iff_unique_keys (dag : DAG n)
    (hunique : uniqueInputKeys dag)
    (node : Fin n) (polarity : Bool) :
    (∃ physical : InputBits,
      flatCNFValue physical (runtimeQuery dag (flatChild node polarity)) = true) ↔
    (∃ source : InputBits,
      signedRead (execute dag source) node polarity = true) := by
  constructor
  · exact runtimeQuery_sat_complete_unique_keys dag hunique node polarity
  · rintro ⟨source, hr⟩
    let bits := execute dag source
    let physical := physicalFromNodes bits
    have hsem : satisfies dag source bits := execute_satisfies dag source
    have hgate : runtimeMatches dag bits = true :=
      runtimeMatches_of_satisfies dag source bits hsem
    have hroot : flatValue physical (flatChild node polarity) = true := by
      rw [flatChild_value, physicalFromNodes_read]
      exact hr
    have hconst : physical 1 = true := physicalFromNodes_one bits
    have hproject : physicalNodeBits physical = bits := physicalFromNodes_read bits
    refine ⟨physical, ?_⟩
    rw [runtimeQuery_exact, hconst, hproject, hgate, hroot]
    rfl

/-- Full UNSAT/output equivalence, with the necessary input-name guard. -/
theorem runtimeQuery_unsat_iff_unique_keys (dag : DAG n)
    (hunique : uniqueInputKeys dag)
    (node : Fin n) (polarity : Bool) :
    (∀ physical : InputBits,
      flatCNFValue physical
        (runtimeQuery dag (flatChild node polarity)) = false) ↔
    (∀ source : InputBits,
      signedRead (execute dag source) node polarity = false) := by
  have hsat := runtimeQuery_sat_iff_unique_keys dag hunique node polarity
  constructor
  · intro hunsat source
    cases hr : signedRead (execute dag source) node polarity with
    | false => rfl
    | true =>
        obtain ⟨physical, hyes⟩ := hsat.mpr ⟨source, hr⟩
        have hno := hunsat physical
        rw [hyes] at hno
        cases hno
  · intro hzero physical
    cases hc : flatCNFValue physical
        (runtimeQuery dag (flatChild node polarity)) with
    | false => rfl
    | true =>
        obtain ⟨source, hr⟩ := hsat.mp ⟨physical, hc⟩
        have hf := hzero source
        rw [hf] at hr
        cases hr


/-- The structural uniqueness condition used in the SAT/source completeness
    theorem is exactly list no-duplication of logical input names. This
    connects the Lean hypothesis to the independently checked source-name
    uniqueness in concrete Python snapshot data. -/
theorem uniqueInputKeys_iff_nodup (dag : DAG n) :
    uniqueInputKeys dag ↔ (inputKeys dag).Nodup := by
  induction dag with
  | nil => simp [uniqueInputKeys, inputKeys]
  | input previous key ih =>
      simp [uniqueInputKeys, inputKeys, ih, and_comm]
  | andGate previous a b pa pb ih =>
      simpa [uniqueInputKeys, inputKeys] using ih
  | xorGate previous a b pa pb ih =>
      simpa [uniqueInputKeys, inputKeys] using ih

#print axioms uniqueInputKeys_iff_nodup

#print axioms inputMatches_congr
#print axioms source_exists_unique_keys
#print axioms runtimeMatches_inputMatches
#print axioms runtimeQuery_sat_complete_unique_keys
#print axioms runtimeQuery_sat_iff_unique_keys
#print axioms runtimeQuery_unsat_iff_unique_keys

#print axioms duplicateKeySourceAlwaysZero
#print axioms duplicateKeyUnpinnedSAT

#print axioms runtimeGateClauses_exact
#print axioms runtimeMatches_of_satisfies
#print axioms runtimeQuery_exact
#print axioms runtimeQuery_unsat_sound

#print axioms physicalFromNodes_one
#print axioms physicalFromNodes_read
#print axioms flatQuery_sat_iff
#print axioms flatQuery_unsat_iff

#print axioms flatAnd_exact
#print axioms flatXor_exact
#print axioms flatPin_exact
#print axioms flatPinned_exact
#print axioms flatQuery_exact

#print axioms restrict_extend
#print axioms finalBit_extend
#print axioms extend_restrict_final
#print axioms execute_satisfies
#print axioms satisfies_unique
#print axioms unique_model
end SymQFormal
