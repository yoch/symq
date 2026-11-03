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

#print axioms restrict_extend
#print axioms finalBit_extend
#print axioms extend_restrict_final
#print axioms execute_satisfies
#print axioms satisfies_unique
#print axioms unique_model
end SymQFormal
